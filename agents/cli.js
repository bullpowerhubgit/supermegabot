#!/usr/bin/env node
import './core/env.js';
import path from 'node:path';
import db, { ROOT } from './core/db.js';
import * as inventory from './agents/inventory.js';
import * as classification from './agents/classification.js';
import * as reporting from './agents/reporting.js';
import * as broker from './agents/sys08-intelligence-broker.js';

const [, , cmd, ...args] = process.argv;

function table(rows) {
  if (rows.length === 0) { console.log('(leer)'); return; }
  console.table(rows);
}

const commands = {
  async status() {
    const q = (sql) => db.prepare(sql).get().n;
    console.log('SuperMegaBot Agenten — Status');
    console.log(`  Kunden:            ${q('SELECT COUNT(*) n FROM clients')}`);
    console.log(`  KI-Systeme:        ${q('SELECT COUNT(*) n FROM ai_systems')}`);
    console.log(`  Klassifiziert:     ${q("SELECT COUNT(*) n FROM classifications WHERE risk_level != 'pending'")}`);
    console.log(`  Offen (pending):   ${q("SELECT COUNT(*) n FROM classifications WHERE risk_level = 'pending'")}`);
    console.log(`  Intel-Quellen:     ${q('SELECT COUNT(*) n FROM intel_sources WHERE enabled=1')}`);
    console.log(`  Intel-Signale:     ${q('SELECT COUNT(*) n FROM intel_signals')}  (Leads: ${q("SELECT COUNT(*) n FROM intel_signals WHERE relevance='lead'")})`);
    console.log(`  Queue offen:       ${q("SELECT COUNT(*) n FROM tasks WHERE status='queued'")}`);
    const runs = db.prepare('SELECT agent, ok, summary, ran_at FROM agent_runs ORDER BY id DESC LIMIT 5').all();
    if (runs.length) { console.log('\nLetzte Läufe:'); table(runs); }
  },

  async intake(file) {
    if (!file) throw new Error('Usage: cli.js intake <datei.json>');
    const r = inventory.intakeFile(path.resolve(file));
    console.log(`OK: ${r.systems} Systeme für ${r.client} übernommen`);
  },

  async classify(clientSlug) {
    const r = await classification.run({ clientSlug: clientSlug || null, batchSize: 100 });
    console.log(`Regel: ${r.byRule} · LLM: ${r.byLlm} · offen: ${r.pending} (von ${r.total})`);
    if (r.pending > 0) process.exitCode = 1;
  },

  async report(clientSlug) {
    if (!clientSlug) throw new Error('Usage: cli.js report <kunden-slug>');
    const r = reporting.buildClientReport(clientSlug);
    console.log(`Report geschrieben: ${r.file}`);
    console.log(`Risikoverteilung: ${JSON.stringify(r.counts)}`);
  },

  async 'broker:add-source'(url, ...nameParts) {
    if (!url) throw new Error('Usage: cli.js broker:add-source <rss-url> [name]');
    const s = broker.addSource(url, nameParts.join(' ') || null);
    console.log(`Quelle #${s.id} aktiv: ${s.name} (${s.url})`);
  },

  async 'broker:pull'() {
    const r = await broker.run();
    console.log(`Neue Signale: ${r.newSignals} · klassifiziert: ${r.classified} · offen: ${r.pending} · Quellen-Fehler: ${r.pullErrors}`);
    if (r.pullErrors > 0 || r.pending > 0) process.exitCode = 1;
  },

  async 'broker:sources'() {
    table(db.prepare('SELECT id, name, url, enabled, last_pull, last_error FROM intel_sources').all());
  },

  async signals(limit = '20') {
    table(db.prepare('SELECT id, relevance, title, link, published FROM intel_signals ORDER BY id DESC LIMIT ?').all(parseInt(limit, 10)));
  },

  async queue(agent, payloadJson) {
    if (!agent) { table(db.prepare('SELECT id, agent, status, error, created_at FROM tasks ORDER BY id DESC LIMIT 20').all()); return; }
    const info = db.prepare('INSERT INTO tasks (agent, payload) VALUES (?,?)').run(agent, payloadJson || null);
    console.log(`Task #${info.lastInsertRowid} für ${agent} eingereiht (Orchestrator muss laufen)`);
  },

  async help() {
    console.log(`Kommandos:
  status                                Gesamtübersicht
  intake <datei.json>                   Kunden-Inventar aufnehmen
  classify [kunden-slug]                Risikoklassifizierung (Regeln + Claude)
  report <kunden-slug>                  Compliance-Report nach reports/ schreiben
  broker:add-source <rss-url> [name]    SYS-08: Quelle hinzufügen
  broker:pull                           SYS-08: Quellen ziehen + Signale klassifizieren
  broker:sources                        SYS-08: Quellenliste
  signals [limit]                       Letzte Intel-Signale
  queue [agent] [payload-json]          Queue ansehen / Task einreihen

Intake-JSON-Schema:
  { "client": { "slug": "acme", "name": "ACME GmbH", "contact": "cto@acme.de" },
    "systems": [ { "name": "...", "vendor": "...", "purpose": "...",
                   "data_types": "...", "users": "...", "deployment": "intern",
                   "is_gpai": false } ] }`);
  }
};

const fn = commands[cmd || 'help'];
if (!fn) { console.error(`Unbekanntes Kommando: ${cmd}\n`); await commands.help(); process.exit(1); }
try {
  await fn(...args);
} catch (e) {
  console.error(`FEHLER: ${e.message}`);
  process.exit(1);
}
