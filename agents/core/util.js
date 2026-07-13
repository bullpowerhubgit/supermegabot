import db from './db.js';

export function log(agent, msg) {
  process.stdout.write(`[${new Date().toISOString()}] [${agent}] ${msg}\n`);
}

export function recordRun(agent, ok, summary, durationMs) {
  db.prepare(
    'INSERT INTO agent_runs (agent, ok, summary, duration_ms) VALUES (?,?,?,?)'
  ).run(agent, ok ? 1 : 0, summary, Math.round(durationMs));
}

/**
 * Claude-API-Call mit erzwungener JSON-Antwort.
 * Wirft einen Fehler, wenn ANTHROPIC_API_KEY fehlt oder die API fehlschlägt —
 * es wird nie ein Fake-Ergebnis zurückgegeben.
 */
export async function claudeJson(systemPrompt, userPrompt, { maxTokens = 1024 } = {}) {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) throw new Error('ANTHROPIC_API_KEY fehlt in .env — LLM-Klassifizierung nicht möglich');

  const model = process.env.CLASSIFIER_MODEL || 'claude-sonnet-4-6';
  const res = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-api-key': apiKey,
      'anthropic-version': '2023-06-01'
    },
    body: JSON.stringify({
      model,
      max_tokens: maxTokens,
      system: systemPrompt + '\nAntworte ausschließlich mit einem einzigen validen JSON-Objekt. Kein Markdown, keine Backticks, kein Text davor oder danach.',
      messages: [{ role: 'user', content: userPrompt }]
    })
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Anthropic API ${res.status}: ${body.slice(0, 300)}`);
  }
  const data = await res.json();
  const text = (data.content || []).filter(b => b.type === 'text').map(b => b.text).join('');
  const clean = text.replace(/```json|```/g, '').trim();
  return { json: JSON.parse(clean), model };
}

/** Telegram-Push an Admin, nur wenn Token + Chat-ID gesetzt sind. */
export async function telegramNotify(text) {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TELEGRAM_ADMIN_CHAT_ID;
  if (!token || !chatId) return false;
  const res = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ chat_id: chatId, text, disable_web_page_preview: true })
  });
  if (!res.ok) throw new Error(`Telegram ${res.status}: ${(await res.text()).slice(0, 200)}`);
  return true;
}
