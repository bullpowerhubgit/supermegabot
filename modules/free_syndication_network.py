#!/usr/bin/env python3
"""
FreeSyndicationNetwork — Kein App-Review nötig, sofort aktiv.
Postet automatisch auf 5+ Plattformen die keine Facebook/Google-Review brauchen.

Kanäle:
- Dev.to      (Developer Community 500K+ Leser, kostenlose API)
- Hashnode    (Developer Blog, SEO-stark)
- Telegram    (direkt, immer aktiv)
- Substack    (Newsletter-Kanal via RSS)
- Gumroad     (Produkt-Updates, Marketplace-Traffic)
- Medium      (API-Key optional)
- Discord     (Webhook, kein Token nötig)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("FreeSyndication")

DATA_DIR    = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data" / "syndication"))
ANTHROPIC   = os.getenv("ANTHROPIC_API_KEY", "")
TG_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN", "")
_TG_CHANNEL = os.getenv("TELEGRAM_CHANNEL_ID", "")
TG_CHAT     = _TG_CHANNEL or ""
DEVTO_KEY   = os.getenv("DEVTO_API_KEY", "")
HASHNODE_KEY = os.getenv("HASHNODE_API_KEY", "")
HASHNODE_PUB = os.getenv("HASHNODE_PUBLICATION_ID", "")
MEDIUM_KEY  = os.getenv("MEDIUM_API_KEY", "")
DISCORD_WH  = os.getenv("DISCORD_WEBHOOK_URL", "")
GUMROAD_TOKEN = os.getenv("GUMROAD_ACCESS_TOKEN", "")
DS24_AFFILIATE = os.getenv("DS24_AFFILIATE_LINK", "")


# ── Content Generator ─────────────────────────────────────────────────────────

async def _generate_article(topic: str, platform: str = "devto") -> dict:
    """Generate platform-specific article via AI fallback chain."""
    try:
        from modules.ai_client import ai_complete
        style_hints = {
            "devto": "Schreibe einen informativen Tech-Artikel für Entwickler und Unternehmer. Nutze Markdown-Formatierung mit ##-Überschriften, Code-Beispielen und Listen. 600-800 Wörter.",
            "hashnode": "Schreibe einen detaillierten Tutorial-Artikel für Developer. Markdown mit Code-Snippets. 700-900 Wörter.",
            "medium": "Schreibe einen Story-Artikel für allgemeines Publikum. Persönlich, motivierend. 500-700 Wörter.",
        }.get(platform, "Schreibe einen informativen Artikel. 500-700 Wörter.")

        prompt = f"""Erstelle einen Artikel zum Thema: "{topic}"

{style_hints}

Integriere natürlich Links zu unserem Tool (Affiliate): {DS24_AFFILIATE}

Antworte NUR mit JSON:
{{
  "title": "SEO-optimierter Artikel-Titel (max 70 Zeichen)",
  "content": "vollständiger Artikel in Markdown",
  "tags": ["tag1", "tag2", "tag3", "tag4"],
  "description": "Meta-Beschreibung (max 160 Zeichen)",
  "cover_image": ""
}}"""
        raw = await ai_complete(prompt, max_tokens=1500)
        if not raw:
            return _fallback_article(topic, platform)
        s, e = raw.find("{"), raw.rfind("}") + 1
        result = json.loads(raw[s:e]) if s >= 0 else {}
        if not result.get("title") or not result.get("content"):
            return _fallback_article(topic, platform)
        return result
    except Exception as exc:
        log.warning("Article generation failed: %s", exc)
        return _fallback_article(topic, platform)


def _fallback_article(topic: str, platform: str) -> dict:
    return {
        "title": f"{topic} — Der komplette Guide 2026",
        "content": f"""# {topic} — Der komplette Guide 2026

## Warum {topic} jetzt wichtig ist

In der heutigen digitalen Wirtschaft ist es entscheidend, die richtigen Tools zu nutzen.
{topic} ermöglicht es dir, schneller und effizienter zu arbeiten.

## Die wichtigsten Strategien

1. **Automatisierung nutzen** — Lass KI-Tools die Arbeit erledigen
2. **Mehrere Einkommensströme** — Diversifiziere deine Quellen
3. **Passives Einkommen aufbauen** — Einmal einrichten, dauerhaft verdienen

## Das beste Tool für {topic}

Für maximale Effizienz empfehle ich: [{DS24_AFFILIATE}]({DS24_AFFILIATE})

## Fazit

Mit den richtigen Strategien und Tools kannst du {topic} meistern und dein Einkommen steigern.

---
*Dieser Artikel wurde von BullPower Hub erstellt — Dein Partner für Online-Business.*
""",
        "tags": ["business", "passive-income", "automation", "ai"],
        "description": f"Kompletter Guide zu {topic} — Strategien, Tools und Tipps für 2026",
        "cover_image": "",
    }


# ── Dev.to Publisher ──────────────────────────────────────────────────────────

async def post_to_devto(article: dict) -> dict:
    """POST article to dev.to via API."""
    if not DEVTO_KEY:
        return {"ok": False, "error": "DEVTO_API_KEY not set"}
    try:
        import aiohttp
        payload = {
            "article": {
                "title": article.get("title", ""),
                "body_markdown": article.get("content", ""),
                "published": True,
                "tags": article.get("tags", [])[:4],
                "description": article.get("description", ""),
            }
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://dev.to/api/articles",
                headers={"api-key": DEVTO_KEY, "Content-Type": "application/json"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                data = await r.json(content_type=None)
        if "id" in data:
            url = data.get("url", "")
            log.info("Dev.to published: %s → %s", article["title"][:40], url)
            return {"ok": True, "url": url, "id": data["id"]}
        return {"ok": False, "error": str(data.get("error", data))}
    except Exception as exc:
        log.warning("Dev.to post failed: %s", exc)
        return {"ok": False, "error": str(exc)}


# ── Hashnode Publisher ────────────────────────────────────────────────────────

async def post_to_hashnode(article: dict) -> dict:
    """POST article to Hashnode via GraphQL API."""
    if not HASHNODE_KEY:
        return {"ok": False, "error": "HASHNODE_API_KEY not set"}
    try:
        import aiohttp
        pub_id = HASHNODE_PUB or ""
        mutation = """
        mutation PublishPost($input: PublishPostInput!) {
          publishPost(input: $input) {
            post { id url title }
          }
        }
        """
        variables = {
            "input": {
                "title": article.get("title", ""),
                "contentMarkdown": article.get("content", ""),
                "tags": [{"name": t, "slug": t.lower().replace(" ", "-")}
                         for t in article.get("tags", [])[:4]],
                "publicationId": pub_id,
            }
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://gql.hashnode.com",
                headers={"Authorization": HASHNODE_KEY, "Content-Type": "application/json"},
                json={"query": mutation, "variables": variables},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                data = await r.json(content_type=None)
        post = data.get("data", {}).get("publishPost", {}).get("post", {})
        if post.get("id"):
            log.info("Hashnode published: %s → %s", article["title"][:40], post.get("url", ""))
            return {"ok": True, "url": post.get("url", ""), "id": post["id"]}
        errors = data.get("errors", [])
        return {"ok": False, "error": str(errors)}
    except Exception as exc:
        log.warning("Hashnode post failed: %s", exc)
        return {"ok": False, "error": str(exc)}


# ── Medium Publisher ──────────────────────────────────────────────────────────

async def post_to_medium(article: dict) -> dict:
    """POST article to Medium via Integration Token."""
    if not MEDIUM_KEY:
        return {"ok": False, "error": "MEDIUM_API_KEY not set"}
    try:
        import aiohttp
        # Get author ID first
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://api.medium.com/v1/me",
                headers={"Authorization": f"Bearer {MEDIUM_KEY}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                me = await r.json(content_type=None)
        user_id = me.get("data", {}).get("id", "")
        if not user_id:
            return {"ok": False, "error": "Could not get Medium user ID"}

        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://api.medium.com/v1/users/{user_id}/posts",
                headers={"Authorization": f"Bearer {MEDIUM_KEY}", "Content-Type": "application/json"},
                json={
                    "title": article.get("title", ""),
                    "contentFormat": "markdown",
                    "content": article.get("content", ""),
                    "tags": article.get("tags", [])[:5],
                    "publishStatus": "public",
                },
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                data = await r.json(content_type=None)
        post = data.get("data", {})
        if post.get("id"):
            url = post.get("url", "")
            log.info("Medium published: %s → %s", article["title"][:40], url)
            return {"ok": True, "url": url, "id": post["id"]}
        return {"ok": False, "error": str(data)}
    except Exception as exc:
        log.warning("Medium post failed: %s", exc)
        return {"ok": False, "error": str(exc)}


# ── Discord Publisher ─────────────────────────────────────────────────────────

async def post_to_discord(article: dict, blog_url: str = "") -> dict:
    """POST article summary to Discord webhook."""
    if not DISCORD_WH:
        return {"ok": False, "error": "DISCORD_WEBHOOK_URL not set"}
    try:
        import aiohttp
        description = (article.get("description") or article.get("content", "")[:300]).strip() + "..."
        embed = {
            "title": article.get("title", ""),
            "description": description,
            "color": 0x00ff88,
            "url": blog_url or DS24_AFFILIATE,
            "footer": {"text": "BullPower Hub — SuperMegaBot"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(
                DISCORD_WH,
                json={"embeds": [embed]},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                ok = r.status in (200, 204)
        log.info("Discord post: %s", "ok" if ok else "failed")
        return {"ok": ok}
    except Exception as exc:
        log.warning("Discord post failed: %s", exc)
        return {"ok": False, "error": str(exc)}


# ── Telegram Publisher ────────────────────────────────────────────────────────

async def post_to_telegram(article: dict, blog_url: str = "") -> dict:
    """Send article teaser to Telegram channel."""
    if not TG_TOKEN or not TG_CHAT:
        return {"ok": False, "error": "Telegram not configured"}
    try:
        import aiohttp
        link = blog_url or DS24_AFFILIATE
        teaser = (article.get("description") or article.get("content", "")[:200]).strip()
        text = f"📝 <b>{article.get('title', '')}</b>\n\n{teaser}\n\n🔗 <a href='{link}'>Artikel lesen</a>"
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": text[:4096],
                      "parse_mode": "HTML", "disable_web_page_preview": False},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                data = await r.json(content_type=None)
        return {"ok": data.get("ok", False)}
    except Exception as exc:
        log.warning("Telegram post failed: %s", exc)
        return {"ok": False, "error": str(exc)}


# ── Main Run Function ─────────────────────────────────────────────────────────

TOPICS = [
    "Passives Einkommen 2026 — KI Tools die wirklich funktionieren",
    "Shopify Automation für Anfänger — Kompletter Guide",
    "Geld verdienen mit KI — 5 bewährte Strategien",
    "Dropshipping 2026 — Was noch funktioniert und was nicht",
    "Affiliate Marketing mit KI beschleunigen",
    "Online Business automatisieren — von 0 auf 5.000€/Monat",
    "Digistore24 Produkte erfolgreich bewerben",
    "E-Commerce Automation mit Python und KI",
    "Passive Income Streams aufbauen — Schritt für Schritt",
    "KI Business Blueprint — Vollautomatisches Online-Einkommen",
]


async def run_free_syndication(topic: str | None = None) -> dict:
    """Run full syndication cycle across all free platforms."""
    if os.getenv("SOCIAL_POSTING_PAUSED", "").lower() in ("1", "true", "yes"):
        log.warning("FreeSyndication: SOCIAL_POSTING_PAUSED=true — übersprungen")
        return {"ok": False, "skipped": True, "reason": "SOCIAL_POSTING_PAUSED"}
    import random
    if not topic:
        topic = random.choice(TOPICS)

    log.info("FreeSyndication: generating content for '%s'", topic[:50])

    # Generate articles for each platform in parallel
    devto_art, medium_art = await asyncio.gather(
        _generate_article(topic, "devto"),
        _generate_article(topic, "medium"),
        return_exceptions=True,
    )
    if isinstance(devto_art, Exception):
        devto_art = _fallback_article(topic, "devto")
    if isinstance(medium_art, Exception):
        medium_art = _fallback_article(topic, "medium")

    # Post to all platforms in parallel
    results = await asyncio.gather(
        post_to_devto(devto_art),
        post_to_hashnode(devto_art),
        post_to_medium(medium_art),
        post_to_discord(devto_art),
        post_to_telegram(devto_art),
        return_exceptions=True,
    )

    names = ["devto", "hashnode", "medium", "discord", "telegram"]
    summary = {}
    for name, res in zip(names, results):
        if isinstance(res, Exception):
            summary[name] = {"ok": False, "error": str(res)}
        else:
            summary[name] = res

    ok_count = sum(1 for r in summary.values() if r.get("ok"))
    log.info("FreeSyndication done: %d/5 platforms — topic='%s'", ok_count, topic[:40])

    # Log to data dir
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        log_file = DATA_DIR / "syndication_log.jsonl"
        with log_file.open("a") as f:
            f.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "topic": topic,
                "results": summary,
            }) + "\n")
    except Exception:
        pass

    return {"ok": ok_count > 0, "platforms_ok": ok_count, "topic": topic, "results": summary}
