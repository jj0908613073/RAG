# RAG System - 專案結構

以 **分層流程**（Step1 → Step2 → Step3）為主，逐步完成 PDF 解析、圖片綁定、Caption 強化，輸出 Markdown 與圖檔，之後可接文本切分、Embedding、檢索。

## 目錄規劃

```
RAG/
├── config.py                    # 路徑與 Docling 設定（RAW_PDF_DIR、PROCESSED_MD_DIR、DOCLING_LAYERED_MODE 等）
├── requirements.txt
├── data/
│   ├── raw/                     # 輸入文件（PDF、DOCX、PPTX、圖片等）
│   └── processed/               # 分層流程輸出
│       ├── *.md                 # 各文件的 Markdown
│       ├── *_meta.json          # 結構化 metadata
│       └── images/              # 圖檔（依文件分子目錄）
│           └── <doc_name>/
│               └── image_*.png
├── prompt/                      # LLM / VLM 用 prompt
│   ├── VLM_prompt.py
│   ├── text_type_prompt.py
│   ├── table_repair_prompt.py
│   └── text_repair_prompt.py
├── src/                         # 主流程與後續步驟
│   ├── step1_parse_pdf.py       # PDF 解析 → .md + 圖 placeholder
│   ├── step2_bind_images.py     # 綁定圖片到 Markdown
│   ├── step3_caption_enhance.py # VLM caption 強化
│   ├── caption_vlm.py           # VLM 呼叫封裝
│   ├── step2_chunk_text.py      # 文本切分（RAG 用）
│   ├── step3_embedding.py       # Embedding（RAG 用）
│   ├── step4_milvus_store.py    # 寫入 Milvus（RAG 用）
│   └── step5_query.py           # 檢索查詢（RAG 用）
├── milvus_data/                 # Milvus 本地資料
└── run_step1_parse.ps1          # 執行 Step1 解析
```

## 主流程：分層 PDF → Markdown

### Step1：解析文件（`step1_parse_pdf.py`）

- **輸入**：`data/raw/` 下的多種格式（PDF、DOCX、PPTX、XLSX、HTML、MD、圖片等）
- **輸出**：`data/processed/*.md`、`*_meta.json`、`data/processed/images/<doc_name>/`
- **說明**：Docling 統一解析多種格式，產出 Markdown（含表格、標題/段落、圖 placeholder），圖另存至 `images/`

### Step2：綁定圖片（`step2_bind_images.py`）

- **輸入**：Step1 產生的 `.md`、`_meta.json`、`images/`
- **輸出**：更新後的 `.md`（圖片連結綁入正確位置）
- **說明**：依 metadata 與 bbox，將圖檔以 `![](path)` 形式插入 Markdown

### Step3：Caption 強化（`step3_caption_enhance.py`）

- **輸入**：Step2 的 `.md`、`images/`
- **輸出**：含 VLM caption 的 `.md`（如 `*Caption: ...*`）
- **說明**：對圖片呼叫 VLM 產生 caption。在 `config.py` 以 `VLM_PROVIDER` 切換後端：
  - `gemini`：家裡測試，需填 `VLM_GEMINI.api_key`，安裝 `google-generativeai`
  - `ollama`：公司自架伺服器，填 `VLM_OLLAMA.base_url`、`model`

### 設定（`config.py`）

- `DOCLING_LAYERED_MODE = True`：使用分層流程
- `RAW_PDF_DIR`：PDF 來源
- `PROCESSED_MD_DIR`：輸出路徑
- `DOCLING_DEVICE`、`DOCLING_NUM_THREADS`、`DOCLING_MAX_PAGES` 等：Docling 相關參數

## 後續步驟（RAG）

1. **step2_chunk_text**：將 `.md` 切分為 chunks
2. **step3_embedding**：對文本與圖片做 Embedding
3. **step4_milvus_store**：寫入 Milvus
4. **step5_query**：實作檢索查詢

## 執行前注意（Windows）

- 若曾用 Granite Docling 且遇權限問題，可設：
  - `HF_HUB_DISABLE_SYMLINKS=1`
  - `PYTHONIOENCODING=utf-8`

## 依賴

- Docling、openai、pyyaml、pandas、Pillow
- 選填：pdf2image + poppler（需匯出每頁 PNG 時）

---

### 備選：pdf2md.py（Docling2md 風格）

單一腳本一次完成 PDF → Markdown，需 `config_docling2md.yaml`。若偏好分層流程則無須使用。
