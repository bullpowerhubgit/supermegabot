import fs from 'node:fs';
import db, { transaction } from '../core/db.js';
import { log, recordRun } from '../core/util.js';

const AGENT = 'inventory';

/**
 * Intake-Format (JSON-Datei):
 * {
 *   "client": { "slug": "...", "name": "...", "contact": "..." },
 *   "systems": [
 *     { "name": "...", "vendor": "...", "purpose": "...",
 *       "data_types": "...", "users": "...", "deployment": "intern|kundengerichtet|eingebettet",
 *       "is_gpai": false }
 *   ]
 * }
 */
export function intakeFile(filePath) {
  const t0 = Date.now();
  const raw = JSON.parse(fs.readFileSync(filePath, 'utf8'));
  if (!raw.client?.slug || !raw.client?.name) throw new Error('Intake: client.slug und client.name sind Pflicht');
  if (!Array.isArray(raw.systems) || raw.systems.length === 0) throw new Error('Intake: systems[] ist leer');

  const upsertClient = db.prepare(`
    INSERT INTO clients (slug, name, contact) VALUES (@slug, @name, @contact)
    ON CONFLICT(slug) DO UPDATE SET name=excluded.name, contact=COALESCE(excluded.contact, clients.contact)
  `);
  upsertClient.run({ slug: raw.client.slug, name: raw.client.name, contact: raw.client.contact ?? null });
  const client = db.prepare('SELECT * FROM clients WHERE slug=?').get(raw.client.slug);

  const upsertSystem = db.prepare(`
    INSERT INTO ai_systems (client_id, name, vendor, purpose, data_types, users, deployment, is_gpai, raw)
    VALUES (@client_id, @name, @vendor, @purpose, @data_types, @users, @deployment, @is_gpai, @raw)
    ON CONFLICT(client_id, name) DO UPDATE SET
      vendor=excluded.vendor, purpose=excluded.purpose, data_types=excluded.data_types,
      users=excluded.users, deployment=excluded.deployment, is_gpai=excluded.is_gpai, raw=excluded.raw
  `);

  let count = 0;
  transaction(() => {
    for (const s of raw.systems) {
      if (!s.name) throw new Error('Intake: jedes System braucht ein name-Feld');
      upsertSystem.run({
        client_id: client.id,
        name: String(s.name),
        vendor: s.vendor ?? null,
        purpose: s.purpose ?? null,
        data_types: s.data_types ?? null,
        users: s.users ?? null,
        deployment: s.deployment ?? null,
        is_gpai: s.is_gpai ? 1 : 0,
        raw: JSON.stringify(s)
      });
      count++;
    }
  });

  const summary = `Intake ${raw.client.slug}: ${count} Systeme übernommen`;
  log(AGENT, summary);
  recordRun(AGENT, true, summary, Date.now() - t0);
  return { client: client.slug, systems: count };
}

/** Periodischer Lauf: nimmt alle *.json aus intake/ auf und verschiebt sie nach intake/done/. */
export async function run({ intakeDir }) {
  const t0 = Date.now();
  fs.mkdirSync(intakeDir, { recursive: true });
  const doneDir = `${intakeDir}/done`;
  fs.mkdirSync(doneDir, { recursive: true });

  const files = fs.readdirSync(intakeDir).filter(f => f.endsWith('.json'));
  let ok = 0, failed = 0;
  for (const f of files) {
    const p = `${intakeDir}/${f}`;
    try {
      intakeFile(p);
      fs.renameSync(p, `${doneDir}/${Date.now()}_${f}`);
      ok++;
    } catch (e) {
      failed++;
      log(AGENT, `FEHLER bei ${f}: ${e.message}`);
    }
  }
  if (files.length > 0) recordRun(AGENT, failed === 0, `Watch-Lauf: ${ok} ok, ${failed} fehlerhaft`, Date.now() - t0);
  return { processed: ok, failed };
}
