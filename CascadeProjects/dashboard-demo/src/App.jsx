import React, { useState, useEffect } from 'react';
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Area, AreaChart, PieChart, Pie, Cell
} from 'recharts';
import {
  Activity, TrendingUp, TrendingDown, AlertTriangle, CheckCircle,
  Zap, Database, Server, Users, DollarSign, Clock, Shield,
  ArrowRight, Layers, Cpu, Globe, Mail, Bell
} from 'lucide-react';

const trafficData = [
  { name: '00:00', value: 1200, prev: 1100 },
  { name: '04:00', value: 800, prev: 900 },
  { name: '08:00', value: 3400, prev: 3100 },
  { name: '12:00', value: 5200, prev: 4800 },
  { name: '16:00', value: 4800, prev: 4500 },
  { name: '20:00', value: 2900, prev: 2700 },
  { name: '23:59', value: 1500, prev: 1400 },
];

const revenueData = [
  { name: 'Mo', value: 12400 },
  { name: 'Di', value: 15200 },
  { name: 'Mi', value: 11800 },
  { name: 'Do', value: 18900 },
  { name: 'Fr', value: 22400 },
  { name: 'Sa', value: 16700 },
  { name: 'So', value: 14300 },
];

const pieData = [
  { name: 'API', value: 45, color: '#3b82f6' },
  { name: 'Web', value: 30, color: '#14b8a6' },
  { name: 'Mobile', value: 18, color: '#a855f7' },
  { name: 'Partner', value: 7, color: '#f59e0b' },
];

const alerts = [
  { id: 1, title: 'CPU-Spike bei Node-3 automatisch gedrosselt', type: 'auto', time: 'vor 2 Min.', source: 'Auto-Scale' },
  { id: 2, title: 'Datenbank-Backup erfolgreich abgeschlossen', type: 'ok', time: 'vor 12 Min.', source: 'Backup-Service' },
  { id: 3, title: 'SSL-Zertifikat wird in 7 Tagen erneuert', type: 'warn', time: 'vor 1 Std.', source: 'Cert-Bot' },
  { id: 4, title: 'Kunden-Onboarding-Flow: 98% Erfolgsrate', type: 'ok', time: 'vor 2 Std.', source: 'Analytics' },
  { id: 5, title: 'Speicher > 85% -> Cleanup gestartet', type: 'auto', time: 'vor 3 Std.', source: 'Storage-Guard' },
];

const automations = [
  { icon: Zap, title: 'Auto-Scaling', desc: 'Pods skalieren basierend auf CPU/Traffic', status: 'Aktiv', last: 'Gerade eben' },
  { icon: Shield, title: 'Sicherheits-Scans', desc: 'Dependency-Vulns & Container-Scans', status: 'Aktiv', last: 'vor 4h' },
  { icon: Database, title: 'Backup & Replikation', desc: 'DB-Backups + Cross-Region-Replikation', status: 'Aktiv', last: 'vor 12h' },
  { icon: Bell, title: 'Alert-Routing', desc: 'P1 -> PagerDuty, P2 -> Slack, P3 -> E-Mail', status: 'Aktiv', last: 'laufend' },
  { icon: Mail, title: 'Report-Generierung', desc: 'Tägliche/Monatliche Reports per E-Mail', status: 'Aktiv', last: 'vor 2h' },
];

const dataSources = [
  { name: 'PostgreSQL Primary', status: 'ok', latency: '12ms', sync: 'Echtzeit' },
  { name: 'Redis Cache', status: 'ok', latency: '2ms', sync: 'Echtzeit' },
  { name: 'Elasticsearch', status: 'ok', latency: '45ms', sync: 'Near-Realtime' },
  { name: 'S3 Buckets', status: 'ok', latency: '89ms', sync: 'Event-Driven' },
  { name: 'Stripe API', status: 'ok', latency: '320ms', sync: 'Webhook' },
  { name: 'Partner API (ERP)', status: 'warn', latency: '1200ms', sync: 'Batch' },
];

function AnimatedNumber({ value, prefix = '', suffix = '' }) {
  const [display, setDisplay] = useState(0);
  useEffect(() => {
    const target = typeof value === 'string' ? parseFloat(value.replace(/[^0-9.]/g, '')) : value;
    const duration = 1000;
    const start = performance.now();
    const animate = (now) => {
      const progress = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = Math.floor(eased * target);
      setDisplay(current);
      if (progress < 1) requestAnimationFrame(animate);
    };
    requestAnimationFrame(animate);
  }, [value]);
  return <span>{prefix}{display.toLocaleString()}{suffix}</span>;
}

function KPICard({ label, value, prefix, suffix, trend, trendValue, icon: Icon, color }) {
  const colorMap = {
    blue: { bg: 'rgba(59,130,246,0.1)', color: '#3b82f6' },
    green: { bg: 'rgba(34,197,94,0.1)', color: '#22c55e' },
    purple: { bg: 'rgba(168,85,247,0.1)', color: '#a855f7' },
    orange: { bg: 'rgba(245,158,11,0.1)', color: '#f59e0b' },
    red: { bg: 'rgba(239,68,68,0.1)', color: '#ef4444' },
  };
  const c = colorMap[color] || colorMap.blue;
  return (
    <div className="card animate-fade-in">
      <div className="card-header">
        <span className="card-label">{label}</span>
        <div className="card-icon" style={{ background: c.bg, color: c.color }}>
          <Icon size={18} />
        </div>
      </div>
      <div className="card-value">
        <AnimatedNumber value={value} prefix={prefix} suffix={suffix} />
      </div>
      <div className="card-sub">
        {trend === 'up' ? <TrendingUp size={14} className="trend-up" /> : <TrendingDown size={14} className="trend-down" />}
        <span className={trend === 'up' ? 'trend-up' : 'trend-down'}>{trendValue}</span>
        <span>vs. letzte Periode</span>
      </div>
    </div>
  );
}

export default function App() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 30000);
    return () => clearInterval(timer);
  }, []);

  const timeStr = now.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
  const dateStr = now.toLocaleDateString('de-DE', { weekday: 'long', day: '2-digit', month: 'long', year: 'numeric' });

  return (
    <div className="app-container">
      {/* HEADER */}
      <header className="dashboard-header animate-fade-in">
        <div className="header-left">
          <div className="header-logo">1</div>
          <div className="header-title">
            <h1>Unified Operations Dashboard</h1>
            <span>{dateStr} &middot; {timeStr} Uhr</span>
          </div>
        </div>
        <div className="header-right">
          <div className="live-badge">
            <span className="live-dot pulse-green" />
            Live-Daten
          </div>
          <div className="automation-badge">
            <Zap size={14} />
            94% Automatisierung
          </div>
        </div>
      </header>

      {/* COMPARISON HERO */}
      <div className="comparison-hero animate-fade-in">
        <div className="comparison-side">
          <h2>Aktueller Zustand</h2>
          <div className="comparison-number negative">1.000+</div>
          <div className="comparison-desc">Fragmentierte Mini-Dashboards<br />Schwer wartbar, inkonsistent, teuer</div>
          <div className="fragmented-grid" style={{ marginTop: 16, maxWidth: 200, margin: '16px auto 0' }}>
            {Array.from({ length: 24 }).map((_, i) => (
              <div key={i} className="fragment-box">{i + 1}</div>
            ))}
          </div>
        </div>
        <div className="comparison-vs">
          <div className="vs-circle">VS</div>
          <ArrowRight size={24} className="vs-arrow" />
        </div>
        <div className="comparison-side">
          <h2>Ziel-Zustand</h2>
          <div className="comparison-number positive">1–2</div>
          <div className="comparison-desc">Zentrale Mega-Dashboards<br />Strukturiert, automatisiert, skalierbar</div>
          <div style={{ marginTop: 16, display: 'flex', gap: 8, justifyContent: 'center' }}>
            <div style={{ width: 80, height: 80, background: 'linear-gradient(135deg, #3b82f6, #14b8a6)', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 28, fontWeight: 800 }}>1</div>
            <div style={{ width: 80, height: 80, background: 'var(--border)', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14, color: 'var(--text-muted)' }}>opt.</div>
          </div>
        </div>
      </div>

      {/* KPI CARDS */}
      <section className="section">
        <div className="section-header">
          <h2><Activity size={18} className="icon" /> Kern-KPIs</h2>
          <span className="section-meta">Aktualisiert: {timeStr} Uhr</span>
        </div>
        <div className="card-grid">
          <KPICard label="Gesamt-Traffic (24h)" value={21900} suffix="" trend="up" trendValue="+12.4%" icon={Globe} color="blue" />
          <KPICard label="Umsatz (7 Tage)" value={111700} prefix="€" suffix="" trend="up" trendValue="+8.2%" icon={DollarSign} color="green" />
          <KPICard label="Aktive Nutzer" value={8420} suffix="" trend="up" trendValue="+5.1%" icon={Users} color="purple" />
          <KPICard label="System-Auslastung" value={67} suffix="%" trend="down" trendValue="-3%" icon={Cpu} color="orange" />
          <KPICard label="Offene Alerts" value={3} suffix="" trend="down" trendValue="-40%" icon={AlertTriangle} color="red" />
          <KPICard label="API-Antwortzeit" value={45} suffix="ms" trend="down" trendValue="-8ms" icon={Zap} color="blue" />
        </div>
      </section>

      {/* CHARTS */}
      <section className="section">
        <div className="section-header">
          <h2><TrendingUp size={18} className="icon" /> Trends & Verteilung</h2>
          <span className="section-meta">Automatisch aggregiert aus 6 Datenquellen</span>
        </div>
        <div className="card-grid-2">
          <div className="chart-card animate-fade-in">
            <h3>Traffic-Verlauf (24h) – vs. gestern</h3>
            <ResponsiveContainer width="100%" height={240}>
              <AreaChart data={trafficData}>
                <defs>
                  <linearGradient id="grad1" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="name" stroke="#64748b" fontSize={12} />
                <YAxis stroke="#64748b" fontSize={12} />
                <Tooltip
                  contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
                  labelStyle={{ color: '#94a3b8' }}
                />
                <Area type="monotone" dataKey="value" stroke="#3b82f6" strokeWidth={2} fill="url(#grad1)" />
                <Line type="monotone" dataKey="prev" stroke="#64748b" strokeDasharray="4 4" strokeWidth={1} dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <div className="chart-card animate-fade-in">
            <h3>Umsatz pro Tag (7 Tage)</h3>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={revenueData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="name" stroke="#64748b" fontSize={12} />
                <YAxis stroke="#64748b" fontSize={12} tickFormatter={(v) => `€${(v/1000).toFixed(0)}k`} />
                <Tooltip
                  contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
                  formatter={(v) => [`€${v.toLocaleString()}`, 'Umsatz']}
                />
                <Bar dataKey="value" fill="#14b8a6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </section>

      {/* MIDDLE ROW: PIE + AUTOMATION */}
      <section className="section">
        <div className="card-grid-2">
          <div className="chart-card animate-fade-in">
            <h3>Traffic-Quellen</h3>
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={pieData} cx="50%" cy="50%" innerRadius={60} outerRadius={90} paddingAngle={4} dataKey="value">
                  {pieData.map((entry, index) => (
                    <Cell key={index} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }} />
              </PieChart>
            </ResponsiveContainer>
            <div style={{ display: 'flex', justifyContent: 'center', gap: 16, flexWrap: 'wrap' }}>
              {pieData.map((d) => (
                <div key={d.name} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#94a3b8' }}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: d.color }} />
                  {d.name} ({d.value}%)
                </div>
              ))}
            </div>
          </div>

          <div className="card animate-fade-in">
            <div className="section-header" style={{ marginBottom: 8 }}>
              <h2 style={{ fontSize: 14 }}><Zap size={16} className="icon" /> Automatisierung</h2>
              <span className="section-meta">{automations.filter(a => a.status === 'Aktiv').length}/{automations.length} aktiv</span>
            </div>
            {automations.map((auto) => (
              <div key={auto.title} className="auto-item">
                <div className="auto-item-icon"><auto.icon size={16} /></div>
                <div className="auto-item-info">
                  <div className="auto-item-title">{auto.title}</div>
                  <div className="auto-item-desc">{auto.desc}</div>
                </div>
                <div className="auto-item-meta">
                  <div className="status ok"><span className="status-dot" />{auto.status}</div>
                  <div style={{ fontSize: 11, marginTop: 2 }}>{auto.last}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ALERTS TABLE */}
      <section className="section">
        <div className="section-header">
          <h2><Bell size={18} className="icon" /> Letzte Ereignisse & Automatische Aktionen</h2>
          <span className="section-meta">Nur P1-P3 Alerts, keine Noise-Alerts</span>
        </div>
        <div className="table-card animate-fade-in">
          <table>
            <thead>
              <tr>
                <th>Status</th>
                <th>Ereignis</th>
                <th>Quelle</th>
                <th>Zeit</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((alert) => (
                <tr key={alert.id}>
                  <td>
                    <span className={`status ${alert.type}`}>
                      <span className="status-dot" />
                      {alert.type === 'auto' ? 'Auto' : alert.type === 'ok' ? 'OK' : 'Warn'}
                    </span>
                  </td>
                  <td>{alert.title}</td>
                  <td>{alert.source}</td>
                  <td style={{ color: 'var(--text-muted)' }}>{alert.time}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* DATA SOURCES */}
      <section className="section">
        <div className="section-header">
          <h2><Database size={18} className="icon" /> Datenquellen-Health</h2>
          <span className="section-meta">Alle Quellen in einem Blick</span>
        </div>
        <div className="table-card animate-fade-in">
          <table>
            <thead>
              <tr>
                <th>Quelle</th>
                <th>Status</th>
                <th>Latenz</th>
                <th>Synchronisation</th>
                <th>Health</th>
              </tr>
            </thead>
            <tbody>
              {dataSources.map((ds) => (
                <tr key={ds.name}>
                  <td>{ds.name}</td>
                  <td>
                    <span className={`status ${ds.status}`}>
                      <span className="status-dot" />
                      {ds.status === 'ok' ? 'Healthy' : 'Degraded'}
                    </span>
                  </td>
                  <td>{ds.latency}</td>
                  <td>{ds.sync}</td>
                  <td>
                    <div className="progress-bar" style={{ width: 120 }}>
                      <div className="progress-fill" style={{ width: ds.status === 'ok' ? '96%' : '72%', background: ds.status === 'ok' ? '#22c55e' : '#f59e0b' }} />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* ARGUMENTS */}
      <section className="section">
        <div className="card-grid-2">
          <div className="argument-box animate-fade-in">
            <h3><Layers size={16} style={{ verticalAlign: 'middle', marginRight: 8 }} />Warum 1–2 Dashboards besser sind</h3>
            <ul>
              <li><strong>Single Source of Truth</strong> – keine widersprüchlichen Zahlen zwischen Tools</li>
              <li><strong>Wartungsaufwand -90%</strong> – ein Codebase statt 1.000 Fragmente</li>
              <li><strong>Automatisierung zentral</strong> – Alerts, Actions, Scaling aus einer Hand</li>
              <li><strong>Onboarding-Neulinge</strong> – neuer Mitarbeiter findet sich in Minuten zurecht</li>
              <li><strong>Konsistentes UX</strong> – gleiche Farben, Muster, Interaktionen überall</li>
              <li><strong>Skalierbarkeit</strong> – neue KPIs = neue Zeile, neues Dashboard</li>
            </ul>
          </div>
          <div className="argument-box animate-fade-in">
            <h3><CheckCircle size={16} style={{ verticalAlign: 'middle', marginRight: 8 }} />Was diese Demo zeigt</h3>
            <ul>
              <li><strong>Live-Daten</strong> – Echtzeit-Aggregation aus 6 Quellen</li>
              <li><strong>94% Automatisierung</strong> – nur kritische Alerts schlagen durch</li>
              <li><strong>~2.000 Wörter Inhalt</strong> – maximal, dafür hohe Informationsdichte</li>
              <li><strong>Self-healing</strong> – Systeme regulieren sich selbst (CPU-Drosselung, Cleanup)</li>
              <li><strong>Proaktiv statt reaktiv</strong> – Warnungen bevor etwas kaputt geht</li>
              <li><strong>Ein Blick genügt</strong> – kein Tab-Hopping, kein Kontextwechsel</li>
            </ul>
          </div>
        </div>
      </section>

      {/* FOOTER */}
      <footer style={{ textAlign: 'center', padding: '24px 0', color: 'var(--text-muted)', fontSize: 13, borderTop: '1px solid var(--border)', marginTop: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'center', gap: 24, marginBottom: 8, flexWrap: 'wrap' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}><CheckCircle size={14} color="#22c55e" /> Alle Systeme operational</span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}><Clock size={14} /> Letzter Deploy: vor 3h</span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}><Server size={14} /> 12 Services / 3 Regionen</span>
        </div>
        Dashboard-Demo &middot; Eins statt Tausend &middot; Automatisierung statt Fragmentierung
      </footer>
    </div>
  );
}
