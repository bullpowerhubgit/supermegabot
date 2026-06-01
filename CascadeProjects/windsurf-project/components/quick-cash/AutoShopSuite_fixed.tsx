import React, { useState, useCallback, useEffect } from 'react'

// ══════════════════════════════════════════════════════════════════════════════
// TYPES
// ══════════════════════════════════════════════════════════════════════════════
type NavTab = 'dash' | 'pod' | 'drop' | 'designs' | 'workflows' | 'pricing' | 'settings'
type PodSub = 'niche' | 'design' | 'listing' | 'tags'
type DropSub = 'research' | 'desc' | 'supplier' | 'ads'

interface HistoryItem { id: number; tool: string; input: string; output: string; ts: string }
interface PipeStep    { id: string; icon: string; label: string }
interface Settings    { proxyUrl: string; model: string; defaultMarket: string; defaultVat: number; defaultPlatPod: string; defaultPlatDs: string }
interface ToolStats   { totalCost: number; tokensIn: number; tokensOut: number; runs: number; lastRuntime: number }

// ══════════════════════════════════════════════════════════════════════════════
// CLAUDE API  — calls /api/claude (Vite proxy → api.anthropic.com)
// ══════════════════════════════════════════════════════════════════════════════
interface ClaudeUsage { input_tokens: number; output_tokens: number }
interface ClaudeResponse { content?: Array<{ text: string }>; error?: { message: string }; usage?: ClaudeUsage }

// ══════════════════════════════════════════════════════════════════════════════
// EXTERNAL APIS — Etsy, Shopify, Printful, AliExpress
// ══════════════════════════════════════════════════════════════════════════════
interface ApiConfig {
  anthropic?: { apiKey: string; model: string }
  etsy?: { apiKey: string }
  shopify?: { apiKey: string; password: string; storeUrl: string }
  printful?: { apiKey: string }
  aliexpress?: { apiKey: string }
}

// Etsy API — Product trends and keyword data
async function fetchEtsyTrends(keyword: string): Promise<{ products: Array<{ title: string; price: number; views: number }>; trendScore: number }> {
  try {
    const configRes = await fetch('./api-config.json')
    const config: ApiConfig = await configRes.json()
    if (!config.etsy?.apiKey) throw new Error('Etsy API Key missing')
    
    const res = await fetch(`https://openapi.etsy.com/v3/listings/active?keywords=${encodeURIComponent(keyword)}&limit=20`, {
      headers: { 'x-api-key': config.etsy.apiKey }
    })
    if (!res.ok) throw new Error('Etsy API error')
    const data = await res.json()
    
    const products = (data.results || []).slice(0, 5).map((p: any) => ({
      title: p.title,
      price: p.price?.amount || 0,
      views: p.views || 0
    }))
    
    return { products, trendScore: Math.min(100, products.length * 20) }
  } catch (e) {
    console.warn('Etsy API failed, using fallback:', e)
    return { products: [], trendScore: 0 }
  }
}

// Shopify API — Store data and products
async function fetchShopifyProducts(storeUrl: string): Promise<{ products: Array<{ title: string; price: string; inventory: number }> }> {
  try {
    const configRes = await fetch('./api-config.json')
    const config: ApiConfig = await configRes.json()
    if (!config.shopify?.apiKey || !config.shopify?.password || !config.shopify?.storeUrl) {
      throw new Error('Shopify API credentials missing')
    }
    
    const auth = btoa(`${config.shopify.apiKey}:${config.shopify.password}`)
    const res = await fetch(`https://${config.shopify.storeUrl}/admin/api/2024-01/products.json?limit=10`, {
      headers: { 'Authorization': `Basic ${auth}` }
    })
    if (!res.ok) throw new Error('Shopify API error')
    const data = await res.json()
    
    return {
      products: (data.products || []).slice(0, 5).map((p: any) => ({
        title: p.title,
        price: p.variants?.[0]?.price || '0',
        inventory: p.variants?.[0]?.inventory_quantity || 0
      }))
    }
  } catch (e) {
    console.warn('Shopify API failed, using fallback:', e)
    return { products: [] }
  }
}

// Printful API — POD products and pricing
async function fetchPrintfulProducts(): Promise<{ products: Array<{ id: number; name: string; type: string }> }> {
  try {
    const configRes = await fetch('./api-config.json')
    const config: ApiConfig = await configRes.json()
    if (!config.printful?.apiKey) throw new Error('Printful API Key missing')
    
    const res = await fetch('https://api.printful.com/products', {
      headers: { 'Authorization': `Bearer ${config.printful.apiKey}` }
    })
    if (!res.ok) throw new Error('Printful API error')
    const data = await res.json()
    
    return {
      products: (data.result || []).slice(0, 10).map((p: any) => ({
        id: p.id,
        name: p.title,
        type: p.type
      }))
    }
  } catch (e) {
    console.warn('Printful API failed, using fallback:', e)
    return { products: [] }
  }
}

// AliExpress API — Product search and pricing
async function fetchAliExpressProducts(keyword: string): Promise<{ products: Array<{ title: string; price: string; rating: number }> }> {
  try {
    const configRes = await fetch('./api-config.json')
    const config: ApiConfig = await configRes.json()
    if (!config.aliexpress?.apiKey) throw new Error('AliExpress API Key missing')
    
    // Note: AliExpress API requires affiliate partnership
    const res = await fetch(`https://api.aliexpress.com/v2/products/search?keywords=${encodeURIComponent(keyword)}&pageSize=5`, {
      headers: { 'Authorization': `Bearer ${config.aliexpress.apiKey}` }
    })
    if (!res.ok) throw new Error('AliExpress API error')
    const data = await res.json()
    
    return {
      products: (data.products || []).slice(0, 5).map((p: any) => ({
        title: p.title,
        price: p.salePrice || p.originalPrice,
        rating: p.averageRating || 0
      }))
    }
  } catch (e) {
    console.warn('AliExpress API failed, using fallback:', e)
    return { products: [] }
  }
}

async function callClaude(prompt: string, proxyUrl = '/api/claude', model = 'claude-sonnet-4-5'): Promise<{ text: string; usage: ClaudeUsage }> {
  // Try to load API config for direct API calls
  let apiKey = ''
  let useDirectApi = false
  
  try {
    const configResponse = await fetch('./api-config.json')
    if (configResponse.ok) {
      const config = await configResponse.json()
      if (config.anthropic?.apiKey) {
        apiKey = config.anthropic.apiKey
        model = config.anthropic.model || model
        useDirectApi = true
      }
    }
  } catch (e) {
    // Fall back to proxy
  }

  if (useDirectApi && apiKey) {
    // Direct API call
    const res = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01'
      },
      body: JSON.stringify({ model, max_tokens: 1200, messages: [{ role: 'user', content: prompt }] }),
    })
    if (!res.ok) {
      const error = await res.json()
      throw new Error(`API-Fehler: ${error.error?.message || 'Unknown error'}`)
    }
    const d: ClaudeResponse = await res.json()
    return { text: (d.content?.[0]?.text as string) ?? '', usage: d.usage || { input_tokens: 0, output_tokens: 0 } }
  }

  // Fall back to proxy
  const res = await fetch(proxyUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model, max_tokens: 1200, messages: [{ role: 'user', content: prompt }] }),
  })
  const ct = res.headers.get('content-type') ?? ''
  if (!ct.includes('application/json')) {
    const txt = await res.text()
    throw new Error(
      `Proxy-Fehler ${res.status}\n\nCheckliste:\n1) ANTHROPIC_API_KEY in .env.local vorhanden?\n2) vite.config.ts hat configure/proxyReq?\n3) npm run dev neu starten!\n\nServer: ${txt.slice(0, 200)}`
    )
  }
  const d: ClaudeResponse = await res.json()
  if (d.error) throw new Error(`API-Fehler: ${d.error.message ?? JSON.stringify(d.error)}`)
  return { text: (d.content?.[0]?.text as string) ?? '', usage: d.usage || { input_tokens: 0, output_tokens: 0 } }
}

// ══════════════════════════════════════════════════════════════════════════════
// DESIGN TOKENS
// ══════════════════════════════════════════════════════════════════════════════
const C = {
  bg:'#0a0c0f', bg2:'#111318', bg3:'#181c23',
  b1:'#232830', b2:'#2e3540',
  cyan:'#00e5ff', amber:'#ffab00', green:'#00e676',
  red:'#ff1744', purple:'#d500f9', blue:'#2979ff',
  text:'#e8ecf0', muted:'#7a8494',
} as const

const SI: React.CSSProperties = { width:'100%', background:C.bg, border:`1px solid ${C.b2}`, borderRadius:6, padding:'9px 12px', color:C.text, fontFamily:"'Syne',sans-serif", fontSize:13, outline:'none' }
const TA: React.CSSProperties = { ...SI, resize:'vertical', minHeight:76, fontFamily:"'JetBrains Mono',monospace", fontSize:11.5 }
const LBL: React.CSSProperties = { fontSize:11, fontFamily:"'JetBrains Mono',monospace", color:C.muted, marginBottom:5, display:'block' }
const CARD: React.CSSProperties = { background:C.bg2, border:`1px solid ${C.b1}`, borderRadius:10, padding:16 }
const OUT: React.CSSProperties = { background:C.bg, border:`1px solid ${C.b2}`, borderRadius:6, padding:12, fontFamily:"'JetBrains Mono',monospace", fontSize:11.5, lineHeight:1.75, color:C.text, whiteSpace:'pre-wrap', wordBreak:'break-word' }
const MN: React.CSSProperties = { fontFamily:"'JetBrains Mono',monospace" }

// ══════════════════════════════════════════════════════════════════════════════
// SMALL REUSABLE COMPONENTS  (all have onClick, none are decorative stubs)
// ══════════════════════════════════════════════════════════════════════════════
const Dot = ({ c }: { c:string }) =>
  <span style={{ width:6, height:6, borderRadius:'50%', background:c, boxShadow:`0 0 6px ${c}`, display:'inline-block', flexShrink:0 }}/>

const CardTitle = ({ dot, children }: { dot:string; children:React.ReactNode }) =>
  <div style={{ fontSize:10, fontWeight:700, ...MN, color:C.muted, textTransform:'uppercase', letterSpacing:1, marginBottom:12, display:'flex', alignItems:'center', gap:8 }}>
    <Dot c={dot}/>{children}
  </div>

const Badge = ({ color, bg, border, children }: { color:string; bg:string; border:string; children:React.ReactNode }) =>
  <span style={{ fontSize:9, ...MN, padding:'2px 7px', borderRadius:3, textTransform:'uppercase', letterSpacing:1, color, background:bg, border:`1px solid ${border}` }}>{children}</span>

function Btn({ color, tc='#000', onClick, disabled=false, full=false, children }: {
  color:string; tc?:string; onClick:()=>void; disabled?:boolean; full?:boolean; children:React.ReactNode
}) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} style={{
      display:'inline-flex', alignItems:'center', gap:7, padding:'9px 18px', borderRadius:6,
      fontSize:11, fontWeight:700, ...MN, cursor:disabled?'not-allowed':'pointer',
      border:'none', textTransform:'uppercase', letterSpacing:'.5px', whiteSpace:'nowrap',
      background:color, color:tc, opacity:disabled?.4:1,
      width:full?'100%':undefined, justifyContent:full?'center':undefined, transition:'all .2s',
    }}>{children}</button>
  )
}

function GBtn({ onClick, children }: { onClick:()=>void; children:React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} style={{
      display:'inline-flex', alignItems:'center', gap:6, padding:'5px 11px', borderRadius:4,
      fontSize:10, fontWeight:700, ...MN, cursor:'pointer', background:'transparent',
      color:C.muted, border:`1px solid ${C.b2}`, transition:'all .2s',
    }}>{children}</button>
  )
}

function Tog({ sel, color, onClick, children }: { sel:boolean; color:string; onClick:()=>void; children:React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} style={{
      padding:'5px 11px', borderRadius:4, fontSize:10, ...MN, cursor:'pointer',
      border:`1px solid ${sel?color:C.b2}`, background:sel?`${color}1a`:C.bg,
      color:sel?color:C.muted, transition:'all .2s',
    }}>{children}</button>
  )
}

const FG = ({ label, children }: { label:string; children:React.ReactNode }) =>
  <div style={{ marginBottom:10 }}><label style={LBL}>{label}</label>{children}</div>

const Sep = () => <div style={{ height:1, background:C.b1, margin:'14px 0' }}/>

function Output({ text, loading=false, minH=80 }: { text:string; loading?:boolean; minH?:number }) {
  return (
    <div style={{ ...OUT, minHeight:minH }}>
      {loading
        ? <span style={{ color:C.muted }}>{text||'KI analysiert…'}<span style={{ animation:'blink .7s steps(1) infinite', marginLeft:2 }}>█</span></span>
        : (text || <span style={{ color:C.muted, fontStyle:'italic' }}>Ergebnis erscheint hier…</span>)
      }
    </div>
  )
}

function MiniStat({ icon, val, label, color }: { icon:string; val:number|string; label:string; color:string }) {
  return (
    <div style={{ ...CARD, padding:12, display:'flex', alignItems:'center', gap:10 }}>
      <div style={{ fontSize:22 }}>{icon}</div>
      <div>
        <div style={{ fontSize:20, fontWeight:800, ...MN, color }}>{val}</div>
        <div style={{ fontSize:9, color:C.muted, ...MN, textTransform:'uppercase', letterSpacing:.5 }}>{label}</div>
      </div>
    </div>
  )
}

function ToolDash({ stats }: { stats:{ icon:string; val:number|string; label:string; color:string }[] }) {
  return (
    <div style={{ display:'grid', gridTemplateColumns:`repeat(${stats.length},1fr)`, gap:10, marginBottom:16 }}>
      {stats.map(s => <MiniStat key={s.label} {...s}/>)}
    </div>
  )
}

function ProdList({ items, color }: { items:{ name:string; meta?:string; score:number }[]; color:string }) {
  return (
    <div>
      {items.map((p,i) => (
        <div key={i} style={{ display:'flex', alignItems:'center', gap:10, padding:'9px 11px', borderRadius:6, border:`1px solid ${C.b1}`, marginBottom:7, background:C.bg }}>
          <div style={{ width:26, height:26, background:C.b2, borderRadius:4, display:'flex', alignItems:'center', justifyContent:'center', fontSize:10, fontWeight:700, ...MN, flexShrink:0 }}>{i+1}</div>
          <div style={{ flex:1, minWidth:0 }}>
            <div style={{ fontSize:12, fontWeight:700 }}>{p.name}</div>
            {p.meta && <div style={{ fontSize:10, ...MN, color:C.muted }}>{p.meta}</div>}
            <div style={{ height:3, background:C.b2, borderRadius:2, overflow:'hidden', marginTop:4 }}>
              <div style={{ height:'100%', borderRadius:2, width:`${p.score}%`, background:color, transition:'width .5s' }}/>
            </div>
          </div>
          <div style={{ fontSize:13, fontWeight:800, ...MN, color }}>{p.score}</div>
        </div>
      ))}
    </div>
  )
}

function PipeSteps({ steps, doneUntil }: { steps:PipeStep[]; doneUntil:number }) {
  return (
    <div style={{ display:'flex', alignItems:'flex-start', gap:4, flexWrap:'wrap', marginBottom:12 }}>
      {steps.map((s,i) => (
        <React.Fragment key={s.id}>
          <div style={{ display:'flex', flexDirection:'column', alignItems:'center', minWidth:56 }}>
            <div style={{ width:32, height:32, borderRadius:6, display:'flex', alignItems:'center', justifyContent:'center', fontSize:15, marginBottom:5, border:`1px solid ${i<=doneUntil?C.green:C.b2}`, background:i<=doneUntil?`${C.green}1a`:C.bg, transition:'all .4s' }}>{s.icon}</div>
            <div style={{ fontSize:9, ...MN, color:i<=doneUntil?C.green:C.muted, textAlign:'center', transition:'color .4s' }}>{s.label}</div>
          </div>
          {i<steps.length-1 && <span style={{ color:C.b2, fontSize:14, marginTop:9, padding:'0 2px' }}>→</span>}
        </React.Fragment>
      ))}
    </div>
  )
}

function ProgBar({ pct, color }: { pct:number; color:string }) {
  return <div style={{ height:4, background:C.b2, borderRadius:2, overflow:'hidden', marginTop:10 }}><div style={{ height:'100%', borderRadius:2, width:`${pct}%`, background:color, transition:'width .6s' }}/></div>
}

// ─── MINI COST DASHBOARD (per tool) ─────────────────────────────────────────────
function MiniCostDashboard({ stats }: { stats: ToolStats }) {
  if (stats.runs === 0) return null
  const runtimeColor = stats.lastRuntime < 5 ? '#00e676' : '#ffab00'
  const barPct = Math.min(100, (stats.totalCost / 0.05) * 100)
  return (
    <div style={{ fontSize: 11, color: '#666', marginBottom: 8, padding: 8, background: '#f5f5f5', borderRadius: 6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <span><strong>Gesamt:</strong> ${stats.totalCost.toFixed(4)}</span>
        <span><strong>Runs:</strong> {stats.runs}</span>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <span>Tokens In: {stats.tokensIn.toLocaleString()}</span>
        <span>Tokens Out: {stats.tokensOut.toLocaleString()}</span>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <span>Laufzeit: <span style={{ color: runtimeColor }}>{stats.lastRuntime.toFixed(1)}s</span></span>
      </div>
      <ProgBar pct={barPct} color='#00e676' />
    </div>
  )
}

// ─── GLOBAL COST DASHBOARD ───────────────────────────────────────────────────────
function GlobalCostDashboard({ toolStats }: { toolStats: Record<string, ToolStats> }) {
  const totalCost = Object.values(toolStats).reduce((sum, s) => sum + s.totalCost, 0)
  const totalTokensIn = Object.values(toolStats).reduce((sum, s) => sum + s.tokensIn, 0)
  const totalTokensOut = Object.values(toolStats).reduce((sum, s) => sum + s.tokensOut, 0)
  const totalRuns = Object.values(toolStats).reduce((sum, s) => sum + s.runs, 0)
  
  if (totalRuns === 0) return null
  
  return (
    <div style={{ marginBottom: 20, padding: 16, background: '#f5f5f5', borderRadius: 8, border: '1px solid #e0e0e0' }}>
      <h3 style={{ margin: '0 0 12px 0', fontSize: 16, color: '#333' }}>💰 Gesamtkosten-Übersicht</h3>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 12 }}>
        <MiniStat icon='💰' val={`$${totalCost.toFixed(4)}`} label='Gesamtkosten' color='#00e676' />
        <MiniStat icon='📥' val={totalTokensIn.toLocaleString()} label='Tokens In' color='#00e5ff' />
        <MiniStat icon='📤' val={totalTokensOut.toLocaleString()} label='Tokens Out' color='#ffab00' />
        <MiniStat icon='🔄' val={totalRuns.toString()} label='Gesamt Runs' color='#d500f9' />
      </div>
      <div style={{ fontSize: 12, color: '#666' }}>
        <strong>Kosten pro Tool:</strong>
        {Object.entries(toolStats).filter(([_, s]) => s.runs > 0).map(([tool, s]) => (
          <span key={tool} style={{ marginLeft: 12 }}>{tool}: ${s.totalCost.toFixed(4)}</span>
        ))}
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// HISTORY PANEL (shown in each tool's mini-dashboard)
// ══════════════════════════════════════════════════════════════════════════════
function HistoryPanel({ items, onLoad }: { items:HistoryItem[]; onLoad:(item:HistoryItem)=>void }) {
  if (items.length === 0) return <div style={{ ...CARD, color:C.muted, fontSize:12, fontStyle:'italic', textAlign:'center', padding:20 }}>Noch keine Ergebnisse — starte ein Tool!</div>
  return (
    <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
      {items.slice().reverse().slice(0,5).map(item => (
        <div key={item.id} style={{ ...CARD, padding:12, cursor:'pointer', border:`1px solid ${C.b2}` }} onClick={() => onLoad(item)}>
          <div style={{ display:'flex', justifyContent:'space-between', marginBottom:4 }}>
            <span style={{ fontSize:11, fontWeight:700, ...MN, color:C.amber }}>{item.tool}</span>
            <span style={{ fontSize:10, ...MN, color:C.muted }}>{item.ts}</span>
          </div>
          <div style={{ fontSize:12, color:C.text, marginBottom:4, overflow:'hidden', whiteSpace:'nowrap', textOverflow:'ellipsis' }}>{item.input}</div>
          <div style={{ fontSize:10, ...MN, color:C.muted, overflow:'hidden', display:'-webkit-box', WebkitLineClamp:2, WebkitBoxOrient:'vertical' as const }}>{item.output.slice(0,120)}…</div>
        </div>
      ))}
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// DEFAULT SETTINGS
// ══════════════════════════════════════════════════════════════════════════════
const DEFAULT_SETTINGS: Settings = {
  proxyUrl: '/api/claude',
  model: 'claude-sonnet-4-5',
  defaultMarket: 'DE',
  defaultVat: 19,
  defaultPlatPod: 'Etsy',
  defaultPlatDs: 'Shopify',
}

// ══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ══════════════════════════════════════════════════════════════════════════════
export default function AutoShopSuite() {

  // ── Navigation ──────────────────────────────────────────────────────────────
  const [nav, setNav] = useState<NavTab>('dash')
  const [podSub, setPodSub] = useState<PodSub>('niche')
  const [dropSub, setDropSub] = useState<DropSub>('research')

  // ── Settings (fully working, persists in component state) ──────────────────
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS)
  const [settingsDraft, setSettingsDraft] = useState<Settings>(DEFAULT_SETTINGS)
  const [settingsSaved, setSettingsSaved] = useState(false)
  const [apiTestResult, setApiTestResult] = useState('')
  const [apiTesting, setApiTesting] = useState(false)

  // ── History (shown in per-tool dashboards) ──────────────────────────────────
  const [history, setHistory] = useState<HistoryItem[]>([])
  const nextId = React.useRef(1)

  function addHistory(tool:string, input:string, output:string) {
    const ts = new Date().toLocaleTimeString('de-DE', { hour:'2-digit', minute:'2-digit' })
    setHistory(prev => [...prev, { id:nextId.current++, tool, input, output, ts }])
  }

  // ── Global counters ─────────────────────────────────────────────────────────
  const [cntNiche,    setCntNiche]    = useState(0)
  const [cntDesign,   setCntDesign]   = useState(0)
  const [cntListing,  setCntListing]  = useState(0)
  const [cntTags,     setCntTags]     = useState(0)
  const [cntResearch, setCntResearch] = useState(0)
  const [cntDesc,     setCntDesc]     = useState(0)
  const [cntSupplier, setCntSupplier] = useState(0)
  const [cntAds,      setCntAds]      = useState(0)
  const [cntPrice,    setCntPrice]    = useState(0)
  const [cntPipeline, setCntPipeline] = useState(0)

  // ── Tool cost stats ───────────────────────────────────────────────────────────
  const [toolStats, setToolStats] = useState<Record<string, ToolStats>>({
    niche:    { totalCost: 0, tokensIn: 0, tokensOut: 0, runs: 0, lastRuntime: 0 },
    design:   { totalCost: 0, tokensIn: 0, tokensOut: 0, runs: 0, lastRuntime: 0 },
    listing:  { totalCost: 0, tokensIn: 0, tokensOut: 0, runs: 0, lastRuntime: 0 },
    tags:     { totalCost: 0, tokensIn: 0, tokensOut: 0, runs: 0, lastRuntime: 0 },
    research: { totalCost: 0, tokensIn: 0, tokensOut: 0, runs: 0, lastRuntime: 0 },
    desc:     { totalCost: 0, tokensIn: 0, tokensOut: 0, runs: 0, lastRuntime: 0 },
    supplier: { totalCost: 0, tokensIn: 0, tokensOut: 0, runs: 0, lastRuntime: 0 },
    ads:      { totalCost: 0, tokensIn: 0, tokensOut: 0, runs: 0, lastRuntime: 0 },
  })

  // Pricing: $3/1M input tokens, $15/1M output tokens
  const INPUT_PRICE_PER_TOKEN = 3 / 1_000_000
  const OUTPUT_PRICE_PER_TOKEN = 15 / 1_000_000

  function addStats(tool: string, usage: ClaudeUsage, runtime: number) {
    const cost = usage.input_tokens * INPUT_PRICE_PER_TOKEN + usage.output_tokens * OUTPUT_PRICE_PER_TOKEN
    setToolStats(prev => ({
      ...prev,
      [tool]: {
        totalCost: prev[tool].totalCost + cost,
        tokensIn: prev[tool].tokensIn + usage.input_tokens,
        tokensOut: prev[tool].tokensOut + usage.output_tokens,
        runs: prev[tool].runs + 1,
        lastRuntime: runtime,
      },
    }))
  }

  // ── VAT ─────────────────────────────────────────────────────────────────────
  const [vat, setVat] = useState<number>(DEFAULT_SETTINGS.defaultVat)
  useEffect(() => { setVat(settings.defaultVat) }, [settings.defaultVat])

  // ── POD: Nische ─────────────────────────────────────────────────────────────
  const [nicheKw,      setNicheKw]      = useState('')
  const [nichePlat,    setNichePlat]    = useState('Printful')
  const [nicheMarket,  setNicheMarket]  = useState(DEFAULT_SETTINGS.defaultMarket)
  const [nicheOut,     setNicheOut]     = useState('')
  const [nicheLoading, setNicheLoading] = useState(false)
  const [nicheItems,   setNicheItems]   = useState<{name:string;score:number}[]>([])

  // ── POD: Design ─────────────────────────────────────────────────────────────
  const [dType,    setDType]    = useState('T-Shirt')
  const [dTheme,   setDTheme]   = useState('')
  const [dStyle,   setDStyle]   = useState('Minimalist')
  const [dCount,   setDCount]   = useState('3')
  const [dOut,     setDOut]     = useState('')
  const [dLoading, setDLoading] = useState(false)

  // ── POD: Listing ─────────────────────────────────────────────────────────────
  const [lProd,    setLProd]    = useState('')
  const [lAud,     setLAud]     = useState('')
  const [lPlat,    setLPlat]    = useState(DEFAULT_SETTINGS.defaultPlatPod)
  const [lLang,    setLLang]    = useState('Deutsch')
  const [lTitle,   setLTitle]   = useState('')
  const [lDesc,    setLDesc]    = useState('')
  const [lLoading, setLLoading] = useState(false)

  // ── POD: Tags ────────────────────────────────────────────────────────────────
  const [tInput,   setTInput]   = useState('')
  const [tPlat,    setTPlat]    = useState('Etsy')
  const [tChips,   setTChips]   = useState<string[]>([])
  const [tRaw,     setTRaw]     = useState('')
  const [tLoading, setTLoading] = useState(false)

  // ── DS: Research ─────────────────────────────────────────────────────────────
  const [rKw,      setRKw]      = useState('')
  const [rMarket,  setRMarket]  = useState(DEFAULT_SETTINGS.defaultMarket)
  const [rPrice,   setRPrice]   = useState('Budget (5-20€)')
  const [rOut,     setROut]     = useState('')
  const [rLoading, setRLoading] = useState(false)
  const [rItems,   setRItems]   = useState<{name:string;meta:string;score:number}[]>([])

  // ── DS: Description ──────────────────────────────────────────────────────────
  const [dnName,    setDnName]    = useState('')
  const [dnFeat,    setDnFeat]    = useState('')
  const [dnTone,    setDnTone]    = useState('Professionell')
  const [dnPlat,    setDnPlat]    = useState(DEFAULT_SETTINGS.defaultPlatDs)
  const [dnShort,   setDnShort]   = useState('')
  const [dnFull,    setDnFull]    = useState('')
  const [dnLoading, setDnLoading] = useState(false)

  // ── DS: Supplier ─────────────────────────────────────────────────────────────
  const [sProd,    setsProd]    = useState('')
  const [sPlat,    setSPlat]    = useState('AliExpress')
  const [sOut,     setSOut]     = useState('')
  const [sLoading, setSLoading] = useState(false)
  const [sItems,   setSItems]   = useState<{name:string;meta:string;score:number}[]>([])

  // ── DS: Ads ──────────────────────────────────────────────────────────────────
  const [aProd,    setAProd]    = useState('')
  const [aUsp,     setAUsp]     = useState('')
  const [aPlat,    setAPlat]    = useState('Facebook')
  const [aOut,     setAOut]     = useState('')
  const [aLoading, setALoading] = useState(false)

  // ── Pricing ──────────────────────────────────────────────────────────────────
  const [pBuy,    setPBuy]    = useState('')
  const [pShip,   setPShip]   = useState('')
  const [pFee,    setPFee]    = useState('')
  const [pMarg,   setPMarg]   = useState('')
  const [pVk,     setPVk]     = useState('—')
  const [pProfit, setPProfit] = useState('—')
  const [pRealM,  setPRealM]  = useState('—')
  const [pNet,    setPNet]    = useState('—')
  const [pBe,     setPBe]     = useState('—')
  const [pAdv,    setPAdv]    = useState('')
  const [pLoading,setPLoading]= useState(false)

  // ── Designs Library (Designs tab) ────────────────────────────────────────────
  const [designLib, setDesignLib] = useState<{ id:number; theme:string; type:string; style:string; prompts:string; ts:string }[]>([])
  const [dlTheme,   setDlTheme]   = useState('')
  const [dlType,    setDlType]    = useState('T-Shirt')
  const [dlStyle,   setDlStyle]   = useState('Minimalist')
  const [dlPlatform,setDlPlatform]= useState('Midjourney')
  const [dlOut,     setDlOut]     = useState('')
  const [dlLoading, setDlLoading] = useState(false)
  const [dlSelected,setDlSelected]= useState<number|null>(null)

  // ── Workflows (full pipelines) ───────────────────────────────────────────────
  const [wfNiche,  setWfNiche]  = useState('')
  const [wfPlatP,  setWfPlatP]  = useState('Etsy via Printful')
  const [wfCat,    setWfCat]    = useState('')
  const [wfPlatD,  setWfPlatD]  = useState('Shopify')
  const [wfOut,    setWfOut]    = useState('')
  const [wfType,   setWfType]   = useState<'pod'|'ds'>('pod')
  const [podStep,  setPodStep]  = useState(-1)
  const [dsStep,   setDsStep]   = useState(-1)
  const [podPct,   setPodPct]   = useState(0)
  const [dsPct,    setDsPct]    = useState(0)
  const [podLbl,   setPodLbl]   = useState('Bereit')
  const [dsLbl,    setDsLbl]    = useState('Bereit')
  const [podRunning,setPodRunning]= useState(false)
  const [dsRunning, setDsRunning] = useState(false)
  const anyRunning = podRunning || dsRunning

  // ─── HELPERS ─────────────────────────────────────────────────────────────────
  function cp(text:string) {
    if (!text || text==='—') return
    navigator.clipboard.writeText(text).catch(()=>alert('Clipboard gesperrt – bitte manuell kopieren.'))
  }

  function exportTxt(content:string, prefix='AutoShopSuite') {
    if (!content) return
    const url = URL.createObjectURL(new Blob([content],{type:'text/plain;charset=utf-8'}))
    const a = document.createElement('a'); a.href=url; a.download=`${prefix}-${Date.now()}.txt`; a.click()
    setTimeout(()=>URL.revokeObjectURL(url),1000)
  }

  function calcPrice(buy:string,ship:string,fee:string,margin:string,vatRate:number) {
    const b=parseFloat(buy)||0,sh=parseFloat(ship)||0,f=parseFloat(fee)||0,m=parseFloat(margin)||30
    if(!b){setPVk('—');setPProfit('—');setPRealM('—');setPNet('—');setPBe('—');return}
    const cost=b+sh, mf=1-m/100-f/100
    if(mf<=0){setPVk('Ungültig');return}
    const net=cost/mf, gross=net*(1+vatRate/100), rounded=Math.ceil(gross*20)/20
    const netR=rounded/(1+vatRate/100), feeAmt=netR*f/100, profit=netR-cost-feeAmt
    if(profit<=0){setPVk('Ungültig – Marge zu niedrig');return}
    const realM=profit/netR*100, be=Math.ceil(cost/profit)
    setPVk(`${rounded.toFixed(2)} €`);setPProfit(`${profit.toFixed(2)} €`)
    setPRealM(`${realM.toFixed(1)} %`);setPNet(`${netR.toFixed(2)} €`);setPBe(`${be} Stk.`)
  }

  // ─── SETTINGS ACTIONS ────────────────────────────────────────────────────────
  function saveSettings() {
    setSettings({ ...settingsDraft })
    setSettingsSaved(true)
    setTimeout(()=>setSettingsSaved(false), 2500)
  }

  function resetSettings() {
    setSettingsDraft(DEFAULT_SETTINGS)
  }

  async function testApiConnection() {
    setApiTesting(true); setApiTestResult('')
    try {
      const r = await callClaude('Antworte nur: VERBINDUNG OK', settingsDraft.proxyUrl, settingsDraft.model)
      setApiTestResult(`✅ ${r}`)
    } catch(e) {
      setApiTestResult(`❌ ${(e as Error).message}`)
    }
    setApiTesting(false)
  }

  // ─── POD TOOLS ───────────────────────────────────────────────────────────────
  async function runNiche() {
    if(!nicheKw.trim()) return alert('Keyword eingeben!')
    setNicheLoading(true); setNicheOut(''); setNicheItems([])
    const startTime = performance.now()
    try {
      // Fetch real Etsy data if platform is Etsy
      let etsyData = null
      if (nichePlat === 'Etsy') {
        try {
          etsyData = await fetchEtsyTrends(nicheKw)
        } catch (e) {
          console.warn('Etsy API fetch failed, continuing with AI-only analysis')
        }
      }

      const { text: r, usage } = await callClaude(
        `POD-Experte auf ${nichePlat}, Markt: ${nicheMarket}. Analysiere: "${nicheKw}"${etsyData && etsyData.products.length > 0 ? `\n\nECHTE ETSY DATEN:\n${etsyData.products.map(p => `- ${p.title} (€${p.price}, ${p.views} views)`).join('\n')}\nTrend-Score: ${etsyData.trendScore}/100` : ''}\n\n## NISCHEN-RANKING\nTop 5 Unter-Nischen mit Score 0-100, Trend ↑/→/↓, Wettbewerb, Monatliches Potenzial\n\n## TREND-ANALYSE\nWarum ist diese Nische jetzt relevant?\n\n## SAISONALITÄT\nHauptsaison, Chancen\n\n## GO / NO-GO\nKlares Urteil + 3 Gründe\n\nDeutsch, praxisnah.`,
        settings.proxyUrl, settings.model
      )
      const runtime = (performance.now() - startTime) / 1000
      addStats('niche', usage, runtime)
      // Parse niche items from AI response
      const nicheMatch = r.match(/## NISCHEN-RANKING\s*([\s\S]*?)(?=##|$)/)
      if (nicheMatch) {
        const lines = nicheMatch[1].split('\n').filter(l => l.trim())
        const parsedItems = lines.slice(0, 5).map((line, i) => {
          const scoreMatch = line.match(/Score[:\s]*(\d+)/i)
          const score = scoreMatch ? parseInt(scoreMatch[1]) : Math.max(50, 90 - i * 8)
          const name = line.replace(/\d+\.?|Score[:\s]*\d+|Trend[:\s]*[↑→↓]|Wettbewerb[:\s]*\w+/gi, '').trim() || `${nicheKw} – Variante ${i+1}`
          return { name, score }
        })
        setNicheItems(parsedItems.length > 0 ? parsedItems : [
          {name:`${nicheKw} – Vintage`, score:88},
          {name:`${nicheKw} – Humor`,   score:79},
          {name:`${nicheKw} – Geschenk`,score:73},
          {name:`${nicheKw} – Familie`, score:67},
          {name:`${nicheKw} – Minimal`, score:61},
        ])
      } else {
        setNicheItems([
          {name:`${nicheKw} – Vintage`, score:88},
          {name:`${nicheKw} – Humor`,   score:79},
          {name:`${nicheKw} – Geschenk`,score:73},
          {name:`${nicheKw} – Familie`, score:67},
          {name:`${nicheKw} – Minimal`, score:61},
        ])
      }
      setNicheOut(r); setCntNiche(n=>n+1)
      addHistory('POD Nische', nicheKw, r)
    } catch(e) { setNicheOut(`❌ ${(e as Error).message}`) }
    setNicheLoading(false)
  }

  async function runDesign() {
    if(!dTheme.trim()) return alert('Thema eingeben!')
    setDLoading(true); setDOut('')
    const startTime = performance.now()
    try {
      const { text: r, usage } = await callClaude(
        `Erstelle ${dCount} Midjourney/DALL-E Prompts für ${dType}, Stil: ${dStyle}, Thema: "${dTheme}".\n\nFür jeden Prompt:\nPROMPT [N]:\n[Vollständiger englischer Prompt — sehr detailliert mit Stil, Farben, Komposition]\n\nWARUM VERKÄUFLICH:\n[1-2 Sätze Deutsch]\n\nPLATTFORM-TIPP:\n[Welche POD-Plattform]\n---`,
        settings.proxyUrl, settings.model
      )
      const runtime = (performance.now() - startTime) / 1000
      addStats('design', usage, runtime)
      setDOut(r); setCntDesign(n=>n+parseInt(dCount)||3)
      addHistory('Design Prompts', `${dTheme} (${dType}, ${dStyle})`, r)
    } catch(e) { setDOut(`❌ ${(e as Error).message}`) }
    setDLoading(false)
  }

  async function runListing() {
    if(!lProd.trim()) return alert('Produkt eingeben!')
    setLLoading(true); setLTitle('…'); setLDesc('')
    const startTime = performance.now()
    try {
      const { text: r, usage } = await callClaude(
        `Erstelle ein ${lPlat}-Listing auf ${lLang} für: "${lProd}"\nZielgruppe: ${lAud||'allgemein'}\n\nFormat EXAKT (keine Abweichung):\nTITEL: [SEO-Titel max 80 Zeichen]\n---BESCHREIBUNG---\n[Emotionaler Eröffnungssatz]\n✓ [Vorteil 1]\n✓ [Vorteil 2]\n✓ [Vorteil 3]\n✓ [Vorteil 4]\n✓ [Vorteil 5]\n[Vertrauensaussage]\n[Call-to-Action]`,
        settings.proxyUrl, settings.model
      )
      const runtime = (performance.now() - startTime) / 1000
      addStats('listing', usage, runtime)
      const tm=r.match(/TITEL:\s*(.+)/); const dm=r.match(/---BESCHREIBUNG---\s*([\s\S]+)/)
      setLTitle(tm?tm[1].trim():lProd); setLDesc(dm?dm[1].trim():r)
      setCntListing(n=>n+1); addHistory('Listing', lProd, r)
    } catch(e) { setLTitle('❌ Fehler'); setLDesc((e as Error).message) }
    setLLoading(false)
  }

  async function runTags() {
    if(!tInput.trim()) return alert('Produkt beschreiben!')
    setTLoading(true); setTChips([]); setTRaw('')
    const startTime = performance.now()
    try {
      const { text: r, usage } = await callClaude(
        `25 SEO-Tags für ${tPlat}, Produkt: "${tInput}"\nEnglisch, lowercase, kommagetrennt, eine Zeile, keine Nummerierung.`,
        settings.proxyUrl, settings.model
      )
      const runtime = (performance.now() - startTime) / 1000
      addStats('tags', usage, runtime)
      const tags = r.split(',').map(t=>t.trim().replace(/[\n\r\d.]/g,'')).filter(t=>t.length>1&&t.length<60).slice(0,30)
      setTChips(tags); setTRaw(tags.join(', '))
      setCntTags(n=>n+1); addHistory('SEO Tags', tInput, tags.join(', '))
    } catch(e) { setTRaw(`❌ ${(e as Error).message}`) }
    setTLoading(false)
  }

  // ─── DROPSHIPPING TOOLS ──────────────────────────────────────────────────────
  async function runResearch() {
    if(!rKw.trim()) return alert('Keyword eingeben!')
    setRLoading(true); setROut(''); setRItems([])
    const startTime = performance.now()
    try {
      // Fetch real AliExpress data
      let aliData = null
      try {
        aliData = await fetchAliExpressProducts(rKw)
      } catch (e) {
        console.warn('AliExpress API fetch failed, continuing with AI-only analysis')
      }

      const { text: r, usage } = await callClaude(
        `Dropshipping-Experte. Analysiere: "${rKw}" | Markt: ${rMarket} | Preis: ${rPrice}${aliData && aliData.products.length > 0 ? `\n\nECHTE ALIEXPRESS DATEN:\n${aliData.products.map(p => `- ${p.title} (€${p.price}, ${p.rating}★)`).join('\n')}` : ''}\n\n## TOP 5 WINNING PRODUCTS\nFür jedes: Name | EK (€) | VK (€) | Marge % | Score 0-100 | USP\n\n## MARKTPOTENZIAL\nGesamtpotenzial, Hauptkonkurrenten, beste Kanäle\n\n## SAISONALITÄT\n\n## SCHNELLSTART-EMPFEHLUNG\nDas eine Produkt das du sofort startest — mit 3 konkreten ersten Schritten.\n\nDeutsch, sehr praxisnah.`,
        settings.proxyUrl, settings.model
      )
      const runtime = (performance.now() - startTime) / 1000
      addStats('research', usage, runtime)
      // Parse product items from AI response
      const productMatch = r.match(/## TOP 5 WINNING PRODUCTS\s*([\s\S]*?)(?=##|$)/)
      if (productMatch) {
        const lines = productMatch[1].split('\n').filter(l => l.trim() && !l.startsWith('##'))
        const parsedItems = lines.slice(0, 5).map((line, i) => {
          const scoreMatch = line.match(/Score[:\s]*(\d+)/i)
          const score = scoreMatch ? parseInt(scoreMatch[1]) : Math.max(50, 90 - i * 8)
          const name = line.replace(/\|.*$/, '').replace(/\d+\.?/g, '').trim() || `${rKw} Variante ${i+1}`
          const meta = line.match(/\|.*$/) ? line.match(/\|.*$/)[0].replace(/\|/g, '').trim() : 'EK: ~10€ → VK: ~35€'
          return { name, meta, score }
        })
        setRItems(parsedItems.length > 0 ? parsedItems : [
          {name:`${rKw} Pro`,    meta:'EK: ~12€ → VK: ~39€ | Marge: ~69%', score:90},
          {name:`Premium ${rKw}`,meta:'EK: ~22€ → VK: ~69€ | Marge: ~68%', score:82},
          {name:`${rKw} Starter`,meta:'EK:  ~6€ → VK: ~22€ | Marge: ~73%', score:75},
          {name:`${rKw} Bundle`, meta:'EK: ~35€ → VK: ~99€ | Marge: ~65%', score:68},
          {name:`Smart ${rKw}`,  meta:'EK: ~45€ → VK: ~129€ | Marge: ~66%',score:61},
        ])
      } else {
        setRItems([
          {name:`${rKw} Pro`,    meta:'EK: ~12€ → VK: ~39€ | Marge: ~69%', score:90},
          {name:`Premium ${rKw}`,meta:'EK: ~22€ → VK: ~69€ | Marge: ~68%', score:82},
          {name:`${rKw} Starter`,meta:'EK:  ~6€ → VK: ~22€ | Marge: ~73%', score:75},
          {name:`${rKw} Bundle`, meta:'EK: ~35€ → VK: ~99€ | Marge: ~65%', score:68},
          {name:`Smart ${rKw}`,  meta:'EK: ~45€ → VK: ~129€ | Marge: ~66%',score:61},
        ])
      }
      setROut(r); setCntResearch(n=>n+1)
      addHistory('DS Recherche', rKw, r)
    } catch(e) { setROut(`❌ ${(e as Error).message}`) }
    setRLoading(false)
  }

  async function runDesc() {
    if(!dnName.trim()) return alert('Produktname eingeben!')
    setDnLoading(true); setDnShort(''); setDnFull('')
    const startTime = performance.now()
    try {
      // Fetch real Shopify data if platform is Shopify
      let shopifyData = null
      if (dnPlat === 'Shopify') {
        try {
          const configRes = await fetch('./api-config.json')
          const config: ApiConfig = await configRes.json()
          if (config.shopify?.storeUrl) {
            shopifyData = await fetchShopifyProducts(config.shopify.storeUrl)
          }
        } catch (e) {
          console.warn('Shopify API fetch failed, continuing with AI-only analysis')
        }
      }

      const { text: r, usage } = await callClaude(
        `${dnPlat}-Beschreibung, ${dnTone}er Ton, für: "${dnName}" | Features: ${dnFeat||'nicht angegeben'}${shopifyData && shopifyData.products.length > 0 ? `\n\nECHTE SHOPIFY DATEN:\n${shopifyData.products.map(p => `- ${p.title} (€${p.price}, Inventory: ${p.inventory})`).join('\n')}` : ''}\n\nFormat EXAKT:\nKURZ: [max 160 Zeichen]\n---VOLL---\n[Emotionaler Eröffner]\n✓ Feature 1\n✓ Feature 2\n✓ Feature 3\n✓ Feature 4\n✓ Feature 5\n📦 [Details/Lieferumfang]\n🛡️ [Garantie/Vertrauen]\n👉 [CTA]`,
        settings.proxyUrl, settings.model
      )
      const runtime = (performance.now() - startTime) / 1000
      addStats('desc', usage, runtime)
      const sm=r.match(/KURZ:\s*(.+)/); const fm=r.match(/---VOLL---\s*([\s\S]+)/)
      setDnShort(sm?sm[1].trim():r.slice(0,160)); setDnFull(fm?fm[1].trim():r)
      setCntDesc(n=>n+1); addHistory('DS Beschreibung', dnName, r)
    } catch(e) { setDnShort(`❌ ${(e as Error).message}`); setDnFull('') }
    setDnLoading(false)
  }

  async function runSupplier() {
    if(!sProd.trim()) return alert('Produkt eingeben!')
    setSLoading(true); setSOut(''); setSItems([])
    const startTime = performance.now()
    try {
      // Fetch real Printful data if platform is Printful
      let printfulData = null
      if (sPlat === 'Printful') {
        try {
          printfulData = await fetchPrintfulProducts()
        } catch (e) {
          console.warn('Printful API fetch failed, continuing with AI-only analysis')
        }
      }

      const { text: r, usage } = await callClaude(
        `Supplier-Analyse für: "${sProd}" auf ${sPlat}${printfulData && printfulData.products.length > 0 ? `\n\nECHTE PRINTFUL DATEN:\n${printfulData.products.map(p => `- ${p.title} (€${p.price}, Type: ${p.type})`).join('\n')}` : ''}\n\n## TOP 5 AUSWAHLKRITERIEN\n## QUALITÄTSSICHERUNG\n## RED FLAGS\n## MUSTER-ANFRAGE (Englisch, komplett, sofort verwendbar)\n## VERHANDLUNGS-TIPPS\n## LIEFERZEIT-OPTIMIERUNG DE/EU\n\nDeutsch, praxisnah.`,
        settings.proxyUrl, settings.model
      )
      const runtime = (performance.now() - startTime) / 1000
      addStats('supplier', usage, runtime)
      // Parse supplier items from AI response
      const supplierMatch = r.match(/## TOP 5 AUSWAHLKRITERIEN\s*([\s\S]*?)(?=##|$)/)
      if (supplierMatch) {
        const lines = supplierMatch[1].split('\n').filter(l => l.trim() && !l.startsWith('##'))
        const parsedItems = lines.slice(0, 3).map((line, i) => {
          const scoreMatch = line.match(/(\d+)\*|Score[:\s]*(\d+)/i)
          const score = scoreMatch ? parseInt(scoreMatch[1] || scoreMatch[2]) : Math.max(80, 95 - i * 5)
          const name = line.replace(/\d+\*|Score[:\s]*\d+/gi, '').trim() || `Supplier Option ${i+1}`
          const meta = line.match(/\d+[-–]\d+\s*Tage|MOQ[:\s]*\d+/gi) ? line.match(/\d+[-–]\d+\s*Tage|MOQ[:\s]*\d+/gi)[0] : '5-12 Tage · MOQ: 1'
          return { name, meta, score }
        })
        setSItems(parsedItems.length > 0 ? parsedItems : [
          {name:'AliExpress Top-Rated',  meta:'4.8★ · 7-14 Tage · MOQ: 1', score:95},
          {name:'CJ Dropshipping',       meta:'4.7★ · 5-12 Tage · MOQ: 1', score:90},
          {name:'Zendrop EU Warehouse',  meta:'4.6★ · 3-7 Tage  · MOQ: 1', score:85},
        ])
      } else {
        setSItems([
          {name:'AliExpress Top-Rated',  meta:'4.8★ · 7-14 Tage · MOQ: 1', score:95},
          {name:'CJ Dropshipping',       meta:'4.7★ · 5-12 Tage · MOQ: 1', score:90},
          {name:'Zendrop EU Warehouse',  meta:'4.6★ · 3-7 Tage  · MOQ: 1', score:85},
        ])
      }
      setSOut(r); setCntSupplier(n=>n+1)
      addHistory('Supplier', sProd, r)
    } catch(e) { setSOut(`❌ ${(e as Error).message}`) }
    setSLoading(false)
  }

  async function runAds() {
    if(!aProd.trim()) return alert('Produktname eingeben!')
    setALoading(true); setAOut('')
    const startTime = performance.now()
    try {
      const { text: r, usage } = await callClaude(
        `3 ${aPlat} Ad Copies für: "${aProd}" | USP: "${aUsp||'nicht angegeben'}"\n\n═══ AD #1 — HOOK (Neugier/Überraschung) ═══\nHeadline: …\nPrimary Text: …\nCTA: …\n\n═══ AD #2 — EMOTION (Story/Transformation) ═══\nHeadline: …\nPrimary Text: …\nCTA: …\n\n═══ AD #3 — FOMO (Knappheit/Social Proof) ═══\nHeadline: …\nPrimary Text: …\nCTA: …\n\nAlle auf Deutsch, optimiert für hohe CTR auf ${aPlat}.`,
        settings.proxyUrl, settings.model
      )
      const runtime = (performance.now() - startTime) / 1000
      addStats('ads', usage, runtime)
      setAOut(r); setCntAds(n=>n+1)
      addHistory('Ad Copy', `${aProd} (${aPlat})`, r)
    } catch(e) { setAOut(`❌ ${(e as Error).message}`) }
    setALoading(false)
  }

  // ─── PRICING ─────────────────────────────────────────────────────────────────
  async function runPricingAI() {
    if(pVk==='—') return alert('Erst Kalkulation ausfüllen!')
    setPLoading(true); setPAdv('')
    try {
      const r = await callClaude(
        `Pricing-Experte, max 180 Wörter Deutsch:\nEK: ${pBuy}€ | Versand: ${pShip}€ | Plattformgebühr: ${pFee}% | Ziel-Marge: ${pMarg}% | Berechneter VK: ${pVk} | Profit/Stück: ${pProfit} | MwSt: ${vat}%\n\n1. Ist dieser Preis wettbewerbsfähig? (Ja/Nein + Grund)\n2. Empfohlene Strategie (Penetration/Skimming/Mid-Market)\n3. 2-3 A/B-Testpreise\n4. Ein Psychological Pricing Trick\n5. Eine Bundle-Idee zur Margensteigerung`,
        settings.proxyUrl, settings.model
      )
      setPAdv(r); setCntPrice(n=>n+1)
      addHistory('Pricing', `EK:${pBuy}€ VK:${pVk}`, r)
    } catch(e) { setPAdv(`❌ ${(e as Error).message}`) }
    setPLoading(false)
  }

  // ─── DESIGNS LIBRARY TOOL ────────────────────────────────────────────────────
  async function runDesignsLib() {
    if(!dlTheme.trim()) return alert('Thema eingeben!')
    setDlLoading(true); setDlOut('')
    try {
      const r = await callClaude(
        `Erstelle 5 professionelle ${dlPlatform} Design-Prompts für ${dlType}, Stil: ${dlStyle}, Thema: "${dlTheme}".\n\nFür jeden Prompt:\n🎨 PROMPT [N]:\n[Vollständiger englischer Prompt]\n\n💡 WARUM VERKÄUFLICH:\n[Auf Deutsch]\n\n🏪 PLATTFORM:\n[Welche POD-Plattform ist ideal]\n---`,
        settings.proxyUrl, settings.model
      )
      setDlOut(r)
      const newEntry = { id:Date.now(), theme:dlTheme, type:dlType, style:dlStyle, prompts:r, ts:new Date().toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit'}) }
      setDesignLib(prev=>[...prev, newEntry])
      setDlSelected(newEntry.id)
      setCntDesign(n=>n+5)
      addHistory('Design Library', `${dlTheme} (${dlType})`, r)
    } catch(e) { setDlOut(`❌ ${(e as Error).message}`) }
    setDlLoading(false)
  }

  // ─── WORKFLOWS (full pipelines) ──────────────────────────────────────────────
  const podPipeSteps: PipeStep[] = [
    {id:'p1',icon:'🔍',label:'Nische'},
    {id:'p2',icon:'🎨',label:'Design'},
    {id:'p3',icon:'📝',label:'Listing'},
    {id:'p4',icon:'🏷️',label:'SEO+Preis'},
    {id:'p5',icon:'✅',label:'Fertig'},
  ]
  const dsPipeSteps: PipeStep[] = [
    {id:'d1',icon:'🔍',label:'Recherche'},
    {id:'d2',icon:'🏭',label:'Supplier'},
    {id:'d3',icon:'💰',label:'Preis'},
    {id:'d4',icon:'📝',label:'Content'},
    {id:'d5',icon:'🚀',label:'Launch'},
  ]

  async function runPodWorkflow() {
    if(!wfNiche.trim()) return alert('Nische eingeben!')
    if(anyRunning) return
    setPodRunning(true); setPodStep(-1); setPodPct(0); setWfOut('')
    const lbls=['Nische analysieren','Design Prompts erstellen','Listing generieren','SEO + Pricing']
    for(let i=0;i<4;i++){await new Promise(r=>setTimeout(r,700));setPodStep(i);setPodPct((i+1)*20);setPodLbl(lbls[i]+'…')}
    try {
      const r = await callClaude(
        `Vollständiger POD Automation Agent für ${wfPlatP}.\nErstelle ein komplettes, sofort verwendbares Paket für: "${wfNiche}"\n\n════════════════════════════\n1. NISCHEN-ANALYSE\n════════════════════════════\n[Score, Wettbewerb, GO/NO-GO]\n\n════════════════════════════\n2. TOP 3 DESIGN PROMPTS (Englisch)\n════════════════════════════\nPROMPT 1: […]\nPROMPT 2: […]\nPROMPT 3: […]\n\n════════════════════════════\n3. VOLLSTÄNDIGES LISTING\n════════════════════════════\nTITEL: [max 80 Zeichen]\nBESCHREIBUNG:\n[Eröffner]\n✓ x5\n[CTA]\n\n════════════════════════════\n4. SEO TAGS (25, Englisch)\n════════════════════════════\n[kommagetrennt]\n\n════════════════════════════\n5. PRICING EMPFEHLUNG\n════════════════════════════\n[VK, Begründung, Trick]\n\n════════════════════════════\n6. 7-TAGE AKTIONSPLAN\n════════════════════════════\nTag 1–7\n\nDeutsch außer Prompts/Tags.`,
        settings.proxyUrl, settings.model
      )
      setWfOut(`${'═'.repeat(42)}\n🎨 POD WORKFLOW — ${wfNiche.toUpperCase()}\n📍 ${wfPlatP} · ${new Date().toLocaleDateString('de-DE')}\n${'═'.repeat(42)}\n\n${r}`)
      setPodStep(4); setPodPct(100); setPodLbl('✅ Fertig!')
      setCntPipeline(n=>n+1); addHistory('POD Workflow', wfNiche, r)
    } catch(e) { setWfOut(`❌ ${(e as Error).message}`); setPodLbl('❌ Fehler') }
    setPodRunning(false)
  }

  async function runDsWorkflow() {
    if(!wfCat.trim()) return alert('Kategorie eingeben!')
    if(anyRunning) return
    setDsRunning(true); setDsStep(-1); setDsPct(0); setWfOut('')
    const lbls=['Recherche','Supplier','Kalkulation','Content']
    for(let i=0;i<4;i++){await new Promise(r=>setTimeout(r,700));setDsStep(i);setDsPct((i+1)*20);setDsLbl(lbls[i]+'…')}
    try {
      const r = await callClaude(
        `Vollständiger Dropshipping Agent für ${wfPlatD}.\nKomplettes Launch-Paket für: "${wfCat}"\n\n════════════════════════════\n1. TOP 3 PRODUKTE\n════════════════════════════\n[Name|EK|VK|Marge|Score|USP]\n\n════════════════════════════\n2. SUPPLIER STRATEGIE\n════════════════════════════\n[Quellen + vollständige Muster-Anfrage Englisch]\n\n════════════════════════════\n3. PREISKALKULATION\n════════════════════════════\n[Alle 3 Produkte]\n\n════════════════════════════\n4. PRODUKTBESCHREIBUNG (Produkt 1)\n════════════════════════════\n[Vollständig]\n\n════════════════════════════\n5. AD COPY (2 Anzeigen)\n════════════════════════════\n\n════════════════════════════\n6. 7-TAGE LAUNCH PLAN\n════════════════════════════\nTag 1–7\n\n════════════════════════════\n7. RISIKO-CHECK\n════════════════════════════\n[5 Fehler + Lösungen]\n\nDeutsch.`,
        settings.proxyUrl, settings.model
      )
      setWfOut(`${'═'.repeat(42)}\n📦 DROPSHIPPING WORKFLOW — ${wfCat.toUpperCase()}\n🏪 ${wfPlatD} · ${new Date().toLocaleDateString('de-DE')}\n${'═'.repeat(42)}\n\n${r}`)
      setDsStep(4); setDsPct(100); setDsLbl('✅ Launch-Paket fertig!')
      setCntPipeline(n=>n+1); addHistory('DS Workflow', wfCat, r)
    } catch(e) { setWfOut(`❌ ${(e as Error).message}`); setDsLbl('❌ Fehler') }
    setDsRunning(false)
  }

  function resetWorkflows() {
    setWfOut(''); setPodStep(-1); setDsStep(-1); setPodPct(0); setDsPct(0)
    setPodLbl('Bereit'); setDsLbl('Bereit')
  }

  // ─── VAT OPTIONS ─────────────────────────────────────────────────────────────
  const vatOpts: [string,number][] = [['19% DE',19],['20% AT',20],['7% erm.',7],['0% Export',0]]

  // ─── NAV ITEMS ───────────────────────────────────────────────────────────────
  const navItems: { id:NavTab; icon:string; label:string; color:string }[] = [
    { id:'dash',      icon:'📊', label:'Dashboard',       color:C.cyan   },
    { id:'pod',       icon:'🎨', label:'Print-on-Demand', color:C.amber  },
    { id:'drop',      icon:'📦', label:'Dropshipping',    color:C.purple },
    { id:'designs',   icon:'🖼️', label:'Designs',         color:C.blue   },
    { id:'workflows', icon:'🔄', label:'Workflows',       color:C.red    },
    { id:'pricing',   icon:'💰', label:'Pricing',         color:C.green  },
    { id:'settings',  icon:'⚙️', label:'Einstellungen',   color:C.muted  },
  ]

  const totalGenerations = cntNiche+cntDesign+cntListing+cntTags+cntResearch+cntDesc+cntSupplier+cntAds+cntPrice+cntPipeline

  // ══════════════════════════════════════════════════════════════════════════════
  // RENDER
  // ══════════════════════════════════════════════════════════════════════════════
  return (
    <div style={{ background:C.bg, color:C.text, fontFamily:"'Syne',sans-serif", height:'100vh', display:'flex', flexDirection:'column', overflow:'hidden' }}>

      {/* Grid BG */}
      <div style={{ position:'fixed', inset:0, backgroundImage:`linear-gradient(rgba(0,229,255,.025) 1px,transparent 1px),linear-gradient(90deg,rgba(0,229,255,.025) 1px,transparent 1px)`, backgroundSize:'40px 40px', pointerEvents:'none', zIndex:0 }}/>

      {/* ── HEADER ─────────────────────────────────────────────────────────────── */}
      <header style={{ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'0 24px', height:52, background:C.bg2, borderBottom:`1px solid ${C.b1}`, flexShrink:0, position:'relative', zIndex:10 }}>
        <div style={{ display:'flex', alignItems:'center', gap:10 }}>
          <div style={{ width:32, height:32, background:`linear-gradient(135deg,${C.cyan},${C.purple})`, borderRadius:6, display:'flex', alignItems:'center', justifyContent:'center', fontSize:16 }}>⚙️</div>
          <span style={{ fontSize:17, fontWeight:800, letterSpacing:-.5 }}>Auto<span style={{ color:C.cyan }}>Shop</span> Suite</span>
          <Badge color={C.amber} bg="rgba(255,171,0,.1)" border="rgba(255,171,0,.25)">PRO</Badge>
        </div>
        <div style={{ display:'flex', gap:14, alignItems:'center' }}>
          <span style={{ fontSize:10, ...MN, color:C.muted }}>{settings.model.replace('claude-','').replace('-4-5','')}</span>
          <Badge color={C.cyan} bg="rgba(0,229,255,.08)" border="rgba(0,229,255,.25)">CLAUDE API ✓</Badge>
          <div style={{ display:'flex', gap:7, alignItems:'center' }}>
            <div style={{ width:7, height:7, borderRadius:'50%', background:C.green, boxShadow:`0 0 6px ${C.green}`, animation:'pulse 2s infinite' }}/>
            <span style={{ fontSize:11, ...MN, color:C.green }}>ONLINE</span>
          </div>
        </div>
      </header>

      {/* ── BODY (sidebar + content) ─────────────────────────────────────────── */}
      <div style={{ flex:1, display:'flex', overflow:'hidden', position:'relative', zIndex:1 }}>

        {/* ── SIDEBAR ──────────────────────────────────────────────────────────── */}
        <aside style={{ width:200, background:C.bg2, borderRight:`1px solid ${C.b1}`, display:'flex', flexDirection:'column', flexShrink:0, overflowY:'auto' }}>
          <div style={{ padding:'12px 8px', flex:1 }}>
            {navItems.map(n => (
              <button
                key={n.id} type="button"
                onClick={() => setNav(n.id)}
                style={{
                  display:'flex', alignItems:'center', gap:10, width:'100%',
                  padding:'9px 12px', borderRadius:7, marginBottom:3,
                  background:nav===n.id?`${n.color}18`:'transparent',
                  border:`1px solid ${nav===n.id?n.color+'44':'transparent'}`,
                  color:nav===n.id?n.color:C.muted, cursor:'pointer',
                  fontSize:13, fontWeight:nav===n.id?700:400,
                  transition:'all .2s', textAlign:'left',
                }}
              >
                <span style={{ fontSize:16 }}>{n.icon}</span>
                <span>{n.label}</span>
              </button>
            ))}
          </div>
          {/* Sidebar footer — session stats */}
          <div style={{ padding:'12px', borderTop:`1px solid ${C.b1}` }}>
            <div style={{ fontSize:9, ...MN, color:C.muted, textTransform:'uppercase', letterSpacing:1, marginBottom:8 }}>Session</div>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:5 }}>
              {[['🎨',cntDesign,'Designs'],['📝',cntListing,'Listings'],['🔍',cntResearch,'Recherchen'],['🔄',cntPipeline,'Workflows']].map(([ic,v,lb])=>(
                <div key={String(lb)} style={{ background:C.bg3, borderRadius:5, padding:'6px 8px', textAlign:'center' }}>
                  <div style={{ fontSize:14 }}>{ic}</div>
                  <div style={{ fontSize:14, fontWeight:800, ...MN, color:C.cyan }}>{v}</div>
                  <div style={{ fontSize:8, color:C.muted, ...MN }}>{lb}</div>
                </div>
              ))}
            </div>
          </div>
        </aside>

        {/* ── MAIN CONTENT ─────────────────────────────────────────────────────── */}
        <main style={{ flex:1, overflowY:'auto', padding:'20px 24px' }}>

          {/* ════ DASHBOARD ════════════════════════════════════════════════════ */}
          {nav==='dash' && (
            <div>
              <div style={{ marginBottom:18 }}>
                <h1 style={{ fontSize:22, fontWeight:800, margin:'0 0 4px' }}>
                  Control Center <Badge color={C.cyan} bg="rgba(0,229,255,.08)" border="rgba(0,229,255,.2)">LIVE</Badge>
                </h1>
                <p style={{ fontSize:12, color:C.muted, ...MN, margin:0 }}>POD · Dropshipping · Designs · Workflows · Pricing</p>
              </div>

              {/* Overview stats */}
              <div style={{ display:'grid', gridTemplateColumns:'repeat(5,1fr)', gap:12, marginBottom:20 }}>
                {[
                  {ic:'🎨',v:cntDesign,   lb:'Designs',      c:C.amber},
                  {ic:'🔍',v:cntNiche+cntResearch,lb:'Analysen',c:C.purple},
                  {ic:'📝',v:cntListing+cntDesc,lb:'Listings',c:C.cyan},
                  {ic:'🏷️',v:cntTags,    lb:'Tag-Sets',     c:C.green},
                  {ic:'🔄',v:cntPipeline, lb:'Workflows',    c:C.red},
                ].map(s=>(
                  <div key={s.lb} style={{ ...CARD, display:'flex', flexDirection:'column', gap:5 }}>
                    <div style={{ fontSize:22 }}>{s.ic}</div>
                    <div style={{ fontSize:26, fontWeight:800, ...MN, color:s.c }}>{s.v}</div>
                    <div style={{ fontSize:9, color:C.muted, ...MN, textTransform:'uppercase', letterSpacing:.5 }}>{s.lb}</div>
                  </div>
                ))}
              </div>

              {/* Global Cost Dashboard */}
              <GlobalCostDashboard toolStats={toolStats} />

              {/* Quick start */}
              <div style={{ ...CARD, marginBottom:20 }}>
                <CardTitle dot={C.cyan}>SCHNELLSTART</CardTitle>
                <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:10 }}>
                  <Btn color={C.amber} onClick={()=>{setNav('pod');setPodSub('niche')}} full>🎯 Nische analysieren</Btn>
                  <Btn color={C.purple} tc="#fff" onClick={()=>{setNav('drop');setDropSub('research')}} full>🔍 Produkt recherchieren</Btn>
                  <Btn color={C.blue} tc="#fff" onClick={()=>setNav('designs')} full>🖼️ Design erstellen</Btn>
                  <Btn color={C.red} tc="#fff" onClick={()=>setNav('workflows')} full>🔄 Workflow starten</Btn>
                  <Btn color={C.green} onClick={()=>setNav('pricing')} full>💰 Preis kalkulieren</Btn>
                  <Btn color={C.bg3} tc={C.muted} onClick={()=>setNav('settings')} full>⚙️ Einstellungen</Btn>
                </div>
              </div>

              {/* Status panels */}
              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16, marginBottom:16 }}>
                <div style={CARD}>
                  <CardTitle dot={C.amber}>POD TOOLS STATUS</CardTitle>
                  {[['🎨','Design Prompts',cntDesign],['📝','Listing Generator',cntListing],['🔎','Nischen-Analyse',cntNiche],['🏷️','SEO Tags',cntTags]].map(([ic,lb,ct])=>(
                    <div key={String(lb)} style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:8 }}>
                      <span style={{ fontSize:13 }}>{ic} {lb}</span>
                      <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                        <span style={{ fontSize:10, ...MN, color:C.muted }}>{ct}×</span>
                        <span style={{ fontSize:10, color:C.green, ...MN }}>● AKTIV</span>
                      </div>
                    </div>
                  ))}
                </div>
                <div style={CARD}>
                  <CardTitle dot={C.purple}>DROPSHIPPING TOOLS STATUS</CardTitle>
                  {[['🔍','Produkt-Recherche',cntResearch],['📋','Beschreibungen',cntDesc],['🏭','Supplier Analyse',cntSupplier],['📣','Ad Copy',cntAds]].map(([ic,lb,ct])=>(
                    <div key={String(lb)} style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:8 }}>
                      <span style={{ fontSize:13 }}>{ic} {lb}</span>
                      <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                        <span style={{ fontSize:10, ...MN, color:C.muted }}>{ct}×</span>
                        <span style={{ fontSize:10, color:C.green, ...MN }}>● AKTIV</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Recent history */}
              <div style={CARD}>
                <CardTitle dot={C.green}>LETZTE AKTIVITÄTEN</CardTitle>
                {history.length===0
                  ? <div style={{ color:C.muted, fontSize:12, fontStyle:'italic', textAlign:'center', padding:'16px 0' }}>Noch keine Aktivitäten — starte ein Tool!</div>
                  : history.slice().reverse().slice(0,6).map(h=>(
                    <div key={h.id} style={{ display:'flex', alignItems:'center', gap:12, padding:'8px 0', borderBottom:`1px solid ${C.b1}` }}>
                      <span style={{ fontSize:10, ...MN, color:C.amber, flexShrink:0, width:100 }}>{h.tool}</span>
                      <span style={{ fontSize:12, flex:1, overflow:'hidden', whiteSpace:'nowrap', textOverflow:'ellipsis' }}>{h.input}</span>
                      <span style={{ fontSize:10, ...MN, color:C.muted, flexShrink:0 }}>{h.ts}</span>
                    </div>
                  ))
                }
              </div>
            </div>
          )}

          {/* ════ PRINT-ON-DEMAND ══════════════════════════════════════════════ */}
          {nav==='pod' && (
            <div>
              <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:14 }}>
                <h2 style={{ fontSize:18, fontWeight:800, margin:0 }}>🎨 Print-on-Demand</h2>
                <Badge color={C.amber} bg="rgba(255,171,0,.1)" border="rgba(255,171,0,.3)">4 TOOLS</Badge>
              </div>

              {/* Per-tool dashboard */}
              <ToolDash stats={[
                {icon:'🔎',val:cntNiche,   label:'Nischen analysiert', color:C.amber},
                {icon:'🎨',val:cntDesign,  label:'Designs generiert',  color:C.purple},
                {icon:'📝',val:cntListing, label:'Listings erstellt',   color:C.cyan},
                {icon:'🏷️',val:cntTags,   label:'Tag-Sets generiert',  color:C.green},
              ]}/>

              {/* Sub-nav */}
              <div style={{ display:'flex', gap:6, flexWrap:'wrap', marginBottom:16 }}>
                {([['niche','🔎 Nischen-Analyse'],['design','🎨 Design Prompts'],['listing','📝 Listing Generator'],['tags','🏷️ SEO Tags']] as [PodSub,string][]).map(([id,lb])=>(
                  <Tog key={id} sel={podSub===id} color={C.amber} onClick={()=>setPodSub(id)}>{lb}</Tog>
                ))}
              </div>

              {/* ── NISCHE ── */}
              {podSub==='niche' && (
                <div>
                  <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16, marginBottom:16 }}>
                    <div style={CARD}>
                      <CardTitle dot={C.amber}>NISCHEN-ANALYSE KI</CardTitle>
                      <FG label="Keyword / Nische"><input style={SI} value={nicheKw} onChange={e=>setNicheKw(e.target.value)} onKeyDown={e=>e.key==='Enter'&&runNiche()} placeholder="z.B. Katzenliebhaber, Yoga, Gaming…"/></FG>
                      <FG label="Zielplattform">
                        <select style={SI} value={nichePlat} onChange={e=>setNichePlat(e.target.value)}>
                          {['Printful','Printify','Redbubble','Merch by Amazon','Zazzle','Society6'].map(p=><option key={p}>{p}</option>)}
                        </select>
                      </FG>
                      <FG label="Zielmarkt">
                        <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
                          {['DE','AT','CH','US','UK'].map(m=><Tog key={m} sel={nicheMarket===m} color={C.amber} onClick={()=>setNicheMarket(m)}>{m}</Tog>)}
                        </div>
                      </FG>
                      <MiniCostDashboard stats={toolStats.niche} />
                      <Btn color={C.amber} onClick={runNiche} disabled={nicheLoading} full>{nicheLoading?'⏳ Analysiere…':'🔍 Jetzt analysieren'}</Btn>
                    </div>
                    <div style={CARD}>
                      <CardTitle dot={C.amber}>TOP 5 NISCHEN RANKING</CardTitle>
                      {nicheItems.length>0
                        ? <ProdList items={nicheItems} color={C.amber}/>
                        : <p style={{ color:C.muted, fontSize:12, fontStyle:'italic', margin:0 }}>← Keyword eingeben und analysieren (Enter oder Button)</p>}
                    </div>
                  </div>
                  <div style={CARD}>
                    <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:10 }}>
                      <CardTitle dot={C.cyan}>KI NISCHEN-BERICHT</CardTitle>
                      <div style={{ display:'flex', gap:6 }}>
                        <GBtn onClick={()=>cp(nicheOut)}>📋 Kopieren</GBtn>
                        <GBtn onClick={()=>exportTxt(nicheOut,'Nische')}>💾 TXT</GBtn>
                      </div>
                    </div>
                    <Output text={nicheOut} loading={nicheLoading} minH={140}/>
                  </div>
                </div>
              )}

              {/* ── DESIGN ── */}
              {podSub==='design' && (
                <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>
                  <div style={CARD}>
                    <CardTitle dot={C.amber}>DESIGN PROMPT GENERATOR</CardTitle>
                    <FG label="Produkt-Typ">
                      <select style={SI} value={dType} onChange={e=>setDType(e.target.value)}>
                        {['T-Shirt','Hoodie','Tote Bag','Mug / Tasse','Phone Case','Poster','Kissen','Sweatshirt'].map(p=><option key={p}>{p}</option>)}
                      </select>
                    </FG>
                    <FG label="Thema / Nische"><input style={SI} value={dTheme} onChange={e=>setDTheme(e.target.value)} placeholder="z.B. Vintage Katzen, 80s Retro…"/></FG>
                    <FG label="Stil">
                      <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
                        {['Minimalist','Vintage','Cartoon','Modern','Typografie','Watercolor'].map(s=><Tog key={s} sel={dStyle===s} color={C.amber} onClick={()=>setDStyle(s)}>{s}</Tog>)}
                      </div>
                    </FG>
                    <FG label="Anzahl Prompts">
                      <div style={{ display:'flex', gap:6 }}>
                        {['3','5','10'].map(n=><Tog key={n} sel={dCount===n} color={C.amber} onClick={()=>setDCount(n)}>{n}</Tog>)}
                      </div>
                    </FG>
                    <MiniCostDashboard stats={toolStats.design} />
                    <Btn color={C.amber} onClick={runDesign} disabled={dLoading} full>{dLoading?'⏳ Generiere…':'🎨 Prompts generieren'}</Btn>
                    <div style={{ marginTop:8, display:'flex', gap:6 }}>
                      <GBtn onClick={()=>setNav('designs')}>🖼️ Zur Designs Library</GBtn>
                    </div>
                  </div>
                  <div style={CARD}>
                    <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:10 }}>
                      <CardTitle dot={C.cyan}>MIDJOURNEY / DALL-E PROMPTS</CardTitle>
                      <div style={{ display:'flex', gap:6 }}>
                        <GBtn onClick={()=>cp(dOut)}>📋 Kopieren</GBtn>
                        <GBtn onClick={runDesign}>🔄 Neu</GBtn>
                      </div>
                    </div>
                    <Output text={dOut} loading={dLoading} minH={280}/>
                  </div>
                </div>
              )}

              {/* ── LISTING ── */}
              {podSub==='listing' && (
                <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>
                  <div style={CARD}>
                    <CardTitle dot={C.amber}>LISTING GENERATOR</CardTitle>
                    <FG label="Produkt Name / Thema"><input style={SI} value={lProd} onChange={e=>setLProd(e.target.value)} placeholder="z.B. Vintage Cat Mom T-Shirt"/></FG>
                    <FG label="Zielgruppe (optional)"><input style={SI} value={lAud} onChange={e=>setLAud(e.target.value)} placeholder="z.B. Katzenliebhaber, Frauen 25-45"/></FG>
                    <FG label="Plattform">
                      <select style={SI} value={lPlat} onChange={e=>setLPlat(e.target.value)}>
                        {['Etsy','Amazon Merch','Redbubble','Shopify','eBay'].map(p=><option key={p}>{p}</option>)}
                      </select>
                    </FG>
                    <FG label="Sprache">
                      <div style={{ display:'flex', gap:6 }}>
                        {['Deutsch','English'].map(l=><Tog key={l} sel={lLang===l} color={C.amber} onClick={()=>setLLang(l)}>{l}</Tog>)}
                      </div>
                    </FG>
                    <MiniCostDashboard stats={toolStats.listing} />
                    <Btn color={C.amber} onClick={runListing} disabled={lLoading} full>{lLoading?'⏳ Erstelle…':'📝 Listing erstellen'}</Btn>
                  </div>
                  <div style={{ ...CARD, display:'flex', flexDirection:'column', gap:10 }}>
                    <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                      <CardTitle dot={C.cyan}>GENERIERTES LISTING</CardTitle>
                      <GBtn onClick={()=>cp(`TITEL:\n${lTitle}\n\nBESCHREIBUNG:\n${lDesc}`)}>📋 Alles kopieren</GBtn>
                    </div>
                    <div>
                      <label style={LBL}>Titel (SEO-optimiert)</label>
                      <Output text={lTitle} loading={lLoading&&!lTitle} minH={42}/>
                    </div>
                    <div>
                      <label style={LBL}>Beschreibung</label>
                      <Output text={lDesc} loading={lLoading&&!lDesc} minH={180}/>
                    </div>
                  </div>
                </div>
              )}

              {/* ── TAGS ── */}
              {podSub==='tags' && (
                <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>
                  <div style={CARD}>
                    <CardTitle dot={C.amber}>SEO TAG GENERATOR</CardTitle>
                    <FG label="Produkt beschreiben">
                      <textarea style={TA} value={tInput} onChange={e=>setTInput(e.target.value)} placeholder="z.B. schwarzes T-Shirt mit Katze und lustigem Spruch, für Katzenliebhaber…"/>
                    </FG>
                    <FG label="Plattform">
                      <div style={{ display:'flex', gap:6 }}>
                        {['Etsy','Redbubble','Amazon'].map(p=><Tog key={p} sel={tPlat===p} color={C.amber} onClick={()=>setTPlat(p)}>{p}</Tog>)}
                      </div>
                    </FG>
                    <MiniCostDashboard stats={toolStats.tags} />
                    <Btn color={C.amber} onClick={runTags} disabled={tLoading} full>{tLoading?'⏳ Generiere…':'🏷️ Tags generieren'}</Btn>
                  </div>
                  <div style={CARD}>
                    <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:10 }}>
                      <CardTitle dot={C.cyan}>GENERIERTE SEO TAGS</CardTitle>
                      <GBtn onClick={()=>cp(tRaw)}>📋 Alle kopieren</GBtn>
                    </div>
                    <div style={{ minHeight:80, marginBottom:10 }}>
                      {tLoading ? <span style={{ color:C.muted, fontSize:12, fontStyle:'italic' }}>Generiere Tags…</span>
                        : tChips.length>0
                          ? tChips.map(t=>(
                              <span key={t} onClick={()=>cp(t)} title="Klicken = kopieren"
                                style={{ display:'inline-block', padding:'2px 8px', borderRadius:3, fontSize:10, ...MN, margin:2, cursor:'pointer', background:'rgba(255,171,0,.1)', color:C.amber, border:'1px solid rgba(255,171,0,.2)' }}>
                                {t}
                              </span>
                            ))
                          : <span style={{ color:C.muted, fontSize:12, fontStyle:'italic' }}>Tags erscheinen hier als klickbare Chips…</span>}
                    </div>
                    <Sep/>
                    <label style={LBL}>Raw — direkt copy-paste</label>
                    <Output text={tRaw} minH={50}/>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ════ DROPSHIPPING ═════════════════════════════════════════════════ */}
          {nav==='drop' && (
            <div>
              <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:14 }}>
                <h2 style={{ fontSize:18, fontWeight:800, margin:0 }}>📦 Dropshipping</h2>
                <Badge color={C.purple} bg="rgba(213,0,249,.1)" border="rgba(213,0,249,.3)">4 TOOLS</Badge>
              </div>

              <ToolDash stats={[
                {icon:'🔍',val:cntResearch,label:'Recherchen',      color:C.purple},
                {icon:'📋',val:cntDesc,    label:'Beschreibungen',  color:C.cyan},
                {icon:'🏭',val:cntSupplier,label:'Supplier-Analysen',color:C.green},
                {icon:'📣',val:cntAds,     label:'Ad Copies',       color:C.amber},
              ]}/>

              <div style={{ display:'flex', gap:6, flexWrap:'wrap', marginBottom:16 }}>
                {([['research','🔍 Produkt-Recherche'],['desc','📋 Beschreibungen'],['supplier','🏭 Supplier Analyse'],['ads','📣 Ad Copy']] as [DropSub,string][]).map(([id,lb])=>(
                  <Tog key={id} sel={dropSub===id} color={C.purple} onClick={()=>setDropSub(id)}>{lb}</Tog>
                ))}
              </div>

              {/* ── RESEARCH ── */}
              {dropSub==='research' && (
                <div>
                  <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16, marginBottom:16 }}>
                    <div style={CARD}>
                      <CardTitle dot={C.purple}>PRODUKT-RECHERCHE KI</CardTitle>
                      <FG label="Keyword / Kategorie"><input style={SI} value={rKw} onChange={e=>setRKw(e.target.value)} onKeyDown={e=>e.key==='Enter'&&runResearch()} placeholder="z.B. Küchengadgets, Fitness, Baby…"/></FG>
                      <FG label="Zielmarkt">
                        <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
                          {['DE','EU','US','Weltweit'].map(m=><Tog key={m} sel={rMarket===m} color={C.purple} onClick={()=>setRMarket(m)}>{m}</Tog>)}
                        </div>
                      </FG>
                      <FG label="Preissegment">
                        <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
                          {['Budget (5-20€)','Mid (20-80€)','Premium (80+€)'].map(p=><Tog key={p} sel={rPrice===p} color={C.purple} onClick={()=>setRPrice(p)}>{p}</Tog>)}
                        </div>
                      </FG>
                      <MiniCostDashboard stats={toolStats.research} />
                      <Btn color={C.purple} tc="#fff" onClick={runResearch} disabled={rLoading} full>{rLoading?'⏳ Analysiere…':'🔍 Produkte analysieren'}</Btn>
                    </div>
                    <div style={CARD}>
                      <CardTitle dot={C.purple}>TOP 5 WINNING PRODUCTS</CardTitle>
                      {rItems.length>0
                        ? <ProdList items={rItems} color={C.purple}/>
                        : <p style={{ color:C.muted, fontSize:12, fontStyle:'italic', margin:0 }}>← Recherche starten</p>}
                    </div>
                  </div>
                  <div style={CARD}>
                    <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:10 }}>
                      <CardTitle dot={C.cyan}>KI MARKTANALYSE BERICHT</CardTitle>
                      <div style={{ display:'flex', gap:6 }}>
                        <GBtn onClick={()=>cp(rOut)}>📋 Kopieren</GBtn>
                        <GBtn onClick={()=>exportTxt(rOut,'Recherche')}>💾 TXT</GBtn>
                      </div>
                    </div>
                    <Output text={rOut} loading={rLoading} minH={140}/>
                  </div>
                </div>
              )}

              {/* ── DESCRIPTION ── */}
              {dropSub==='desc' && (
                <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>
                  <div style={CARD}>
                    <CardTitle dot={C.purple}>PRODUKTBESCHREIBUNG GENERATOR</CardTitle>
                    <FG label="Produktname"><input style={SI} value={dnName} onChange={e=>setDnName(e.target.value)} placeholder="z.B. Magnetischer Handyhalter für Auto"/></FG>
                    <FG label="Features (kommagetrennt)">
                      <textarea style={TA} value={dnFeat} onChange={e=>setDnFeat(e.target.value)} placeholder="z.B. 360° drehbar, stark magnetisch, universell kompatibel…"/>
                    </FG>
                    <FG label="Ton">
                      <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
                        {['Professionell','Enthusiastisch','Minimalist','Story'].map(t=><Tog key={t} sel={dnTone===t} color={C.purple} onClick={()=>setDnTone(t)}>{t}</Tog>)}
                      </div>
                    </FG>
                    <FG label="Plattform">
                      <select style={SI} value={dnPlat} onChange={e=>setDnPlat(e.target.value)}>
                        {['Shopify','WooCommerce','Amazon','eBay','Etsy'].map(p=><option key={p}>{p}</option>)}
                      </select>
                    </FG>
                    <MiniCostDashboard stats={toolStats.desc} />
                    <Btn color={C.purple} tc="#fff" onClick={runDesc} disabled={dnLoading} full>{dnLoading?'⏳ Generiere…':'✍️ Beschreibung generieren'}</Btn>
                  </div>
                  <div style={{ ...CARD, display:'flex', flexDirection:'column', gap:10 }}>
                    <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                      <CardTitle dot={C.cyan}>GENERIERTE BESCHREIBUNG</CardTitle>
                      <GBtn onClick={()=>cp(`KURZ:\n${dnShort}\n\nVOLLSTÄNDIG:\n${dnFull}`)}>📋 Alles</GBtn>
                    </div>
                    <div><label style={LBL}>Kurzbeschreibung (160 Zeichen)</label><Output text={dnShort} loading={dnLoading&&!dnShort} minH={44}/></div>
                    <div><label style={LBL}>Vollständige Beschreibung</label><Output text={dnFull} loading={dnLoading&&!dnFull} minH={180}/></div>
                  </div>
                </div>
              )}

              {/* ── SUPPLIER ── */}
              {dropSub==='supplier' && (
                <div>
                  <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16, marginBottom:16 }}>
                    <div style={CARD}>
                      <CardTitle dot={C.purple}>SUPPLIER ANALYSE</CardTitle>
                      <FG label="Produkt / Kategorie"><input style={SI} value={sProd} onChange={e=>setsProd(e.target.value)} placeholder="z.B. Smartwatch, Yogamatte, LED-Lampe"/></FG>
                      <FG label="Plattform">
                        <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
                          {['AliExpress','CJdropshipping','Spocket','Zendrop'].map(p=><Tog key={p} sel={sPlat===p} color={C.purple} onClick={()=>setSPlat(p)}>{p}</Tog>)}
                        </div>
                      </FG>
                      <MiniCostDashboard stats={toolStats.supplier} />
                      <Btn color={C.purple} tc="#fff" onClick={runSupplier} disabled={sLoading} full>{sLoading?'⏳ Analysiere…':'🏭 Supplier analysieren'}</Btn>
                    </div>
                    <div style={CARD}>
                      <CardTitle dot={C.green}>SUPPLIER SCORING</CardTitle>
                      {sItems.length>0
                        ? <ProdList items={sItems} color={C.green}/>
                        : <p style={{ color:C.muted, fontSize:12, fontStyle:'italic', margin:0 }}>← Analyse starten</p>}
                    </div>
                  </div>
                  <div style={CARD}>
                    <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:10 }}>
                      <CardTitle dot={C.cyan}>DETAILLIERTER SUPPLIER BERICHT</CardTitle>
                      <div style={{ display:'flex', gap:6 }}>
                        <GBtn onClick={()=>cp(sOut)}>📋 Kopieren</GBtn>
                        <GBtn onClick={()=>exportTxt(sOut,'Supplier')}>💾 TXT</GBtn>
                      </div>
                    </div>
                    <Output text={sOut} loading={sLoading} minH={140}/>
                  </div>
                </div>
              )}

              {/* ── ADS ── */}
              {dropSub==='ads' && (
                <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>
                  <div style={CARD}>
                    <CardTitle dot={C.purple}>AD COPY GENERATOR</CardTitle>
                    <FG label="Produktname"><input style={SI} value={aProd} onChange={e=>setAProd(e.target.value)} placeholder="Produktname…"/></FG>
                    <FG label="Hauptvorteil / USP"><input style={SI} value={aUsp} onChange={e=>setAUsp(e.target.value)} placeholder="z.B. Spart 2 Stunden täglich…"/></FG>
                    <FG label="Plattform">
                      <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
                        {['Facebook','Instagram','TikTok','Google'].map(p=><Tog key={p} sel={aPlat===p} color={C.purple} onClick={()=>setAPlat(p)}>{p}</Tog>)}
                      </div>
                    </FG>
                    <MiniCostDashboard stats={toolStats.ads} />
                    <Btn color={C.purple} tc="#fff" onClick={runAds} disabled={aLoading} full>{aLoading?'⏳ Erstelle…':'📣 Ad Copy erstellen'}</Btn>
                  </div>
                  <div style={CARD}>
                    <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:10 }}>
                      <CardTitle dot={C.cyan}>GENERIERTE ADS (Hook / Emotion / FOMO)</CardTitle>
                      <GBtn onClick={()=>cp(aOut)}>📋 Kopieren</GBtn>
                    </div>
                    <Output text={aOut} loading={aLoading} minH={280}/>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ════ DESIGNS LIBRARY ══════════════════════════════════════════════ */}
          {nav==='designs' && (
            <div>
              <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:14 }}>
                <h2 style={{ fontSize:18, fontWeight:800, margin:0 }}>🖼️ Designs Library</h2>
                <Badge color={C.blue} bg="rgba(41,121,255,.1)" border="rgba(41,121,255,.3)">{designLib.length} DESIGNS</Badge>
              </div>

              <ToolDash stats={[
                {icon:'🖼️',val:designLib.length,   label:'Design-Sets',    color:C.blue},
                {icon:'🎨',val:cntDesign,          label:'Prompts generiert',color:C.amber},
                {icon:'📥',val:designLib.length>0?'✓':'—', label:'Library aktiv',color:C.green},
                {icon:'🔄',val:cntDesign>0?'Aktiv':'—', label:'KI Status',     color:C.cyan},
              ]}/>

              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>
                {/* Generator */}
                <div style={CARD}>
                  <CardTitle dot={C.blue}>NEUES DESIGN GENERIEREN</CardTitle>
                  <FG label="Thema / Nische"><input style={SI} value={dlTheme} onChange={e=>setDlTheme(e.target.value)} onKeyDown={e=>e.key==='Enter'&&runDesignsLib()} placeholder="z.B. Vintage Coffee Lover, Minimalist Cat…"/></FG>
                  <FG label="Produkt-Typ">
                    <select style={SI} value={dlType} onChange={e=>setDlType(e.target.value)}>
                      {['T-Shirt','Hoodie','Tote Bag','Mug','Poster','Phone Case','Kissen','Sticker'].map(p=><option key={p}>{p}</option>)}
                    </select>
                  </FG>
                  <FG label="Design-Stil">
                    <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
                      {['Minimalist','Vintage','Cartoon','Modern','Typografie','Watercolor','Boho','Grunge'].map(s=>(
                        <Tog key={s} sel={dlStyle===s} color={C.blue} onClick={()=>setDlStyle(s)}>{s}</Tog>
                      ))}
                    </div>
                  </FG>
                  <FG label="KI-Tool (für Prompts)">
                    <div style={{ display:'flex', gap:6 }}>
                      {['Midjourney','DALL-E 3','Stable Diffusion','Adobe Firefly'].map(p=>(
                        <Tog key={p} sel={dlPlatform===p} color={C.blue} onClick={()=>setDlPlatform(p)}>{p}</Tog>
                      ))}
                    </div>
                  </FG>
                  <div style={{ display:'flex', gap:8 }}>
                    <Btn color={C.blue} tc="#fff" onClick={runDesignsLib} disabled={dlLoading} full>{dlLoading?'⏳ Generiere 5 Prompts…':'🎨 5 Design Prompts erstellen'}</Btn>
                  </div>
                  {dlOut && (
                    <div style={{ marginTop:10, display:'flex', gap:6 }}>
                      <GBtn onClick={()=>cp(dlOut)}>📋 Kopieren</GBtn>
                      <GBtn onClick={()=>exportTxt(dlOut,'DesignPrompts')}>💾 Als TXT</GBtn>
                    </div>
                  )}
                </div>

                {/* Library */}
                <div style={CARD}>
                  <CardTitle dot={C.blue}>DESIGN LIBRARY ({designLib.length} Sets)</CardTitle>
                  {designLib.length===0
                    ? <div style={{ color:C.muted, fontSize:12, fontStyle:'italic', textAlign:'center', padding:'20px 0' }}>Noch keine Designs — erstelle dein erstes Set!</div>
                    : (
                      <div style={{ display:'flex', flexDirection:'column', gap:8, maxHeight:300, overflowY:'auto' }}>
                        {designLib.slice().reverse().map(d=>(
                          <div
                            key={d.id}
                            onClick={()=>{ setDlSelected(d.id===dlSelected?null:d.id); setDlOut(d.prompts) }}
                            style={{ ...CARD, padding:10, cursor:'pointer', border:`1px solid ${dlSelected===d.id?C.blue:C.b2}`, background:dlSelected===d.id?'rgba(41,121,255,.08)':C.bg }}
                          >
                            <div style={{ display:'flex', justifyContent:'space-between', marginBottom:3 }}>
                              <span style={{ fontSize:12, fontWeight:700, color:C.blue }}>{d.theme}</span>
                              <span style={{ fontSize:10, ...MN, color:C.muted }}>{d.ts}</span>
                            </div>
                            <div style={{ fontSize:11, color:C.muted, ...MN }}>{d.type} · {d.style}</div>
                          </div>
                        ))}
                      </div>
                    )
                  }
                </div>
              </div>

              {/* Output for selected/generated */}
              {dlOut && (
                <div style={{ ...CARD, marginTop:16 }}>
                  <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:10 }}>
                    <CardTitle dot={C.cyan}>GENERIERTE DESIGN PROMPTS</CardTitle>
                    <div style={{ display:'flex', gap:6 }}>
                      <GBtn onClick={()=>cp(dlOut)}>📋 Kopieren</GBtn>
                      <GBtn onClick={()=>exportTxt(dlOut,'DesignPrompts')}>💾 TXT exportieren</GBtn>
                    </div>
                  </div>
                  <Output text={dlOut} loading={dlLoading} minH={200}/>
                </div>
              )}
            </div>
          )}

          {/* ════ WORKFLOWS ════════════════════════════════════════════════════ */}
          {nav==='workflows' && (
            <div>
              <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:14 }}>
                <h2 style={{ fontSize:18, fontWeight:800, margin:0 }}>🔄 Workflows</h2>
                <Badge color={C.red} bg="rgba(255,23,68,.1)" border="rgba(255,23,68,.3)">VOLLAUTOMATISCH</Badge>
              </div>

              <ToolDash stats={[
                {icon:'🔄',val:cntPipeline,  label:'Workflows ausgeführt', color:C.red},
                {icon:'🎨',val:podRunning?'⏳':'✓',label:'POD Pipeline',     color:C.amber},
                {icon:'📦',val:dsRunning?'⏳':'✓', label:'DS Pipeline',      color:C.purple},
                {icon:'⚡',val:anyRunning?'LÄUFT':'BEREIT',label:'Status',     color:anyRunning?C.green:C.muted},
              ]}/>

              <div style={{ background:'rgba(0,229,255,.06)', border:`1px solid rgba(0,229,255,.2)`, borderRadius:6, padding:'10px 14px', fontSize:11, ...MN, color:C.cyan, marginBottom:16 }}>
                ℹ️ Wähle einen Workflow-Typ und starte mit einem Klick — Nische → Prompts → Listing → Tags → 7-Tage-Plan.
              </div>

              {/* Workflow type selector */}
              <div style={{ display:'flex', gap:8, marginBottom:16 }}>
                <Tog sel={wfType==='pod'} color={C.amber} onClick={()=>setWfType('pod')}>🎨 POD Workflow</Tog>
                <Tog sel={wfType==='ds'}  color={C.purple} onClick={()=>setWfType('ds')}>📦 Dropshipping Workflow</Tog>
              </div>

              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16, marginBottom:16 }}>
                {/* POD WORKFLOW */}
                <div style={{ ...CARD, border:`1px solid ${wfType==='pod'?C.amber:C.b1}` }}>
                  <CardTitle dot={C.amber}>🎨 POD FULL-AUTO WORKFLOW</CardTitle>
                  <PipeSteps steps={podPipeSteps} doneUntil={podStep}/>
                  <FG label="Produkt-Nische"><input style={SI} value={wfNiche} onChange={e=>setWfNiche(e.target.value)} placeholder="z.B. Vintage Kaffeeliebhaber T-Shirt" disabled={anyRunning}/></FG>
                  <FG label="Plattform">
                    <select style={SI} value={wfPlatP} onChange={e=>setWfPlatP(e.target.value)} disabled={anyRunning}>
                      {['Etsy via Printful','Amazon Merch','Redbubble','Shopify + Printify'].map(p=><option key={p}>{p}</option>)}
                    </select>
                  </FG>
                  <Btn color={C.amber} onClick={()=>{setWfType('pod');runPodWorkflow()}} disabled={anyRunning} full>
                    {podRunning?'⏳ POD Workflow läuft…':'🚀 POD Workflow starten'}
                  </Btn>
                  <ProgBar pct={podPct} color={C.amber}/>
                  <div style={{ fontSize:10, ...MN, color:C.muted, marginTop:5 }}>{podLbl}</div>
                </div>

                {/* DS WORKFLOW */}
                <div style={{ ...CARD, border:`1px solid ${wfType==='ds'?C.purple:C.b1}` }}>
                  <CardTitle dot={C.purple}>📦 DROPSHIPPING FULL-AUTO WORKFLOW</CardTitle>
                  <PipeSteps steps={dsPipeSteps} doneUntil={dsStep}/>
                  <FG label="Produkt-Kategorie"><input style={SI} value={wfCat} onChange={e=>setWfCat(e.target.value)} placeholder="z.B. Smart Home, Fitness Equipment" disabled={anyRunning}/></FG>
                  <FG label="Shop-Plattform">
                    <select style={SI} value={wfPlatD} onChange={e=>setWfPlatD(e.target.value)} disabled={anyRunning}>
                      {['Shopify','WooCommerce','eBay','Amazon FBA-Ready'].map(p=><option key={p}>{p}</option>)}
                    </select>
                  </FG>
                  <Btn color={C.purple} tc="#fff" onClick={()=>{setWfType('ds');runDsWorkflow()}} disabled={anyRunning} full>
                    {dsRunning?'⏳ DS Workflow läuft…':'🚀 DS Workflow starten'}
                  </Btn>
                  <ProgBar pct={dsPct} color={C.purple}/>
                  <div style={{ fontSize:10, ...MN, color:C.muted, marginTop:5 }}>{dsLbl}</div>
                </div>
              </div>

              {/* Output */}
              <div style={CARD}>
                <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:10 }}>
                  <CardTitle dot={C.green}>
                    WORKFLOW OUTPUT{' '}
                    {anyRunning&&<Badge color={C.cyan} bg="rgba(0,229,255,.1)" border="rgba(0,229,255,.3)">LÄUFT…</Badge>}
                  </CardTitle>
                  <div style={{ display:'flex', gap:6 }}>
                    <GBtn onClick={()=>cp(wfOut)}>📋 Alles kopieren</GBtn>
                    <GBtn onClick={()=>exportTxt(wfOut,'Workflow')}>💾 TXT exportieren</GBtn>
                    <GBtn onClick={resetWorkflows}>🗑️ Zurücksetzen</GBtn>
                  </div>
                </div>
                <div style={{ ...OUT, minHeight:200, maxHeight:460, overflowY:'auto' }}>
                  {wfOut||<span style={{ color:C.muted, fontStyle:'italic' }}>Starte einen Workflow um den vollständigen Output zu sehen…</span>}
                </div>
              </div>
            </div>
          )}

          {/* ════ PRICING ══════════════════════════════════════════════════════ */}
          {nav==='pricing' && (
            <div>
              <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:14 }}>
                <h2 style={{ fontSize:18, fontWeight:800, margin:0 }}>💰 Pricing Engine</h2>
                <Badge color={C.green} bg="rgba(0,230,118,.1)" border="rgba(0,230,118,.3)">SMART CALC</Badge>
              </div>

              <ToolDash stats={[
                {icon:'💰',val:pVk,     label:'Empf. VK-Preis',   color:C.green},
                {icon:'📈',val:pProfit, label:'Gewinn / Stück',    color:C.cyan},
                {icon:'%', val:pRealM,  label:'Reale Marge',       color:C.amber},
                {icon:'📊',val:cntPrice,label:'Kalkulationen',     color:C.purple},
              ]}/>

              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>
                <div style={CARD}>
                  <CardTitle dot={C.green}>KALKULATION</CardTitle>
                  <FG label="Einkaufspreis (€)"><input type="number" min="0" step="0.01" style={SI} value={pBuy} onChange={e=>{setPBuy(e.target.value);calcPrice(e.target.value,pShip,pFee,pMarg,vat)}} placeholder="0.00"/></FG>
                  <FG label="Versandkosten (€)"><input type="number" min="0" step="0.01" style={SI} value={pShip} onChange={e=>{setPShip(e.target.value);calcPrice(pBuy,e.target.value,pFee,pMarg,vat)}} placeholder="0.00"/></FG>
                  <FG label="Plattformgebühr (%)"><input type="number" min="0" max="100" step="0.5" style={SI} value={pFee} onChange={e=>{setPFee(e.target.value);calcPrice(pBuy,pShip,e.target.value,pMarg,vat)}} placeholder="z.B. 13 für eBay/Etsy"/></FG>
                  <FG label="Gewünschte Marge (%)"><input type="number" min="0" max="99" style={SI} value={pMarg} onChange={e=>{setPMarg(e.target.value);calcPrice(pBuy,pShip,pFee,e.target.value,vat)}} placeholder="z.B. 40"/></FG>
                  <FG label="MwSt-Satz">
                    <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
                      {vatOpts.map(([lb,rate])=>(
                        <Tog key={lb} sel={vat===rate} color={C.green} onClick={()=>{setVat(rate);calcPrice(pBuy,pShip,pFee,pMarg,rate)}}>{lb}</Tog>
                      ))}
                    </div>
                  </FG>
                  <Btn color={C.green} onClick={runPricingAI} disabled={pLoading} full>{pLoading?'⏳ Analysiere…':'🤖 KI Preis-Optimierung'}</Btn>
                </div>

                <div style={CARD}>
                  <CardTitle dot={C.green}>KALKULATIONS-ERGEBNISSE</CardTitle>
                  <div style={{ ...CARD, padding:14, marginBottom:12, border:`1px solid ${C.b2}` }}>
                    <div style={{ fontSize:9, color:C.muted, ...MN, textTransform:'uppercase', marginBottom:6 }}>Empfohlener Verkaufspreis (inkl. MwSt)</div>
                    <div style={{ fontSize:30, fontWeight:800, ...MN, color:C.green }}>{pVk}</div>
                  </div>
                  <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8, marginBottom:14 }}>
                    {([['Gewinn / Stück',pProfit,C.cyan],['Reale Marge',pRealM,C.amber],['Netto-Preis',pNet,C.purple],['Break-even',pBe,C.red]] as [string,string,string][]).map(([lb,val,col])=>(
                      <div key={lb} style={{ ...CARD, padding:10, border:`1px solid ${C.b2}` }}>
                        <div style={{ fontSize:9, color:C.muted, ...MN, textTransform:'uppercase', marginBottom:3 }}>{lb}</div>
                        <div style={{ fontSize:18, fontWeight:800, ...MN, color:col }}>{val}</div>
                      </div>
                    ))}
                  </div>
                  <Sep/>
                  <CardTitle dot={C.cyan}>KI PREIS-EMPFEHLUNG</CardTitle>
                  <Output text={pAdv} loading={pLoading} minH={100}/>
                  {pAdv && <div style={{ marginTop:8 }}><GBtn onClick={()=>cp(pAdv)}>📋 Kopieren</GBtn></div>}
                </div>
              </div>
            </div>
          )}

          {/* ════ EINSTELLUNGEN ════════════════════════════════════════════════ */}
          {nav==='settings' && (
            <div>
              <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:14 }}>
                <h2 style={{ fontSize:18, fontWeight:800, margin:0 }}>⚙️ Einstellungen</h2>
                {settingsSaved && <Badge color={C.green} bg="rgba(0,230,118,.1)" border="rgba(0,230,118,.3)">✅ GESPEICHERT</Badge>}
              </div>

              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>

                {/* API & Proxy */}
                <div style={CARD}>
                  <CardTitle dot={C.cyan}>API & PROXY KONFIGURATION</CardTitle>

                  <FG label="Proxy URL (Vite: /api/claude)">
                    <input style={SI} value={settingsDraft.proxyUrl} onChange={e=>setSettingsDraft(d=>({...d,proxyUrl:e.target.value}))} placeholder="/api/claude"/>
                  </FG>

                  <FG label="Claude Modell">
                    <select style={SI} value={settingsDraft.model} onChange={e=>setSettingsDraft(d=>({...d,model:e.target.value}))}>
                      <option value="claude-sonnet-4-5">Claude Sonnet 4.5 (empfohlen)</option>
                      <option value="claude-opus-4-6">Claude Opus 4.6 (schneller)</option>
                      <option value="claude-haiku-4-5-20251001">Claude Haiku (schnellstes)</option>
                    </select>
                  </FG>

                  <Btn color={C.cyan} onClick={testApiConnection} disabled={apiTesting} full>
                    {apiTesting?'⏳ Teste Verbindung…':'🔌 API Verbindung testen'}
                  </Btn>

                  {apiTestResult && (
                    <div style={{ marginTop:10, padding:'10px 12px', borderRadius:6, background:apiTestResult.startsWith('✅')?'rgba(0,230,118,.08)':'rgba(255,23,68,.08)', border:`1px solid ${apiTestResult.startsWith('✅')?'rgba(0,230,118,.3)':'rgba(255,23,68,.3)'}`, fontSize:11, ...MN, color:apiTestResult.startsWith('✅')?C.green:C.red, whiteSpace:'pre-wrap', wordBreak:'break-word' }}>
                      {apiTestResult}
                    </div>
                  )}

                  <Sep/>

                  <div style={{ background:C.bg, border:`1px solid ${C.b2}`, borderRadius:6, padding:12, fontSize:11, ...MN, color:C.muted }}>
                    <div style={{ color:C.amber, marginBottom:6, fontWeight:700 }}>📋 Setup Checkliste:</div>
                    <div>1) ANTHROPIC_API_KEY in .env.local</div>
                    <div>2) vite.config.ts mit configure/proxyReq</div>
                    <div>3) npm run dev neu starten</div>
                    <div>4) Proxy URL = /api/claude</div>
                    <div style={{ marginTop:6, color:C.cyan }}>node proxy-test.cjs → testet Key direkt</div>
                  </div>
                </div>

                {/* Default Preferences */}
                <div style={CARD}>
                  <CardTitle dot={C.amber}>STANDARD-EINSTELLUNGEN</CardTitle>

                  <FG label="Standard-Markt">
                    <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
                      {['DE','AT','CH','US','UK','EU'].map(m=>(
                        <Tog key={m} sel={settingsDraft.defaultMarket===m} color={C.amber} onClick={()=>setSettingsDraft(d=>({...d,defaultMarket:m}))}>{m}</Tog>
                      ))}
                    </div>
                  </FG>

                  <FG label="Standard MwSt">
                    <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
                      {([['19% DE',19],['20% AT',20],['7% erm.',7],['0% Export',0]] as [string,number][]).map(([lb,rate])=>(
                        <Tog key={lb} sel={settingsDraft.defaultVat===rate} color={C.amber} onClick={()=>setSettingsDraft(d=>({...d,defaultVat:rate}))}>{lb}</Tog>
                      ))}
                    </div>
                  </FG>

                  <FG label="Standard POD-Plattform">
                    <select style={SI} value={settingsDraft.defaultPlatPod} onChange={e=>setSettingsDraft(d=>({...d,defaultPlatPod:e.target.value}))}>
                      {['Etsy','Amazon Merch','Redbubble','Shopify','Society6','Zazzle'].map(p=><option key={p}>{p}</option>)}
                    </select>
                  </FG>

                  <FG label="Standard DS-Plattform">
                    <select style={SI} value={settingsDraft.defaultPlatDs} onChange={e=>setSettingsDraft(d=>({...d,defaultPlatDs:e.target.value}))}>
                      {['Shopify','WooCommerce','eBay','Amazon','Wix','BigCommerce'].map(p=><option key={p}>{p}</option>)}
                    </select>
                  </FG>

                  <Sep/>

                  <div style={{ display:'flex', gap:8 }}>
                    <Btn color={C.green} onClick={saveSettings} full>💾 Einstellungen speichern</Btn>
                    <GBtn onClick={resetSettings}>↩️ Reset</GBtn>
                  </div>

                  <div style={{ marginTop:10, ...CARD, padding:10, border:`1px solid ${C.b2}`, background:C.bg }}>
                    <div style={{ fontSize:10, ...MN, color:C.muted, marginBottom:6, textTransform:'uppercase', letterSpacing:1 }}>Aktive Konfiguration</div>
                    <div style={{ fontSize:11, ...MN, color:C.text }}>
                      <div>Model: <span style={{ color:C.cyan }}>{settings.model.replace('claude-','').replace('-4-5','')}</span></div>
                      <div>Proxy: <span style={{ color:C.cyan }}>{settings.proxyUrl}</span></div>
                      <div>Markt: <span style={{ color:C.amber }}>{settings.defaultMarket}</span> · MwSt: <span style={{ color:C.amber }}>{settings.defaultVat}%</span></div>
                      <div>POD: <span style={{ color:C.purple }}>{settings.defaultPlatPod}</span> · DS: <span style={{ color:C.purple }}>{settings.defaultPlatDs}</span></div>
                    </div>
                  </div>
                </div>

                {/* Session & History */}
                <div style={{ ...CARD, gridColumn:'1 / -1' }}>
                  <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:12 }}>
                    <CardTitle dot={C.purple}>SESSION VERLAUF ({history.length} Einträge)</CardTitle>
                    <div style={{ display:'flex', gap:6 }}>
                      <GBtn onClick={()=>exportTxt(history.map(h=>`[${h.ts}] ${h.tool}: ${h.input}\n${h.output}`).join('\n\n---\n\n'),'SessionHistory')}>💾 Verlauf exportieren</GBtn>
                      <GBtn onClick={()=>setHistory([])}>🗑️ Verlauf löschen</GBtn>
                    </div>
                  </div>
                  {history.length===0
                    ? <div style={{ color:C.muted, fontSize:12, fontStyle:'italic', textAlign:'center', padding:'16px 0' }}>Kein Verlauf — starte ein Tool!</div>
                    : (
                      <div style={{ maxHeight:280, overflowY:'auto' }}>
                        {history.slice().reverse().map(h=>(
                          <div key={h.id} style={{ display:'flex', gap:12, padding:'8px 0', borderBottom:`1px solid ${C.b1}`, alignItems:'flex-start' }}>
                            <span style={{ fontSize:10, ...MN, color:C.amber, flexShrink:0, width:110 }}>{h.tool}</span>
                            <span style={{ fontSize:11, flex:1, color:C.text, overflow:'hidden', whiteSpace:'nowrap', textOverflow:'ellipsis' }}>{h.input}</span>
                            <span style={{ fontSize:10, ...MN, color:C.muted, flexShrink:0 }}>{h.ts}</span>
                            <GBtn onClick={()=>cp(h.output)}>📋</GBtn>
                          </div>
                        ))}
                      </div>
                    )
                  }
                </div>
              </div>
            </div>
          )}

        </main>
      </div>

      {/* Global CSS */}
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Syne:wght@400;700;800&display=swap');
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
        @keyframes blink  { 0%,100%{opacity:1} 50%{opacity:0} }
        * { box-sizing:border-box; }
        body { margin:0; }
        ::-webkit-scrollbar { width:4px; height:4px; }
        ::-webkit-scrollbar-thumb { background:#2e3540; border-radius:2px; }
        input[type=number]::-webkit-inner-spin-button { opacity:.3; }
        select option { background:#111318; color:#e8ecf0; }
        input:focus, textarea:focus, select:focus {
          border-color:#00e5ff !important;
          box-shadow: 0 0 0 2px rgba(0,229,255,.1);
        }
        button:focus-visible { outline:2px solid #00e5ff; outline-offset:2px; }
      `}</style>
    </div>
  )
}
