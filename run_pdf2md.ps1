# 主流程：PDF → Markdown + JSON（Docling2md 流程）
$env:PYTHONIOENCODING = "utf-8"
Set-Location $PSScriptRoot
python pdf2md.py
