"""
e RAG System - 統一配置檔
"""
import os
from pathlib import Path

# ==================== 路徑設定 ====================
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_PDF_DIR = DATA_DIR / "raw"
RAW_DOCS_DIR = RAW_PDF_DIR  # 多格式輸入目錄（與 RAW_PDF_DIR 相同）
PROCESSED_MD_DIR = DATA_DIR / "processed"

# 多格式支援：Step1 可解析的副檔名（PDF、Office、圖片、網頁等）
SUPPORTED_DOC_EXTENSIONS = (
    ".pdf", ".docx", ".pptx", ".xlsx",
    ".html", ".htm", ".md", ".csv", ".asciidoc",
    ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp",
)
# Docling2md 風格輸出：output/<pdf_hash>/*.md, *.json, page/, *.png
OUTPUT_BASE = PROJECT_ROOT / "output"
MILVUS_DATA_DIR = PROJECT_ROOT / "milvus_data"

# 建立必要目錄
for dir_path in [RAW_PDF_DIR, PROCESSED_MD_DIR, OUTPUT_BASE, MILVUS_DATA_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

# ==================== Docling 設定 ====================
# 分層模式：True = Step1 用標準 pipeline（標題/段落/圖 placeholder），圖另存；之後再對圖做 VLM caption
# False = Step1 直接用 Granite VLM 解析整份 PDF（圖內文字靠 VLM，較吃資源）
DOCLING_LAYERED_MODE = True

# 僅在非分層模式時使用 VLM
USE_GRANITE_DOCLING = True

# 運算裝置：GPU 環境未就緒時用 CPU，就緒後改 "cuda" 或 "auto"
# 可選："auto"（自動選最佳）、"cpu"、"cuda"、"cuda:0"
DOCLING_DEVICE = "cuda"
# CPU 執行緒數（僅 device=cpu 時有效）：可調低以減輕 CPU 負載，例如 2
DOCLING_NUM_THREADS = 4
# 只解析前 N 頁（測試用）：設 1 只解析第一頁，設 None 解析全部
DOCLING_MAX_PAGES = 5
# 提取圖片的縮放倍率：1.0 預設、2.0 較清晰（較大檔案），圖糊可調高
DOCLING_IMAGES_SCALE = 2.0

DOCLING_CONFIG = {
    "do_ocr": True,  # 處理掃描式 PDF
    "do_table_structure": True,  # 解析表格結構
    "image_export_mode": "placeholder",  # 'placeholder' 或 'embedded'
}

# ==================== LangChain 切分設定 ====================
CHUNK_CONFIG = {
    "chunk_size": 512,  # 單位：字元數
    "chunk_overlap": 50,  # 重疊區域
    "separators": ["\n## ", "\n### ", "\n#### ", "\n\n", "\n", " ", ""],
    "length_function": len,
}

# ==================== Embedding 模型設定 ====================
# BGE-M3 文本模型
TEXT_EMBEDDING_CONFIG = {
    "model_name": "BAAI/bge-m3",
    "device": "cuda",  # 'cuda' 或 'cpu'
    "normalize_embeddings": True,
    "embedding_dim": 1024,
}

# SigLIP 圖片模型
IMAGE_EMBEDDING_CONFIG = {
    "model_name": "hf-hub:timm/ViT-SO400M-14-SigLIP-384",
    "device": "cuda",
    "embedding_dim": 1152,
}

# ==================== Milvus 設定 ====================
MILVUS_CONFIG = {
    "uri": str(MILVUS_DATA_DIR / "milvus_lite.db"),  # Milvus Lite 使用本地檔案
    "collection_name": "vibe_rag_collection",
    "metric_type": "COSINE",  # 相似度計算方式
    "index_type": "FLAT",  # 索引類型（小資料集用 FLAT，大資料集用 IVF_FLAT）
}

# ==================== VLM 圖片摘要設定（Step3 caption，僅 Ollama） ====================
# 家裡：http://127.0.0.1:11434 | 公司：http://t2c2ap6:9999/v1
OLLAMA_BASE_URL = "http://127.0.0.1:11434"  # 公司；家裡改 "http://127.0.0.1:11434"
OLLAMA_MODEL = "qwen3-vl:8b"

# ==================== 檢索設定 ====================
RETRIEVAL_CONFIG = {
    "top_k": 5,  # 返回前 k 個結果
    "text_weight": 0.7,  # 文本檢索權重
    "image_weight": 0.3,  # 圖片檢索權重
}

# ==================== 除錯設定 ====================
DEBUG = True
LOG_LEVEL = "INFO"

if __name__ == "__main__":
    print("✅ 配置檔載入成功")
    print(f"專案根目錄: {PROJECT_ROOT}")
    print(f"原始 PDF 目錄: {RAW_PDF_DIR}")
    print(f"Milvus 資料目錄: {MILVUS_DATA_DIR}")