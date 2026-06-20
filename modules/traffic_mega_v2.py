#!/usr/bin/env python3
"""
Traffic Mega v2 — RSS pings, content syndication (Dev.to, Hashnode, Reddit, Tumblr),
backlink opportunities, Amazon/Fiverr/Upwork promo, multi-platform blast.
Fully autonomous: no paid APIs required.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from datetime import datetime, timezone
from typing import Any

import aiohttp

log = logging.getLogger("TrafficMegaV2")

SHOP_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "autopilot-store-suite-fmbka.myshopify.com")
SHOP_URL = f"https://{SHOP_DOMAIN}"
DS24_URL = os.getenv("DS24_AFFILIATE_LINK", "https://www.digistore24.com/redir/669750/user37405262/")
AMAZON_TAG = os.getenv("AMAZON_AFFILIATE_TAG", "bullpowerhub-21")
DEVTO_API_KEY = os.getenv("DEVTO_API_KEY", "")
HASHNODE_TOKEN = os.getenv("HASHNODE_TOKEN", "")
HASHNODE_PUBID = os.getenv("HASHNODE_PUBLICATION_ID", "")
TUMBLR_TOKEN = os.getenv("TUMBLR_ACCESS_TOKEN", "")
TUMBLR_BLOG = os.getenv("TUMBLR_BLOG_NAME", "bullpowerhub")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USERNAME = os.getenv("REDDIT_USERNAME", "")
REDDIT_PASSWORD = os.getenv("REDDIT_PASSWORD", "")

RSS_PING_SERVICES = [
    "http://rpc.pingomatic.com/RPC2",
    "http://ping.blogs.yandex.ru/RPC2",
    "http://rpc.technorati.com/rpc/ping",
    "http://rpc.weblogs.com/RPC2",
    "http://ping.feedburner.com",
    "http://api.feedster.com/ping",
    "http://ping.feedshot.com",
    "http://ping.syndic8.com/xmlrpc.client",
    "http://ping.weblogalot.com/rpc.php",
    "http://rpc.blogrolling.com/pinger/",
    "http://www.weblogues.com/RPC/",
    "http://blogsearch.google.com/ping/RPC2",
    "http://www.blogdigger.com/RPC2",
    "http://www.blogroots.com/tb_populi.blog",
    "http://ping.blo.gs/",
    "http://ping.blogg.de/",
]

TRAFFIC_TOPICS = [
    "KI-Business Automatisierung 2026 — So startest du heute",
    "Dropshipping Erfolg: 5 Strategien die wirklich funktionieren",
    "Shopify Automation: Dein Shop läuft 24/7 ohne dich",
    "Digistore24 Affiliate: €500+ täglich mit digitalen Produkten",
    "Print on Demand mit Printify: Passives Einkommen ohne Lager",
    "Amazon Affiliate Marketing: Schritt-für-Schritt Anleitung 2026",
    "E-Mail Marketing Automation: Klaviyo vs Mailchimp 2026",
    "TikTok Shop: Produkte viral gehen lassen",
    "SEO 2026: KI-Texte die Google liebt",
    "Online Business skalieren: Von €0 zu €5000/Monat",
]

AMAZON_PRODUCTS = [
    ("Shopify E-Commerce Starter Kit", "B09XJ2Y1MF"),
    ("Print on Demand Business Kit", "B08N5WRWNW"),
    ("Online Marketing Masterclass", "B07VGQX5SK"),
    ("KI Business Tools Bundle", "B0BVWQ5X1N"),
    ("E-Commerce Automation Guide", "B08K2MXHQZ"),
]


async def _ai(prompt: str, max_tokens: int = 600) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


async def _tg(msg: str) -> None:
    try:
        from modules.telegram_hub_bridge import send_telegram_message
        await send_telegram_message(msg[:3500])
    except Exception:
        pass


async def ping_rss_directories() -> dict[str, Any]:
    results = {}
    xmlrpc_body = (
        '<?xml version="1.0"?><methodCall><methodName>weblogUpdates.ping</methodName>'
        f"<params><param><value><string>BullPowerHub</string></value></param>"
        f"<param><value><string>{SHOP_URL}</string></value></param></params></methodCall>"
    )
    tasks = []
    for ep in RSS_PING_SERVICES:
        async def _ping(endpoint: str = ep) -> tuple[str, Any]:
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.post(
                        endpoint, data=xmlrpc_body,
                        headers={"Content-Type": "text/xml"},
                        timeout=aiohttp.ClientTimeout(total=6),
                    ) as r:
                        return endpoint, r.status
            except Exception as exc:
                return endpoint, str(exc)
        tasks.append(_ping())
    raw = await asyncio.gather(*tasks, return_exceptions=True)
    for item in raw:
        if isinstance(item, tuple):
            results[item[0]] = item[1]
    ok = sum(1 for v in results.values() if v == 200)
    log.info("RSS pings: %d/%d OK", ok, len(RSS_PING_SERVICES))
    return {"ok": ok > 0, "pings": len(RSS_PING_SERVICES), "ok_count": ok, "details": results}


async def syndicate_devto(title: str, body: str, tags: list[str]) -> dict[str, Any]:
    if not DEVTO_API_KEY:
        return {"ok": False, "error": "no DEVTO_API_KEY"}
    try:
        payload = {
            "article": {
                "title": title,
                "body_markdown": body,
                "published": True,
                "tags": tags[:4],
                "canonical_url": SHOP_URL,
            }
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://dev.to/api/articles",
                json=payload,
                headers={"api-key": DEVTO_API_KEY, "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json()
                return {"ok": r.status in (200, 201), "id": data.get("id"), "url": data.get("url")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def syndicate_hashnode(title: str, body: str, tags: list[str]) -> dict[str, Any]:
    if not HASHNODE_TOKEN or not HASHNODE_PUBID:
        return {"ok": False, "error": "no HASHNODE_TOKEN or HASHNODE_PUBLICATION_ID"}
    try:
        query = """
        mutation PublishPost($input: PublishPostInput!) {
          publishPost(input: $input) {
            post { id url title }
          }
        }
        """
        variables = {
            "input": {
                "title": title,
                "contentMarkdown": body,
                "publicationId": HASHNODE_PUBID,
                "tags": [{"name": t, "slug": t.lower().replace(" ", "-")} for t in tags[:5]],
                "originalArticleURL": SHOP_URL,
            }
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://gql.hashnode.com",
                json={"query": query, "variables": variables},
                headers={"Authorization": HASHNODE_TOKEN, "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json()
                post = data.get("data", {}).get("publishPost", {}).get("post", {})
                return {"ok": bool(post.get("id")), "url": post.get("url"), "id": post.get("id")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def syndicate_tumblr(title: str, body: str) -> dict[str, Any]:
    if not TUMBLR_TOKEN:
        return {"ok": False, "error": "no TUMBLR_ACCESS_TOKEN"}
    try:
        payload = {
            "type": "text",
            "state": "published",
            "title": title,
            "body": f"{body}\n\n<a href='{DS24_URL}'>Jetzt starten →</a>",
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://api.tumblr.com/v2/blog/{TUMBLR_BLOG}.tumblr.com/post",
                json=payload,
                headers={"Authorization": f"Bearer {TUMBLR_TOKEN}", "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json()
                return {"ok": r.status in (200, 201), "id": data.get("response", {}).get("id")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def _reddit_token() -> str:
    if not all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD]):
        return ""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://www.reddit.com/api/v1/access_token",
                data={"grant_type": "password", "username": REDDIT_USERNAME, "password": REDDIT_PASSWORD},
                auth=aiohttp.BasicAuth(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET),
                headers={"User-Agent": "BullPowerHub/1.0"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                d = await r.json()
                return d.get("access_token", "")
    except Exception:
        return ""


async def syndicate_reddit(title: str, body: str) -> dict[str, Any]:
    token = await _reddit_token()
    if not token:
        return {"ok": False, "error": "Reddit auth failed — check app type=script"}
    subreddits = ["r/entrepreneur", "r/ecommerce", "r/shopify", "r/passive_income"]
    sr = random.choice(subreddits).replace("r/", "")
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://oauth.reddit.com/api/submit",
                data={"api_type": "json", "kind": "self", "sr": sr, "title": title[:300], "text": body[:10000]},
                headers={"Authorization": f"Bearer {token}", "User-Agent": "BullPowerHub/1.0"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json()
                errors = data.get("json", {}).get("errors", [])
                url = data.get("json", {}).get("data", {}).get("url", "")
                return {"ok": not errors and bool(url), "subreddit": sr, "url": url, "errors": errors}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def amazon_affiliate_blast(topic: str) -> dict[str, Any]:
    links = []
    for name, asin in AMAZON_PRODUCTS[:3]:
        url = f"https://www.amazon.de/dp/{asin}?tag={AMAZON_TAG}"
        links.append({"name": name, "url": url})

    msg = f"🛒 *Amazon Empfehlungen: {topic}*\n\n"
    for item in links:
        msg += f"• [{item['name']}]({item['url']})\n"
    msg += f"\n💼 Shop: {SHOP_URL}\n🚀 DS24: {DS24_URL}"

    await _tg(msg)

    try:
        from modules.brutus_core import fire
        content = f"Amazon Empfehlungen für {topic}: " + " | ".join(f"{i['name']} {i['url']}" for i in links)
        await fire(f"Amazon-Deals: {topic}", content, channels=["telegram", "linkedin"])
    except Exception:
        pass

    return {"ok": True, "links": links, "topic": topic}


async def run_traffic_mega_cycle() -> dict[str, Any]:
    start = time.time()
    log.info("TrafficMegaV2 cycle starting")

    topic = random.choice(TRAFFIC_TOPICS)
    body_prompt = (
        f"Schreibe einen informativen Artikel auf Deutsch über: '{topic}'\n"
        f"Shop: {SHOP_URL}\nAffiliate: {DS24_URL}\n"
        f"Format: Markdown, 300-500 Wörter, mit ## Überschriften und CTA am Ende."
    )
    body = await _ai(body_prompt, max_tokens=700)
    if not body:
        body = (
            f"# {topic}\n\n"
            f"Entdecke die besten Strategien für 2026.\n\n"
            f"## Schritt 1: Automatisierung\nNutze KI-Tools für deinen Shop.\n\n"
            f"## Schritt 2: Traffic\nMehr Traffic mit Content-Marketing.\n\n"
            f"## Fazit\n[Jetzt starten →]({DS24_URL})"
        )

    tags = ["ecommerce", "shopify", "dropshipping", "affiliate", "automation"]

    results: dict[str, Any] = {}

    rss, devto, hashnode, tumblr, reddit, amazon = await asyncio.gather(
        ping_rss_directories(),
        syndicate_devto(topic, body, tags),
        syndicate_hashnode(topic, body, tags),
        syndicate_tumblr(topic, body),
        syndicate_reddit(topic, body),
        amazon_affiliate_blast(topic),
        return_exceptions=True,
    )

    results["rss_pings"] = rss if not isinstance(rss, Exception) else {"ok": False, "error": str(rss)}
    results["devto"] = devto if not isinstance(devto, Exception) else {"ok": False, "error": str(devto)}
    results["hashnode"] = hashnode if not isinstance(hashnode, Exception) else {"ok": False, "error": str(hashnode)}
    results["tumblr"] = tumblr if not isinstance(tumblr, Exception) else {"ok": False, "error": str(tumblr)}
    results["reddit"] = reddit if not isinstance(reddit, Exception) else {"ok": False, "error": str(reddit)}
    results["amazon"] = amazon if not isinstance(amazon, Exception) else {"ok": False, "error": str(amazon)}

    elapsed = round(time.time() - start, 1)
    ok_channels = sum(1 for v in results.values() if isinstance(v, dict) and v.get("ok"))

    summary = (
        f"🚀 *Traffic Mega V2 fertig* ({elapsed}s)\n"
        f"📡 Topic: {topic[:60]}\n"
        f"✅ Kanäle erfolgreich: {ok_channels}/6\n"
        f"📻 RSS Pings: {results['rss_pings'].get('ok_count', 0)}/{len(RSS_PING_SERVICES)}\n"
        f"📝 Dev.to: {'✅' if results['devto'].get('ok') else '❌'} | "
        f"Hashnode: {'✅' if results['hashnode'].get('ok') else '❌'} | "
        f"Reddit: {'✅' if results['reddit'].get('ok') else '❌'}"
    )
    await _tg(summary)
    log.info("TrafficMegaV2 done: %d/6 channels OK, elapsed=%.1fs", ok_channels, elapsed)

    return {
        "ok": ok_channels > 0,
        "topic": topic,
        "channels_ok": ok_channels,
        "results": results,
        "elapsed": elapsed,
    }
