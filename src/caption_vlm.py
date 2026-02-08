import argparse
import os
import re

try:
    from PIL import Image
    import pytesseract
    HAS_OCR = True
except Exception:
    HAS_OCR = False


def load_vlm_list(vlm_list_path):
    if not vlm_list_path or not os.path.exists(vlm_list_path):
        return set()
    with open(vlm_list_path, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]
    # allow indexes or filenames
    indexes = set()
    names = set()
    for l in lines:
        if l.isdigit():
            indexes.add(int(l))
        else:
            names.add(l)
    return indexes, names


def generate_caption_with_ocr(image_path):
    if not HAS_OCR:
        return f"[AUTO] caption for {os.path.basename(image_path)}"
    try:
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img)
        text = text.strip().replace('\n', ' ').strip()
        if not text:
            return f"[AUTO] no text detected for {os.path.basename(image_path)}"
        return text
    except Exception as e:
        return f"[AUTO] OCR error: {e}"


def insert_captions(md_path, vlm_list_path, images_dir):
    with open(md_path, "r", encoding="utf-8") as f:
        text = f.read()

    indexes_set, names_set = load_vlm_list(vlm_list_path)

    def repl(match):
        full = match.group(0)
        src = match.group('src')
        idx = int(match.group('index'))
        filename = os.path.basename(src)

        should_run = False
        if isinstance(indexes_set, set) and idx in indexes_set:
            should_run = True
        if isinstance(names_set, set) and filename in names_set:
            should_run = True

        if should_run:
            # try to find image on disk
            img_path = os.path.join(images_dir, filename)
            if not os.path.exists(img_path):
                caption = f"[MISSING] {filename}"
            else:
                caption = generate_caption_with_ocr(img_path)
            return full + "\n\n*Caption: " + caption + "*"
        else:
            return full

    pattern = re.compile(r'<image\s+src="(?P<src>[^"]+)"\s+index="(?P<index>\d+)"\s*/>')
    new_text = pattern.sub(repl, text)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(new_text)


def main():
    p = argparse.ArgumentParser(description="Insert captions for images listed in vlm_list.txt (index or filename)")
    p.add_argument("md", help="Markdown file to modify (in-place)")
    p.add_argument("--vlm-list", default=None, help="Path to vlm_list.txt (each line: index or filename)")
    p.add_argument("--images-dir", default="../images", help="Directory where images are located (used to run OCR)")
    args = p.parse_args()

    insert_captions(args.md, args.vlm_list, args.images_dir)
    print(f"Processed captions for {args.md}")


if __name__ == '__main__':
    main()
