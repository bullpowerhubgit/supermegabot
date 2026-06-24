// Klaviyo New Subscriber Webhook Handler
// Receives webhook from Klaviyo when profile is added to list Xwxq6V
// Sends immediate welcome email via Klaviyo Send Campaign API
// Setup: Klaviyo → Integrations → Webhooks → Add Webhook → this URL + topic: Subscribed to List

const KLAVIYO_KEY = process.env.KLAVIYO_API_KEY;
const LIST_ID = 'Xwxq6V';
const TELEGRAM_BOT = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT = process.env.TELEGRAM_CHAT_ID;

// Welcome Flow Template IDs (created 2026-06-24)
const WELCOME_TEMPLATE_ID = 'WLRWGt';
const WELCOME_SUBJECT = 'Deine KI-Checkliste ist bereit 🎉';

async function sendTelegram(msg) {
  if (!TELEGRAM_BOT || !TELEGRAM_CHAT) return;
  try {
    await fetch(`https://api.telegram.org/bot${TELEGRAM_BOT}/sendMessage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: TELEGRAM_CHAT, text: msg }),
    });
  } catch {}
}

async function kv(method, path, body) {
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

async function sendWelcomeEmail(email, firstName) {
  // Step 1: Create the campaign with inline message
  const c = await kv('POST', '/api/campaigns/', {
    data: {
      type: 'campaign',
      attributes: {
        name: `Welcome-${email.split('@')[0]}-${Date.now()}`,
        audiences: { included: [LIST_ID], excluded: [] },
        send_strategy: { method: 'immediate' },
        'campaign-messages': {
          data: [
            {
              type: 'campaign-message',
              attributes: {
                channel: 'email',
                label: 'Welcome Email Auto',
                content: {
                  subject: WELCOME_SUBJECT,
                  preview_text: 'Hier ist deine kostenlose 21-Punkte Checkliste...',
                  from_email: 'newsletter@aiitec.de',
                  from_label: 'Rudolf von AiiteC',
                  reply_to_email: 'support@aiitec.de',
                },
              },
            },
          ],
        },
      },
    },
  });

  if (![200, 201].includes(c.status)) {
    throw new Error(`Campaign creation failed: ${c.status} ${JSON.stringify(c.data).substring(0, 200)}`);
  }

  const campaignId = c.data.data.id;
  await new Promise((r) => setTimeout(r, 800));

  // Step 2: Get campaign message ID
  const msgs = await kv('GET', `/api/campaigns/${campaignId}/campaign-messages/`);
  const messageId = msgs.data?.data?.[0]?.id;
  if (!messageId) throw new Error('No message ID found');

  await new Promise((r) => setTimeout(r, 500));

  // Step 3: Assign template
  const assign = await kv('POST', '/api/campaign-message-assign-template/', {
    data: {
      type: 'campaign-message',
      id: messageId,
      attributes: {
        label: 'Welcome',
        channel: 'email',
        content: {
          subject: WELCOME_SUBJECT,
          preview_text: 'Deine kostenlose 21-Punkte KI-Einkommen Checkliste',
          from_email: 'newsletter@aiitec.de',
          from_label: 'Rudolf von AiiteC',
          reply_to_email: 'support@aiitec.de',
        },
      },
      relationships: {
        template: { data: { type: 'template', id: WELCOME_TEMPLATE_ID } },
      },
    },
  });

  if (![200, 201].includes(assign.status)) {
    throw new Error(`Template assign failed: ${assign.status} ${JSON.stringify(assign.data).substring(0, 200)}`);
  }

  await new Promise((r) => setTimeout(r, 800));

  // Step 4: Send
  const send = await kv('POST', '/api/campaign-send-jobs/', {
    data: {
      type: 'campaign-send-job',
      attributes: { id: campaignId },
    },
  });

  if (![200, 201, 202].includes(send.status)) {
    throw new Error(`Send failed: ${send.status} ${JSON.stringify(send.data).substring(0, 200)}`);
  }

  return campaignId;
}

export default async function handler(req, res) {
  if (req.method === 'GET') {
    // Health check
    return res.status(200).json({ ok: true, endpoint: 'klaviyo-webhook', ready: true });
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  let body;
  try {
    body = typeof req.body === 'string' ? JSON.parse(req.body) : req.body;
  } catch (e) {
    return res.status(400).json({ error: 'Invalid JSON' });
  }

  // Klaviyo webhook payload can come in multiple formats:
  // v2: { type: 'profile.added_to_list', data: { attributes: { profile: { email, first_name } } } }
  // v1: { event: 'Added to List', customer_properties: { $email, $first_name } }
  const eventType = body?.type || body?.event || '';

  // Parse email from various payload formats
  let email = (
    body?.data?.attributes?.profile?.email ||
    body?.data?.attributes?.email ||
    body?.customer_properties?.['$email'] ||
    body?.profile?.email ||
    body?.email
  );

  let firstName = (
    body?.data?.attributes?.profile?.first_name ||
    body?.data?.attributes?.first_name ||
    body?.customer_properties?.['$first_name'] ||
    body?.profile?.first_name ||
    body?.first_name ||
    'du'
  );

  if (!email) {
    // Log but return 200 so Klaviyo doesn't retry
    await sendTelegram(`⚠️ Klaviyo Webhook — kein Email im Payload: ${JSON.stringify(body).substring(0, 200)}`);
    return res.status(200).json({ ok: true, skipped: 'no email', body });
  }

  // Only process list subscription events
  const isSubscription = (
    !eventType ||
    eventType.includes('list') ||
    eventType.includes('subscribe') ||
    eventType.includes('added')
  );

  if (!isSubscription) {
    return res.status(200).json({ ok: true, skipped: `event: ${eventType}` });
  }

  try {
    const campaignId = await sendWelcomeEmail(email, firstName);
    await sendTelegram(`✅ Welcome Email gesendet!\n📧 ${email}\n👤 ${firstName}\nCampaign: ${campaignId}`);
    return res.status(200).json({ ok: true, email, campaignId });
  } catch (err) {
    await sendTelegram(`❌ Welcome Email Fehler für ${email}: ${err.message.substring(0, 200)}`);
    // Return 200 so Klaviyo doesn't retry infinitely
    return res.status(200).json({ ok: false, error: err.message, email });
  }
}
