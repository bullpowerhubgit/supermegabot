import { useState } from "react";

const PRICE_IN  = 0.000003;
const PRICE_OUT = 0.000015;

const MODULES = [
  {
    id: "fiverr", icon: "🎯", label: "Fiverr Gig", color: "#00ff88",
    fields: [
      { key: "service", label: "Service",   placeholder: "z.B. Logo Design" },
      { key: "price",   label: "Preis ($)", placeholder: "z.B. 49" },
    ],
    prompt: (f) =>
      `Erstelle einen kompletten Fiverr Gig auf Englisch.\nService: ${f.service}\nPreis: $${f.price}\n\nBrauche:\n1. GIG TITLE (SEO, max 80 Zeichen)\n2. BESCHREIBUNG (300 Woerter, Bullets)\n3. 3 PAKETE (Basic/Standard/Premium)\n4. 5 TAGS\n5. FAQ (3 Fragen)`,
  },
  {
    id: "upwork", icon: "💼", label: "Upwork Proposal", color: "#14a800",
    fields: [
      { key: "job",   label: "Job-Titel",       placeholder: "z.B. React Developer needed" },
      { key: "skill", label: "Dein Skill",       placeholder: "z.B. React, Copywriting" },
      { key: "rate",  label: "Stundensatz ($)",  placeholder: "z.B. 45" },
    ],
    prompt: (f) =>
      `Schreibe ein Upwork Proposal auf Englisch.\nJob: ${f.job}\nSkill: ${f.skill}\nRate: $${f.rate}/h\n\nAnforderungen:\n- Starker Hook (kein "I saw your job posting")\n- Schmerz des Clients ansprechen\n- Ergebnis zeigen\n- CTA am Ende\n- Max 200 Woerter\n\nNur das fertige Proposal, keine Erklaerungen.`,
  },
  {
    id: "leads", icon: "📍", label: "Local Lead Gen", color: "#ff6b35",
    fields: [
      { key: "niche", label: "Branche",        placeholder: "z.B. Zahnarzt, Restaurant" },
      { key: "city",  label: "Stadt",           placeholder: "z.B. Muenchen" },
      { key: "lead",  label: "Preis/Lead ($)",  placeholder: "z.B. 20" },
    ],
    prompt: (f) =>
      `Local Lead Generation Strategie auf Deutsch.\nBranche: ${f.niche} | Stadt: ${f.city} | Preis/Lead: $${f.lead}\n\n1. Zielgruppen-Analyse\n2. Top 3 Lead-Kanaele\n3. Kalt-Ansprache Skript (Email)\n4. Pricing-Paket\n5. 30-Tage Aktionsplan`,
  },
  {
    id: "outreach", icon: "📧", label: "Cold Outreach", color: "#a855f7",
    fields: [
      { key: "service", label: "Dein Service",   placeholder: "z.B. AI Automatisierung" },
      { key: "target",  label: "Zielgruppe",     placeholder: "z.B. E-Commerce Shops" },
      { key: "value",   label: "Wert ($)",        placeholder: "z.B. 500" },
    ],
    prompt: (f) =>
      `Cold Email Sequenz auf Englisch.\nAngebot: ${f.service} | Zielgruppe: ${f.target} | Wert: $${f.value}\n\n1. Email 1 – Erstkontakt (Hook + Value + CTA)\n2. Email 2 – Follow-up Tag 3\n3. Email 3 – Breakup Email Tag 7\n4. Subject Lines (3x pro Mail)\n5. LinkedIn Nachricht (max 300 Zeichen)\n\nJede Email max 100 Woerter.`,
  },
  {
    id: "ugc", icon: "🎬", label: "UGC Agency", color: "#ec4899",
    fields: [
      { key: "niche", label: "Nische",          placeholder: "z.B. Beauty, Fitness" },
      { key: "price", label: "Preis/Video ($)", placeholder: "z.B. 150" },
    ],
    prompt: (f) =>
      `UGC Agency Business Plan auf Deutsch.\nNische: ${f.niche} | Preis/Video: $${f.price}\n\n1. Business Model erklaeren\n2. Creator Rekrutierung (wo + wie)\n3. Angebot an Marken (3 Pakete)\n4. Pitch-Template (Englisch)\n5. Creator Briefing-Template\n6. Umsatz-Prognose Monat 1-3`,
  },
  {
    id: "youtube", icon: "📺", label: "YouTube Faceless", color: "#ff4444",
    fields: [
      { key: "niche", label: "Nische",         placeholder: "z.B. True Crime, Finance" },
      { key: "freq",  label: "Videos/Woche",   placeholder: "z.B. 2" },
    ],
    prompt: (f) =>
      `Faceless YouTube Strategie auf Deutsch.\nNische: ${f.niche} | Frequenz: ${f.freq}x/Woche\n\n1. Kanal-Konzept + Name\n2. 10 Video-Ideen (SEO-Titel auf Englisch)\n3. Produktions-Workflow (Tools)\n4. Monetarisierung\n5. 6-Monats Wachstumsplan\n6. Beispiel-Skript Video 1 (Englisch, 250 Woerter)`,
  },
  {
    id: "newsletter", icon: "✉️", label: "Newsletter Ghost", color: "#f59e0b",
    fields: [
      { key: "topic",   label: "Thema",           placeholder: "z.B. AI, Marketing" },
      { key: "price",   label: "Preis/Monat ($)",  placeholder: "z.B. 300" },
      { key: "clients", label: "Zielkunden",        placeholder: "z.B. Coaches, CEOs" },
    ],
    prompt: (f) =>
      `Newsletter Ghostwriting Business auf Deutsch.\nThema: ${f.topic} | Preis: $${f.price}/Monat | Kunden: ${f.clients}\n\n1. Service-Positionierung\n2. Pitch an Kunden (Englisch, 150 Woerter)\n3. Newsletter-Struktur Template\n4. Beispiel-Newsletter (vollstaendig, Englisch)\n5. Workflow pro Ausgabe\n6. Skalierungsplan`,
  },
  {
    id: "digital", icon: "🛒", label: "Digital Products", color: "#06b6d4",
    fields: [
      { key: "product",  label: "Produkt",     placeholder: "z.B. Prompt Pack, E-Book" },
      { key: "price",    label: "Preis ($)",   placeholder: "z.B. 27" },
      { key: "platform", label: "Plattform",   placeholder: "z.B. Gumroad, Etsy" },
    ],
    prompt: (f) =>
      `Digital Product Launch Plan auf Deutsch.\nProdukt: ${f.product} | Preis: $${f.price} | Plattform: ${f.platform}\n\n1. Sales Copy (Englisch, ueberzeugend)\n2. Produkt-Struktur / Inhalt\n3. Sales Page (Headline + Bullets + CTA)\n4. Launch Strategie (erste 100 Verkaeufe)\n5. Upsell Ideen\n6. 90-Tage Umsatz-Projektion`,
  },
];

const S = {
  app:     { fontFamily: "monospace", background: "#070b10", minHeight: "100vh", color: "#e6edf3", display: "flex", flexDirection: "column" },
  header:  { background: "#0d1117", borderBottom: "1px solid #1e2733", padding: "10px 16px", display: "flex", alignItems: "center", gap: "10px" },
  monitor: { background: "#0a0f16", borderBottom: "1px solid #ffd70033", padding: "7px 14px", display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" },
  body:    { display: "flex", flex: 1, overflow: "hidden" },
  sidebar: { width: "105px", background: "#0d1117", borderRight: "1px solid #1e2733", padding: "8px", display: "flex", flexDirection: "column", gap: "5px", overflowY: "auto" },
  main:    { flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" },
  row:     { flex: 1, display: "flex", overflow: "hidden" },
  inputs:  { width: "250px", padding: "14px", borderRight: "1px solid #1e2733", overflowY: "auto" },
  output:  { flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" },
  outHead: { padding: "7px 12px", background: "#0d1117", borderBottom: "1px solid #1e2733", display: "flex", alignItems: "center", gap: "8px" },
  outBody: { flex: 1, padding: "14px", overflowY: "auto", whiteSpace: "pre-wrap", fontSize: "12px", lineHeight: "1.8", fontFamily: "monospace" },
  log:     { height: "90px", background: "#050810", borderTop: "1px solid #1e2733", padding: "6px 12px", overflowY: "auto" },
};

function MonBox({ label, value, color, sub }) {
  return (
    <div style={{ background: "#070b10", border: "1px solid #1e2733", borderRadius: "5px", padding: "4px 9px", minWidth: "70px" }}>
      <div style={{ color: "#3d4a5c", fontSize: "7px", letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: "1px" }}>{label}</div>
      <div style={{ color, fontSize: "13px", fontWeight: "700" }}>{value}</div>
      {sub && <div style={{ color: "#3d4a5c", fontSize: "7px" }}>{sub}</div>}
    </div>
  );
}

export default function App() {
  const [active, setActive]   = useState("fiverr");
  const [fields, setFields]   = useState({});
  const [output, setOutput]   = useState("");
  const [logs,   setLogs]     = useState(["// Bereit. Modul waehlen und Felder ausfuellen."]);
  const [busy,   setBusy]     = useState(false);
  const [stats,  setStats]    = useState([]);
  const [apiKey, setApiKey]   = useState(() => localStorage.getItem('anthropic_api_key') || '');

  const mod = MODULES.find((m) => m.id === active);
  const log = (msg) => setLogs((p) => [...p.slice(-40), msg]);

  const totalCost = stats.reduce((a, s) => a + s.cost, 0);
  const totalIn   = stats.reduce((a, s) => a + s.tokIn, 0);
  const totalOut  = stats.reduce((a, s) => a + s.tokOut, 0);
  const last      = stats[stats.length - 1];

  const run = async () => {
    if (!mod) return;
    const missing = mod.fields.filter((f) => !fields[f.key]?.trim());
    if (missing.length) { log("❌ Fehlende Felder: " + missing.map((f) => f.label).join(", ")); return; }

    setBusy(true);
    setOutput("");
    log("🔄 Starte " + mod.label + "…");

    try {
      // Try to load API config for direct API calls
      let apiKeyToUse = apiKey || '';
      let apiUrl = 'https://api.anthropic.com/v1/messages';
      let model = 'claude-sonnet-4-5';
      
      try {
        const configResponse = await fetch('./api-config.json');
        if (configResponse.ok) {
          const config = await configResponse.json();
          if (config.anthropic?.apiKey) {
            apiKeyToUse = config.anthropic.apiKey;
            model = config.anthropic.model || model;
          }
        }
      } catch (e) {
        // Use state apiKey as fallback
      }

      if (!apiKeyToUse) {
        log("❌ Bitte API Key eingeben");
        return;
      }

      const headers = { "Content-Type": "application/json" };
      headers["x-api-key"] = apiKeyToUse;
      headers["anthropic-version"] = "2023-06-01";

      const res = await fetch(apiUrl, {
        method: "POST",
        headers: headers,
        body: JSON.stringify({
          model: model,
          max_tokens: 1000,
          messages: [{ role: "user", content: mod.prompt(fields) }],
        }),
      });

      if (!res.ok) {
        const err = await res.text();
        throw new Error(`HTTP ${res.status}: ${err.slice(0, 120)}`);
      }

      const data = await res.json();
      const text = (data.content || []).map((b) => b.text || "").join("");
      if (!text) throw new Error("Leere API-Antwort");

      setOutput(text);

      const tokIn  = data.usage?.input_tokens  || 0;
      const tokOut = data.usage?.output_tokens || 0;
      const cost   = tokIn * PRICE_IN + tokOut * PRICE_OUT;
      setStats((p) => [...p, { mod: mod.label, tokIn, tokOut, cost }]);
      log(`✅ Fertig! ${tokIn} IN · ${tokOut} OUT · $${cost.toFixed(5)}`);

    } catch (e) {
      log("❌ " + e.message);
    } finally {
      setBusy(false);
    }
  };

  const inputStyle = (key) => ({
    background: "#0d1117",
    border: `1px solid ${fields[key] ? (mod?.color + "55") : "#1e2733"}`,
    borderRadius: "6px", color: "#e6edf3",
    padding: "8px 10px", width: "100%",
    fontSize: "12px", outline: "none",
    boxSizing: "border-box", fontFamily: "monospace",
  });

  const btnStyle = {
    width: "100%", padding: "10px",
    background: busy ? "#1e2733" : (mod?.color + "18" || "#1e2733"),
    border: `1px solid ${busy ? "#1e2733" : (mod?.color || "#1e2733")}`,
    borderRadius: "6px",
    color: busy ? "#3d4a5c" : (mod?.color || "#e6edf3"),
    cursor: busy ? "not-allowed" : "pointer",
    fontFamily: "monospace", fontSize: "12px",
    fontWeight: "700", letterSpacing: "0.06em",
    marginTop: "8px",
  };

  return (
    <div style={S.app}>

      {/* ── HEADER ── */}
      <div style={S.header}>
        <span style={{ fontSize: "18px" }}>⚡</span>
        <div>
          <div style={{ color: "#00ff88", fontWeight: "700", fontSize: "13px", letterSpacing: "0.08em" }}>AI SERVICE ARBITRAGE SYSTEM</div>
          <div style={{ color: "#3d4a5c", fontSize: "9px" }}>Buy AI · Sell to Clients · Print Money</div>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", gap: "8px", alignItems: "center" }}>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => { setApiKey(e.target.value); localStorage.setItem('anthropic_api_key', e.target.value); }}
            placeholder="Anthropic API Key"
            style={{ background: "#0d1117", border: "1px solid #1e2733", borderRadius: "4px", color: "#e6edf3", padding: "4px 8px", fontSize: "10px", width: "180px", outline: "none" }}
          />
          {["#ff5f57","#ffbd2e","#28c940"].map(c => <div key={c} style={{ width: "8px", height: "8px", borderRadius: "50%", background: c }} />)}
        </div>
      </div>

      {/* ── COST MONITOR ── */}
      <div style={S.monitor}>
        <span style={{ color: "#ffd700", fontSize: "9px", letterSpacing: "0.1em", marginRight: "4px" }}>💰 COST MONITOR</span>
        <MonBox label="Session $"   value={`$${totalCost.toFixed(5)}`} color="#ff6b35" />
        <MonBox label="API Calls"   value={stats.length}               color="#a855f7" />
        <MonBox label="Tokens IN"   value={totalIn.toLocaleString()}   color="#8892a4" sub="$3/1M" />
        <MonBox label="Tokens OUT"  value={totalOut.toLocaleString()}  color="#8892a4" sub="$15/1M" />
        {last && <>
          <div style={{ width: "1px", height: "28px", background: "#1e2733" }} />
          <MonBox label="Letzter Call" value={`$${last.cost.toFixed(5)}`}           color="#00ff88" sub={last.mod} />
          <MonBox label="IN / OUT"     value={`${last.tokIn} / ${last.tokOut}`}     color="#06b6d4" sub="tokens" />
        </>}
        {stats.length > 0 && (
          <button onClick={() => setStats([])} style={{ marginLeft: "auto", background: "none", border: "1px solid #1e2733", borderRadius: "4px", color: "#3d4a5c", padding: "2px 8px", cursor: "pointer", fontSize: "8px", fontFamily: "monospace" }}>
            RESET
          </button>
        )}
      </div>

      <div style={S.body}>

        {/* ── SIDEBAR ── */}
        <div style={S.sidebar}>
          {MODULES.map((m) => (
            <button
              key={m.id}
              onClick={() => { setActive(m.id); setFields({}); setOutput(""); }}
              style={{ background: active === m.id ? m.color + "15" : "transparent", border: `1px solid ${active === m.id ? m.color : "#1e2733"}`, borderRadius: "7px", padding: "8px 6px", cursor: "pointer", textAlign: "left", width: "100%" }}
            >
              <div style={{ fontSize: "16px", marginBottom: "2px" }}>{m.icon}</div>
              <div style={{ color: active === m.id ? m.color : "#4a5568", fontSize: "8px", fontWeight: "700", letterSpacing: "0.03em", fontFamily: "monospace", wordBreak: "break-word" }}>
                {m.label.toUpperCase()}
              </div>
            </button>
          ))}
          {/* Kalkulation */}
          <button
            onClick={() => { setActive("calc"); setOutput(""); }}
            style={{ background: active === "calc" ? "#ffd70015" : "transparent", border: `1px solid ${active === "calc" ? "#ffd700" : "#1e2733"}`, borderRadius: "7px", padding: "8px 6px", cursor: "pointer", textAlign: "left", width: "100%" }}
          >
            <div style={{ fontSize: "16px", marginBottom: "2px" }}>💰</div>
            <div style={{ color: active === "calc" ? "#ffd700" : "#4a5568", fontSize: "8px", fontWeight: "700", fontFamily: "monospace" }}>KALKULATION</div>
          </button>
        </div>

        {/* ── MAIN ── */}
        <div style={S.main}>
          <div style={S.row}>

            {/* ── INPUT PANEL ── */}
            <div style={S.inputs}>
              {active === "calc" ? (
                <CalcPanel />
              ) : mod ? (
                <>
                  <div style={{ color: mod.color, fontSize: "15px", fontWeight: "700", marginBottom: "14px" }}>
                    {mod.icon} {mod.label}
                  </div>
                  {mod.fields.map((f) => (
                    <div key={f.key} style={{ marginBottom: "10px" }}>
                      <div style={{ color: "#8892a4", fontSize: "9px", letterSpacing: "0.05em", marginBottom: "4px", textTransform: "uppercase" }}>{f.label}</div>
                      <input
                        value={fields[f.key] || ""}
                        placeholder={f.placeholder}
                        onChange={(e) => setFields((p) => ({ ...p, [f.key]: e.target.value }))}
                        style={inputStyle(f.key)}
                      />
                    </div>
                  ))}
                  <button onClick={run} disabled={busy} style={btnStyle}>
                    {busy ? "⏳ GENERIERE…" : "▶  STARTEN"}
                  </button>
                </>
              ) : null}
            </div>

            {/* ── OUTPUT ── */}
            <div style={S.output}>
              <div style={S.outHead}>
                <div style={{ width: "7px", height: "7px", borderRadius: "50%", background: busy ? "#ffd700" : "#00ff88" }} />
                <span style={{ color: "#8892a4", fontSize: "9px", letterSpacing: "0.07em" }}>OUTPUT</span>
                {output && (
                  <button onClick={() => navigator.clipboard.writeText(output)}
                    style={{ marginLeft: "auto", background: "none", border: "1px solid #1e2733", borderRadius: "4px", color: "#8892a4", padding: "2px 8px", cursor: "pointer", fontSize: "9px", fontFamily: "monospace" }}>
                    📋 COPY
                  </button>
                )}
              </div>
              <div style={{ ...S.outBody, color: output ? "#e6edf3" : "#2d3a4a" }}>
                {output || "// Output erscheint hier...\n// Felder ausfullen → ▶ STARTEN"}
              </div>
            </div>
          </div>

          {/* ── LOG ── */}
          <div style={S.log}>
            <div style={{ color: "#2d3a4a", fontSize: "7px", letterSpacing: "0.1em", marginBottom: "4px" }}>SYSTEM LOG</div>
            {logs.map((l, i) => (
              <div key={i} style={{ fontSize: "10px", lineHeight: "1.7", color: l.startsWith("✅") ? "#00ff88" : l.startsWith("❌") ? "#ff4444" : l.startsWith("🔄") ? "#f59e0b" : "#8892a4" }}>
                {l}
              </div>
            ))}
          </div>
        </div>
      </div>

      <style>{`
        button:hover { opacity: 0.85; }
        input::placeholder { color: #252f3a; }
        ::-webkit-scrollbar { width: 3px; }
        ::-webkit-scrollbar-thumb { background: #1e2733; border-radius: 2px; }
      `}</style>
    </div>
  );
}

function CalcPanel() {
  const [buy, setBuy]     = useState(0.05);
  const [sell, setSell]   = useState(49);
  const [vol, setVol]     = useState(10);
  const profit = (sell - buy) * vol;
  const roi    = (((sell - buy) * vol) / (buy * vol || 0.001) * 100).toFixed(0);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
      <div style={{ color: "#ffd700", fontSize: "14px", fontWeight: "700" }}>💰 Preiskalkulation</div>
      {[
        { label: "AI-Kosten / Gig ($)", val: buy,  set: setBuy,  step: "0.001" },
        { label: "Verkaufspreis ($)",    val: sell, set: setSell, step: "1" },
        { label: "Gigs / Monat",         val: vol,  set: setVol,  step: "1" },
      ].map((f) => (
        <div key={f.label}>
          <div style={{ color: "#8892a4", fontSize: "9px", letterSpacing: "0.05em", marginBottom: "4px", textTransform: "uppercase" }}>{f.label}</div>
          <input type="number" step={f.step} value={f.val}
            onChange={(e) => f.set(parseFloat(e.target.value) || 0)}
            style={{ background: "#0d1117", border: "1px solid #1e2733", borderRadius: "6px", color: "#e6edf3", padding: "8px 10px", width: "100%", fontSize: "13px", outline: "none", boxSizing: "border-box", fontFamily: "monospace" }}
          />
        </div>
      ))}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", marginTop: "4px" }}>
        {[
          { label: "Marge / Gig",      val: `$${(sell - buy).toFixed(2)}`,        color: "#00ff88" },
          { label: "Umsatz / Monat",   val: `$${(sell * vol).toFixed(2)}`,         color: "#ffd700" },
          { label: "AI-Kosten / Mon.", val: `$${(buy * vol).toFixed(4)}`,          color: "#ff6b35" },
          { label: "Profit / Monat",   val: `$${profit.toFixed(2)}`,               color: "#00ff88" },
          { label: "ROI",              val: `${roi}%`,                             color: "#a855f7" },
          { label: "Marge %",          val: `${((sell - buy) / sell * 100).toFixed(1)}%`, color: "#06b6d4" },
        ].map((s) => (
          <div key={s.label} style={{ background: "#0d1117", border: "1px solid #1e2733", borderRadius: "7px", padding: "9px" }}>
            <div style={{ color: "#8892a4", fontSize: "9px", marginBottom: "2px" }}>{s.label}</div>
            <div style={{ color: s.color, fontSize: "16px", fontWeight: "700" }}>{s.val}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
