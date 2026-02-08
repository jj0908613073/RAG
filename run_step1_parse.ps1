# Step 1: PDF 解析（Granite Docling）
# 設定環境變數後執行，避免 Windows 權限與編碼問題

$env:HF_HUB_DISABLE_SYMLINKS = "1"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
$env:PYTHONIOENCODING = "utf-8"

Set-Location $PSScriptRoot
python src/step1_parse_pdf.py
