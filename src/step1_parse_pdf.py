"""
Step 1: 使用 Docling 解析多種文件格式（PDF、DOCX、PPTX、圖片等）並輸出 Markdown
"""
# Windows 需停用 symlinks，避免 [WinError 1314] 用戶端沒有這項特殊權限
import os

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import sys
import traceback
from pathlib import Path
from typing import List, Dict
import json

# 確保能導入 config
sys.path.append(str(Path(__file__).parent.parent))
from config import (
    RAW_DOCS_DIR,
    PROCESSED_MD_DIR,
    SUPPORTED_DOC_EXTENSIONS,
    DOCLING_LAYERED_MODE,
    USE_GRANITE_DOCLING,
    DOCLING_DEVICE,
    DOCLING_NUM_THREADS,
    DOCLING_MAX_PAGES,
    DOCLING_IMAGES_SCALE,
)

try:
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import ThreadedPdfPipelineOptions

except ImportError:
    print("❌ 請先安裝 docling: pip install docling")
    sys.exit(1)

if USE_GRANITE_DOCLING and not DOCLING_LAYERED_MODE:
    try:
        from docling.pipeline.vlm_pipeline import VlmPipeline
        from docling.datamodel.pipeline_options import VlmPipelineOptions
        from docling.datamodel.accelerator_options import AcceleratorOptions
    except ImportError as e:
        print("[WARN] Granite Docling 需 VLM 支援，改用預設解析:", e)
        USE_GRANITE_DOCLING = False

# 分層模式：Step2 會把 <!-- image --> 或 ![Image](...) 換成 <image path="..." />
try:
    from docling_core.types.doc.base import ImageRefMode
except ImportError:
    ImageRefMode = None

from table_dual_track import apply_table_dual_track


def _collect_doc_files(directory: Path) -> List[Path]:
    """收集目錄下所有支援格式的檔案"""
    files = []
    for ext in SUPPORTED_DOC_EXTENSIONS:
        files.extend(directory.glob(f"*{ext}"))
    return sorted(files, key=lambda p: p.name.lower())


class DocumentParser:
    """使用 Docling 解析多種文件格式（PDF、DOCX、PPTX、圖片等）的封裝類別"""

    def __init__(self):
        # 支援的格式（Docling 會依副檔名自動選擇對應 pipeline）
        allowed_formats = [
            InputFormat.PDF,
            InputFormat.DOCX,
            InputFormat.PPTX,
            InputFormat.XLSX,
            InputFormat.HTML,
            InputFormat.MD,
            InputFormat.CSV,
            InputFormat.IMAGE,
        ]
        format_options = {}

        if DOCLING_LAYERED_MODE:
            pdf_opts = ThreadedPdfPipelineOptions(
                generate_picture_images=True,
                generate_page_images=True,
                images_scale=DOCLING_IMAGES_SCALE,
            )
            format_options[InputFormat.PDF] = PdfFormatOption(pipeline_options=pdf_opts)
            print("[OK] 分層模式：多格式 Docling（PDF/DOCX/PPTX/圖片等 → Markdown）")
        elif USE_GRANITE_DOCLING:
            accel = AcceleratorOptions(device=DOCLING_DEVICE, num_threads=DOCLING_NUM_THREADS)
            format_options[InputFormat.PDF] = PdfFormatOption(
                pipeline_cls=VlmPipeline,
                pipeline_options=VlmPipelineOptions(accelerator_options=accel),
            )
            print(f"[OK] Granite Docling (VLM)，裝置: {DOCLING_DEVICE}")

        self.converter = DocumentConverter(
            allowed_formats=allowed_formats,
            format_options=format_options or {},
        )

    def parse_single_document(self, doc_path: Path) -> Dict:
        """解析單一文件（PDF、DOCX、PPTX、圖片等）"""
        print(f"📄 開始解析: {doc_path.name}")
        try:
            kwargs = {}
            # 僅 PDF 支援 page_range（限制頁數）
            if doc_path.suffix.lower() == ".pdf" and DOCLING_MAX_PAGES is not None:
                kwargs["page_range"] = (1, DOCLING_MAX_PAGES)
                print(f"   （僅前 {DOCLING_MAX_PAGES} 頁，測試用）")
            result = self.converter.convert(str(doc_path), **kwargs)

            from docling_core.types.doc import TableItem, PictureItem, TextItem

            try:
                from docling_core.types.doc import DocItemLabel
            except ImportError:
                try:
                    from docling_core.types.doc.labels import DocItemLabel
                except ImportError:
                    DocItemLabel = None

            table_counter = [0]
            elements = []
            for item, level in result.document.iterate_items():
                prov = item.prov[0] if item.prov else None
                bbox = prov.bbox if prov and hasattr(prov, "bbox") and prov.bbox else None

                # 依 label 區分 heading 與 paragraph
                label = "paragraph"
                if DocItemLabel is not None:
                    item_label = getattr(item, "label", None)
                    if item_label is not None:
                        if item_label in (DocItemLabel.SECTION_HEADER, DocItemLabel.TITLE):
                            label = "heading"
                # fallback：很短且不像句子 → heading 候選（DOCX/PPTX 常漏標）
                text = (getattr(item, "text", "") or "").strip()
                if label == "paragraph" and text:
                    if len(text) <= 40 and not any(p in text for p in "。.!?"):
                        label = "heading"

                element = {
                    "type": "text",
                    "level": level,
                    "text": getattr(item, "text", ""),
                    "label": label,
                    "page_number": getattr(prov, "page_no", None) if prov else None,
                    "bbox": {
                        "left": bbox.l, "top": bbox.t, "right": bbox.r, "bottom": bbox.b,
                        "coord_origin": "CoordOrigin.BOTTOMLEFT"
                    } if bbox else None
                }

                if isinstance(item, TableItem):
                    element["type"] = "table"
                    element["label"] = "table"
                    table_counter[0] += 1
                    element["table_id"] = f"{table_counter[0]:04d}"
                    try:
                        html_content = item.export_to_html(doc=result.document)
                        if html_content.strip() == "<table></table>" or not html_content:
                            element["text"] = item.export_to_markdown(doc=result.document)
                        else:
                            element["text"] = html_content
                    except Exception:
                        element["text"] = item.export_to_markdown(doc=result.document)

                elif isinstance(item, PictureItem):
                    element["type"] = "picture"
                    element["label"] = "picture"
                    element["image"] = f"{item.self_ref.split('/')[-1]}.png"
                    element["caption"] = getattr(item, "caption", "[Image description failed]")
                    element["text"] = element["caption"]

                # 過濾空 text element，避免雜訊
                if element["type"] == "text" and not (element.get("text") or "").strip():
                    continue
                elements.append(element)

            if DOCLING_LAYERED_MODE and ImageRefMode is not None:
                md_path = PROCESSED_MD_DIR / (doc_path.stem + ".md")
                (PROCESSED_MD_DIR / "images" / doc_path.stem).mkdir(parents=True, exist_ok=True)
                artifacts_dir = Path("images") / doc_path.stem
                result.document.save_as_markdown(
                    filename=md_path,
                    artifacts_dir=artifacts_dir,
                    image_mode=ImageRefMode.REFERENCED,
                )
                markdown_text = md_path.read_text(encoding="utf-8")
            else:
                markdown_text = result.document.export_to_markdown()

            metadata = {
                "source": doc_path.name,
                "num_pages": len(result.document.pages) if hasattr(result.document, "pages") else 0,
                "title": getattr(result.document, "title", doc_path.stem),
                "elements": elements,
            }

            return {
                "markdown": markdown_text,
                "metadata": metadata,
                "success": True
            }

        except Exception as e:
            print(f"❌ 解析失敗: {e}")
            traceback.print_exc()
            return {
                "markdown": "",
                "metadata": {},
                "success": False,
                "error": str(e)
            }
    def save_markdown(self, doc_path: Path, result: Dict):
        """儲存 Markdown 到檔案（含表格雙軌：HTML 保真 + TABLE_TEXT 檢索版）"""
        if not result["success"]:
            return

        output_path = PROCESSED_MD_DIR / (doc_path.stem + ".md")

        # 表格雙軌：placeholders + elements 回填 TABLE_HTML + TABLE_TEXT
        markdown_content = apply_table_dual_track(
            result["markdown"],
            result["metadata"].get("elements", []),
        )

        # 寫入格式化後的內容（分層模式和非分層模式都需要寫入）
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        print(f"✅ 已儲存: {output_path}")

        meta_path = PROCESSED_MD_DIR / (doc_path.stem + "_meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(result["metadata"], f, indent=2, ensure_ascii=False)
        print(f"📊 Metadata: {meta_path}")
    
    def parse_directory(self, max_files: int = None) -> List[Dict]:
        """批次解析目錄下所有支援格式的檔案"""
        doc_files = _collect_doc_files(RAW_DOCS_DIR)

        if not doc_files:
            print(f"⚠️  在 {RAW_DOCS_DIR} 找不到支援的檔案")
            print(f"   支援副檔名: {', '.join(SUPPORTED_DOC_EXTENSIONS)}")
            return []

        if max_files:
            doc_files = doc_files[:max_files]

        print(f"🔍 找到 {len(doc_files)} 個檔案 ({', '.join(p.suffix for p in doc_files[:5])}{'...' if len(doc_files) > 5 else ''})")

        results = []
        for doc_path in doc_files:
            result = self.parse_single_document(doc_path)
            if result["success"]:
                self.save_markdown(doc_path, result)
            results.append(result)
        
        # 統計
        success_count = sum(1 for r in results if r["success"])
        print(f"\n📈 完成: {success_count}/{len(results)} 個檔案成功解析")
        
        return results


def main():
    """主程式 - 測試解析功能"""
    print("=" * 60)
    print("Step 1: 多格式文件解析（PDF / DOCX / PPTX / 圖片等）")
    print("=" * 60)

    parser = DocumentParser()

    doc_files = _collect_doc_files(RAW_DOCS_DIR)
    if not doc_files:
        print(f"\n⚠️  請先將文件放到: {RAW_DOCS_DIR}")
        print(f"   支援副檔名: {', '.join(SUPPORTED_DOC_EXTENSIONS)}")
        return

    print(f"\n🚀 開始解析所有檔案...")
    results = parser.parse_directory(max_files=None)
    
    if results and results[0]["success"]:
        print("\n" + "=" * 60)
        print("✅ 解析成功！可以查看生成的 Markdown 檔案")
        print(f"輸出目錄: {PROCESSED_MD_DIR}")
        print("=" * 60)
    

if __name__ == "__main__":
    main()