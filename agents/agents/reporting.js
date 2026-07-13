import fs from 'node:fs';
import path from 'node:path';
import db, { ROOT } from '../core/db.js';
import { log, recordRun, telegramNotify } from '../core/util.js';

const AGENT = 'reporting';
const REPORT_DIR = path.join(ROOT, 'reports');

const LEVEL_LABEL = {
  unacceptable: 'Unzulässig (Art. 5)',
  high: 'Hochrisiko (Anhang III)',
  limited: 'Begrenztes Risiko (Art. 50)',
  minimal: 'Minimales Risiko',
  pending: 'OFFEN — noch nicht klassifiziert'
};

export function buildClientReport(clientSlug) {
  const client = db.prepare('SELECT * FROM clients WHERE slug=?').get(clientSlug);
  if (!client) throw new Error(`Unbekannter Kunde: ${clientSlug}`);

  const systems = db.prepare(`
    SELECT s.*, k.risk_level, k.method, k.rationale, k.obligations, k.classified_at
    FROM ai_systems s LEFT JOIN classifications k ON k.system_id = s.id
    WHERE s.client_id=? ORDER BY
      CASE k.risk_level WHEN 'unacceptable' THEN 0 WHEN 'high' THEN 1 WHEN 'limited' THEN 2 WHEN 'minimal' THEN 3 ELSE 4 END, s.name
  `).all(client.id);
  if (systems.length === 0) throw new Error(`Kein Inventar für ${clientSlug} — zuerst Intake ausführen`);

  const counts = {};
  for (const s of systems) counts[s.risk_level ?? 'pending'] = (counts[s.risk_level ?? 'pending'] || 0) + 1;

  const signals = db.prepare(`
    SELECT * FROM intel_signals WHERE relevance IN ('regulatorisch','lead')
    ORDER BY id DESC LIMIT 10
  `).all();

  const now = new Date().toISOString().slice(0, 16).replace('T', ' ');
  const lines = [];
  lines.push(`# AI-Act Compliance-Report — ${client.name}`);
  lines.push('');
  lines.push(`Stand: ${now} UTC · Systeme im Inventar: ${systems.length}`);
  lines.push('');
  lines.push('## Risikoverteilung');
  lines.push('');
  for (const lvl of ['unacceptable', 'high', 'limited', 'minimal', 'pending']) {
    if (counts[lvl]) lines.push(`- ${LEVEL_LABEL[lvl]}: **${counts[lvl]}**`);
  }
  lines.push('');
  lines.push('## Systeme im Detail');
  for (const s of systems) {
    const lvl = s.risk_level ?? 'pending';
    lines.push('');
    lines.push(`### ${s.name} — ${LEVEL_LABEL[lvl]}`);
    if (s.vendor) lines.push(`- Anbieter: ${s.vendor}`);
    if (s.purpose) lines.push(`- Zweck: ${s.purpose}`);
    if (s.deployment) lines.push(`- Einsatz: ${s.deployment}${s.is_gpai ? ' · GPAI-Komponente' : ''}`);
    if (s.rationale) lines.push(`- Einordnung (${s.method === 'rule' ? 'Regelwerk' : 'KI-Analyse'}): ${s.rationale}`);
    const obligations = s.obligations ? JSON.parse(s.obligations) : [];
    if (obligations.length > 0) {
      lines.push('- Pflichten:');
      for (const o of obligations) lines.push(`  - ${o}`);
    }
    if (lvl === 'pending') lines.push('- ⚠ Klassifizierung steht aus — kein Ergebnis vorgetäuscht.');
  }
  if (signals.length > 0) {
    lines.push('');
    lines.push('## Regulatorische Signale & Lead-Hinweise (SYS-08)');
    for (const sig of signals) {
      lines.push(`- [${sig.relevance}] ${sig.title}${sig.link ? ` — ${sig.link}` : ''}`);
    }
  }
  lines.push('');
  lines.push('---');
  lines.push('Automatisch erstellt vom SuperMegaBot Reporting-Agent. Keine Rechtsberatung.');

  fs.mkdirSync(REPORT_DIR, { recursive: true });
  const file = path.join(REPORT_DIR, `${clientSlug}_${new Date().toISOString().slice(0, 10)}.md`);
  fs.writeFileSync(file, lines.join('\n'), 'utf8');
  return { file, systems: systems.length, counts };
}

/** Täglicher Digest: Reports für alle Kunden + Telegram-Kurzfassung. */
export async function run() {
  const t0 = Date.now();
  const clients = db.prepare('SELECT slug FROM clients').all();
  const results = [];
  for (const c of clients) {
    try {
      results.push(buildClientReport(c.slug));
    } catch (e) {
      log(AGENT, `Report ${c.slug} übersprungen: ${e.message}`);
    }
  }

  const leads = db.prepare("SELECT COUNT(*) n FROM intel_signals WHERE relevance='lead'").get().n;
  const reg = db.prepare("SELECT COUNT(*) n FROM intel_signals WHERE relevance='regulatorisch'").get().n;
  const summary = `${results.length} Report(s) erstellt · Signale gesamt: ${leads} Leads, ${reg} regulatorisch`;
  log(AGENT, summary);

  try {
    const sent = await telegramNotify(`📊 SuperMegaBot Reporting\n${summary}`);
    if (sent) log(AGENT, 'Telegram-Digest gesendet');
  } catch (e) {
    log(AGENT, `Telegram-Digest fehlgeschlagen: ${e.message}`);
  }

  if (clients.length > 0) recordRun(AGENT, true, summary, Date.now() - t0);
  return { reports: results.map(r => r.file) };
}
