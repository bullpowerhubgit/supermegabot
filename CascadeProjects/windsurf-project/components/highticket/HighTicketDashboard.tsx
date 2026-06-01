import { useState, useRef } from "react";

const CATEGORIES = [
  { id: "watches", label: "Uhren", icon: "⌚", avg: 28000 },
  { id: "jewelry", label: "Schmuck", icon: "💎", avg: 45000 },
  { id: "cars", label: "Fahrzeuge", icon: "🚗", avg: 180000 },
  { id: "realestate", label: "Immobilien", icon: "🏛️", avg: 850000 },
  { id: "art", label: "Kunst", icon: "🖼️", avg: 62000 },
  { id: "coaching", label: "Coaching/B2B", icon: "🎯", avg: 35000 },
];

const CHANNELS = ["Shopify", "Instagram", "WhatsApp", "Email", "Telefon", "Messe"];

const MOCK_PRODUCTS = [
  { id: 1, name: "Patek Philippe Nautilus 5711", category: "watches", price: 142000, margin: 18, stock: 2, trend: "+12%", channel: "Instagram", status: "hot" },
  { id: 2, name: "Rolex Daytona Weißgold", category: "watches", price: 68500, margin: 22, stock: 5, trend: "+8%", channel: "Shopify", status: "active" },
  { id: 3, name: "Ferrari SF90 Stradale", category: "cars", price: 520000, margin: 8, stock: 1, trend: "+3%", channel: "WhatsApp", status: "hot" },
  { id: 4, name: "Penthouse Frankfurt Westend", category: "realestate", price: 3200000, margin: 4, stock: 1, trend: "+15%", channel: "Email", status: "active" },
  { id: 5, name: "Cartier Love Armreif Platin", category: "jewelry", price: 24800, margin: 35, stock: 8, trend: "+6%", channel: "Instagram", status: "active" },
  { id: 6, name: "Banksy 'Girl with Balloon'", category: "art", price: 185000, margin: 12, stock: 1, trend: "+28%", channel: "Messe", status: "hot" },
  { id: 7, name: "1:1 Business Mastermind 12M", category: "coaching", price: 48000, margin: 82, stock: 3, trend: "+20%", channel: "Telefon", status: "active" },
  { id: 8, name: "Porsche 911 GT3 RS", category: "cars", price: 268000, margin: 11, stock: 2, trend: "+5%", channel: "WhatsApp", status: "active" },
];

const MOCK_LEADS = [
  { id: 1, name: "Dr. Klaus Berger", value: 142000, stage: "Angebot", channel: "Instagram", probability: 78, product: "Patek Philippe Nautilus" },
  { id: 2, name: "Familie Schneider", value: 3200000, stage: "Besichtigung", channel: "Email", probability: 45, product: "Penthouse Frankfurt" },
  { id: 3, name: "Hendrik Müller GmbH", value: 48000, stage: "Vertrag", channel: "Telefon", probability: 92, product: "Business Mastermind" },
  { id: 4, name: "Sophie Laurent", value: 68500, stage: "Erstgespräch", channel: "WhatsApp", probability: 30, product: "Rolex Daytona" },
  { id: 5, name: "Max Weidmann AG", value: 185000, stage: "Due Diligence", channel: "Messe", probability: 61, product: "Banksy Print" },
];

const formatEuro = (n) =>
  new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n);

export default function HighTicketDashboard() {
  const [tab, setTab] = useState("overview");
  const [aiQuery, setAiQuery] = useState("");
  const [aiResponse, setAiResponse] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [selectedChannel, setSelectedChannel] = useState("all");
  const [aiMode, setAiMode] = useState("sourcing");
  const [pricingInput, setPricingInput] = useState({ name: "", buyPrice: "", category: "watches", channel: "Instagram" });
  const [pricingResult, setPricingResult] = useState(null);
  const [pricingLoading, setPricingLoading] = useState(false);
  const [funnelLead, setFunnelLead] = useState({ name: "", product: "", value: "", channel: "WhatsApp" });
  const [funnelScript, setFunnelScript] = useState("");
  const [funnelLoading, setFunnelLoading] = useState(false);
  const aiInputRef = useRef(null);

  const totalRevenue = MOCK_PRODUCTS.reduce((s, p) => s + p.price * p.stock, 0);
  const totalLeadValue = MOCK_LEADS.reduce((s, l) => s + l.value * (l.probability / 100), 0);
  const hotProducts = MOCK_PRODUCTS.filter((p) => p.status === "hot").length;

  const filteredProducts = MOCK_PRODUCTS.filter(
    (p) =>
      (selectedCategory === "all" || p.category === selectedCategory) &&
      (selectedChannel === "all" || p.channel === selectedChannel)
  );

  const callClaude = async (systemPrompt, userMsg) => {
    // Claude API integration with fallback to mock mode
    const apiKey = localStorage.getItem('anthropic_api_key') || process.env.REACT_APP_ANTHROPIC_API_KEY;
    
    if (!apiKey) {
      // Mock response for demo purposes
      await new Promise(resolve => setTimeout(resolve, 800));
      const mockResponses = {
        sourcing: "Für Luxusuhren: Chrono24, WatchBox, Auktionen. Schmuck: Christie's, Sotheby's. Fahrzeuge: Mobile.de, Exklusivhändler. Immobilien: Engel & Völkers, Sotheby's. Coaching: LinkedIn, Mastermind Groups.",
        pricing: "Luxuspreise: 15-35% Marge bei Uhren, 25-45% bei Schmuck, 8-15% bei Fahrzeugen, 4-8% bei Immobilien, 70-85% bei Coaching. Psychologische Preisanker wichtig.",
        outreach: "WhatsApp: 'Guten Tag [Name], ich bemerkte Ihr Interesse an [Produkt]. Ich habe exklusiven Zugang zu [Besonderheit]. Wären Sie verfügbar für ein kurzes Gespräch?'",
        market: "Luxusmarkt DACH: +12% YoY. Uhren: Rolex, Patek Philippe dominieren. Immobilien: Frankfurt, München, Zürich stark. Coaching: Business Mastermind +28% Nachfrage."
      };
      return mockResponses[aiMode] || "Mock-Antwort: Bitte API-Key konfigurieren.";
    }

    try {
      const res = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: { 
          "Content-Type": "application/json",
          "x-api-key": apiKey,
          "anthropic-version": "2023-06-01"
        },
        body: JSON.stringify({
          model: "claude-3-sonnet-20240229",
          max_tokens: 1000,
          system: systemPrompt,
          messages: [{ role: "user", content: userMsg }],
        }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      return data.content?.[0]?.text || "Keine Antwort erhalten.";
    } catch (error) {
      console.error('Claude API Error:', error);
      return "API-Fehler. Bitte versuchen Sie es später erneut.";
    }
  };

  const handleAiQuery = async () => {
    if (!aiQuery.trim()) return;
    setAiLoading(true);
    setAiResponse("");
    const systems = {
      sourcing: `Du bist ein Ultra High-Ticket Sourcing Experte für Luxusgüter (10.000€+). 
Du kennst die besten Quellen für Luxusuhren, Schmuck, Luxusautos, High-End Immobilien und Premium Coaching.
Antworte präzise auf Deutsch. Gib konkrete Lieferanten, Marktplätze, Netzwerke und Strategien an.
Fokus: Beschaffung, Margen, Exklusivität, Vertrauensaufbau. Maximal 300 Wörter.`,
      pricing: `Du bist ein Pricing-Stratege für Ultra High-Ticket Luxusgüter (10.000€+).
Analysiere Preisstrategien, Margen, Positionierung und psychologische Preisgestaltung im Luxussegment.
Antworte auf Deutsch. Konkrete Zahlen und Prozente. Maximal 300 Wörter.`,
      outreach: `Du bist ein Ultra High-Ticket Sales Spezialist für vermögende Kunden (UHNWI).
Du schreibst hochpersonalisierte Outreach-Nachrichten für WhatsApp, E-Mail, Instagram DMs.
Ton: Exklusiv, vertrauenswürdig, niemals pushy. Deutsch. Maximal 300 Wörter.`,
      market: `Du bist ein Marktanalyst für Luxusgüter und Ultra High-Ticket Produkte.
Analysiere Trends, Nachfrage, saisonale Faktoren und Zielgruppen im Luxussegment (10.000€+).
Konkrete Insights für den DACH-Markt. Deutsch. Maximal 300 Wörter.`,
    };
    try {
      const text = await callClaude(systems[aiMode], aiQuery);
      setAiResponse(text);
    } catch (error) {
      setAiResponse("Fehler: " + (error instanceof Error ? error.message : "Unbekannter Fehler"));
    } finally {
      setAiLoading(false);
    }
  };

  const handlePricingAnalysis = async () => {
    if (!pricingInput.name || !pricingInput.buyPrice) return;
    setPricingLoading(true);
    setPricingResult(null);
    const prompt = `Analysiere dieses Ultra High-Ticket Produkt und gib mir eine JSON-Preisempfehlung:
Produkt: ${pricingInput.name}
Einkaufspreis: ${pricingInput.buyPrice}€
Kategorie: ${pricingInput.category}
Verkaufskanal: ${pricingInput.channel}

Antworte NUR mit diesem JSON (kein Markdown, kein Text drumherum):
{
  "empfohlenerVerkaufspreis": number,
  "marge": number,
  "gewinn": number,
  "positionierung": "string (1 Satz)",
  "preispsychologie": "string (1 Satz)",
  "kanalStrategie": "string (1 Satz)",
  "risikoLevel": "niedrig|mittel|hoch"
}`;
    try {
      const raw = await callClaude(
        "Du bist ein Pricing-Experte für Luxusgüter. Antworte ausschließlich mit validem JSON.",
        prompt
      );
      const cleaned = raw.replace(/```json|```/g, "").trim();
      setPricingResult(JSON.parse(cleaned));
    } catch (error) {
      setPricingResult({ error: "Konnte nicht parsen: " + (error instanceof Error ? error.message : "Unbekannter Fehler") });
    } finally {
      setPricingLoading(false);
    }
  };

  const handleFunnelScript = async () => {
    if (!funnelLead.name || !funnelLead.product) return;
    setFunnelLoading(true);
    setFunnelScript("");
    const prompt = `Schreibe ein personalisiertes Sales-Skript / Outreach-Nachricht für:
Kundenname: ${funnelLead.name}
Produkt: ${funnelLead.product}
Wert: ${funnelLead.value ? funnelLead.value + "€" : "nicht angegeben"}
Kanal: ${funnelLead.channel}

Wichtig: Luxus-Ton, exklusiv, kein Druck, vertrauenswürdig. 
Für ${funnelLead.channel === "Email" ? "eine formelle E-Mail" : funnelLead.channel === "WhatsApp" ? "eine WhatsApp-Nachricht (kurz, persönlich)" : "einen professionellen Erstkontakt"}.
Deutsch. Direkt nutzbar.`;
    try {
      const text = await callClaude(
        "Du bist ein Ultra High-Ticket Sales Experte für UHNWI Kunden. Schreibe präzise, luxuriöse Verkaufstexte.",
        prompt
      );
      setFunnelScript(text);
    } catch (error) {
      setFunnelScript("Fehler: " + (error instanceof Error ? error.message : "Unbekannter Fehler"));
    } finally {
      setFunnelLoading(false);
    }
  };

  const stageColor = { "Erstgespräch": "#6b7280", "Angebot": "#f59e0b", "Besichtigung": "#3b82f6", "Due Diligence": "#8b5cf6", "Vertrag": "#10b981" };

  return (
    <div style={{ fontFamily: "'Georgia', 'Times New Roman', serif", background: "#0a0a0a", minHeight: "100vh", color: "#e8dcc8" }}>
      {/* Header */}
      <div style={{ background: "linear-gradient(135deg, #0a0a0a 0%, #1a1208 50%, #0a0a0a 100%)", borderBottom: "1px solid #2a2010", padding: "0 32px" }}>
        <div style={{ maxWidth: 1400, margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between", height: 72 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <div style={{ width: 44, height: 44, background: "linear-gradient(135deg, #c9a84c, #8b6914)", borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 20 }}>◆</div>
            <div>
              <div style={{ fontSize: 20, fontWeight: 700, letterSpacing: "0.15em", color: "#c9a84c" }}>LUXE·OS</div>
              <div style={{ fontSize: 11, color: "#6b5a3a", letterSpacing: "0.3em", textTransform: "uppercase" }}>Ultra High-Ticket Intelligence</div>
            </div>
          </div>
          <div style={{ display: "flex", gap: 4 }}>
            {[
              { id: "overview", label: "Übersicht" },
              { id: "products", label: "Produkte" },
              { id: "leads", label: "Pipeline" },
              { id: "ai", label: "◆ AI Berater" },
              { id: "pricing", label: "Pricing" },
              { id: "funnel", label: "Sales Skript" },
            ].map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                style={{
                  padding: "8px 18px", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 13,
                  fontFamily: "inherit", letterSpacing: "0.05em",
                  background: tab === t.id ? "linear-gradient(135deg, #c9a84c, #8b6914)" : "transparent",
                  color: tab === t.id ? "#0a0a0a" : "#8b7a5a",
                  fontWeight: tab === t.id ? 700 : 400,
                  transition: "all 0.2s",
                }}
              >{t.label}</button>
            ))}
          </div>
        </div>
      </div>

      <div style={{ maxWidth: 1400, margin: "0 auto", padding: "32px 32px" }}>

        {/* OVERVIEW */}
        {tab === "overview" && (
          <div>
            <div style={{ marginBottom: 32 }}>
              <div style={{ fontSize: 11, color: "#6b5a3a", letterSpacing: "0.4em", textTransform: "uppercase", marginBottom: 8 }}>Portfolio Intelligence</div>
              <div style={{ fontSize: 28, fontWeight: 300, color: "#e8dcc8", letterSpacing: "0.05em" }}>Echtzeit-Übersicht</div>
            </div>
            {/* KPI Cards */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 20, marginBottom: 32 }}>
              {[
                { label: "Inventarwert", value: formatEuro(totalRevenue), sub: `${MOCK_PRODUCTS.length} Artikel`, icon: "◆" },
                { label: "Erwarteter Pipeline", value: formatEuro(totalLeadValue), sub: "gewichtet", icon: "◈" },
                { label: "Hot Products", value: `${hotProducts}`, sub: "hohe Nachfrage", icon: "▲" },
                { label: "Ø Ticket-Size", value: formatEuro(totalRevenue / MOCK_PRODUCTS.length), sub: "Portfolio Ø", icon: "◇" },
              ].map((kpi, i) => (
                <div key={i} style={{ background: "linear-gradient(135deg, #111008 0%, #1a1508 100%)", border: "1px solid #2a2010", borderRadius: 12, padding: 24 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
                    <div style={{ fontSize: 11, color: "#6b5a3a", letterSpacing: "0.3em", textTransform: "uppercase" }}>{kpi.label}</div>
                    <div style={{ color: "#c9a84c", fontSize: 18 }}>{kpi.icon}</div>
                  </div>
                  <div style={{ fontSize: 28, fontWeight: 700, color: "#c9a84c", marginBottom: 4 }}>{kpi.value}</div>
                  <div style={{ fontSize: 12, color: "#4a3f2a" }}>{kpi.sub}</div>
                </div>
              ))}
            </div>
            {/* Channel Distribution */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
              <div style={{ background: "#111008", border: "1px solid #2a2010", borderRadius: 12, padding: 24 }}>
                <div style={{ fontSize: 12, color: "#6b5a3a", letterSpacing: "0.3em", textTransform: "uppercase", marginBottom: 20 }}>Kanal-Performance</div>
                {CHANNELS.map((ch) => {
                  const chProducts = MOCK_PRODUCTS.filter((p) => p.channel === ch);
                  const chLeads = MOCK_LEADS.filter((l) => l.channel === ch);
                  const val = chLeads.reduce((s, l) => s + l.value, 0);
                  const maxVal = 3200000;
                  return (
                    <div key={ch} style={{ marginBottom: 14 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
                        <span style={{ fontSize: 13, color: "#b8a888" }}>{ch}</span>
                        <span style={{ fontSize: 12, color: "#6b5a3a" }}>{chProducts.length > 0 ? formatEuro(val) : "—"}</span>
                      </div>
                      <div style={{ height: 4, background: "#1a1508", borderRadius: 2 }}>
                        <div style={{ height: "100%", width: `${Math.max((val / maxVal) * 100, chProducts.length * 10)}%`, background: "linear-gradient(90deg, #c9a84c, #8b6914)", borderRadius: 2, transition: "width 0.5s" }} />
                      </div>
                    </div>
                  );
                })}
              </div>
              <div style={{ background: "#111008", border: "1px solid #2a2010", borderRadius: 12, padding: 24 }}>
                <div style={{ fontSize: 12, color: "#6b5a3a", letterSpacing: "0.3em", textTransform: "uppercase", marginBottom: 20 }}>Kategorie-Übersicht</div>
                {CATEGORIES.map((cat) => {
                  const count = MOCK_PRODUCTS.filter((p) => p.category === cat.id).length;
                  return (
                    <div key={cat.id} style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 14, padding: "10px 14px", background: "#0d0b06", borderRadius: 8, border: "1px solid #1a1508" }}>
                      <span style={{ fontSize: 20 }}>{cat.icon}</span>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: 13, color: "#b8a888" }}>{cat.label}</div>
                        <div style={{ fontSize: 11, color: "#4a3f2a" }}>Ø {formatEuro(cat.avg)}</div>
                      </div>
                      <div style={{ fontSize: 18, fontWeight: 700, color: count > 0 ? "#c9a84c" : "#2a2010" }}>{count}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {/* PRODUCTS */}
        {tab === "products" && (
          <div>
            <div style={{ marginBottom: 24 }}>
              <div style={{ fontSize: 11, color: "#6b5a3a", letterSpacing: "0.4em", textTransform: "uppercase", marginBottom: 8 }}>Inventar</div>
              <div style={{ fontSize: 28, fontWeight: 300, color: "#e8dcc8" }}>High-Ticket Produkte</div>
            </div>
            {/* Filters */}
            <div style={{ display: "flex", gap: 10, marginBottom: 24, flexWrap: "wrap" }}>
              <button onClick={() => setSelectedCategory("all")} style={{ padding: "7px 16px", borderRadius: 6, border: "1px solid #2a2010", background: selectedCategory === "all" ? "#c9a84c" : "transparent", color: selectedCategory === "all" ? "#0a0a0a" : "#8b7a5a", cursor: "pointer", fontSize: 12, fontFamily: "inherit" }}>Alle</button>
              {CATEGORIES.map((c) => (
                <button key={c.id} onClick={() => setSelectedCategory(c.id)} style={{ padding: "7px 16px", borderRadius: 6, border: "1px solid #2a2010", background: selectedCategory === c.id ? "#c9a84c" : "transparent", color: selectedCategory === c.id ? "#0a0a0a" : "#8b7a5a", cursor: "pointer", fontSize: 12, fontFamily: "inherit" }}>
                  {c.icon} {c.label}
                </button>
              ))}
            </div>
            <div style={{ display: "grid", gap: 12 }}>
              {filteredProducts.map((p) => (
                <div key={p.id} style={{ background: "#111008", border: `1px solid ${p.status === "hot" ? "#c9a84c40" : "#2a2010"}`, borderRadius: 12, padding: "18px 24px", display: "flex", alignItems: "center", gap: 24 }}>
                  {p.status === "hot" && <div style={{ width: 8, height: 8, background: "#c9a84c", borderRadius: "50%", flexShrink: 0, boxShadow: "0 0 8px #c9a84c" }} />}
                  {p.status !== "hot" && <div style={{ width: 8, height: 8, background: "#2a2010", borderRadius: "50%", flexShrink: 0 }} />}
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 15, color: "#e8dcc8", fontWeight: 500, marginBottom: 4 }}>{p.name}</div>
                    <div style={{ fontSize: 12, color: "#4a3f2a" }}>{CATEGORIES.find(c => c.id === p.category)?.label} · {p.channel}</div>
                  </div>
                  <div style={{ textAlign: "right", minWidth: 120 }}>
                    <div style={{ fontSize: 18, fontWeight: 700, color: "#c9a84c" }}>{formatEuro(p.price)}</div>
                    <div style={{ fontSize: 11, color: "#4a3f2a" }}>{p.stock} verfügbar</div>
                  </div>
                  <div style={{ textAlign: "center", minWidth: 80 }}>
                    <div style={{ fontSize: 15, color: "#10b981" }}>{p.margin}%</div>
                    <div style={{ fontSize: 11, color: "#4a3f2a" }}>Marge</div>
                  </div>
                  <div style={{ textAlign: "center", minWidth: 80 }}>
                    <div style={{ fontSize: 14, color: p.trend.startsWith("+") ? "#10b981" : "#ef4444" }}>{p.trend}</div>
                    <div style={{ fontSize: 11, color: "#4a3f2a" }}>Trend</div>
                  </div>
                  <div style={{ padding: "4px 12px", borderRadius: 20, background: p.status === "hot" ? "#c9a84c20" : "#1a1508", border: `1px solid ${p.status === "hot" ? "#c9a84c60" : "#2a2010"}`, fontSize: 11, color: p.status === "hot" ? "#c9a84c" : "#4a3f2a", letterSpacing: "0.1em" }}>
                    {p.status === "hot" ? "HOT" : "AKTIV"}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* LEADS / PIPELINE */}
        {tab === "leads" && (
          <div>
            <div style={{ marginBottom: 24 }}>
              <div style={{ fontSize: 11, color: "#6b5a3a", letterSpacing: "0.4em", textTransform: "uppercase", marginBottom: 8 }}>CRM</div>
              <div style={{ fontSize: 28, fontWeight: 300, color: "#e8dcc8" }}>Sales Pipeline</div>
            </div>
            <div style={{ display: "grid", gap: 14 }}>
              {MOCK_LEADS.map((lead) => (
                <div key={lead.id} style={{ background: "#111008", border: "1px solid #2a2010", borderRadius: 12, padding: "20px 24px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
                    <div style={{ width: 44, height: 44, background: "linear-gradient(135deg, #1a1508, #2a2010)", borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16, color: "#c9a84c", flexShrink: 0 }}>
                      {lead.name.charAt(0)}
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 15, color: "#e8dcc8", fontWeight: 500, marginBottom: 3 }}>{lead.name}</div>
                      <div style={{ fontSize: 12, color: "#4a3f2a" }}>{lead.product} · {lead.channel}</div>
                    </div>
                    <div style={{ textAlign: "right", minWidth: 140 }}>
                      <div style={{ fontSize: 18, fontWeight: 700, color: "#c9a84c" }}>{formatEuro(lead.value)}</div>
                      <div style={{ fontSize: 11, color: "#4a3f2a" }}>Dealwert</div>
                    </div>
                    <div style={{ minWidth: 120 }}>
                      <div style={{ padding: "6px 14px", borderRadius: 20, background: "#1a1508", border: `1px solid ${stageColor[lead.stage] || "#2a2010"}40`, display: "inline-block" }}>
                        <span style={{ fontSize: 12, color: stageColor[lead.stage] || "#8b7a5a" }}>{lead.stage}</span>
                      </div>
                    </div>
                    <div style={{ minWidth: 100 }}>
                      <div style={{ marginBottom: 5, display: "flex", justifyContent: "space-between" }}>
                        <span style={{ fontSize: 11, color: "#4a3f2a" }}>Abschluss</span>
                        <span style={{ fontSize: 12, color: lead.probability > 70 ? "#10b981" : lead.probability > 40 ? "#f59e0b" : "#ef4444" }}>{lead.probability}%</span>
                      </div>
                      <div style={{ height: 4, background: "#1a1508", borderRadius: 2 }}>
                        <div style={{ height: "100%", width: `${lead.probability}%`, background: lead.probability > 70 ? "#10b981" : lead.probability > 40 ? "#f59e0b" : "#ef4444", borderRadius: 2 }} />
                      </div>
                    </div>
                    <div style={{ textAlign: "right", minWidth: 100 }}>
                      <div style={{ fontSize: 14, color: "#c9a84c", fontWeight: 600 }}>{formatEuro(lead.value * lead.probability / 100)}</div>
                      <div style={{ fontSize: 11, color: "#4a3f2a" }}>Erwartet</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <div style={{ marginTop: 20, padding: "16px 24px", background: "#111008", border: "1px solid #2a2010", borderRadius: 12, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 13, color: "#6b5a3a" }}>Gesamt Pipeline (gewichtet)</span>
              <span style={{ fontSize: 24, fontWeight: 700, color: "#c9a84c" }}>{formatEuro(totalLeadValue)}</span>
            </div>
          </div>
        )}

        {/* AI BERATER */}
        {tab === "ai" && (
          <div>
            <div style={{ marginBottom: 24 }}>
              <div style={{ fontSize: 11, color: "#6b5a3a", letterSpacing: "0.4em", textTransform: "uppercase", marginBottom: 8 }}>Claude AI</div>
              <div style={{ fontSize: 28, fontWeight: 300, color: "#e8dcc8" }}>Ultra High-Ticket Berater</div>
            </div>
            {/* Mode selector */}
            <div style={{ display: "flex", gap: 10, marginBottom: 24 }}>
              {[
                { id: "sourcing", label: "◆ Sourcing" },
                { id: "pricing", label: "◈ Pricing" },
                { id: "outreach", label: "✦ Outreach" },
                { id: "market", label: "◇ Markt" },
              ].map((m) => (
                <button key={m.id} onClick={() => setAiMode(m.id)} style={{ padding: "9px 20px", borderRadius: 8, border: `1px solid ${aiMode === m.id ? "#c9a84c" : "#2a2010"}`, background: aiMode === m.id ? "#c9a84c15" : "transparent", color: aiMode === m.id ? "#c9a84c" : "#6b5a3a", cursor: "pointer", fontSize: 13, fontFamily: "inherit", letterSpacing: "0.05em" }}>
                  {m.label}
                </button>
              ))}
            </div>
            <div style={{ background: "#111008", border: "1px solid #2a2010", borderRadius: 12, padding: 24, marginBottom: 16 }}>
              <div style={{ fontSize: 12, color: "#4a3f2a", marginBottom: 12 }}>
                {{ sourcing: "Frage nach Lieferanten, Quellen, Netzwerken für Luxusgüter...", pricing: "Lass Preisstrategien und Margen analysieren...", outreach: "Generiere Outreach-Nachrichten für deine Zielkunden...", market: "Erhalte Marktanalysen und Trendberichte..." }[aiMode]}
              </div>
              <textarea
                ref={aiInputRef}
                value={aiQuery}
                onChange={(e) => setAiQuery(e.target.value)}
                placeholder={{ sourcing: "Wo finde ich exklusive Patek Philippe Händler für Resale mit 15%+ Marge?", pricing: "Wie preise ich eine limitierte Rolex optimal für Instagram-Verkauf?", outreach: "Schreibe eine WhatsApp-Nachricht für einen HNWI der Interesse an einer Ferrari-Vermittlung zeigte.", market: "Wie entwickelt sich der DACH-Markt für Pre-owned Luxusuhren 2025?" }[aiMode]}
                style={{ width: "100%", minHeight: 100, background: "#0a0a0a", border: "1px solid #2a2010", borderRadius: 8, padding: 16, color: "#e8dcc8", fontSize: 14, fontFamily: "inherit", resize: "vertical", boxSizing: "border-box" }}
                onKeyDown={(e) => { if (e.key === "Enter" && e.ctrlKey) handleAiQuery(); }}
              />
              <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 12 }}>
                <button onClick={handleAiQuery} disabled={aiLoading || !aiQuery.trim()} style={{ padding: "11px 28px", background: aiLoading ? "#2a2010" : "linear-gradient(135deg, #c9a84c, #8b6914)", border: "none", borderRadius: 8, color: aiLoading ? "#4a3f2a" : "#0a0a0a", cursor: aiLoading ? "not-allowed" : "pointer", fontSize: 14, fontWeight: 700, fontFamily: "inherit", letterSpacing: "0.1em" }}>
                  {aiLoading ? "Analysiert..." : "◆ ANALYSIEREN"}
                </button>
              </div>
            </div>
            {aiResponse && (
              <div style={{ background: "#111008", border: "1px solid #c9a84c30", borderRadius: 12, padding: 24 }}>
                <div style={{ fontSize: 11, color: "#c9a84c", letterSpacing: "0.3em", textTransform: "uppercase", marginBottom: 16 }}>◆ AI ANALYSE</div>
                <div style={{ fontSize: 14, color: "#b8a888", lineHeight: 1.8, whiteSpace: "pre-wrap" }}>{aiResponse}</div>
              </div>
            )}
          </div>
        )}

        {/* PRICING */}
        {tab === "pricing" && (
          <div>
            <div style={{ marginBottom: 24 }}>
              <div style={{ fontSize: 11, color: "#6b5a3a", letterSpacing: "0.4em", textTransform: "uppercase", marginBottom: 8 }}>AI Pricing Engine</div>
              <div style={{ fontSize: 28, fontWeight: 300, color: "#e8dcc8" }}>Profit-Kalkulator</div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
              <div style={{ background: "#111008", border: "1px solid #2a2010", borderRadius: 12, padding: 28 }}>
                <div style={{ fontSize: 12, color: "#6b5a3a", letterSpacing: "0.3em", textTransform: "uppercase", marginBottom: 24 }}>Produkt eingeben</div>
                {[
                  { label: "Produktname", key: "name", type: "text", placeholder: "z.B. Rolex Daytona Stahl" },
                  { label: "Einkaufspreis (€)", key: "buyPrice", type: "number", placeholder: "z.B. 18500" },
                ].map(field => (
                  <div key={field.key} style={{ marginBottom: 18 }}>
                    <div style={{ fontSize: 12, color: "#4a3f2a", marginBottom: 8, letterSpacing: "0.1em" }}>{field.label}</div>
                    <input
                      type={field.type}
                      placeholder={field.placeholder}
                      value={pricingInput[field.key]}
                      onChange={(e) => setPricingInput(p => ({ ...p, [field.key]: e.target.value }))}
                      style={{ width: "100%", background: "#0a0a0a", border: "1px solid #2a2010", borderRadius: 8, padding: "12px 16px", color: "#e8dcc8", fontSize: 14, fontFamily: "inherit", boxSizing: "border-box" }}
                    />
                  </div>
                ))}
                <div style={{ marginBottom: 18 }}>
                  <div style={{ fontSize: 12, color: "#4a3f2a", marginBottom: 8 }}>Kategorie</div>
                  <select value={pricingInput.category} onChange={(e) => setPricingInput(p => ({ ...p, category: e.target.value }))} style={{ width: "100%", background: "#0a0a0a", border: "1px solid #2a2010", borderRadius: 8, padding: "12px 16px", color: "#e8dcc8", fontSize: 14, fontFamily: "inherit" }}>
                    {CATEGORIES.map(c => <option key={c.id} value={c.id}>{c.icon} {c.label}</option>)}
                  </select>
                </div>
                <div style={{ marginBottom: 24 }}>
                  <div style={{ fontSize: 12, color: "#4a3f2a", marginBottom: 8 }}>Verkaufskanal</div>
                  <select value={pricingInput.channel} onChange={(e) => setPricingInput(p => ({ ...p, channel: e.target.value }))} style={{ width: "100%", background: "#0a0a0a", border: "1px solid #2a2010", borderRadius: 8, padding: "12px 16px", color: "#e8dcc8", fontSize: 14, fontFamily: "inherit" }}>
                    {CHANNELS.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <button onClick={handlePricingAnalysis} disabled={pricingLoading} style={{ width: "100%", padding: 14, background: "linear-gradient(135deg, #c9a84c, #8b6914)", border: "none", borderRadius: 8, color: "#0a0a0a", fontSize: 14, fontWeight: 700, cursor: "pointer", fontFamily: "inherit", letterSpacing: "0.1em" }}>
                  {pricingLoading ? "Analysiert..." : "◆ PRICING ANALYSE"}
                </button>
              </div>
              <div>
                {pricingResult && !pricingResult.error ? (
                  <div style={{ background: "#111008", border: "1px solid #c9a84c30", borderRadius: 12, padding: 28 }}>
                    <div style={{ fontSize: 12, color: "#c9a84c", letterSpacing: "0.3em", textTransform: "uppercase", marginBottom: 24 }}>◆ AI EMPFEHLUNG</div>
                    <div style={{ marginBottom: 24 }}>
                      <div style={{ fontSize: 11, color: "#4a3f2a", marginBottom: 6 }}>EMPFOHLENER VERKAUFSPREIS</div>
                      <div style={{ fontSize: 36, fontWeight: 700, color: "#c9a84c" }}>{formatEuro(pricingResult.empfohlenerVerkaufspreis)}</div>
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 20 }}>
                      <div style={{ background: "#0a0a0a", borderRadius: 8, padding: 16, border: "1px solid #1a1508" }}>
                        <div style={{ fontSize: 11, color: "#4a3f2a", marginBottom: 6 }}>MARGE</div>
                        <div style={{ fontSize: 22, fontWeight: 700, color: "#10b981" }}>{pricingResult.marge}%</div>
                      </div>
                      <div style={{ background: "#0a0a0a", borderRadius: 8, padding: 16, border: "1px solid #1a1508" }}>
                        <div style={{ fontSize: 11, color: "#4a3f2a", marginBottom: 6 }}>GEWINN</div>
                        <div style={{ fontSize: 22, fontWeight: 700, color: "#10b981" }}>{formatEuro(pricingResult.gewinn)}</div>
                      </div>
                    </div>
                    {[
                      { label: "Positionierung", value: pricingResult.positionierung },
                      { label: "Preispsychologie", value: pricingResult.preispsychologie },
                      { label: "Kanal-Strategie", value: pricingResult.kanalStrategie },
                    ].map(item => (
                      <div key={item.label} style={{ marginBottom: 14, padding: 14, background: "#0a0a0a", borderRadius: 8, border: "1px solid #1a1508" }}>
                        <div style={{ fontSize: 10, color: "#4a3f2a", marginBottom: 5, letterSpacing: "0.2em", textTransform: "uppercase" }}>{item.label}</div>
                        <div style={{ fontSize: 13, color: "#b8a888", lineHeight: 1.6 }}>{item.value}</div>
                      </div>
                    ))}
                    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 16px", background: "#0a0a0a", borderRadius: 8, border: `1px solid ${pricingResult.risikoLevel === "niedrig" ? "#10b981" : pricingResult.risikoLevel === "mittel" ? "#f59e0b" : "#ef4444"}30` }}>
                      <span style={{ fontSize: 11, color: "#4a3f2a" }}>RISIKO:</span>
                      <span style={{ fontSize: 13, color: pricingResult.risikoLevel === "niedrig" ? "#10b981" : pricingResult.risikoLevel === "mittel" ? "#f59e0b" : "#ef4444", textTransform: "uppercase", fontWeight: 700 }}>{pricingResult.risikoLevel}</span>
                    </div>
                  </div>
                ) : pricingResult?.error ? (
                  <div style={{ background: "#111008", border: "1px solid #ef444430", borderRadius: 12, padding: 28, color: "#ef4444", fontSize: 13 }}>{pricingResult.error}</div>
                ) : (
                  <div style={{ background: "#111008", border: "1px solid #2a2010", borderRadius: 12, padding: 28, display: "flex", alignItems: "center", justifyContent: "center", minHeight: 300 }}>
                    <div style={{ textAlign: "center", color: "#2a2010" }}>
                      <div style={{ fontSize: 40, marginBottom: 12 }}>◆</div>
                      <div style={{ fontSize: 13, letterSpacing: "0.2em" }}>ANALYSE STARTEN</div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* FUNNEL / SALES SCRIPT */}
        {tab === "funnel" && (
          <div>
            <div style={{ marginBottom: 24 }}>
              <div style={{ fontSize: 11, color: "#6b5a3a", letterSpacing: "0.4em", textTransform: "uppercase", marginBottom: 8 }}>AI Sales Engine</div>
              <div style={{ fontSize: 28, fontWeight: 300, color: "#e8dcc8" }}>Persönlicher Verkaufs-Skript Generator</div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
              <div style={{ background: "#111008", border: "1px solid #2a2010", borderRadius: 12, padding: 28 }}>
                <div style={{ fontSize: 12, color: "#6b5a3a", letterSpacing: "0.3em", textTransform: "uppercase", marginBottom: 24 }}>Lead-Daten</div>
                {[
                  { label: "Kundenname", key: "name", placeholder: "Dr. Klaus Berger" },
                  { label: "Produkt", key: "product", placeholder: "Patek Philippe Nautilus 5711" },
                  { label: "Dealwert (€)", key: "value", placeholder: "142000" },
                ].map(f => (
                  <div key={f.key} style={{ marginBottom: 18 }}>
                    <div style={{ fontSize: 12, color: "#4a3f2a", marginBottom: 8 }}>{f.label}</div>
                    <input
                      type="text"
                      placeholder={f.placeholder}
                      value={funnelLead[f.key]}
                      onChange={(e) => setFunnelLead(l => ({ ...l, [f.key]: e.target.value }))}
                      style={{ width: "100%", background: "#0a0a0a", border: "1px solid #2a2010", borderRadius: 8, padding: "12px 16px", color: "#e8dcc8", fontSize: 14, fontFamily: "inherit", boxSizing: "border-box" }}
                    />
                  </div>
                ))}
                <div style={{ marginBottom: 18 }}>
                  <div style={{ fontSize: 12, color: "#4a3f2a", marginBottom: 8 }}>Kanal</div>
                  <select value={funnelLead.channel} onChange={(e) => setFunnelLead(l => ({ ...l, channel: e.target.value }))} style={{ width: "100%", background: "#0a0a0a", border: "1px solid #2a2010", borderRadius: 8, padding: "12px 16px", color: "#e8dcc8", fontSize: 14, fontFamily: "inherit" }}>
                    {CHANNELS.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <button onClick={handleFunnelScript} disabled={funnelLoading} style={{ width: "100%", padding: 14, background: "linear-gradient(135deg, #c9a84c, #8b6914)", border: "none", borderRadius: 8, color: "#0a0a0a", fontSize: 14, fontWeight: 700, cursor: "pointer", fontFamily: "inherit", letterSpacing: "0.1em" }}>
                  {funnelLoading ? "Generiert..." : "◆ SKRIPT GENERIEREN"}
                </button>
              </div>
              <div>
                {funnelScript ? (
                  <div style={{ background: "#111008", border: "1px solid #c9a84c30", borderRadius: 12, padding: 28 }}>
                    <div style={{ fontSize: 12, color: "#c9a84c", letterSpacing: "0.3em", textTransform: "uppercase", marginBottom: 24 }}>◆ GENERIERTES SKRIPT</div>
                    <div style={{ fontSize: 14, color: "#b8a888", lineHeight: 1.8, whiteSpace: "pre-wrap" }}>{funnelScript}</div>
                  </div>
                ) : (
                  <div style={{ background: "#111008", border: "1px solid #2a2010", borderRadius: 12, padding: 28, display: "flex", alignItems: "center", justifyContent: "center", minHeight: 300 }}>
                    <div style={{ textAlign: "center", color: "#2a2010" }}>
                      <div style={{ fontSize: 40, marginBottom: 12 }}>◆</div>
                      <div style={{ fontSize: 13, letterSpacing: "0.2em" }}>SKRIPT GENERIEREN</div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
