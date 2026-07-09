#!/usr/bin/env python3
"""
ShopText.ai — Routes & Landing Page
GET  /shoptext               Landing page
POST /api/shoptext/generate  AI text generation
POST /api/shoptext/checkout  Stripe checkout
GET  /shoptext/success       Success page
GET  /api/shoptext/stats     Stats
"""
from __future__ import annotations

import os
from aiohttp import web

LANDING_HTML = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ShopText.ai — KI-Produkttexte für Shopify</title>
<meta name="description" content="Professionelle, SEO-optimierte Produkttexte auf Knopfdruck. Powered by Claude AI. Für deutsche Shopify-Händler.">
<style>
:root{
  --bg:#07090F;--surface:#0E1320;--card:#131C2E;--card2:#0F1828;
  --border:#1A2840;--border2:#152235;
  --gold:#D4941E;--gold2:#F0AB28;--gold-lo:rgba(212,148,30,.1);
  --green:#26C274;--green-lo:rgba(38,194,116,.08);
  --blue:#4B9FFF;--blue-lo:rgba(75,159,255,.08);
  --text:#EAE5DB;--text2:#9AA4B8;--text3:#4E5C72;
  --mono:ui-monospace,"SF Mono",monospace;
  --sans:-apple-system,BlinkMacSystemFont,"SF Pro Display","Segoe UI",system-ui,sans-serif;
  --r:10px;
}
@media(prefers-color-scheme:light){
  :root{
    --bg:#F2EFE9;--surface:#E8E4DC;--card:#FFFFFF;--card2:#F7F5F1;
    --border:#D8D3C8;--border2:#E4E0D8;
    --gold:#8A600A;--gold2:#A37010;--gold-lo:rgba(138,96,10,.07);
    --green:#197A4E;--green-lo:rgba(25,122,78,.07);
    --blue:#1A5FCC;--blue-lo:rgba(26,95,204,.07);
    --text:#14110D;--text2:#44403A;--text3:#807A72;
  }
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:var(--sans);font-size:15px;line-height:1.65;-webkit-font-smoothing:antialiased}
a{color:var(--blue);text-decoration:none}
/* NAV */
nav{background:var(--surface);border-bottom:1px solid var(--border);padding:0 24px;display:flex;align-items:center;justify-content:space-between;height:56px;position:sticky;top:0;z-index:100}
.logo{font-size:17px;font-weight:700;letter-spacing:-.02em;color:var(--text)}
.logo span{color:var(--gold)}
.nav-badge{font-family:var(--mono);font-size:10px;background:var(--green-lo);color:var(--green);border:1px solid rgba(38,194,116,.2);border-radius:4px;padding:3px 8px;letter-spacing:.06em}
/* HERO */
.hero{text-align:center;padding:72px 24px 48px;max-width:740px;margin:0 auto}
.hero-badge{display:inline-flex;align-items:center;gap:8px;font-family:var(--mono);font-size:11px;background:var(--gold-lo);color:var(--gold2);border:1px solid rgba(212,148,30,.2);border-radius:20px;padding:5px 14px;margin-bottom:24px;letter-spacing:.08em}
.hero-badge::before{content:'';width:6px;height:6px;border-radius:50%;background:var(--gold);box-shadow:0 0 8px var(--gold);animation:blink 2s ease-in-out infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.3}}
@media(prefers-reduced-motion:reduce){.hero-badge::before{animation:none}}
h1{font-size:clamp(28px,5vw,48px);font-weight:800;letter-spacing:-.03em;line-height:1.1;text-wrap:balance;margin-bottom:16px}
h1 .accent{color:var(--gold)}
.hero-sub{font-size:17px;color:var(--text2);max-width:52ch;margin:0 auto 32px;line-height:1.6;text-wrap:balance}
.trial-note{font-family:var(--mono);font-size:12px;color:var(--text3);margin-top:12px;letter-spacing:.04em}
/* MAIN TOOL */
.tool-wrap{max-width:820px;margin:0 auto;padding:0 16px 80px}
.tool-card{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:28px}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:600px){.form-grid{grid-template-columns:1fr}}
.field{display:flex;flex-direction:column;gap:6px}
.field.full{grid-column:1/-1}
label{font-family:var(--mono);font-size:11px;color:var(--text3);letter-spacing:.08em;text-transform:uppercase;font-weight:700}
input,select,textarea{background:var(--card2);border:1px solid var(--border2);border-radius:6px;color:var(--text);font-family:var(--sans);font-size:14px;padding:10px 14px;width:100%;outline:none;transition:border-color .15s}
input:focus,select:focus,textarea:focus{border-color:var(--gold)}
select option{background:var(--card)}
.email-row{display:flex;gap:10px;margin-top:14px;align-items:flex-end}
.email-row .field{flex:1}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;font-family:var(--sans);font-size:14px;font-weight:700;padding:12px 24px;border:none;border-radius:7px;cursor:pointer;transition:all .15s;white-space:nowrap}
.btn-primary{background:var(--gold);color:#07090F}
.btn-primary:hover{background:var(--gold2);transform:translateY(-1px)}
.btn-primary:disabled{opacity:.5;cursor:not-allowed;transform:none}
/* RESULT */
.result-card{background:var(--card);border:1px solid var(--border);border-left:3px solid var(--green);border-radius:var(--r);padding:24px;margin-top:20px;display:none}
.result-card.visible{display:block;animation:fadeIn .3s ease}
@keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
.result-section{margin-bottom:20px}
.result-label{font-family:var(--mono);font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--text3);font-weight:700;margin-bottom:8px;display:flex;align-items:center;gap:8px}
.result-label::after{content:'';flex:1;height:1px;background:var(--border2)}
.result-value{font-size:14px;color:var(--text2);line-height:1.7;white-space:pre-wrap}
.result-value.title-val{font-size:17px;font-weight:700;color:var(--text);letter-spacing:-.01em}
.result-value.meta-val{font-family:var(--mono);font-size:12px;color:var(--blue)}
.tags-row{display:flex;flex-wrap:wrap;gap:6px}
.tag{font-family:var(--mono);font-size:11px;background:var(--blue-lo);color:var(--blue);border:1px solid rgba(75,159,255,.18);border-radius:4px;padding:3px 8px}
.bullets{list-style:none;display:flex;flex-direction:column;gap:6px}
.bullets li{font-size:14px;color:var(--text2);line-height:1.5}
.copy-btn{font-family:var(--mono);font-size:10px;background:var(--card2);border:1px solid var(--border2);color:var(--text3);border-radius:4px;padding:3px 8px;cursor:pointer;float:right;margin-left:8px;letter-spacing:.05em}
.copy-btn:hover{border-color:var(--gold);color:var(--gold)}
/* LOADING */
.loader{display:none;justify-content:center;align-items:center;gap:12px;padding:32px;color:var(--text3);font-family:var(--mono);font-size:13px}
.loader.visible{display:flex}
.spinner{width:20px;height:20px;border:2px solid var(--border);border-top-color:var(--gold);border-radius:50%;animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
/* PAYWALL */
.paywall{background:var(--card);border:1px solid var(--border);border-top:2px solid var(--gold);border-radius:var(--r);padding:28px;margin-top:20px;text-align:center;display:none}
.paywall.visible{display:block}
.paywall h3{font-size:20px;font-weight:700;margin-bottom:8px}
.paywall p{color:var(--text2);font-size:14px;margin-bottom:24px;max-width:44ch;margin-left:auto;margin-right:auto}
.plan-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px}
@media(max-width:500px){.plan-grid{grid-template-columns:1fr}}
.plan-box{background:var(--card2);border:1px solid var(--border2);border-radius:8px;padding:18px;text-align:left}
.plan-box.popular{border-color:rgba(212,148,30,.35);background:var(--gold-lo)}
.plan-name{font-weight:700;font-size:15px;margin-bottom:4px}
.plan-price{font-family:var(--mono);font-size:22px;font-weight:700;color:var(--gold);margin-bottom:10px}
.plan-price span{font-size:13px;color:var(--text3)}
.plan-features{list-style:none;display:flex;flex-direction:column;gap:5px;margin-bottom:14px}
.plan-features li{font-size:13px;color:var(--text2)}
.plan-features li::before{content:'✓ ';color:var(--green)}
.btn-plan{width:100%;padding:10px;font-size:13px}
/* PRICING SECTION */
.pricing-section{max-width:820px;margin:40px auto;padding:0 16px}
.section-title{font-size:22px;font-weight:700;letter-spacing:-.02em;text-align:center;margin-bottom:6px}
.section-sub{color:var(--text2);text-align:center;font-size:14px;margin-bottom:28px}
/* ERROR */
.error-box{background:rgba(224,69,69,.08);border:1px solid rgba(224,69,69,.2);border-radius:6px;padding:12px 16px;font-size:13px;color:#E04545;margin-top:12px;display:none}
.error-box.visible{display:block}
/* COUNTER */
.usage-counter{display:flex;align-items:center;gap:8px;font-family:var(--mono);font-size:11px;color:var(--text3);margin-top:12px}
.usage-dot{width:8px;height:8px;border-radius:50%;background:var(--green)}
.usage-dot.warn{background:var(--gold)}
.usage-dot.empty{background:#E04545}
</style>
</head>
<body>

<nav>
  <div class="logo">Shop<span>Text</span>.ai</div>
  <div class="nav-badge">✨ Powered by Claude AI</div>
</nav>

<div class="hero">
  <div class="hero-badge">🛒 Für Shopify-Händler in DACH</div>
  <h1>Professionelle <span class="accent">Produkttexte</span><br>auf Knopfdruck</h1>
  <p class="hero-sub">KI-generierte, SEO-optimierte Beschreibungen auf Deutsch — inkl. Meta-Titel, Tags und Bulletpoints. In 15 Sekunden fertig.</p>
  <p class="trial-note">3 KOSTENLOSE TEXTE — KEINE KREDITKARTE NÖTIG</p>
</div>

<div class="tool-wrap">
  <div class="tool-card">
    <div class="form-grid">
      <div class="field full">
        <label>Produktname *</label>
        <input type="text" id="pname" placeholder="z.B. Kabellose Bluetooth-Kopfhörer Pro X200" maxlength="120">
      </div>
      <div class="field">
        <label>Keywords (komma-getrennt)</label>
        <input type="text" id="pkw" placeholder="z.B. noise cancelling, sport, kabellos">
      </div>
      <div class="field">
        <label>Produktkategorie</label>
        <input type="text" id="ptype" placeholder="z.B. Elektronik, Mode, Haushalt">
      </div>
      <div class="field">
        <label>Tonalität</label>
        <select id="ptone">
          <option value="professionell">Professionell & seriös</option>
          <option value="modern">Modern & jugendlich</option>
          <option value="luxus">Luxus & premium</option>
          <option value="freundlich">Herzlich & nahbar</option>
        </select>
      </div>
    </div>
    <div class="email-row">
      <div class="field">
        <label>Deine E-Mail (für kostenloses Konto)</label>
        <input type="email" id="pemail" placeholder="deine@email.de">
      </div>
      <button class="btn btn-primary" id="generateBtn" onclick="generateText()">
        ✨ Text generieren
      </button>
    </div>
    <div class="usage-counter" id="usageCounter" style="display:none">
      <div class="usage-dot" id="usageDot"></div>
      <span id="usageText"></span>
    </div>
    <div class="error-box" id="errorBox"></div>
  </div>

  <div class="loader" id="loader">
    <div class="spinner"></div>
    Claude KI generiert deinen Text…
  </div>

  <div class="result-card" id="resultCard">
    <div class="result-section">
      <div class="result-label">Produkttitel <button class="copy-btn" onclick="copyField('rTitle')">Kopieren</button></div>
      <div class="result-value title-val" id="rTitle"></div>
    </div>
    <div class="result-section">
      <div class="result-label">Produktbeschreibung <button class="copy-btn" onclick="copyField('rDesc')">Kopieren</button></div>
      <div class="result-value" id="rDesc"></div>
    </div>
    <div class="result-section">
      <div class="result-label">Meta-Title <button class="copy-btn" onclick="copyField('rMetaTitle')">Kopieren</button></div>
      <div class="result-value meta-val" id="rMetaTitle"></div>
    </div>
    <div class="result-section">
      <div class="result-label">Meta-Description <button class="copy-btn" onclick="copyField('rMetaDesc')">Kopieren</button></div>
      <div class="result-value meta-val" id="rMetaDesc"></div>
    </div>
    <div class="result-section">
      <div class="result-label">Tags</div>
      <div class="tags-row" id="rTags"></div>
    </div>
    <div class="result-section">
      <div class="result-label">Bullet Points <button class="copy-btn" onclick="copyBullets()">Kopieren</button></div>
      <ul class="bullets" id="rBullets"></ul>
    </div>
  </div>

  <div class="paywall" id="paywallCard">
    <h3>🔒 Kostenlose Texte verbraucht</h3>
    <p>Upgrade für unlimitierte KI-Produkttexte, direkte Shopify-Synchronisation und Batch-Generierung.</p>
    <div class="plan-grid">
      <div class="plan-box">
        <div class="plan-name">Starter</div>
        <div class="plan-price">€49<span>/Monat</span></div>
        <ul class="plan-features">
          <li>50 Texte pro Monat</li>
          <li>Alle Tonalitäten</li>
          <li>Meta-Texte inklusive</li>
          <li>E-Mail Support</li>
        </ul>
        <button class="btn btn-primary btn-plan" onclick="startCheckout('starter')">Starter wählen</button>
      </div>
      <div class="plan-box popular">
        <div class="plan-name">Pro ⭐</div>
        <div class="plan-price">€99<span>/Monat</span></div>
        <ul class="plan-features">
          <li>Unlimited Texte</li>
          <li>Shopify-Direktimport</li>
          <li>Batch: 50 Produkte auf einmal</li>
          <li>Priority Support</li>
        </ul>
        <button class="btn btn-primary btn-plan" onclick="startCheckout('pro')">Pro wählen</button>
      </div>
    </div>
  </div>
</div>

<script>
let lastResult = null;

async function generateText() {
  const name = document.getElementById('pname').value.trim();
  const email = document.getElementById('pemail').value.trim();
  if (!name) { showError('Bitte gib einen Produktnamen ein.'); return; }

  hideError();
  document.getElementById('resultCard').classList.remove('visible');
  document.getElementById('paywallCard').classList.remove('visible');
  document.getElementById('loader').classList.add('visible');
  document.getElementById('generateBtn').disabled = true;

  try {
    const resp = await fetch('/api/shoptext/generate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        product_name: name,
        keywords: document.getElementById('pkw').value.trim(),
        product_type: document.getElementById('ptype').value.trim(),
        tone: document.getElementById('ptone').value,
        email: email,
      })
    });
    const data = await resp.json();

    document.getElementById('loader').classList.remove('visible');

    if (data.paywall) {
      document.getElementById('paywallCard').classList.add('visible');
      return;
    }
    if (!resp.ok || data.error) {
      showError(data.error || 'Fehler bei der Generierung. Bitte erneut versuchen.');
      return;
    }

    lastResult = data.result;
    renderResult(data.result);
    updateUsageCounter(data.usage);
  } catch(e) {
    document.getElementById('loader').classList.remove('visible');
    showError('Netzwerkfehler. Bitte prüfe deine Verbindung.');
  } finally {
    document.getElementById('generateBtn').disabled = false;
  }
}

function renderResult(r) {
  document.getElementById('rTitle').textContent = r.title || '';
  document.getElementById('rDesc').textContent = r.description || '';
  document.getElementById('rMetaTitle').textContent = r.meta_title || '';
  document.getElementById('rMetaDesc').textContent = r.meta_description || '';

  const tagsEl = document.getElementById('rTags');
  tagsEl.innerHTML = '';
  (r.tags || []).forEach(t => {
    const span = document.createElement('span');
    span.className = 'tag';
    span.textContent = t;
    tagsEl.appendChild(span);
  });

  const bulletsEl = document.getElementById('rBullets');
  bulletsEl.innerHTML = '';
  (r.bullet_points || []).forEach(b => {
    const li = document.createElement('li');
    li.textContent = b;
    bulletsEl.appendChild(li);
  });

  document.getElementById('resultCard').classList.add('visible');
  document.getElementById('resultCard').scrollIntoView({behavior:'smooth', block:'nearest'});
}

function updateUsageCounter(usage) {
  if (!usage) return;
  const c = document.getElementById('usageCounter');
  const dot = document.getElementById('usageDot');
  const txt = document.getElementById('usageText');
  c.style.display = 'flex';
  if (usage.plan !== 'free') {
    dot.className = 'usage-dot';
    txt.textContent = 'Unlimited · ' + usage.plan + ' Plan aktiv';
  } else if (usage.remaining > 1) {
    dot.className = 'usage-dot';
    txt.textContent = usage.remaining + ' kostenlose Texte verbleibend';
  } else if (usage.remaining === 1) {
    dot.className = 'usage-dot warn';
    txt.textContent = 'Letzter kostenloser Text!';
  } else {
    dot.className = 'usage-dot empty';
    txt.textContent = 'Keine kostenlosen Texte mehr — Upgrade für unlimitierten Zugang';
  }
}

async function startCheckout(plan) {
  const email = document.getElementById('pemail').value.trim();
  const resp = await fetch('/api/shoptext/checkout', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({plan, email})
  });
  const data = await resp.json();
  if (data.url) {
    window.location.href = data.url;
  } else {
    showError('Checkout-Fehler: ' + (data.error || 'Unbekannter Fehler'));
  }
}

function copyField(id) {
  const el = document.getElementById(id);
  if (!el) return;
  navigator.clipboard.writeText(el.textContent).then(() => {
    const btn = el.parentElement.querySelector('.copy-btn');
    if (btn) { btn.textContent = 'Kopiert!'; setTimeout(() => btn.textContent = 'Kopieren', 1500); }
  });
}

function copyBullets() {
  const items = document.querySelectorAll('#rBullets li');
  const text = Array.from(items).map(li => li.textContent).join('\\n');
  navigator.clipboard.writeText(text).then(() => {
    const btn = document.querySelector('#rBullets').parentElement.querySelector('.copy-btn');
    if (btn) { btn.textContent = 'Kopiert!'; setTimeout(() => btn.textContent = 'Kopieren', 1500); }
  });
}

function showError(msg) {
  const box = document.getElementById('errorBox');
  box.textContent = msg;
  box.classList.add('visible');
}
function hideError() {
  document.getElementById('errorBox').classList.remove('visible');
}

document.getElementById('pname').addEventListener('keypress', e => {
  if (e.key === 'Enter') generateText();
});
</script>
</body>
</html>"""

SUCCESS_HTML = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Erfolgreich abonniert — ShopText.ai</title>
<style>
body{background:#07090F;color:#EAE5DB;font-family:-apple-system,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;text-align:center;padding:24px}
.box{max-width:480px}
.icon{font-size:64px;margin-bottom:24px}
h1{font-size:28px;font-weight:700;margin-bottom:12px}
p{color:#9AA4B8;margin-bottom:24px}
a{display:inline-block;background:#D4941E;color:#07090F;font-weight:700;padding:12px 28px;border-radius:7px;text-decoration:none;font-size:15px}
a:hover{background:#F0AB28}
</style>
</head>
<body>
<div class="box">
  <div class="icon">🎉</div>
  <h1>Willkommen bei ShopText.ai!</h1>
  <p>Dein Abo ist aktiv. Starte sofort mit unbegrenzten KI-Produkttexten für deinen Shopify-Shop.</p>
  <a href="/shoptext">Jetzt Texte generieren →</a>
</div>
</body>
</html>"""


async def handle_shoptext_landing(req: web.Request) -> web.Response:
    return web.Response(text=LANDING_HTML, content_type="text/html")


async def handle_shoptext_generate(req: web.Request) -> web.Response:
    try:
        body = await req.json()
    except Exception:
        return web.json_response({"error": "Ungültiges JSON"}, status=400)

    product_name = (body.get("product_name") or "").strip()
    if not product_name:
        return web.json_response({"error": "Produktname fehlt"}, status=400)

    keywords   = (body.get("keywords") or "").strip()
    ptype      = (body.get("product_type") or "").strip()
    tone       = (body.get("tone") or "professionell").strip()
    email      = (body.get("email") or "").strip().lower()

    # Identifier: email or IP
    identifier = email or req.headers.get("X-Forwarded-For", req.remote or "anon").split(",")[0].strip()

    try:
        from modules.shoptext_ai import get_usage, generate_product_text, record_generation
    except ImportError as e:
        return web.json_response({"error": f"Modul-Import fehlgeschlagen: {e}"}, status=500)

    usage = get_usage(identifier)
    if not usage["can_generate"]:
        return web.json_response({"paywall": True, "usage": usage})

    try:
        result = await generate_product_text(product_name, keywords, ptype, tone)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

    record_generation(identifier, product_name, keywords, result)
    updated_usage = get_usage(identifier)

    return web.json_response({"ok": True, "result": result, "usage": updated_usage})


async def handle_shoptext_checkout(req: web.Request) -> web.Response:
    try:
        body = await req.json()
    except Exception:
        return web.json_response({"error": "Ungültiges JSON"}, status=400)

    plan  = (body.get("plan") or "starter").strip()
    email = (body.get("email") or "").strip()

    base_url = f"https://{req.headers.get('Host', 'localhost')}"
    forwarded = req.headers.get("X-Forwarded-Proto")
    if forwarded:
        base_url = f"{forwarded}://{req.headers.get('Host', 'localhost')}"

    try:
        from modules.shoptext_ai import create_checkout_session
        url = create_checkout_session(plan, email, base_url)
        return web.json_response({"ok": True, "url": url})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_shoptext_success(req: web.Request) -> web.Response:
    session_id = req.rel_url.query.get("session_id", "")
    plan = req.rel_url.query.get("plan", "starter")

    if session_id:
        try:
            from modules.shoptext_ai import activate_plan
            activate_plan(session_id, plan, stripe_sub=session_id)
        except Exception:
            pass

    return web.Response(text=SUCCESS_HTML, content_type="text/html")


async def handle_shoptext_stats(req: web.Request) -> web.Response:
    try:
        from modules.shoptext_ai import get_stats
        return web.json_response(get_stats())
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)
