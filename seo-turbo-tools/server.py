import sys
import os
import json
import logging
import re
import time
import asyncio
from datetime import datetime
from pathlib import Path
import aiohttp
import stripe
from aiohttp import web


async def ai_complete(prompt: str, system: str = "Du bist ein SEO-Experte.", max_tokens: int = 800) -> str:
    groq_key = os.getenv("GROQ_API_KEY", "")
    or_key = os.getenv("OPENROUTER_API_KEY", "")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    msgs = [{"role": "user", "content": prompt}]
    async with aiohttp.ClientSession() as session:
        if groq_key:
            try:
                async with session.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                    json={"model": "llama-3.1-8b-instant", "messages": msgs, "max_tokens": max_tokens, "temperature": 0.7},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as r:
                    if r.status == 200:
                        d = await r.json()
                        return d["choices"][0]["message"]["content"]
            except Exception:
                pass
        if anthropic_key:
            try:
                async with session.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": anthropic_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                    json={"model": "claude-haiku-4-5-20251001", "messages": msgs, "max_tokens": max_tokens, "system": system},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as r:
                    if r.status == 200:
                        d = await r.json()
                        return d["content"][0]["text"]
            except Exception:
                pass
        if or_key:
            try:
                async with session.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {or_key}", "Content-Type": "application/json"},
                    json={"model": "meta-llama/llama-3.1-8b-instruct:free", "messages": msgs, "max_tokens": max_tokens},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as r:
                    if r.status == 200:
                        d = await r.json()
                        return d["choices"][0]["message"]["content"]
            except Exception:
                pass
    return ""

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PORT = int(os.getenv("PORT", 8080))
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
SHOPIFY_SHOP_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_ADMIN_API_TOKEN = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
APP_URL = os.getenv("APP_URL", "https://seo-turbo-tools-production.up.railway.app")
KV_API_KEY = os.getenv("KLAVIYO_API_KEY", "")

PRICE_IDS = {
    "starter": os.getenv("STRIPE_PRICE_STARTER", "price_1Thnt5RJECiV6vSmb4nBpi7W"),
    "pro": os.getenv("STRIPE_PRICE_PRO", "price_1Thnt6RJECiV6vSmRdEKjNc7"),
}

_analysis_history: list = []

# ── SEO Traffic Engine Bridge ──────────────────────────────────────────────
_SEO_ENGINE = os.getenv("SEO_ENGINE_URL", "https://seo-traffic-engine-production.up.railway.app")
_AMAZON_TAG = os.getenv("AMAZON_AFFILIATE_TAG", "bullpower-21")
_EBAY_APP_ID = os.getenv("EBAY_APP_ID", "")


async def seo_get_products(keyword: str, source: str = "all") -> list:
    import urllib.parse
    results = []
    if source in ("amazon", "all"):
        amazon_url = f"https://www.amazon.de/s?k={urllib.parse.quote(keyword)}&tag={_AMAZON_TAG}"
        results.append({"title": f"Amazon: {keyword}", "url": amazon_url, "source": "amazon", "price": ""})
    if source in ("ebay", "all") and _EBAY_APP_ID:
        try:
            params = f"OPERATION-NAME=findItemsByKeywords&SERVICE-VERSION=1.0.0&SECURITY-APPNAME={_EBAY_APP_ID}&RESPONSE-DATA-FORMAT=JSON&keywords={urllib.parse.quote(keyword)}&paginationInput.entriesPerPage=3"
            async with aiohttp.ClientSession() as s:
                async with s.get(f"https://svcs.ebay.com/services/search/FindingService/v1?{params}", timeout=aiohttp.ClientTimeout(total=8)) as r:
                    if r.status == 200:
                        data = await r.json()
                        items = data.get("findItemsByKeywordsResponse", [{}])[0].get("searchResult", [{}])[0].get("item", [])
                        for item in items[:3]:
                            results.append({"title": item.get("title", [""])[0], "url": item.get("viewItemURL", [""])[0], "source": "ebay", "price": item.get("sellingStatus", [{}])[0].get("currentPrice", [{}])[0].get("__value__", "")})
        except Exception as e:
            logger.warning(f"eBay API: {e}")
    elif source in ("ebay", "all"):
        import urllib.parse as _up
        ebay_url = f"https://www.ebay.de/sch/i.html?_nkw={_up.quote(keyword)}"
        results.append({"title": f"eBay: {keyword}", "url": ebay_url, "source": "ebay", "price": ""})
    return results


async def seo_push_keyword(keyword: str, url: str = "") -> bool:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{_SEO_ENGINE}/api/trigger/articles", json={"keyword": keyword}, timeout=aiohttp.ClientTimeout(total=8)) as r:
                return r.status == 200
    except Exception:
        return False
# ── End SEO Bridge ──────────────────────────────────────────────────────────

stripe.api_key = STRIPE_SECRET_KEY
_start_time = time.time()

LANDING_HTML = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>SEO Turbo Tools — KI-gestützte SEO-Optimierung</title>
<meta name="description" content="Analysiere, optimiere und dominiere Suchergebnisse mit KI-Power. Keyword-Analyse, Meta-Generator, SEO-Score — alles automatisch."/>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0a0f1a;--bg2:#0d1525;--surface:#111827;--border:#1f2937;--text:#f9fafb;--muted:#9ca3af;--green:#10b981;--blue:#3b82f6;--purple:#8b5cf6}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;line-height:1.6}
.hero{background:linear-gradient(135deg,#0a0f1a 0%,#111827 50%,#0a0f1a 100%);padding:80px 20px;text-align:center;border-bottom:1px solid var(--border)}
.badge{display:inline-block;background:rgba(139,92,246,.15);color:var(--purple);border:1px solid rgba(139,92,246,.3);border-radius:20px;padding:6px 16px;font-size:13px;font-weight:600;margin-bottom:24px;letter-spacing:.5px}
h1{font-size:clamp(2rem,5vw,3.5rem);font-weight:800;margin-bottom:20px;background:linear-gradient(135deg,#f9fafb,#10b981);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.subtitle{font-size:1.2rem;color:var(--muted);max-width:600px;margin:0 auto 40px}
.demo-box{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:24px;max-width:640px;margin:0 auto 40px;text-align:left}
.demo-box h3{color:var(--green);margin-bottom:12px;font-size:1rem}
.demo-input{display:flex;gap:10px;flex-wrap:wrap}
.demo-input input{flex:1;min-width:200px;background:#0a0f1a;border:1px solid var(--border);border-radius:8px;padding:12px 16px;color:var(--text);font-size:14px;outline:none}
.demo-input input:focus{border-color:var(--green)}
.btn{display:inline-block;background:var(--green);color:#000;padding:12px 24px;border-radius:8px;font-weight:700;font-size:14px;border:none;cursor:pointer;text-decoration:none;transition:all .2s}
.btn:hover{background:#059669;transform:translateY(-1px)}
.btn-outline{background:transparent;color:var(--green);border:1px solid var(--green)}
.btn-outline:hover{background:var(--green);color:#000}
#demo-result{margin-top:16px;display:none}
.score-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-top:8px}
.score-item{background:#0a0f1a;border-radius:8px;padding:10px;text-align:center}
.score-num{font-size:1.5rem;font-weight:800;color:var(--green)}
.score-label{font-size:11px;color:var(--muted)}
.features{padding:60px 20px;max-width:1100px;margin:0 auto}
.features h2{text-align:center;font-size:2rem;font-weight:800;margin-bottom:40px}
.feature-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:20px}
.feature-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:24px}
.feature-icon{font-size:2rem;margin-bottom:12px}
.feature-card h3{font-size:1.1rem;font-weight:700;margin-bottom:8px}
.feature-card p{color:var(--muted);font-size:.9rem}
.pricing{background:var(--bg2);padding:60px 20px;border-top:1px solid var(--border);border-bottom:1px solid var(--border)}
.pricing h2{text-align:center;font-size:2rem;font-weight:800;margin-bottom:40px}
.plan-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:24px;max-width:700px;margin:0 auto}
.plan{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:32px;text-align:center}
.plan.popular{border-color:var(--green);position:relative}
.plan.popular::before{content:'BELIEBT';position:absolute;top:-12px;left:50%;transform:translateX(-50%);background:var(--green);color:#000;font-size:11px;font-weight:800;padding:4px 12px;border-radius:20px}
.plan-name{font-size:1.2rem;font-weight:700;margin-bottom:8px}
.plan-price{font-size:3rem;font-weight:800;color:var(--green)}
.plan-price span{font-size:1rem;color:var(--muted)}
.plan-features{list-style:none;margin:20px 0 24px;text-align:left}
.plan-features li{padding:6px 0;color:var(--muted);font-size:.9rem}
.plan-features li::before{content:'✓ ';color:var(--green)}
.cta{padding:60px 20px;text-align:center}
.api-demo{padding:40px 20px;max-width:800px;margin:0 auto}
.api-demo h2{font-size:1.5rem;font-weight:800;margin-bottom:20px;text-align:center}
.tabs{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}
.tab{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:8px 16px;cursor:pointer;font-size:13px;color:var(--muted)}
.tab.active{background:var(--green);color:#000;border-color:var(--green);font-weight:700}
.api-output{background:#000;border:1px solid var(--border);border-radius:8px;padding:16px;font-family:monospace;font-size:13px;color:#10b981;min-height:120px;white-space:pre-wrap;word-break:break-all}
footer{text-align:center;padding:30px;color:var(--muted);font-size:.85rem;border-top:1px solid var(--border)}
</style>
</head>
<body>
<div class="hero">
  <div class="badge">🚀 KI-GESTÜTZTE SEO AUTOMATION</div>
  <h1>SEO Turbo Tools</h1>
  <p class="subtitle">Analysiere jede Webseite in Sekunden. KI optimiert deine Metas, findet Keywords und gibt konkrete Handlungsempfehlungen.</p>
  <div class="demo-box">
    <h3>🔍 Live SEO-Analyse — Teste jetzt kostenlos</h3>
    <div class="demo-input">
      <input type="url" id="analyze-url" placeholder="https://deine-webseite.de" value=""/>
      <button class="btn" onclick="runAnalysis()">Analysieren</button>
    </div>
    <div id="demo-result"></div>
  </div>
  <a href="#pricing" class="btn" style="margin-right:12px">Jetzt starten ab €29/mo</a>
  <a href="#features" class="btn btn-outline">Features ansehen</a>
</div>

<div class="features" id="features">
  <h2>Alles was du brauchst</h2>
  <div class="feature-grid">
    <div class="feature-card">
      <div class="feature-icon">🧠</div>
      <h3>KI SEO-Analyse</h3>
      <p>Claude KI analysiert deine Seiten auf Title, Meta, Content, Struktur und gibt einen Score 0-100 mit konkreten Fixes.</p>
    </div>
    <div class="feature-card">
      <div class="feature-icon">🔑</div>
      <h3>Keyword-Turbo</h3>
      <p>Gib ein Thema ein — KI generiert sofort relevante Keywords, Long-Tails und Suchintentionen für deinen Markt.</p>
    </div>
    <div class="feature-card">
      <div class="feature-icon">✍️</div>
      <h3>Meta-Generator</h3>
      <p>Perfekte Title-Tags und Descriptions in Sekunden. KI-optimiert für Klickrate und Suchmaschinen-Relevanz.</p>
    </div>
    <div class="feature-card">
      <div class="feature-icon">📊</div>
      <h3>SEO-Score Dashboard</h3>
      <p>Vier Dimensionen: Title, Meta, Content, Struktur. Siehst du sofort wo du Punkte verlierst.</p>
    </div>
    <div class="feature-card">
      <div class="feature-icon">⚡</div>
      <h3>API-Zugang</h3>
      <p>Alle Tools als REST-API verfügbar. Integriere SEO-Analyse direkt in dein CMS oder Workflow.</p>
    </div>
    <div class="feature-card">
      <div class="feature-icon">🔔</div>
      <h3>Telegram Alerts</h3>
      <p>Erhalte SEO-Reports direkt auf dein Handy. Automatisch täglich oder bei kritischen Issues.</p>
    </div>
  </div>
</div>

<div class="api-demo">
  <h2>Live API Demo</h2>
  <div class="tabs">
    <div class="tab active" onclick="setTab(this,'keywords')">Keywords</div>
    <div class="tab" onclick="setTab(this,'meta')">Meta Generator</div>
  </div>
  <div style="display:flex;gap:10px;margin-bottom:10px;flex-wrap:wrap">
    <input id="api-input" type="text" placeholder="Thema eingeben z.B. 'Shopify Store erstellen'" style="flex:1;min-width:200px;background:#0a0f1a;border:1px solid #1f2937;border-radius:8px;padding:10px 14px;color:#f9fafb;font-size:13px;outline:none"/>
    <button class="btn" onclick="runApiDemo()">Generieren</button>
  </div>
  <div class="api-output" id="api-output">// Klick auf "Generieren" für Live-Demo...</div>
</div>

<div class="pricing" id="pricing">
  <h2>Einfache Preise</h2>
  <div class="plan-grid">
    <div class="plan">
      <div class="plan-name">Starter</div>
      <div class="plan-price">€29<span>/mo</span></div>
      <ul class="plan-features">
        <li>50 SEO-Analysen/Monat</li>
        <li>Keyword-Generator</li>
        <li>Meta-Tag-Generator</li>
        <li>API-Zugang</li>
        <li>Email Support</li>
      </ul>
      <button class="btn btn-outline" style="width:100%" onclick="checkout('starter')">Starter wählen</button>
    </div>
    <div class="plan popular">
      <div class="plan-name">Pro</div>
      <div class="plan-price">€79<span>/mo</span></div>
      <ul class="plan-features">
        <li>Unbegrenzte Analysen</li>
        <li>Keyword-Turbo + Long-Tails</li>
        <li>Bulk Meta-Generator</li>
        <li>Priority API-Zugang</li>
        <li>Telegram Alerts</li>
        <li>Priority Support</li>
      </ul>
      <button class="btn" style="width:100%" onclick="checkout('pro')">Pro wählen</button>
    </div>
  </div>
</div>

<div class="cta">
  <h2 style="font-size:2rem;font-weight:800;margin-bottom:16px">Bereit für besseres SEO?</h2>
  <p style="color:#9ca3af;margin-bottom:24px">Starte heute. 14 Tage kostenlos testen.</p>
  <button class="btn" onclick="checkout('starter')" style="margin-right:12px">Starter — €29/mo</button>
  <button class="btn" style="background:#8b5cf6" onclick="checkout('pro')">Pro — €79/mo</button>
</div>

<footer>SEO Turbo Tools &copy; 2026 — Powered by Claude KI &amp; Anthropic</footer>

<script>
let currentTab = 'keywords';
function setTab(el, tab) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  currentTab = tab;
  document.getElementById('api-output').textContent = '// Klick auf "Generieren" für Live-Demo...';
}
async function runAnalysis() {
  const url = document.getElementById('analyze-url').value.trim();
  if (!url) { alert('Bitte URL eingeben'); return; }
  const res = document.getElementById('demo-result');
  res.style.display = 'block';
  res.innerHTML = '<p style="color:#9ca3af;text-align:center;padding:16px">⏳ Analysiere...</p>';
  try {
    const r = await fetch('/api/analyze', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});
    const d = await r.json();
    if (d.error) { res.innerHTML = '<p style="color:#ef4444">Fehler: '+d.error+'</p>'; return; }
    res.innerHTML = '<div class="score-grid">' +
      '<div class="score-item"><div class="score-num">'+d.overall_score+'</div><div class="score-label">Gesamt</div></div>' +
      '<div class="score-item"><div class="score-num">'+d.title_score+'</div><div class="score-label">Title</div></div>' +
      '<div class="score-item"><div class="score-num">'+d.meta_score+'</div><div class="score-label">Meta</div></div>' +
      '<div class="score-item"><div class="score-num">'+d.content_score+'</div><div class="score-label">Content</div></div>' +
      '</div>' +
      '<div style="margin-top:12px;font-size:13px;color:#9ca3af">💡 '+( d.recommendations && d.recommendations[0] ? d.recommendations[0] : 'Keine Empfehlung')+'</div>';
  } catch(e) { res.innerHTML = '<p style="color:#ef4444">Netzwerkfehler: '+e.message+'</p>'; }
}
async function runApiDemo() {
  const input = document.getElementById('api-input').value.trim();
  if (!input) { alert('Bitte Thema eingeben'); return; }
  const out = document.getElementById('api-output');
  out.textContent = '⏳ KI generiert...';
  try {
    const endpoint = currentTab === 'keywords' ? '/api/keywords' : '/api/meta';
    const body = currentTab === 'keywords' ? {topic: input} : {topic: input};
    const r = await fetch(endpoint, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const d = await r.json();
    out.textContent = JSON.stringify(d, null, 2);
  } catch(e) { out.textContent = 'Fehler: ' + e.message; }
}
async function checkout(plan) {
  try {
    const r = await fetch('/api/checkout', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({plan})});
    const d = await r.json();
    if (d.url) window.location.href = d.url;
    else alert('Fehler: ' + (d.error || 'Unbekannt'));
  } catch(e) { alert('Netzwerkfehler: ' + e.message); }
}
</script>
</body>
</html>"""

SUCCESS_HTML = """<!DOCTYPE html>
<html lang="de">
<head><meta charset="UTF-8"/><title>Willkommen bei SEO Turbo Tools!</title>
<style>body{background:#0a0f1a;color:#f9fafb;font-family:sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;text-align:center;padding:20px}
.box{background:#111827;border:1px solid #10b981;border-radius:16px;padding:48px;max-width:500px}
h1{color:#10b981;font-size:2rem;margin-bottom:16px}p{color:#9ca3af;margin-bottom:24px}
.btn{display:inline-block;background:#10b981;color:#000;padding:12px 24px;border-radius:8px;font-weight:700;text-decoration:none}</style>
</head>
<body><div class="box">
<div style="font-size:3rem;margin-bottom:16px">🎉</div>
<h1>Willkommen!</h1>
<p>Dein SEO Turbo Tools Abo ist aktiv. Du erhältst in Kürze eine Bestätigung per Email.</p>
<a href="/" class="btn">Zur Startseite</a>
</div></body></html>"""


async def klaviyo_track(event: str, props: dict):
    if not KV_API_KEY:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                "https://a.klaviyo.com/api/events/",
                headers={"Authorization": f"Klaviyo-API-Key {KV_API_KEY}",
                         "revision": "2024-06-15", "Content-Type": "application/json"},
                json={"data": {"type": "event", "attributes": {
                    "metric": {"data": {"type": "metric", "attributes": {"name": event}}},
                    "properties": props,
                }}},
                timeout=aiohttp.ClientTimeout(total=8),
            )
    except Exception:
        pass


async def send_telegram(msg: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    async with aiohttp.ClientSession() as session:
        await session.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"})


async def handle_health(request):
    return web.json_response({
        "status": "ok",
        "service": "seo-turbo-tools",
        "uptime": round(time.time() - _start_time, 1),
    })


async def handle_root(request):
    return web.Response(text=LANDING_HTML, content_type="text/html")


async def handle_success(request):
    return web.Response(text=SUCCESS_HTML, content_type="text/html")


async def handle_analyze(request):
    try:
        data = await request.json()
        url = data.get("url", "").strip()
        if not url:
            return web.json_response({"error": "URL erforderlich"}, status=400)
        if not url.startswith("http"):
            url = "https://" + url

        html_content = ""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=12),
                                       headers={"User-Agent": "SEOTurboTools/1.0"}) as r:
                    html_content = await r.text()
        except Exception as e:
            return web.json_response({"error": f"URL nicht erreichbar: {str(e)}"}, status=400)

        prompt = f"""Analysiere diese HTML-Seite für SEO und antworte NUR mit gültigem JSON (kein Markdown, kein Text davor/danach):
{{
  "title_score": <0-100>,
  "meta_score": <0-100>,
  "content_score": <0-100>,
  "overall_score": <0-100>,
  "issues": ["issue1", "issue2"],
  "recommendations": ["empfehlung1", "empfehlung2"]
}}

HTML (erste 4000 Zeichen): {html_content[:4000]}"""

        text = await ai_complete(prompt, max_tokens=800)
        text = text.strip()
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            result = json.loads(match.group())
        else:
            result = json.loads(text)
        result["url"] = url
        _analysis_history.insert(0, result)
        if len(_analysis_history) > 50:
            _analysis_history.pop()
        logger.info(f"SEO analyzed: {url} → score {result.get('overall_score')}")
        return web.json_response(result)
    except Exception as e:
        logger.error(f"Analyze error: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def handle_keywords(request):
    try:
        data = await request.json()
        topic = data.get("topic", "").strip()
        if not topic:
            return web.json_response({"error": "Thema erforderlich"}, status=400)

        prompt = f"""Generiere SEO-Keywords für das Thema "{topic}" auf Deutsch. Antworte NUR mit JSON (kein Markdown):
{{
  "primary_keywords": ["keyword1", "keyword2", "keyword3"],
  "long_tail": ["longtail phrase 1", "longtail phrase 2", "longtail phrase 3"],
  "questions": ["frage 1?", "frage 2?", "frage 3?"],
  "search_volume": "hoch/mittel/niedrig",
  "competition": "hoch/mittel/niedrig"
}}"""

        text = await ai_complete(prompt, max_tokens=600)
        text = text.strip()
        match = re.search(r'\{.*\}', text, re.DOTALL)
        result = json.loads(match.group() if match else text)
        return web.json_response(result)
    except Exception as e:
        logger.error(f"Keywords error: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def handle_meta(request):
    try:
        data = await request.json()
        topic = data.get("topic", "").strip()
        if not topic:
            return web.json_response({"error": "Thema erforderlich"}, status=400)

        prompt = f"""Erstelle optimierte SEO Meta-Tags für "{topic}" auf Deutsch. Antworte NUR mit JSON (kein Markdown):
{{
  "title": "<60 Zeichen, keyword-optimiert>",
  "description": "<155 Zeichen, mit Call-to-Action>",
  "og_title": "<Facebook/LinkedIn Titel>",
  "og_description": "<Social Media Beschreibung>",
  "keywords": ["keyword1", "keyword2", "keyword3"]
}}"""

        text = await ai_complete(prompt, max_tokens=500)
        text = text.strip()
        match = re.search(r'\{.*\}', text, re.DOTALL)
        result = json.loads(match.group() if match else text)
        return web.json_response(result)
    except Exception as e:
        logger.error(f"Meta error: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def handle_checkout(request):
    try:
        data = await request.json()
        plan = data.get("plan", "starter")
        sk = os.getenv("STRIPE_SECRET_KEY", "")
        price_starter = os.getenv("STRIPE_PRICE_STARTER", PRICE_IDS["starter"])
        price_pro = os.getenv("STRIPE_PRICE_PRO", PRICE_IDS["pro"])
        app_url = os.getenv("APP_URL", APP_URL)
        price_map = {"starter": price_starter, "pro": price_pro}
        price_id = price_map.get(plan, "")
        if not sk:
            return web.json_response({"error": "STRIPE_SECRET_KEY nicht gesetzt"}, status=500)
        if not price_id:
            return web.json_response({"error": f"Plan '{plan}' nicht konfiguriert (STRIPE_PRICE_{plan.upper()} fehlt)"}, status=400)

        import stripe as _stripe
        client = _stripe.StripeClient(sk)
        session = client.checkout.sessions.create(params={
            "mode": "subscription",
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": f"{app_url}/success?session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": f"{app_url}/",
            "allow_promotion_codes": True,
            "subscription_data": {"trial_period_days": 14},
        })
        logger.info(f"Checkout created: plan={plan} session={session.id} price={price_id}")
        return web.json_response({"url": session.url})
    except Exception as e:
        logger.error(f"Checkout error: {type(e).__name__}: {repr(e)}")
        return web.json_response({"error": f"{type(e).__name__}: {str(e) or repr(e)}"}, status=500)


async def handle_webhook(request):
    payload = await request.read()
    sig = request.headers.get("stripe-signature", "")

    try:
        if STRIPE_WEBHOOK_SECRET and sig:
            event = stripe.webhooks.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
        else:
            event = json.loads(payload)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return web.json_response({"error": str(e)}, status=400)

    if event["type"] == "checkout.session.completed":
        s = event["data"]["object"]
        plan = s.get("metadata", {}).get("plan", "starter") if s.get("metadata") else "starter"
        email = s.get("customer_email") or "unbekannt"
        amount = s.get("amount_total", 0)
        msg = (
            f"🎉 <b>NEUER SEO TURBO KUNDE!</b>\n\n"
            f"💳 Plan: <b>{plan.upper()}</b>\n"
            f"📧 Email: {email}\n"
            f"💰 Betrag: €{amount/100:.2f}\n"
            f"⏰ SEO Turbo Tools — {__import__('datetime').datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        asyncio.create_task(send_telegram(msg))
        logger.info(f"New customer: {email} plan={plan}")

    return web.json_response({"received": True})


async def handle_content_optimizer(request):
    try:
        data = await request.json()
        content = data.get("content", "").strip()
        keyword = data.get("target_keyword", "").strip()
        if not content or not keyword:
            return web.json_response({"error": "content und target_keyword erforderlich"}, status=400)
        words = content.split()
        kw_count = content.lower().count(keyword.lower())
        density = round(kw_count / max(len(words), 1) * 100, 2)
        prompt = f"""Optimiere diesen Content für das Keyword "{keyword}". Antworte NUR mit JSON:
{{
  "keyword_density": {density},
  "density_rating": "optimal(0.5-2.5%)/zu_niedrig/zu_hoch",
  "lsi_keywords": ["verwandtes_keyword1","verwandtes_keyword2","verwandtes_keyword3"],
  "readability_score": <0-100>,
  "recommendations": ["empfehlung1","empfehlung2","empfehlung3"],
  "optimized_intro": "<erste 2 Sätze optimiert>"
}}
Content (erste 1500 Zeichen): {content[:1500]}"""
        text = await ai_complete(prompt, max_tokens=700)
        text = text.strip()
        match = re.search(r'\{.*\}', text, re.DOTALL)
        result = json.loads(match.group() if match else text)
        result["word_count"] = len(words)
        result["keyword_occurrences"] = kw_count
        return web.json_response(result)
    except Exception as e:
        logger.error(f"Content optimizer error: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def handle_shopify_audit(request):
    try:
        domain = SHOPIFY_SHOP_DOMAIN
        token = SHOPIFY_ADMIN_API_TOKEN
        if not domain or not token:
            return web.json_response({"error": "SHOPIFY_SHOP_DOMAIN / SHOPIFY_ADMIN_API_TOKEN nicht gesetzt"}, status=500)
        issues, checked = [], 0
        async with aiohttp.ClientSession() as session:
            url = f"https://{domain}/admin/api/2024-10/products.json?limit=20&fields=id,title,body_html,handle,images,variants"
            async with session.get(url, headers={"X-Shopify-Access-Token": token},
                                   timeout=aiohttp.ClientTimeout(total=15)) as r:
                products_data = await r.json()
        products = products_data.get("products", [])
        no_desc, no_img_alt, short_title = 0, 0, 0
        for p in products:
            checked += 1
            if not p.get("body_html") or len(p.get("body_html", "")) < 50:
                no_desc += 1
                issues.append(f"Produkt '{p['title'][:40]}': Keine/kurze Beschreibung")
            if len(p.get("title", "")) < 20:
                short_title += 1
                issues.append(f"Produkt '{p['title'][:40]}': Titel zu kurz (<20 Zeichen)")
            for img in p.get("images", []):
                if not img.get("alt"):
                    no_img_alt += 1
        score = max(0, 100 - (no_desc * 5) - (short_title * 3) - min(no_img_alt, 10) * 2)
        return web.json_response({
            "shop_domain": domain,
            "products_checked": checked,
            "seo_score": score,
            "issues_found": len(issues),
            "no_description": no_desc,
            "short_titles": short_title,
            "missing_alt_tags": no_img_alt,
            "top_issues": issues[:10],
            "recommendation": "Füge Beschreibungen und Alt-Tags hinzu für besseres SEO" if issues else "SEO-Struktur ist gut!"
        })
    except Exception as e:
        logger.error(f"Shopify audit error: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def handle_seo_products(request):
    keyword = request.rel_url.query.get("keyword", "shopify automation")
    source = request.rel_url.query.get("source", "all")
    products = await seo_get_products(keyword, source)
    return web.json_response({"keyword": keyword, "products": products, "seo_engine": _SEO_ENGINE})


async def handle_sitemap(request):
    now = datetime.utcnow().strftime("%Y-%m-%d")
    urls = [
        ("", "1.0", "daily"),
        ("/success", "0.5", "monthly"),
    ]
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path, priority, freq in urls:
        lines.append(f"  <url><loc>{APP_URL}{path}</loc><lastmod>{now}</lastmod>"
                     f"<changefreq>{freq}</changefreq><priority>{priority}</priority></url>")
    lines.append("</urlset>")
    return web.Response(text="\n".join(lines), content_type="application/xml")


async def handle_robots(request):
    body = f"User-agent: *\nAllow: /\nSitemap: {APP_URL}/sitemap.xml\n"
    return web.Response(text=body, content_type="text/plain")


async def handle_ingest(request):
    try:
        data = await request.json()
        title = data.get("title", "")
        url = data.get("url", "")
        keyword = data.get("keyword", "")
        product_name = data.get("product_name", "")
        product_url = data.get("product_url", "")
        is_relevant = bool(re.search(r"seo|keyword|ranking|traffic|backlink", keyword + " " + title, re.I))
        prefix = "🎯 <b>Relevanter SEO Artikel!</b>" if is_relevant else "📰 <b>SEO Artikel → SEO Turbo Tools</b>"
        asyncio.create_task(send_telegram(
            f"{prefix}\n🔑 {keyword}\n📄 {title}\n🔗 {url}\n🛒 {product_name}: {product_url}"
        ))
        return web.json_response({"status": "ok", "service": "seo-turbo-tools", "processed": title, "relevant": is_relevant})
    except Exception as e:
        logger.error("Ingest error: %s", e)
        return web.json_response({"error": str(e)}, status=200)


async def handle_dashboard_data(request):
    return web.json_response({
        "analyses_total": len(_analysis_history),
        "recent_analyses": _analysis_history[:10],
        "avg_score": round(sum(a.get("overall_score", 0) for a in _analysis_history) / max(len(_analysis_history), 1), 1),
        "service": "seo-turbo-tools",
        "uptime": round(time.time() - _start_time, 1),
    })


async def _autonomous_loop():
    """Vollautomatischer SEO/Content/Traffic Loop — alle 6h"""
    await asyncio.sleep(30)
    topics = ['Shopify SEO optimieren 2025', 'E-Commerce Traffic steigern', 'Google Rankings verbessern',
              'Keyword-Strategie für Online-Shops', 'On-Page SEO Checkliste']
    cycle = 0
    while True:
        try:
            topic = topics[cycle % len(topics)]
            prompt = (
                f'Schreibe einen kurzen SEO-Artikel (200 Wörter) auf Deutsch über: {topic}. '
                f'Format: JSON {{"title":"...","content":"...","keywords":["..."]}}'
            )
            txt = await ai_complete(prompt, max_tokens=600)
            m = re.search(r'\{[\s\S]+\}', txt)
            if m:
                article = json.loads(m.group())
                title = article.get('title', topic)
                content = article.get('content', '')
                keywords = ', '.join(article.get('keywords', []))
                await send_telegram(
                    f'🔍 <b>SEO Turbo Update</b>\n\n<b>{title}</b>\n\n'
                    f'{content[:300]}...\n\n🏷 Keywords: {keywords}\n🌐 {APP_URL}')
                await klaviyo_track("SEO Article Published", {
                    "title": title, "topic": topic, "keywords": keywords, "url": APP_URL
                })
                logger.info(f'Auto-Artikel gepostet: {title}')
                try:
                    async with aiohttp.ClientSession() as s:
                        await s.post(f'{_SEO_ENGINE}/api/ingest',
                            json={'title': title, 'content': content, 'keyword': topic,
                                  'source': 'seo-turbo-tools', 'url': APP_URL},
                            timeout=aiohttp.ClientTimeout(total=10))
                except Exception:
                    pass
            if cycle % 4 == 0:
                sitemap = f'{APP_URL}/sitemap.xml'
                async with aiohttp.ClientSession() as s:
                    for ping_url in [f'https://www.google.com/ping?sitemap={sitemap}',
                                     f'https://www.bing.com/ping?sitemap={sitemap}']:
                        try:
                            await s.get(ping_url, timeout=aiohttp.ClientTimeout(total=10))
                        except Exception:
                            pass
                logger.info('Sitemap gepingt: Google + Bing')
            cycle += 1
        except Exception as e:
            logger.error(f'_autonomous_loop Fehler: {e}')
        await asyncio.sleep(6 * 3600)


def create_app():
    app = web.Application()
    app.on_startup.append(lambda a: asyncio.create_task(_autonomous_loop()))
    app.router.add_get("/", handle_root)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/success", handle_success)
    app.router.add_get("/api/dashboard", handle_dashboard_data)
    app.router.add_get("/api/seo/products", handle_seo_products)
    app.router.add_post("/api/analyze", handle_analyze)
    app.router.add_post("/api/keywords", handle_keywords)
    app.router.add_post("/api/meta", handle_meta)
    app.router.add_post("/api/content-optimizer", handle_content_optimizer)
    app.router.add_post("/api/shopify-audit", handle_shopify_audit)
    app.router.add_post("/api/checkout", handle_checkout)
    app.router.add_post("/api/webhook", handle_webhook)
    app.router.add_post("/api/ingest", handle_ingest)
    app.router.add_get("/sitemap.xml", handle_sitemap)
    app.router.add_get("/robots.txt", handle_robots)
    return app


if __name__ == "__main__":
    logger.info(f"SEO Turbo Tools starting on port {PORT}")
    web.run_app(create_app(), host="0.0.0.0", port=PORT)
