"""
Step 1: 使用 Docling 解析 PDF 並輸出 Markdown
"""
import sys
from pathlib import Path
from typing import List, Dict
import json

# 確保能導入 config
sys.path.append(str(Path(__file__).parent.parent))
from config import RAW_PDF_DIR, PROCESSED_MD_DIR, IMAGES_DIR, DOCLING_CONFIG

try:
    from docling.document_converter import DocumentConverter
except ImportError:
    print("❌ 請先安裝 docling: pip install docling")
    sys.exit(1)


class PDFParser:
    """使用 Docling 解析 PDF 的封裝類別"""
    
    def __init__(self):
        # 建立 Docling 轉換器
        # Docling 2.x 的新 API
        try:
            # 嘗試新版 API
            self.converter = DocumentConverter()
        except Exception as e:
            print(f"⚠️  初始化 DocumentConverter 失敗: {e}")
            print("嘗試使用預設設定...")
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
        
        try:
            # 執行轉換
            result = self.converter.convert(str(pdf_path))
            
            # 提取 Markdown
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
            return {
                "markdown": "",
                "metadata": {},
                "success": False,
                "error": str(e)
            }
    
    def save_markdown(self, pdf_path: Path, result: Dict):
        """儲存 Markdown 到檔案"""
        if not result["success"]:
            return
        
        # 產生輸出檔名
        output_name = pdf_path.stem + ".md"
        output_path = PROCESSED_MD_DIR / output_name
        
        # 寫入 Markdown
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result["markdown"])
        
        # 儲存 metadata
        meta_path = PROCESSED_MD_DIR / (pdf_path.stem + "_meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(result["metadata"], f, indent=2, ensure_ascii=False)
        
        print(f"✅ 已儲存: {output_path}")
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