"""
Step 1: 使用 Docling 解析 PDF 並輸出 Markdown
"""
import sys
import traceback
from pathlib import Path
from typing import List, Dict
import json

# 確保能導入 config
sys.path.append(str(Path(__file__).parent.parent))
from config import (
    RAW_PDF_DIR,
    PROCESSED_MD_DIR,
    DOCLING_CONFIG,
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


class PDFParser:
    """使用 Docling 解析 PDF 的封裝類別（可選 Granite Docling VLM）"""
    
    def __init__(self):
        # 建立 Docling 轉換器（分層模式用標準 pipeline，不跑 VLM）
        if DOCLING_LAYERED_MODE:
            # 必須開啟 generate_picture_images 才會有圖可匯出；images_scale 愈高圖愈清晰
            pdf_opts = ThreadedPdfPipelineOptions(
                generate_picture_images=True,
                generate_page_images=True,
                images_scale=DOCLING_IMAGES_SCALE,
            )
            self.converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_opts),
                }
            )
            print("[OK] 分層模式：標準 Docling（標題/段落 + 圖匯出至 images/）")
        elif USE_GRANITE_DOCLING:
            # 使用 Granite Docling（VLM pipeline），裝置與執行緒由 config 控制
            accel = AcceleratorOptions(device=DOCLING_DEVICE, num_threads=DOCLING_NUM_THREADS)
            self.converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(
                        pipeline_cls=VlmPipeline,
                        pipeline_options=VlmPipelineOptions(accelerator_options=accel),
                    ),
                }
            )
            print(f"[OK] Granite Docling (VLM)，裝置: {DOCLING_DEVICE}，執行緒: {DOCLING_NUM_THREADS}")
        else:
            self.converter = DocumentConverter()
        
    def parse_single_pdf(self, pdf_path: Path) -> Dict:
        """
        解析單一 PDF 檔案
        
        Args:
            pdf_path: PDF 檔案路徑
            
        Returns:
            包含 markdown 文本、metadata 的字典
        """
        print(f"📄 開始解析: {pdf_path.name}")
        if DOCLING_MAX_PAGES is not None:
            print(f"   （僅前 {DOCLING_MAX_PAGES} 頁，測試用）")
        try:
            # 只處理前 N 頁：用 page_range，不要用 max_num_pages（會把多頁 PDF 整份拒收）
            kwargs = {}
            if DOCLING_MAX_PAGES is not None:
                kwargs["page_range"] = (1, DOCLING_MAX_PAGES)
            result = self.converter.convert(str(pdf_path), **kwargs)
            
            if DOCLING_LAYERED_MODE and ImageRefMode is not None:
                # 分層：直接寫入 .md + 匯出圖片到 images/{doc_stem}/（相對路徑，方便 Step2）
                md_path = PROCESSED_MD_DIR / (pdf_path.stem + ".md")
                (PROCESSED_MD_DIR / "images" / pdf_path.stem).mkdir(parents=True, exist_ok=True)
                artifacts_dir = Path("images") / pdf_path.stem  # 相對路徑，md 內為 images/doc_stem/xxx.png
                result.document.save_as_markdown(
                    filename=md_path,
                    artifacts_dir=artifacts_dir,
                    image_mode=ImageRefMode.REFERENCED,
                )
                markdown_text = md_path.read_text(encoding="utf-8")
            else:
                markdown_text = result.document.export_to_markdown()
            
            # 提取 metadata
            metadata = {
                "source": pdf_path.name,
                "num_pages": len(result.document.pages) if hasattr(result.document, 'pages') else 0,
                "title": getattr(result.document, 'title', pdf_path.stem),
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
    
    def save_markdown(self, pdf_path: Path, result: Dict):
        """儲存 Markdown 到檔案（分層模式時 .md 已在 parse 時寫入，只寫 metadata）"""
        if not result["success"]:
            return
        
        output_path = PROCESSED_MD_DIR / (pdf_path.stem + ".md")
        if not DOCLING_LAYERED_MODE:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(result["markdown"])
            print(f"✅ 已儲存: {output_path}")
        
        meta_path = PROCESSED_MD_DIR / (pdf_path.stem + "_meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(result["metadata"], f, indent=2, ensure_ascii=False)
        print(f"📊 Metadata: {meta_path}")
    
    def parse_directory(self, max_files: int = None) -> List[Dict]:
        """
        批次解析目錄下的所有 PDF
        
        Args:
            max_files: 最多處理幾個檔案（測試用）
            
        Returns:
            解析結果列表
        """
        pdf_files = list(RAW_PDF_DIR.glob("*.pdf"))
        
        if not pdf_files:
            print(f"⚠️  在 {RAW_PDF_DIR} 找不到 PDF 檔案")
            return []
        
        if max_files:
            pdf_files = pdf_files[:max_files]
        
        print(f"🔍 找到 {len(pdf_files)} 個 PDF 檔案")
        
        results = []
        for pdf_path in pdf_files:
            result = self.parse_single_pdf(pdf_path)
            if result["success"]:
                self.save_markdown(pdf_path, result)
            results.append(result)
        
        # 統計
        success_count = sum(1 for r in results if r["success"])
        print(f"\n📈 完成: {success_count}/{len(results)} 個檔案成功解析")
        
        return results


def main():
    """主程式 - 測試解析功能"""
    print("=" * 60)
    print("Step 1: PDF 解析測試")
    print("=" * 60)
    
    parser = PDFParser()
    
    # 檢查是否有 PDF 檔案
    pdf_files = list(RAW_PDF_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"\n⚠️  請先將 PDF 檔案放到: {RAW_PDF_DIR}")
        print("提示：你可以從 LongDocURL 資料集下載測試檔案")
        return
    
    # 先測試解析第一個檔案
    print(f"\n🧪 測試模式：只解析第一個檔案")
    results = parser.parse_directory(max_files=1)
    
    if results and results[0]["success"]:
        print("\n" + "=" * 60)
        print("✅ 解析成功！可以查看生成的 Markdown 檔案")
        print(f"輸出目錄: {PROCESSED_MD_DIR}")
        print("=" * 60)
    

if __name__ == "__main__":
    main()