#!/usr/bin/env python3
"""
SaaS Radar — Vollautonomer Problem-Scanner
Scannt Reddit/HN/ProductHunt auf echte Nischenprobleme mit Zahlungsbereitschaft.
Output: Ranked list of validated problems → triggers MVP Factory.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
log = logging.getLogger("SaaSRadar")

REDDIT_CLIENT_ID     = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT    = os.getenv("REDDIT_USER_AGENT", "SuperMegaBot/1.0")
ANTHROPIC_API_KEY    = os.getenv("ANTHROPIC_API_KEY", "")
OPENROUTER_API_KEY   = os.getenv("OPENROUTER_API_KEY", "")

PAIN_SUBREDDITS = [
    "entrepreneur", "SaaS", "smallbusiness", "freelance", "productivity",
    "webdev", "Entrepreneur", "startups", "digitalnomad", "ecommerce",
    "shopify", "dropshipping", "Accounting", "legaladvice", "marketing",
]

PAIN_SIGNALS = [
    r"wish there (was|were|is)",
    r"(hate|annoying|frustrating) when",
    r"(waste|wasting|wasted) (hours?|days?|time)",
    r"no tool (exists|for this|that)",
    r"(would|will) pay (for|someone|anything)",
    r"(can't find|couldn't find) (a |an |any )?tool",
    r"(manually|by hand|one by one)",
    r"(nightmare|pain in the ass|pain point)",
    r"(spend|spent) (hours?|days?) (just )?(to|on)",
    r"does (anyone|anybody) know (of )?(a |an )?tool",
]

WILLINGNESS_TO_PAY = [
    r"\€\d+", r"\$\d+", r"pay(ing)?", r"subscri(be|ption|bing)",
    r"worth it", r"pricing", r"(per|a) month", r"lifetime",
    r"saas", r"tool", r"software", r"app",
]

STATE_FILE = Path(__file__).parent.parent / "data" / "saas_radar_state.json"


def _load_state() -> dict:
    STATE_FILE.parent.mkdir(exist_ok=True)
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"seen_ids": [], "validated_problems": [], "last_scan": 0}


def _save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))


def _score_post(title: str, body: str, score: int, comments: int) -> tuple[float, list[str]]:
    text = (title + " " + body).lower()
    pain_hits = [p for p in PAIN_SIGNALS if re.search(p, text)]
    pay_hits  = [p for p in WILLINGNESS_TO_PAY if re.search(p, text)]

    if not pain_hits:
        return 0.0, []

    base = len(pain_hits) * 15 + len(pay_hits) * 25
    base += min(score / 10, 50)
    base += min(comments * 2, 30)
    return round(base, 1), pain_hits + pay_hits


async def _get_reddit_token(session: aiohttp.ClientSession) -> str:
    if not (REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET):
        return ""
    try:
        async with session.post(
            "https://www.reddit.com/api/v1/access_token",
            data={"grant_type": "client_credentials"},
            auth=aiohttp.BasicAuth(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET),
            headers={"User-Agent": REDDIT_USER_AGENT},
        ) as r:
            if r.status == 200:
                d = await r.json()
                return d.get("access_token", "")
    except Exception as e:
        log.warning(f"Reddit token error: {e}")
    return ""


async def _scan_subreddit(
    session: aiohttp.ClientSession, token: str, sub: str, limit: int = 25
) -> list[dict]:
    headers = {"User-Agent": REDDIT_USER_AGENT}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    results = []
    base = "https://oauth.reddit.com" if token else "https://www.reddit.com"
    try:
        async with session.get(
            f"{base}/r/{sub}/hot.json",
            params={"limit": limit},
            headers=headers,
        ) as r:
            if r.status != 200:
                return results
            data = await r.json()
            posts = data.get("data", {}).get("children", [])
            for p in posts:
                d = p.get("data", {})
                post_id = d.get("id", "")
                title   = d.get("title", "")
                body    = d.get("selftext", "")
                score_v = d.get("score", 0)
                comments= d.get("num_comments", 0)
                url     = d.get("url", "")
                author  = d.get("author", "")

                pain_score, signals = _score_post(title, body, score_v, comments)
                if pain_score >= 30:
                    results.append({
                        "id":         post_id,
                        "subreddit":  sub,
                        "title":      title,
                        "body":       body[:500],
                        "score":      score_v,
                        "comments":   comments,
                        "url":        f"https://reddit.com{d.get('permalink','')}",
                        "author":     author,
                        "pain_score": pain_score,
                        "signals":    signals[:5],
                        "found_at":   datetime.now(timezone.utc).isoformat(),
                    })
    except Exception as e:
        log.warning(f"Subreddit {sub}: {e}")
    return results


async def _scan_hn_front(session: aiohttp.ClientSession) -> list[dict]:
    results = []
    try:
        async with session.get(
            "https://hacker-news.firebaseio.com/v0/topstories.json"
        ) as r:
            if r.status != 200:
                return results
            ids = (await r.json())[:30]

        async def fetch_item(item_id: int) -> dict | None:
            try:
                async with session.get(
                    f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json"
                ) as r:
                    if r.status == 200:
                        return await r.json()
            except Exception:
                pass
            return None

        items = await asyncio.gather(*[fetch_item(i) for i in ids])
        for item in items:
            if not item:
                continue
            title = item.get("title", "")
            score = item.get("score", 0)
            desc  = item.get("text", "") or ""
            pain_score, signals = _score_post(title, desc, score, item.get("descendants", 0))
            if pain_score >= 25:
                results.append({
                    "id":         f"hn_{item.get('id')}",
                    "subreddit":  "HackerNews",
                    "title":      title,
                    "body":       desc[:500],
                    "score":      score,
                    "comments":   item.get("descendants", 0),
                    "url":        item.get("url", f"https://news.ycombinator.com/item?id={item.get('id')}"),
                    "pain_score": pain_score,
                    "signals":    signals[:5],
                    "found_at":   datetime.now(timezone.utc).isoformat(),
                })
    except Exception as e:
        log.warning(f"HN scan: {e}")
    return results


async def _validate_with_ai(problems: list[dict]) -> list[dict]:
    if not problems or not (ANTHROPIC_API_KEY or OPENROUTER_API_KEY):
        return problems

    prompt = f"""Du bist ein SaaS-Experte. Analysiere diese {len(problems)} Probleme aus Reddit/HN.
Für jedes Problem: bewerte ob es ein valides SaaS-Produkt rechtfertigt (1-10).

Kriterien:
- Technisch lösbar in < 1 Woche MVP
- Klare Zahlungsbereitschaft erkennbar
- Wiederholender Bedarf (Abo-Potential)
- Nicht schon 10 etablierte Konkurrenten
- Nischig genug für Alleinstellung

Probleme:
{json.dumps([{"title": p["title"], "body": p["body"][:200], "signals": p["signals"]} for p in problems[:10]], indent=2, ensure_ascii=False)}

Antworte NUR als JSON-Array:
[{{"index": 0, "saas_score": 8, "product_idea": "Name: X\\nProblem: Y\\nSolution: Z\\nPreis: €XX/Monat", "mvp_type": "webapp|chrome_ext|api|cli", "target": "Zielgruppe"}}]"""

    headers = {"Content-Type": "application/json"}
    url     = ""
    payload: dict[str, Any] = {}

    if ANTHROPIC_API_KEY:
        url  = "https://api.anthropic.com/v1/messages"
        headers.update({"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"})
        payload = {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 1500,
            "messages": [{"role": "user", "content": prompt}],
        }
    elif OPENROUTER_API_KEY:
        url  = "https://openrouter.ai/api/v1/chat/completions"
        headers["Authorization"] = f"Bearer {OPENROUTER_API_KEY}"
        payload = {
            "model": "mistralai/mistral-7b-instruct:free",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1500,
        }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as r:
                if r.status == 200:
                    resp = await r.json()
                    text = ""
                    if ANTHROPIC_API_KEY:
                        text = resp.get("content", [{}])[0].get("text", "")
                    else:
                        text = resp.get("choices", [{}])[0].get("message", {}).get("content", "")

                    m = re.search(r"\[.*?\]", text, re.DOTALL)
                    if m:
                        ratings = json.loads(m.group())
                        for r_item in ratings:
                            idx = r_item.get("index", -1)
                            if 0 <= idx < len(problems):
                                problems[idx]["saas_score"]   = r_item.get("saas_score", 5)
                                problems[idx]["product_idea"] = r_item.get("product_idea", "")
                                problems[idx]["mvp_type"]     = r_item.get("mvp_type", "webapp")
                                problems[idx]["target"]       = r_item.get("target", "")
    except Exception as e:
        log.warning(f"AI validate: {e}")

    return problems


async def run_saas_radar() -> dict:
    state = _load_state()
    seen  = set(state.get("seen_ids", []))

    log.info("SaaS Radar — scanne Reddit + HN auf Pain Points...")

    async with aiohttp.ClientSession() as session:
        token = await _get_reddit_token(session)

        tasks = [_scan_subreddit(session, token, sub) for sub in PAIN_SUBREDDITS[:8]]
        tasks.append(_scan_hn_front(session))
        results = await asyncio.gather(*tasks, return_exceptions=True)

    all_posts: list[dict] = []
    for r in results:
        if isinstance(r, list):
            all_posts.extend(r)

    # Dedup + filter seen
    fresh = [p for p in all_posts if p["id"] not in seen]
    fresh.sort(key=lambda x: x["pain_score"], reverse=True)
    fresh = fresh[:15]

    if fresh:
        fresh = await _validate_with_ai(fresh)

    # Keep top validated
    validated = [p for p in fresh if p.get("saas_score", 0) >= 6]
    validated.sort(key=lambda x: x.get("saas_score", 0), reverse=True)

    # Update state
    seen.update(p["id"] for p in fresh)
    state["seen_ids"]           = list(seen)[-500:]
    state["last_scan"]          = time.time()
    state["validated_problems"] = (
        validated[:5] + state.get("validated_problems", [])
    )[:20]
    _save_state(state)

    log.info(
        f"SaaS Radar: {len(fresh)} neue Posts · {len(validated)} validierte Probleme"
    )
    return {
        "scanned":   len(all_posts),
        "fresh":     len(fresh),
        "validated": len(validated),
        "top":       validated[:3],
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = asyncio.run(run_saas_radar())
    print(json.dumps(result, indent=2, default=str, ensure_ascii=False))
