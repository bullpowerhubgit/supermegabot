// Klaviyo: Email-Sequenz (täglich 10:00 UTC) + Webhook-Handler (Sofort-Welcome bei Subscriber)
// Cron: 4-stufige Sequenz: Tag 0 Welcome | Tag 2 Follow-up | Tag 5 Urgency | Tag 10 Affiliate
// Webhook: POST ohne CRON_SECRET → Sofort-Welcome für neuen Subscriber

const KLAVIYO_KEY = process.env.KLAVIYO_API_KEY;
const TELEGRAM_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT = process.env.TELEGRAM_CHAT_ID;
const LIST_ID = 'Xwxq6V';
const CRON_SECRET = process.env.CRON_SECRET || 'bullpower2026';
const PRODUCT_URL = 'https://www.checkout-ds24.com/product/668035';
const UPSELL_URL = 'https://www.checkout-ds24.com/product/704677';

const WELCOME_EMAIL = {
  subject: '👋 Willkommen — hier ist dein kostenloser KI-Einkommens-Leitfaden',
  preview: 'Schön dass du da bist. Dieser Guide startet dich sofort.',
  html: `<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;background:#ffffff;">
<div style="text-align:center;padding:20px 0;">
  <h1 style="color:#7c3aed;font-size:1.8rem;">Willkommen bei AiiteC! 🎉</h1>
  <p style="color:#64748b;font-size:1rem;">Du hast den ersten richtigen Schritt gemacht.</p>
</div>

<div style="background:#f8f9fa;border-radius:12px;padding:24px;margin:20px 0;">
  <h2 style="color:#1e293b;font-size:1.3rem;margin-bottom:16px;">Was du jetzt bekommst:</h2>
  <p style="color:#475569;line-height:1.8;">
    ✅ <strong>KI-Einkommens Checkliste</strong> — 21 Schritte zum ersten passiven Einkommen<br>
    ✅ <strong>Wöchentliche KI-Tipps</strong> — was wirklich funktioniert, was nicht<br>
    ✅ <strong>Exklusive Angebote</strong> — nur für E-Mail-Subscriber<br>
  </p>
</div>

<div style="background:linear-gradient(135deg,#7c3aed,#5b21b6);border-radius:12px;padding:28px;margin:20px 0;text-align:center;color:white;">
  <p style="font-size:1rem;margin-bottom:8px;opacity:0.9;">Bereit für den nächsten Schritt?</p>
  <h2 style="font-size:1.5rem;margin-bottom:12px;">AI Income Machine Blueprint</h2>
  <p style="opacity:0.85;margin-bottom:8px;">90-Day Plan · Auf Deutsch · Vollautomatisch</p>
  <div style="font-size:2rem;font-weight:900;margin:16px 0;">€37 <span style="font-size:1rem;opacity:0.6;text-decoration:line-through;">€97</span></div>
  <a href="${PRODUCT_URL}" style="display:inline-block;background:white;color:#7c3aed;padding:14px 36px;border-radius:50px;font-size:1rem;font-weight:700;text-decoration:none;">
    Jetzt starten →
  </a>
  <p style="font-size:0.8rem;margin-top:12px;opacity:0.7;">60-Tage Geld-zurück-Garantie · Einmalzahlung · Kein Abo</p>
</div>

<div style="border-top:1px solid #e2e8f0;padding-top:20px;margin-top:20px;">
  <h3 style="color:#1e293b;margin-bottom:12px;">Was andere über uns sagen:</h3>
  <div style="background:#f8f9fa;border-left:4px solid #7c3aed;padding:16px;border-radius:4px;margin-bottom:12px;">
    <p style="color:#475569;font-style:italic;">"Das System hat mir geholfen meinen ersten digitalen Produktverkauf zu erzielen — in Woche 3 des Blueprints."</p>
    <p style="color:#7c3aed;font-size:0.85rem;margin-top:8px;font-weight:600;">— Kunde, München</p>
  </div>
</div>

<div style="text-align:center;padding:20px 0;color:#64748b;font-size:0.85rem;">
  <p>AiiteC KI-Automation · Rudolf Sarkany</p>
  <p style="margin-top:8px;">
    <a href="https://autoincome-ai.vercel.app/blog" style="color:#7c3aed;">Blog lesen</a> &nbsp;·&nbsp;
    <a href="https://autoincome-ai.vercel.app/affiliate.html" style="color:#7c3aed;">Affiliate werden</a>
  </p>
</div>
</body></html>`,
  text: `Willkommen bei AiiteC! Dein AI Income Machine Blueprint für €37: ${PRODUCT_URL}`,
};

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
    signal: AbortSignal.timeout(10000),
  });
  return { status: r.status, data: await r.json().catch(() => ({})) };
}

async function getSubscribersByAge(daysAgo) {
  const from = new Date(Date.now() - (daysAgo + 0.6) * 24 * 60 * 60 * 1000).toISOString();
  const to   = new Date(Date.now() - (daysAgo - 0.6) * 24 * 60 * 60 * 1000).toISOString();
  const r = await klaviyoRequest('GET',
    `/api/lists/${LIST_ID}/profiles/?filter=greater-than(joined_group_at,${from}),less-than(joined_group_at,${to})&page[size]=100`
  );
  if (r.status !== 200) return [];
  return r.data.data || [];
}

// Day 0 — welcome
async function getNewSubscribers() {
  return getSubscribersByAge(0.5); // joined in last ~12-36h
}

async function sendWelcomeCampaign(newCount) {
  const date = new Date().toISOString().slice(0, 10);

  const t = await klaviyoRequest('POST', '/api/templates/', {
    data: {
      type: 'template',
      attributes: {
        name: `Welcome-${date}-${Date.now()}`,
        editor_type: 'CODE',
        html: WELCOME_EMAIL.html,
        text: WELCOME_EMAIL.text,
      },
    },
  });
  if (t.status !== 201) throw new Error(`Template ${t.status}`);
  const tmplId = t.data.data.id;

  await new Promise((r) => setTimeout(r, 1000));

  const c = await klaviyoRequest('POST', '/api/campaigns/', {
    data: {
      type: 'campaign',
      attributes: {
        name: `Welcome Auto [${date}] — ${newCount} neue Subscriber`,
        audiences: { included: [LIST_ID], excluded: [] },
        send_strategy: { method: 'immediate' },
        'campaign-messages': {
          data: [{
            type: 'campaign-message',
            attributes: {
              channel: 'email',
              label: 'Welcome Email',
              content: {
                subject: WELCOME_EMAIL.subject,
                preview_text: WELCOME_EMAIL.preview,
                from_email: 'newsletter@aiitec.de',
                from_label: 'Rudolf — AiiteC',
                reply_to_email: 'support@aiitec.de',
              },
            },
          }],
        },
      },
    },
  });
  if (![200, 201].includes(c.status)) throw new Error(`Campaign ${c.status}`);
  const campId = c.data.data.id;

  await new Promise((r) => setTimeout(r, 1000));

  const msgs = await klaviyoRequest('GET', `/api/campaigns/${campId}/campaign-messages/`);
  const msgId = msgs.data.data?.[0]?.id;
  if (!msgId) throw new Error('No message ID');

  await klaviyoRequest('POST', '/api/campaign-message-assign-template/', {
    data: { type: 'campaign-message', id: msgId, relationships: { template: { data: { type: 'template', id: tmplId } } } },
  });

  await new Promise((r) => setTimeout(r, 1000));

  await klaviyoRequest('POST', '/api/campaign-send-jobs/', {
    data: { type: 'campaign-send-job', attributes: { id: campId } },
  });

  return campId;
}

const FOLLOWUP_EMAILS = {
  day2: {
    subject: '📊 Tag 2 — erste Ergebnisse schon möglich?',
    preview: 'Was andere in Woche 1 erreicht haben.',
    html: `<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
<h2 style="color:#7c3aed;">Hast du schon angefangen? 🚀</h2>
<p style="color:#475569;">Vor 2 Tagen hast du dich angemeldet. Hier ist was viele in Woche 1 schon umsetzen:</p>
<div style="background:#f8f9fa;border-radius:12px;padding:20px;margin:20px 0;">
  <p style="color:#1e293b;font-weight:600;">✅ Was in Woche 1 funktioniert:</p>
  <p style="color:#475569;">→ Digistore24-Account erstellen (kostenlos, 15 Min)<br>
  → Erstes digitales Produkt auflisten<br>
  → LinkedIn-Profil für passives Einkommen optimieren<br>
  → Erste Email-Liste aufbauen</p>
</div>
<p style="color:#475569;">Das AI Income Machine Blueprint zeigt dir Schritt für Schritt wie — auf Deutsch, mit konkreten Vorlagen.</p>
<div style="text-align:center;margin:24px 0;">
  <a href="${PRODUCT_URL}" style="background:linear-gradient(135deg,#7c3aed,#5b21b6);color:white;padding:14px 32px;border-radius:50px;font-weight:700;text-decoration:none;display:inline-block;">Blueprint für €37 →</a>
</div>
<p style="color:#94a3b8;font-size:0.85rem;">60-Tage Geld-zurück-Garantie · Rudolf — AiiteC</p>
</body></html>`,
    text: `Tag 2 Follow-up: Blueprint für €37 → ${PRODUCT_URL}`,
  },
  day5: {
    subject: '⏰ Noch 25 Plätze — oder gleich das VOLLE System',
    preview: 'Zwei Optionen: Blueprint €37 oder das komplette KI-Automation System €97.',
    html: `<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
<h2 style="color:#7c3aed;">Warum gerade JETZT der richtige Zeitpunkt ist</h2>
<p style="color:#475569;">Du bist seit 5 Tagen dabei. Hier ist ein ehrlicher Einblick:</p>
<div style="background:linear-gradient(135deg,#7c3aed,#5b21b6);border-radius:12px;padding:24px;color:white;margin:20px 0;">
  <p style="font-size:1.1rem;font-weight:600;">Der deutschsprachige Markt 2026:</p>
  <p>🇩🇪 85% weniger Konkurrenz als auf Englisch<br>
  💶 Höhere Kaufkraft (Ø €37-97 Digital-Produkt)<br>
  📈 KI-Themen explodieren gerade auf LinkedIn DE<br>
  🏆 Erste Mover haben massive Vorteile</p>
</div>
<p style="color:#475569;">Mein System hat in 4 Monaten €111 generiert — vollautomatisch, ohne Ads, ohne Follow-ups per Hand.</p>
<table width="100%" cellpadding="0" cellspacing="12" style="margin:24px 0;">
  <tr>
    <td width="48%" style="background:#f8f9fa;border:2px solid #e2e8f0;border-radius:12px;padding:20px;text-align:center;vertical-align:top;">
      <p style="color:#7c3aed;font-weight:700;font-size:1rem;margin:0 0 8px;">Blueprint</p>
      <p style="font-size:1.8rem;font-weight:900;color:#1e293b;margin:8px 0;">€37</p>
      <p style="color:#475569;font-size:0.85rem;margin:8px 0;">90-Day Plan · PDF + Checklisten</p>
      <a href="${PRODUCT_URL}" style="display:inline-block;background:#7c3aed;color:white;padding:10px 20px;border-radius:25px;font-weight:700;text-decoration:none;font-size:0.9rem;margin-top:12px;">Kaufen →</a>
    </td>
    <td width="48%" style="background:linear-gradient(135deg,#1e293b,#0f172a);border:2px solid #7c3aed;border-radius:12px;padding:20px;text-align:center;vertical-align:top;">
      <p style="color:#a78bfa;font-weight:700;font-size:1rem;margin:0 0 4px;">⭐ SuperMegaBot</p>
      <p style="color:#64748b;font-size:0.75rem;margin:0 0 8px;text-decoration:line-through;">€297</p>
      <p style="font-size:1.8rem;font-weight:900;color:white;margin:4px 0;">€97</p>
      <p style="color:#94a3b8;font-size:0.82rem;margin:8px 0;">KI-Automation System · Code + Deploy</p>
      <a href="${UPSELL_URL}" style="display:inline-block;background:linear-gradient(135deg,#7c3aed,#5b21b6);color:white;padding:10px 20px;border-radius:25px;font-weight:700;text-decoration:none;font-size:0.9rem;margin-top:12px;">Vollsystem →</a>
    </td>
  </tr>
</table>
<p style="color:#94a3b8;font-size:0.85rem;text-align:center;">60-Tage Geld-zurück-Garantie · Einmalzahlung · Rudolf — AiiteC</p>
</body></html>`,
    text: `Tag 5: Blueprint €37 → ${PRODUCT_URL} | SuperMegaBot Vollsystem €97 → ${UPSELL_URL}`,
  },
  day10: {
    subject: '🚀 Letzte Chance — 3 Wege zu passivem Einkommen',
    preview: 'Blueprint €37, Vollsystem €97, oder 50% Affiliate-Provision.',
    html: `<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
<h2 style="color:#7c3aed;">10 Tage sind vergangen — hier sind deine 3 Optionen</h2>
<p style="color:#475569;">Du bist seit 10 Tagen in meiner Liste. Diese E-Mail ist die letzte meiner Sequenz. Danke für dein Vertrauen.</p>

<div style="background:#fefce8;border:1px solid #fbbf24;border-radius:12px;padding:20px;margin:16px 0;">
  <p style="color:#92400e;font-weight:700;">Option A — Starter: Blueprint €37</p>
  <p style="color:#78350f;font-size:0.9rem;">90-Day Plan · Checklisten · Vorlagen · Auf Deutsch<br>Für: Einsteiger die systematisch starten wollen</p>
  <a href="${PRODUCT_URL}" style="display:inline-block;margin-top:10px;background:#d97706;color:white;padding:10px 24px;border-radius:25px;font-weight:700;text-decoration:none;font-size:0.9rem;">Blueprint kaufen →</a>
</div>

<div style="background:linear-gradient(135deg,#1e293b,#0f172a);border:2px solid #7c3aed;border-radius:12px;padding:20px;margin:16px 0;">
  <p style="color:#a78bfa;font-weight:700;">⭐ Option B — Vollsystem: SuperMegaBot €97</p>
  <p style="color:#94a3b8;font-size:0.9rem;">Komplettes KI-Automation System · Code + Deploy<br>LinkedIn-Bot · Email-Automation · Shopify-Integration<br>Für: Wer das komplette automatische Setup will</p>
  <a href="${UPSELL_URL}" style="display:inline-block;margin-top:10px;background:linear-gradient(135deg,#7c3aed,#5b21b6);color:white;padding:10px 24px;border-radius:25px;font-weight:700;text-decoration:none;font-size:0.9rem;">Vollsystem kaufen →</a>
</div>

<div style="background:#f0fdf4;border:1px solid #86efac;border-radius:12px;padding:20px;margin:16px 0;">
  <p style="color:#166534;font-weight:700;">💰 Option C — Affiliate: 50% Provision kostenlos</p>
  <p style="color:#166534;font-size:0.9rem;">Pro Verkauf: €18,50 (Blueprint) oder €48,50 (Vollsystem)<br>Digistore24 zahlt wöchentlich aus · Keine Website nötig</p>
  <a href="https://autoincome-ai.vercel.app/affiliate.html" style="display:inline-block;margin-top:10px;background:#059669;color:white;padding:10px 24px;border-radius:25px;font-weight:700;text-decoration:none;font-size:0.9rem;">Jetzt Affiliate werden →</a>
</div>

<p style="color:#94a3b8;font-size:0.82rem;text-align:center;margin-top:20px;">60-Tage Geld-zurück-Garantie · Rudolf Sarkany — AiiteC</p>
</body></html>`,
    text: `Tag 10: Blueprint €37 → ${PRODUCT_URL} | Vollsystem €97 → ${UPSELL_URL} | Affiliate 50% → https://autoincome-ai.vercel.app/affiliate.html`,
  },
};

async function sendFollowupCampaign(emailDef, subCount, tag) {
  const date = new Date().toISOString().slice(0, 10);
  const t = await klaviyoRequest('POST', '/api/templates/', {
    data: { type: 'template', attributes: { name: `Followup-${tag}-${date}`, editor_type: 'CODE', html: emailDef.html, text: emailDef.text } },
  });
  if (t.status !== 201) throw new Error(`Template ${t.status}: ${JSON.stringify(t.data)}`);
  const tmplId = t.data.data.id;
  await new Promise(r => setTimeout(r, 1000));
  const c = await klaviyoRequest('POST', '/api/campaigns/', {
    data: { type: 'campaign', attributes: {
      name: `Followup-${tag} [${date}] ${subCount} subs`,
      audiences: { included: [LIST_ID], excluded: [] },
      send_strategy: { method: 'immediate' },
      'campaign-messages': { data: [{ type: 'campaign-message', attributes: {
        channel: 'email', label: `Followup ${tag}`,
        content: { subject: emailDef.subject, preview_text: emailDef.preview, from_email: 'newsletter@aiitec.de', from_label: 'Rudolf — AiiteC', reply_to_email: 'support@aiitec.de' },
      }}]},
    }},
  });
  if (![200,201].includes(c.status)) throw new Error(`Campaign ${c.status}`);
  const campId = c.data.data.id;
  await new Promise(r => setTimeout(r, 1000));
  const msgs = await klaviyoRequest('GET', `/api/campaigns/${campId}/campaign-messages/`);
  const msgId = msgs.data.data?.[0]?.id;
  if (!msgId) throw new Error('No message ID');
  await klaviyoRequest('POST', '/api/campaign-message-assign-template/', {
    data: { type: 'campaign-message', id: msgId, relationships: { template: { data: { type: 'template', id: tmplId } } } },
  });
  await new Promise(r => setTimeout(r, 1000));
  await klaviyoRequest('POST', '/api/campaign-send-jobs/', { data: { type: 'campaign-send-job', attributes: { id: campId } } });
  return campId;
}

async function handleWebhook(req, res) {
  let body;
  try { body = typeof req.body === 'string' ? JSON.parse(req.body) : req.body; } catch { return res.status(400).json({ error: 'Invalid JSON' }); }
  const email = body?.data?.attributes?.profile?.email || body?.data?.attributes?.email || body?.customer_properties?.['$email'] || body?.profile?.email || body?.email;
  const firstName = body?.data?.attributes?.profile?.first_name || body?.customer_properties?.['$first_name'] || body?.profile?.first_name || 'du';
  if (!email) return res.status(200).json({ ok: true, skipped: 'no email' });
  try {
    const campId = await sendWelcomeCampaign(1);
    await sendTelegram(`✅ Sofort-Welcome gesendet!\n📧 ${email} (${firstName})\nCampaign: ${campId}`);
    return res.status(200).json({ ok: true, email, campId });
  } catch (err) {
    await sendTelegram(`❌ Welcome-Webhook Fehler für ${email}: ${err.message.substring(0, 150)}`);
    return res.status(200).json({ ok: false, error: err.message });
  }
}

export default async function handler(req, res) {
  const secret = req.headers['x-cron-secret'] || req.query?.secret;
  // Webhook-Mode: POST ohne CRON_SECRET = incoming Klaviyo event
  if (req.method === 'POST' && secret !== CRON_SECRET) return handleWebhook(req, res);
  if (secret !== CRON_SECRET) return res.status(401).json({ error: 'unauthorized' });
  if (!KLAVIYO_KEY) return res.status(200).json({ ok: true, note: 'no klaviyo key' });

  const results = [];

  try {
    // Day 0 — welcome email
    const newSubs = await getNewSubscribers();
    if (newSubs.length > 0) {
      const campId = await sendWelcomeCampaign(newSubs.length);
      results.push({ tag: 'day0', count: newSubs.length, campId });
      await sendTelegram(`📧 <b>Welcome-Email</b>: ${newSubs.length} neue Subscriber → Kampagne ${campId}`);
    }

    // Day 2 follow-up
    const day2subs = await getSubscribersByAge(2);
    if (day2subs.length > 0) {
      const campId = await sendFollowupCampaign(FOLLOWUP_EMAILS.day2, day2subs.length, 'day2');
      results.push({ tag: 'day2', count: day2subs.length, campId });
      await sendTelegram(`📧 <b>Follow-up Tag 2</b>: ${day2subs.length} Subscriber → ${campId}`);
    }

    // Day 5 follow-up
    const day5subs = await getSubscribersByAge(5);
    if (day5subs.length > 0) {
      const campId = await sendFollowupCampaign(FOLLOWUP_EMAILS.day5, day5subs.length, 'day5');
      results.push({ tag: 'day5', count: day5subs.length, campId });
      await sendTelegram(`📧 <b>Follow-up Tag 5</b>: ${day5subs.length} Subscriber → ${campId}`);
    }

    // Day 10 follow-up
    const day10subs = await getSubscribersByAge(10);
    if (day10subs.length > 0) {
      const campId = await sendFollowupCampaign(FOLLOWUP_EMAILS.day10, day10subs.length, 'day10');
      results.push({ tag: 'day10', count: day10subs.length, campId });
      await sendTelegram(`📧 <b>Follow-up Tag 10</b>: ${day10subs.length} Subscriber → ${campId}`);
    }

    if (results.length === 0) {
      await sendTelegram('ℹ️ Email-Sequenz: Heute keine Subscriber in keiner Stufe.');
    }

    return res.status(200).json({ ok: true, results });
  } catch (err) {
    await sendTelegram(`❌ Email-Sequenz Fehler: ${err.message}`);
    return res.status(500).json({ ok: false, error: err.message });
  }
}
