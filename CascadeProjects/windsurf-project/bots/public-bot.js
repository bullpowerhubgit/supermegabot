import TelegramBot from 'node-telegram-bot-api'
import { PUBLIC_BOT_TOKEN, WEBAPP_URL } from './shared/config.js'
import { saveUser, publishEvent } from './shared/supabase-bridge.js'

const bot = new TelegramBot(PUBLIC_BOT_TOKEN, { polling: true })

bot.on('polling_error', (err) => {
  console.error('[PublicBot] Polling Fehler:', err.message)
})

bot.onText(/\/start/, async (msg) => {
  const chatId = msg.chat.id
  const user = msg.from

  await saveUser(user)
  await publishEvent('control', 'user_joined', { user_id: user.id, username: user.username })

  const opts = {
    reply_markup: {
      inline_keyboard: [
        [{ text: 'WebApp öffnen', web_app: { url: WEBAPP_URL || 'https://example.com' } }],
        [{ text: 'Hilfe', callback_data: 'help' }]
      ]
    }
  }

  bot.sendMessage(chatId, `Willkommen ${user.first_name}!`, opts)
})

bot.onText(/\/help/, (msg) => {
  const chatId = msg.chat.id
  bot.sendMessage(chatId,
    '*Public Bot Befehle:*\n' +
    '/start – Startet den Bot und öffnet WebApp\n' +
    '/help – Zeigt diese Hilfe\n' +
    '/status – Dein Account-Status',
    { parse_mode: 'Markdown' }
  )
})

bot.onText(/\/status/, async (msg) => {
  const chatId = msg.chat.id
  const user = msg.from
  bot.sendMessage(chatId,
    `Deine ID: ${user.id}\n` +
    `Username: @${user.username || '—'}\n` +
    `Bot läuft: ✅`,
    { parse_mode: 'Markdown' }
  )
})

bot.on('message', async (msg) => {
  if (msg.web_app_data) {
    try {
      const data = JSON.parse(msg.web_app_data.data)
      console.log('[PublicBot] WebApp Daten:', data)
      await publishEvent('control', 'webapp_data', {
        user_id: msg.from.id,
        username: msg.from.username,
        data
      })
      bot.sendMessage(msg.chat.id, '✅ Daten empfangen!')
    } catch (e) {
      bot.sendMessage(msg.chat.id, '❌ Fehler beim Verarbeiten der Daten.')
    }
  }
})

bot.on('callback_query', (query) => {
  if (query.data === 'help') {
    bot.answerCallbackQuery(query.id, { text: 'Nutze /help für alle Befehle!' })
  }
})

console.log('[PublicBot] Gestartet. Warte auf Messages...')
