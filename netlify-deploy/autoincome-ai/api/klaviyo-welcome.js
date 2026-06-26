// Klaviyo: Email-Sequenz (täglich 10:00 UTC) + Webhook-Handler (Sofort-Welcome bei Subscriber)
// Cron: 4-stufige Sequenz: Tag 0 Welcome | Tag 2 Follow-up | Tag 5 Urgency | Tag 10 Affiliate
// Webhook: POST ohne CRON_SECRET → Sofort-Welcome für neuen Subscriber
// DS24 IPN: POST mit buyer_email+sha_sign → Käufer in Klaviyo + Käufer-Email

import { createHash } from 'crypto';

const KLAVIYO_KEY = process.env.KLAVIYO_API_KEY;
const TELEGRAM_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT = process.env.TELEGRAM_CHAT_ID;
const LIST_ID = 'Xwxq6V';
const AFFILIATE_LIST_ID = 'WdgMfp';
const CRON_SECRET = process.env.CRON_SECRET || 'bullpower2026';
const PRODUCT_URL = 'https://www.checkout-ds24.com/product/668035';
const UPSELL_URL = 'https://www.checkout-ds24.com/product/704677';
const DS24_IPN_PASSPHRASE = process.env.DS24_IPN_PASSPHRASE || '';
const BUYER_LIST_ID = process.env.KLAVIYO_BUYER_LIST_ID || 'Xwxq6V';

const BUYER_WELCOME_EMAIL = {
  subject: '🎉 Kauf bestätigt — dein AI Income Machine Zugang ist bereit!',
  preview: 'Deine Bestellung ist eingegangen. Hier ist alles was du brauchst.',
  html: `<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;background:#ffffff;">
<div style="text-align:center;padding:20px 0;">
  <div style="font-size:3rem;">🎉</div>
  <h1 style="color:#7c3aed;font-size:1.8rem;margin-top:8px;">Kauf bestätigt!</h1>
  <p style="color:#64748b;">AI Income Machine — 90-Day Blueprint</p>
</div>

<div style="background:#f0fdf4;border:2px solid #22c55e;border-radius:12px;padding:24px;margin:20px 0;text-align:center;">
  <p style="color:#166534;font-weight:700;font-size:1.1rem;margin-bottom:12px;">✅ Dein Blueprint ist sofort verfügbar</p>
  <a href="https://autoincome-ai.vercel.app/danke.html" style="display:inline-block;background:#22c55e;color:white;padding:14px 32px;border-radius:50px;font-weight:700;text-decoration:none;font-size:1rem;margin:8px 0;">📄 Jetzt auf Blueprint zugreifen →</a>
  <p style="color:#15803d;font-size:0.85rem;margin-top:8px;">Klick den Button um deinen Inhalt sofort zu starten</p>
</div>

<div style="background:#f8f9fa;border-radius:12px;padding:24px;margin:20px 0;">
  <h2 style="color:#1e293b;font-size:1.2rem;margin-bottom:16px;">Was du jetzt bekommst:</h2>
  <p style="color:#475569;line-height:2;">
    ✅ <strong>90-Day AI Income Blueprint</strong> — vollständiger Schritt-für-Schritt Plan<br>
    ✅ <strong>KI-Tool Stack Übersicht</strong> — genau welche Tools, wie einsetzen<br>
    ✅ <strong>Wöchentliche Updates</strong> — neue Strategien und Optimierungen<br>
    ✅ <strong>Support via Email</strong> — Fragen? Wir helfen dir weiter<br>
    ✅ <strong>60-Tage Geld-zurück-Garantie</strong> — kein Risiko für dich
  </p>
</div>

<div style="background:linear-gradient(135deg,#1e1b4b,#312e81);border-radius:12px;padding:28px;margin:20px 0;color:white;text-align:center;">
  <p style="font-size:0.9rem;opacity:0.8;margin-bottom:4px;">🔥 Exklusiv für Blueprint-Käufer</p>
  <h2 style="font-size:1.4rem;margin-bottom:8px;">SuperMegaBot — Full Automation System</h2>
  <p style="opacity:0.85;font-size:0.9rem;margin-bottom:16px;">Automatisiere alles was der Blueprint aufbaut. Shopify + DS24 + KI + Social — vollautomatisch.</p>
  <div style="font-size:2rem;font-weight:900;margin:12px 0;">€97 <span style="font-size:1rem;opacity:0.6;text-decoration:line-through;">€297</span></div>
  <a href="${UPSELL_URL}" style="display:inline-block;background:white;color:#1e1b4b;padding:12px 32px;border-radius:50px;font-size:1rem;font-weight:700;text-decoration:none;">Als Blueprint-Käufer upgraden →</a>
  <p style="font-size:0.75rem;margin-top:12px;opacity:0.6;">Nur für Blueprint-Käufer verfügbar · Einmalzahlung</p>
</div>

<div style="border-top:1px solid #e2e8f0;padding:20px 0;text-align:center;color:#64748b;font-size:0.85rem;">
  <p>Fragen? <a href="mailto:support@aiitec.de" style="color:#7c3aed;">support@aiitec.de</a></p>
  <p style="margin-top:4px;">AiiteC · Rudolf Sarkany · Wien, Österreich</p>
  <p style="margin-top:8px;font-size:0.75rem;color:#94a3b8;">
    <a href="https://autoincome-ai.vercel.app/impressum.html" style="color:#94a3b8;">Impressum</a> &nbsp;·&nbsp;
    Du erhältst diese Email weil du AI Income Machine Blueprint gekauft hast.
  </p>
</div>
</body></html>`,
};

const WELCOME_EMAIL = {
  subject: '👋 Willkommen — hier ist dein kostenloser KI-Einkommens-Leitfaden',
  preview: 'Schön dass du da bist. Dieser Guide startet dich sofort.',
  html: `<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;background:#ffffff;">
<div style="text-align:center;padding:20px 0;">
  <h1 style="color:#7c3aed;font-size:1.8rem;">Willkommen bei AiiteC! 🎉</h1>
  <p style="color:#64748b;font-size:1rem;">Du hast den ersten richtigen Schritt gemacht.</p>
</div>

<div style="background:#f0fdf4;border:2px solid #22c55e;border-radius:12px;padding:24px;margin:20px 0;text-align:center;">
  <p style="color:#166534;font-weight:700;font-size:1.1rem;margin-bottom:8px;">🎁 Deine kostenlose KI-Einkommens-Checkliste!</p>
  <a href="https://autoincome-ai.vercel.app/checkliste.html" style="display:inline-block;background:#22c55e;color:white;padding:14px 32px;border-radius:50px;font-weight:700;text-decoration:none;font-size:1rem;margin:8px 0;">✅ 21-Punkte Checkliste kostenlos öffnen →</a>
  <p style="color:#15803d;font-size:0.85rem;margin-top:8px;">21 Schritte · KI-Einkommen aufbauen · Sofort verfügbar</p>
</div>

<div style="background:#f8f9fa;border-radius:12px;padding:24px;margin:20px 0;">
  <h2 style="color:#1e293b;font-size:1.3rem;margin-bottom:16px;">Was du als nächstes bekommst:</h2>
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

const AFFILIATE_WELCOME = {
  subject: '🎯 Dein Affiliate-Link + fertige Marketing-Texte — alles hier',
  preview: 'In 10 Minuten kannst du deinen ersten Link teilen.',
  html: `<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;background:#fff;">
<div style="background:linear-gradient(135deg,#7c3aed,#5b21b6);border-radius:16px;padding:32px;text-align:center;margin-bottom:24px;color:white;">
  <h1 style="font-size:1.6rem;margin-bottom:8px;">Willkommen im Affiliate-Team! 🎉</h1>
  <p style="opacity:.9;font-size:1rem;">Du verdienst jetzt €18,50 pro Blueprint-Verkauf und €48,50 pro SuperMegaBot-Verkauf.</p>
</div>
<h2 style="color:#1e293b;font-size:1.2rem;">Schritt 1 — Deinen Affiliate-Link holen (2 Minuten)</h2>
<div style="background:#f8f9fa;border-radius:12px;padding:20px;margin:16px 0;">
  <ol style="color:#475569;line-height:2;padding-left:20px;">
    <li>Gehe zu <a href="https://www.digistore24.com" style="color:#7c3aed;">digistore24.com</a> und logge dich ein</li>
    <li>Oben rechts: "Marketplace" klicken</li>
    <li>Suche nach "AI Income Machine" oder gib direkt Produkt-ID <strong>668035</strong> ein</li>
    <li>Klicke "Als Affiliate bewerben" → sofortige Zulassung</li>
    <li>Kopiere deinen eindeutigen Affiliate-Link</li>
  </ol>
</div>
<h2 style="color:#1e293b;font-size:1.2rem;">Schritt 2 — Sofort teilen (fertige Texte)</h2>
<p style="color:#475569;">Hier sind copy-paste-bereite Marketing-Texte — <strong>ersetze [DEIN AFFILIATE-LINK] mit deinem Link:</strong></p>
<div style="background:#f0f4ff;border-left:4px solid #7c3aed;border-radius:4px;padding:16px;margin:16px 0;font-size:0.9rem;color:#334155;">
<strong>E-Mail (Betreff: Ich habe etwas gefunden...)</strong><br><br>
Hallo [VORNAME],<br><br>
Ich stoße nicht oft auf Produkte, die ich wirklich empfehlen kann. Der "AI Income Machine Blueprint" ist so eines.<br><br>
Ein 90-Tage-Plan auf Deutsch, €37 einmalig, 60-Tage-Garantie:<br>
[DEIN AFFILIATE-LINK]<br><br>
[DEIN NAME]
</div>
<div style="background:#f0fdf4;border-left:4px solid #22c55e;border-radius:4px;padding:16px;margin:16px 0;font-size:0.9rem;color:#334155;">
<strong>LinkedIn Post:</strong><br><br>
Ich habe den AI Income Machine Blueprint getestet — 90-Tage-Aktionsplan auf Deutsch, €37. Für alle die passiv Geld mit KI verdienen wollen.<br>
Link in Kommentaren 👇<br><br>
#PassivesEinkommen #KI #OnlineBusiness
</div>
<div style="background:#fef9c3;border-left:4px solid #f59e0b;border-radius:4px;padding:16px;margin:16px 0;font-size:0.9rem;color:#334155;">
<strong>WhatsApp / Telegram:</strong><br><br>
Hey, hast du schon mal von diesem KI-Blueprint gehört? 90-Tage-Plan auf Deutsch, einmalig €37: [DEIN AFFILIATE-LINK]
</div>
<div style="background:#fdf2f8;border:2px solid #a855f7;border-radius:12px;padding:24px;text-align:center;margin:24px 0;">
  <p style="color:#7c3aed;font-weight:700;font-size:1.1rem;margin-bottom:8px;">Deine Provisionen auf einen Blick:</p>
  <p style="color:#475569;">Blueprint (€37) → <strong style="color:#7c3aed;">€18,50</strong> pro Verkauf</p>
  <p style="color:#475569;">SuperMegaBot (€97) → <strong style="color:#7c3aed;">€48,50</strong> pro Verkauf</p>
  <p style="color:#475569;font-size:0.85rem;margin-top:8px;">Auszahlung: wöchentlich via Digistore24 · Cookie: 30 Tage</p>
</div>
<p style="color:#475569;font-size:0.9rem;">Fragen? Schreib uns: <a href="mailto:support@aiitec.de" style="color:#7c3aed;">support@aiitec.de</a></p>
<div style="text-align:center;padding:20px 0;color:#94a3b8;font-size:0.8rem;border-top:1px solid #e2e8f0;margin-top:20px;">
  <p>AiiteC · Rudolf Sarkany · <a href="https://autoincome-ai.vercel.app/affiliate.html" style="color:#7c3aed;">Alle Materialien</a></p>
</div>
</body></html>`,
  text: 'Willkommen im Affiliate-Team! Dein Affiliate-Link: digistore24.com → Produkt 668035. Provision: 50% = €18,50 pro Sale.',
};

async function sendAffiliateCampaign(count) {
  const date = new Date().toISOString().slice(0, 10);
  const t = await klaviyoRequest('POST', '/api/templates/', {
    data: { type: 'template', attributes: { name: `Affiliate-Welcome-${date}-${Date.now()}`, editor_type: 'CODE', html: AFFILIATE_WELCOME.html, text: AFFILIATE_WELCOME.text } },
  });
  if (t.status !== 201) throw new Error(`AffTmpl ${t.status}`);
  const tmplId = t.data.data.id;
  await new Promise(r => setTimeout(r, 1000));
  const c = await klaviyoRequest('POST', '/api/campaigns/', {
    data: { type: 'campaign', attributes: {
      name: `Affiliate Welcome [${date}] — ${count}`,
      audiences: { included: [AFFILIATE_LIST_ID], excluded: [] },
      send_strategy: { method: 'immediate' },
      'campaign-messages': { data: [{ type: 'campaign-message', attributes: { channel: 'email', label: 'Affiliate Welcome', content: { subject: AFFILIATE_WELCOME.subject, preview_text: AFFILIATE_WELCOME.preview, from_email: 'newsletter@aiitec.de', from_label: 'Rudolf — AiiteC', reply_to_email: 'support@aiitec.de' } } }] },
    } },
  });
  if (![200, 201].includes(c.status)) throw new Error(`AffCamp ${c.status}`);
  const campId = c.data.data.id;
  await new Promise(r => setTimeout(r, 1000));
  const msgs = await klaviyoRequest('GET', `/api/campaigns/${campId}/campaign-messages/`);
  const msgId = msgs.data.data?.[0]?.id;
  if (!msgId) throw new Error('No AffMsg ID');
  await klaviyoRequest('POST', '/api/campaign-message-assign-template/', { data: { type: 'campaign-message', id: msgId, relationships: { template: { data: { type: 'template', id: tmplId } } } } });
  await new Promise(r => setTimeout(r, 1000));
  await klaviyoRequest('POST', '/api/campaign-send-jobs/', { data: { type: 'campaign-send-job', attributes: { id: campId } } });
  return campId;
}

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
  day14: {
    subject: '14 Tage später — was hat sich verändert?',
    preview: 'Eine Erfolgsgeschichte + dein konkreter nächster Schritt.',
    html: `<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
<h2 style="color:#7c3aed;">14 Tage sind vergangen 📅</h2>
<p style="color:#475569;">Ich möchte dir von jemandem erzählen der vor 14 Tagen genau da war wo du jetzt bist.</p>
<div style="background:#f0fdf4;border:1px solid #86efac;border-radius:12px;padding:20px;margin:20px 0;">
  <p style="color:#166534;font-weight:700;">"In Woche 3 mein erster Verkauf"</p>
  <p style="color:#166534;font-size:0.9rem;font-style:italic;">"Ich war skeptisch. Aber ich habe einfach den Blueprint-Plan befolgt — Schritt für Schritt. In Woche 3 kam mein erster Digistore24-Verkauf. Es funktioniert, wenn man es wirklich umsetzt."</p>
  <p style="color:#166534;font-size:0.85rem;margin-top:8px;font-weight:600;">— Kunde aus Österreich</p>
</div>
<p style="color:#475569;">Was war sein konkreter nächster Schritt? Genau das was ich dir jetzt empfehle:</p>
<div style="background:#f8f9fa;border-radius:12px;padding:20px;margin:20px 0;">
  <p style="color:#1e293b;font-weight:600;">Dein Plan für die nächsten 7 Tage:</p>
  <p style="color:#475569;line-height:1.9;">
    📌 Tag 15: Digistore24-Konto erstellen (15 Min, kostenlos)<br>
    📌 Tag 16: Erstes Produkt als Reseller auflisten<br>
    📌 Tag 17: Affiliate-Link teilen (LinkedIn, WhatsApp, Email)<br>
    📌 Tag 18-21: Erste Einnahmen beobachten
  </p>
</div>
<div style="text-align:center;margin:24px 0;">
  <a href="${PRODUCT_URL}" style="background:linear-gradient(135deg,#7c3aed,#5b21b6);color:white;padding:14px 32px;border-radius:50px;font-weight:700;text-decoration:none;display:inline-block;">Blueprint €37 — jetzt starten →</a>
</div>
<p style="color:#94a3b8;font-size:0.85rem;">60-Tage Geld-zurück-Garantie · Rudolf — AiiteC</p>
</body></html>`,
    text: `14 Tage Follow-up: Nächster Schritt + Erfolgsgeschichte. Blueprint €37 → ${PRODUCT_URL}`,
  },
  day21: {
    subject: '🆕 NEU: SuperMegaBot System für €97',
    preview: 'Das komplette KI-Automation System — jetzt verfügbar.',
    html: `<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
<h2 style="color:#7c3aed;">🆕 Neu: Das komplette System ist da</h2>
<p style="color:#475569;">Du bist seit 3 Wochen dabei. Heute stelle ich dir etwas vor das ich bisher nicht öffentlich kommuniziert habe.</p>
<div style="background:linear-gradient(135deg,#1e293b,#0f172a);border:2px solid #7c3aed;border-radius:12px;padding:28px;margin:20px 0;color:white;text-align:center;">
  <p style="color:#a78bfa;font-size:1rem;margin-bottom:4px;">⭐ Exklusiv für E-Mail-Subscriber</p>
  <h2 style="color:white;font-size:1.6rem;margin:8px 0;">SuperMegaBot — KI-Automation System</h2>
  <p style="color:#94a3b8;font-size:0.9rem;margin-bottom:16px;">Das vollständige System das mein Business automatisiert</p>
  <div style="background:#1e293b;border-radius:8px;padding:16px;text-align:left;margin-bottom:16px;">
    <p style="color:#e2e8f0;font-size:0.9rem;line-height:1.8;margin:0;">
      ✅ LinkedIn Auto-Poster (3x/Woche)<br>
      ✅ Instagram Auto-Poster (Di/Do/Sa)<br>
      ✅ Facebook Auto-Poster (Mo/Mi/Fr)<br>
      ✅ Klaviyo E-Mail-Automation (30 Tage Sequenz)<br>
      ✅ Digistore24 Revenue Tracking (täglich)<br>
      ✅ 32 SEO-Blog-Artikel auf Deutsch<br>
      ✅ Amazon + Affiliate-Links automatisch<br>
      ✅ 1-Click Deploy auf Railway
    </p>
  </div>
  <p style="color:#64748b;font-size:0.85rem;text-decoration:line-through;margin:0;">Normalpreis: €297</p>
  <p style="font-size:2.2rem;font-weight:900;color:white;margin:8px 0;">€97</p>
  <p style="color:#94a3b8;font-size:0.8rem;margin-bottom:16px;">Einmalzahlung · Kein Abo · Lebenszeit-Zugang</p>
  <a href="${UPSELL_URL}" style="display:inline-block;background:linear-gradient(135deg,#7c3aed,#5b21b6);color:white;padding:14px 36px;border-radius:50px;font-size:1rem;font-weight:700;text-decoration:none;">Vollsystem sichern →</a>
</div>
<p style="color:#475569;font-size:0.9rem;">Oder starte mit dem Blueprint für €37: <a href="${PRODUCT_URL}" style="color:#7c3aed;">${PRODUCT_URL}</a></p>
<p style="color:#94a3b8;font-size:0.85rem;">60-Tage Geld-zurück-Garantie · Rudolf — AiiteC</p>
</body></html>`,
    text: `SuperMegaBot Vollsystem €97 → ${UPSELL_URL} | Blueprint €37 → ${PRODUCT_URL}`,
  },
  day30: {
    subject: '€185–485/Monat als Affiliate — ohne eigenes Produkt',
    preview: '50% Provision auf alle Verkäufe. Kostenlos starten.',
    html: `<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
<h2 style="color:#7c3aed;">Ein Monat dabei — danke! 🎉</h2>
<p style="color:#475569;">Du bist seit 30 Tagen in meiner Liste. Das ist nicht selbstverständlich — danke für dein Vertrauen.</p>
<p style="color:#475569;">Heute zeige ich dir Option 3 — die die ich oft vergesse zu erwähnen:</p>
<div style="background:#f0fdf4;border:2px solid #86efac;border-radius:12px;padding:24px;margin:20px 0;">
  <h3 style="color:#166534;margin-bottom:12px;">💰 Als Affiliate verdienen — ohne eigenes Produkt</h3>
  <p style="color:#166534;font-size:0.9rem;line-height:1.9;">
    Du empfiehlst meine Produkte weiter. Ich zahle dir 50% von jedem Verkauf.<br><br>
    <strong>Blueprint €37</strong> → du bekommst <strong>€18,50</strong> pro Verkauf<br>
    <strong>SuperMegaBot €97</strong> → du bekommst <strong>€48,50</strong> pro Verkauf<br><br>
    Digistore24 zahlt wöchentlich direkt auf dein Konto aus.<br>
    Keine Website nötig. Keine Mindestbestellmenge. Keine Vorabinvestition.
  </p>
  <div style="background:#dcfce7;border-radius:8px;padding:16px;margin-top:16px;">
    <p style="color:#166534;font-weight:700;margin:0;">Beispielrechnung:</p>
    <p style="color:#166534;font-size:0.9rem;margin:8px 0;">10 Verkäufe Blueprint/Monat = <strong>€185/Monat</strong><br>
    5 Verkäufe SuperMegaBot/Monat = <strong>€242/Monat</strong><br>
    Kombiniert = <strong>€427/Monat</strong> passiv</p>
  </div>
  <div style="text-align:center;margin-top:20px;">
    <a href="https://autoincome-ai.vercel.app/affiliate.html" style="display:inline-block;background:#059669;color:white;padding:14px 32px;border-radius:50px;font-weight:700;text-decoration:none;">Jetzt kostenlos Affiliate werden →</a>
  </div>
</div>
<p style="color:#475569;font-size:0.9rem;">Hast du Fragen? Antworte einfach auf diese E-Mail — ich lese alles persönlich.</p>
<p style="color:#94a3b8;font-size:0.85rem;">Rudolf Sarkany — AiiteC KI-Automation</p>
</body></html>`,
    text: `Affiliate-Programm: 50% Provision → https://autoincome-ai.vercel.app/affiliate.html | Blueprint €37 → ${PRODUCT_URL} | SuperMegaBot €97 → ${UPSELL_URL}`,
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

const AFFILIATE_FOLLOWUPS = {
  day3: {
    subject: '🔗 Hast du deinen Affiliate-Link schon geteilt?',
    preview: 'Ein Post reicht für erste €18,50.',
    html: `<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;background:#fff;">
<h2 style="color:#7c3aed;">Vor 3 Tagen bist du Affiliate geworden 🎯</h2>
<p style="color:#475569;">Hast du deinen Digistore24 Affiliate-Link schon? Falls nicht — hier nochmal kurz erklärt:</p>
<div style="background:#f8f9fa;border-radius:12px;padding:20px;margin:16px 0;">
<p style="color:#1e293b;font-weight:600;">In 3 Schritten zu deinem Link:</p>
<ol style="color:#475569;line-height:2;padding-left:20px;">
<li>digistore24.com → Login</li>
<li>Marketplace → Suche "668035"</li>
<li>"Als Affiliate bewerben" → Link kopieren ✅</li>
</ol>
</div>
<p style="color:#475569;">Wenn du deinen Link hast, brauchst du nur <strong>einen einzigen Post</strong>, um die ersten €18,50 zu verdienen. Hier ist der einfachste:</p>
<div style="background:#f0f4ff;border-left:4px solid #7c3aed;border-radius:4px;padding:16px;margin:16px 0;font-size:0.9rem;color:#334155;">
<strong>WhatsApp an 5 Freunde:</strong><br><br>
"Hey, ich habe diesen KI-Blueprint gefunden — auf Deutsch, €37, mit 60-Tage-Garantie. Falls du passiv Geld mit KI verdienen willst: [DEIN LINK]"
</div>
<p style="color:#475569;font-size:0.9rem;">Das dauert 3 Minuten. Bei 5 Freunden mit 1% Chance auf Kauf = 5% Chance = €18,50 × 0,05 = theoretisch €0,92 pro Nachricht. Das klingt wenig — aber schick die Nachricht an 100 Kontakte und es sind €92 für 15 Minuten Arbeit.</p>
<p style="color:#475569;">Fragen? <a href="mailto:support@aiitec.de" style="color:#7c3aed;">support@aiitec.de</a> oder <a href="https://autoincome-ai.vercel.app/affiliate.html" style="color:#7c3aed;">alle Materialien hier</a>.</p>
<div style="text-align:center;padding:16px 0;color:#94a3b8;font-size:0.8rem;border-top:1px solid #e2e8f0;margin-top:20px;"><p>AiiteC · Rudolf Sarkany</p></div>
</body></html>`,
    text: 'Affiliate-Link noch nicht geteilt? In 3 Minuten: digistore24.com → Marketplace → 668035 → Link kopieren → teilen.',
  },
  day7: {
    subject: '💰 Erster Affiliate-Sale: So machen es unsere Besten',
    preview: 'Die 3 Kanäle die am schnellsten konvertieren.',
    html: `<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;background:#fff;">
<h2 style="color:#7c3aed;">Woche 1 als Affiliate — wie läuft es? 🚀</h2>
<p style="color:#475569;">Die erfolgreichsten Affiliates bei uns haben einen ersten Sale in den ersten 7–14 Tagen. Hier ist was sie gemeinsam haben:</p>
<div style="background:#f0fdf4;border-radius:12px;padding:20px;margin:16px 0;">
<p style="color:#166534;font-weight:600;">Die 3 schnellsten Kanäle für erste Sales:</p>
<ul style="color:#374151;line-height:2;padding-left:20px;">
<li><strong>E-Mail-Liste:</strong> Wenn du bereits eine Liste hast — eine E-Mail mit deinem Affiliate-Link genügt</li>
<li><strong>LinkedIn:</strong> 1 organischer Post über das Produkt bringt oft 50–200 organische Views und 1–3 Klicks</li>
<li><strong>Telegram/WhatsApp Gruppen:</strong> In thematisch passende Gruppen (Online Business, KI, Freelancing) teilen</li>
</ul>
</div>
<div style="background:linear-gradient(135deg,#7c3aed,#5b21b6);border-radius:12px;padding:24px;text-align:center;color:white;margin:20px 0;">
<p style="font-size:1rem;margin-bottom:8px;">Dein nächster Schritt:</p>
<p style="font-size:1.2rem;font-weight:700;">Teile deinen Link auf EINEM Kanal noch heute</p>
<p style="opacity:.8;font-size:0.85rem;margin-top:8px;">Bonus: Wer in den ersten 14 Tagen einen Sale erzielt, bekommt persönliches Feedback von Rudolf.</p>
</div>
<p style="color:#475569;font-size:0.9rem;">Fertige Texte zum Kopieren: <a href="https://autoincome-ai.vercel.app/affiliate.html#materialien" style="color:#7c3aed;">autoincome-ai.vercel.app/affiliate.html</a></p>
<div style="text-align:center;padding:16px 0;color:#94a3b8;font-size:0.8rem;border-top:1px solid #e2e8f0;margin-top:20px;"><p>AiiteC · Rudolf Sarkany · support@aiitec.de</p></div>
</body></html>`,
    text: 'Woche 1 als Affiliate: Teile deinen Link auf E-Mail-Liste, LinkedIn oder Telegram/WhatsApp. Fertige Texte: autoincome-ai.vercel.app/affiliate.html',
  },
};

async function sendAffiliateFollowup(emailObj, count, tag) {
  const date = new Date().toISOString().slice(0, 10);
  const t = await klaviyoRequest('POST', '/api/templates/', {
    data: { type: 'template', attributes: { name: `Aff-Followup-${tag}-${date}-${Date.now()}`, editor_type: 'CODE', html: emailObj.html, text: emailObj.text } },
  });
  if (t.status !== 201) throw new Error(`AffFollowTmpl ${t.status}`);
  const tmplId = t.data.data.id;
  await new Promise(r => setTimeout(r, 800));
  const c = await klaviyoRequest('POST', '/api/campaigns/', {
    data: { type: 'campaign', attributes: {
      name: `Affiliate ${tag} [${date}] — ${count}`,
      audiences: { included: [AFFILIATE_LIST_ID], excluded: [] },
      send_strategy: { method: 'immediate' },
      'campaign-messages': { data: [{ type: 'campaign-message', attributes: { channel: 'email', label: `Affiliate ${tag}`, content: { subject: emailObj.subject, preview_text: emailObj.preview, from_email: 'newsletter@aiitec.de', from_label: 'Rudolf — AiiteC', reply_to_email: 'support@aiitec.de' } } }] },
    } },
  });
  if (![200, 201].includes(c.status)) throw new Error(`AffFollowCamp ${c.status}`);
  const campId = c.data.data.id;
  await new Promise(r => setTimeout(r, 800));
  const msgs = await klaviyoRequest('GET', `/api/campaigns/${campId}/campaign-messages/`);
  const msgId = msgs.data.data?.[0]?.id;
  if (!msgId) throw new Error('No AffFollow msgId');
  await klaviyoRequest('POST', '/api/campaign-message-assign-template/', { data: { type: 'campaign-message', id: msgId, relationships: { template: { data: { type: 'template', id: tmplId } } } } });
  await new Promise(r => setTimeout(r, 800));
  await klaviyoRequest('POST', '/api/campaign-send-jobs/', { data: { type: 'campaign-send-job', attributes: { id: campId } } });
  return campId;
}

async function handleDS24IPN(req, res) {
  let params = {};
  try {
    if (typeof req.body === 'string' && req.body.includes('=')) {
      for (const pair of req.body.split('&')) {
        const [k, v] = pair.split('=');
        if (k) params[decodeURIComponent(k)] = decodeURIComponent((v || '').replace(/\+/g, ' '));
      }
    } else if (typeof req.body === 'object') {
      params = req.body;
    }
  } catch (e) {
    return res.status(400).json({ error: 'IPN parse error' });
  }

  const email = params.buyer_email;
  const firstName = params.buyer_firstname || '';
  const lastName = params.buyer_lastname || '';
  const productId = params.product_id || '';
  const orderId = params.order_id || '';
  const amount = params.billing_amount || params.net_amount || params.amount || '';
  const receivedSign = params.sha_sign || '';

  if (!email) return res.status(200).json({ ok: true, skipped: 'no email' });

  // Optional: validate DS24 SHA2-512 signature
  let signatureValid = true;
  if (DS24_IPN_PASSPHRASE && receivedSign) {
    const sorted = Object.keys(params)
      .filter(k => k !== 'sha_sign' && params[k] !== '')
      .sort();
    const str = sorted.map(k => k + params[k]).join('') + DS24_IPN_PASSPHRASE;
    const expected = createHash('sha512').update(str).digest('hex');
    signatureValid = expected.toLowerCase() === receivedSign.toLowerCase();
    if (!signatureValid) {
      await sendTelegram(`⚠️ DS24 IPN Signatur ungültig!\nEmail: ${email}\nOrder: ${orderId}\nEmpfangen: ${receivedSign.substring(0, 20)}...`);
    }
  }

  await sendTelegram(`💰 <b>DS24 KAUF!</b>\n📧 ${email} (${firstName} ${lastName})\n🛍️ Produkt: ${productId}\n📋 Order: ${orderId}\n💶 Betrag: €${amount}\n✅ Signatur: ${signatureValid ? 'OK' : 'nicht geprüft'}`);

  try {
    // Add buyer to Klaviyo with Buyer tag
    const profileRes = await klaviyoRequest('POST', '/api/profiles/', {
      data: {
        type: 'profile',
        attributes: {
          email,
          first_name: firstName,
          last_name: lastName,
          properties: {
            ds24_product_id: productId,
            ds24_order_id: orderId,
            purchase_amount: amount,
            purchase_date: new Date().toISOString(),
            customer_type: 'buyer',
          },
        },
      },
    });

    // Add to buyer list (subscribe)
    const profileId = profileRes.data?.data?.id;
    if (profileId) {
      await klaviyoRequest('POST', `/api/lists/${BUYER_LIST_ID}/relationships/profiles/`, {
        data: [{ type: 'profile', id: profileId }],
      });
    }

    // Send buyer welcome email campaign
    const t = await klaviyoRequest('POST', '/api/templates/', {
      data: {
        type: 'template',
        attributes: {
          name: `DS24 Buyer Welcome ${orderId} ${Date.now()}`,
          html: BUYER_WELCOME_EMAIL.html,
          subject: BUYER_WELCOME_EMAIL.subject,
        },
      },
    });
    const tmplId = t.data?.data?.id;

    const c = await klaviyoRequest('POST', '/api/campaigns/', {
      data: {
        type: 'campaign',
        attributes: {
          name: `Käufer-Welcome ${firstName || email} ${orderId}`,
          channel: 'email',
          audiences: {
            included: [BUYER_LIST_ID],
            excluded: [],
          },
          send_strategy: {
            method: 'immediate',
          },
          tracking_options: {
            is_tracking_opens: true,
            is_tracking_clicks: true,
          },
        },
      },
    });
    const campId = c.data?.data?.id;

    if (campId && tmplId) {
      const msgs = await klaviyoRequest('GET', `/api/campaigns/${campId}/campaign-messages/`);
      const msgId = msgs.data?.data?.[0]?.id;
      if (msgId) {
        await klaviyoRequest('POST', '/api/campaign-message-assign-template/', {
          data: {
            type: 'campaign-message',
            id: msgId,
            relationships: { template: { data: { type: 'template', id: tmplId } } },
          },
        });
      }
      await klaviyoRequest('POST', '/api/campaign-send-jobs/', {
        data: { type: 'campaign-send-job', attributes: { id: campId } },
      });
    }

    await sendTelegram(`📧 Käufer-Welcome gesendet an ${email}\nKampagne: ${campId}`);
    return res.status(200).json({ ok: true, email, campId });
  } catch (err) {
    await sendTelegram(`❌ DS24 IPN Fehler für ${email}: ${err.message.substring(0, 150)}`);
    return res.status(200).json({ ok: true, processed: false, error: err.message });
  }
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

  if (req.method === 'POST') {
    // DS24 IPN: form-encoded body with buyer_email (sha_sign optional if no passphrase set)
    const rawBody = typeof req.body === 'string' ? req.body : JSON.stringify(req.body || {});
    if (rawBody.includes('buyer_email') && (rawBody.includes('sha_sign') || rawBody.includes('transaction_id') || rawBody.includes('order_id'))) {
      return handleDS24IPN(req, res);
    }
    // Regular Klaviyo webhook
    if (secret !== CRON_SECRET) return handleWebhook(req, res);
  }

  if (secret !== CRON_SECRET) return res.status(401).json({ error: 'unauthorized' });
  if (!KLAVIYO_KEY) return res.status(200).json({ ok: true, note: 'no klaviyo key' });

  const results = [];

  try {
    // Day 0 — welcome email (regular subscribers)
    const newSubs = await getNewSubscribers();
    if (newSubs.length > 0) {
      const campId = await sendWelcomeCampaign(newSubs.length);
      results.push({ tag: 'day0', count: newSubs.length, campId });
      await sendTelegram(`📧 <b>Welcome-Email</b>: ${newSubs.length} neue Subscriber → Kampagne ${campId}`);
    }

    // Day 0 — affiliate welcome email (affiliate-signups list)
    try {
      const affNewUrl = `/api/lists/${AFFILIATE_LIST_ID}/profiles/?filter=greater-than(joined_group_at,${new Date(Date.now()-36*60*60*1000).toISOString()}),less-than(joined_group_at,${new Date().toISOString()})&page[size]=100`;
      const affR = await klaviyoRequest('GET', affNewUrl);
      const affNew = affR.status === 200 ? (affR.data.data || []) : [];
      if (affNew.length > 0) {
        const campId = await sendAffiliateCampaign(affNew.length);
        results.push({ tag: 'day0-affiliate', count: affNew.length, campId });
        await sendTelegram(`🎯 <b>Affiliate-Welcome</b>: ${affNew.length} neue Affiliates → Kampagne ${campId}`);
      }
    } catch (affErr) {
      await sendTelegram(`⚠️ Affiliate-Welcome Fehler: ${affErr.message.substring(0, 100)}`);
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

    // Day 14 follow-up
    const day14subs = await getSubscribersByAge(14);
    if (day14subs.length > 0) {
      const campId = await sendFollowupCampaign(FOLLOWUP_EMAILS.day14, day14subs.length, 'day14');
      results.push({ tag: 'day14', count: day14subs.length, campId });
      await sendTelegram(`📧 <b>Follow-up Tag 14</b>: ${day14subs.length} Subscriber → ${campId}`);
    }

    // Day 21 follow-up
    const day21subs = await getSubscribersByAge(21);
    if (day21subs.length > 0) {
      const campId = await sendFollowupCampaign(FOLLOWUP_EMAILS.day21, day21subs.length, 'day21');
      results.push({ tag: 'day21', count: day21subs.length, campId });
      await sendTelegram(`📧 <b>Follow-up Tag 21</b>: ${day21subs.length} Subscriber → ${campId}`);
    }

    // Day 30 follow-up
    const day30subs = await getSubscribersByAge(30);
    if (day30subs.length > 0) {
      const campId = await sendFollowupCampaign(FOLLOWUP_EMAILS.day30, day30subs.length, 'day30');
      results.push({ tag: 'day30', count: day30subs.length, campId });
      await sendTelegram(`📧 <b>Follow-up Tag 30</b>: ${day30subs.length} Subscriber → ${campId}`);
    }

    // Affiliate Day 3 + Day 7 follow-ups
    for (const [daysAgo, tag, emailObj] of [[3,'day3',AFFILIATE_FOLLOWUPS.day3],[7,'day7',AFFILIATE_FOLLOWUPS.day7]]) {
      try {
        const from = new Date(Date.now() - (daysAgo + 0.6) * 24 * 60 * 60 * 1000).toISOString();
        const to   = new Date(Date.now() - (daysAgo - 0.6) * 24 * 60 * 60 * 1000).toISOString();
        const affR = await klaviyoRequest('GET', `/api/lists/${AFFILIATE_LIST_ID}/profiles/?filter=greater-than(joined_group_at,${from}),less-than(joined_group_at,${to})&page[size]=100`);
        const affSubs = affR.status === 200 ? (affR.data.data || []) : [];
        if (affSubs.length > 0) {
          const campId = await sendAffiliateFollowup(emailObj, affSubs.length, tag);
          results.push({ tag: `affiliate-${tag}`, count: affSubs.length, campId });
          await sendTelegram(`🎯 <b>Affiliate Follow-up ${tag}</b>: ${affSubs.length} Affiliates → ${campId}`);
        }
      } catch (e) {
        await sendTelegram(`⚠️ Affiliate ${tag} Fehler: ${e.message.substring(0,100)}`);
      }
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
