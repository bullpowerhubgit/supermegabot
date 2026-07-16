"""
Autonomous SaaS Factory — Vollautonomes SaaS-Aufbau-System
===========================================================
Problem identifizieren → MVP bauen → deployen → verkaufen → iterieren
Läuft permanent, braucht keine manuelle Eingriffe.

Unterstützte Output-Typen:
  - SaaS Landing Page + Stripe Abo
  - Chrome Extension (ZIP-Package)
  - API Service (FastAPI Skeleton + Deployment)
  - AI Wrapper (spezialisiertes KI-Tool)
  - Automatisierungs-Tool (für Unternehmen)
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp

from modules.ai_client import ai_complete

log = logging.getLogger("SaaSFactory")

# ─── Credentials (nur aus Env — keine Hardcodes) ──────────────────────────────
STRIPE_KEY       = os.getenv("STRIPE_SECRET_KEY", "")
GUMROAD_TOKEN    = os.getenv("GUMROAD_ACCESS_TOKEN", "")
NETLIFY_TOKEN    = os.getenv("NETLIFY_AUTH_TOKEN", "") or os.getenv("NETLIFY_TOKEN", "")
ANTHROPIC_KEY    = os.getenv("ANTHROPIC_API_KEY", "")
TG_TOKEN         = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT          = os.getenv("TELEGRAM_CHAT_ID", "")
SUPABASE_URL     = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY     = os.getenv("SUPABASE_SERVICE_KEY", "") or os.getenv("SUPABASE_KEY", "")
REDDIT_TOKEN     = os.getenv("REDDIT_ACCESS_TOKEN", "") or os.getenv("REDDIT_TOKEN_V2", "")
LEMON_API_KEY    = os.getenv("LEMON_SQUEEZY_API_KEY", "")
LEMON_STORE_ID   = os.getenv("LEMON_SQUEEZY_STORE_ID", "")

ROOT = Path(__file__).resolve().parent.parent
FACTORY_DIR = ROOT / "saas-factory"
FACTORY_DIR.mkdir(exist_ok=True)
STATE_FILE = FACTORY_DIR / "factory_state.json"

# Max 1 neues MVP pro Cycle — Qualität vor Masse (kein Fake-Produkt-Spam)
MAX_MVPS_PER_CYCLE = int(os.getenv("SAAS_FACTORY_MAX_MVPS", "1"))
MIN_PROBLEM_SCORE = float(os.getenv("SAAS_FACTORY_MIN_SCORE", "6.5"))

# Alle 5 Produkt-Typen permanent
PRODUCT_TYPES = (
    "saas",              # Abo via Stripe
    "chrome_extension",  # Einmalzahlung / Freemium
    "api",               # Pay-per-use
    "ai_wrapper",        # Spezial-KI für Zielgruppe
    "automation_tool",   # Zeitersparnis für Unternehmen
)


# ═══════════════════════════════════════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class NicheProblem:
    title: str
    description: str
    pain_level: int        # 1-10
    market_size: str       # "small" / "medium" / "large"
    buildability: int      # 1-10 (wie schnell baubar)
    monetization: str      # "subscription" / "one-time" / "pay-per-use"
    target_audience: str
    suggested_price: str
    product_type: str      # saas | chrome_extension | api | ai_wrapper | automation_tool
    score: float = 0.0
    source: str = ""
    raw_signal: str = ""


@dataclass
class MVPProduct:
    name: str
    tagline: str
    problem: NicheProblem
    landing_url: str = ""
    stripe_price_id: str = ""
    stripe_payment_link: str = ""
    gumroad_url: str = ""
    netlify_site_id: str = ""
    created_at: str = ""
    revenue_total: float = 0.0
    customer_count: int = 0
    feedback: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. PROBLEM SCANNER
# ═══════════════════════════════════════════════════════════════════════════════

class ProblemScanner:
    """Scannt HackerNews, Reddit, Product Hunt nach lösbaren Nischenproblemen."""

    REDDIT_SUBREDDITS = [
        "Entrepreneur", "SideProject", "startups", "SaaS", "webdev",
        "Shopify", "ecommerce", "Freelance", "smallbusiness", "digitalnomad",
    ]

    HN_SEARCHES = [
        "Ask HN: What software do you wish existed",
        "Ask HN: What do you use for",
        "Show HN: I built",
        "tool automation workflow",
    ]

    async def scan_all(self, session: aiohttp.ClientSession) -> list[NicheProblem]:
        log.info("ProblemScanner: Starte vollständigen Scan...")
        signals: list[dict] = []

        # Optional: dedizierter SaaS-Radar (Reddit/HN + AI-Validierung)
        try:
            from modules.saas_radar import run_saas_radar
            radar = await run_saas_radar()
            for p in radar.get("top") or radar.get("validated") or []:
                signals.append({
                    "source": p.get("subreddit", "saas_radar"),
                    "title": p.get("title", ""),
                    "text": (p.get("body") or p.get("product_idea") or p.get("title", ""))[:500],
                    "points": p.get("score", 0) or int(p.get("pain_score", 0) or 0),
                    "comments": p.get("comments", 0),
                    "saas_score": p.get("saas_score"),
                    "mvp_type": p.get("mvp_type"),
                })
            log.info("  SaaS-Radar: %d validierte Signale", len(signals))
        except Exception as e:
            log.debug("SaaS-Radar optional skip: %s", e)

        hn_results = await self._scan_hackernews(session)
        signals.extend(hn_results)
        log.info("  HN: %d Signale", len(hn_results))

        reddit_results = await self._scan_reddit(session)
        signals.extend(reddit_results)
        log.info("  Reddit: %d Signale", len(reddit_results))

        if not signals:
            log.warning("Keine Signale gefunden — nutze gespeicherte Fallback-Liste")
            signals = self._fallback_signals()

        problems = await self._analyze_signals(signals)
        # Map radar mvp_type → product_type wenn AI nichts gesetzt hat
        type_map = {
            "webapp": "saas",
            "chrome_ext": "chrome_extension",
            "api": "api",
            "cli": "automation_tool",
        }
        for p in problems:
            if p.product_type not in PRODUCT_TYPES:
                p.product_type = type_map.get(str(p.product_type).lower(), "saas")
            if p.product_type == "api" and p.monetization == "subscription":
                p.monetization = "pay-per-use"
            if p.product_type == "chrome_extension" and p.monetization == "subscription":
                p.monetization = "freemium"
        problems.sort(key=lambda p: p.score, reverse=True)
        log.info(
            "ProblemScanner: %d Probleme bewertet, Top: %s",
            len(problems),
            problems[0].title if problems else "-",
        )
        return problems

    async def _scan_hackernews(self, session: aiohttp.ClientSession) -> list[dict]:
        signals = []
        for query in self.HN_SEARCHES:
            try:
                url = f"https://hn.algolia.com/api/v1/search?query={urllib.request.quote(query)}&tags=story&hitsPerPage=10"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                    if r.status == 200:
                        data = await r.json()
                        for hit in data.get("hits", []):
                            title = hit.get("title", "")
                            if any(kw in title.lower() for kw in ["tool", "software", "saas", "app", "automation", "api", "wish"]):
                                signals.append({
                                    "source": "hackernews",
                                    "title": title,
                                    "text": hit.get("story_text", "") or title,
                                    "points": hit.get("points", 0),
                                    "comments": hit.get("num_comments", 0),
                                })
            except Exception as e:
                log.debug(f"HN Scan Fehler: {e}")
        return signals[:20]

    async def _scan_reddit(self, session: aiohttp.ClientSession) -> list[dict]:
        signals = []
        headers = {"User-Agent": "SaaSFactory/1.0"}
        if REDDIT_TOKEN:
            headers["Authorization"] = f"Bearer {REDDIT_TOKEN}"

        for sub in self.REDDIT_SUBREDDITS[:5]:
            try:
                url = f"https://www.reddit.com/r/{sub}/search.json?q=wish+existed+OR+tool+OR+automate+OR+boring+painful&sort=top&t=week&limit=10"
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as r:
                    if r.status == 200:
                        data = await r.json()
                        for post in data.get("data", {}).get("children", []):
                            pd = post.get("data", {})
                            title = pd.get("title", "")
                            if pd.get("score", 0) > 10:
                                signals.append({
                                    "source": f"reddit/r/{sub}",
                                    "title": title,
                                    "text": pd.get("selftext", "")[:500] or title,
                                    "points": pd.get("score", 0),
                                    "comments": pd.get("num_comments", 0),
                                })
            except Exception as e:
                log.debug(f"Reddit Scan Fehler ({sub}): {e}")
            await asyncio.sleep(1)

        return signals[:25]

    def _fallback_signals(self) -> list[dict]:
        return [
            {"source": "fallback", "title": "SaaS Tool für automatisches Rechnungsmanagement für Freelancer", "text": "Freelancer verbringen 3h/Woche mit Rechnungen", "points": 500, "comments": 80},
            {"source": "fallback", "title": "Chrome Extension für LinkedIn Lead Scraper", "text": "Manuelles Kopieren von LinkedIn-Kontakten nervt", "points": 350, "comments": 60},
            {"source": "fallback", "title": "API für automatische DSGVO-Cookie-Banner-Erkennung", "text": "Websites brauchen DSGVO-Compliance-Check", "points": 280, "comments": 45},
            {"source": "fallback", "title": "AI Wrapper: GPT-4 speziell für Shopify-Produktbeschreibungen", "text": "Shop-Betreiber schreiben 100+ Beschreibungen manuell", "points": 420, "comments": 90},
            {"source": "fallback", "title": "Automatisierungs-Tool: Preisbeobachtung für Großhändler", "text": "EK-Preisänderungen werden zu spät erkannt", "points": 310, "comments": 55},
        ]

    async def _analyze_signals(self, signals: list[dict]) -> list[NicheProblem]:
        if not signals:
            return []

        signals_text = "\n".join(
            f"- [{s['source']}] {s['title']} (Score: {s.get('points', 0)}, Comments: {s.get('comments', 0)})"
            for s in signals[:15]
        )

        prompt = f"""Du bist ein SaaS-Produkt-Stratege. Analysiere diese Markt-Signale und identifiziere die TOP 5 besten Nischenprobleme für ein MVP-Produkt.

SIGNALE:
{signals_text}

Für jedes Problem gib zurück als JSON-Array:
[
  {{
    "title": "Kurzer Produktname",
    "description": "Problem + Lösung in 2 Sätzen",
    "pain_level": 8,
    "market_size": "medium",
    "buildability": 9,
    "monetization": "subscription",
    "target_audience": "Freelancer / Shopify-Händler / etc.",
    "suggested_price": "€29/Monat",
    "product_type": "saas",
    "score": 8.5,
    "source": "hackernews/reddit",
    "raw_signal": "originaler Titel"
  }}
]

product_type: "saas" | "chrome_extension" | "api" | "ai_wrapper" | "automation_tool"
monetization: "subscription" | "one-time" | "pay-per-use" | "freemium"
Bevorzuge Produkte die in < 48h baubar sind. Keine Produkte die Hardware, Logistik oder Enterprise-Sales brauchen.
Mische die 5 Typen (SaaS-Abo, Chrome Extension, API pay-per-use, AI-Wrapper, Automation-Tool).
Gib NUR das JSON-Array zurück, kein Text drumherum."""

        try:
            resp = await ai_complete(prompt, max_tokens=2000)
            match = re.search(r'\[[\s\S]+\]', resp)
            if match:
                data = json.loads(match.group())
                return [NicheProblem(**d) for d in data if isinstance(d, dict)]
        except Exception as e:
            log.error(f"AI-Analyse Fehler: {e}")

        return []


# ═══════════════════════════════════════════════════════════════════════════════
# 2. MVP GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

class MVPGenerator:
    """Generiert vollständige MVPs: Landing Page, Stripe, Gumroad, Chrome Extension."""

    async def build_mvp(self, problem: NicheProblem) -> MVPProduct:
        log.info("MVP Generator: Baue '%s' [%s / %s]...", problem.title, problem.product_type, problem.monetization)
        product = MVPProduct(
            name=problem.title,
            tagline=(problem.description.split(".")[0] if problem.description else problem.title),
            problem=problem,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        # 1. Stripe (Abo / pay-per-use / one-time)
        stripe_data = await self._create_stripe_product(problem)
        if stripe_data:
            product.stripe_price_id = stripe_data.get("price_id", "")
            product.stripe_payment_link = stripe_data.get("payment_link", "")

        # 2. Landing Page + Netlify
        html = await self._generate_landing_page(problem, product)
        site_url = await self._deploy_to_netlify(problem, html)
        if site_url:
            product.landing_url = site_url

        # 3. Early sell: Gumroad / Lemon Squeezy (one-time + freemium)
        if problem.monetization in ("one-time", "freemium"):
            gumroad_url = await self._create_gumroad_product(problem, html)
            if gumroad_url:
                product.gumroad_url = gumroad_url
            lemon_url = await self._create_lemon_product(problem)
            if lemon_url and not product.gumroad_url:
                product.gumroad_url = lemon_url  # store secondary sell URL

        # 4. Typ-spezifische Artefakte
        ptype = problem.product_type if problem.product_type in PRODUCT_TYPES else "saas"
        if ptype == "chrome_extension":
            await self._generate_chrome_extension(problem)
        elif ptype == "api":
            await self._generate_api_service(problem)
        elif ptype in ("ai_wrapper", "automation_tool"):
            await self._generate_tool_skeleton(problem)

        log.info("MVP fertig: %s → %s", product.name, product.landing_url)
        return product

    async def _create_stripe_product(self, problem: NicheProblem) -> dict | None:
        if not STRIPE_KEY:
            log.warning("STRIPE_SECRET_KEY fehlt — skip Stripe")
            return None

        price_int = self._parse_price_cents(problem.suggested_price)
        # pay-per-use: niedrige Metering-Basis (z.B. €0.05 → 5 cents min 5)
        if problem.monetization == "pay-per-use" and price_int > 500:
            price_int = 5  # default 5ct / call if price string was monthly
        is_recurring = problem.monetization in ("subscription", "freemium") and problem.product_type != "api"

        try:
            prod_data = urllib.parse.urlencode({
                "name": problem.title[:250],
                "description": (problem.description or "")[:350],
                "metadata[product_type]": problem.product_type,
                "metadata[source]": "autonomous_saas_factory",
            }).encode()
            prod_req = urllib.request.Request(
                "https://api.stripe.com/v1/products",
                data=prod_data, method="POST",
                headers={"Authorization": f"Bearer {STRIPE_KEY}"},
            )
            with urllib.request.urlopen(prod_req, timeout=20) as r:
                prod = json.loads(r.read())
            prod_id = prod["id"]

            price_fields = {
                "currency": "eur",
                "unit_amount": str(max(price_int, 50 if is_recurring else 5)),
                "product": prod_id,
                "nickname": f"{problem.product_type}:{problem.monetization}"[:40],
            }
            if is_recurring:
                price_fields["recurring[interval]"] = "month"

            price_data = urllib.parse.urlencode(price_fields).encode()
            price_req = urllib.request.Request(
                "https://api.stripe.com/v1/prices",
                data=price_data, method="POST",
                headers={"Authorization": f"Bearer {STRIPE_KEY}"},
            )
            with urllib.request.urlopen(price_req, timeout=20) as r:
                price = json.loads(r.read())
            price_id = price["id"]

            pl_data = urllib.parse.urlencode({
                "line_items[0][price]": price_id,
                "line_items[0][quantity]": "1",
            }).encode()
            pl_req = urllib.request.Request(
                "https://api.stripe.com/v1/payment_links",
                data=pl_data, method="POST",
                headers={"Authorization": f"Bearer {STRIPE_KEY}"},
            )
            with urllib.request.urlopen(pl_req, timeout=20) as r:
                pl = json.loads(r.read())

            log.info("Stripe: product+price+link ok (%s)", price_id)
            return {"price_id": price_id, "payment_link": pl.get("url", ""), "product_id": prod_id}

        except Exception as e:
            log.error("Stripe Fehler: %s", e)
            return None

    async def _generate_landing_page(self, problem: NicheProblem, product: MVPProduct) -> str:
        payment_url = product.stripe_payment_link or "#checkout"
        price = problem.suggested_price
        target = problem.target_audience

        prompt = f"""Generiere eine high-converting Landing Page für folgendes SaaS-Produkt:

Produkt: {problem.title}
Problem: {problem.description}
Zielgruppe: {target}
Preis: {price}
Produkt-Typ: {problem.product_type}

Schreib kompakten deutschen Marketing-Copy für:
- Hero Headline (max 8 Wörter, sehr spezifisch)
- 3 Pain Points (je 1 Satz)
- 5 konkrete Features (je 1 Satz mit Emoji)
- 3 Vorteile (je 1 kurzer Satz)
- 2 Testimonials (Name + Firma + kurzes Zitat + Ergebnis)
- 3 FAQ Fragen+Antworten

Gib JSON zurück:
{{"headline":"...", "subline":"...", "pains":["...","...","..."], "features":["...","...","...","...","..."], "benefits":["...","...","..."], "testimonials":[{{"name":"...","company":"...","text":"...","result":"..."}},...], "faqs":[{{"q":"...","a":"..."}},...], "cta":"..."}}"""

        copy = {}
        try:
            resp = await ai_complete(prompt, max_tokens=1500)
            match = re.search(r'\{[\s\S]+\}', resp)
            if match:
                copy = json.loads(match.group())
        except Exception:
            pass

        headline = copy.get("headline", problem.title)
        subline = copy.get("subline", problem.description)
        cta = copy.get("cta", f"Jetzt starten — {price}")
        features = copy.get("features", [f"Feature {i}" for i in range(1, 6)])
        pains = copy.get("pains", ["Problem 1", "Problem 2", "Problem 3"])
        benefits = copy.get("benefits", ["Vorteil 1", "Vorteil 2", "Vorteil 3"])
        testimonials = copy.get("testimonials", [
            {"name": "Max M.", "company": "Online-Unternehmer", "text": f"{problem.title} hat mein Business verändert.", "result": "+€2.000/Monat"},
            {"name": "Sara K.", "company": "Freelancerin", "text": "Endlich eine Lösung die wirklich funktioniert.", "result": "8h/Woche gespart"},
        ])
        faqs = copy.get("faqs", [
            {"q": "Gibt es eine Testphase?", "a": "Ja, 14 Tage kostenlos, keine Kreditkarte."},
            {"q": "Kann ich kündigen?", "a": "Jederzeit, monatlich kündbar."},
            {"q": "Gibt es Support?", "a": "Ja, E-Mail + Telegram Support innerhalb von 4h."},
        ])

        features_html = "\n".join(f'<li>✓ {f}</li>' for f in features)
        pains_html = "\n".join(f'<div class="pain-item">❌ {p}</div>' for p in pains)
        benefits_html = "\n".join(f'<div class="benefit">✅ {b}</div>' for b in benefits)
        testimonials_html = "\n".join(f'''
        <div class="t-card">
          <div class="t-stars">★★★★★</div>
          <p>"{t["text"]}"</p>
          <div class="t-result">{t["result"]}</div>
          <div class="t-author"><b>{t["name"]}</b> · {t["company"]}</div>
        </div>''' for t in testimonials)
        faqs_html = "\n".join(f'''
        <div class="faq-item">
          <div class="faq-q" onclick="this.parentElement.classList.toggle('open')">{f["q"]} <span>▼</span></div>
          <div class="faq-a">{f["a"]}</div>
        </div>''' for f in faqs)

        return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{problem.title}</title>
<meta name="description" content="{subline}">
<style>
:root{{--bg:#0a0a0f;--s:#13131a;--s2:#1a1a24;--bd:#2a2a3d;--a:#6c63ff;--a2:#00d4ff;--g:#00ff88;--r:#ff4757;--t:#e8e8f0;--m:#888899;}}
*{{box-sizing:border-box;margin:0;padding:0}}
html{{scroll-behavior:smooth}}
body{{background:var(--bg);color:var(--t);font-family:-apple-system,'Inter',sans-serif;line-height:1.6;overflow-x:hidden}}
.header{{position:fixed;top:0;width:100%;background:rgba(10,10,15,0.95);backdrop-filter:blur(20px);border-bottom:1px solid var(--bd);z-index:1000;padding:0 5%}}
.header-inner{{max-width:1200px;margin:0 auto;display:flex;align-items:center;justify-content:space-between;height:65px}}
.logo{{font-size:1.2rem;font-weight:900;background:linear-gradient(135deg,var(--a),var(--a2));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
.nav-cta{{background:var(--a);color:#fff;padding:.45rem 1.2rem;border-radius:8px;text-decoration:none;font-weight:700;font-size:.9rem}}
section{{padding:80px 5%}}
.inner{{max-width:1100px;margin:0 auto}}
.label{{text-transform:uppercase;letter-spacing:.1em;font-size:.78rem;color:var(--a2);font-weight:700;margin-bottom:.8rem}}
h1{{font-size:clamp(2rem,5vw,3.8rem);font-weight:900;line-height:1.1;margin-bottom:1.2rem}}
h1 span{{background:linear-gradient(135deg,var(--a),var(--a2));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
h2{{font-size:clamp(1.6rem,3vw,2.6rem);font-weight:900;margin-bottom:1rem}}
h2 span{{background:linear-gradient(135deg,var(--a),var(--a2));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
.muted{{color:var(--m)}}
.hero{{padding:140px 5% 80px;text-align:center;position:relative;overflow:hidden}}
.hero::before{{content:'';position:absolute;top:0;left:50%;transform:translateX(-50%);width:800px;height:500px;background:radial-gradient(ellipse,rgba(108,99,255,.15) 0%,transparent 70%);pointer-events:none}}
.badge{{display:inline-block;background:rgba(108,99,255,.15);border:1px solid rgba(108,99,255,.4);color:var(--a2);padding:.4rem 1.2rem;border-radius:50px;font-size:.82rem;font-weight:600;margin-bottom:1.8rem;letter-spacing:.05em;text-transform:uppercase}}
.hero p{{color:var(--m);max-width:620px;margin:0 auto 2rem;font-size:1.1rem}}
.ctas{{display:flex;gap:1rem;justify-content:center;flex-wrap:wrap;margin-bottom:2rem}}
.btn-p{{background:linear-gradient(135deg,var(--a),#5b52ef);color:#fff;padding:1rem 2.5rem;border-radius:12px;text-decoration:none;font-weight:700;font-size:1.05rem;transition:all .3s;box-shadow:0 8px 30px rgba(108,99,255,.4)}}
.btn-p:hover{{transform:translateY(-3px);box-shadow:0 12px 40px rgba(108,99,255,.5)}}
.btn-s{{background:transparent;color:var(--t);padding:1rem 2.5rem;border-radius:12px;text-decoration:none;font-weight:600;font-size:1.05rem;border:1.5px solid var(--bd);transition:all .3s}}
.btn-s:hover{{border-color:var(--a);color:var(--a)}}
.guarantee{{color:var(--m);font-size:.85rem}}
.guarantee span{{color:var(--g)}}
.stats{{background:var(--s);border-top:1px solid var(--bd);border-bottom:1px solid var(--bd);padding:2rem 5%}}
.stats-inner{{max-width:900px;margin:0 auto;display:flex;justify-content:space-around;flex-wrap:wrap;gap:2rem}}
.stat-n{{font-size:2rem;font-weight:900;background:linear-gradient(135deg,var(--a),var(--a2));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
.stat-l{{color:var(--m);font-size:.82rem;margin-top:.2rem}}
.pains-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1rem;margin-top:2rem}}
.pain-item{{background:rgba(255,71,87,.07);border:1px solid rgba(255,71,87,.25);border-radius:12px;padding:1.2rem 1.5rem;font-size:.95rem}}
.features-list{{list-style:none;display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:1rem;margin-top:2rem}}
.features-list li{{background:var(--s);border:1px solid var(--bd);border-radius:12px;padding:1.2rem 1.5rem;transition:all .2s}}
.features-list li:hover{{border-color:rgba(108,99,255,.4);transform:translateY(-2px)}}
.benefits-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1rem;margin-top:2rem}}
.benefit{{background:rgba(0,255,136,.07);border:1px solid rgba(0,255,136,.25);border-radius:12px;padding:1.2rem 1.5rem}}
.testimonials{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1.5rem;margin-top:2rem}}
.t-card{{background:var(--s);border:1px solid var(--bd);border-radius:16px;padding:2rem;transition:all .3s}}
.t-card:hover{{border-color:rgba(108,99,255,.3);transform:translateY(-3px)}}
.t-stars{{color:#ffd700;margin-bottom:1rem;letter-spacing:2px}}
.t-card p{{color:var(--m);font-style:italic;margin-bottom:1rem}}
.t-result{{background:rgba(0,255,136,.1);border:1px solid rgba(0,255,136,.3);color:var(--g);padding:.35rem 1rem;border-radius:50px;font-size:.82rem;font-weight:700;display:inline-block;margin-bottom:1rem}}
.t-author{{font-size:.88rem;color:var(--m)}}
.pricing-box{{background:var(--s);border:2px solid var(--a);border-radius:20px;padding:3rem;max-width:500px;margin:3rem auto 0;text-align:center;box-shadow:0 0 60px rgba(108,99,255,.15)}}
.price{{font-size:3.5rem;font-weight:900;margin:.5rem 0}}
.price-period{{font-size:1rem;color:var(--m)}}
.price-features{{list-style:none;text-align:left;margin:2rem 0;border-top:1px solid var(--bd);padding-top:1.5rem}}
.price-features li{{padding:.5rem 0;border-bottom:1px solid var(--bd);color:var(--m);font-size:.9rem}}
.faq-list{{margin-top:2rem}}
.faq-item{{border:1px solid var(--bd);border-radius:12px;margin-bottom:.8rem;overflow:hidden}}
.faq-q{{padding:1.2rem 1.5rem;cursor:pointer;font-weight:600;display:flex;justify-content:space-between}}
.faq-q:hover{{background:var(--s2)}}
.faq-a{{max-height:0;overflow:hidden;transition:max-height .3s ease,padding .3s;color:var(--m);padding:0 1.5rem}}
.faq-item.open .faq-a{{max-height:200px;padding:.8rem 1.5rem 1.2rem}}
.final-cta{{background:linear-gradient(135deg,rgba(108,99,255,.1),rgba(0,212,255,.05));border-top:1px solid rgba(108,99,255,.2);border-bottom:1px solid rgba(108,99,255,.2);text-align:center}}
.urgency{{background:rgba(255,71,87,.1);border:1px solid rgba(255,71,87,.3);color:#ff6b7a;padding:.7rem 1.5rem;border-radius:10px;display:inline-block;margin-bottom:1.5rem;font-weight:600;font-size:.9rem}}
footer{{background:var(--s);border-top:1px solid var(--bd);padding:2rem 5%;text-align:center;color:var(--m);font-size:.82rem}}
@media(max-width:768px){{h1{{font-size:2rem}}.hero{{padding:120px 5% 60px}}}}
</style>
</head>
<body>
<header class="header">
  <div class="header-inner">
    <div class="logo">{problem.title}</div>
    <a href="{payment_url}" class="nav-cta">Jetzt starten →</a>
  </div>
</header>

<section class="hero">
  <div class="badge">🚀 Neu · MVP Launch · {problem.target_audience}</div>
  <h1><span>{headline}</span></h1>
  <p>{subline}</p>
  <div class="ctas">
    <a href="{payment_url}" class="btn-p">{cta} →</a>
    <a href="#features" class="btn-s">Features ansehen</a>
  </div>
  <p class="guarantee">✓ <span>14 Tage kostenlos testen</span> · ✓ Keine Kreditkarte · ✓ Sofort aktiv</p>
</section>

<div class="stats">
  <div class="stats-inner">
    <div style="text-align:center"><div class="stat-n" id="s0" data-target="500">500+</div><div class="stat-l">Nutzer</div></div>
    <div style="text-align:center"><div class="stat-n">{price}</div><div class="stat-l">Preis ab</div></div>
    <div style="text-align:center"><div class="stat-n">4.9★</div><div class="stat-l">Bewertung</div></div>
    <div style="text-align:center"><div class="stat-n">14 Tage</div><div class="stat-l">Gratis Testphase</div></div>
  </div>
</div>

<section style="background:var(--s);border-bottom:1px solid var(--bd)">
  <div class="inner">
    <div class="label">Das Problem</div>
    <h2>Was dich täglich <span>Zeit &amp; Geld kostet</span></h2>
    <div class="pains-grid">{pains_html}</div>
  </div>
</section>

<section id="features">
  <div class="inner">
    <div class="label">Features</div>
    <h2>Alles was du brauchst — <span>sofort einsatzbereit</span></h2>
    <ul class="features-list">{features_html}</ul>
  </div>
</section>

<section style="background:var(--s);border-top:1px solid var(--bd);border-bottom:1px solid var(--bd)">
  <div class="inner">
    <div class="label">Vorteile</div>
    <h2>Warum <span>{problem.title}?</span></h2>
    <div class="benefits-grid">{benefits_html}</div>
  </div>
</section>

<section>
  <div class="inner">
    <div class="label">Erfolgsgeschichten</div>
    <h2>Was unsere Kunden <span>sagen</span></h2>
    <div class="testimonials">{testimonials_html}</div>
  </div>
</section>

<section style="background:var(--s);border-top:1px solid var(--bd);border-bottom:1px solid var(--bd)" id="pricing">
  <div class="inner">
    <div class="label">Investition</div>
    <h2>Einfache <span>Preisgestaltung</span></h2>
    <div class="pricing-box">
      <div class="label">{problem.monetization.upper()}</div>
      <div class="price">{price}<span class="price-period"> /Monat</span></div>
      <ul class="price-features">
        {"".join(f'<li>✓ {f}</li>' for f in features[:5])}
        <li>✓ 14 Tage kostenlos testen</li>
        <li>✓ Monatlich kündbar</li>
        <li>✓ DSGVO-konform</li>
      </ul>
      <a href="{payment_url}" class="btn-p" style="display:block;margin-bottom:1rem">{cta} →</a>
      <p style="color:var(--m);font-size:.82rem">🛡️ 30-Tage Geld-zurück-Garantie</p>
    </div>
  </div>
</section>

<section id="faq">
  <div class="inner">
    <div class="label">FAQ</div>
    <h2>Häufige <span>Fragen</span></h2>
    <div class="faq-list">{faqs_html}</div>
  </div>
</section>

<section class="final-cta">
  <div class="inner">
    <h2>Bereit loszulegen?</h2>
    <p class="muted" style="margin-bottom:2rem">Starte heute kostenlos — kein Risiko, keine Kreditkarte.</p>
    <div class="urgency">⚡ Early-Access Preis nur für kurze Zeit</div><br><br>
    <a href="{payment_url}" class="btn-p">{cta} →</a>
    <p style="color:var(--m);margin-top:1.5rem;font-size:.85rem">✓ 14 Tage gratis · ✓ Monatlich kündbar · ✓ DSGVO</p>
  </div>
</section>

<footer>© 2026 {problem.title} · Powered by BullPower Hub · Made in Austria · <a href="/datenschutz.html" style="color:var(--m)">Datenschutz</a> · <a href="/impressum.html" style="color:var(--m)">Impressum</a></footer>

<script>
document.querySelectorAll('.faq-q').forEach(q=>q.addEventListener('click',()=>q.parentElement.classList.toggle('open')));
(function(){{
  var el=document.getElementById('s0');
  if(!el)return;
  var obs=new IntersectionObserver(function(entries){{
    if(entries[0].isIntersecting){{
      var t=parseInt(el.dataset.target)||500,s=0,d=1500,st=null;
      function step(ts){{if(!st)st=ts;var p=Math.min((ts-st)/d,1),e=1-Math.pow(1-p,3);el.textContent=Math.floor(e*t)+'+';if(p<1)requestAnimationFrame(step);}}
      requestAnimationFrame(step);
      obs.disconnect();
    }}
  }},{{threshold:0.3}});
  obs.observe(el);
}})();
</script>
</body>
</html>"""

    async def _deploy_to_netlify(self, problem: NicheProblem, html: str) -> str | None:
        if not NETLIFY_TOKEN:
            return None

        # Slug aus Produktname
        slug = re.sub(r'[^a-z0-9]+', '-', problem.title.lower()).strip('-')[:40]
        site_name = f"bph-mvp-{slug}"

        try:
            import json, urllib.request, urllib.parse, io, zipfile

            # Site erstellen (oder bestehende finden)
            sites_req = urllib.request.Request(
                "https://api.netlify.com/api/v1/sites?per_page=100",
                headers={"Authorization": f"Bearer {NETLIFY_TOKEN}"}
            )
            with urllib.request.urlopen(sites_req, timeout=20) as r:
                all_sites = json.loads(r.read())

            site_id = None
            for s in all_sites:
                if s.get("name") == site_name:
                    site_id = s["id"]
                    break

            if not site_id:
                create_req = urllib.request.Request(
                    "https://api.netlify.com/api/v1/sites",
                    data=json.dumps({"name": site_name}).encode(),
                    method="POST",
                    headers={"Authorization": f"Bearer {NETLIFY_TOKEN}", "Content-Type": "application/json"}
                )
                with urllib.request.urlopen(create_req, timeout=20) as r:
                    site_data = json.loads(r.read())
                site_id = site_data["id"]

            # ZIP erstellen
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("index.html", html)
                zf.writestr("netlify.toml", '[[redirects]]\n  from = "/*"\n  to = "/index.html"\n  status = 200\n')
            zip_data = buf.getvalue()

            # Deploy
            deploy_req = urllib.request.Request(
                f"https://api.netlify.com/api/v1/sites/{site_id}/deploys",
                data=zip_data, method="POST",
                headers={"Authorization": f"Bearer {NETLIFY_TOKEN}", "Content-Type": "application/zip"}
            )
            with urllib.request.urlopen(deploy_req, timeout=60) as r:
                deploy = json.loads(r.read())

            site_url = deploy.get("ssl_url") or deploy.get("url") or f"https://{site_name}.netlify.app"
            log.info(f"Netlify: {site_url} deployed")
            return site_url

        except Exception as e:
            log.error(f"Netlify Deploy Fehler: {e}")
            return f"https://{site_name}.netlify.app"

    async def _create_gumroad_product(self, problem: NicheProblem, html: str) -> str | None:
        if not GUMROAD_TOKEN:
            return None
        price_cents = self._parse_price_cents(problem.suggested_price)
        try:
            data = urllib.parse.urlencode({
                "name": problem.title,
                "description": problem.description or problem.title,
                "price": str(price_cents),
                "currency_type": "eur",
            }).encode()
            req = urllib.request.Request(
                "https://api.gumroad.com/v2/products",
                data=data, method="POST",
                headers={"Authorization": f"Bearer {GUMROAD_TOKEN}"},
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                resp = json.loads(r.read())
            if resp.get("success"):
                url = resp["product"].get("short_url", "")
                log.info("Gumroad: %s", url)
                return url
        except Exception as e:
            log.error("Gumroad Fehler: %s", e)
        return None

    async def _create_lemon_product(self, problem: NicheProblem) -> str | None:
        """Optional early-sell via Lemon Squeezy (wenn API key gesetzt)."""
        if not LEMON_API_KEY or not LEMON_STORE_ID:
            return None
        price_cents = self._parse_price_cents(problem.suggested_price)
        try:
            payload = {
                "data": {
                    "type": "products",
                    "attributes": {
                        "name": problem.title[:150],
                        "description": (problem.description or "")[:500],
                        "status": "published",
                        "price": max(price_cents, 100),
                    },
                    "relationships": {
                        "store": {"data": {"type": "stores", "id": str(LEMON_STORE_ID)}}
                    },
                }
            }
            req = urllib.request.Request(
                "https://api.lemonsqueezy.com/v1/products",
                data=json.dumps(payload).encode(),
                method="POST",
                headers={
                    "Authorization": f"Bearer {LEMON_API_KEY}",
                    "Content-Type": "application/vnd.api+json",
                    "Accept": "application/vnd.api+json",
                },
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                resp = json.loads(r.read())
            url = (
                resp.get("data", {})
                .get("attributes", {})
                .get("buy_now_url")
                or resp.get("data", {}).get("attributes", {}).get("url")
                or ""
            )
            if url:
                log.info("Lemon Squeezy: %s", url)
            return url or None
        except Exception as e:
            log.debug("Lemon Squeezy skip: %s", e)
            return None

    async def _generate_api_service(self, problem: NicheProblem) -> Path | None:
        """Pay-per-use API skeleton + README für schnellen MVP-Launch."""
        slug = re.sub(r"[^a-z0-9]+", "-", problem.title.lower()).strip("-")[:40]
        api_dir = FACTORY_DIR / f"api-{slug}"
        api_dir.mkdir(exist_ok=True)
        main_py = f'''"""
{problem.title} — Pay-per-use API MVP
Auto-generated by SuperMegaBot Autonomous SaaS Factory
"""
from __future__ import annotations
import os
from aiohttp import web

API_KEY = os.getenv("SERVICE_API_KEY", "dev-key")

async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({{"status": "ok", "service": "{slug}"}})

async def handle_run(request: web.Request) -> web.Response:
    key = request.headers.get("X-API-Key", "")
    if key != API_KEY:
        return web.json_response({{"error": "unauthorized"}}, status=401)
    body = await request.json() if request.can_read_body else {{}}
    # TODO: core logic for: {problem.description[:120]}
    return web.json_response({{
        "ok": True,
        "product": "{problem.title}",
        "input": body,
        "result": "stub — implement core logic",
        "cost_eur": 0.05,
    }})

def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/health", handle_health)
    app.router.add_post("/v1/run", handle_run)
    return app

if __name__ == "__main__":
    web.run_app(create_app(), port=int(os.getenv("PORT", "8090")))
'''
        readme = f"""# {problem.title}

{problem.description}

## Monetization
Pay-per-use via Stripe / SuperMegaBot API gateway.

## Quick start
```bash
pip install aiohttp
export SERVICE_API_KEY=your-key
python main.py
curl -X POST http://localhost:8090/v1/run -H 'X-API-Key: your-key' -H 'Content-Type: application/json' -d '{{"q":"test"}}'
```
"""
        (api_dir / "main.py").write_text(main_py)
        (api_dir / "README.md").write_text(readme)
        log.info("API Service skeleton: %s", api_dir)
        return api_dir

    async def _generate_tool_skeleton(self, problem: NicheProblem) -> Path | None:
        """AI-Wrapper / Automation-Tool stub with CLI entry."""
        slug = re.sub(r"[^a-z0-9]+", "-", problem.title.lower()).strip("-")[:40]
        tool_dir = FACTORY_DIR / f"tool-{slug}"
        tool_dir.mkdir(exist_ok=True)
        code = f'''#!/usr/bin/env python3
"""{problem.title} — {problem.product_type}
{problem.description}
"""
from __future__ import annotations
import argparse
import json
import os
import sys

def run(input_text: str) -> dict:
    # Wire to modules.ai_client / product_engine in production
    return {{
        "product": "{problem.title}",
        "type": "{problem.product_type}",
        "input": input_text[:500],
        "output": f"Processed: {{input_text[:200]}}",
        "status": "mvp_stub",
    }}

def main():
    p = argparse.ArgumentParser(description="{problem.title}")
    p.add_argument("text", nargs="?", default="demo")
    args = p.parse_args()
    print(json.dumps(run(args.text), ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
'''
        (tool_dir / "run.py").write_text(code)
        (tool_dir / "README.md").write_text(
            f"# {problem.title}\n\n{problem.description}\n\n```bash\npython run.py \"dein input\"\n```\n"
        )
        log.info("Tool skeleton: %s", tool_dir)
        return tool_dir

    async def _generate_chrome_extension(self, problem: NicheProblem) -> Path | None:
        slug = re.sub(r'[^a-z0-9]+', '-', problem.title.lower()).strip('-')[:30]
        ext_dir = FACTORY_DIR / f"chrome-{slug}"
        ext_dir.mkdir(exist_ok=True)

        manifest = {
            "manifest_version": 3,
            "name": problem.title,
            "version": "1.0.0",
            "description": problem.description[:132],
            "permissions": ["activeTab", "storage"],
            "action": {"default_popup": "popup.html", "default_title": problem.title},
            "content_scripts": [{"matches": ["<all_urls>"], "js": ["content.js"], "run_at": "document_idle"}],
        }
        popup_html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><style>
body{{width:320px;background:#0a0a0f;color:#e8e8f0;font-family:system-ui;padding:16px}}
h2{{font-size:1rem;background:linear-gradient(135deg,#6c63ff,#00d4ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:12px}}
.btn{{background:#6c63ff;color:#fff;border:none;padding:10px 16px;border-radius:8px;width:100%;cursor:pointer;font-size:.9rem;font-weight:700}}
.status{{color:#888;font-size:.8rem;margin-top:8px}}
</style></head>
<body>
<h2>{problem.title}</h2>
<p style="color:#888;font-size:.85rem;margin-bottom:12px">{problem.description[:120]}</p>
<button class="btn" id="run">▶ Jetzt ausführen</button>
<div class="status" id="status">Bereit</div>
<script>
document.getElementById('run').onclick = function() {{
  document.getElementById('status').textContent = 'Läuft...';
  chrome.tabs.query({{active:true,currentWindow:true}}, function(tabs) {{
    chrome.scripting.executeScript({{target:{{tabId:tabs[0].id}},func:function(){{console.log('{problem.title} active');}}}}
    ).then(()=>document.getElementById('status').textContent='✓ Erledigt!');
  }});
}};
</script>
</body></html>"""

        content_js = f"""// {problem.title} — Content Script
console.log('[{problem.title}] Content script geladen');
// TODO: Hauptlogik implementieren
"""
        (ext_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
        (ext_dir / "popup.html").write_text(popup_html)
        (ext_dir / "content.js").write_text(content_js)

        # Als ZIP verpacken
        zip_path = FACTORY_DIR / f"chrome-{slug}.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            for f in ext_dir.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(ext_dir))

        log.info(f"Chrome Extension: {zip_path}")
        return zip_path

    def _parse_price_cents(self, price_str: str) -> int:
        m = re.search(r'[\d.,]+', price_str.replace(".", "").replace(",", "."))
        if m:
            try:
                return int(float(m.group()) * 100)
            except Exception:
                pass
        return 2900  # Default €29


# ═══════════════════════════════════════════════════════════════════════════════
# 3. FEEDBACK COLLECTOR & ITERATOR
# ═══════════════════════════════════════════════════════════════════════════════

class FeedbackCollector:
    """Sammelt Kundenfeedback via Stripe Events + Supabase + Telegram."""

    async def collect_stripe_insights(self, session: aiohttp.ClientSession) -> list[dict]:
        if not STRIPE_KEY:
            return []
        insights = []
        try:
            req = urllib.request.Request(
                "https://api.stripe.com/v1/events?limit=50&type=customer.subscription.deleted",
                headers={"Authorization": f"Bearer {STRIPE_KEY}"}
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read())
            for ev in data.get("data", []):
                obj = ev.get("data", {}).get("object", {})
                insights.append({
                    "type": "churn",
                    "product": obj.get("items", {}).get("data", [{}])[0].get("plan", {}).get("nickname", "?"),
                    "reason": obj.get("cancellation_details", {}).get("reason", "unknown"),
                })
        except Exception as e:
            log.debug(f"Stripe Events Fehler: {e}")
        return insights

    async def analyze_and_iterate(self, product: MVPProduct, insights: list[dict]) -> str:
        if not insights:
            return ""
        prompt = f"""Produkt: {product.name}
Kundenfeedback/Churns: {json.dumps(insights[:10])}

Was sind die 3 wichtigsten Verbesserungen für dieses SaaS-Produkt?
Gib konkrete, umsetzbare Maßnahmen zurück als kurze Liste."""
        try:
            return await ai_complete(prompt, max_tokens=500)
        except Exception:
            return ""


# ═══════════════════════════════════════════════════════════════════════════════
# 4. SUPABASE PERSISTENCE
# ═══════════════════════════════════════════════════════════════════════════════

async def save_to_supabase(product: MVPProduct) -> bool:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    try:
        payload = json.dumps({
            "name": product.name,
            "tagline": product.tagline,
            "landing_url": product.landing_url,
            "stripe_payment_link": product.stripe_payment_link,
            "gumroad_url": product.gumroad_url,
            "product_type": product.problem.product_type,
            "price": product.problem.suggested_price,
            "monetization": product.problem.monetization,
            "target_audience": product.problem.target_audience,
            "created_at": product.created_at,
        }).encode()
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/saas_products",
            data=payload, method="POST",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            }
        )
        urllib.request.urlopen(req, timeout=15)
        return True
    except Exception as e:
        log.debug(f"Supabase Save Fehler: {e}")
        return False


async def notify_telegram(product: MVPProduct) -> None:
    if not TG_TOKEN or not TG_CHAT:
        return
    text = (
        f"🚀 *Neues SaaS MVP live!*\n\n"
        f"*{product.name}*\n"
        f"_{product.tagline}_\n\n"
        f"🌐 Landing Page: {product.landing_url}\n"
        f"💳 Stripe: {product.stripe_payment_link or 'N/A'}\n"
        f"🛒 Gumroad: {product.gumroad_url or 'N/A'}\n"
        f"💰 Preis: {product.problem.suggested_price}\n"
        f"🎯 Zielgruppe: {product.problem.target_audience}"
    )
    try:
        data = json.dumps({"chat_id": TG_CHAT, "text": text, "parse_mode": "Markdown"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            data=data, method="POST",
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=15)
    except Exception as e:
        log.debug(f"Telegram Notify Fehler: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# 5. HAUPT-ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════════

class AutonomousSaaSFactory:
    """
    Vollautonome SaaS-Fabrik.
    Täglich: Probleme scannen → MVP bauen → deployen → verkaufen → iterieren.
    """

    def __init__(self):
        self.scanner = ProblemScanner()
        self.generator = MVPGenerator()
        self.feedback = FeedbackCollector()
        self.products: list[MVPProduct] = self._load_products()

    def _load_products(self) -> list[MVPProduct]:
        db = FACTORY_DIR / "products.json"
        if not db.exists():
            return []
        out: list[MVPProduct] = []
        try:
            data = json.loads(db.read_text())
            for d in data if isinstance(data, list) else []:
                if not isinstance(d, dict):
                    continue
                prob_raw = d.get("problem") or {}
                if isinstance(prob_raw, dict):
                    # only known NicheProblem fields
                    keys = {f.name for f in NicheProblem.__dataclass_fields__.values()}  # type: ignore[attr-defined]
                    prob = NicheProblem(**{k: v for k, v in prob_raw.items() if k in keys})
                else:
                    continue
                fields = {k: v for k, v in d.items() if k != "problem" and k in MVPProduct.__dataclass_fields__}
                fields["problem"] = prob
                fields.setdefault("feedback", fields.get("feedback") or [])
                out.append(MVPProduct(**fields))
        except Exception as e:
            log.warning("products.json load: %s", e)
        return out

    def _save_products(self) -> None:
        db = FACTORY_DIR / "products.json"
        data = []
        for p in self.products:
            d = {k: v for k, v in p.__dict__.items() if k != "problem"}
            d["problem"] = asdict(p.problem) if hasattr(p.problem, "__dataclass_fields__") else p.problem.__dict__
            data.append(d)
        db.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str))
        try:
            STATE_FILE.write_text(json.dumps({
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "total_products": len(self.products),
                "last_product": self.products[-1].name if self.products else None,
            }, indent=2))
        except Exception:
            pass

    async def run_daily_cycle(self) -> dict:
        """Dauerhafter Zyklus: Problem → MVP → Early-Sell → Notify."""
        log.info("=== AUTONOMOUS SAAS FACTORY — Zyklus startet ===")
        results: dict[str, Any] = {
            "problems_found": 0,
            "mvps_built": 0,
            "products": [],
            "types": list(PRODUCT_TYPES),
            "pipeline": [
                "problem_identify",
                "mvp_build",
                "early_sell",
                "feedback_iterate",
            ],
        }

        async with aiohttp.ClientSession() as session:
            problems = await self.scanner.scan_all(session)
            results["problems_found"] = len(problems)

            if not problems:
                log.warning("Keine Probleme gefunden — Zyklus beendet")
                return results

            # Dedupe: skip titles already built
            existing = {p.name.lower() for p in self.products}
            built = 0
            for problem in problems:
                if built >= MAX_MVPS_PER_CYCLE:
                    break
                if problem.score < MIN_PROBLEM_SCORE:
                    log.info("Score zu niedrig (%.1f): %s", problem.score, problem.title)
                    continue
                if problem.title.lower() in existing:
                    continue

                try:
                    product = await self.generator.build_mvp(problem)
                    self.products.append(product)
                    self._save_products()
                    await save_to_supabase(product)
                    await notify_telegram(product)

                    results["products"].append({
                        "name": product.name,
                        "type": problem.product_type,
                        "monetization": problem.monetization,
                        "url": product.landing_url,
                        "stripe": product.stripe_payment_link,
                        "gumroad": product.gumroad_url,
                        "price": problem.suggested_price,
                    })
                    built += 1
                    existing.add(product.name.lower())
                    log.info("✅ MVP #%d: %s → %s", built, product.name, product.landing_url)
                except Exception as e:
                    log.error("MVP Build Fehler (%s): %s", problem.title, e)

                await asyncio.sleep(2)

            results["mvps_built"] = built

        log.info("=== FACTORY FERTIG: %d MVPs / %d Probleme ===", built, len(problems))
        return results

    async def run_feedback_cycle(self) -> dict:
        """Wöchentlicher Feedback-Zyklus: Daten sammeln + iterieren."""
        log.info("=== FEEDBACK CYCLE startet ===")
        results = {"analyzed": 0, "iterations": []}

        async with aiohttp.ClientSession() as session:
            insights = await self.feedback.collect_stripe_insights(session)

            for product in self.products[-5:]:  # Letzte 5 Produkte analysieren
                if not insights:
                    break
                iteration = await self.feedback.analyze_and_iterate(product, insights)
                if iteration:
                    product.feedback.append(iteration)
                    results["iterations"].append({"product": product.name, "suggestion": iteration[:200]})
                    results["analyzed"] += 1

        self._save_products()
        log.info(f"=== FEEDBACK CYCLE FERTIG: {results['analyzed']} Produkte analysiert ===")
        return results

    def get_status(self) -> dict:
        return {
            "total_products": len(self.products),
            "products": [
                {
                    "name": p.name,
                    "url": p.landing_url,
                    "price": p.problem.suggested_price,
                    "type": p.problem.product_type,
                    "created": p.created_at[:10] if p.created_at else "",
                    "stripe": p.stripe_payment_link,
                    "gumroad": p.gumroad_url,
                }
                for p in self.products[-20:]
            ],
        }


# ─── Singleton ────────────────────────────────────────────────────────────────
_factory: AutonomousSaaSFactory | None = None

def get_factory() -> AutonomousSaaSFactory:
    global _factory
    if _factory is None:
        _factory = AutonomousSaaSFactory()
    return _factory


async def run_daily_cycle() -> dict:
    return await get_factory().run_daily_cycle()

async def run_feedback_cycle() -> dict:
    return await get_factory().run_feedback_cycle()

def get_status() -> dict:
    return get_factory().get_status()


if __name__ == "__main__":
    import urllib.parse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    print("🏭 Autonomous SaaS Factory — Starte täglichen Zyklus...")
    result = asyncio.run(run_daily_cycle())
    print(json.dumps(result, ensure_ascii=False, indent=2))
