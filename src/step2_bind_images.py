"""
Step 2：把 .md 裡的圖片標記統一成 <image path="..." />

- 若 Step1 用 REFERENCED：md 裡已是 ![Image](path)，依序替換成 <image path="path" />
- 若 md 裡是 <!-- image -->：依序對應到 images/{doc_stem}/ 下的檔案，替換成 <image path="..." />
之後可再對 <image ... /> 做 VLM caption，插回下方。
"""
import re
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from config import PROCESSED_MD_DIR

# 圖片 placeholder（Docling 預設）
IMAGE_PLACEHOLDER = "<!-- image -->"
# 目標 tag 格式
IMAGE_TAG_PATTERN = re.compile(r'!\[Image\]\(([^)]+)\)')


def bind_images_in_md(md_path: Path, images_dir: Path) -> str:
    """
    讀取 .md，將 ![Image](path) 換成 <image path="path" />；
    若有 <!-- image -->，依序對應 images_dir 內檔案並替換。
    """
    text = md_path.read_text(encoding="utf-8")
    out = text

    # 1) 先將 ![Image](path) 換成 <image path="path" />
    def repl_ref(match: re.Match) -> str:
        path = match.group(1).strip()
        return f'<image path="{path}" />'
    out = IMAGE_TAG_PATTERN.sub(repl_ref, out)

    # 2) 若還有 <!-- image -->，依序綁定到 images_dir 內的檔案（依檔名字母序）
    if IMAGE_PLACEHOLDER in out:
        if not images_dir.is_dir():
            print(f"[WARN] 找不到圖片目錄: {images_dir}，保留 <!-- image -->")
            return out
        image_files = sorted(images_dir.glob("*.png")) + sorted(images_dir.glob("*.jpg"))
        idx = [0]  # 用 list 讓 closure 可改
        def repl_placeholder(_: re.Match) -> str:
            if idx[0] < len(image_files):
                img_path = images_dir / image_files[idx[0]].name
                try:
                    rel_path = img_path.relative_to(PROCESSED_MD_DIR).as_posix()
                except ValueError:
                    rel_path = str(img_path)
                idx[0] += 1
                return f'<image path="{rel_path}" />'
            return IMAGE_PLACEHOLDER
        out = re.sub(re.escape(IMAGE_PLACEHOLDER), repl_placeholder, out)

    return out


def main():
    print("Step 2: 綁定圖片路徑 -> <image path=\"...\" />")
    print("=" * 60)
    md_files = list(PROCESSED_MD_DIR.glob("*.md"))
    if not md_files:
        print(f"在 {PROCESSED_MD_DIR} 找不到 .md 檔案，請先執行 Step1")
        return
    for md_path in md_files:
        if md_path.name.endswith("_meta.md"):
            continue
        stem = md_path.stem
        images_dir = PROCESSED_MD_DIR / "images" / stem
        new_content = bind_images_in_md(md_path, images_dir)
        if new_content != md_path.read_text(encoding="utf-8"):
            md_path.write_text(new_content, encoding="utf-8")
            print(f"已更新: {md_path.name}")
        else:
            print(f"無須變更: {md_path.name}")
    print("完成.")


if __name__ == "__main__":
    main()
