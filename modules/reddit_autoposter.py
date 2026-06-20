"""Reddit auto-poster — DS24 + Shopify affiliate content to relevant subreddits."""
import os
import logging
import asyncio
import aiohttp
from datetime import datetime, timezone

log = logging.getLogger("RedditPoster")

REDDIT_CLIENT_ID     = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USERNAME      = os.getenv("REDDIT_USERNAME", "")
REDDIT_PASSWORD      = os.getenv("REDDIT_PASSWORD", "")
DS24_LINK            = os.getenv("DS24_AFFILIATE_LINK", "https://www.digistore24.com/redir/669750/user37405262/")

TARGET_SUBREDDITS = [
    "passive_income",
    "entrepreneur",
    "ecommerce",
    "dropshipping",
    "affiliatemarketing",
    "shopify",
    "onlinebusiness",
    "digitalnomad",
]

_USER_AGENT = "SuperMegaBot/2.0 by /u/bullpowersrtkennels"


async def _get_token() -> str:
    if not all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD]):
        return ""
    try:
        auth = aiohttp.BasicAuth(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET)
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://www.reddit.com/api/v1/access_token",
                auth=auth,
                data={"grant_type": "password", "username": REDDIT_USERNAME, "password": REDDIT_PASSWORD},
                headers={"User-Agent": _USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                d = await r.json(content_type=None)
        token = d.get("access_token", "")
        if token:
            log.info("Reddit token obtained")
        return token
    except Exception as e:
        log.warning("Reddit token error: %s", e)
        return ""


async def _post_to_subreddit(subreddit: str, title: str, text: str, token: str) -> dict:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://oauth.reddit.com/api/submit",
                headers={"Authorization": f"bearer {token}", "User-Agent": _USER_AGENT},
                data={"sr": subreddit, "kind": "self", "title": title[:300], "text": text[:10000], "nsfw": False},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                d = await r.json(content_type=None)
        errors = d.get("json", {}).get("errors", [])
        post_id = d.get("json", {}).get("data", {}).get("id", "")
        return {"ok": not errors and bool(post_id), "post_id": post_id, "subreddit": subreddit, "errors": errors}
    except Exception as e:
        return {"ok": False, "error": str(e), "subreddit": subreddit}


async def run_reddit_blast(topic: str = "passives Einkommen KI 2026") -> dict:
    """Post to up to 3 subreddits per run to avoid spam detection."""
    token = await _get_token()
    if not token:
        return {
            "ok": False,
            "error": "REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET + REDDIT_USERNAME + REDDIT_PASSWORD required",
            "posted": 0,
        }

    title = f"[Guide] {topic} — Vollständiger Leitfaden 2026"
    text = (
        f"Hey alle!\n\nIch wollte meine Erfahrungen teilen, wie man mit KI-Tools wirklich passives Einkommen aufbaut.\n\n"
        f"**Was wirklich funktioniert:**\n\n"
        f"1. **Automatisierte Shops** — Shopify + KI-Produktbeschreibungen + Auto-Fulfillment\n"
        f"2. **Affiliate Marketing** — Digistore24 Produkte mit hohen Provisionen bewerben\n"
        f"3. **KI Content Creation** — Einmal erstellen, immer wieder recyceln\n\n"
        f"**Das Tool das alles vereint:** {DS24_LINK}\n\n"
        f"Hat jemand ähnliche Erfahrungen? Gerne im Kommentar teilen!\n\n"
        f"---\n*Eigene Erfahrungen, kein bezahlter Post*"
    )

    # Rotate subreddits based on hour to spread posts over time
    hour = datetime.now(timezone.utc).hour
    offset = (hour // 8) % len(TARGET_SUBREDDITS)
    selected = TARGET_SUBREDDITS[offset:offset + 3] or TARGET_SUBREDDITS[:3]

    tasks = [_post_to_subreddit(sub, title, text, token) for sub in selected]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    clean = []
    for r in results:
        if isinstance(r, Exception):
            clean.append({"ok": False, "error": str(r)})
        else:
            clean.append(r)

    posted = sum(1 for r in clean if r.get("ok"))
    log.info("Reddit blast: %d/%d posted", posted, len(selected))
    return {"ok": posted > 0, "posted": posted, "total": len(selected), "results": clean}


async def run_with_brutus_traffic(topic: str = "passives Einkommen KI 2026") -> dict:
    """Reddit blast + BRUTUS traffic swarm."""
    reddit_result = await run_reddit_blast(topic)
    try:
        from modules.brutus_traffic_engine import brutus_blast_for_tool
        brutus_result = await brutus_blast_for_tool(
            "Reddit Affiliate",
            DS24_LINK,
            keywords=["reddit passive income", "affiliate marketing reddit", topic],
        )
    except Exception as e:
        brutus_result = {"error": str(e)}
    return {"reddit": reddit_result, "brutus": brutus_result}
