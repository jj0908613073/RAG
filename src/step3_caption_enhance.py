"""
Step 3（選用）：對 .md 中的 <image path="..." /> 呼叫 VLM 產生 caption，插回 tag 下方。

整合自 Docling2md：https://github.com/EvannZhongg/Docling2md
需設定 config_docling2md.yaml（VLM api_key / base_url / model）。
"""
import re
import sys
from pathlib import Path
from base64 import b64encode
from io import BytesIO

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import PROCESSED_MD_DIR, PROJECT_ROOT

# 選用：YAML 設定（VLM API）
try:
    import yaml
    _CONFIG_PATH = PROJECT_ROOT / "config_docling2md.yaml"
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            _DOCLING2MD_CONFIG = yaml.safe_load(f)
    else:
        _DOCLING2MD_CONFIG = None
except Exception:
    _DOCLING2MD_CONFIG = None

# <image path="..." />
IMAGE_TAG = re.compile(r'<image\s+path="([^"]+)"\s*/>')


def get_vlm_client():
    """取得 OpenAI 相容的 VLM client（DashScope / 其他）。"""
    if not _DOCLING2MD_CONFIG or "VLM" not in _DOCLING2MD_CONFIG:
        return None
    vlm = _DOCLING2MD_CONFIG["VLM"]
    try:
        from openai import OpenAI
        return OpenAI(
            api_key=vlm.get("api_key", ""),
            base_url=vlm.get("base_url", ""),
        ), vlm.get("model", "qwen2.5-vl-72b-instruct")
    except Exception:
        return None


def caption_image_with_vlm(image_path: Path, prompt: str, client, model: str) -> str:
    """傳入圖片路徑與 prompt，回傳 VLM 產生的 caption。"""
    try:
        from PIL import Image
        pil = Image.open(image_path).convert("RGB")
        buf = BytesIO()
        pil.save(buf, format="JPEG")
        b64 = b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        return f"[Error loading image: {e}]"
    try:
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


def process_md_file(md_path: Path, images_base: Path, client, model: str, prompt: str) -> bool:
    """對單一 .md 內所有 <image path="..." /> 插上 VLM caption。"""
    text = md_path.read_text(encoding="utf-8")
    changed = False

    def repl(match: re.Match) -> str:
        nonlocal changed
        rel_path = match.group(1).strip()
        abs_path = (md_path.parent / rel_path).resolve()
        if not abs_path.exists():
            return match.group(0)
        caption = caption_image_with_vlm(abs_path, prompt, client, model)
        changed = True
        return f'<image path="{rel_path}" />\n*Caption: {caption}*'

    new_text = IMAGE_TAG.sub(repl, text)
    if changed:
        md_path.write_text(new_text, encoding="utf-8")
    return changed


def main():
    if _DOCLING2MD_CONFIG is None:
        print("未找到 config_docling2md.yaml，請複製 config_docling2md.yaml.example 並填入 VLM api_key / base_url / model")
        return
    out = get_vlm_client()
    if out is None:
        print("無法建立 VLM client，請檢查 config_docling2md.yaml 的 VLM 設定與 openai 套件")
        return
    client, model = out
    try:
        from prompt.VLM_prompt import VLM_PROMPT
    except Exception:
        VLM_PROMPT = "Describe the content of this image in one concise sentence. Output a short English description."
    md_files = [f for f in PROCESSED_MD_DIR.glob("*.md") if not f.name.endswith("_meta.md")]
    if not md_files:
        print(f"在 {PROCESSED_MD_DIR} 沒有找到 .md 檔案，請先執行 Step1 與 Step2")
        return
    for md_path in md_files:
        stem = md_path.stem
        images_base = PROCESSED_MD_DIR / "images" / stem
        if process_md_file(md_path, images_base, client, model, VLM_PROMPT):
            print(f"已寫入 caption: {md_path.name}")
        else:
            print(f"無須變更: {md_path.name}")
    print("完成.")


if __name__ == "__main__":
    main()
