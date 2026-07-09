"""
Hashnode Publisher — vollautonomes Artikel-Posting zu Hashnode via GraphQL.
Aktiviert sich automatisch wenn HASHNODE_TOKEN + HASHNODE_PUBLICATION_ID gesetzt.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone

import aiohttp

log = logging.getLogger("HashnodePublisher")

HASHNODE_TOKEN          = os.getenv("HASHNODE_TOKEN", "")
HASHNODE_PUBLICATION_ID = os.getenv("HASHNODE_PUBLICATION_ID", "")
GQL_URL                 = "https://gql.hashnode.com"


def _is_active() -> bool:
    return bool(HASHNODE_TOKEN and HASHNODE_PUBLICATION_ID)


def _slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower())
    return s.strip("-")[:80]


async def publish_article(title: str, body_markdown: str,
                          tags: list[str] | None = None) -> dict:
    if not _is_active():
        return {"ok": False, "reason": "HASHNODE_TOKEN oder HASHNODE_PUBLICATION_ID fehlt"}

    tags_gql = [{"name": t, "slug": _slug(t)} for t in (tags or ["automation", "ecommerce"])[:5]]

    mutation = """
    mutation PublishPost($input: PublishPostInput!) {
      publishPost(input: $input) {
        post { id url title }
      }
    }
    """
    variables = {
        "input": {
            "title":          title[:250],
            "contentMarkdown": body_markdown,
            "publicationId":  HASHNODE_PUBLICATION_ID,
            "tags":           tags_gql,
            "slug":           _slug(title),
        }
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                GQL_URL,
                json={"query": mutation, "variables": variables},
                headers={"Authorization": HASHNODE_TOKEN, "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                data = await r.json(content_type=None)
        post = data.get("data", {}).get("publishPost", {}).get("post", {})
        if post.get("url"):
            log.info("Hashnode: Artikel veröffentlicht — %s", post["url"])
            return {"ok": True, "url": post["url"], "id": post.get("id")}
        errors = data.get("errors", [])
        log.warning("Hashnode GraphQL errors: %s", errors)
        return {"ok": False, "errors": errors}
    except Exception as exc:
        log.error("Hashnode publish error: %s", exc)
        return {"ok": False, "error": str(exc)}


async def run_hashnode_post(topic: str = "Shopify Automation mit KI — 2026 Guide") -> dict:
    """Scheduler entry point."""
    if not _is_active():
        return {"ok": False, "skipped": True, "reason": "HASHNODE_TOKEN/PUBLICATION_ID fehlt"}

    from modules.ai_client import generate_text_async
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prompt = (
        f"Write a professional Hashnode blog post in English about: {topic}\n"
        "Format: Markdown, 700-1000 words, H2 headings, practical code examples, "
        "CTA for SuperMegaBot (https://supermegabot-production.up.railway.app)\n"
        "First line: title only (no #)"
    )
    try:
        raw   = await generate_text_async(prompt, max_tokens=1400)
        lines = raw.strip().split("\n")
        title = lines[0].lstrip("#").strip() if lines else topic
        body  = "\n".join(lines[1:]).strip() if len(lines) > 1 else raw
    except Exception:
        title = f"Shopify AI Automation Guide — {ts}"
        body  = "## Introduction\n\nAutomate your Shopify store with AI...\n\n[Try SuperMegaBot](https://supermegabot-production.up.railway.app)"

    return await publish_article(title, body, ["automation", "ecommerce", "ai", "shopify"])
