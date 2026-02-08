# RAG System - 專案結構（主流程同 Docling2md）

主流程與 [Docling2md](https://github.com/EvannZhongg/Docling2md) 一致：**單一腳本** 完成 PDF → 結構解析 → 表格／圖片／文字處理（VLM caption、LLM 標題判斷、表格修復）→ 輸出 .md、.json、圖檔。

## 目錄規劃

```
RAG/
├── pdf2md.py                    # 主程式：PDF → Markdown + JSON（Docling2md 流程）
├── config.py                    # 路徑與 Docling 設定（RAW_PDF_DIR、OUTPUT_BASE 等）
├── config_docling2md.yaml       # API 設定（由 .example 複製，填 OPENAI / VLM / OCR / POPPLER）
├── config_docling2md.yaml.example
├── requirements.txt
├── data/
│   └── raw/                     # 輸入 PDF 放這裡
├── output/                      # Docling2md 風格輸出（依 PDF hash 分子目錄）
│   └── <pdf_hash>/
│       ├── <hash>.md
│       ├── <hash>.json
│       ├── page/                 # 每頁 PNG（需設定 POPPLER 時才有）
│       ├── <hash>-table-*.png
│       └── <hash>-picture-*.png
├── prompt/
│   ├── VLM_prompt.py
│   ├── text_type_prompt.py
│   ├── table_repair_prompt.py
│   └── text_repair_prompt.py
├── src/                         # 其他步驟（切分、embedding、檢索等）
│   ├── step2_chunk_text.py
│   ├── step3_embedding.py
│   ├── step4_milvus_store.py
│   └── step5_query.py
├── milvus_data/
└── run_step1_parse.ps1          # 舊分層流程用（可選）
```

## 主流程：pdf2md.py（與 Docling2md 相同）

1. **設定**
   - 將 `config_docling2md.yaml.example` 複製為 `config_docling2md.yaml`，填入：
     - **OPENAI**：api_key、base_url、model（如 DeepSeek，用於標題/段落判斷、英文斷字）
     - **VLM**：api_key、base_url、model（如 DashScope Qwen-VL，用於圖片 caption、表格修復）
     - **OCR**：enabled（true/false）
     - **POPPLER**：path（選填，要匯出每頁 PNG 時需填）

2. **輸入**
   - PDF 放在 `data/raw/`（由 `config.py` 的 `RAW_PDF_DIR` 決定）。

3. **執行**
   ```bash
   python pdf2md.py
   ```
   - 會處理 `data/raw/` 下所有 PDF，每個 PDF 對應一個 `output/<pdf_hash>/` 目錄。

4. **輸出**（與 Docling2md 一致）
   - `output/<pdf_hash>/<hash>.md`：依文件順序的 Markdown（表格、圖片 caption、標題/段落）。
   - `output/<pdf_hash>/<hash>.json`：結構化資料（type、level、page_number、bbox 等）。
   - `output/<pdf_hash>/page/page-*.png`：每頁圖（需設定 POPPLER）。
   - `output/<pdf_hash>/*-table-*.png`、`*-picture-*.png`：表格與圖片檔。

5. **流程摘要**
   - Docling 解析 PDF → 依 `document.iterate_items()` 順序處理：
     - **表格**：匯出 DataFrame → Markdown；若結構異常則切片 + VLM 修復。
     - **圖片**：存檔 + VLM 產生 caption，寫成 `![caption](./檔名.png)`。
     - **文字**：可選英文斷字修復 + LLM 判斷 Heading / Paragraph，標題加 `#`。

## 執行前注意（Windows）

- 若本機曾用 Granite Docling 且遇權限問題，可設：
  - `HF_HUB_DISABLE_SYMLINKS=1`
  - `PYTHONIOENCODING=utf-8`
- `pdf2md.py` 使用標準 Docling pipeline（非 Granite VLM），不需 GPU。

## 依賴

- 主流程需：`docling`、`openai`、`pyyaml`、`pandas`、`Pillow`。
- 選填：`pdf2image` + 系統安裝 **poppler**（用於匯出每頁 PNG）。

## 後續步驟（RAG）

1. 以 `output/<pdf_hash>/*.md` 或 `.json` 做文本切分（如 `step2_chunk_text`）。
2. Embedding、寫入 Milvus、實作檢索（`step3_embedding`、`step4_milvus_store`、`step5_query`）。

---

舊的「分層流程」（Step1 只解析、Step2 綁圖、Step3 再 caption）仍保留在 `src/step1_parse_pdf.py`、`src/step2_bind_images.py`、`src/step3_caption_enhance.py`，可當備用或比對用。
