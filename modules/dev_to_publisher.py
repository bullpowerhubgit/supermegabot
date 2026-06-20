"""
dev.to Publisher — vollautonomes Artikel-Posting zu dev.to
Aktiviert sich automatisch wenn DEVTO_API_KEY in Env vorhanden.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import aiohttp

log = logging.getLogger("DevToPublisher")

DEVTO_API_KEY = os.getenv("DEVTO_API_KEY", "")
API_BASE      = "https://dev.to/api"

TAGS_MAP = {
    "shopify":    ["shopify", "ecommerce", "automation", "python"],
    "ai":         ["ai", "machinelearning", "python", "productivity"],
    "affiliate":  ["business", "marketing", "passive_income", "ecommerce"],
    "default":    ["automation", "python", "productivity", "business"],
}


def _is_active() -> bool:
    return bool(DEVTO_API_KEY)


async def publish_article(title: str, body_markdown: str, tags: list[str] | None = None,
                          canonical_url: str = "") -> dict:
    if not _is_active():
        return {"ok": False, "reason": "DEVTO_API_KEY nicht gesetzt — Artikel übersprungen"}

    tags = (tags or TAGS_MAP["default"])[:4]
    payload: dict = {
        "article": {
            "title": title[:250],
            "body_markdown": body_markdown,
            "published": True,
            "tags": tags,
        }
    }
    if canonical_url:
        payload["article"]["canonical_url"] = canonical_url

    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{API_BASE}/articles",
                json=payload,
                headers={"api-key": DEVTO_API_KEY, "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                data = await r.json(content_type=None)
                if r.status in (200, 201):
                    url = data.get("url", "")
                    log.info("dev.to: Artikel veröffentlicht — %s", url)
                    return {"ok": True, "url": url, "id": data.get("id")}
                log.warning("dev.to: HTTP %d — %s", r.status, str(data)[:200])
                return {"ok": False, "status": r.status, "detail": str(data)[:200]}
    except Exception as exc:
        log.error("dev.to publish error: %s", exc)
        return {"ok": False, "error": str(exc)}


async def run_dev_to_post(topic: str = "KI-Automation für E-Commerce 2026") -> dict:
    """Scheduler entry point — generiert + postet KI-Artikel zu dev.to."""
    if not _is_active():
        return {"ok": False, "skipped": True, "reason": "DEVTO_API_KEY fehlt"}

    from modules.ai_client import generate_text_async
    ts   = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prompt = (
        f"Schreib einen professionellen dev.to Artikel auf Englisch über: {topic}\n"
        "Format: Markdown, 600-900 Wörter, H2-Überschriften, praktische Tipps, "
        "CTA am Ende für SuperMegaBot SaaS (https://dudirudibot-mega-production.up.railway.app)\n"
        "Erste Zeile: nur der Titel ohne #"
    )
    try:
        raw = await generate_text_async(prompt, max_tokens=1200)
        lines  = raw.strip().split("\n")
        title  = lines[0].lstrip("#").strip() if lines else topic
        body   = "\n".join(lines[1:]).strip() if len(lines) > 1 else raw
    except Exception:
        title = f"AI Automation for E-Commerce — {ts}"
        body  = f"*{topic}*\n\nLearn how to automate your Shopify store with AI...\n\n[Try SuperMegaBot Free](https://dudirudibot-mega-production.up.railway.app)"

    tags = ["automation", "ecommerce", "python", "ai"]
    return await publish_article(title, body, tags)
