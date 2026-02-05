from pathlib import Path
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from tqdm import tqdm
import time
import urllib3

# 關閉 InsecureRequestWarning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

OUT_DIR = Path("data/raw")
OUT_DIR.mkdir(parents=True, exist_ok=True)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0"})

PAGE_URLS = [
    "https://ilabor.ntpc.gov.tw/page/training-materials-for-occupational-safety-and-health-in-non-construction-industry/general-safety-and-health-management",
    "https://isafeel.osha.gov.tw/mooc/download.php",
]

def get_pdf_links(page_url):
    print(f"🔍 掃描頁面: {page_url}")
    r = SESSION.get(page_url, timeout=30, verify=False)  # ✅ 關 SSL 驗證
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if ".pdf" in href.lower():
            links.add(urljoin(page_url, href))

    print(f"📄 找到 {len(links)} 個 PDF 連結")
    return list(links)

def download_pdf(url):
    name = url.split("/")[-1].split("?")[0]
    if not name.lower().endswith(".pdf"):
        name += ".pdf"

    path = OUT_DIR / name
    if path.exists():
        print(f"⏭️ 已存在: {name}")
        return

    print(f"📥 下載 {name}")
    r = SESSION.get(url, stream=True, timeout=60, verify=False)  # ✅ 關 SSL 驗證
    r.raise_for_status()

    total = int(r.headers.get("content-length", 0))
    with open(path, "wb") as f, tqdm(total=total or None, unit="B", unit_scale=True) as pbar:
        for chunk in r.iter_content(1024 * 64):
            if not chunk:
                continue
            f.write(chunk)
            if total:
                pbar.update(len(chunk))

def main():
    all_links = set()

    for page in PAGE_URLS:
        try:
            all_links.update(get_pdf_links(page))
        except Exception as e:
            print(f"⚠️ 頁面失敗: {page}\n{e}")

    print(f"\n📦 準備下載 {len(all_links)} 個 PDF 到 {OUT_DIR.resolve()}\n")

    ok = 0
    for link in sorted(all_links):
        try:
            download_pdf(link)
            ok += 1
            time.sleep(0.3)
        except Exception as e:
            print(f"❌ 下載失敗: {link}\n{e}")

    print(f"\n🎉 全部完成！成功下載 {ok} 個 PDF")

if __name__ == "__main__":
    main()
