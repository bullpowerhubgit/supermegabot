import React from 'react';
import {
  Cpu, HardDrive, MemoryStick, Server, AlertTriangle, AlertOctagon,
  Cloud, Activity, Clock, FolderSync, XCircle
} from 'lucide-react';
import { useDashboardData } from '../hooks/useDashboardData';

function formatBytes(mb: number): string {
  if (mb > 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${Math.round(mb)} MB`;
}

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h ${m}m`;
  return `${h}h ${m}m`;
}

function ProgressBar({ value, thresholds }: { value: number; thresholds?: { warn: number; crit: number } }) {
  const t = thresholds || { warn: 70, crit: 90 };
  let color = 'bg-emerald-500';
  if (value >= t.crit) color = 'bg-rose-500';
  else if (value >= t.warn) color = 'bg-amber-500';
  return (
    <div className="w-full h-2 bg-slate-700/50 rounded-full overflow-hidden mt-1.5">
      <div
        className={`h-full rounded-full transition-all duration-500 ${color}`}
        style={{ width: `${Math.min(value, 100)}%` }}
      />
    </div>
  );
}

function StatCard({ icon, label, value, sub, progress }: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub?: string;
  progress?: { value: number; thresholds?: { warn: number; crit: number } };
}) {
  return (
    <div className="card">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-md bg-indigo-500/10 text-indigo-400">{icon}</div>
          <span className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">{label}</span>
        </div>
      </div>
      <div className="text-xl font-bold text-slate-100 mt-2">{value}</div>
      {sub && <div className="text-xs text-slate-400 mt-0.5">{sub}</div>}
      {progress && <ProgressBar value={progress.value} thresholds={progress.thresholds} />}
    </div>
  );
}

export default function SystemPanel() {
  const { data, loading, error, connected } = useDashboardData();

  if (loading) {
    return (
      <div className="card mb-8">
        <div className="flex items-center gap-2 text-slate-400 text-sm">
          <Activity size={16} className="animate-pulse" />
          Systemdaten werden geladen...
        </div>
      </div>
    );
  }

  if (error || !connected) {
    return (
      <div className="card mb-8 border-rose-500/30">
        <div className="flex items-center gap-2 text-rose-400 text-sm">
          <XCircle size={16} />
          Keine Verbindung zum Super-Server. Bitte sicherstellen, dass <code className="bg-slate-800 px-1 rounded">super-server.js</code> auf Port 9001 läuft.
        </div>
      </div>
    );
  }

  const sys = data.system;
  const cpu = data.cpu;
  const disks = data.disks;
  const processes = data.processes;
  const alerts = data.alerts;
  const cloud = data.cloudStorage;
  const server = data.server;

  return (
    <section className="mb-8">
      <div className="flex items-center justify-between mb-4">
        <h2 className="section-title flex items-center gap-2">
          <Server size={18} className="text-indigo-400" />
          Live-Systemmonitor — Echte Daten aus dem Super-Server
        </h2>
        <div className="flex items-center gap-3 text-xs text-slate-500">
          <span className="flex items-center gap-1.5">
            <span className={`w-2 h-2 rounded-full ${connected ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'}`} />
            {connected ? 'Echtzeit' : 'Offline'}
          </span>
          <span>PID {server.pid}</span>
          <span>Uptime {formatUptime(sys.uptime)}</span>
        </div>
      </div>

      {/* System Stats Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard
          icon={<MemoryStick size={16} />}
          label="Memory"
          value={`${sys.percent}%`}
          sub={`${formatBytes(sys.usedmem)} / ${formatBytes(sys.totalmem)}`}
          progress={{ value: sys.percent, thresholds: { warn: 70, crit: 90 } }}
        />
        <StatCard
          icon={<Cpu size={16} />}
          label="CPU"
          value={`${cpu.usage}%`}
          sub={`${cpu.cores} Cores · Load ${cpu.loadavg[0].toFixed(2)}`}
          progress={{ value: cpu.usage, thresholds: { warn: 70, crit: 90 } }}
        />
        <StatCard
          icon={<HardDrive size={16} />}
          label="Disk"
          value={disks.length > 0 ? `${Math.round(disks.reduce((s, d) => s + d.usePercent, 0) / disks.length)}%` : 'N/A'}
          sub={disks.map(d => `${d.name}: ${d.usePercent}%`).join(' · ') || 'Keine Daten'}
        />
        <StatCard
          icon={<Clock size={16} />}
          label="Uptime"
          value={formatUptime(sys.uptime)}
          sub={`Server PID ${server.pid}`}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Top Processes */}
        <div className="lg:col-span-2 card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="section-title flex items-center gap-2">
              <Activity size={16} className="text-indigo-400" />
              Top Prozesse
            </h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700/50 text-left text-[10px] uppercase tracking-wider text-slate-500">
                  <th className="pb-2 pr-3">PID</th>
                  <th className="pb-2 pr-3">Name</th>
                  <th className="pb-2 pr-3">CPU %</th>
                  <th className="pb-2 pr-3">RAM</th>
                  <th className="pb-2">RAM %</th>
                </tr>
              </thead>
              <tbody>
                {processes.map((p) => (
                  <tr key={p.pid} className="border-b border-slate-800/50 last:border-0">
                    <td className="py-2 pr-3 text-slate-500 font-mono text-xs">{p.pid}</td>
                    <td className="py-2 pr-3 text-slate-200 font-medium">{p.name}</td>
                    <td className="py-2 pr-3 text-slate-300">{p.cpuPercent.toFixed(1)}%</td>
                    <td className="py-2 pr-3 text-slate-300">{p.memMB} MB</td>
                    <td className="py-2">
                      <span className={`text-xs font-medium ${p.memPercent > 10 ? 'text-amber-400' : 'text-slate-400'}`}>
                        {p.memPercent.toFixed(1)}%
                      </span>
                    </td>
                  </tr>
                ))}
                {processes.length === 0 && (
                  <tr><td colSpan={5} className="py-4 text-slate-500 text-center text-xs">Keine Prozessdaten verfügbar</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Alerts & Cloud */}
        <div className="space-y-6">
          {/* Active Alerts */}
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h3 className="section-title flex items-center gap-2">
                <AlertTriangle size={16} className="text-amber-400" />
                Alerts
              </h3>
              <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${alerts.length > 0 ? 'bg-rose-500/15 text-rose-400' : 'bg-emerald-500/15 text-emerald-400'}`}>
                {alerts.length}
              </span>
            </div>
            <div className="space-y-2 max-h-[200px] overflow-y-auto">
              {alerts.length === 0 ? (
                <div className="flex items-center gap-2 text-emerald-400 text-sm py-2">
                  <span className="w-2 h-2 rounded-full bg-emerald-500" />
                  Keine aktiven Alerts
                </div>
              ) : (
                alerts.map((a, i) => (
                  <div
                    key={i}
                    className={`flex items-start gap-2 p-2.5 rounded-lg text-xs border-l-2 ${
                      a.type === 'critical'
                        ? 'bg-rose-500/10 border-rose-500 text-rose-300'
                        : 'bg-amber-500/10 border-amber-500 text-amber-300'
                    }`}
                  >
                    {a.type === 'critical' ? <AlertOctagon size={14} /> : <AlertTriangle size={14} />}
                    <div>
                      <div className="font-medium">{a.message}</div>
                      <div className="opacity-70 text-[10px] mt-0.5">{a.source} · {new Date(a.timestamp).toLocaleTimeString('de-DE')}</div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Cloud Storage */}
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h3 className="section-title flex items-center gap-2">
                <Cloud size={16} className="text-indigo-400" />
                Cloud-Services
              </h3>
            </div>
            <div className="space-y-2">
              {cloud.map((c) => (
                <div key={c.name} className="flex items-center justify-between text-xs">
                  <span className="text-slate-300">{c.name}</span>
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-medium ${
                    c.status === 'running' ? 'bg-emerald-500/15 text-emerald-400' :
                    c.status === 'stopped' ? 'bg-rose-500/15 text-rose-400' :
                    'bg-slate-500/15 text-slate-400'
                  }`}>
                    {c.status === 'running' ? <FolderSync size={10} /> : c.status === 'stopped' ? <XCircle size={10} /> : <Cloud size={10} />}
                    {c.status === 'running' ? 'Aktiv' : c.status === 'stopped' ? 'Gestoppt' : 'N/A'}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Disk Detail */}
          <div className="card">
            <div className="flex items-center justify-between mb-3">
              <h3 className="section-title flex items-center gap-2">
                <HardDrive size={16} className="text-indigo-400" />
                Speicher
              </h3>
            </div>
            <div className="space-y-3">
              {disks.map((d) => (
                <div key={d.filesystem}>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-slate-300">{d.name}</span>
                    <span className="text-slate-400">{d.used} / {d.size}</span>
                  </div>
                  <ProgressBar value={d.usePercent} thresholds={{ warn: 75, crit: 90 }} />
                </div>
              ))}
              {disks.length === 0 && (
                <div className="text-xs text-slate-500">Keine Laufwerksdaten verfügbar</div>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
