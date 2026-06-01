import { useState } from "react";
import { Send, DollarSign, BarChart3, Moon, Sun, Zap, Clock, CheckCircle, AlertCircle, Terminal, Rocket, Download, TrendingUp, Target, Users, Mail, MessageSquare, Briefcase, ChevronRight, Sparkles } from "lucide-react";

const FONT = `@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');`;

const css = `
${FONT}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Syne', sans-serif; }

:root {
  --bg: #0a0a0f;
  --surface: #111118;
  --surface2: #18181f;
  --border: rgba(255,255,255,0.07);
  --border2: rgba(255,255,255,0.12);
  --text: #f0f0f5;
  --muted: #6b6b80;
  --green: #00e676;
  --green-dim: rgba(0,230,118,0.12);
  --blue: #448aff;
  --blue-dim: rgba(68,138,255,0.12);
  --amber: #ffab40;
  --amber-dim: rgba(255,171,64,0.12);
  --red: #ff5252;
  --red-dim: rgba(255,82,82,0.12);
  --gradient: linear-gradient(135deg, #00e676 0%, #448aff 100%);
  --mono: 'JetBrains Mono', monospace;
}

.light {
  --bg: #f4f4f8;
  --surface: #ffffff;
  --surface2: #f0f0f5;
  --border: rgba(0,0,0,0.07);
  --border2: rgba(0,0,0,0.12);
  --text: #0a0a0f;
  --muted: #888899;
  --green-dim: rgba(0,180,90,0.08);
  --blue-dim: rgba(50,100,220,0.08);
  --amber-dim: rgba(200,130,0,0.08);
  --red-dim: rgba(200,50,50,0.08);
}

.shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--bg);
  color: var(--text);
  transition: background 0.3s, color 0.3s;
  position: relative;
  overflow: hidden;
}

/* Ambient bg glow */
.shell::before {
  content: '';
  position: fixed;
  top: -20%;
  left: -10%;
  width: 60%;
  height: 60%;
  background: radial-gradient(ellipse, rgba(0,230,118,0.04) 0%, transparent 70%);
  pointer-events: none;
  z-index: 0;
}
.shell::after {
  content: '';
  position: fixed;
  bottom: -20%;
  right: -10%;
  width: 60%;
  height: 60%;
  background: radial-gradient(ellipse, rgba(68,138,255,0.04) 0%, transparent 70%);
  pointer-events: none;
  z-index: 0;
}

/* Header */
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 28px;
  height: 64px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  position: relative;
  z-index: 10;
  flex-shrink: 0;
}
.logo-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.logo-icon {
  width: 38px;
  height: 38px;
  background: var(--gradient);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #000;
  flex-shrink: 0;
}
.logo-title {
  font-size: 18px;
  font-weight: 800;
  letter-spacing: -0.5px;
  background: var(--gradient);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.logo-sub {
  font-size: 11px;
  color: var(--muted);
  font-family: var(--mono);
  margin-top: 1px;
}
.theme-btn {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  border: 1px solid var(--border2);
  background: var(--surface2);
  color: var(--muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}
.theme-btn:hover { color: var(--text); border-color: var(--border2); }

/* Layout */
.body-wrap {
  display: flex;
  flex: 1;
  overflow: hidden;
  position: relative;
  z-index: 1;
}

/* Sidebar */
.sidebar {
  width: 220px;
  flex-shrink: 0;
  background: var(--surface);
  border-right: 1px solid var(--border);
  padding: 20px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.nav-btn {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  border: none;
  background: transparent;
  color: var(--muted);
  font-family: 'Syne', sans-serif;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  text-align: left;
}
.nav-btn:hover { background: var(--surface2); color: var(--text); }
.nav-btn.active {
  background: var(--green-dim);
  color: var(--green);
  border: 1px solid rgba(0,230,118,0.2);
}
.sidebar-card {
  margin-top: auto;
  background: var(--green-dim);
  border: 1px solid rgba(0,230,118,0.15);
  border-radius: 10px;
  padding: 14px;
}
.sidebar-card-title {
  font-size: 11px;
  font-weight: 700;
  color: var(--green);
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 5px;
}
.timeline-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11px;
  padding: 3px 0;
  color: var(--muted);
  font-family: var(--mono);
}
.timeline-row span:last-child { color: var(--green); font-weight: 600; }

/* Main */
.main { flex: 1; overflow-y: auto; padding: 28px; }

/* Section titles */
.section-title { font-size: 26px; font-weight: 800; letter-spacing: -0.5px; margin-bottom: 4px; }
.section-sub { font-size: 13px; color: var(--muted); margin-bottom: 24px; }

/* Warning banner */
.warn-banner {
  background: var(--amber-dim);
  border: 1px solid rgba(255,171,64,0.2);
  border-radius: 12px;
  padding: 18px 22px;
  margin-bottom: 24px;
}
.warn-banner h3 { font-size: 14px; font-weight: 700; color: var(--amber); margin-bottom: 12px; }
.warn-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.warn-item { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--text); opacity: 0.85; }

/* Terminal */
.terminal-wrap {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
}
.terminal-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: var(--surface2);
  border-bottom: 1px solid var(--border);
}
.term-dot { width: 10px; height: 10px; border-radius: 50%; }
.term-body {
  padding: 16px;
  min-height: 260px;
  max-height: 340px;
  overflow-y: auto;
  font-family: var(--mono);
  font-size: 12px;
  line-height: 1.7;
}
.term-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 220px;
  color: var(--muted);
  gap: 10px;
}
.term-line-info { color: #888; }
.term-line-success { color: var(--green); }
.term-line-error { color: var(--red); }
.term-stamp { color: var(--muted); margin-right: 6px; }

/* Tool cards */
.tool-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 22px;
  margin-bottom: 18px;
  transition: border-color 0.2s;
}
.tool-card:hover { border-color: var(--border2); }
.tool-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 6px; }
.tool-name { font-size: 17px; font-weight: 800; }
.tool-cat {
  font-size: 10px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 20px;
  background: var(--blue-dim);
  color: var(--blue);
  font-family: var(--mono);
  letter-spacing: 0.5px;
  text-transform: uppercase;
}
.tool-desc { font-size: 13px; color: var(--muted); margin-bottom: 12px; line-height: 1.5; }
.badges { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
.badge {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 20px;
  font-family: var(--mono);
  font-weight: 500;
}
.badge-green { background: var(--green-dim); color: var(--green); }
.badge-blue { background: var(--blue-dim); color: var(--blue); }
.badge-amber { background: var(--amber-dim); color: var(--amber); }
.platforms { font-size: 11px; color: var(--muted); margin-bottom: 16px; }

/* Fields */
.fields-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 16px; }
.field-label { font-size: 12px; font-weight: 600; color: var(--muted); margin-bottom: 6px; display: block; text-transform: uppercase; letter-spacing: 0.5px; }
.field-input, .field-select {
  width: 100%;
  padding: 9px 12px;
  border-radius: 8px;
  border: 1px solid var(--border2);
  background: var(--surface2);
  color: var(--text);
  font-family: 'Syne', sans-serif;
  font-size: 13px;
  outline: none;
  transition: border-color 0.2s;
}
.field-input:focus, .field-select:focus { border-color: var(--green); }

/* Run button */
.run-btn {
  width: 100%;
  padding: 12px;
  border: none;
  border-radius: 10px;
  background: var(--gradient);
  color: #000;
  font-family: 'Syne', sans-serif;
  font-size: 14px;
  font-weight: 800;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: opacity 0.2s, transform 0.1s;
  letter-spacing: 0.3px;
}
.run-btn:hover:not(:disabled) { opacity: 0.9; transform: translateY(-1px); }
.run-btn:active:not(:disabled) { transform: translateY(0); }
.run-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* Downloads */
.dl-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 22px;
  margin-bottom: 18px;
}
.dl-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 14px; }
.dl-btn {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-radius: 10px;
  border: 1px solid rgba(0,230,118,0.2);
  background: var(--green-dim);
  color: var(--green);
  cursor: pointer;
  font-family: 'Syne', sans-serif;
  transition: all 0.2s;
}
.dl-btn:hover { background: rgba(0,230,118,0.18); transform: translateY(-1px); }
.dl-btn-name { font-size: 13px; font-weight: 700; }
.dl-btn-sub { font-size: 11px; opacity: 0.7; font-family: var(--mono); margin-top: 1px; }
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 300px;
  color: var(--muted);
  gap: 10px;
  text-align: center;
}
.empty-state p { font-size: 15px; }
.empty-state small { font-size: 12px; font-family: var(--mono); }

/* Scrollbar */
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 4px; }

/* Cost Dashboard */
.cost-dash {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 14px;
  margin-bottom: 14px;
}
.cost-dash-title {
  font-size: 10px;
  font-weight: 700;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.8px;
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 5px;
}
.cost-metrics {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 8px;
}
.cost-metric { text-align: center; }
.cost-metric-val {
  font-size: 13px;
  font-weight: 700;
  font-family: var(--mono);
  color: var(--text);
  margin-bottom: 2px;
}
.cost-metric-val.green { color: var(--green); }
.cost-metric-val.amber { color: var(--amber); }
.cost-metric-val.blue  { color: var(--blue); }
.cost-metric-val.red   { color: var(--red); }
.cost-metric-label {
  font-size: 10px;
  color: var(--muted);
  font-family: var(--mono);
}
.cost-bar-wrap {
  margin-top: 10px;
  background: var(--border);
  border-radius: 4px;
  height: 3px;
  overflow: hidden;
}
.cost-bar-fill {
  height: 100%;
  border-radius: 4px;
  background: var(--gradient);
  transition: width 0.6s ease;
}
.global-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-bottom: 24px;
}
.gstat {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px;
  text-align: center;
}
.gstat-val {
  font-size: 18px;
  font-weight: 800;
  font-family: var(--mono);
  margin-bottom: 3px;
}
.gstat-label {
  font-size: 10px;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
`;

const quickCashTools = [
  {
    id: 1, name: "AI Service Arbitrage", category: "Freelancing",
    timeToFirstDollar: "24–48h", weeklyPotential: "$200–800", effort: "Mittel",
    description: "Verkaufe AI-Services (Logos, Content, Design) auf Fiverr mit 500%+ Markup. Die AI macht die Arbeit – du kassierst.",
    platforms: ["Fiverr", "Upwork", "Freelancer"],
    fields: [
      { name: "service", label: "Service", type: "select", options: ["Logo Design", "Content Writing", "Social Media Posts", "Business Names", "Presentations"] },
      { name: "price", label: "Dein Preis ($)", type: "number", placeholder: "50" },
      { name: "turnaround", label: "Lieferzeit (Stunden)", type: "number", placeholder: "24" }
    ]
  },
  {
    id: 2, name: "Local Lead Generator", category: "Lead Generation",
    timeToFirstDollar: "3–7 Tage", weeklyPotential: "$300–1000", effort: "Hoch",
    description: "Generiere qualifizierte Leads für lokale Businesses und verkaufe sie für $10–50 pro Stück.",
    platforms: ["Direkt", "Cold Email", "LinkedIn"],
    fields: [
      { name: "industry", label: "Industrie", type: "select", options: ["Immobilien", "Versicherungen", "Handwerker", "Zahnärzte", "Anwälte"] },
      { name: "location", label: "Stadt/Region", type: "text", placeholder: "München" },
      { name: "leadPrice", label: "Preis pro Lead ($)", type: "number", placeholder: "20" }
    ]
  },
  {
    id: 3, name: "Upwork Gig Automation", category: "Freelancing",
    timeToFirstDollar: "2–5 Tage", weeklyPotential: "$400–1200", effort: "Hoch",
    description: "Automatisiere Upwork-Bewerbungen und liefere mit AI in 10% der angegebenen Zeit.",
    platforms: ["Upwork", "Freelancer.com"],
    fields: [
      { name: "skill", label: "Skill", type: "select", options: ["Writing", "Data Entry", "Virtual Assistant", "Research", "Transcription"] },
      { name: "hourlyRate", label: "Stundensatz ($)", type: "number", placeholder: "25" },
      { name: "hoursPerWeek", label: "Stunden/Woche", type: "number", placeholder: "20" }
    ]
  },
  {
    id: 4, name: "Cold Outreach Machine", category: "Client Acquisition",
    timeToFirstDollar: "5–10 Tage", weeklyPotential: "$500–2000", effort: "Sehr Hoch",
    description: "Vollautomatisierte Cold Outreach für hochpreisige Services – Emails, LinkedIn, Skripte.",
    platforms: ["Email", "LinkedIn", "Cold Calls"],
    fields: [
      { name: "targetRole", label: "Ziel-Position", type: "text", placeholder: "Marketing Manager" },
      { name: "serviceOffered", label: "Dein Service", type: "text", placeholder: "SEO Audit" },
      { name: "price", label: "Preis ($)", type: "number", placeholder: "500" }
    ]
  },
  {
    id: 5, name: "UGC Creator Agency", category: "Content Creation",
    timeToFirstDollar: "3–7 Tage", weeklyPotential: "$400–1500", effort: "Mittel",
    badge: "🔥 TRENDING",
    description: "Brands zahlen $150–500 pro Video für authentischen User-Generated-Content. Mit AI-Skripten + Handy-Kamera in 30 Min liefern.",
    platforms: ["TikTok", "Instagram", "Brands Direct"],
    fields: [
      { name: "niche", label: "Nische", type: "select", options: ["Beauty & Skincare", "Tech & Gadgets", "Food & Drinks", "Fitness & Health", "Home & Lifestyle"] },
      { name: "videoPrice", label: "Preis pro Video ($)", type: "number", placeholder: "200" },
      { name: "videosPerWeek", label: "Videos/Woche", type: "number", placeholder: "5" }
    ]
  },
  {
    id: 6, name: "Faceless YouTube Channel", category: "AI Video",
    timeToFirstDollar: "14–30 Tage", weeklyPotential: "$300–2000", effort: "Mittel",
    badge: "🚀 HOT 2025",
    description: "KI-generierte Skripte + Text-to-Speech + Stock-Footage = monetisierbarer YouTube-Kanal ohne Kamera oder Gesicht.",
    platforms: ["YouTube", "TikTok", "Reels"],
    fields: [
      { name: "channelNiche", label: "Kanal-Nische", type: "select", options: ["True Crime", "Finance & Money", "Motivation", "History Facts", "AI & Technology"] },
      { name: "uploadFreq", label: "Videos/Woche", type: "number", placeholder: "3" },
      { name: "targetSubs", label: "Ziel-Abonnenten", type: "number", placeholder: "1000" }
    ]
  },
  {
    id: 7, name: "Newsletter Ghostwriting", category: "Ghostwriting",
    timeToFirstDollar: "5–10 Tage", weeklyPotential: "$500–3000", effort: "Mittel",
    badge: "💎 HIGH TICKET",
    description: "Schreibe mit AI Newsletters für X/LinkedIn-Creator. Monatliche Retainer $500–2000. Einer der heißesten Services 2025.",
    platforms: ["X (Twitter)", "LinkedIn", "Beehiiv", "Substack"],
    fields: [
      { name: "newsletterNiche", label: "Newsletter-Thema", type: "select", options: ["Business & Startups", "Personal Finance", "AI & Tech", "Marketing", "Health & Wellness"] },
      { name: "retainerPrice", label: "Monats-Retainer ($)", type: "number", placeholder: "800" },
      { name: "issuesPerMonth", label: "Ausgaben/Monat", type: "number", placeholder: "4" }
    ]
  },
  {
    id: 8, name: "Digital Products Empire", category: "Digital Products",
    timeToFirstDollar: "2–5 Tage", weeklyPotential: "$200–1500", effort: "Niedrig",
    badge: "⚡ SCHNELLSTART",
    description: "Notion-Templates, Prompt-Packs, AI-Guides auf Gumroad/Etsy verkaufen. Einmal erstellen – immer wieder verkaufen.",
    platforms: ["Gumroad", "Etsy", "Lemon Squeezy"],
    fields: [
      { name: "productType", label: "Produkt-Typ", type: "select", options: ["Notion Template", "Prompt Pack", "AI Guide/Ebook", "Canva Template", "Spreadsheet System"] },
      { name: "productPrice", label: "Produkt-Preis ($)", type: "number", placeholder: "27" },
      { name: "targetSales", label: "Ziel-Verkäufe/Monat", type: "number", placeholder: "50" }
    ]
  }
];

// ── API helpers ─────────────────────────────────────────────────────────────

async function callClaude(prompt) {
  // Load API config dynamically
  let apiKey = '';
  let apiUrl = 'http://localhost:3001/api/claude';
  let model = 'claude-sonnet-4-20250514';
  let useDirectApi = false;
  let version = '2023-06-01';
  
  try {
    const configResponse = await fetch('./api-config.json');
    if (configResponse.ok) {
      const config = await configResponse.json();
      if (config.anthropic) {
        apiKey = config.anthropic.apiKey || apiKey;
        model = config.anthropic.model || model;
        version = config.anthropic.version || version;
        if (config.anthropic.apiKey) {
          apiUrl = (config.anthropic.baseUrl || 'https://api.anthropic.com/v1') + '/messages';
          useDirectApi = true;
        }
      }
    }
  } catch (e) {
    console.warn('API config nicht gefunden, nutze Proxy');
  }

  // Also check localStorage for API key
  if (!apiKey && typeof window !== 'undefined') {
    apiKey = localStorage.getItem('anthropic_api_key') || '';
    if (apiKey) {
      apiUrl = 'https://api.anthropic.com/v1/messages';
      useDirectApi = true;
    }
  }

  // Check for example API keys
  if (!apiKey || apiKey === 'DEIN_ANTHROPIC_API_KEY_HIER' || apiKey === 'sk-ant-api03-DEIN_API_KEY_HIER') {
    console.warn('Bitte echten Anthropic API-Key in api-config.json oder localStorage eintragen!');
  }

  const headers = { "Content-Type": "application/json" };
  if (useDirectApi && apiKey) {
    headers["x-api-key"] = apiKey;
    headers["anthropic-version"] = version;
  }

  const res = await fetch(apiUrl, {
    method: "POST",
    headers: headers,
    body: JSON.stringify({
      model: model,
      max_tokens: 1000,
      messages: [{ role: "user", content: prompt }]
    })
  });
  const data = await res.json();
  if (data.error) throw new Error(data.error.message);
  return {
    text: data.content[0].text,
    tokensIn:  data.usage?.input_tokens  || 0,
    tokensOut: data.usage?.output_tokens || 0
  };
}

// ── Tool runners ─────────────────────────────────────────────────────────────

async function runAIServiceArbitrage(config, log, stats) {
  const _t0 = Date.now();
  log("🚀 Starte AI Service Arbitrage System…", "info");
  log(`📦 Generiere Fiverr Gig für: ${config.service}`, "info");

  const r1 = await callClaude(
    `Create a complete Fiverr gig package for: ${config.service}. Price: $${config.price}. Turnaround: ${config.turnaround}h.
Generate: 1. Compelling gig title (<80 chars) 2. SEO-optimized description (300 words) 3. 3 pricing tiers 4. 5 FAQ items 5. 5 search tags 6. Quick AI prompt to deliver this instantly. Make it irresistible and professional.`
  );
  const gigPackage = r1.text;
  stats(r1.tokensIn, r1.tokensOut, Date.now() - _t0);

  const deliveryTemplate = `# ${config.service} — AI Delivery System

## How to Deliver in <15 Minutes

### Step 1: Requirements from Client
${config.service === "Logo Design" ? "- Company name\n- Industry\n- Preferred colors\n- Style (modern/classic)" :
  config.service === "Content Writing" ? "- Topic\n- Word count\n- Target audience\n- Keywords" :
  "- Project details\n- Style preferences\n- Deadline"}

### Step 2: AI Prompt Template
\`\`\`
Create professional ${config.service}:
[CLIENT REQUIREMENTS]
High-quality, professional, ready to deliver.
\`\`\`

### Step 3: Deliver & Review
- Polish AI output (5 min)
- Package (PDF/ZIP)
- Deliver within ${config.turnaround}h
- Ask for 5-star review ⭐

## Economics
| Item | Value |
|------|-------|
| Your price | $${config.price} |
| AI cost | ~$0.50 |
| Time | ~15 min |
| Profit | $${(config.price - 0.5).toFixed(2)} |
| Effective $/hr | $${((config.price - 0.5) * 4).toFixed(0)} |

## Weekly Projections
- 5 orders → $${config.price * 5}
- 20 orders → $${config.price * 20}
- 50 orders → $${config.price * 50}`;

  log("✅ Fiverr Gig Package generiert!", "success");
  log("📋 Delivery System (15 Min/Order) erstellt", "success");
  log(`⏱️  Zeit bis erste $${config.price}: 24–48h`, "info");
  log(`💰 Woche 1 Potenzial: $${config.price * 2}–$${config.price * 5}`, "success");

  return {
    "fiverr-gig.txt": gigPackage,
    "delivery-system.md": deliveryTemplate
  };
}

async function runLeadGenerator(config, log, stats) {
  const _t0 = Date.now();
  log("🎯 Local Lead Generator startet…", "info");
  log(`📍 ${config.industry} in ${config.location} @ $${config.leadPrice}/Lead`, "info");

  const r2 = await callClaude(
    `Create a complete lead generation system for ${config.industry} businesses in ${config.location}. Lead price: $${config.leadPrice} each.
Generate: 1. Lead qualification criteria 2. Where to find leads 3. Two cold email templates 4. LinkedIn script 5. Sales pitch to sell leads.`
  );
  const leadSystem = r2.text;
  stats(r2.tokensIn, r2.tokensOut, Date.now() - _t0);

  const actionPlan = `# 7-Day Action Plan → First $${config.leadPrice * 20}

## Day 1 – Research & Setup
- [ ] Research ${config.industry} in ${config.location}
- [ ] Find 50 businesses via Google Maps
- [ ] Collect contact info in spreadsheet

## Day 2 – Lead Collection
- [ ] Qualify & clean 20 leads
- [ ] Verify emails

## Day 3 – Outreach
- [ ] Send 50 cold emails
- [ ] Send 20 LinkedIn messages
- [ ] Attach 3 free sample leads

## Day 4–5 – Follow-up
- [ ] Reply to all responses
- [ ] Close first deal 🎉

## Day 6–7 – Deliver & Scale
- [ ] Deliver leads + invoice
- [ ] Get testimonial
- [ ] Find 100 more prospects

## Revenue Projections
| Week | Clients | Revenue |
|------|---------|---------|
| 1 | 1–2 | $${config.leadPrice * 20}–$${config.leadPrice * 40} |
| 2 | 3–5 | $${config.leadPrice * 60}–$${config.leadPrice * 100} |
| 4 | 5–10 | $${config.leadPrice * 100}–$${config.leadPrice * 200} (recurring) |`;

  log("✅ Lead Generation System komplett!", "success");
  log("📅 7-Tage Aktionsplan erstellt", "success");
  log(`💰 Woche 1 Potenzial: $${config.leadPrice * 20}–$${config.leadPrice * 40}`, "success");

  return {
    "lead-system.txt": leadSystem,
    "7-day-action-plan.md": actionPlan
  };
}

async function runUpworkAutomation(config, log, stats) {
  const _t0 = Date.now();
  log("💼 Upwork Automation startet…", "info");
  log(`🔧 Skill: ${config.skill} @ $${config.hourlyRate}/h`, "info");

  const r3 = await callClaude(
    `Create Upwork automation system for: ${config.skill}. Rate: $${config.hourlyRate}/hour. Hours available: ${config.hoursPerWeek}/week.
Generate: 1. Profile optimization tips 2. Three proposal templates 3. How to deliver with AI in 10% of quoted time 4. Client communication templates.`
  );
  const upworkSystem = r3.text;
  stats(r3.tokensIn, r3.tokensOut, Date.now() - _t0);

  const timeSaving = `# Deliver ${config.skill} 10× Faster

## The System
1. Client hires you → quote ${config.hoursPerWeek}h @ $${config.hourlyRate}
2. Use AI → complete in 2–3 hours
3. Deliver over several days (realistic pacing)
4. Earn full rate

## Weekly Economics
| Metric | Value |
|--------|-------|
| Projects/week | 3 |
| Avg value | $${config.hourlyRate * 15} |
| Weekly revenue | $${config.hourlyRate * 45} |
| Actual hours | ~6h |
| Real $/hr | $${Math.round(config.hourlyRate * 45 / 6)} |

## Week-by-Week
- Week 1: $${config.hourlyRate * 20}–$${config.hourlyRate * 40}
- Week 2: $${config.hourlyRate * 45}–$${config.hourlyRate * 60}
- Week 4: $${config.hourlyRate * 75}–$${config.hourlyRate * 120}`;

  log("✅ Upwork Automation System komplett!", "success");
  log("📝 Proposal Templates + AI Guide erstellt", "success");
  log(`💰 Woche 1 Potenzial: $${config.hourlyRate * 20}–$${config.hourlyRate * 40}`, "success");

  return {
    "upwork-system.txt": upworkSystem,
    "time-saving-guide.md": timeSaving
  };
}

async function runColdOutreach(config, log, stats) {
  const _t0 = Date.now();
  log("📧 Cold Outreach Machine startet…", "info");
  log(`🎯 Ziel: ${config.targetRole} → ${config.serviceOffered} @ $${config.price}`, "info");

  const r4 = await callClaude(
    `Create cold outreach system. Target: ${config.targetRole}. Service: ${config.serviceOffered}. Price: $${config.price}.
Generate: 1. LinkedIn connection message 2. Three-email cold sequence 3. Objection handling 4. Closing script 5. Where to find 500+ prospects.`
  );
  const outreachSystem = r4.text;
  stats(r4.tokensIn, r4.tokensOut, Date.now() - _t0);

  const emailSequence = `# Cold Email Sequence — ${config.serviceOffered}

## Email 1 (Day 1) — Initial Touch
**Subject:** Quick question about [COMPANY]'s ${config.serviceOffered}

Hi [Name],

I noticed [COMPANY] and had a quick question — are you happy with your current ${config.serviceOffered} results?

I help ${config.targetRole}s achieve [specific metric] improvement. Worth a 15-min call?

— [Your Name]

P.S. Free audit available, no strings attached.

---

## Email 2 (Day 4) — Value Drop
**Subject:** [COMPANY] — Free ${config.serviceOffered} Analysis

Hi [Name],

Did a quick analysis of [COMPANY] — found 3 wins:
1. [Insight 1]
2. [Insight 2]
3. [Insight 3]

Want the full report? Completely free.

---

## Email 3 (Day 8) — Close or Goodbye
**Subject:** Should I close your file?

Hi [Name],

One last thing before I move on — [COMPETITOR] implemented ${config.serviceOffered} and saw [result] in [timeframe].

Calendar link below if you'd like to chat. Otherwise, I'll follow up in 90 days.

---

## Expected Funnel (per 100 emails)
| Stage | Count |
|-------|-------|
| Opens (50%) | 50 |
| Responses (12%) | 12 |
| Discovery calls (4%) | 4 |
| Closes (40%) | ~1–2 |
| Revenue | $${config.price}–$${config.price * 2} |`;

  log("✅ Cold Outreach System komplett!", "success");
  log("📧 3-Email Sequenz erstellt", "success");
  log("💬 Closing Scripts erstellt", "success");
  log(`💰 Woche 1 Potenzial: $${config.price}–$${config.price * 2}`, "success");

  return {
    "outreach-system.txt": outreachSystem,
    "email-sequence.md": emailSequence
  };
}

async function runUGCCreator(config, log, stats) {
  const _t0 = Date.now();
  log("🎬 UGC Creator Agency startet…", "info");
  log(`📱 Nische: ${config.niche} @ $${config.videoPrice}/Video`, "info");

  const r5 = await callClaude(
    `Create a complete UGC (User Generated Content) creator business system for the ${config.niche} niche.
Price per video: $${config.videoPrice}. Target: ${config.videosPerWeek} videos/week.
Generate: 1. How to find brand deals (5 methods) 2. Pitch email template to brands 3. UGC video script template (hook + demo + CTA) 4. Pricing packages (Basic/Standard/Premium) 5. Portfolio tips without prior experience.`
  );
  const ugcSystem = r5.text;
  stats(r5.tokensIn, r5.tokensOut, Date.now() - _t0);

  const scriptTemplates = `# UGC Video Script Templates — ${config.niche}

## The 3-Part Formula (Works Every Time)
Hook (3 sec) → Problem/Demo (15–20 sec) → CTA (5 sec)

---

## Script 1: Problem-Solution Hook
**Hook:** "I tried every [product type] in ${config.niche} and THIS one actually works…"
**Demo:** Show product, 3 key benefits, authentic reaction
**CTA:** "Link in bio / Use code [BRAND] for 10% off"

---

## Script 2: Before/After
**Hook:** "My [problem] was ruining my [life area] until I found this…"
**Demo:** Before state → using product → after result
**CTA:** "Comment '${config.niche.split(' ')[0].toUpperCase()}' and I'll DM you the link"

---

## Script 3: POV / Reaction
**Hook:** "POV: You just discovered the best [product] for ${config.niche}"
**Demo:** Unboxing / first use reaction, highlight 2–3 features
**CTA:** "Find it at [Brand website] — link below"

---

## Shot List (Film in 30 Min)
1. Close-up of product (5 shots)
2. You holding/using product (5 shots)
3. Detail shots / texture (3 shots)
4. Lifestyle B-roll (3 shots)
5. Talking-to-camera (2 takes per script)

## Equipment
- Phone (any modern iPhone/Android)
- Ring light ($20 Amazon)
- Simple background (wall / aesthetic corner)

## Economics
| Metric | Value |
|--------|-------|
| Videos/week | ${config.videosPerWeek} |
| Price/video | $${config.videoPrice} |
| Weekly revenue | $${config.videoPrice * config.videosPerWeek} |
| Monthly revenue | $${config.videoPrice * config.videosPerWeek * 4} |
| Time/video | ~30–45 min |`;

  const brandOutreach = `# Brand Outreach System — UGC ${config.niche}

## Where to Find Brands
1. **TikTok Creator Marketplace** (creator.tiktok.com) – direct brand deals
2. **Billo / Trend / Insense** – UGC platforms, brands come to you
3. **Instagram DMs** – search ${config.niche} brands with 10k–200k followers
4. **LinkedIn** – search "Brand Manager ${config.niche}" + pitch directly
5. **Shopify stores** – find brands via Google, cold email marketing@brand.com

## Pitch Email (Cold)
Subject: UGC Videos for [BRAND] — ${config.niche} Creator

Hi [Name],

I'm a UGC creator specializing in ${config.niche} content.

I create authentic, scroll-stopping videos for brands like yours — no influencer fees, no algorithm dependency. Pure conversion-focused content.

My package:
• ${config.videosPerWeek} videos/week
• All raw footage + edited versions
• Usage rights included
• Investment: $${config.videoPrice * config.videosPerWeek}/week

Here are 3 sample concepts I'd create for [BRAND]: [describe]

Interested in a free sample video?

Best,
[Your Name]

## Pricing Page
- Starter: 1 video = $${config.videoPrice}
- Bundle 5: $${Math.round(config.videoPrice * 4.5)} (save 10%)
- Monthly Retainer (${config.videosPerWeek * 4} videos): $${Math.round(config.videoPrice * config.videosPerWeek * 4 * 0.85)}/mo

## Week 1 Target: $${config.videoPrice * 3}–$${config.videoPrice * 6}
Send 20 pitches → 3–5 interested → 1–2 pay`;

  log("✅ UGC Creator System komplett!", "success");
  log("🎬 3 Video-Skript-Templates erstellt", "success");
  log("📧 Brand Outreach System bereit", "success");
  log(`💰 Woche 1 Potenzial: $${config.videoPrice * 3}–$${config.videoPrice * 6}`, "success");

  return {
    "ugc-system.txt": ugcSystem,
    "video-scripts.md": scriptTemplates,
    "brand-outreach.md": brandOutreach
  };
}

async function runFacelessYouTube(config, log, stats) {
  const _t0 = Date.now();
  log("📺 Faceless YouTube Channel System startet…", "info");
  log(`🎯 Nische: ${config.channelNiche} | ${config.uploadFreq} Videos/Woche`, "info");

  const r6 = await callClaude(
    `Create a complete faceless YouTube channel system for the "${config.channelNiche}" niche.
Upload frequency: ${config.uploadFreq} videos/week. Target: ${config.targetSubs} subscribers.
Generate: 1. Channel name ideas (5) 2. Content pillars (5 recurring formats) 3. Complete video script template 4. AI tools stack (free + paid) 5. Monetization roadmap from 0 to $1000/month.`
  );
  const channelSystem = r6.text;
  stats(r6.tokensIn, r6.tokensOut, Date.now() - _t0);

  const videoBlueprint = `# Faceless YouTube Blueprint — ${config.channelNiche}

## The AI Production Stack (Kostenlos starten)

| Tool | Aufgabe | Kosten |
|------|---------|--------|
| Claude / ChatGPT | Skript schreiben | Free |
| ElevenLabs | AI Voiceover | Free (10k chars/mo) |
| CapCut / DaVinci | Schneiden | Free |
| Pexels / Pixabay | Stock Footage | Free |
| Canva | Thumbnails | Free |
| TubeBuddy | SEO | Free tier |

---

## Video-Produktionsprozess (2–3h/Video)

**Schritt 1: Titel & Hook finden (15 Min)**
- Suche: "[${config.channelNiche}] most viewed" auf YouTube
- Angle: Liste, Rankingschartes, Enthüllungen, Vergleiche
- Formel: "Top 10 [X] die [Y]" / "Die Wahrheit über [X]"

**Schritt 2: Skript mit AI (20 Min)**
Prompt: "Write a 8-minute YouTube script about [TOPIC] in ${config.channelNiche} style.
Include: hook, 5 main points with stories, smooth transitions, strong outro CTA.
Tone: engaging, conversational, slightly dramatic."

**Schritt 3: Voiceover (10 Min)**
- ElevenLabs → paste script → Download MP3
- Empfohlene Stimmen: Adam, Antoni, Josh (neutral, authoritative)

**Schritt 4: Schneiden (60–90 Min)**
- CapCut: Import audio → add stock footage per Abschnitt
- Untertitel: Auto-generate + korrigieren
- Übergänge: simple cuts, keine fancy effects

**Schritt 5: Thumbnail (15 Min)**
- Canva Template: großer Text + kontrastreiche Farbe + Emotion
- A/B Test: 2 Thumbnails, wechsle nach 48h wenn schlecht

---

## Monetarisierungs-Roadmap

| Meilenstein | Zeitrahmen | Einnahmen |
|-------------|------------|-----------|
| 100 Subs | 2–4 Wo | $0 (Wachstum) |
| ${config.targetSubs} Subs | 2–3 Mo | Sponsoren möglich |
| 1.000 Subs + 4.000h | 3–6 Mo | YouTube Partner ($3–7/1000 views) |
| 10.000 Subs | 6–12 Mo | $500–2000/Mo |

## Nebeneinnahmen (ohne Monetarisierung)
- Affiliate-Links in Beschreibung: +$50–300/Mo
- Sponsoren ab 1k Subs: $50–200/Video
- Patreon / Community: +$100–500/Mo

## Woche 1 Ziel: Ersten ${config.uploadFreq} Videos hochladen`;

  log("✅ Faceless YouTube System komplett!", "success");
  log("🛠️ AI Production Stack Guide erstellt", "success");
  log("📈 Monetarisierungs-Roadmap erstellt", "success");
  log(`🎯 Ziel: ${config.targetSubs} Subs in 2–3 Monaten`, "info");

  return {
    "youtube-system.txt": channelSystem,
    "video-blueprint.md": videoBlueprint
  };
}

async function runNewsletterGhostwriting(config, log, stats) {
  const _t0 = Date.now();
  log("✉️ Newsletter Ghostwriting System startet…", "info");
  log(`📋 Thema: ${config.newsletterNiche} | $${config.retainerPrice}/Monat`, "info");

  const r7 = await callClaude(
    `Create a complete newsletter ghostwriting business system for the "${config.newsletterNiche}" niche.
Retainer price: $${config.retainerPrice}/month. ${config.issuesPerMonth} issues per month.
Generate: 1. Ideal client profile 2. How to find clients (LinkedIn, X/Twitter, cold email) 3. Newsletter writing framework + template 4. Client onboarding process 5. Upsell opportunities.`
  );
  const ghostwritingSystem = r7.text;
  stats(r7.tokensIn, r7.tokensOut, Date.now() - _t0);

  const newsletterTemplate = `# Newsletter Writing System — ${config.newsletterNiche}

## Die AIDA-Newsletter-Formel

### Struktur (600–900 Wörter optimal)
1. **Subject Line** (öffnet die Email) — Neugier + Nutzen
2. **Hook** (erste 2 Sätze) — starke These oder unerwartete Aussage
3. **Body** (3–4 Abschnitte) — Story → Insight → Anwendung
4. **CTA** (letzte 50 Wörter) — Eine klare Aufforderung

---

## Subject Line Formeln (${config.newsletterNiche})
- "Die eine Sache, die [Zielgruppe] nie tut (aber sollte)"
- "Warum [Mainstream-Meinung] falsch liegt"
- "[Zahl] Erkenntnisse aus [Erfahrung/Buch/Gespräch]"
- "Ich habe [X] analysiert. Das habe ich gefunden:"
- "Das passiert, wenn du [Handlung] ignorierst"

---

## AI-Prompts für jede Ausgabe (${config.issuesPerMonth}×/Monat)

**Prompt 1 — Erstentwurf:**
"Write a ${config.newsletterNiche} newsletter issue. Topic: [TOPIC].
Style: smart, direct, no fluff. 700 words. Structure: bold hook, 3 insight sections, strong CTA.
Target reader: [CLIENT'S AUDIENCE DESCRIPTION]"

**Prompt 2 — Subject Lines:**
"Generate 10 subject line options for a newsletter about [TOPIC]. 
Mix of: curiosity, controversy, numbers, personal. Under 50 characters each."

**Prompt 3 — Polish:**
"Review this newsletter draft for [CLIENT]. 
Make it sound more like [VOICE DESCRIPTION]. 
Improve hook, tighten body, strengthen CTA."

---

## Client Onboarding (Woche 1)
- [ ] Voice doc: 10 Fragen zum Stil, Ton, Meinungen
- [ ] 3 Lieblins-Newsletter des Kunden analysieren
- [ ] Erster Entwurf: 24h Lieferzeit
- [ ] 2 Revisionen inbegriffen
- [ ] Monatliches 30-Min-Call

---

## Retainer Economics
| Faktor | Wert |
|--------|------|
| Retainer/Monat | $${config.retainerPrice} |
| Ausgaben/Monat | ${config.issuesPerMonth} |
| Preis/Ausgabe | $${Math.round(config.retainerPrice / config.issuesPerMonth)} |
| AI-Zeit/Ausgabe | ~45 Min |
| Review-Zeit | ~30 Min |
| Real $/Stunde | $${Math.round(config.retainerPrice / (config.issuesPerMonth * 1.25))} |
| 3 Kunden | $${config.retainerPrice * 3}/Mo |
| 6 Kunden | $${config.retainerPrice * 6}/Mo |`;

  const clientFinder = `# Wo findest du Newsletter-Ghostwriting-Kunden?

## Methode 1: LinkedIn (Beste Quelle)
Search: "${config.newsletterNiche}" + "newsletter" + "Substack" OR "Beehiiv"
→ Finde Creator mit 5k–50k Followern die selbst schreiben
→ Pitch: "Ich sehe dein Newsletter wächst — ich ghostwrite für 3 Creator in deiner Nische"

## Methode 2: X (Twitter)
Search: "newsletter" + "${config.newsletterNiche}" + "looking for help"
→ Beobachte wer über Zeitproblem klagt
→ Reply oder DM mit Pitch + Probe-Ausgabe

## Methode 3: Upwork / Contra
Search: "newsletter writer" "ghostwriter" "${config.newsletterNiche}"
→ Hohe Nachfrage, wenig gute Angebote
→ Profil auf ${config.newsletterNiche} Ghostwriting spezialisieren

## Pitch-Nachricht (X/LinkedIn DM):
"Hey [Name], 

Ich lese deinen Newsletter zu ${config.newsletterNiche} — gute Arbeit.

Ich ghostwrite für 2 Creator in deiner Nische und habe einen Slot frei.

Darf ich dir eine Probe-Ausgabe schreiben? Kostenlos, kein Pitch.

Wenn du magst, reden wir über eine monatliche Zusammenarbeit."

## Woche 1 Ziel: 1 bezahlender Kunde = $${config.retainerPrice}`;

  log("✅ Newsletter Ghostwriting System komplett!", "success");
  log("📝 Newsletter-Vorlage + AI-Prompts erstellt", "success");
  log("🎯 Client Finder Guide erstellt", "success");
  log(`💰 Potenzial: $${config.retainerPrice * 3}–$${config.retainerPrice * 6}/Monat`, "success");

  return {
    "ghostwriting-system.txt": ghostwritingSystem,
    "newsletter-template.md": newsletterTemplate,
    "client-finder.md": clientFinder
  };
}

async function runDigitalProducts(config, log, stats) {
  const _t0 = Date.now();
  log("🛒 Digital Products Empire startet…", "info");
  log(`📦 Produkt: ${config.productType} @ $${config.productPrice}`, "info");

  const r8 = await callClaude(
    `Create a complete digital product business system for selling a "${config.productType}" at $${config.productPrice}.
Target: ${config.targetSales} sales/month = $${config.productPrice * config.targetSales}/month.
Generate: 1. Product concept and what to include 2. Where to sell (platforms comparison) 3. Sales page copy template 4. Launch strategy (Day 1–7) 5. Traffic sources (free and paid).`
  );
  const productSystem = r8.text;
  stats(r8.tokensIn, r8.tokensOut, Date.now() - _t0);

  const productBlueprint = `# Digital Product Blueprint — ${config.productType}

## Was verkauft sich 2025 am besten?

${config.productType === "Notion Template" ? `
### Bestseller-Kategorien (Notion):
- Life OS / Second Brain ($29–97)
- Business Dashboard ($19–49)
- Content Creator Hub ($19–39)
- Student Planner ($9–19)
- Freelancer CRM ($19–49)

### Dein Produkt soll enthalten:
- Hauptdatenbank mit 5+ Views
- Anleitungs-Video (Loom, 5 Min)
- Quick-Start-Guide (1 Seite)
- Update-Versprechen (1 Jahr)
` : config.productType === "Prompt Pack" ? `
### Bestseller-Kategorien (Prompts):
- "100 AI Prompts für [Beruf]" ($9–27)
- ChatGPT Business Templates ($17–47)
- Midjourney Style Guide ($14–37)
- Social Media Prompt Bundle ($9–27)

### Dein Paket soll enthalten:
- 50–200 Prompts (kategorisiert)
- Erklärung für jeden Prompt
- Beispiel-Output Screenshot
- Bonus: 10 "Power Prompts"
` : `
### Was rein muss:
- Klarer Nutzen auf Titelseite
- Schritt-für-Schritt Struktur
- Screenshots / Beispiele
- Bonus-Material
- Umsetzbar in < 7 Tagen
`}

## Plattform-Vergleich

| Plattform | Gebühren | Traffic | Beste für |
|-----------|----------|---------|-----------|
| Gumroad | 10% | Mittel | Alles |
| Etsy | 6.5% + $0.20 | Hoch | Templates |
| Lemon Squeezy | 5% + $0.50 | Niedrig | Tech-Produkte |
| Eigene Website | 2–3% | 0 (du bringst Traffic) | Skalierung |

**Empfehlung Woche 1:** Gumroad (schnellste Einrichtung)

## Sales Page Formel (Copy)

**Headline:** "Das ${config.productType}, das [PROBLEM löst] in [Zeitraum]"
**Subheadline:** Für [Zielgruppe] die [Wunsch] ohne [Schmerzpunkt]

**3 Bullet Benefits:**
✅ [Benefit 1 — konkret]
✅ [Benefit 2 — emotional]
✅ [Benefit 3 — zeitlich]

**Preis:** ~~$${config.productPrice * 2}~~ Jetzt $${config.productPrice}

**CTA:** "Jetzt herunterladen →"

---

## Launch-Woche Plan

| Tag | Aktion | Ziel |
|-----|--------|------|
| 1 | Produkt fertigstellen, Seite live | 0 Verkäufe (Setup) |
| 2 | Post auf LinkedIn + X (Reddit) | 2–3 Verkäufe |
| 3 | TikTok/Reels: "I made a [product]" | 3–5 Verkäufe |
| 4 | Email an Netzwerk | 2–4 Verkäufe |
| 5 | Pinterest Pins erstellen | Langfristiger Traffic |
| 6 | Finde 3 Affiliates (50% Provision) | Multiplikator |
| 7 | Auswerten + Preis testen | Optimierung |

## Monatsziel: ${config.targetSales} × $${config.productPrice} = $${config.productPrice * config.targetSales}

### Traffic-Rechnung:
- Conversion Rate: 2–5%
- Besucher nötig: ${Math.round(config.targetSales / 0.03)} Besucher/Monat
- Das sind ${Math.round(config.targetSales / 0.03 / 30)} Besucher/Tag — realistisch mit Konsistenz`;

  const marketingKit = `# Marketing Kit — ${config.productType} @ $${config.productPrice}

## TikTok / Reels Content-Ideen (Virales Format)

1. "I built a ${config.productType} and made $[X] in a week" — Storytelling
2. "The ${config.productType} I wish I had when starting" — Listicle
3. "Tour through my ${config.productType}" — Screen-Recording
4. "I analyzed 100 [Nische]-Profis — das nutzen sie alle" — Research
5. "Stop doing X, start doing Y" — Kontroverse These

## Reddit Traffic (Kostenlos, sehr effektiv)
Relevante Subreddits:
${config.productType === "Notion Template" ? "r/Notion, r/productivity, r/PKMS, r/GetMotivated" :
  config.productType === "Prompt Pack" ? "r/ChatGPT, r/artificial, r/productivity, r/MachineLearning" :
  "r/entrepreneur, r/sidehustle, r/passive_income, r/digitalnomad"}

Strategie:
- Poste hilfreiche Antworten (kein Spam!)
- Nach 3–5 hilfreichen Posts → Erwähne Produkt als Ressource
- "Ich habe das zu einem vollständigen [Produkt] zusammengefasst: [Link]"

## Pinterest (Langfristiger Traffic-Motor)
- 5 Pins/Tag (Canva-Templates, 2:3 Format)
- Keywords: "${config.productType}", "${config.productType} free", "best ${config.productType} 2025"
- Setzt nach 3–6 Monaten Compounding-Traffic ein

## Affiliate-Programm Setup
- 30–50% Provision anbieten
- Gumroad hat eingebautens Affiliate-System
- Finde 5–10 Micro-Creator in deiner Nische
- Jeder bringt 2–5 Verkäufe/Monat

## Monatliche Projektionen
| Monat | Verkäufe | Einnahmen |
|-------|----------|-----------|
| 1 | ${Math.round(config.targetSales * 0.3)} | $${Math.round(config.productPrice * config.targetSales * 0.3)} |
| 2 | ${Math.round(config.targetSales * 0.6)} | $${Math.round(config.productPrice * config.targetSales * 0.6)} |
| 3 | ${config.targetSales} | $${config.productPrice * config.targetSales} |
| 6 | ${config.targetSales * 2} | $${config.productPrice * config.targetSales * 2} (mit Affiliates) |`;

  log("✅ Digital Products System komplett!", "success");
  log("📦 Produkt-Blueprint + Sales Page erstellt", "success");
  log("📣 Marketing Kit (TikTok, Reddit, Pinterest) bereit", "success");
  log(`💰 Monatsziel: ${config.targetSales} Verkäufe = $${config.productPrice * config.targetSales}`, "success");

  return {
    "product-system.txt": productSystem,
    "product-blueprint.md": productBlueprint,
    "marketing-kit.md": marketingKit
  };
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function QuickCashSystem() {
  const [activeTab, setActiveTab] = useState("dashboard");
  const [dark, setDark] = useState(true);
  const [logs, setLogs] = useState([]);
  const [running, setRunning] = useState(new Set());
  const [configs, setConfigs] = useState({});
  const [assets, setAssets] = useState({});
  const [toolStats, setToolStats] = useState({});

  const addStats = (toolId, tokensIn, tokensOut, ms) => {
    const costIn  = tokensIn  * 0.000003;
    const costOut = tokensOut * 0.000015;
    setToolStats(prev => {
      const s = prev[toolId] || { runs: 0, tokensIn: 0, tokensOut: 0, cost: 0, lastMs: 0 };
      return {
        ...prev,
        [toolId]: {
          runs:      s.runs + 1,
          tokensIn:  s.tokensIn  + tokensIn,
          tokensOut: s.tokensOut + tokensOut,
          cost:      s.cost + costIn + costOut,
          lastMs:    ms
        }
      };
    });
  };

  const log = (toolId) => (msg, type = "info") => {
    setLogs(prev => [...prev, { toolId, msg, type, ts: new Date().toLocaleTimeString("de", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) }]);
  };

  const setConfig = (toolId, field, val) =>
    setConfigs(prev => ({ ...prev, [toolId]: { ...prev[toolId], [field]: val } }));

  const runTool = async (tool) => {
    const cfg = configs[tool.id] || {};
    const missing = tool.fields.filter(f => !cfg[f.name]);
    if (missing.length) {
      log(tool.id)(`Bitte alle Felder ausfüllen: ${missing.map(f => f.label).join(", ")}`, "error");
      setActiveTab("dashboard");
      return;
    }
    setRunning(prev => new Set([...prev, tool.id]));
    try {
      let result;
      const statsFn = (tIn, tOut, ms) => addStats(tool.id, tIn, tOut, ms);
      if (tool.id === 1) result = await runAIServiceArbitrage(cfg, log(tool.id), statsFn);
      if (tool.id === 2) result = await runLeadGenerator(cfg, log(tool.id), statsFn);
      if (tool.id === 3) result = await runUpworkAutomation(cfg, log(tool.id), statsFn);
      if (tool.id === 4) result = await runColdOutreach(cfg, log(tool.id), statsFn);
      if (tool.id === 5) result = await runUGCCreator(cfg, log(tool.id), statsFn);
      if (tool.id === 6) result = await runFacelessYouTube(cfg, log(tool.id), statsFn);
      if (tool.id === 7) result = await runNewsletterGhostwriting(cfg, log(tool.id), statsFn);
      if (tool.id === 8) result = await runDigitalProducts(cfg, log(tool.id), statsFn);
      if (result) setAssets(prev => ({ ...prev, [tool.id]: result }));
      setActiveTab("dashboard");
    } catch (e) {
      log(tool.id)("Fehler: " + e.message, "error");
    } finally {
      setRunning(prev => { const s = new Set(prev); s.delete(tool.id); return s; });
    }
  };

  const downloadFile = (name, content) => {
    const blob = new Blob([content], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = name; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <style>{css}</style>
      <div className={`shell ${dark ? "" : "light"}`}>

        {/* Topbar */}
        <header className="topbar">
          <div className="logo-row">
            <div className="logo-icon"><Zap size={20} /></div>
            <div>
              <div className="logo-title">Quick Cash System</div>
              <div className="logo-sub">Erste $100–500 in 1–4 Wochen</div>
            </div>
          </div>
          <button className="theme-btn" onClick={() => setDark(d => !d)}>
            {dark ? <Sun size={16} /> : <Moon size={16} />}
          </button>
        </header>

        <div className="body-wrap">
          {/* Sidebar */}
          <aside className="sidebar">
            {[
              { id: "dashboard", icon: BarChart3, label: "Dashboard" },
              { id: "tools", icon: Rocket, label: "Quick Cash Tools" },
              { id: "downloads", icon: Download, label: "Downloads" + (Object.keys(assets).length ? ` (${Object.keys(assets).length})` : "") }
            ].map(tab => (
              <button
                key={tab.id}
                className={`nav-btn${activeTab === tab.id ? " active" : ""}`}
                onClick={() => setActiveTab(tab.id)}
              >
                <tab.icon size={16} />
                {tab.label}
              </button>
            ))}

            <div className="sidebar-card">
              <div className="sidebar-card-title"><TrendingUp size={12} /> Realistische Zahlen</div>
              {[["Woche 1", "$0–200"], ["Woche 2", "$100–500"], ["Woche 3", "$300–800"], ["Woche 4", "$500–1200"]].map(([w, v]) => (
                <div className="timeline-row" key={w}>
                  <span>{w}</span><span>{v}</span>
                </div>
              ))}
            </div>
          </aside>

          {/* Main Content */}
          <main className="main">

            {/* ── DASHBOARD ── */}
            {activeTab === "dashboard" && (
              <div>
                <div className="section-title">Dashboard</div>
                <div className="section-sub">Live-Output & Systemübersicht</div>

                {Object.keys(toolStats).length > 0 && (() => {
                  const totCost = Object.values(toolStats).reduce((a, s) => a + s.cost, 0);
                  const totIn   = Object.values(toolStats).reduce((a, s) => a + s.tokensIn, 0);
                  const totOut  = Object.values(toolStats).reduce((a, s) => a + s.tokensOut, 0);
                  const totRuns = Object.values(toolStats).reduce((a, s) => a + s.runs, 0);
                  return (
                    <div className="global-stats">
                      <div className="gstat">
                        <div className="gstat-val" style={{ color: "var(--green)" }}>
                          {totCost < 0.01 ? "<$0.01" : "$" + totCost.toFixed(4)}
                        </div>
                        <div className="gstat-label">Gesamtkosten</div>
                      </div>
                      <div className="gstat">
                        <div className="gstat-val" style={{ color: "var(--blue)" }}>{totIn.toLocaleString()}</div>
                        <div className="gstat-label">Input Tokens</div>
                      </div>
                      <div className="gstat">
                        <div className="gstat-val" style={{ color: "var(--amber)" }}>{totOut.toLocaleString()}</div>
                        <div className="gstat-label">Output Tokens</div>
                      </div>
                      <div className="gstat">
                        <div className="gstat-val">{totRuns}</div>
                        <div className="gstat-label">Generierungen</div>
                      </div>
                    </div>
                  );
                })()}

                <div className="warn-banner">
                  <h3>⚠️ Das ist KEIN passives Einkommen!</h3>
                  <div className="warn-grid">
                    {["Aktive Arbeit erforderlich", "10–30 Std/Woche", "Service-Verkauf (Zeit gegen Geld)", "Schneller als SaaS/SEO/Blog"].map(t => (
                      <div className="warn-item" key={t}>
                        <CheckCircle size={14} color="var(--amber)" />
                        <span>{t}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="terminal-wrap">
                  <div className="terminal-header">
                    <div className="term-dot" style={{ background: "#ff5f57" }} />
                    <div className="term-dot" style={{ background: "#febc2e" }} />
                    <div className="term-dot" style={{ background: "#28c840" }} />
                    <span style={{ marginLeft: 8, fontSize: 11, color: "var(--muted)", fontFamily: "var(--mono)" }}>system.log</span>
                  </div>
                  <div className="term-body">
                    {logs.length === 0 ? (
                      <div className="term-empty">
                        <Rocket size={36} />
                        <p>Bereit. Wähle ein Quick Cash Tool.</p>
                      </div>
                    ) : (
                      logs.map((l, i) => (
                        <div key={i} className={`term-line-${l.type}`}>
                          <span className="term-stamp">[{l.ts}]</span>{l.msg}
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* ── TOOLS ── */}
            {activeTab === "tools" && (
              <div>
                <div className="section-title">Quick Cash Tools</div>
                <div className="section-sub">Fülle die Felder aus → Klicke "System Generieren" → Lade Assets herunter</div>

                {quickCashTools.map(tool => (
                  <div className="tool-card" key={tool.id}>
                    <div className="tool-head">
                      <div className="tool-name">{tool.name}</div>
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        {tool.badge && (
                          <span style={{ fontSize: 10, fontWeight: 700, padding: "3px 8px", borderRadius: 20, background: "var(--red-dim)", color: "var(--red)", fontFamily: "var(--mono)" }}>
                            {tool.badge}
                          </span>
                        )}
                        <div className="tool-cat">{tool.category}</div>
                      </div>
                    </div>
                    <div className="tool-desc">{tool.description}</div>
                    <div className="badges">
                      <span className="badge badge-green">⏱ {tool.timeToFirstDollar}</span>
                      <span className="badge badge-blue">💰 {tool.weeklyPotential}/Woche</span>
                      <span className="badge badge-amber">{tool.effort} Aufwand</span>
                    </div>
                    <div className="platforms">Plattformen: {tool.platforms.join("  ·  ")}</div>

                    <div className="fields-grid">
                      {tool.fields.map(f => (
                        <div key={f.name}>
                          <label className="field-label">{f.label}</label>
                          {f.type === "select" ? (
                            <select
                              className="field-select"
                              value={configs[tool.id]?.[f.name] || ""}
                              onChange={e => setConfig(tool.id, f.name, e.target.value)}
                            >
                              <option value="">Wähle…</option>
                              {f.options.map(o => <option key={o} value={o}>{o}</option>)}
                            </select>
                          ) : (
                            <input
                              type={f.type}
                              className="field-input"
                              value={configs[tool.id]?.[f.name] || ""}
                              onChange={e => setConfig(tool.id, f.name, e.target.value)}
                              placeholder={f.placeholder}
                            />
                          )}
                        </div>
                      ))}
                    </div>

                    {toolStats[tool.id] && (() => {
                      const s = toolStats[tool.id];
                      const costStr = s.cost < 0.01 ? "<$0.01" : "$" + s.cost.toFixed(4);
                      const barPct  = Math.min(100, (s.cost / 0.05) * 100);
                      return (
                        <div className="cost-dash">
                          <div className="cost-dash-title">
                            <DollarSign size={10} /> API-Kosten Dashboard
                          </div>
                          <div className="cost-metrics">
                            <div className="cost-metric">
                              <div className="cost-metric-val green">{costStr}</div>
                              <div className="cost-metric-label">Gesamt</div>
                            </div>
                            <div className="cost-metric">
                              <div className="cost-metric-val blue">{s.tokensIn.toLocaleString()}</div>
                              <div className="cost-metric-label">Tokens In</div>
                            </div>
                            <div className="cost-metric">
                              <div className="cost-metric-val amber">{s.tokensOut.toLocaleString()}</div>
                              <div className="cost-metric-label">Tokens Out</div>
                            </div>
                            <div className="cost-metric">
                              <div className="cost-metric-val">{s.runs}×</div>
                              <div className="cost-metric-label">Runs</div>
                            </div>
                            <div className="cost-metric">
                              <div className="cost-metric-val" style={{ color: s.lastMs > 5000 ? "var(--amber)" : "var(--green)" }}>
                                {(s.lastMs / 1000).toFixed(1)}s
                              </div>
                              <div className="cost-metric-label">Laufzeit</div>
                            </div>
                          </div>
                          <div className="cost-bar-wrap">
                            <div className="cost-bar-fill" style={{ width: barPct + "%" }} />
                          </div>
                        </div>
                      );
                    })()}

                    <button
                      className="run-btn"
                      onClick={() => runTool(tool)}
                      disabled={running.has(tool.id)}
                    >
                      {running.has(tool.id) ? (
                        <><Terminal size={16} className="spin" /> Generiert…</>
                      ) : (
                        <><Zap size={16} /> System Generieren</>
                      )}
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* ── DOWNLOADS ── */}
            {activeTab === "downloads" && (
              <div>
                <div className="section-title">Generierte Assets</div>
                <div className="section-sub">Download deine Quick Cash Systeme</div>

                {Object.keys(assets).length === 0 ? (
                  <div className="empty-state">
                    <Download size={48} />
                    <p>Noch keine Systeme generiert</p>
                    <small>Gehe zu Quick Cash Tools → starte ein System</small>
                  </div>
                ) : (
                  Object.entries(assets).map(([toolId, files]) => {
                    const tool = quickCashTools.find(t => t.id === parseInt(toolId));
                    return (
                      <div className="dl-card" key={toolId}>
                        <div style={{ fontWeight: 800, fontSize: 15 }}>{tool?.name}</div>
                        <div className="dl-grid">
                          {Object.entries(files).map(([name, content]) => (
                            <button key={name} className="dl-btn" onClick={() => downloadFile(name, content)}>
                              <Download size={18} />
                              <div>
                                <div className="dl-btn-name">{name}</div>
                                <div className="dl-btn-sub">Klick zum Download</div>
                              </div>
                            </button>
                          ))}
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            )}
          </main>
        </div>
      </div>
    </>
  );
}
