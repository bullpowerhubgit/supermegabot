#!/usr/bin/env python3
"""Telegram DM outreach variants from marketing/telegram_dm_sheet_30.md"""
from __future__ import annotations
import random
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHEET = ROOT / "marketing" / "telegram_dm_sheet_30.md"

@lru_cache(maxsize=1)
def load_variants() -> dict[int, str]:
    text = SHEET.read_text(encoding="utf-8") if SHEET.exists() else ""
    return {int(i): t.strip() for i, t in re.findall(r"^(\d+)\)\s+(.+)$", text, re.M)}

def pick(lang: str = "de", n: int = 1) -> list[str]:
    """lang=de -> 1-15, en -> 16-30"""
    allv = load_variants()
    keys = range(1, 16) if lang.lower().startswith("de") else range(16, 31)
    pool = [allv[k] for k in keys if k in allv]
    if not pool:
        return []
    n = min(n, len(pool))
    return random.sample(pool, n)

def followups() -> dict[str, str]:
    text = SHEET.read_text(encoding="utf-8") if SHEET.exists() else ""
    out = {}
    for label, key in [
        ("24h", r"### Follow-up 1.*?\n([\s\S]*?)(?=###|$)"),
        ("value", r"### Follow-up 2.*?\n([\s\S]*?)(?=###|$)"),
        ("close", r"### Follow-up 3.*?\n([\s\S]*?)(?=###|$)"),
    ]:
        m = re.search(key, text)
        if m:
            out[label] = m.group(1).strip()
    # Sales-call + case study snippets
    try:
        from modules.sales_call_process import (
            telegram_book_script,
            telegram_after_case,
            cta_block,
        )

        cta = cta_block("de")
        out.setdefault("book_call", telegram_book_script())
        out.setdefault("after_case", telegram_after_case("shopify"))
        out.setdefault(
            "close_options",
            f"Option A Trial: {cta['primary_url']}\nOption B Call: {cta['secondary_url']}",
        )
    except Exception:
        pass
    return out
