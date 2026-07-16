#!/usr/bin/env python3
"""
PUSH STRIPE LINKS NOW — Multi-Kanal Revenue Blast
=================================================
Telegram + LinkedIn + Twitter + IndexNow + Facebook (AiiteC)
Top High-Ticket Stripe Payment Links + Landings.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ── Top monétisierte Stripe-Links (money_map featured) ───────────────────────
STRIPE_TOP = [
    ("BullPower Full-Stack Empire Bundle", "€4.997/mo", "https://buy.stripe.com/fZueVf9jAguu1gc9kO4F42Ev"),
    ("BullPower Hub — 12 KI-Tools", "€2.997/mo", "https://buy.stripe.com/cNicN7cvM2DE2kg0Oi4F42DV"),
    ("BullPower Launcher", "€2.997/mo", "https://buy.stripe.com/00wcN71R87XYcYU8gK4F42DJ"),
    ("AutoIncome AI", "€2.997 einmalig", "https://buy.stripe.com/bJe5kF53k5PQcYU9kO4F42DP"),
    ("AiiteC Agency OS", "€2.497/mo", "https://buy.stripe.com/8x228t1R8guu4soeF84F42Es"),
    ("Master Command Center", "€2.497/mo", "https://buy.stripe.com/3cI28t67oa663ok0Oi4F42Ed"),
    ("Content Empire Bundle", "€1.997/mo", "https://buy.stripe.com/8x228t3Zg2DE4soaoS4F42EB"),
    ("CreatorAI Ultra", "€997/mo", "https://buy.stripe.com/cNiaEZ2Vc1zAgb6bsW4F42DY"),
    ("BullPower AI", "€997/mo", "https://buy.stripe.com/6oU14p1R8a663ok9kO4F42DS"),
    ("SteuercockPit Business", "€997/mo", "https://buy.stripe.com/cNi4gBgM23HI1gcfJc4F42Dr"),
]

# Einstiegs-Links (Conversion-freundlich)
STRIPE_ENTRY = [
    ("SuperMegaBot Starter", "€49/mo", os.getenv("STRIPE_PLINK_STARTER", "") or "https://buy.stripe.com/"),
    ("SuperMegaBot Pro", "€99/mo", os.getenv("STRIPE_PLINK_PRO", "") or ""),
]

LANDINGS = [
    "https://bullpower-hub.vercel.app/",
    "https://aiitec-all.vercel.app/",
    "https://shopify-brutal-tuning.vercel.app/",
    "https://creatorai-ultra.vercel.app/",
    "https://autoincome-ai.vercel.app/",
    "https://bullpower-ai.vercel.app/",
    "https://steuercockpit.vercel.app/",
    "https://digistore24-suite.vercel.app/",
    "https://cognitive-symphony.vercel.app/",
    "https://supermegabot-production.up.railway.app/",
]


def _load_env() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _http_json(url: str, payload: dict | None = None, headers: dict | None = None, method: str = "GET") -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    h = {"Content-Type": "application/json", "User-Agent": "SuperMegaBot-StripePush/1.0"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read()
            try:
                return {"ok": True, "status": r.status, "json": json.loads(body) if body else {}}
            except Exception:
                return {"ok": True, "status": r.status, "raw": body[:200].decode(errors="ignore")}
    except urllib.error.HTTPError as e:
        err = e.read()[:300].decode(errors="ignore")
        return {"ok": False, "status": e.code, "error": err}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def enrich_entry_links() -> None:
    """Fill Starter/Pro from .env plinks if present."""
    global STRIPE_ENTRY
    starter = (
        os.getenv("STRIPE_PLINK_STARTER")
        or os.getenv("STRIPE_LINK_STARTER")
        or ""
    )
    pro = os.getenv("STRIPE_PLINK_PRO") or os.getenv("STRIPE_LINK_PRO") or ""
    # money_map products often have lower tiers — keep high ticket as primary
    STRIPE_ENTRY = [
        ("High-Ticket Full-Stack", "€4.997/mo", STRIPE_TOP[0][2]),
        ("BullPower Hub", "€2.997/mo", STRIPE_TOP[1][2]),
        ("AiiteC Agency", "€2.497/mo", STRIPE_TOP[4][2]),
    ]
    if starter and starter.startswith("http"):
        STRIPE_ENTRY.append(("Starter SaaS", "€49/mo", starter))
    if pro and pro.startswith("http"):
        STRIPE_ENTRY.append(("Pro SaaS", "€99/mo", pro))


# ── Telegram ──────────────────────────────────────────────────────────────────

def telegram_send(text: str, disable_preview: bool = False) -> dict:
    tok = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = os.getenv("TELEGRAM_CHAT_ID", "") or os.getenv("TELEGRAM_CHANNEL_ID", "")
    if not tok or not chat:
        return {"ok": False, "error": "no telegram"}
    payload = {
        "chat_id": chat,
        "text": text[:4000],
        "parse_mode": "HTML",
        "disable_web_page_preview": disable_preview,
    }
    return _http_json(
        f"https://api.telegram.org/bot{tok}/sendMessage",
        payload,
        method="POST",
    )


def telegram_blast() -> list[dict]:
    results = []
    # Message 1: Hero + Top 5
    lines = [
        "💰 <b>HIGH-TICKET LIVE — Stripe Checkout</b>",
        "",
        "E-Commerce + KI Automation für DACH. Sofort starten:",
        "",
    ]
    for name, price, url in STRIPE_TOP[:5]:
        lines.append(f"🔥 <b>{name}</b> — {price}\n   👉 {url}")
    lines += [
        "",
        "🌐 Hub: https://bullpower-hub.vercel.app/",
        "🤖 Agency: https://aiitec-all.vercel.app/",
        "🛒 Shopify Tuning: https://shopify-brutal-tuning.vercel.app/",
    ]
    r1 = telegram_send("\n".join(lines))
    results.append({"msg": "top5", **r1})
    time.sleep(3.5)

    # Message 2: next 5
    lines2 = ["📦 <b>Weitere Live-Angebote (Stripe)</b>", ""]
    for name, price, url in STRIPE_TOP[5:10]:
        lines2.append(f"• <b>{name}</b> — {price}\n  {url}")
    lines2 += [
        "",
        "Catalog: https://supermegabot-production.up.railway.app/api/money-map",
        "SteuercockPit: https://steuercockpit.vercel.app/",
    ]
    r2 = telegram_send("\n".join(lines2))
    results.append({"msg": "next5", **r2})
    time.sleep(3.5)

    # Message 3: landings
    lines3 = [
        "🚀 <b>Landing Pages (public)</b>",
        "",
    ]
    for u in LANDINGS[:8]:
        lines3.append(f"• {u}")
    lines3.append("\n💳 Alle Checkouts: Stripe Live · sofort zahlbar")
    r3 = telegram_send("\n".join(lines3), disable_preview=True)
    results.append({"msg": "landings", **r3})
    return results


# ── IndexNow ──────────────────────────────────────────────────────────────────

def indexnow_blast() -> dict:
    key = os.getenv("INDEXNOW_KEY", "bullpower2026indexnow")
    payload = {
        "host": "bullpower-hub.vercel.app",
        "key": key,
        "urlList": LANDINGS[:10],
    }
    r = _http_json("https://api.indexnow.org/indexnow", payload, method="POST")
    # also bing
    r2 = _http_json("https://www.bing.com/indexnow", payload, method="POST")
    return {"indexnow": r, "bing": r2}


def google_indexing_ping() -> list[dict]:
    """Best-effort URL inspection ping via simple GET (no Search Console API required)."""
    out = []
    for u in LANDINGS[:6]:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "SuperMegaBot-Bot/1.0"})
            with urllib.request.urlopen(req, timeout=12) as r:
                out.append({"url": u, "status": r.status})
        except Exception as e:
            out.append({"url": u, "error": str(e)[:80]})
    return out


# ── Social posts (guarded) ────────────────────────────────────────────────────

LINKEDIN_TEXT = (
    "Shopify + KI-Automation für DACH E-Commerce 2026.\n\n"
    "High-Ticket SaaS live auf Stripe:\n"
    "• BullPower Hub — 12 KI-Tools (€2.997/mo)\n"
    "• AiiteC Agency OS — Full Stack Automation (€2.497/mo)\n"
    "• Full-Stack Empire Bundle (€4.997/mo)\n\n"
    "Landing: https://bullpower-hub.vercel.app/\n"
    "Agency: https://aiitec-all.vercel.app/\n"
    "Checkout (Stripe Live):\n"
    "https://buy.stripe.com/cNicN7cvM2DE2kg0Oi4F42DV\n\n"
    "#Shopify #Ecommerce #KI #Automation #SaaS"
)

TWITTER_TEXT = (
    "Shopify + KI Automation DACH 🚀\n"
    "BullPower Hub live — Stripe Checkout\n"
    "https://buy.stripe.com/cNicN7cvM2DE2kg0Oi4F42DV\n"
    "Hub: https://bullpower-hub.vercel.app/\n"
    "#Shopify #Ecommerce #AI"
)

FB_TEXT = (
    "🔥 E-Commerce KI-Automation für DACH — jetzt live.\n\n"
    "BullPower Hub: 12 KI-Tools für Shopify, Marketing & Revenue.\n"
    "Sofort starten (Stripe):\n"
    "https://buy.stripe.com/cNicN7cvM2DE2kg0Oi4F42DV\n\n"
    "Demo-Landing: https://bullpower-hub.vercel.app/\n"
    "AiiteC Agency: https://aiitec-all.vercel.app/\n\n"
    "#Shopify #SmartTech #Ecommerce #Automation"
)


async def social_blast() -> dict:
    out: dict = {}

    # LinkedIn via gateway
    try:
        from modules.post_gateway import safe_post
        li = await safe_post("linkedin", LINKEDIN_TEXT, source_module="push_stripe_links_now")
        out["linkedin"] = {
            "ok": li.get("ok"),
            "blocked": li.get("blocked"),
            "errors": li.get("errors", [])[:3],
            "post_id": li.get("post_id"),
        }
    except Exception as e:
        out["linkedin"] = {"ok": False, "error": str(e)[:160]}

    # Twitter
    try:
        from modules.twitter_auto_poster import post_tweet
        tw = await post_tweet(TWITTER_TEXT)
        out["twitter"] = tw if isinstance(tw, dict) else {"result": str(tw)[:120]}
    except Exception as e:
        out["twitter"] = {"ok": False, "error": str(e)[:160]}

    # Facebook Page (AiiteC)
    try:
        token = os.getenv("FACEBOOK_PAGE_TOKEN_AIITEC") or os.getenv("FB_PAGE_TOKEN", "")
        page = os.getenv("FACEBOOK_PAGE_ID", "1016738738178786")
        if token:
            # Graph API form
            import urllib.parse
            data = urllib.parse.urlencode({
                "message": FB_TEXT,
                "access_token": token,
                "link": "https://bullpower-hub.vercel.app/",
            }).encode()
            req = urllib.request.Request(
                f"https://graph.facebook.com/v21.0/{page}/feed",
                data=data,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                body = json.loads(r.read())
                out["facebook"] = {"ok": True, "id": body.get("id")}
        else:
            out["facebook"] = {"ok": False, "error": "no token"}
    except Exception as e:
        out["facebook"] = {"ok": False, "error": str(e)[:200]}

    return out


def verify_stripe_links() -> list[dict]:
    """HEAD/GET check that buy.stripe.com links respond."""
    out = []
    for name, price, url in STRIPE_TOP[:8]:
        try:
            req = urllib.request.Request(url, method="GET", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                out.append({"name": name, "price": price, "status": r.status, "url": url})
        except urllib.error.HTTPError as e:
            # Stripe often 200 or redirect
            out.append({"name": name, "price": price, "status": e.code, "url": url})
        except Exception as e:
            out.append({"name": name, "error": str(e)[:80], "url": url})
    return out


async def main() -> int:
    _load_env()
    enrich_entry_links()
    report: dict = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    print("=== 1) Verify Stripe links ===")
    report["stripe_verify"] = verify_stripe_links()
    for x in report["stripe_verify"]:
        print(" ", x.get("status", x.get("error")), x.get("name"), x.get("price"))

    print("=== 2) Telegram blast ===")
    report["telegram"] = telegram_blast()
    for x in report["telegram"]:
        print(" ", x.get("msg"), "ok=" + str(x.get("ok")), x.get("status") or x.get("error", "")[:60])

    print("=== 3) IndexNow ===")
    report["indexnow"] = indexnow_blast()
    print(" ", report["indexnow"])

    print("=== 4) Landing warm ===")
    report["landings"] = google_indexing_ping()
    for x in report["landings"]:
        print(" ", x)

    print("=== 5) Social (LI/TW/FB) ===")
    report["social"] = await social_blast()
    print(" ", json.dumps(report["social"], ensure_ascii=False)[:500])

    # Persist report
    out_path = ROOT / "data" / "stripe_push_last.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("=== DONE ===", out_path)
    # success if telegram or any social ok
    tg_ok = any(x.get("ok") for x in report.get("telegram", []))
    soc = report.get("social") or {}
    soc_ok = any(
        (isinstance(v, dict) and (v.get("ok") or v.get("id") or v.get("post_id")))
        for v in soc.values()
    )
    return 0 if (tg_ok or soc_ok) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
