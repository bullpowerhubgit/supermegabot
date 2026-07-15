import { readFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dir = dirname(fileURLToPath(import.meta.url));
try {
  const lines = readFileSync(resolve(__dir, '../.env'), 'utf8').split('\n');
  for (const l of lines) {
    const m = l.match(/^([A-Z_][A-Z0-9_]*)=(.*)$/);
    if (m && !process.env[m[1]]) process.env[m[1]] = m[2].replace(/^["']|["']$/g, '');
  }
} catch {}

import { App } from '@slack/bolt';

const SLACK_BOT_TOKEN = process.env.SLACK_BOT_TOKEN || '';
const SLACK_APP_TOKEN = process.env.SLACK_APP_TOKEN || '';

const SB_KEY = process.env.SUPABASE_SERVICE_KEY || '';
const SB_URL = process.env.SUPABASE_URL || 'https://qyrjeckzacjaazkpvnjk.supabase.co';
const SB_HEADERS = {
  apikey: SB_KEY,
  Authorization: `Bearer ${SB_KEY}`,
  'Accept-Profile': 'public',
};

const TG_TOKEN = process.env.TELEGRAM_BOT_TOKEN || '';
const TG_CHAT  = process.env.TELEGRAM_CHAT_ID   || '';

async function sbGet(path) {
  const r = await fetch(`${SB_URL}/rest/v1/${path}`, { headers: SB_HEADERS });
  return r.json();
}

async function tgSend(text) {
  try {
    await fetch(`https://api.telegram.org/bot${TG_TOKEN}/sendMessage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: TG_CHAT, text, parse_mode: 'HTML' }),
    });
  } catch {}
}

if (!SLACK_BOT_TOKEN) {
  console.log('⚠️  SLACK_BOT_TOKEN (xoxb-) fehlt — Slack-Bot inaktiv, Telegram läuft als Fallback');
  console.log('   Holen von: api.slack.com/apps → deine App → OAuth & Permissions → Bot User OAuth Token');
  await tgSend('⚠️ Slack Bot: SLACK_BOT_TOKEN fehlt. Bitte in Railway ENV setzen.');
  process.exit(0);
}

const app = new App({
  token: SLACK_BOT_TOKEN,
  appToken: SLACK_APP_TOKEN,
  socketMode: true,
  logLevel: 'warn',
});

// ── /status — Live-Status aller Services ─────────────────────────────────────
app.command('/status', async ({ ack, respond }) => {
  await ack();
  const services = [
    { name: 'icomeauto',        url: 'https://icomeauto-production.up.railway.app/health' },
    { name: 'shopify-engine',   url: 'https://shopify-acquisition-engine-production.up.railway.app/health' },
    { name: 'digistore24',      url: 'https://digistore24-automation-production.up.railway.app/api/health' },
    { name: 'supermegabot',     url: 'https://supermegabot-production.up.railway.app/health' },
  ];
  const results = await Promise.allSettled(
    services.map(async s => {
      const r = await fetch(s.url, { signal: AbortSignal.timeout(5000) });
      const d = await r.json();
      return `${d.status === 'ok' ? '✅' : '⚠️'} *${s.name}*`;
    })
  );
  const lines = results.map((r, i) =>
    r.status === 'fulfilled' ? r.value : `❌ *${services[i].name}*: offline`
  );
  await respond({ text: `*System Status:*\n${lines.join('\n')}`, response_type: 'in_channel' });
});

// ── /revenue — Letzte Einnahmen aus Hermes ────────────────────────────────────
app.command('/revenue', async ({ ack, respond }) => {
  await ack();
  try {
    const events = await sbGet(
      'hermes_events?event_type=eq.new_subscription&order=created_at.desc&limit=10'
    );
    if (!Array.isArray(events) || !events.length) {
      return await respond({ text: 'Noch keine Subscription-Events in hermes_events.' });
    }
    const lines = events.map(e =>
      `💰 ${e.message} — ${new Date(e.created_at).toLocaleString('de')}`
    );
    await respond({ text: `*Letzte Einnahmen:*\n${lines.join('\n')}`, response_type: 'in_channel' });
  } catch (e) {
    await respond({ text: `Fehler: ${e.message}` });
  }
});

// ── /leads — Letzte Leads ─────────────────────────────────────────────────────
app.command('/leads', async ({ ack, respond }) => {
  await ack();
  try {
    const leads = await sbGet('leads?order=created_at.desc&limit=5');
    if (!Array.isArray(leads) || !leads.length) {
      return await respond({ text: 'Noch keine Leads.' });
    }
    const lines = leads.map(l =>
      `📧 ${l.email} | ${l.source} | ${new Date(l.created_at).toLocaleString('de')}`
    );
    await respond({ text: `*Letzte Leads:*\n${lines.join('\n')}`, response_type: 'in_channel' });
  } catch (e) {
    await respond({ text: `Fehler: ${e.message}` });
  }
});

// ── /jobs — Hermes Job-Queue Status ──────────────────────────────────────────
app.command('/jobs', async ({ ack, respond }) => {
  await ack();
  try {
    const jobs = await sbGet('hermes_jobs?status=eq.pending&order=created_at.desc&limit=10');
    if (!Array.isArray(jobs) || !jobs.length) {
      return await respond({ text: 'Keine ausstehenden Jobs in der Queue.' });
    }
    const lines = jobs.map(j =>
      `⚙️ [${j.service}] ${j.job_name} (prio: ${j.priority}) — ${new Date(j.created_at).toLocaleString('de')}`
    );
    await respond({ text: `*Pending Jobs:*\n${lines.join('\n')}`, response_type: 'in_channel' });
  } catch (e) {
    await respond({ text: `Fehler: ${e.message}` });
  }
});

// ── Mention — antworte auf @supermegabot ─────────────────────────────────────
app.event('app_mention', async ({ event, say }) => {
  const text = (event.text || '').toLowerCase();
  if (text.includes('status')) {
    await say('Nutze `/status` für den System-Status.');
  } else if (text.includes('revenue') || text.includes('umsatz')) {
    await say('Nutze `/revenue` für die letzten Einnahmen.');
  } else if (text.includes('lead')) {
    await say('Nutze `/leads` für die letzten Leads.');
  } else {
    await say(
      'Commands: `/status` · `/revenue` · `/leads` · `/jobs`\n' +
      'Alle Daten live aus Supabase + Railway.'
    );
  }
});

// ── Startup ───────────────────────────────────────────────────────────────────
(async () => {
  await app.start();
  console.log('✅ Slack Bot läuft (Socket Mode)');
  console.log('   Workspace: marketing-m9r3843.slack.com');
  console.log('   Commands: /status /revenue /leads /jobs');
  await tgSend('✅ <b>Slack Bot gestartet</b>\nWorkspace: marketing-m9r3843.slack.com\nCommands: /status /revenue /leads /jobs');
})();
