"""
Step 3（選用）：對 .md 中的 <image path="..." /> 呼叫 Ollama VLM 產生 caption，插回 tag 下方。

流程：先對圖片做 OCR（RapidOCR / pytesseract）→ 將 OCR 結果注入 prompt → Ollama 產生結構化 caption

在 config.py 設定：
- OLLAMA_BASE_URL：家裡 "http://127.0.0.1:11434"（不加 /v1），公司 "http://t2c2ap6:9999/v1"（要加 /v1）
- OLLAMA_MODEL：如 qwen3-vl:8b
"""
import re
import sys
from pathlib import Path
from base64 import b64encode
from io import BytesIO

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import PROCESSED_MD_DIR, OLLAMA_BASE_URL, OLLAMA_MODEL

# <image path="..." /> 與其後至下一個 <image 或結尾的整段（含舊 caption）
# 用 (?=...) 確保吃掉舊 caption，避免重跑時殘留
IMAGE_TAG = re.compile(
    r'<image\s+path="([^"]+)"\s*/>\s*[\s\S]*?(?=\s*<image\s+path=|\Z)',
    re.MULTILINE | re.DOTALL,
)


def run_ocr_on_image(image_path: Path) -> str:
    """對圖片執行 OCR，回傳文字。先試 RapidOCR，失敗則試 pytesseract。"""
    text = ""
    try:
        from rapidocr import RapidOCR

        ocr = RapidOCR()
        result = ocr(str(image_path))
        if result and hasattr(result, "txts") and result.txts:
            text = "\n".join(result.txts).strip()
    except Exception:
        pass
    if not text:
        try:
            from PIL import Image
            import pytesseract

            img = Image.open(image_path)
            text = pytesseract.image_to_string(img, lang="chi_sim+eng").strip()
        except Exception:
            pass
    return text


def build_prompt_with_ocr(base_prompt: str, ocr_text: str, ocr_section_template: str) -> str:
    """若有 OCR 結果，注入到 prompt 中；否則僅使用 base prompt。"""
    if not ocr_text or not ocr_text.strip():
        return base_prompt
    return base_prompt + ocr_section_template.format(ocr_text=ocr_text.strip())


def _caption_ollama(image_path: Path, prompt: str, base_url: str, model: str) -> str:
    """使用 Ollama（OpenAI 相容 API）產生 caption"""
    try:
        from openai import OpenAI
        from PIL import Image

        client = OpenAI(base_url=base_url, api_key="ollama")
        pil = Image.open(image_path).convert("RGB")
        buf = BytesIO()
        pil.save(buf, format="JPEG")
        b64 = b64encode(buf.getvalue()).decode("utf-8")
        content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ]
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": content}],
        )
        return (r.choices[0].message.content or "").strip() or "[No caption]"
    except Exception as e:
        return f"[VLM error: {e}]"


CAPTION_STUB = "[無法產生]"


def process_md_file(md_path: Path, images_base: Path, base_prompt: str, ocr_section: str) -> bool:
    """對單一 .md 內所有 <image path="..." /> 插上 VLM caption。先 OCR，再 Ollama。
    會完整覆寫舊 caption（匹配至下一個 <image 或結尾）。若 VLM 失敗只寫 stub，不寫錯誤進 md。"""
    text = md_path.read_text(encoding="utf-8")
    changed = False

    def repl(match: re.Match) -> str:
        nonlocal changed
        rel_path = match.group(1).strip()
        abs_path = (md_path.parent / rel_path).resolve()
        if not abs_path.exists():
            return match.group(0)
        try:
            ocr_text = run_ocr_on_image(abs_path)
            full_prompt = build_prompt_with_ocr(base_prompt, ocr_text, ocr_section)
            caption = _caption_ollama(abs_path, full_prompt, OLLAMA_BASE_URL, OLLAMA_MODEL)
            if caption.startswith("[VLM error:"):
                print(f"  [WARN] VLM 失敗 {abs_path.name}: {caption}")
                caption = CAPTION_STUB
        except Exception as e:
            print(f"  [WARN] VLM 異常 {abs_path.name}: {e}")
            caption = CAPTION_STUB
        changed = True
        return f'<image path="{rel_path}" />\n*Caption: {caption}*'

    new_text = IMAGE_TAG.sub(repl, text)
    if changed:
        md_path.write_text(new_text, encoding="utf-8")
    return changed


def main():
    try:
        from prompt.VLM_prompt import VLM_PROMPT_BASE, VLM_PROMPT_OCR_SECTION
    except Exception:
        from prompt.VLM_prompt import VLM_PROMPT_BASE

        VLM_PROMPT_OCR_SECTION = "\n\n---\n## Provided OCR text\n{ocr_text}\n"

    print(f"Ollama: {OLLAMA_BASE_URL} / {OLLAMA_MODEL}，流程: 先 OCR 再 VLM caption")

    md_files = [f for f in PROCESSED_MD_DIR.glob("*.md") if not f.name.endswith("_meta.md")]
    if not md_files:
        print(f"在 {PROCESSED_MD_DIR} 沒有找到 .md 檔案，請先執行 Step1 與 Step2")
        return

    for md_path in md_files:
        stem = md_path.stem
        images_base = PROCESSED_MD_DIR / "images" / stem
        if process_md_file(md_path, images_base, VLM_PROMPT_BASE, VLM_PROMPT_OCR_SECTION):
            print(f"已寫入 caption: {md_path.name}")
        else:
            print(f"無須變更: {md_path.name}")
    print("完成.")


if __name__ == "__main__":
    main()
