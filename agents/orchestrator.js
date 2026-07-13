import './core/env.js';
import path from 'node:path';
import db, { ROOT } from './core/db.js';
import { log } from './core/util.js';
import * as inventory from './agents/inventory.js';
import * as classification from './agents/classification.js';
import * as reporting from './agents/reporting.js';
import * as broker from './agents/sys08-intelligence-broker.js';

const AGENT = 'orchestrator';
const INTAKE_DIR = path.join(ROOT, 'intake');

const minutes = (name, fallback) => Math.max(1, parseInt(process.env[name] || fallback, 10)) * 60_000;

const SCHEDULE = [
  { name: 'inventory',    every: minutes('INVENTORY_INTERVAL_MIN', '2'),   fn: () => inventory.run({ intakeDir: INTAKE_DIR }) },
  { name: 'classification', every: minutes('CLASSIFY_INTERVAL_MIN', '10'), fn: () => classification.run() },
  { name: 'sys08-broker', every: minutes('BROKER_INTERVAL_MIN', '30'),     fn: () => broker.run() },
  { name: 'reporting',    every: minutes('REPORT_INTERVAL_MIN', '720'),    fn: () => reporting.run() }
];

const AGENTS = {
  inventory: (p) => p?.file ? inventory.intakeFile(p.file) : inventory.run({ intakeDir: INTAKE_DIR }),
  classification: (p) => classification.run(p || {}),
  'sys08-broker': (p) => broker.run(p || {}),
  reporting: (p) => p?.client ? reporting.buildClientReport(p.client) : reporting.run()
};

let running = false;

async function processQueue() {
  const next = db.prepare("SELECT * FROM tasks WHERE status='queued' ORDER BY id LIMIT 1").get();
  if (!next) return;
  db.prepare("UPDATE tasks SET status='running', started_at=datetime('now') WHERE id=?").run(next.id);
  try {
    const payload = next.payload ? JSON.parse(next.payload) : null;
    const fn = AGENTS[next.agent];
    if (!fn) throw new Error(`Unbekannter Agent: ${next.agent}`);
    const result = await fn(payload);
    db.prepare("UPDATE tasks SET status='done', result=?, finished_at=datetime('now') WHERE id=?")
      .run(JSON.stringify(result ?? null), next.id);
    log(AGENT, `Task #${next.id} (${next.agent}) done`);
  } catch (e) {
    db.prepare("UPDATE tasks SET status='failed', error=?, finished_at=datetime('now') WHERE id=?")
      .run(e.message, next.id);
    log(AGENT, `Task #${next.id} (${next.agent}) FAILED: ${e.message}`);
  }
}

async function tick() {
  if (running) return;          // keine überlappenden Läufe
  running = true;
  try {
    await processQueue();
    const now = Date.now();
    for (const job of SCHEDULE) {
      if (!job.nextAt) job.nextAt = now + Math.min(job.every, 5_000); // Erststart kurz nach Boot
      if (now >= job.nextAt) {
        job.nextAt = now + job.every;
        try {
          await job.fn();
        } catch (e) {
          log(AGENT, `Geplanter Lauf ${job.name} FAILED: ${e.message}`);
        }
      }
    }
  } finally {
    running = false;
  }
}

log(AGENT, `Start — Intake: ${INTAKE_DIR}`);
log(AGENT, `Zeitplan: ${SCHEDULE.map(j => `${j.name}=${j.every / 60000}min`).join(', ')}`);
const timer = setInterval(tick, 5_000);
tick();

for (const sig of ['SIGINT', 'SIGTERM']) {
  process.on(sig, () => {
    clearInterval(timer);
    log(AGENT, `Stop (${sig})`);
    db.close();
    process.exit(0);
  });
}
