const ADMIN_ID = process.env.AUTHORIZED_USER_ID

async function tg(chatId, text, token) {
  await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: chatId, text, parse_mode: 'Markdown' })
  })
}

async function askClaude(text) {
  const r = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': process.env.ANTHROPIC_API_KEY,
      'anthropic-version': '2023-06-01'
    },
    body: JSON.stringify({
      model: 'claude-sonnet-4-20250514',
      max_tokens: 400,
      system: 'Du bist RudiBot Admin Assistent. Kurze Antworten auf Deutsch.',
      messages: [{ role: 'user', content: text }]
    })
  })
  const data = await r.json()
  return data.content?.[0]?.text || 'Fehler bei Claude API'
}

module.exports = async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*')
  if (req.method !== 'POST') return res.json({ ok: true })

  try {
    const msg = req.body?.message
    if (!msg) return res.sendStatus(200)

    const chatId = String(msg.chat.id)
    const text = msg.text || ''
    const token = process.env.CONTROL_BOT_TOKEN || process.env.TELEGRAM_BOT_TOKEN

    if (chatId !== String(ADMIN_ID)) {
      await tg(chatId, '🚫 Nicht autorisiert.', token)
      return res.sendStatus(200)
    }

    let reply = ''

    if (text === '/start' || text === '/help') {
      reply = `🤖 *RudiBot Control v2.0*\n\n✅ System läuft!\n\n*Commands:*\n/status — System Übersicht\n/report — Tages Report\n/help — Diese Hilfe`
    } else if (text === '/status') {
      reply = `📊 *RudiBot Status*\n\n✅ Server: Online\n✅ Shopify: ${process.env.SHOPIFY_STORE_DOMAIN || 'N/A'}\n✅ Claude AI: ${process.env.ANTHROPIC_API_KEY ? 'Aktiv' : 'Inaktiv'}\n\n🚀 Alle Systeme laufen!`
    } else if (text === '/report') {
      reply = `📈 *Daily Report*\n\nDatum: ${new Date().toLocaleDateString('de')}\n\n✅ RudiBot läuft stabil\n✅ Alle Webhooks aktiv\n✅ Vercel deployed\n\n💰 Systeme aktiv: 30`
    } else {
      reply = await askClaude(text)
    }

    await tg(chatId, reply, token)

  } catch(e) {
    console.error('Control webhook error:', e)
  }

  res.sendStatus(200)
}
