import React from 'react'
import {
  Activity, AlertTriangle, ArrowUpRight,
  BarChart3, Bot, CheckCircle2, ChevronRight, Clock,
  GitPullRequest, LayoutDashboard, Minus,
  RefreshCw, Shield, Sparkles, TrendingDown,
  Users, Zap
} from 'lucide-react'
import {
  AreaChart, Area, CartesianGrid,
  ResponsiveContainer, Tooltip, XAxis, YAxis, Legend
} from 'recharts'
import SystemPanel from './SystemPanel'
import {
  kpis, automationFlows, chartData, actionItems, dashboardComparison
} from '../data/dashboardData'

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { color: string; icon: React.ReactNode }> = {
    running: { color: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30', icon: <RefreshCw size={12} /> },
    paused: { color: 'bg-amber-500/15 text-amber-400 border-amber-500/30', icon: <Clock size={12} /> },
    error: { color: 'bg-rose-500/15 text-rose-400 border-rose-500/30', icon: <AlertTriangle size={12} /> },
  }
  const s = map[status] || map.paused
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${s.color}`}>
      {s.icon}
      {status === 'running' ? 'Aktiv' : status === 'paused' ? 'Pausiert' : 'Fehler'}
    </span>
  )
}

function PriorityBadge({ p }: { p: string }) {
  const colors: Record<string, string> = {
    high: 'bg-rose-500/15 text-rose-400 border-rose-500/30',
    medium: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
    low: 'bg-slate-500/15 text-slate-400 border-slate-500/30',
  }
  const labels: Record<string, string> = { high: 'Hoch', medium: 'Mittel', low: 'Niedrig' }
  return (
    <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium border ${colors[p]}`}>
      {labels[p]}
    </span>
  )
}

export default function Dashboard() {
  return (
    <div className="max-w-[1400px] mx-auto p-6">
      {/* Header */}
      <header className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <div className="p-2.5 bg-indigo-500/15 rounded-lg border border-indigo-500/20">
            <LayoutDashboard className="text-indigo-400" size={24} />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-slate-100 tracking-tight">
              Mega Dashboard
            </h1>
            <p className="text-sm text-slate-400">
              Eine zentrale Wahrheit statt 1.000 fragmentierter Ansichten – automatisiert, verdichtet, handlungsorientiert
            </p>
          </div>
        </div>
        <div className="flex items-center gap-4 mt-4 text-xs text-slate-500">
          <span className="flex items-center gap-1.5">
            <RefreshCw size={12} className="text-emerald-400 animate-spin" style={{ animationDuration: '3s' }} />
            Letzte Aktualisierung: Echtzeit
          </span>
          <span className="flex items-center gap-1.5">
            <Bot size={12} className="text-indigo-400" />
            98% der Metriken automatisiert
          </span>
        </div>
      </header>

      {/* KPI Grid */}
      <section className="mb-8">
        <h2 className="section-title mb-4 flex items-center gap-2">
          <BarChart3 size={18} className="text-indigo-400" />
          Kennzahlen – Live & Automatisiert
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          {kpis.map((kpi, i) => (
            <div key={i} className="card hover:bg-slate-800 transition-colors">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">{kpi.label}</span>
                {kpi.automated && <Bot size={12} className="text-indigo-400 opacity-60" />}
              </div>
              <div className="text-xl font-bold text-slate-100">{kpi.value}</div>
              <div className="flex items-center gap-1 mt-1">
                {kpi.trend === 'up' ? (
                  kpi.change > 0 ? (
                    <ArrowUpRight size={14} className="kpi-positive" />
                  ) : (
                    <TrendingDown size={14} className="kpi-positive" />
                  )
                ) : (
                  <Minus size={14} className="text-slate-500" />
                )}
                <span className={`text-xs font-medium ${kpi.change > 0 ? 'text-emerald-400' : kpi.change < 0 ? 'text-emerald-400' : 'text-slate-500'}`}>
                  {kpi.change > 0 ? '+' : ''}{kpi.change}%
                </span>
                <span className="text-[10px] text-slate-600 ml-1">vs. Vorwoche</span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Live System Data */}
      <SystemPanel />

      {/* Main Grid: Charts + Automation + Actions */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {/* Chart */}
        <div className="lg:col-span-2 card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="section-title flex items-center gap-2">
              <Activity size={18} className="text-indigo-400" />
              Traffic & Fehlerrate (7 Tage)
            </h2>
            <span className="text-xs text-slate-500">Datenquelle: Prometheus / Grafana (auto-aggregiert)</span>
          </div>
          <div className="h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="c1" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="c2" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
                <XAxis dataKey="name" stroke="#64748b" fontSize={12} tickLine={false} axisLine={false} />
                <YAxis stroke="#64748b" fontSize={12} tickLine={false} axisLine={false} />
                <Tooltip
                  contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '8px', fontSize: '12px' }}
                  itemStyle={{ color: '#cbd5e1' }}
                />
                <Legend wrapperStyle={{ fontSize: '12px', paddingTop: '10px' }} />
                <Area type="monotone" dataKey="value1" name="Requests/min" stroke="#6366f1" fill="url(#c1)" strokeWidth={2} />
                <Area type="monotone" dataKey="value2" name="Fehlerfreie Requests" stroke="#10b981" fill="url(#c2)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Automation Status */}
        <div className="card">
          <h2 className="section-title mb-4 flex items-center gap-2">
            <Sparkles size={18} className="text-amber-400" />
            Automatisierungs-Engine
          </h2>
          <div className="space-y-3">
            {automationFlows.map((flow, i) => (
              <div key={i} className="flex items-start justify-between p-3 rounded-lg bg-slate-900/50 border border-slate-700/30">
                <div>
                  <div className="text-sm font-medium text-slate-200">{flow.name}</div>
                  <div className="text-[10px] text-slate-500 mt-0.5">Letzter Lauf: {flow.lastRun} · {flow.frequency}</div>
                  <div className="text-[10px] text-emerald-400 mt-1">{flow.impact}</div>
                </div>
                <StatusBadge status={flow.status} />
              </div>
            ))}
          </div>
          <div className="mt-4 p-3 rounded-lg bg-indigo-500/10 border border-indigo-500/20">
            <div className="text-xs text-indigo-300 font-medium">Automation-Score</div>
            <div className="text-2xl font-bold text-indigo-200 mt-1">94%</div>
            <div className="text-[10px] text-indigo-400/70 mt-1">13 von 14 kritischen Prozessen voll automatisiert</div>
          </div>
        </div>
      </div>

      {/* Comparison Section */}
      <section className="mb-8">
        <h2 className="section-title mb-4 flex items-center gap-2">
          <Zap size={18} className="text-amber-400" />
          Vorher → Nachher: Warum 2 Dashboards genügen
        </h2>
        <div className="card">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            {[
              { label: 'Dashboards', before: dashboardComparison.before.dashboards, after: dashboardComparison.after.dashboards, unit: '' },
              { label: 'Manuelle Checks', before: dashboardComparison.before.manualChecks, after: dashboardComparison.after.manualChecks, unit: '/Tag' },
              { label: 'Discovery-Zeit', before: dashboardComparison.before.avgDiscoveryTime, after: dashboardComparison.after.avgDiscoveryTime, unit: '' },
              { label: 'Wartungsaufwand', before: dashboardComparison.before.maintenanceHours, after: dashboardComparison.after.maintenanceHours, unit: 'h/Woche' },
              { label: 'Alert Fatigue', before: dashboardComparison.before.alertFatigue, after: dashboardComparison.after.alertFatigue, unit: '' },
            ].map((item, i) => (
              <div key={i} className="text-center p-4 rounded-lg bg-slate-900/50 border border-slate-700/30">
                <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-2">{item.label}</div>
                <div className="text-sm text-rose-400 line-through opacity-60">{item.before}{item.unit}</div>
                <div className="flex items-center justify-center gap-1 mt-1">
                  <ChevronRight size={14} className="text-slate-600" />
                  <span className="text-lg font-bold text-emerald-400">{item.after}{item.unit}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Action Items */}
      <section className="mb-8">
        <h2 className="section-title mb-4 flex items-center gap-2">
          <GitPullRequest size={18} className="text-indigo-400" />
          Handlungsbedarf – Priorisiert & Gekürzt
        </h2>
        <div className="card">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700/50 text-left text-[10px] uppercase tracking-wider text-slate-500">
                  <th className="pb-3 pr-4">Priorität</th>
                  <th className="pb-3 pr-4">Aktion</th>
                  <th className="pb-3 pr-4">Verantwortlich</th>
                  <th className="pb-3 pr-4">Fällig</th>
                  <th className="pb-3">Trigger</th>
                </tr>
              </thead>
              <tbody>
                {actionItems.map((item, i) => (
                  <tr key={i} className="border-b border-slate-800/50 last:border-0">
                    <td className="py-3 pr-4"><PriorityBadge p={item.priority} /></td>
                    <td className="py-3 pr-4 text-slate-200">{item.title}</td>
                    <td className="py-3 pr-4 text-slate-400">{item.assignee}</td>
                    <td className="py-3 pr-4 text-slate-400">{item.due}</td>
                    <td className="py-3">
                      {item.autoTriggered ? (
                        <span className="inline-flex items-center gap-1 text-emerald-400 text-xs">
                          <Bot size={12} /> Auto
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-slate-500 text-xs">
                          <Users size={12} /> Manuell
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* Rationale / Manifesto */}
      <section className="mb-8">
        <div className="card-highlight">
          <h2 className="section-title mb-4 flex items-center gap-2">
            <Shield size={18} className="text-indigo-400" />
            Prinzip: Weniger Dashboards, mehr Wirkung
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 text-sm text-slate-300 leading-relaxed">
            <div className="space-y-3">
              <p>
                <strong className="text-slate-100">Das Problem:</strong> Mit jeder neuen Metrik entstand bisher ein separates Dashboard. Nach 47 Ansichten verliert jeder Überblick – Entscheider scrollen, Entwickler suchen, Nachteilsübernahme bleibt auf der Strecke.
              </p>
              <p>
                <strong className="text-slate-100">Die Lösung:</strong> Ein zentrales Mega-Dashboard (und maximal ein zweites für tiefe Dives) bündelt alle kritischen KPIs, Automatisierungs-Status und Handlungsaufforderungen an einem Ort. Kein Kontextwechsel, keine veralteten Ansichten.
              </p>
            </div>
            <div className="space-y-3">
              <p>
                <strong className="text-slate-100">Automatisierung als Pflicht:</strong> Jede Metrik, die manuell geprüft werden muss, ist eine Design-Schwäche. Ziel ist 95%+ Auto-Discovery – vom Health-Check bis zur Kosten-Anomalie.
              </p>
              <p>
                <strong className="text-slate-100">Für Management & Devs:</strong> Das Dashboard spricht beide Sprachen. Oben die Business-Kennzahlen (Verfügbarkeit, Kosten, MTTR), unten die technische Tiefe (Alerts, Deployments, CVEs). Eine Quelle, zwei Perspektiven.
              </p>
            </div>
          </div>
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs">
              <CheckCircle2 size={14} /> 2 Dashboards statt 47
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs">
              <CheckCircle2 size={14} /> 98% Automation-Score
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs">
              <CheckCircle2 size={14} /> 8.5 min → 12 sek Discovery
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs">
              <CheckCircle2 size={14} /> 14h → 1.5h Wartung/Woche
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="text-center text-xs text-slate-600 pt-4 border-t border-slate-800">
        Mega Dashboard v1.0 — Generiert via Code-CLI — Daten automatisch aggregiert aus Prometheus, Grafana, GitHub Actions & AWS Cost Explorer
      </footer>
    </div>
  )
}
