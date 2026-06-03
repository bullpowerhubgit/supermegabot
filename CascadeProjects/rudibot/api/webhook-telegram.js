import Anthropic from '@anthropic-ai/sdk'
import { createClient } from '@supabase/supabase-js'

const ai = new Anthropic({ 
  apiKey: process.env.ANTHROPIC_API_KEY,
  dangerouslyAllowBrowser: false,
})
const supabase = createClient(
  process.env.SUPABASE_URL, 
  process.env.SUPABASE_SERVICE_KEY || process.env.SUPABASE_ANON_KEY
)

async function tg(chatId, text) {
  await fetch(`https://api.telegram.org/bot${process.env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: chatId, text, parse_mode: 'Markdown' })
  })
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*')
  if (req.method !== 'POST') return res.json({ ok: true })

  try {
    const msg = req.body?.message
    if (!msg) return res.sendStatus(200)

    const chatId = msg.chat.id
    const text = msg.text || ''

    const reply = await ai.messages.create({
      model: 'claude-sonnet-4-6',
      max_tokens: 500,
      system: `Du bist RudiBot, ein freundlicher KI-Assistent. Antworte kurz auf Deutsch.`,
      messages: [{ role: 'user', content: text }]
    })

    await tg(chatId, reply.content[0].text)

    try {
      await supabase.from('logs').insert({
        system: 'telegram', event: 'message',
        data: { chatId, text: text.substring(0, 100) }
      })
    } catch (_) {}

    return res.sendStatus(200)
  } catch (e) {
    console.error('webhook-telegram error:', e.message)
    return res.sendStatus(200)
  }
}
