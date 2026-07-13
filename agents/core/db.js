import { DatabaseSync } from 'node:sqlite';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const DATA_DIR = path.join(ROOT, 'data');
fs.mkdirSync(DATA_DIR, { recursive: true });

const db = new DatabaseSync(path.join(DATA_DIR, 'agents.db'));
db.exec('PRAGMA journal_mode = WAL;');
db.exec('PRAGMA foreign_keys = ON;');

db.exec(`
CREATE TABLE IF NOT EXISTS clients (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  slug        TEXT UNIQUE NOT NULL,
  name        TEXT NOT NULL,
  contact     TEXT,
  created_at  TEXT DEFAULT (datetime('now'))
);

-- Inventory-Agent: KI-System-Inventar pro Kunde (AI-Act Art. 3 / Bestandsaufnahme)
CREATE TABLE IF NOT EXISTS ai_systems (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  client_id     INTEGER NOT NULL REFERENCES clients(id),
  name          TEXT NOT NULL,
  vendor        TEXT,
  purpose       TEXT,
  data_types    TEXT,
  users         TEXT,
  deployment    TEXT,              -- intern | kundengerichtet | eingebettet
  is_gpai       INTEGER DEFAULT 0,
  raw           TEXT,              -- Original-Intake als JSON
  created_at    TEXT DEFAULT (datetime('now')),
  UNIQUE(client_id, name)
);

-- Classification-Agent: Risikoklassifizierung
CREATE TABLE IF NOT EXISTS classifications (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  system_id     INTEGER UNIQUE NOT NULL REFERENCES ai_systems(id),
  risk_level    TEXT CHECK (risk_level IN ('unacceptable','high','limited','minimal','pending')),
  method        TEXT CHECK (method IN ('rule','llm')),
  rationale     TEXT,
  obligations   TEXT,              -- JSON-Array relevanter Art.-8-17-Pflichten
  model         TEXT,
  classified_at TEXT
);

-- SYS-08 Intelligence Broker
CREATE TABLE IF NOT EXISTS intel_sources (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  name       TEXT NOT NULL,
  type       TEXT NOT NULL DEFAULT 'rss',
  url        TEXT UNIQUE NOT NULL,
  enabled    INTEGER DEFAULT 1,
  last_pull  TEXT,
  last_error TEXT
);

CREATE TABLE IF NOT EXISTS intel_signals (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id   INTEGER NOT NULL REFERENCES intel_sources(id),
  guid        TEXT UNIQUE NOT NULL,
  title       TEXT NOT NULL,
  link        TEXT,
  published   TEXT,
  summary     TEXT,
  matched_keywords TEXT,           -- JSON-Array
  relevance   TEXT CHECK (relevance IN ('lead','regulatorisch','markt','irrelevant','pending')) DEFAULT 'pending',
  relevance_method TEXT,
  relevance_rationale TEXT,
  created_at  TEXT DEFAULT (datetime('now'))
);

-- Orchestrator: Task-Queue + Agenten-Runs
CREATE TABLE IF NOT EXISTS tasks (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  agent      TEXT NOT NULL,
  payload    TEXT,
  status     TEXT DEFAULT 'queued' CHECK (status IN ('queued','running','done','failed')),
  result     TEXT,
  error      TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  started_at TEXT,
  finished_at TEXT
);

CREATE TABLE IF NOT EXISTS agent_runs (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  agent       TEXT NOT NULL,
  ok          INTEGER NOT NULL,
  summary     TEXT,
  duration_ms INTEGER,
  ran_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status, agent);
CREATE INDEX IF NOT EXISTS idx_signals_rel ON intel_signals(relevance);
`);

/** Manuelle Transaktion (node:sqlite hat kein db.transaction()) */
export function transaction(fn) {
  db.exec('BEGIN');
  try {
    const result = fn();
    db.exec('COMMIT');
    return result;
  } catch (e) {
    db.exec('ROLLBACK');
    throw e;
  }
}

export default db;
export { ROOT, DATA_DIR };
