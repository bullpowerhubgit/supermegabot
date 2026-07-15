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
DS24_LINK            = os.getenv("DS24_AFFILIATE_LINK", "")

TARGET_SUBREDDITS = [
    # Verified working via cookie-auth (no flair req, no AI-block):
    "smallbusiness",
    "Flipping",
    "WorkOnline",
    "SideProject",
    "dropshipping",
    "makinmoney",
    "passive_income",     # requires flair — cookie poster handles gracefully
    "affiliatemarketing",
]

_USER_AGENT = "SuperMegaBot/2.0 by /u/bullpowersrtkennels"


def _load_refresh_token() -> str:
    """Load refresh token from env var or persistent file."""
    rt = os.getenv("REDDIT_REFRESH_TOKEN", "")
    if rt:
        return rt
    try:
        import json as _json
        from pathlib import Path
        data_dir = Path(os.getenv("DATA_DIR", "/tmp"))
        rt_file = data_dir / "reddit_refresh_token.json"
        if rt_file.exists():
            return _json.loads(rt_file.read_text()).get("refresh_token", "")
    except Exception as _e:
        log.debug("skipped: %s", _e)
    return ""


async def _get_token() -> str:
    """Get Reddit access token via refresh_token (OAuth2) or password grant (script apps)."""
    refresh_token = _load_refresh_token()
    if refresh_token and REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET:
        try:
            import base64
            creds = base64.b64encode(f"{REDDIT_CLIENT_ID}:{REDDIT_CLIENT_SECRET}".encode()).decode()
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    "https://www.reddit.com/api/v1/access_token",
                    headers={"Authorization": f"Basic {creds}", "User-Agent": _USER_AGENT},
                    data={"grant_type": "refresh_token", "refresh_token": refresh_token},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as r:
                    d = await r.json(content_type=None)
            token = d.get("access_token", "")
            if token:
                log.info("Reddit token via refresh_token OK")
                return token
        except Exception as e:
            log.warning("Reddit refresh_token error: %s", e)

    # Fallback: password grant (only works for "script" app type)
    if not all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD]):
        log.warning("Reddit: no refresh token and no password credentials — visit /api/reddit/auth to authorize")
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
            log.info("Reddit token via password grant OK")
        else:
            log.warning("Reddit password grant failed (app type may be 'web app' — visit /api/reddit/auth)")
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
    """Post to up to 3 subreddits per run — Cookie Auth primary, OAuth2 fallback."""
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

    # Primary: Cookie-based auth (no OAuth2 app needed)
    try:
        from modules.reddit_cookie_poster import post_to_subreddits as _cookie_post
        results = await _cookie_post(title=title, text=text, subreddits=selected, max_posts=3)
        posted = sum(1 for r in results if r.get("ok"))
        if posted > 0:
            log.info("Reddit blast (cookie): %d/%d posted", posted, len(selected))
            return {"ok": True, "posted": posted, "total": len(selected),
                    "method": "cookie_auth", "results": results}
        log.warning("Cookie auth got 0 posts, trying OAuth2 fallback")
    except Exception as e:
        log.warning("Cookie poster error: %s", e)

    # Fallback: OAuth2 token
    token = await _get_token()
    if not token:
        return {"ok": False, "error": "No auth method available (cookie + OAuth2 both failed)", "posted": 0}

    tasks = [_post_to_subreddit(sub, title, text, token) for sub in selected]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    clean = [r if not isinstance(r, Exception) else {"ok": False, "error": str(r)} for r in results]
    posted = sum(1 for r in clean if r.get("ok"))
    log.info("Reddit blast (oauth2): %d/%d posted", posted, len(selected))
    return {"ok": posted > 0, "posted": posted, "total": len(selected),
            "method": "oauth2", "results": clean}


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
