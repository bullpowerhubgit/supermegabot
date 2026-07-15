"""
Traffic Maximizer — koordiniert alle Traffic-Quellen auf maximale Leistung.
Täglich 3× aufgerufen vom Scheduler. Kein manueller Eingriff nötig.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import time
import xml.etree.ElementTree as ET
from datetime import datetime, date
from pathlib import Path

import aiohttp

log = logging.getLogger("TrafficMaximizer")

_DB = Path(__file__).parent.parent / "data" / "traffic_maximizer.db"

STRIPE_STARTER  = "https://buy.stripe.com/7sYeVf53k5PQ7EA2Wq4F203"
STRIPE_PRO      = "https://buy.stripe.com/bJecN7gM23HIgb6dB44F204"
DS24_AFFILIATE  = "https://www.checkout-ds24.com/product/668035?affiliate=user37405262"
SHOPIFY_VERSION = os.getenv("SHOPIFY_API_VERSION", "2024-01")


# ── DB ────────────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    _DB.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS posts (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        REAL,
            platform  TEXT,
            topic     TEXT,
            content   TEXT,
            result    TEXT,
            ok        INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS daily_stats (
            day        TEXT PRIMARY KEY,
            posts_ok   INTEGER DEFAULT 0,
            posts_fail INTEGER DEFAULT 0,
            platforms  TEXT DEFAULT '',
            reach_est  INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS topics_cache (
            ts     REAL,
            topics TEXT
        );
    """)
    conn.commit()
    return conn


def _log_post(platform: str, topic: str, content: str, result: str, ok: bool) -> None:
    conn = _db()
    conn.execute(
        "INSERT INTO posts (ts, platform, topic, content, result, ok) VALUES (?,?,?,?,?,?)",
        (time.time(), platform, topic[:120], content[:400], result[:200], 1 if ok else 0),
    )
    day = str(date.today())
    conn.execute("""
        INSERT INTO daily_stats (day, posts_ok, posts_fail, platforms)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(day) DO UPDATE SET
          posts_ok   = posts_ok   + excluded.posts_ok,
          posts_fail = posts_fail + excluded.posts_fail,
          platforms  = CASE WHEN instr(platforms, ?) > 0 THEN platforms
                            ELSE trim(platforms || ',' || ?, ',') END
    """, (day, 1 if ok else 0, 0 if ok else 1, platform, platform, platform))
    conn.commit()
    conn.close()


# ── Trending Topics ───────────────────────────────────────────────────────────

async def fetch_trending_topics(session: aiohttp.ClientSession) -> list:
    """Google Trends DE (RSS) + HN — Top-5 Topics."""
    conn = _db()
    row = conn.execute("SELECT ts, topics FROM topics_cache ORDER BY ts DESC LIMIT 1").fetchone()
    conn.close()
    if row and (time.time() - row["ts"]) < 7200:
        return row["topics"].split("|||")[:5]

    topics = []

    try:
        async with session.get(
            "https://trends.google.com/trends/trendingsearches/daily/rss?geo=DE",
            timeout=aiohttp.ClientTimeout(total=8),
        ) as r:
            if r.status == 200:
                root = ET.fromstring(await r.text())
                for item in root.iter("item"):
                    t = item.findtext("title", "")
                    if t and len(topics) < 5:
                        topics.append(t)
    except Exception as e:
        log.debug("Trends: %s", e)

    if len(topics) < 5:
        try:
            async with session.get(
                "https://hacker-news.firebaseio.com/v0/topstories.json",
                timeout=aiohttp.ClientTimeout(total=6),
            ) as r:
                ids = (await r.json())[:10] if r.status == 200 else []
            for sid in ids[:5 - len(topics)]:
                async with session.get(
                    f"https://hacker-news.firebaseio.com/v0/item/{sid}.json",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as r:
                    if r.status == 200:
                        d = await r.json()
                        if d and d.get("title"):
                            topics.append(d["title"])
        except Exception as e:
            log.debug("HN: %s", e)

    if not topics:
        topics = ["E-Commerce Automatisierung 2026", "Shopify KI Tools", "DACH Online-Shop"]

    conn = _db()
    conn.execute("DELETE FROM topics_cache")
    conn.execute("INSERT INTO topics_cache (ts, topics) VALUES (?,?)",
                 (time.time(), "|||".join(topics)))
    conn.commit()
    conn.close()
    return topics[:5]


# ── KI-Content via Groq (kostenlos) ──────────────────────────────────────────

_PROMPTS = {
    "linkedin": (
        "Du bist Rudolf Sarkany, Gründer SuperMegaBot (E-Commerce Automation SaaS). "
        "LinkedIn-Post DEUTSCH, 900-1200 Zeichen. Hook: Zahl/Provokation. Body: 3 konkrete Vorteile. "
        "CTA: 'Demo buchen → {link}'. Max 3 Hashtags. Professionell."
    ),
    "facebook": (
        "Facebook-Post DEUTSCH 300-500 Zeichen. Locker, 2-3 Emojis. Problem→Lösung→CTA. "
        "CTA: 'Mehr infos: {link}'. Über Shopify-Automatisierung."
    ),
    "shopify_blog": (
        "SEO Blog-Artikel DEUTSCH 1000-1500 Wörter. Thema: {topic}. "
        "H1-Titel + Einleitung + 4 H2-Abschnitte + Fazit. "
        "Keywords: 'Shopify automatisieren', 'E-Commerce Automation DACH'. "
        "Ende: 'Jetzt testen: {link}'"
    ),
    "hn": (
        "Show HN post ENGLISH, technical tone, no marketing. "
        "2-3 sentences what SuperMegaBot does (E-Commerce automation SaaS for DACH). "
        "Context: {topic}"
    ),
}


async def generate_viral_content(
    session: aiohttp.ClientSession, topic: str, platform: str
) -> str:
    from modules.ai_client import ai_complete
    prompt = _PROMPTS.get(platform, _PROMPTS["facebook"])
    prompt = prompt.replace("{topic}", topic).replace("{link}", STRIPE_STARTER)

    text = await ai_complete(prompt, system="", max_tokens=1500)
    if text:
        return text.strip()
    return _fallback(platform, topic)


def _fallback(platform: str, topic: str) -> str:
    d = {
        "linkedin": (
            f"🚀 Fakt: Die meisten DACH Shops verlieren täglich Zeit durch manuelle Prozesse.\n\n"
            f"Zum Thema {topic}: Genau deshalb habe ich SuperMegaBot gebaut.\n\n"
            f"Was wir automatisieren:\n✅ Shopify Preise & Bestände\n✅ 1.000 B2B-Emails/Tag\n"
            f"✅ Social Media Posts\n✅ KI-Telefongespräche\n\n"
            f"Demo buchen → {STRIPE_STARTER}\n\n#shopify #ecommerce #automatisierung"
        ),
        "facebook": (
            f"💡 {topic} — genau dafür gibt es SuperMegaBot.\n"
            f"Shopify vollautomatisch. Ab €49/Monat.\n"
            f"Mehr infos: {STRIPE_STARTER}"
        ),
        "shopify_blog": (
            f"# {topic}: Shopify 2026 vollautomatisch betreiben\n\n"
            f"E-Commerce Automatisierung ist der Schlüssel für DACH Online-Shops.\n\n"
            f"Jetzt testen: {STRIPE_STARTER}"
        ),
        "hn": (
            f"Show HN: SuperMegaBot — E-Commerce automation for DACH market\n\n"
            f"Sends 1k cold B2B emails/day, syncs Shopify, AI phone agent for demos. "
            f"Context: {topic}"
        ),
    }
    return d.get(platform, d["facebook"])


# ── Platform Poster ───────────────────────────────────────────────────────────

async def post_shopify_blog(
    session: aiohttp.ClientSession, title: str, content: str, tags: list
) -> dict:
    domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
    token  = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
    if not domain or not token:
        return {"ok": False, "error": "Shopify credentials fehlen"}

    try:
        from modules.post_guardian import validate_post
        ok_g, errors = validate_post(content, "shopify_blog", "")
        if not ok_g:
            return {"ok": False, "error": f"Guardian: {errors}"}
    except ImportError:
        pass

    # Blog ID holen
    blog_id = ""
    try:
        async with session.get(
            f"https://{domain}/admin/api/{SHOPIFY_VERSION}/blogs.json",
            headers={"X-Shopify-Access-Token": token},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            if r.status == 200:
                blogs = (await r.json()).get("blogs", [])
                if blogs:
                    blog_id = str(blogs[0]["id"])
    except Exception as e:
        return {"ok": False, "error": f"Blog discovery: {e}"}

    if not blog_id:
        return {"ok": False, "error": "Kein Blog gefunden"}

    payload = {"article": {
        "title": title,
        "body_html": content.replace("\n", "<br>"),
        "tags": ", ".join(tags),
        "published": True,
    }}
    try:
        async with session.post(
            f"https://{domain}/admin/api/{SHOPIFY_VERSION}/blogs/{blog_id}/articles.json",
            headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
            json=payload,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            if r.status in (200, 201):
                art = (await r.json()).get("article", {})
                return {"ok": True, "article_id": art.get("id")}
            return {"ok": False, "error": f"HTTP {r.status}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def post_linkedin_content(session: aiohttp.ClientSession, text: str) -> dict:
    from modules.circuit_breaker import is_open, success as cb_ok, failure as cb_fail
    if is_open("linkedin"):
        return {"ok": False, "error": "circuit_open"}

    token = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
    urn   = os.getenv("LINKEDIN_PERSON_URN", "urn:li:person:YcxbqVN0ZR")
    if not token:
        return {"ok": False, "error": "LINKEDIN_ACCESS_TOKEN fehlt"}

    try:
        from modules.post_guardian import validate_post
        ok_g, errors = validate_post(text, "linkedin", "")
        if not ok_g:
            return {"ok": False, "error": f"Guardian: {errors}"}
    except ImportError:
        pass

    payload = {
        "author": urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {"com.linkedin.ugc.ShareContent": {
            "shareCommentary": {"text": text},
            "shareMediaCategory": "NONE",
        }},
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    try:
        async with session.post(
            "https://api.linkedin.com/v2/ugcPosts",
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json",
                     "X-Restli-Protocol-Version": "2.0.0"},
            json=payload,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            if r.status in (200, 201):
                cb_ok("linkedin")
                return {"ok": True}
            txt = await r.text()
            cb_fail("linkedin", txt[:100], r.status)
            return {"ok": False, "error": f"HTTP {r.status}"}
    except Exception as e:
        cb_fail("linkedin", str(e))
        return {"ok": False, "error": str(e)}


async def post_facebook_content(
    session: aiohttp.ClientSession, text: str, link: str = ""
) -> dict:
    from modules.circuit_breaker import is_open, success as cb_ok, failure as cb_fail
    if is_open("facebook"):
        return {"ok": False, "error": "circuit_open"}

    token   = os.getenv("META_ACCESS_TOKEN", os.getenv("FACEBOOK_USER_TOKEN", ""))
    page_id = os.getenv("META_PAGE_ID", os.getenv("FACEBOOK_PAGE_ID", ""))
    if not token or not page_id:
        return {"ok": False, "error": "Facebook credentials fehlen"}

    try:
        from modules.post_guardian import validate_post
        ok_g, errors = validate_post(text, "facebook", "")
        if not ok_g:
            return {"ok": False, "error": f"Guardian: {errors}"}
    except ImportError:
        pass

    params = {"message": text, "access_token": token}
    if link:
        params["link"] = link
    try:
        async with session.post(
            f"https://graph.facebook.com/v18.0/{page_id}/feed",
            params=params,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            d = await r.json(content_type=None)
            if r.status == 200 and d.get("id"):
                cb_ok("facebook")
                return {"ok": True, "post_id": d["id"]}
            err = d.get("error", {}).get("message", str(d))[:100]
            cb_fail("facebook", err, r.status)
            return {"ok": False, "error": err}
    except Exception as e:
        cb_fail("facebook", str(e))
        return {"ok": False, "error": str(e)}


async def post_reddit(
    session: aiohttp.ClientSession, subreddit: str, title: str, text: str
) -> dict:
    cid = os.getenv("REDDIT_CLIENT_ID", "")
    cs  = os.getenv("REDDIT_CLIENT_SECRET", "")
    rt  = os.getenv("REDDIT_REFRESH_TOKEN", "")
    if not all([cid, cs, rt]):
        return {"ok": False, "error": "Reddit credentials fehlen"}

    try:
        async with session.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=aiohttp.BasicAuth(cid, cs),
            data={"grant_type": "refresh_token", "refresh_token": rt},
            headers={"User-Agent": "SuperMegaBot/1.0"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            if r.status != 200:
                return {"ok": False, "error": f"Reddit auth {r.status}"}
            at = (await r.json()).get("access_token", "")
    except Exception as e:
        return {"ok": False, "error": str(e)}

    try:
        async with session.post(
            "https://oauth.reddit.com/api/submit",
            headers={"Authorization": f"Bearer {at}", "User-Agent": "SuperMegaBot/1.0"},
            data={"sr": subreddit, "kind": "self",
                  "title": title[:300], "text": text, "resubmit": True},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            d = await r.json(content_type=None)
            url = d.get("json", {}).get("data", {}).get("url", "")
            return {"ok": bool(url), "url": url} if url else \
                   {"ok": False, "error": str(d.get("json", {}).get("errors", d))[:100]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Haupt-Blast ───────────────────────────────────────────────────────────────

async def run_full_traffic_blast() -> dict:
    """Generiert Content und postet auf alle Kanäle. 3× täglich aufgerufen."""
    from modules.agent_coordinator import run as coord_run
    async with coord_run("traffic_blast", "traffic_maximizer", ttl=900, reuse_result_age=600) as ctx:
        if ctx.already_running:
            log.info("Traffic Blast läuft bereits oder zu frisch — übersprungen")
            return ctx.last_result.get("result", {"skipped": True}) if ctx.last_result else {"skipped": True}
        result = await _run_traffic_blast_inner()
        ctx.result = result
        return result


async def _run_traffic_blast_inner() -> dict:
    posts_ok = 0
    platforms_ok = []

    async with aiohttp.ClientSession(
        headers={"User-Agent": "SuperMegaBot/2.8 TrafficMaximizer"}
    ) as session:
        topics = await fetch_trending_topics(session)
        topic  = topics[0] if topics else "E-Commerce Automatisierung 2026"
        log.info("Traffic Blast — Thema: %s", topic)

        # Content für alle Plattformen generieren
        contents = {}
        for platform in ("linkedin", "facebook", "shopify_blog"):
            try:
                contents[platform] = await generate_viral_content(session, topic, platform)
            except Exception as e:
                log.warning("Content %s: %s", platform, e)
                contents[platform] = _fallback(platform, topic)

        # Alle Plattformen parallel bespielen
        tasks = [
            ("linkedin",     post_linkedin_content(session, contents["linkedin"])),
            ("facebook",     post_facebook_content(session, contents["facebook"], STRIPE_STARTER)),
            ("shopify_blog", post_shopify_blog(
                session,
                title=f"{topic} — Shopify 2026 automatisieren",
                content=contents["shopify_blog"],
                tags=["shopify automation", "e-commerce", "dach", "ki tools"],
            )),
        ]
        if os.getenv("REDDIT_CLIENT_ID"):
            hn = await generate_viral_content(session, topic, "hn")
            tasks.append(("reddit", post_reddit(session, "ecommerce",
                                                f"Show HN: {topic}", hn)))

        for platform, coro in tasks:
            try:
                r = await coro
                ok = r.get("ok", False)
                _log_post(platform, topic, contents.get(platform, ""), str(r), ok)
                if ok:
                    posts_ok += 1
                    platforms_ok.append(platform)
                    log.info("✅ %s", platform)
                else:
                    log.warning("❌ %s: %s", platform, r.get("error"))
            except Exception as e:
                log.error("Post %s: %s", platform, e)
                _log_post(platform, topic, "", str(e), False)

    reach_map = {"linkedin": 1500, "facebook": 800, "shopify_blog": 250, "reddit": 500}
    reach     = sum(reach_map.get(p, 100) for p in platforms_ok)

    if posts_ok == 0:
        _tg(f"⚠️ Traffic Blast: 0 Posts erfolgreich. Thema: {topic}")

    return {"posts_sent": posts_ok, "platforms": platforms_ok,
            "estimated_reach": reach, "topic": topic,
            "timestamp": datetime.now().isoformat()}


def _tg(msg: str) -> None:
    try:
        import urllib.request, json as _j
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat  = os.getenv("TELEGRAM_CHAT_ID", "")
        if not token or not chat:
            return
        urllib.request.urlopen(
            urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=_j.dumps({"chat_id": chat, "text": msg}).encode(),
                headers={"Content-Type": "application/json"},
            ), timeout=5
        )
    except Exception:
        pass


def get_traffic_stats() -> dict:
    conn = _db()
    day  = str(date.today())
    row  = conn.execute("SELECT * FROM daily_stats WHERE day=?", (day,)).fetchone()
    total = conn.execute("SELECT COUNT(*) FROM posts WHERE ok=1").fetchone()[0]
    conn.close()
    if row:
        return {"today_ok": row["posts_ok"], "today_fail": row["posts_fail"],
                "today_platforms": row["platforms"], "total_posts": total}
    return {"today_ok": 0, "today_fail": 0, "total_posts": total}


async def task_traffic_blast() -> str:
    try:
        r = await run_full_traffic_blast()
        return (f"TrafficBlast: {r['posts_sent']} Posts | "
                f"{r['platforms']} | Reach ~{r['estimated_reach']}")
    except Exception as e:
        return f"TrafficBlast Fehler: {e}"


# ── VOLLBESCHLEUNIGER / DAEMON ─────────────────────────────────────────────────

import subprocess as _sp, sys as _sys

_LAUNCHAGENTS = {
    "outreach":    "com.aiitec.outreach.plist",
    "inbox":       "com.aiitec.inbox.plist",
    "postmonitor": "com.aiitec.postmonitor.plist",
    "apihunt":     "com.aiitec.apihunt.plist",
}

def _daemon_status(label: str) -> bool:
    try:
        out = _sp.check_output(["launchctl", "list", label],
                                stderr=_sp.DEVNULL, text=True)
        for line in out.splitlines():
            if "PID" in line and "=" in line:
                v = line.split("=")[1].strip().strip('";')
                return v not in ("-", "0", "")
    except _sp.CalledProcessError:
        return False
    return False

def _restart_daemon(plist_name: str):
    p = Path.home() / "Library" / "LaunchAgents" / plist_name
    if p.exists():
        _sp.run(["launchctl", "unload", str(p)], capture_output=True)
        _sp.run(["launchctl", "load",   str(p)], capture_output=True)

async def _run_outreach_blast():
    """Startet sofortigen Outreach-Blast."""
    try:
        _BASE = Path(__file__).parent.parent
        _sys.path.insert(0, str(_BASE))
        from modules.aiitec_outreach_machine import (
            init_db, run_outreach, _report, health_check, discover_new_companies
        )
        await init_db()
        hc = await health_check()
        if hc.get("queue_size", 99) < 50:
            await discover_new_companies(count=80)
        stats = await run_outreach()
        await _report(stats)
        return stats
    except Exception as e:
        log.error("[OUTREACH] %s", e)
        return {}

async def _run_api_hunt():
    try:
        from modules.free_api_hunt_daemon import hunt
        return await hunt(report=True)
    except Exception as e:
        log.warning("[API-HUNT] %s", e)
        return {}

async def vollblast():
    """Vollbeschleuniger: Discovery → Outreach → Social → API-Hunt in einem Lauf."""
    log.info("=== VOLLBESCHLEUNIGER START ===")
    _tg("🚀 *AIITEC Vollbeschleuniger* gestartet — alle Kanäle auf Maximum!")

    # 1. Daemon-Check + Auto-Restart
    restarted = []
    for name, plist in _LAUNCHAGENTS.items():
        label = plist.replace(".plist", "")
        if not _daemon_status(label):
            _restart_daemon(plist)
            restarted.append(name)
    if restarted:
        log.info("↻ Neugestartet: %s", restarted)

    # 2. B2B Outreach
    log.info("[1/3] B2B Outreach-Blast ...")
    out_stats = await _run_outreach_blast()
    sent = out_stats.get("sent", 0) + out_stats.get("followup", 0)

    # 3. Social Media / Content Traffic
    log.info("[2/3] Social Traffic Blast ...")
    try:
        traffic_stats = await run_full_traffic_blast()
        posts = traffic_stats.get("posts_sent", 0)
        reach = traffic_stats.get("estimated_reach", 0)
    except Exception as e:
        log.warning("Traffic-Blast: %s", e)
        posts, reach = 0, 0

    # 4. API Hunt
    log.info("[3/3] API Hunt ...")
    api_stats = await _run_api_hunt()

    running = sum(1 for n, pl in _LAUNCHAGENTS.items()
                  if _daemon_status(pl.replace(".plist", "")))

    _tg(
        f"✅ *Vollbeschleuniger abgeschlossen!*\n\n"
        f"📧 Emails gesendet: {sent}\n"
        f"📱 Social Posts: {posts} (Reach ~{reach})\n"
        f"🔍 APIs getestet: {api_stats.get('tested', 0)}\n"
        f"🤖 Daemons aktiv: {running}/{len(_LAUNCHAGENTS)}\n"
        f"↻ Neugestartet: {', '.join(restarted) if restarted else 'keine'}"
    )
    return {"sent": sent, "posts": posts, "reach": reach,
            "apis": api_stats.get("tested", 0), "running": running}

async def daemon_coordinator():
    """
    Vollautonomer Koordinations-Daemon:
    - Alle 10 Min: Daemon-Health-Check + Auto-Restart
    - Alle 60 Min: Stunden-Report
    - Alle 6h: API-Hunt
    Outreach läuft via eigenem LaunchAgent 3× täglich.
    """
    import logging as _log
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [TRAFFIC] %(levelname)s — %(message)s",
        handlers=[logging.StreamHandler(_sys.stdout)],
    )
    log.info("Traffic-Koordinator Daemon gestartet — vollautomatisch 24/7")
    _tg(
        "🏎 *AIITEC Traffic-Koordinator* gestartet!\n\n"
        "• B2B-Outreach: 3× täglich (08:00 / 13:00 / 18:00)\n"
        "• Inbox-Monitor: alle 10 Min\n"
        "• Post-Monitor: alle 2 Min\n"
        "• API-Hunt: alle 6h\n"
        "• Daemon-AutoRestart: alle 10 Min\n"
        "_Keine manuellen Eingriffe nötig!_"
    )

    CHECK_INTERVAL = 600   # 10 Min
    REPORT_EVERY   = 6     # × CHECK = 60 Min
    API_EVERY      = 36    # × CHECK = 6h

    counter = 0
    total_sent = 0

    while True:
        await asyncio.sleep(CHECK_INTERVAL)
        counter += 1

        # Auto-Restart toter Daemons
        restarted = []
        for name, plist in _LAUNCHAGENTS.items():
            label = plist.replace(".plist", "")
            if not _daemon_status(label):
                _restart_daemon(plist)
                restarted.append(name)
        if restarted:
            log.warning("↻ Auto-Restart: %s", restarted)
            _tg(f"↻ Auto-Repair: {', '.join(restarted)} neugestartet")

        # API-Hunt alle 6h
        if counter % API_EVERY == 0:
            log.info("[API-HUNT] Scheduled Hunt ...")
            await _run_api_hunt()

        # Stunden-Report
        if counter % REPORT_EVERY == 0:
            running = sum(1 for n, pl in _LAUNCHAGENTS.items()
                          if _daemon_status(pl.replace(".plist", "")))
            stats = get_traffic_stats()
            _tg(
                f"📊 *Stunden-Report*\n"
                f"🤖 Daemons: {running}/{len(_LAUNCHAGENTS)}\n"
                f"📱 Posts heute: {stats.get('today_ok', 0)}\n"
                f"_Traffic-Koordinator läuft autonom_"
            )


if __name__ == "__main__":
    import sys
    if "--blast" in sys.argv:
        asyncio.run(vollblast())
    elif "--daemon" in sys.argv:
        asyncio.run(daemon_coordinator())
    elif "--stats" in sys.argv:
        stats = get_traffic_stats()
        print(json := __import__("json"))
        print(__import__("json").dumps(stats, indent=2))
    else:
        asyncio.run(daemon_coordinator())
