import crypto from 'node:crypto';
import { XMLParser } from 'fast-xml-parser';
import db from '../core/db.js';
import { log, recordRun, claudeJson } from '../core/util.js';

const AGENT = 'sys08-broker';

// Relevanz-Keywords für DACH / AI-Act / Lead-Signale
const KEYWORDS = [
  'ai act', 'ki-verordnung', 'ki verordnung', 'eu ai act', 'hochrisiko',
  'gpai', 'general purpose ai', 'bußgeld', 'bussgeld', 'aufsichtsbehörde',
  'bafin', 'datenschutz', 'dsgvo', 'compliance', 'künstliche intelligenz',
  'insolvenz', 'restrukturierung', 'automatisierung', 'llm', 'chatbot',
  'biometri', 'sanktion', 'marktüberwachung', 'konformitätsbewertung'
];

function guidOf(item) {
  const base = textOf(item.guid) || textOf(item.id) || textOf(item.link) || textOf(item.title) || '';
  return crypto.createHash('sha1').update(String(base)).digest('hex');
}

function textOf(v) {
  if (v == null) return null;
  if (typeof v === 'string') return v;
  if (typeof v === 'object') return v['#text'] ?? v['@_href'] ?? null;
  return String(v);
}

export function normalizeItems(xmlObj) {
  // RSS 2.0
  const rssItems = xmlObj?.rss?.channel?.item;
  if (rssItems) return (Array.isArray(rssItems) ? rssItems : [rssItems]).map(i => ({
    guid: guidOf(i),
    title: textOf(i.title) || '(ohne Titel)',
    link: textOf(i.link),
    published: textOf(i.pubDate),
    summary: (textOf(i.description) || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 600)
  }));
  // Atom
  const atomEntries = xmlObj?.feed?.entry;
  if (atomEntries) return (Array.isArray(atomEntries) ? atomEntries : [atomEntries]).map(e => ({
    guid: guidOf(e),
    title: textOf(e.title) || '(ohne Titel)',
    link: Array.isArray(e.link) ? textOf(e.link[0]) : textOf(e.link),
    published: textOf(e.updated) || textOf(e.published),
    summary: (textOf(e.summary) || textOf(e.content) || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 600)
  }));
  return [];
}

function keywordMatches(item) {
  const hay = `${item.title} ${item.summary}`.toLowerCase();
  return KEYWORDS.filter(k => hay.includes(k));
}

async function pullSource(source) {
  const res = await fetch(source.url, {
    headers: { 'user-agent': 'supermegabot-sys08/1.0', accept: 'application/rss+xml, application/atom+xml, application/xml, text/xml' },
    signal: AbortSignal.timeout(20000)
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const xml = await res.text();
  const parser = new XMLParser({ ignoreAttributes: false });
  return normalizeItems(parser.parse(xml));
}

async function classifySignal(sig) {
  const system = `Du bist der Relevanz-Filter eines Intelligence Brokers für einen DACH-Anbieter von AI-Act-Compliance- und Automatisierungs-Dienstleistungen.
Klassifiziere die Meldung in genau eine Kategorie:
"lead" (konkretes Vertriebs-Signal: Unternehmen mit KI-Compliance-Bedarf, Bußgeld-Fall, Insolvenz/Restrukturierung als Zielkunde),
"regulatorisch" (Gesetz/Behörde/Frist, relevant für Compliance-Reports),
"markt" (allgemeine Branchen-/Wettbewerbsinfo),
"irrelevant".
JSON-Schema: {"relevance":"lead|regulatorisch|markt|irrelevant","rationale":"1 Satz auf Deutsch"}`;
  const { json, model } = await claudeJson(system, JSON.stringify({ titel: sig.title, zusammenfassung: sig.summary }), { maxTokens: 300 });
  if (!['lead', 'regulatorisch', 'markt', 'irrelevant'].includes(json.relevance)) {
    throw new Error(`LLM lieferte ungültige Relevanz: ${JSON.stringify(json).slice(0, 200)}`);
  }
  return { relevance: json.relevance, rationale: json.rationale || '', model };
}

export function addSource(url, name = null, type = 'rss') {
  db.prepare('INSERT INTO intel_sources (name, type, url) VALUES (?,?,?) ON CONFLICT(url) DO UPDATE SET enabled=1, name=excluded.name')
    .run(name || new URL(url).hostname, type, url);
  return db.prepare('SELECT * FROM intel_sources WHERE url=?').get(url);
}

export async function run({ classify = true, llmBudget = 15 } = {}) {
  const t0 = Date.now();
  const sources = db.prepare('SELECT * FROM intel_sources WHERE enabled=1').all();
  if (sources.length === 0) {
    log(AGENT, 'Keine Quellen konfiguriert — mit `node cli.js broker:add-source <url>` hinzufügen');
    return { sources: 0, pullErrors: 0, newSignals: 0, classified: 0, pending: 0 };
  }

  const insert = db.prepare(`
    INSERT OR IGNORE INTO intel_signals (source_id, guid, title, link, published, summary, matched_keywords, relevance)
    VALUES (@source_id, @guid, @title, @link, @published, @summary, @matched_keywords, @relevance)
  `);
  const touch = db.prepare("UPDATE intel_sources SET last_pull=datetime('now'), last_error=NULL WHERE id=?");
  const fail = db.prepare("UPDATE intel_sources SET last_error=? WHERE id=?");

  let newSignals = 0, pullErrors = 0;
  for (const src of sources) {
    try {
      const items = await pullSource(src);
      for (const item of items) {
        const kw = keywordMatches(item);
        const r = insert.run({
          source_id: src.id, guid: item.guid, title: item.title, link: item.link,
          published: item.published, summary: item.summary,
          matched_keywords: JSON.stringify(kw),
          relevance: kw.length === 0 ? 'irrelevant' : 'pending'   // ohne Keyword-Treffer kein LLM-Budget verbrennen
        });
        if (r.changes > 0) newSignals++;
      }
      touch.run(src.id);
      log(AGENT, `${src.name}: ${items.length} Items gelesen`);
    } catch (e) {
      pullErrors++;
      fail.run(e.message.slice(0, 300), src.id);
      log(AGENT, `FEHLER ${src.name}: ${e.message}`);
    }
  }

  // Relevanz-Klassifizierung der Keyword-Treffer (Budget-begrenzt)
  let classified = 0, pending = 0;
  if (classify) {
    const todo = db.prepare("SELECT * FROM intel_signals WHERE relevance='pending' ORDER BY id DESC LIMIT ?").all(llmBudget);
    const upd = db.prepare('UPDATE intel_signals SET relevance=?, relevance_method=?, relevance_rationale=? WHERE id=?');
    for (const sig of todo) {
      try {
        const r = await classifySignal(sig);
        upd.run(r.relevance, 'llm', r.rationale, sig.id);
        classified++;
      } catch (e) {
        pending++;
        log(AGENT, `Signal #${sig.id} bleibt pending: ${e.message}`);
        break; // API-Problem -> nicht weiter hämmern
      }
    }
  }

  const summary = `Pull: ${newSignals} neue Signale aus ${sources.length - pullErrors}/${sources.length} Quellen; klassifiziert: ${classified}, offen: ${pending}`;
  log(AGENT, summary);
  recordRun(AGENT, pullErrors === 0, summary, Date.now() - t0);
  return { sources: sources.length, pullErrors, newSignals, classified, pending };
}
