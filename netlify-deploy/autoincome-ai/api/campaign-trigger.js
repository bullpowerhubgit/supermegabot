// Autonomer Klaviyo Kampagnen-Trigger
// Läuft via Vercel Cron: Mo + Do 08:00 UTC
// Auch manuell: GET /api/campaign-trigger?secret=bullpower2026

const KLAVIYO_KEY = process.env.KLAVIYO_API_KEY;
const TELEGRAM_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT = process.env.TELEGRAM_CHAT_ID;
const LIST_ID = 'Xwxq6V';
const CRON_SECRET = process.env.CRON_SECRET || 'bullpower2026';

const CAMPAIGNS = [
  {
    name: 'KI-Einkommenssystem — Wochenbeginn',
    subject: '🚀 Diese Woche startest du durch — KI-Einkommen 2026',
    preview: 'Ein System. Vollautomatisch. Ab €37.',
    html: `<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
<h2 style="color:#FF6B00;">Diese Woche wird anders 🚀</h2>
<p>Was wäre wenn du ab heute anfängst, passiv Geld zu verdienen?</p>
<p>Das AI Income Machine 90-Day Blueprint gibt dir genau das:</p>
<ul>
<li>✅ KI-Tools die wirklich Geld bringen</li>
<li>✅ Schritt-für-Schritt auf Deutsch erklärt</li>
<li>✅ In 90 Tagen zum ersten passiven Einkommen</li>
<li>✅ Einmalig €37 — kein Abo, kein Risiko</li>
</ul>
<p style="text-align:center;margin:30px 0;">
<a href="https://www.checkout-ds24.com/product/668035" style="background:#FF6B00;color:white;padding:16px 40px;text-decoration:none;border-radius:8px;font-size:1.1rem;font-weight:700;">
Jetzt für €37 starten →
</a>
</p>
<p>Rudolf Sarkany<br>AiiteC KI-Automation</p>
</body></html>`,
    text: 'KI-Einkommen starten: AI Income Machine für €37. https://www.checkout-ds24.com/product/668035',
  },
  {
    name: 'Wochenabschluss — KI-Tipp',
    subject: '💡 KI-Tipp der Woche: So verdienst du mit ChatGPT',
    preview: 'Tipp #1: Prompts vermieten. Tipp #2: Automatisch skalieren.',
    html: `<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
<h2>💡 KI-Tipp der Woche</h2>
<p><strong>Tipp #1: ChatGPT-Prompts verkaufen</strong><br>
Gut formulierte Prompts werden auf Etsy und DS24 verkauft. Einmalig erstellen, immer wieder verkaufen.</p>
<p><strong>Tipp #2: KI-Texte automatisieren</strong><br>
Mit den richtigen Workflows schreibt deine KI täglich Produktbeschreibungen ohne dein Zutun.</p>
<p><strong>Tipp #3: Das komplette System</strong></p>
<p style="text-align:center;margin:30px 0;">
<a href="https://www.checkout-ds24.com/product/668035" style="background:#1e40af;color:white;padding:16px 40px;text-decoration:none;border-radius:8px;font-size:1.1rem;font-weight:700;">
Komplettes System ansehen →
</a>
</p>
<p>Rudolf</p>
</body></html>`,
    text: 'KI-Tipp: Prompts verkaufen + System: https://www.checkout-ds24.com/product/668035',
  },
  {
    name: 'Social Proof — Zahlen sprechen',
    subject: '📊 3 Käufer, 0 Rückgaben — was du wissen solltest',
    preview: '€111 Revenue. 14-Tage-Garantie. Was macht Käufer #4?',
    html: `<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
<h2>📊 Die Zahlen sprechen für sich</h2>
<p>Fakten zum AI Income Machine 90-Day Blueprint:</p>
<div style="background:#f8f9fa;border-left:4px solid #FF6B00;padding:15px;margin:15px 0;">
<strong>✅ 3 zahlende Kunden</strong> — haben für €37 gekauft<br>
<strong>✅ 0 Rückgaben</strong> — trotz 14-Tage-Garantie<br>
<strong>✅ €111 Gesamt-Revenue</strong> — organisch gewachsen<br>
<strong>✅ Sofortzugang</strong> — direkt nach Zahlung
</div>
<p style="text-align:center;margin:30px 0;">
<a href="https://www.checkout-ds24.com/product/668035" style="background:#10b981;color:white;padding:16px 40px;text-decoration:none;border-radius:8px;font-size:1.1rem;font-weight:700;">
Käufer #4 werden — €37
</a>
</p>
<p>Rudolf Sarkany<br>AiiteC</p>
</body></html>`,
    text: '3 Käufer, 0 Rückgaben. AI Income Machine für €37: https://www.checkout-ds24.com/product/668035',
  },
  {
    name: 'Affiliate Recruitment Reminder',
    subject: '💰 40% Provision: Wirst du unser Affiliate?',
    preview: '€14.80 pro Verkauf. Fertige Marketing-Materialien.',
    html: `<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
<h2>💰 Verdiene 40% Provision</h2>
<p>Als Affiliate des AI Income Machine Blueprints verdienst du:</p>
<ul>
<li>40% Provision = €14.80 pro Sale</li>
<li>Fertige Marketing-Templates inklusive</li>
<li>Sofortige Auszahlung über Digistore24</li>
<li>Keine Vorabkosten, kein Risiko</li>
</ul>
<p style="text-align:center;margin:30px 0;">
<a href="https://www.digistore24.com/product/668035" style="background:#FF6B00;color:white;padding:16px 40px;text-decoration:none;border-radius:8px;font-size:1.1rem;font-weight:700;">
Kostenlos als Affiliate anmelden →
</a>
</p>
<p>Rudolf Sarkany</p>
</body></html>`,
    text: '40% Provision als Affiliate: https://www.digistore24.com/product/668035',
  },
];

async function sendTelegram(msg) {
  if (!TELEGRAM_TOKEN || !TELEGRAM_CHAT) return;
  try {
    await fetch(`https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ chat_id: TELEGRAM_CHAT, text: msg, parse_mode: 'HTML' }),
    });
  } catch {}
}

async function klaviyoRequest(method, path, body) {
  const r = await fetch(`https://a.klaviyo.com${path}`, {
    method,
    headers: {
      Authorization: `Klaviyo-API-Key ${KLAVIYO_KEY}`,
      revision: '2024-10-15',
      'content-type': 'application/json',
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  return { status: r.status, data: await r.json().catch(() => ({})) };
}

async function createAndSendCampaign(camp) {
  // 1. Create template
  const t = await klaviyoRequest('POST', '/api/templates/', {
    data: {
      type: 'template',
      attributes: {
        name: `AutoCron-${camp.name.slice(0, 40)}-${Date.now()}`,
        editor_type: 'CODE',
        html: camp.html,
        text: camp.text,
      },
    },
  });
  if (t.status !== 201) throw new Error(`Template failed: ${t.status}`);
  const tmplId = t.data.data.id;

  await new Promise((r) => setTimeout(r, 1000));

  // 2. Create campaign
  const c = await klaviyoRequest('POST', '/api/campaigns/', {
    data: {
      type: 'campaign',
      attributes: {
        name: `${camp.name} [${new Date().toISOString().slice(0, 10)}]`,
        audiences: { included: [LIST_ID], excluded: [] },
        send_strategy: { method: 'immediate' },
        'campaign-messages': {
          data: [
            {
              type: 'campaign-message',
              attributes: {
                channel: 'email',
                label: camp.name,
                content: {
                  subject: camp.subject,
                  preview_text: camp.preview,
                  from_email: 'newsletter@aiitec.de',
                  from_label: 'AiiteC KI-Automation',
                  reply_to_email: 'support@aiitec.de',
                },
              },
            },
          ],
        },
      },
    },
  });
  if (![200, 201].includes(c.status)) throw new Error(`Campaign failed: ${c.status}`);
  const campId = c.data.data.id;

  await new Promise((r) => setTimeout(r, 1000));

  // 3. Get message ID
  const msgs = await klaviyoRequest('GET', `/api/campaigns/${campId}/campaign-messages/`);
  const msgId = msgs.data.data?.[0]?.id;
  if (!msgId) throw new Error('No message ID');

  // 4. Assign template
  const a = await klaviyoRequest('POST', '/api/campaign-message-assign-template/', {
    data: {
      type: 'campaign-message',
      id: msgId,
      relationships: { template: { data: { type: 'template', id: tmplId } } },
    },
  });
  if (![200, 201, 202].includes(a.status)) throw new Error(`Assign failed: ${a.status}`);

  await new Promise((r) => setTimeout(r, 1000));

  // 5. Send
  const s = await klaviyoRequest('POST', '/api/campaign-send-jobs/', {
    data: { type: 'campaign-send-job', attributes: { id: campId } },
  });
  if (![200, 201, 202].includes(s.status)) throw new Error(`Send failed: ${s.status}`);

  return campId;
}

export default async function handler(req, res) {
  const secret = req.headers['x-cron-secret'] || req.query?.secret;
  if (secret !== CRON_SECRET) {
    return res.status(401).json({ error: 'Unauthorized' });
  }

  const idx = Math.floor(Date.now() / (1000 * 60 * 60 * 24 * 3)) % CAMPAIGNS.length;
  const camp = CAMPAIGNS[idx];
  const date = new Date().toISOString().replace('T', ' ').slice(0, 16) + ' UTC';

  try {
    const campId = await createAndSendCampaign(camp);
    await sendTelegram(
      `✅ <b>Auto-Kampagne gesendet</b> [${date}]\n\n📧 <b>${camp.name}</b>\nBetreff: ${camp.subject}\nAn: Liste Xwxq6V\nCampaign ID: ${campId}`
    );
    return res.json({ ok: true, campaign: camp.name, id: campId });
  } catch (err) {
    await sendTelegram(`⚠️ Auto-Kampagne FEHLER [${date}]: ${err.message}`);
    return res.status(500).json({ ok: false, error: err.message });
  }
}
