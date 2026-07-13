import db from '../core/db.js';
import { log, recordRun, claudeJson } from '../core/util.js';

const AGENT = 'classification';

// Art. 5 — verbotene Praktiken (eindeutige Treffer => unacceptable, per Regel)
const PROHIBITED_PATTERNS = [
  /social[\s-]?scoring/i, /sozial.?bewertung/i,
  /unterschwellige (beeinflussung|manipulation)/i, /subliminal/i,
  /emotionserkennung.*(arbeitsplatz|schule|bildung)/i,
  /biometrische echtzeit.?fern.?identifi/i, /predictive policing.*(person|individu)/i,
  /ungezieltes auslesen.*gesichts/i
];

// Anhang III — Hochrisiko-Indikatoren (eindeutige Treffer => high, per Regel)
const HIGH_RISK_PATTERNS = [
  /biometri/i, /kritische infrastruktur/i, /(bewerber|recruiting|einstellung|hr.?auswahl)/i,
  /kredit(würdigkeit|scoring|vergabe)/i, /bonität/i,
  /(bildung|prüfung).*(bewertung|zulassung)/i, /strafverfolgung/i, /migration|asyl|grenzkontrolle/i,
  /justiz|gericht/i, /wesentliche (öffentliche |private )?(dienste|leistungen)/i,
  /medizin|diagnos|patient/i, /versicherungs.?(tarif|risiko)/i
];

// Art.-8–17-Pflichten für Hochrisiko-Systeme
export const HIGH_RISK_OBLIGATIONS = [
  'Art. 9 – Risikomanagementsystem einrichten und dokumentieren',
  'Art. 10 – Daten-Governance: Trainings-/Test-Daten auf Qualität und Bias prüfen',
  'Art. 11 – Technische Dokumentation nach Anhang IV erstellen',
  'Art. 12 – Automatische Protokollierung (Logging) sicherstellen',
  'Art. 13 – Transparenz- und Bereitstellungsinformationen für Betreiber',
  'Art. 14 – Menschliche Aufsicht konzipieren und umsetzen',
  'Art. 15 – Genauigkeit, Robustheit, Cybersicherheit nachweisen',
  'Art. 16/17 – Pflichten des Anbieters inkl. Qualitätsmanagementsystem'
];

const LIMITED_OBLIGATIONS = [
  'Art. 50 – Transparenzpflicht: Nutzer müssen erkennen können, dass sie mit KI interagieren bzw. dass Inhalte KI-generiert sind'
];

function ruleClassify(sys) {
  const text = [sys.name, sys.vendor, sys.purpose, sys.data_types, sys.users, sys.deployment]
    .filter(Boolean).join(' | ');
  for (const p of PROHIBITED_PATTERNS) {
    if (p.test(text)) return { risk_level: 'unacceptable', rationale: `Regel-Treffer Art. 5: Muster "${p.source}"` };
  }
  for (const p of HIGH_RISK_PATTERNS) {
    if (p.test(text)) return { risk_level: 'high', rationale: `Regel-Treffer Anhang III: Muster "${p.source}"` };
  }
  return null; // uneindeutig -> LLM
}

async function llmClassify(sys) {
  const system = `Du bist ein Klassifizierungs-Agent für die EU-KI-Verordnung (AI Act).
Klassifiziere das beschriebene KI-System in genau eine der vier Risikostufen:
"unacceptable" (Art. 5, verbotene Praktik), "high" (Anhang III / Art. 6),
"limited" (nur Transparenzpflichten Art. 50), "minimal" (keine besonderen Pflichten).
Sei konservativ: Im Zweifel zwischen zwei Stufen wähle die höhere.
JSON-Schema: {"risk_level":"unacceptable|high|limited|minimal","rationale":"1-3 Sätze auf Deutsch mit Artikel-Bezug"}`;
  const user = JSON.stringify({
    name: sys.name, vendor: sys.vendor, zweck: sys.purpose,
    datenarten: sys.data_types, nutzer: sys.users, einsatz: sys.deployment, gpai: !!sys.is_gpai
  });
  const { json, model } = await claudeJson(system, user);
  if (!['unacceptable', 'high', 'limited', 'minimal'].includes(json.risk_level)) {
    throw new Error(`LLM lieferte ungültige Stufe: ${JSON.stringify(json).slice(0, 200)}`);
  }
  return { risk_level: json.risk_level, rationale: json.rationale || '', model };
}

function obligationsFor(level) {
  if (level === 'unacceptable') return ['Art. 5 – Praktik ist verboten: System darf so nicht betrieben werden'];
  if (level === 'high') return HIGH_RISK_OBLIGATIONS;
  if (level === 'limited') return LIMITED_OBLIGATIONS;
  return [];
}

export async function run({ clientSlug = null, batchSize = 25 } = {}) {
  const t0 = Date.now();
  let rows;
  if (clientSlug) {
    rows = db.prepare(`
      SELECT s.* FROM ai_systems s
      JOIN clients c ON c.id = s.client_id
      LEFT JOIN classifications k ON k.system_id = s.id
      WHERE c.slug = ? AND (k.id IS NULL OR k.risk_level = 'pending')
      LIMIT ?`).all(clientSlug, batchSize);
  } else {
    rows = db.prepare(`
      SELECT s.* FROM ai_systems s
      LEFT JOIN classifications k ON k.system_id = s.id
      WHERE k.id IS NULL OR k.risk_level = 'pending'
      LIMIT ?`).all(batchSize);
  }

  const upsert = db.prepare(`
    INSERT INTO classifications (system_id, risk_level, method, rationale, obligations, model, classified_at)
    VALUES (@system_id, @risk_level, @method, @rationale, @obligations, @model, datetime('now'))
    ON CONFLICT(system_id) DO UPDATE SET
      risk_level=excluded.risk_level, method=excluded.method, rationale=excluded.rationale,
      obligations=excluded.obligations, model=excluded.model, classified_at=excluded.classified_at
  `);
  const markPending = db.prepare(`
    INSERT INTO classifications (system_id, risk_level, method, rationale, classified_at)
    VALUES (?, 'pending', 'llm', ?, datetime('now'))
    ON CONFLICT(system_id) DO UPDATE SET rationale=excluded.rationale, classified_at=excluded.classified_at
  `);

  let byRule = 0, byLlm = 0, pending = 0;
  for (const sys of rows) {
    const ruleHit = ruleClassify(sys);
    if (ruleHit) {
      upsert.run({
        system_id: sys.id, risk_level: ruleHit.risk_level, method: 'rule',
        rationale: ruleHit.rationale, obligations: JSON.stringify(obligationsFor(ruleHit.risk_level)), model: null
      });
      byRule++;
      continue;
    }
    try {
      const r = await llmClassify(sys);
      upsert.run({
        system_id: sys.id, risk_level: r.risk_level, method: 'llm',
        rationale: r.rationale, obligations: JSON.stringify(obligationsFor(r.risk_level)), model: r.model
      });
      byLlm++;
    } catch (e) {
      // Ehrlich offen lassen statt raten
      markPending.run(sys.id, `Offen: ${e.message}`);
      pending++;
      log(AGENT, `System #${sys.id} "${sys.name}" bleibt pending: ${e.message}`);
    }
  }

  const summary = `Klassifiziert: ${byRule} per Regel, ${byLlm} per LLM, ${pending} offen (von ${rows.length})`;
  if (rows.length > 0) { log(AGENT, summary); recordRun(AGENT, pending === 0, summary, Date.now() - t0); }
  return { total: rows.length, byRule, byLlm, pending };
}
