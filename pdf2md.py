"""
PDF → Markdown + JSON（與 Docling2md 相同流程）

單一腳本：Docling 解析 → 依序處理表格（必要時 VLM 修復）、圖片（VLM caption）、
文字（可選斷字修復 + LLM 標題/段落判斷）→ 輸出 .md、.json、page/、圖表檔。

設定：config.py 路徑；config_docling2md.yaml 的 OPENAI / VLM / OCR / POPPLER。
"""
import logging
import time
import base64
import json
import re
import hashlib
from pathlib import Path
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor

import sys
sys.path.insert(0, str(Path(__file__).parent))

from config import PROJECT_ROOT, RAW_PDF_DIR, OUTPUT_BASE

# 載入 config_docling2md.yaml
try:
    import yaml
    _config_path = PROJECT_ROOT / "config_docling2md.yaml"
    if not _config_path.exists():
        print("請複製 config_docling2md.yaml.example 為 config_docling2md.yaml 並填入 API key")
        sys.exit(1)
    with open(_config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
except Exception as e:
    print(f"載入 config_docling2md.yaml 失敗: {e}")
    sys.exit(1)

# Docling
from docling_core.types.doc import PictureItem, TableItem
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    ThreadedPdfPipelineOptions,
    RapidOcrOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption

# Prompts
from prompt.VLM_prompt import VLM_PROMPT
from prompt.text_type_prompt import TEXT_TYPE_PROMPT
from prompt.table_repair_prompt import TABLE_REPAIR_PROMPT
from prompt.text_repair_prompt import TEXT_REPAIR_PROMPT

# 其他
import pandas as pd
from PIL import Image
from openai import OpenAI

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# === 設定（來自 config_docling2md.yaml）===
ENABLE_OCR = config.get("OCR", {}).get("enabled", False)
VLM_CFG = config.get("VLM", {})
TEXT_CFG = config.get("OPENAI", {})
VLM_API_KEY = VLM_CFG.get("api_key", "")
VLM_API_URL = VLM_CFG.get("base_url", "")
VLM_MODEL = VLM_CFG.get("model", "qwen2.5-vl-72b-instruct")
TEXT_API_KEY = TEXT_CFG.get("api_key", "")
TEXT_API_URL = TEXT_CFG.get("base_url", "")
TEXT_MODEL = TEXT_CFG.get("model", "deepseek-chat")
MAX_CONCURRENCY_VLM = VLM_CFG.get("max_concurrency", 3)
MAX_CONCURRENCY_TEXT = TEXT_CFG.get("max_concurrency", 10)


def generate_hash_from_file(file_path: Path) -> str:
    md5_hash = hashlib.md5()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            md5_hash.update(chunk)
    return md5_hash.hexdigest()


def convert_pdf_to_images(pdf_path: Path, output_dir: Path) -> None:
    """將 PDF 每頁轉成 PNG（需 poppler）。"""
    poppler_cfg = config.get("POPPLER", {})
    poppler_path = poppler_cfg.get("path") or ""
    if not poppler_path:
        log.warning("未設定 POPPLER.path，跳過匯出頁面圖")
        return
    try:
        from pdf2image import convert_from_path
    except ImportError:
        log.warning("未安裝 pdf2image，跳過匯出頁面圖")
        return
    page_dir = output_dir / "page"
    page_dir.mkdir(parents=True, exist_ok=True)
    pages = convert_from_path(pdf_path, dpi=300, poppler_path=str(poppler_path))
    for page_num, page in enumerate(pages, start=1):
        out_path = page_dir / f"page-{page_num}.png"
        page.save(out_path, "PNG")
        log.info(f"Saved page {page_num}: {out_path.name}")


def ask_table_from_image(pil_image: Image.Image, prompt: str = TABLE_REPAIR_PROMPT) -> str:
    try:
        buf = BytesIO()
        pil_image.save(buf, format="JPEG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        client = OpenAI(api_key=VLM_API_KEY, base_url=VLM_API_URL)
        content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ]
        r = client.chat.completions.create(model=VLM_MODEL, messages=[{"role": "user", "content": content}])
        return (r.choices[0].message.content or "").strip()
    except Exception as e:
        log.warning("Table image repair failed: %s", e)
        return "[Table repair failed]"


def ask_image_vlm_base64(pil_image: Image.Image, prompt: str = VLM_PROMPT) -> str:
    try:
        buf = BytesIO()
        pil_image.save(buf, format="JPEG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        client = OpenAI(api_key=VLM_API_KEY, base_url=VLM_API_URL)
        content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ]
        r = client.chat.completions.create(model=VLM_MODEL, messages=[{"role": "user", "content": content}])
        return (r.choices[0].message.content or "").strip()
    except Exception as e:
        log.warning("Image VLM failed: %s", e)
        return "[Image description failed]"


def needs_repair(text: str, threshold: int = 30) -> bool:
    matches = re.findall(r"[A-Za-z0-9,.\-()]{%d,}" % threshold, text)
    return len(matches) > 0


def ask_repair_text(text: str) -> str:
    try:
        client = OpenAI(api_key=TEXT_API_KEY, base_url=TEXT_API_URL)
        prompt = f"{TEXT_REPAIR_PROMPT}\n{text}"
        r = client.chat.completions.create(model=TEXT_MODEL, messages=[{"role": "user", "content": prompt}])
        return (r.choices[0].message.content or "").strip()
    except Exception as e:
        log.warning("Text repair failed: %s", e)
        return text


def ask_if_heading(text: str) -> str:
    try:
        client = OpenAI(api_key=TEXT_API_KEY, base_url=TEXT_API_URL)
        prompt = f"{TEXT_TYPE_PROMPT}\n{text}"
        r = client.chat.completions.create(model=TEXT_MODEL, messages=[{"role": "user", "content": prompt}])
        answer = (r.choices[0].message.content or "").strip().lower()
        return "heading" if "heading" in answer else "paragraph"
    except Exception as e:
        log.warning("Heading/paragraph check failed: %s", e)
        return "paragraph"


def split_table_image_rows(pil_img: Image.Image, row_height: int = 400) -> list:
    w, h = pil_img.size
    return [pil_img.crop((0, top, w, min(top + row_height, h))) for top in range(0, h, row_height)]


def merge_small_chunks(chunks: list, min_height: int = 300, min_width: int = 20) -> list:
    merged = []
    temp = None
    for ch in chunks:
        w, h = ch.size
        if h < min_height or w < min_width:
            if temp is None:
                temp = ch
            else:
                new_w = max(temp.width, ch.width)
                new_h = temp.height + ch.height
                new_img = Image.new("RGB", (new_w, new_h))
                new_img.paste(temp, (0, 0))
                new_img.paste(ch, (0, temp.height))
                temp = new_img
        else:
            if temp is not None:
                merged.append(temp)
                temp = None
            merged.append(ch)
    if temp is not None:
        if temp.height < min_height:
            pad = Image.new("RGB", (temp.width, max(temp.height, 20)))
            pad.paste(temp, (0, 0))
            merged.append(pad)
        else:
            merged.append(temp)
    return merged


def get_bbox(element):
    if hasattr(element, "prov") and element.prov:
        b = element.prov[0].bbox
        return {"left": b.l, "top": b.t, "right": b.r, "bottom": b.b, "coord_origin": str(getattr(b, "coord_origin", ""))}
    return None


def convert_pdf_to_markdown_with_images(input_pdf_path: Path) -> None:
    start = time.time()
    pdf_hash = generate_hash_from_file(input_pdf_path)
    output_dir = OUTPUT_BASE / pdf_hash
    output_dir.mkdir(parents=True, exist_ok=True)

    # Docling pipeline
    pipeline_options = ThreadedPdfPipelineOptions(
        images_scale=2.0,
        generate_picture_images=True,
        generate_page_images=True,
        generate_table_images=True,
    )
    if ENABLE_OCR:
        pipeline_options.do_ocr = True
        pipeline_options.ocr_options = RapidOcrOptions(force_full_page_ocr=True)

    doc_converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
    )
    conv_res = doc_converter.convert(str(input_pdf_path))
    document = conv_res.document

    convert_pdf_to_images(input_pdf_path, output_dir)

    markdown_lines_items = []
    json_data = []
    table_counter = 0
    picture_counter = 0
    futures = []
    vlm_executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENCY_VLM)
    text_executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENCY_TEXT)

    for element, level in document.iterate_items():
        bbox = get_bbox(element)
        if isinstance(element, TableItem):
            table_counter += 1
            table_image_path = output_dir / f"{pdf_hash}-table-{table_counter}.png"
            pil_img = element.get_image(document)
            if pil_img:
                pil_img.save(table_image_path, "PNG")
            try:
                table_df = element.export_to_dataframe()
            except Exception:
                table_df = None
            if table_df is None or table_df.shape[1] < 2 or (hasattr(table_df.columns, "is_unique") and not table_df.columns.is_unique):
                log.warning("Table %d structure abnormal, using VLM repair", table_counter)
                sub_images = split_table_image_rows(pil_img) if pil_img else []
                sub_images = merge_small_chunks(sub_images)
                full_md_lines = []
                for idx, chunk_img in enumerate(sub_images):
                    chunk_md = ask_table_from_image(chunk_img)
                    lines = chunk_md.splitlines()
                    if idx == 0:
                        full_md_lines.extend(lines)
                    else:
                        full_md_lines.extend(lines[2:])
                markdown_lines_items.append("\n" + "\n".join(full_md_lines))
                json_data.append({
                    "type": "table", "level": level, "image": table_image_path.name,
                    "source": "reconstructed_by_vlm_chunked", "markdown": "\n".join(full_md_lines),
                    "page_number": element.prov[0].page_no if element.prov else None, "bbox": bbox,
                })
            else:
                md_table = table_df.to_markdown(index=False)
                markdown_lines_items.append(md_table)
                json_data.append({
                    "type": "table", "level": level, "image": table_image_path.name,
                    "data": table_df.to_dict(orient="records"),
                    "page_number": element.prov[0].page_no if element.prov else None, "bbox": bbox,
                })

        elif isinstance(element, PictureItem):
            picture_counter += 1
            picture_path = output_dir / f"{pdf_hash}-picture-{picture_counter}.png"
            pil_img = element.get_image(document)
            if pil_img:
                pil_img.save(picture_path, "PNG")
            future = vlm_executor.submit(ask_image_vlm_base64, pil_img) if pil_img else None
            futures.append((future, "picture", {
                "image_path": picture_path, "level": level,
                "page": element.prov[0].page_no if element.prov else None, "bbox": bbox,
            }))
            markdown_lines_items.append(future)

        else:
            if hasattr(element, "text") and element.text:
                text = element.text.strip()
                if text:
                    if needs_repair(text):
                        text = ask_repair_text(text)
                    future = text_executor.submit(ask_if_heading, text)
                    futures.append((future, "text", {
                        "text": text, "level": level,
                        "page": element.prov[0].page_no if element.prov else None, "bbox": bbox,
                    }))
                    markdown_lines_items.append(future)

    results_map = {}
    for future, task_type, meta in futures:
        try:
            result = future.result() if future is not None else ""
            if task_type == "picture":
                caption = result or "[No caption]"
                results_map[future] = f"![{caption}](./{meta['image_path'].name})"
                json_data.append({
                    "type": "picture", "level": meta["level"], "image": meta["image_path"].name,
                    "caption": caption, "page_number": meta["page"], "bbox": meta["bbox"],
                })
            elif task_type == "text":
                label = result or "paragraph"
                md = f"# {meta['text']}" if label == "heading" else meta["text"]
                results_map[future] = md
                json_data.append({
                    "type": "text", "level": meta["level"], "text": meta["text"],
                    "label": label, "page_number": meta["page"], "bbox": meta["bbox"],
                })
        except Exception as e:
            log.warning("Concurrent task failed: %s", e)

    vlm_executor.shutdown(wait=True)
    text_executor.shutdown(wait=True)

    markdown_lines = []
    for item in markdown_lines_items:
        if isinstance(item, str):
            markdown_lines.append(item)
            markdown_lines.append("")
        elif hasattr(item, "result"):
            markdown_lines.append(results_map.get(item, ""))
            markdown_lines.append("")

    md_file = output_dir / f"{pdf_hash}.md"
    md_file.write_text("\n".join(markdown_lines), encoding="utf-8")
    json_file = output_dir / f"{pdf_hash}.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)

    log.info("Completed in %.2f s. Markdown: %s  JSON: %s", time.time() - start, md_file, json_file)


def process_multiple_pdfs():
    pdf_files = list(RAW_PDF_DIR.glob("*.pdf"))
    if not pdf_files:
        log.warning("No PDFs in %s", RAW_PDF_DIR)
        return
    log.info("Found %d PDFs in %s", len(pdf_files), RAW_PDF_DIR)
    for pdf_path in pdf_files:
        log.info("Processing: %s", pdf_path.name)
        try:
            convert_pdf_to_markdown_with_images(pdf_path)
        except Exception as e:
            log.exception("Failed %s: %s", pdf_path.name, e)


if __name__ == "__main__":
    process_multiple_pdfs()
