# Prompts from Docling2md-style pipeline (image caption, text type, table repair, text repair)
from .VLM_prompt import VLM_PROMPT
from .text_type_prompt import TEXT_TYPE_PROMPT
from .table_repair_prompt import TABLE_REPAIR_PROMPT
from .text_repair_prompt import TEXT_REPAIR_PROMPT

__all__ = ["VLM_PROMPT", "TEXT_TYPE_PROMPT", "TABLE_REPAIR_PROMPT", "TEXT_REPAIR_PROMPT"]
