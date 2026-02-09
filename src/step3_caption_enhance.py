"""
Step 3（選用）：對 .md 中的 <image path="..." /> 呼叫 VLM 產生 caption，插回 tag 下方。

流程：先對圖片做 OCR（RapidOCR / pytesseract）→ 將 OCR 結果注入 prompt → VLM 產生結構化 caption

支援 VLM 後端（在 config.py 切換）：
- gemini：家裡測試用，Google Gemini API
- ollama：公司自架，透過 URL 請求（OpenAI 相容）
"""
import re
import sys
from pathlib import Path
from base64 import b64encode
from io import BytesIO

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    PROCESSED_MD_DIR,
    VLM_PROVIDER,
    VLM_GEMINI,
    VLM_OLLAMA,
    VLM_OPENAI,
)

# <image path="..." /> 與可選的既有 *Caption: ...*
# 重跑時會覆寫既有 caption
IMAGE_TAG = re.compile(r'<image\s+path="([^"]+)"\s*/>(?:\s*\n\*Caption: [\s\S]*?\*)?', re.MULTILINE)


def run_ocr_on_image(image_path: Path) -> str:
    """對圖片執行 OCR，回傳文字。先試 RapidOCR，失敗則試 pytesseract。"""
    text = ""
    # 1) RapidOCR（對中文支援較好）
    try:
        from rapidocr import RapidOCR
        ocr = RapidOCR()
        result = ocr(str(image_path))
        if result and hasattr(result, "txts") and result.txts:
            text = "\n".join(result.txts).strip()
    except Exception:
        pass
    # 2) Fallback: pytesseract
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


def _caption_gemini(image_path: Path, prompt: str, cfg: dict) -> str:
    """使用 Google Gemini API 產生 caption。支援 google-generativeai 與 google-genai 兩套件。"""
    api_key = cfg.get("api_key") or ""
    model = cfg.get("model", "gemini-2.5-flash")
    if not api_key:
        return "[VLM error: 請在 config.py 的 VLM_GEMINI 填入 api_key]"
    try:
        from PIL import Image

        img = Image.open(image_path).convert("RGB")
        img_bytes = BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes.seek(0)
        img_b64 = b64encode(img_bytes.getvalue()).decode("utf-8")

        # 1) 嘗試 google-generativeai（較常見）
        try:
            import google.generativeai as genai

            genai.configure(api_key=api_key)
            model_obj = genai.GenerativeModel(model)
            response = model_obj.generate_content([prompt, img])
            text = response.text if response and response.text else ""
            return text.strip() or "[No caption]"
        except ImportError:
            pass

        # 2) 嘗試 google-genai（新 SDK）
        try:
            import google.genai as genai

            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=model,
                contents=[
                    {
                        "role": "user",
                        "parts": [
                            {"text": prompt},
                            {"inline_data": {"mime_type": "image/png", "data": img_b64}},
                        ],
                    }
                ],
            )
            text = response.text if response and response.text else ""
            return text.strip() or "[No caption]"
        except ImportError:
            pass

        return "[VLM error: 請安裝 google-generativeai 或 google-genai: pip install google-generativeai]"
    except Exception as e:
        return f"[VLM error: {e}]"


def _caption_ollama(image_path: Path, prompt: str, cfg: dict) -> str:
    """使用 Ollama（OpenAI 相容 API）產生 caption"""
    base_url = (cfg.get("base_url") or "http://localhost:11434/v1").rstrip("/")
    model = cfg.get("model", "llava")
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


def _caption_openai(image_path: Path, prompt: str, cfg: dict) -> str:
    """使用 OpenAI 相容 API（DashScope、OpenAI 等）"""
    api_key = cfg.get("api_key") or ""
    base_url = cfg.get("base_url") or ""
    model = cfg.get("model", "gpt-4o")
    if not api_key:
        return "[VLM error: 請在 config.py 的 VLM_OPENAI 填入 api_key]"
    try:
        from openai import OpenAI
        from PIL import Image

        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        client = OpenAI(**kwargs)
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


def caption_image(image_path: Path, prompt: str) -> str:
    """依 config.VLM_PROVIDER 選擇後端產生 caption"""
    provider = (VLM_PROVIDER or "gemini").lower()
    if provider == "gemini":
        return _caption_gemini(image_path, prompt, VLM_GEMINI)
    if provider == "ollama":
        return _caption_ollama(image_path, prompt, VLM_OLLAMA)
    if provider == "openai":
        return _caption_openai(image_path, prompt, VLM_OPENAI)
    return f"[VLM error: 未知的 VLM_PROVIDER={VLM_PROVIDER}，請設為 gemini / ollama / openai]"


CAPTION_STUB = "[無法產生]"


def process_md_file(md_path: Path, images_base: Path, base_prompt: str, ocr_section: str) -> bool:
    """對單一 .md 內所有 <image path="..." /> 插上 VLM caption。先 OCR，再將結果注入 prompt 呼叫 VLM。
    若 VLM 失敗則只記錄 log，不將錯誤訊息寫入 md，改寫入 stub。"""
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
            caption = caption_image(abs_path, full_prompt)
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
    provider = (VLM_PROVIDER or "").lower()
    if provider not in ("gemini", "ollama", "openai"):
        print("請在 config.py 設定 VLM_PROVIDER 為 gemini、ollama 或 openai")
        return

    try:
        from prompt.VLM_prompt import VLM_PROMPT_BASE, VLM_PROMPT_OCR_SECTION
    except Exception:
        from prompt.VLM_prompt import VLM_PROMPT_BASE
        VLM_PROMPT_OCR_SECTION = "\n\n---\n## Provided OCR text\n{ocr_text}\n"

    print(f"使用 VLM 後端: {VLM_PROVIDER}，流程: 先 OCR 再 VLM caption")

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
