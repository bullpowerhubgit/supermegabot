#!/usr/bin/env python3
"""Traffic blast: Top-5 High-Ticket links → Telegram + IndexNow + sitemap ping."""
from __future__ import annotations

import asyncio
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TOP5 = [
    ("BullPower Full-Stack Empire", "€4.997/mo", "https://buy.stripe.com/fZueVf9jAguu1gc9kO4F42Ev"),
    ("BullPower Hub Business", "€2.997/mo", "https://buy.stripe.com/cNicN7cvM2DE2kg0Oi4F42DV"),
    ("BullPower Launcher Business", "€2.997/mo", "https://buy.stripe.com/00wcN71R87XYcYU8gK4F42DJ"),
    ("Shopify Empire Scale", "€2.997/mo", "https://buy.stripe.com/eVq6oJeDU922f72fJc4F42Ey"),
    ("AiiteC Agency OS Pro", "€2.497/mo", "https://buy.stripe.com/8x228t1R8guu4soeF84F42Es"),
]

LANDINGS = [
    "https://bullpower-hub.vercel.app/",
    "https://steuercockpit.vercel.app/",
    "https://rudibot-deploy.vercel.app/",
    "https://creatorai-ultra.vercel.app/",
    "https://shopify-brutal-tuning.vercel.app/",
    "https://supermegabot-production.up.railway.app/",
    "https://seo-turbo-tools-production.up.railway.app/",
]


def _load_env():
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def telegram_blast() -> dict:
    tok = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = os.getenv("TELEGRAM_CHAT_ID", "") or os.getenv("TELEGRAM_CHANNEL_ID", "")
    if not tok or not chat:
        return {"ok": False, "error": "no telegram creds"}
    lines = [
        "💰 <b>HIGH-TICKET LIVE — JETZT KAUFEN</b>",
        "",
        "Top-5 Angebote (Stripe Live):",
        "",
    ]
    for name, price, url in TOP5:
        lines.append(f"• <b>{name}</b> — {price}\n  {url}")
    lines += [
        "",
        "Landing / Demo:",
        "https://bullpower-hub.vercel.app/",
        "https://steuercockpit.vercel.app/demo.html",
        "https://rudibot-deploy.vercel.app/",
        "",
        "Catalog API: https://supermegabot-production.up.railway.app/api/money-map",
    ]
    text = "\n".join(lines)[:3900]
    data = json.dumps({
        "chat_id": chat,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{tok}/sendMessage",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = json.loads(r.read())
            return {"ok": bool(body.get("ok")), "status": r.status}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def indexnow_blast() -> dict:
    """Ping Bing IndexNow for landings (best-effort)."""
    key = os.getenv("INDEXNOW_KEY", "supermegabot")
    host = "bullpower-hub.vercel.app"
    endpoint = "https://api.indexnow.org/indexnow"
    payload = {
        "host": host,
        "key": key,
        "urlList": LANDINGS[:10],
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        endpoint,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return {"ok": r.status in (200, 202), "status": r.status}
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


def sitemap_ping() -> dict:
    results = []
    for landing in LANDINGS[:5]:
        sm = landing.rstrip("/") + "/sitemap.xml"
        for engine, base in (
            ("google", "https://www.google.com/ping?sitemap="),
            ("bing", "https://www.bing.com/ping?sitemap="),
        ):
            try:
                urllib.request.urlopen(base + urllib.parse.quote(sm, safe=""), timeout=8)
                results.append({"engine": engine, "url": sm, "ok": True})
            except Exception as e:
                results.append({"engine": engine, "url": sm, "ok": False, "error": str(e)[:80]})
    return {"pings": len(results), "ok_count": sum(1 for r in results if r.get("ok")), "details": results[:6]}


async def maybe_twitter() -> dict:
    try:
        # best-effort if module exists
        from modules import twitter_client  # type: ignore
        if hasattr(twitter_client, "post_tweet"):
            msg = (
                "High-Ticket Automation live ⚡ Full-Stack Empire €4.997/mo "
                "https://buy.stripe.com/fZueVf9jAguu1gc9kO4F42Ev"
            )
            r = await twitter_client.post_tweet(msg)
            return {"ok": True, "result": str(r)[:120]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}
    return {"ok": False, "skipped": True}


def main():
    _load_env()
    out = {
        "telegram": telegram_blast(),
        "indexnow": indexnow_blast(),
        "sitemap": sitemap_ping(),
        "top5": [{"name": n, "price": p, "url": u} for n, p, u in TOP5],
    }
    try:
        out["twitter"] = asyncio.get_event_loop().run_until_complete(maybe_twitter())
    except Exception as e:
        out["twitter"] = {"ok": False, "error": str(e)[:100]}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return out


if __name__ == "__main__":
    main()
