#!/usr/bin/env python3
"""
Meta / Facebook Token Resolver — DAUERHAFT
==========================================
Einzige Quelle für Facebook/Instagram Tokens im Default-Pfad.

Regel (nie wieder falsch):
- Default / AiiteC Posts → IMMER AiiteC Page Token
- Alias-Vars (FB_PAGE_TOKEN, FACEBOOK_PAGE_TOKEN, …) müssen denselben Wert haben
- Andere Pages (IWIN, I_NEED_IT) nur über explizite page_key

Verhindert den alten Bug: facebook_token_manager setzte FACEBOOK_PAGE_TOKEN = IWIN.
"""
from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional

log = logging.getLogger("MetaTokenResolver")

# Canonical page
AIITEC_PAGE_ID = "1016738738178786"

# All env vars that MUST equal the AiiteC page token (default posting path)
AIITEC_TOKEN_ALIASES: List[str] = [
    "FACEBOOK_PAGE_TOKEN_AIITEC",
    "FACEBOOK_PAGE_TOKEN",
    "FACEBOOK_PAGE_ACCESS_TOKEN",
    "FACEBOOK_ACCESS_TOKEN",
    "FACEBOOK_META_TOKEN",
    "FACEBOOK_USER_TOKEN",
    "FACEBOOK_IG_ACCESS_TOKEN",
    "FB_PAGE_TOKEN",
    "INSTAGRAM_TOKEN_AIITEC",
    "INSTAGRAM_ACCESS_TOKEN",
    "META_PAGE_ACCESS_TOKEN",
    "META_ACCESS_TOKEN",
]

# Page-specific tokens (NOT forced to AiiteC)
PAGE_SPECIFIC: Dict[str, str] = {
    "AIITEC": "FACEBOOK_PAGE_TOKEN_AIITEC",
    "IWIN": "FACEBOOK_PAGE_TOKEN_IWIN",
    "I_NEED_IT": "FACEBOOK_PAGE_TOKEN_I_NEED_IT",
}


def get_aiitec_page_token() -> str:
    """Return the AiiteC page token (prefer dedicated var, then any alias)."""
    for key in AIITEC_TOKEN_ALIASES:
        val = (os.getenv(key) or "").strip()
        if val and len(val) > 40:
            # Prefer dedicated AIITEC key first; others only as fallback
            if key == "FACEBOOK_PAGE_TOKEN_AIITEC":
                return val
    for key in AIITEC_TOKEN_ALIASES:
        val = (os.getenv(key) or "").strip()
        if val and len(val) > 40:
            return val
    return ""


def get_page_token(page_key: str = "AIITEC") -> str:
    """Token for a named page. Default = AiiteC."""
    key = (page_key or "AIITEC").upper().replace(" ", "_")
    if key in ("DEFAULT", "MAIN", "AIITEC", "FB", "FACEBOOK", "META"):
        return get_aiitec_page_token()
    env_name = PAGE_SPECIFIC.get(key, f"FACEBOOK_PAGE_TOKEN_{key}")
    val = (os.getenv(env_name) or "").strip()
    if val:
        return val
    return get_aiitec_page_token()


def get_ig_token() -> str:
    """Instagram token for @aaiitecc — same AiiteC stack."""
    for key in (
        "FACEBOOK_IG_ACCESS_TOKEN",
        "INSTAGRAM_TOKEN_AIITEC",
        "INSTAGRAM_ACCESS_TOKEN",
        "FACEBOOK_PAGE_TOKEN_AIITEC",
    ):
        val = (os.getenv(key) or "").strip()
        if val and len(val) > 40:
            return val
    return get_aiitec_page_token()


def apply_aiitec_aliases_to_process(token: Optional[str] = None) -> dict:
    """
    Force-set all AiiteC alias env vars in the running process.
    Call at app startup so no module can use a stale/wrong token.
    """
    token = (token or get_aiitec_page_token()).strip()
    if not token:
        log.error("MetaTokenResolver: no AiiteC token available")
        return {"ok": False, "set": 0, "error": "empty_token"}
    set_count = 0
    for key in AIITEC_TOKEN_ALIASES:
        os.environ[key] = token
        set_count += 1
    os.environ.setdefault("FACEBOOK_PAGE_ID", AIITEC_PAGE_ID)
    os.environ.setdefault("FACEBOOK_ASSET_ID", AIITEC_PAGE_ID)
    os.environ.setdefault("META_PAGE_ID", AIITEC_PAGE_ID)
    log.info("MetaTokenResolver: applied AiiteC token to %d alias env vars", set_count)
    return {"ok": True, "set": set_count, "token_prefix": token[:20]}


def audit_aliases() -> dict:
    """Check which alias env vars diverge from AiiteC token."""
    canonical = get_aiitec_page_token()
    mismatches = []
    missing = []
    ok = []
    for key in AIITEC_TOKEN_ALIASES:
        val = (os.getenv(key) or "").strip()
        if not val:
            missing.append(key)
        elif canonical and val != canonical:
            mismatches.append({"key": key, "prefix": val[:20], "len": len(val)})
        else:
            ok.append(key)
    return {
        "ok": len(mismatches) == 0 and bool(canonical),
        "canonical_prefix": (canonical[:20] if canonical else ""),
        "canonical_len": len(canonical),
        "matched": ok,
        "missing": missing,
        "mismatches": mismatches,
    }


# Backwards-compatible aliases
resolve_fb_token = get_aiitec_page_token
resolve_page_token = get_page_token
