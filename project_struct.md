# RAG System - 專案結構

## 目錄規劃
```
vibe_rag/
├── requirements.txt          # 套件清單
├── .env                      # 環境變數（API keys 等）
├── config.py                 # 統一配置檔
├── data/
│   ├── raw/                  # 原始 PDF 檔案
│   ├── processed/            # Docling 解析後的 MD
│   └── images/               # 提取的圖片
├── src/
│   ├── __init__.py
│   ├── step1_parse_pdf.py    # Docling 解析
│   ├── step2_chunk_text.py   # LangChain 切分
│   ├── step3_embedding.py    # BGE-M3 + SigLIP
│   ├── step4_milvus_store.py # Milvus 儲存
│   └── step5_query.py        # 檢索查詢
├── milvus_data/              # Milvus Lite 資料目錄
├── tests/
│   └── test_pipeline.py      # 測試腳本
└── notebooks/
    └── demo.ipynb            # 互動式測試
```

## 開發流程
1. **Step 1**: 測試 Docling 解析單一 PDF
2. **Step 2**: 實作文本切分邏輯
3. **Step 3**: 載入 embedding 模型並測試
4. **Step 4**: 建立 Milvus 集合並儲存向量
5. **Step 5**: 實作混合檢索與驗證

