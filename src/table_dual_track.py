"""
表格雙軌：HTML 保真 + TABLE_TEXT 檢索版

1. 將 markdown 中的 table block 換成 placeholder 並回填：
   - <!--TABLE_HTML:000k--> ... <!--/TABLE_HTML:000k-->（保真/展示，chunk 可排除）
   - <!--TABLE_TEXT:000k--> ... <!--/TABLE_TEXT:000k-->（檢索版）
2. 從 <!--/TABLE_TEXT:xxxx--> 後面往下掃描殘留的 pipe table 行，
   解析後 append 進 TABLE_TEXT（檢索用），
   同時包成 TABLE_MD_SCRAPS（debug 用）並從正文移除
"""
import re
import html as html_module
import logging
from typing import List, Dict, Tuple

logger = logging.getLogger(__name__)

# placeholder 避免與文件內容衝突
_CODE_PLACEHOLDER = "\uE000CODE_BLOCK\uE001"


def _html_table_to_rows(html: str) -> List[List[str]]:
    """從 HTML table 解析出 rows（每行是 cell 列表）。"""
    rows: List[List[str]] = []
    tr_pattern = re.compile(r"<tr[^>]*>([\s\S]*?)</tr>", re.IGNORECASE)
    cell_pattern = re.compile(r"<t[dh][^>]*>([\s\S]*?)</t[dh]>", re.IGNORECASE)

    for tr_match in tr_pattern.finditer(html):
        cells = []
        for cell_match in cell_pattern.finditer(tr_match.group(1)):
            raw = cell_match.group(1)
            clean = re.sub(r"<[^>]+>", " ", raw)
            clean = " ".join(clean.split()).strip()
            clean = html_module.unescape(clean)
            cells.append(clean)
        if cells:
            rows.append(cells)
    return rows


def _rows_to_table_text(rows: List[List[str]], section_header: str = "### 表格內容（檢索版）") -> str:
    """將 rows 轉成檢索友善的 TABLE_TEXT（row 展開 / KV bullets）。"""
    if not rows:
        return ""

    lines = [section_header, ""]
    headers = rows[0] if rows else []
    data_rows = rows[1:] if len(rows) > 1 else []

    for idx, row in enumerate(data_rows, 1):
        parts = []
        for j, cell in enumerate(row):
            h = headers[j] if j < len(headers) else f"欄{j+1}"
            if cell.strip():
                parts.append(f"{h}={cell.strip()}")
        if parts:
            lines.append(f"- **row {idx}:** " + " | ".join(parts))
    return "\n".join(lines) if len(lines) > 2 else "\n".join(lines)


def _md_pipe_table_to_rows(md_table: str) -> List[List[str]]:
    """從 markdown pipe table 解析出 rows。"""
    rows: List[List[str]] = []
    for line in md_table.split("\n"):
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if not cells:
            continue
        # 略過 separator 行 |---|---|
        if all(re.match(r"^[-:\s]+$", c) for c in cells):
            continue
        rows.append(cells)
    return rows


def _make_dual_block(el: Dict, table_id: str) -> str:
    """產生單一表格的雙軌區塊（含 closing tag 方便 chunk 排除 TABLE_HTML）。"""
    html_content = el.get("text", "").strip()
    if not html_content.lower().startswith("<table"):
        html_content = f"<table><tbody><tr><td>{html_content}</td></tr></tbody></table>"

    rows = _html_table_to_rows(html_content)
    table_text = _rows_to_table_text(rows)

    return f"""<!--TABLE:{table_id}-->
<!--TABLE_HTML:{table_id}-->
{html_content}
<!--/TABLE_HTML:{table_id}-->

<!--TABLE_TEXT:{table_id}-->
{table_text}
<!--/TABLE_TEXT:{table_id}-->
"""


def _mask_code_blocks(text: str) -> Tuple[str, List[str]]:
    """將 ``` ... ``` 替換成 placeholder，回傳 (masked_text, [block1, block2, ...])"""
    blocks: List[str] = []

    def repl(m: re.Match) -> str:
        blocks.append(m.group(0))
        return _CODE_PLACEHOLDER

    pat = re.compile(r"```[\s\S]*?```", re.MULTILINE)
    masked = pat.sub(repl, text)
    return masked, blocks


def _unmask_code_blocks(text: str, blocks: List[str]) -> str:
    """還原 code block placeholder。"""
    for orig in blocks:
        text = text.replace(_CODE_PLACEHOLDER, orig, 1)
    return text


def _is_table_line(line: str) -> bool:
    """判斷是否為表格行（| 開頭，含 separator |---|---|）。"""
    return line.strip().startswith("|")


def _collect_table_scraps_after_end_tag(text: str, after_pos: int) -> tuple[str, int]:
    """
    從 after_pos 開始往下掃描連續的 markdown table 行。
    允許中間空行，遇到非表格行（#、-、<、一般文字）即停止。
    回傳 (收集到的 table 行字串, 該段結束位置 exclusive)
    """
    lines = text[after_pos:].split("\n")
    collected: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped == "":
            collected.append(line)
            i += 1
            continue
        if _is_table_line(line):
            collected.append(line)
            i += 1
            continue
        break
    if not any(_is_table_line(ln) for ln in collected):
        return "", after_pos
    block = "\n".join(collected)
    end_pos = after_pos + sum(len(ln) + 1 for ln in lines[:i]) - (1 if i > 0 else 0)
    return block.rstrip(), end_pos


def _wrap_and_remove_table_scraps(text: str) -> str:
    """
    1) 定位每個 <!--/TABLE_TEXT:xxxx-->
    2) 從 end tag 後面往下掃描連續 table 行
    3) scraps 解析後 append 進 TABLE_TEXT（檢索用）
    4) 包成 TABLE_MD_SCRAPS（debug 用）並從正文移除該段 table 行
    """
    pat = re.compile(r"<!--/TABLE_TEXT:(\d{4})-->")
    for m in reversed(list(pat.finditer(text))):
        table_id = m.group(1)
        after_pos = m.end()
        rest = text[after_pos:]
        strip_len = len(rest) - len(rest.lstrip("\n\r"))
        scan_start = after_pos + strip_len
        scraps, end_pos = _collect_table_scraps_after_end_tag(text, scan_start)
        if not scraps:
            continue

        # scraps 轉成 row 展開，append 進 TABLE_TEXT
        rows = _md_pipe_table_to_rows(scraps)
        scraps_text = _rows_to_table_text(rows, section_header="### 補充（scraps）")
        if scraps_text:
            close_tag = f"<!--/TABLE_TEXT:{table_id}-->"
            text = text.replace(close_tag, f"\n\n{scraps_text}\n\n{close_tag}", 1)

        # 包成 TABLE_MD_SCRAPS、移除原本 table 行
        insert = f"\n\n<!--TABLE_MD_SCRAPS:{table_id}-->\n{scraps}\n<!--/TABLE_MD_SCRAPS:{table_id}-->"
        before = text[:scan_start]
        after = text[end_pos:]
        text = before + insert + after
    return text


def apply_table_dual_track(markdown_text: str, elements: List[Dict]) -> str:
    """
    2.1 將 md 中的 table block（HTML 或 markdown pipe）換成 placeholder
    2.2 用 elements 的 table（含 table_id）依序回填 TABLE_HTML + TABLE_TEXT

    - 跳過 code block 內的 | 誤判
    - 回填數量不符時 output warning
    """
    table_elements = [e for e in elements if e.get("type") == "table"]
    if not table_elements:
        return markdown_text

    for i, el in enumerate(table_elements):
        if "table_id" not in el:
            el["table_id"] = f"{(i+1):04d}"

    # 1) Mask code blocks，避免 pipe table 誤判
    masked, code_blocks = _mask_code_blocks(markdown_text)

    # 2) 收集所有 table  match（HTML + MD），依 start 排序
    html_pat = re.compile(r"<table[\s\S]*?</table>", re.IGNORECASE | re.DOTALL)
    md_pat = re.compile(
        r"^(\|[^\n]+\|\s*\n)((?:\|[^\n]+\|\s*\n){1,})",
        re.MULTILINE,
    )

    matches: List[Tuple[int, int, str]] = []  # (start, end, full_match)
    for m in html_pat.finditer(masked):
        matches.append((m.start(), m.end(), m.group(0)))
    for m in md_pat.finditer(masked):
        matches.append((m.start(), m.end(), m.group(0)))

    matches.sort(key=lambda x: x[0])

    # 3) 從後往前替換，保留位置。最後一個 match 對應 table_elements[-1]
    n = len(matches)
    for idx in range(n - 1, -1, -1):
        start, end, _ = matches[idx]
        el_idx = idx
        if el_idx >= len(table_elements):
            logger.warning("[table_dual_track] 表格 match 多於 elements，跳過多餘的")
            continue
        el = table_elements[el_idx]
        table_id = el.get("table_id", f"{(el_idx+1):04d}")
        replacement = _make_dual_block(el, table_id)
        masked = masked[:start] + replacement + masked[end:]

    if n != len(table_elements):
        logger.warning(
            "[table_dual_track] 表格回填數量不符: md 中 %d 處 table, elements 有 %d 個 table",
            n,
            len(table_elements),
        )

    text = _unmask_code_blocks(masked, code_blocks)
    text = _wrap_and_remove_table_scraps(text)
    return text
