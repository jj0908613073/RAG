"""Demo script to run step2 binding and caption insertion on the sample markdown.
Creates a tiny placeholder PNG and runs the two scripts in-process.
"""
import os
import base64
import sys

# Ensure repo root is on sys.path so `src` package can be imported when running tests
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
)


def ensure_image(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = base64.b64decode(PNG_BASE64)
    with open(path, "wb") as f:
        f.write(data)


def main():
    md_path = os.path.join("data", "processed", "2025 職安署線上推廣宣導會簡報.md")
    img_dir = os.path.join("data", "images")
    img_path = os.path.join(img_dir, "page_001.png")

    ensure_image(img_path)

    # run binding
    from src.step2_bind_images import bind_images
    from src.caption_vlm import insert_captions

    replaced = bind_images(md_path, images_prefix="../images", image_pattern="page_{:03d}.png")
    print(f"Bound {replaced} images in {md_path}")

    # run captioner using vlm_list
    vlm_list = os.path.join("data", "processed", "vlm_list.txt")
    insert_captions(md_path, vlm_list, images_dir=img_dir)
    print("Inserted captions (if any).\n")

    with open(md_path, "r", encoding="utf-8") as f:
        print(f.read())


if __name__ == '__main__':
    main()
