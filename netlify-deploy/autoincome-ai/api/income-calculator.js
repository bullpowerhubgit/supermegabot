// KI Einkommens-Rechner — Lead-Gen Tool
// Serves interactive HTML page at /rechner
// Viral tool: users calculate their AI income potential, then sign up to see full plan

const PRODUCT_URL = 'https://www.checkout-ds24.com/product/668035';
const UPSELL_URL = 'https://www.checkout-ds24.com/product/704677';
const KLAVIYO_LIST_ID = 'Xwxq6V';
const KLAVIYO_ACCOUNT_ID = 'VaCYq3';

export default function handler(req, res) {
  const html = `<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>KI Einkommens-Rechner 2026 — Was kannst du mit KI verdienen?</title>
  <meta name="description" content="Berechne kostenlos dein KI-Einkommen-Potential 2026. Wie viel passives Einkommen kannst du mit KI-Tools realistisch verdienen? Kostenloser Rechner auf Deutsch."/>
  <link rel="canonical" href="https://autoincome-ai.vercel.app/rechner"/>
  <meta property="og:title" content="KI Einkommens-Rechner 2026 — Dein Einkommen-Potential"/>
  <meta property="og:description" content="Berechne in 60 Sekunden dein realistisches KI-Einkommen. Kostenlos, auf Deutsch, sofortige Ergebnisse."/>
  <meta property="og:url" content="https://autoincome-ai.vercel.app/rechner"/>
  <meta property="og:image" content="https://autoincome-ai.vercel.app/og-image.png"/>
  <script type="application/ld+json">{"@context":"https://schema.org","@type":"WebApplication","name":"KI Einkommens-Rechner 2026","description":"Kostenloser Rechner für KI-Einkommen-Potential","url":"https://autoincome-ai.vercel.app/rechner","applicationCategory":"FinanceApplication","inLanguage":"de","offers":{"@type":"Offer","price":"0","priceCurrency":"EUR"}}</script>
  <style>
    *{margin:0;padding:0;box-sizing:border-box}
    body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f0f1a;color:#e2e8f0;min-height:100vh}
    nav{background:rgba(15,15,26,.95);padding:14px 20px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid rgba(255,255,255,.05);position:sticky;top:0;z-index:100;backdrop-filter:blur(10px)}
    .logo{font-size:1rem;font-weight:800;color:white;text-decoration:none}.logo span{color:#7c3aed}
    .nav-cta{background:linear-gradient(135deg,#7c3aed,#5b21b6);color:white;padding:7px 18px;border-radius:50px;font-size:.82rem;font-weight:700;text-decoration:none}
    .hero{background:linear-gradient(135deg,#1a1a2e,#16213e);padding:48px 20px 36px;text-align:center;border-bottom:1px solid rgba(255,255,255,.05)}
    .hero h1{font-size:clamp(1.7rem,4vw,2.8rem);font-weight:900;margin-bottom:12px;line-height:1.2}
    .hero p{color:#94a3b8;font-size:1.05rem;max-width:600px;margin:0 auto}
    .badge{display:inline-flex;align-items:center;gap:6px;background:rgba(124,58,237,.15);border:1px solid rgba(124,58,237,.4);color:#a78bfa;padding:5px 14px;border-radius:99px;font-size:.8rem;font-weight:700;margin-bottom:16px}
    .container{max-width:720px;margin:0 auto;padding:36px 20px}
    .step{display:none;animation:fadeIn .3s ease}
    .step.active{display:block}
    @keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
    .step-header{margin-bottom:24px}
    .step-num{font-size:.75rem;font-weight:700;color:#7c3aed;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px}
    .step-q{font-size:1.4rem;font-weight:800;color:#f1f5f9;line-height:1.3}
    .options{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:28px}
    @media(max-width:480px){.options{grid-template-columns:1fr}}
    .opt{background:rgba(255,255,255,.03);border:2px solid rgba(255,255,255,.08);border-radius:12px;padding:18px;cursor:pointer;transition:all .2s;text-align:left}
    .opt:hover{border-color:#7c3aed;background:rgba(124,58,237,.06)}
    .opt.selected{border-color:#7c3aed;background:rgba(124,58,237,.12)}
    .opt-title{font-size:1rem;font-weight:700;color:#e2e8f0;margin-bottom:4px}
    .opt-desc{font-size:.83rem;color:#64748b}
    .opt-emoji{font-size:1.6rem;margin-bottom:8px;display:block}
    .progress{background:rgba(255,255,255,.06);height:4px;border-radius:99px;margin-bottom:32px;overflow:hidden}
    .progress-bar{height:100%;background:linear-gradient(90deg,#7c3aed,#5b21b6);border-radius:99px;transition:width .4s ease}
    .btn{background:linear-gradient(135deg,#7c3aed,#5b21b6);color:white;border:none;padding:14px 36px;border-radius:50px;font-size:1rem;font-weight:700;cursor:pointer;width:100%;transition:opacity .2s}
    .btn:hover{opacity:.9}
    .btn:disabled{opacity:.4;cursor:not-allowed}
    .result-box{background:linear-gradient(135deg,rgba(124,58,237,.12),rgba(91,33,182,.06));border:2px solid #7c3aed;border-radius:20px;padding:32px;text-align:center;margin:24px 0}
    .result-label{font-size:.8rem;color:#a78bfa;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px}
    .result-amount{font-size:3.5rem;font-weight:900;color:white;line-height:1;margin-bottom:4px}
    .result-suffix{font-size:1rem;color:#94a3b8;margin-bottom:16px}
    .timeline{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:24px 0}
    .tl-item{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-radius:10px;padding:14px;text-align:center}
    .tl-period{font-size:.75rem;color:#64748b;margin-bottom:4px;font-weight:600}
    .tl-amount{font-size:1.3rem;font-weight:800;color:#e2e8f0}
    .email-gate{background:rgba(16,185,129,.06);border:2px solid rgba(16,185,129,.3);border-radius:16px;padding:28px;text-align:center;margin:24px 0}
    .email-gate h3{font-size:1.2rem;font-weight:800;color:#10b981;margin-bottom:8px}
    .email-gate p{color:#94a3b8;font-size:.9rem;margin-bottom:18px}
    .email-form{display:flex;gap:8px;max-width:420px;margin:0 auto;flex-wrap:wrap;justify-content:center}
    .email-form input{flex:1;min-width:200px;padding:12px 16px;border-radius:8px;border:1px solid rgba(255,255,255,.15);background:rgba(255,255,255,.06);color:#e2e8f0;font-size:.95rem;outline:none}
    .email-form input:focus{border-color:#10b981}
    .email-form button{background:#10b981;color:white;border:none;padding:12px 24px;border-radius:8px;font-weight:700;cursor:pointer;font-size:.95rem;white-space:nowrap}
    .plan-grid{display:grid;grid-template-columns:1fr;gap:12px;margin:20px 0}
    .plan-item{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.07);border-radius:10px;padding:16px;display:flex;gap:12px;align-items:flex-start}
    .plan-step{background:rgba(124,58,237,.2);color:#a78bfa;width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:.82rem;font-weight:800;flex-shrink:0}
    .plan-text{flex:1}
    .plan-title{font-size:.95rem;font-weight:700;color:#e2e8f0;margin-bottom:3px}
    .plan-desc{font-size:.82rem;color:#64748b}
    .products{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:24px 0}
    @media(max-width:480px){.products{grid-template-columns:1fr}}
    .product-card{border-radius:12px;padding:20px;text-align:center}
    .product-card.starter{background:rgba(255,255,255,.04);border:2px solid rgba(255,255,255,.1)}
    .product-card.pro{background:linear-gradient(135deg,#1e1b4b,#0f0a1f);border:2px solid #7c3aed}
    .product-card .p-badge{font-size:.7rem;font-weight:800;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px}
    .product-card.starter .p-badge{color:#94a3b8}
    .product-card.pro .p-badge{color:#a78bfa}
    .product-card h4{font-size:1rem;font-weight:800;margin-bottom:4px}
    .product-card.starter h4{color:#e2e8f0}
    .product-card.pro h4{color:white}
    .product-card .p-price{font-size:1.8rem;font-weight:900;margin:8px 0}
    .product-card.starter .p-price{color:#e2e8f0}
    .product-card.pro .p-price{color:white}
    .product-card .p-desc{font-size:.8rem;color:#64748b;margin-bottom:14px}
    .product-card.pro .p-desc{color:#94a3b8}
    .product-card a{display:block;padding:10px;border-radius:25px;font-size:.85rem;font-weight:700;text-decoration:none}
    .product-card.starter a{background:rgba(124,58,237,.2);color:#a78bfa}
    .product-card.pro a{background:linear-gradient(135deg,#7c3aed,#5b21b6);color:white}
    .share-box{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.07);border-radius:12px;padding:20px;text-align:center;margin:20px 0}
    .share-box p{color:#94a3b8;font-size:.88rem;margin-bottom:12px}
    .share-btns{display:flex;gap:8px;justify-content:center;flex-wrap:wrap}
    .share-btn{padding:8px 18px;border-radius:20px;font-size:.82rem;font-weight:700;cursor:pointer;border:none;text-decoration:none;display:inline-block}
    footer{background:rgba(0,0,0,.3);padding:28px 20px;text-align:center;color:#475569;font-size:.82rem;border-top:1px solid rgba(255,255,255,.05);margin-top:50px}
    footer a{color:#64748b;text-decoration:none;margin:0 8px}
    .disclaimer{color:#475569;font-size:.75rem;text-align:center;margin-top:12px;font-style:italic}
  </style>
</head>
<body>
<nav>
  <a href="/" class="logo">AI<span>Income</span></a>
  <a href="${PRODUCT_URL}" class="nav-cta">Blueprint €37 →</a>
</nav>

<div class="hero">
  <div class="badge">🧮 Kostenloser KI-Einkommens-Rechner 2026</div>
  <h1>Was kannst du mit KI<br>wirklich verdienen?</h1>
  <p>Beantworte 3 Fragen — wir berechnen dein realistisches Einkommen-Potential in 60 Sekunden.</p>
</div>

<div class="container">
  <div class="progress"><div class="progress-bar" id="progress-bar" style="width:0%"></div></div>

  <!-- Step 1 -->
  <div class="step active" id="step-1">
    <div class="step-header">
      <div class="step-num">Frage 1 von 3</div>
      <div class="step-q">Wie viel Zeit kannst du pro Woche investieren?</div>
    </div>
    <div class="options">
      <div class="opt" onclick="select(1,'5h')" data-step="1" data-val="5h">
        <span class="opt-emoji">⏱️</span>
        <div class="opt-title">1–5 Stunden</div>
        <div class="opt-desc">Nebenbei, neben Job/Studium</div>
      </div>
      <div class="opt" onclick="select(1,'10h')" data-step="1" data-val="10h">
        <span class="opt-emoji">🕐</span>
        <div class="opt-title">5–10 Stunden</div>
        <div class="opt-desc">Ernsthaftes Nebenprojekt</div>
      </div>
      <div class="opt" onclick="select(1,'20h')" data-step="1" data-val="20h">
        <span class="opt-emoji">💼</span>
        <div class="opt-title">10–20 Stunden</div>
        <div class="opt-desc">Halbtags-Fokus</div>
      </div>
      <div class="opt" onclick="select(1,'40h')" data-step="1" data-val="40h">
        <span class="opt-emoji">🚀</span>
        <div class="opt-title">20+ Stunden</div>
        <div class="opt-desc">Vollzeit oder fast</div>
      </div>
    </div>
    <button class="btn" id="btn-1" disabled onclick="nextStep(2)">Weiter →</button>
  </div>

  <!-- Step 2 -->
  <div class="step" id="step-2">
    <div class="step-header">
      <div class="step-num">Frage 2 von 3</div>
      <div class="step-q">Welche KI-Methode interessiert dich am meisten?</div>
    </div>
    <div class="options">
      <div class="opt" onclick="select(2,'affiliate')" data-step="2" data-val="affiliate">
        <span class="opt-emoji">🔗</span>
        <div class="opt-title">Affiliate Marketing</div>
        <div class="opt-desc">Provision für fremde Produkte</div>
      </div>
      <div class="opt" onclick="select(2,'digital')" data-step="2" data-val="digital">
        <span class="opt-emoji">📦</span>
        <div class="opt-title">Digitale Produkte</div>
        <div class="opt-desc">Eigene eBooks / Blueprints</div>
      </div>
      <div class="opt" onclick="select(2,'freelance')" data-step="2" data-val="freelance">
        <span class="opt-emoji">💻</span>
        <div class="opt-title">KI-Freelancing</div>
        <div class="opt-desc">Texte, Code, Design per KI</div>
      </div>
      <div class="opt" onclick="select(2,'shop')" data-step="2" data-val="shop">
        <span class="opt-emoji">🛍️</span>
        <div class="opt-title">Shopify / Drop-Shipping</div>
        <div class="opt-desc">Online-Shop mit KI-Automation</div>
      </div>
    </div>
    <button class="btn" id="btn-2" disabled onclick="nextStep(3)">Weiter →</button>
  </div>

  <!-- Step 3 -->
  <div class="step" id="step-3">
    <div class="step-header">
      <div class="step-num">Frage 3 von 3</div>
      <div class="step-q">Was ist dein Einkommens-Ziel?</div>
    </div>
    <div class="options">
      <div class="opt" onclick="select(3,'500')" data-step="3" data-val="500">
        <span class="opt-emoji">🌱</span>
        <div class="opt-title">€500 / Monat</div>
        <div class="opt-desc">Solide Basis, realistisch</div>
      </div>
      <div class="opt" onclick="select(3,'1000')" data-step="3" data-val="1000">
        <span class="opt-emoji">💶</span>
        <div class="opt-title">€1.000 / Monat</div>
        <div class="opt-desc">Nebeneinkommen verdoppeln</div>
      </div>
      <div class="opt" onclick="select(3,'2000')" data-step="3" data-val="2000">
        <span class="opt-emoji">🏆</span>
        <div class="opt-title">€2.000 / Monat</div>
        <div class="opt-desc">Finanziell unabhängig werden</div>
      </div>
      <div class="opt" onclick="select(3,'5000')" data-step="3" data-val="5000">
        <span class="opt-emoji">🚀</span>
        <div class="opt-title">€5.000+ / Monat</div>
        <div class="opt-desc">Vollzeit-Online-Business</div>
      </div>
    </div>
    <button class="btn" id="btn-3" disabled onclick="showResult()">Ergebnis berechnen ✨</button>
  </div>

  <!-- Result -->
  <div class="step" id="step-result">
    <h2 style="font-size:1.4rem;font-weight:800;color:#f1f5f9;margin-bottom:6px;text-align:center">Dein KI-Einkommens-Potential</h2>
    <p style="color:#64748b;font-size:.88rem;text-align:center;margin-bottom:20px">Basierend auf deinen Antworten — realistische Schätzung</p>

    <div class="result-box">
      <div class="result-label">📈 Realistisches Ziel bis Monat 6</div>
      <div class="result-amount" id="res-amount">€0</div>
      <div class="result-suffix">pro Monat — passives KI-Einkommen</div>
      <div class="timeline">
        <div class="tl-item"><div class="tl-period">Monat 1–2</div><div class="tl-amount" id="tl1">—</div></div>
        <div class="tl-item"><div class="tl-period">Monat 3–4</div><div class="tl-amount" id="tl2">—</div></div>
        <div class="tl-item"><div class="tl-period">Monat 5–6</div><div class="tl-amount" id="tl3">—</div></div>
      </div>
    </div>

    <!-- Email gate for detailed plan -->
    <div class="email-gate" id="email-gate">
      <h3>🎯 Dein persönlicher 90-Tage-Plan</h3>
      <p>Trage deine E-Mail ein und erhalte deinen konkreten Schritt-für-Schritt-Plan — kostenlos, auf Deutsch, sofort in der Inbox.</p>
      <form class="email-form" action="https://manage.kmail-lists.com/subscriptions/subscribe" method="POST" target="_blank" onsubmit="onEmailSubmit(event)">
        <input type="hidden" name="g" value="${KLAVIYO_LIST_ID}"/>
        <input type="hidden" name="a" value="${KLAVIYO_ACCOUNT_ID}"/>
        <input type="hidden" name="$fields" value="$source"/>
        <input type="hidden" name="$source" value="rechner"/>
        <input type="email" name="email" id="gate-email" placeholder="deine@email.de" required/>
        <button type="submit">Plan anzeigen →</button>
      </form>
      <p style="font-size:.75rem;color:#475569;margin-top:10px">Kein Spam. Abmeldung jederzeit. Sofortzugang.</p>
    </div>

    <!-- Plan (hidden until email submitted) -->
    <div id="plan-section" style="display:none">
      <h3 style="font-size:1.1rem;font-weight:800;color:#f1f5f9;margin:24px 0 12px">Dein persönlicher Aktionsplan</h3>
      <div class="plan-grid" id="plan-grid"></div>

      <div class="products">
        <div class="product-card starter">
          <div class="p-badge">Starter</div>
          <h4>AI Income Machine Blueprint</h4>
          <div class="p-price">€37</div>
          <div class="p-desc">90-Tage-Plan · PDF · Sofortzugang</div>
          <a href="${PRODUCT_URL}" target="_blank">Blueprint kaufen →</a>
        </div>
        <div class="product-card pro">
          <div class="p-badge">⭐ Empfohlen</div>
          <h4>SuperMegaBot System</h4>
          <div class="p-price">€97 <span style="font-size:.9rem;color:#475569;text-decoration:line-through;font-weight:400">€297</span></div>
          <div class="p-desc">Vollautomatik · Code + Deploy · 1-Click</div>
          <a href="${UPSELL_URL}" target="_blank">Vollsystem holen →</a>
        </div>
      </div>

      <div class="share-box">
        <p>Teile deinen Rechner — hilf anderen ihr Potential zu entdecken:</p>
        <div class="share-btns">
          <a class="share-btn" style="background:rgba(10,102,194,.2);color:#93c5fd" href="https://www.linkedin.com/sharing/share-offsite/?url=https%3A%2F%2Fautoincome-ai.vercel.app%2Frechner" target="_blank" rel="noopener">LinkedIn teilen</a>
          <a class="share-btn" style="background:rgba(29,161,242,.15);color:#93c5fd" href="https://twitter.com/intent/tweet?text=Kostenloser+KI+Einkommens-Rechner+2026+%F0%9F%A4%96+Was+kannst+du+realistisch+verdienen%3F&url=https%3A%2F%2Fautoincome-ai.vercel.app%2Frechner" target="_blank" rel="noopener">Twitter teilen</a>
          <button class="share-btn" style="background:rgba(124,58,237,.2);color:#a78bfa" onclick="copyLink()">🔗 Link kopieren</button>
        </div>
      </div>

      <p class="disclaimer">Die Einkommensschätzungen basieren auf realistischen Durchschnittswerten aus dem deutschen Markt 2026. Individuelle Ergebnisse variieren je nach Aufwand, Strategie und Marktbedingungen. Keine Erfolgsgarantie.</p>
    </div>

    <div style="text-align:center;margin-top:20px">
      <button onclick="restart()" style="background:none;border:none;color:#475569;font-size:.85rem;cursor:pointer;text-decoration:underline">Neu berechnen</button>
    </div>
  </div>
</div>

<footer>
  <a href="/">Startseite</a>
  <a href="/blog">Blog</a>
  <a href="/affiliate.html">Affiliate</a>
  <p style="margin-top:10px">© 2026 AiiteC — Rudolf Sarkany &nbsp;|&nbsp; <a href="/impressum.html">Impressum</a></p>
</footer>

<script>
var answers = {};
var PLANS = {
  affiliate: [
    {t:'Woche 1–2: Digistore24 Konto erstellen',d:'Kostenlos anmelden, 15 Minuten. Direkte Zulassung als Affiliate für Blueprint + SuperMegaBot.'},
    {t:'Woche 3–4: Ersten Affiliate-Link teilen',d:'LinkedIn, WhatsApp-Gruppen, E-Mail-Liste. Ziel: 5 Shares pro Woche = erste Conversions.'},
    {t:'Monat 2: Content-System aufbauen',d:'3 LinkedIn-Posts/Woche über KI-Einkommen mit deinem Affiliate-Link in den Kommentaren.'},
    {t:'Monat 3+: Skalieren mit E-Mail-Liste',d:'Kostenloser Lead-Magnet → E-Mail-Sequenz → automatische Affiliate-Sales. Komplett passiv.'},
  ],
  digital: [
    {t:'Woche 1–2: Produkt-Idee validieren',d:'Keyword-Recherche mit kostenlosen Tools. Thema: KI-Tools, passives Einkommen, Automatisierung.'},
    {t:'Woche 3–4: Produkt mit KI erstellen',d:'eBook/Blueprint in 2–3 Tagen mit ChatGPT schreiben. Auf Digistore24 listen (kostenlos).'},
    {t:'Monat 2: Affiliate-Programm starten',d:'50% Provision anbieten. Affiliates bringen Traffic — du kassierst ohne Werbung.'},
    {t:'Monat 3+: Automation & Skalierung',d:'E-Mail-Sequenz, LinkedIn-Posts automatisch. Verkäufe laufen ohne tägliche Arbeit.'},
  ],
  freelance: [
    {t:'Woche 1: KI-Tool-Stack aufbauen',d:'ChatGPT + Claude für Texte, Midjourney für Bilder, GitHub Copilot für Code. Alles gratis starten.'},
    {t:'Woche 2–3: Fiverr/Upwork Profil erstellen',d:'3 Gigs mit KI-Beschleunigung: SEO-Texte, Social-Media-Posts, E-Mail-Kampagnen.'},
    {t:'Monat 2: Erste 5 Kunden gewinnen',d:'€25–75 pro Auftrag. Mit KI 3x schneller liefern als ohne = 3x mehr Umsatz pro Stunde.'},
    {t:'Monat 3+: Auf Retainer-Kunden umstellen',d:'€300–800/Monat pro Retainer-Klient. 5 Klienten = €1.500–4.000 monatlich.'},
  ],
  shop: [
    {t:'Woche 1–2: Shopify + Printify einrichten',d:'Kostenloser Trial. Print-on-Demand: kein Lager, kein Risiko. Produkte mit KI designen.'},
    {t:'Woche 3–4: KI-Produktbeschreibungen',d:'ChatGPT schreibt 50 Produktbeschreibungen in 2 Stunden. SEO-optimiert, konversionsstark.'},
    {t:'Monat 2: Erste Werbeanzeigen schalten',d:'€5/Tag auf Pinterest + TikTok = organische Reichweite. Erster Umsatz in Woche 3–6.'},
    {t:'Monat 3+: Automation mit SuperMegaBot',d:'Automatische Produktimporte, Preisoptimierung, Social-Posting. Hands-free E-Commerce.'},
  ],
};
var INCOME = {
  '5h':   {m1:'€0–25',  m2:'€50–150', m3:'€150–300', final:'€150–300'},
  '10h':  {m1:'€25–75', m2:'€100–250',m3:'€250–500', final:'€250–500'},
  '20h':  {m1:'€50–150',m2:'€200–500',m3:'€500–900', final:'€500–900'},
  '40h':  {m1:'€100–300',m2:'€400–900',m3:'€900–1.800',final:'€900–1.800'},
};

function select(step, val) {
  document.querySelectorAll('[data-step="'+step+'"]').forEach(function(el){el.classList.remove('selected')});
  var el = document.querySelector('[data-step="'+step+'"][data-val="'+val+'"]');
  if(el) el.classList.add('selected');
  answers['s'+step] = val;
  var btn = document.getElementById('btn-'+step);
  if(btn) btn.disabled = false;
}

function nextStep(n) {
  document.querySelectorAll('.step').forEach(function(s){s.classList.remove('active')});
  document.getElementById('step-'+n).classList.add('active');
  var pct = ((n-1)/3*100);
  document.getElementById('progress-bar').style.width = pct+'%';
  window.scrollTo({top:0,behavior:'smooth'});
}

function showResult() {
  var time = answers.s1 || '10h';
  var method = answers.s2 || 'affiliate';
  var inc = INCOME[time] || INCOME['10h'];
  document.getElementById('res-amount').textContent = inc.final;
  document.getElementById('tl1').textContent = inc.m1;
  document.getElementById('tl2').textContent = inc.m2;
  document.getElementById('tl3').textContent = inc.m3;
  document.querySelectorAll('.step').forEach(function(s){s.classList.remove('active')});
  document.getElementById('step-result').classList.add('active');
  document.getElementById('progress-bar').style.width = '100%';
  window.scrollTo({top:0,behavior:'smooth'});
  // Build plan
  var plans = PLANS[method] || PLANS.affiliate;
  var html = plans.map(function(p,i){
    return '<div class="plan-item"><div class="plan-step">'+(i+1)+'</div><div class="plan-text"><div class="plan-title">'+p.t+'</div><div class="plan-desc">'+p.d+'</div></div></div>';
  }).join('');
  document.getElementById('plan-grid').innerHTML = html;
}

function onEmailSubmit(e) {
  setTimeout(function(){
    document.getElementById('email-gate').style.display = 'none';
    document.getElementById('plan-section').style.display = 'block';
    window.scrollTo({top: document.getElementById('plan-section').offsetTop - 80, behavior:'smooth'});
  }, 400);
}

function restart() {
  answers = {};
  document.querySelectorAll('.opt').forEach(function(o){o.classList.remove('selected')});
  document.querySelectorAll('.btn').forEach(function(b){b.disabled=true});
  document.getElementById('email-gate').style.display = 'block';
  document.getElementById('plan-section').style.display = 'none';
  document.getElementById('progress-bar').style.width = '0%';
  nextStep(1);
}

function copyLink() {
  navigator.clipboard.writeText('https://autoincome-ai.vercel.app/rechner').then(function(){
    alert('Link kopiert! ✅');
  });
}
</script>
</body>
</html>`;

  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  res.setHeader('Cache-Control', 'public, max-age=3600');
  return res.status(200).send(html);
}
