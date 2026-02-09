# Image caption prompt for RAG - structured output for retrieval

VLM_PROMPT_BASE = """Context:
This image is extracted from a document. It may be part of an instructional / procedural document that explains how to use a system.

You are an expert AI assistant tasked with analyzing images extracted from documents for a Retrieval-Augmented Generation (RAG) system.
Your goal is to extract accurate, structured, and retrievable information so it can be reliably used for search and question answering.

The input may already include OCR results. Do NOT invent, guess, or hallucinate any text, data, or relationships that are not clearly visible in the image.

Follow the steps below and output your response in clear Markdown using the exact section headers specified.

---

## 1. Content Type
Classify the image into ONE of the following categories:
- Flowchart
- Table
- Chart
- Diagram
- Screenshot
- Photograph
- Other

---

## 2. Visible Text Summary
Based only on visible text in the image or provided OCR:
- List key titles, labels, UI elements, headings, or terms exactly as they appear.
- If the image contains a table, describe its rows and columns logically without guessing missing values.
- If the image contains a flowchart or diagram, list node labels or decision texts.

Do not paraphrase or normalize terminology.

---

## 3. Structural / Semantic Description
Describe the structure and meaning of the image in a factual and concise manner:
- For flowcharts: explain the main steps, decision points, and branching logic.
- For charts: state the X/Y axes, observable trends, and notable data points.
- For diagrams: describe components and their relationships.
- For screenshots: explain what part of the system interface is shown and what action or information it supports.

Do not add assumptions beyond what is visible.

---

## 4. Key Takeaway
Summarize the core message, purpose, or instructional value of this image in 1–2 concise sentences.

---

## 5. Relevance
If the image is purely decorative, a logo, or contains no meaningful information for retrieval or understanding, output exactly:
Irrelevant
"""

# 用於注入 OCR 結果的區塊（若無 OCR 則不加入）
VLM_PROMPT_OCR_SECTION = """

---

## Provided OCR text (use only if visible in image, do not invent)

{ocr_text}
"""

# 相容舊程式碼
VLM_PROMPT = VLM_PROMPT_BASE
