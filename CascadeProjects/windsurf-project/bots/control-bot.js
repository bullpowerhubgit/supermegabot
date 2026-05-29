import TelegramBot from 'node-telegram-bot-api'
import { exec } from 'child_process'
import fs from 'fs'
import { CONTROL_BOT_TOKEN, PUBLIC_BOT_TOKEN, ADMIN_TELEGRAM_ID } from './shared/config.js'
import { consumeEvents, getUsers, publishEvent } from './shared/supabase-bridge.js'
import { startMTProto, sendMTMessage, getDialogs, getMe, getStatus, resolveUsername } from './mtproto-client.js'

const bot = new TelegramBot(CONTROL_BOT_TOKEN, { polling: true })
const publicBot = new TelegramBot(PUBLIC_BOT_TOKEN)

function isAdmin(msg) {
  return String(msg.from.id) === String(ADMIN_TELEGRAM_ID)
}

function adminOnly(handler) {
  return (msg, match) => {
    if (!isAdmin(msg)) {
      bot.sendMessage(msg.chat.id, '⛔ Nur der Admin darf das.')
      return
    }
    handler(msg, match)
  }
}

bot.on('polling_error', (err) => {
  console.error('[ControlBot] Polling Fehler:', err.message)
})

bot.onText(/\/start/, adminOnly((msg) => {
  bot.sendMessage(msg.chat.id,
    '*Control Bot – Admin Panel*\n' +
    'Befehle:\n' +
    '/status – System-Status\n' +
    '/exec <cmd> – Befehl ausführen\n' +
    '/logs – Letzte Logs\n' +
    '/broadcast <text> – Nachricht an alle User\n' +
    '/users – Registrierte User\n' +
    '/events – Events vom Public Bot\n' +
    '/stopbot public – Stoppt Public Bot (lokal)\n' +
    '/startbot public – Startet Public Bot (lokal)\n' +
    '/mtproto connect – Verbindet MTProto Client\n' +
    '/mtproto status – MTProto Status\n' +
    '/mtproto send <id> <text> – Nachricht senden\n' +
    '/mtproto dialogs – Alle Chats auflisten\n' +
    '/mtproto me – Account-Info',
    { parse_mode: 'Markdown' }
  )
}))

bot.onText(/\/status/, adminOnly(async (msg) => {
  const mem = process.memoryUsage()
  const uptime = Math.floor(process.uptime())
  bot.sendMessage(msg.chat.id,
    `*System Status*\n` +
    `Uptime: ${uptime}s\n` +
    `Memory: ${Math.round(mem.rss / 1024 / 1024)} MB\n` +
    `Node: ${process.version}\n` +
    `Platform: ${process.platform}`,
    { parse_mode: 'Markdown' }
  )
}))

bot.onText(/\/exec (.+)/, adminOnly((msg, match) => {
  const cmd = match[1]
  bot.sendMessage(msg.chat.id, `Führe aus: \`${cmd}\``, { parse_mode: 'Markdown' })

  exec(cmd, { cwd: process.cwd(), timeout: 30000 }, (error, stdout, stderr) => {
    const output = stdout || stderr || 'Keine Ausgabe'
    const chunks = output.match(/[\s\S]{1,4000}/g) || ['Keine Ausgabe']
    chunks.forEach((chunk, i) => {
      bot.sendMessage(msg.chat.id, `[${i + 1}/${chunks.length}]\n\`\`\`\n${chunk}\n\`\`\``, { parse_mode: 'Markdown' })
    })
    if (error) {
      bot.sendMessage(msg.chat.id, `❌ Exit Code: ${error.code}`)
    }
  })
}))

bot.onText(/\/broadcast (.+)/, adminOnly(async (msg, match) => {
  const text = match[1]
  const users = await getUsers()

  if (!users.length) {
    bot.sendMessage(msg.chat.id, 'Keine User in der Datenbank.')
    return
  }

  let sent = 0, failed = 0
  for (const user of users) {
    try {
      await publicBot.sendMessage(user.id, `📢 *Broadcast:*\n${text}`, { parse_mode: 'Markdown' })
      sent++
    } catch (e) {
      failed++
    }
  }

  bot.sendMessage(msg.chat.id, `✅ ${sent} gesendet\n❌ ${failed} fehlgeschlagen`)
}))

bot.onText(/\/users/, adminOnly(async (msg) => {
  const users = await getUsers()
  if (!users.length) {
    bot.sendMessage(msg.chat.id, 'Keine User gespeichert.')
    return
  }

  const list = users.map(u =>
    `- ${u.first_name || 'Unbekannt'} (@${u.username || '—'}) — \`${u.id}\``
  ).join('\n')

  bot.sendMessage(msg.chat.id, `*${users.length} User:*\n${list}`, { parse_mode: 'Markdown' })
}))

bot.onText(/\/events/, adminOnly(async (msg) => {
  const events = await consumeEvents('control')
  if (!events.length) {
    bot.sendMessage(msg.chat.id, 'Keine neuen Events.')
    return
  }

  for (const ev of events.slice(0, 5)) {
    const payload = JSON.stringify(ev.payload).slice(0, 300)
    bot.sendMessage(msg.chat.id,
      `*Event:* \`${ev.type}\`\n` +
      `Zeit: ${ev.created_at}\n` +
      `Data: \`${payload}\``,
      { parse_mode: 'Markdown' }
    )
  }
}))

bot.onText(/\/logs/, adminOnly((msg) => {
  const logFiles = [
    './bots/shared/queue.json',
  ].filter(f => fs.existsSync(f))

  if (!logFiles.length) {
    bot.sendMessage(msg.chat.id, 'Keine Log-Dateien gefunden.')
    return
  }

  logFiles.forEach(f => {
    const content = fs.readFileSync(f, 'utf8').slice(0, 3000)
    bot.sendMessage(msg.chat.id, `*${f}*\n\`\`\`json\n${content}\n\`\`\``, { parse_mode: 'Markdown' })
  })
}))

bot.onText(/\/stopbot public/, adminOnly((msg) => {
  publishEvent('public', 'shutdown', { reason: 'admin_command' })
  bot.sendMessage(msg.chat.id, '🛑 Shutdown-Signal an Public Bot gesendet (via Event Queue).')
}))

bot.onText(/\/startbot public/, adminOnly((msg) => {
  bot.sendMessage(msg.chat.id, '⚠️ Starte den Public Bot manuell mit:\n`node bots/public-bot.js`', { parse_mode: 'Markdown' })
}))

let mtProtoClient = null

bot.onText(/\/mtproto connect/, adminOnly(async (msg) => {
  bot.sendMessage(msg.chat.id, '🔌 Verbinde MTProto Client...\nFalls nötig, wirst du nach Telefonnummer + Code gefragt (im Terminal).')
  try {
    mtProtoClient = await startMTProto()
    if (mtProtoClient) {
      bot.sendMessage(msg.chat.id, '✅ MTProto Client verbunden!')
    } else {
      bot.sendMessage(msg.chat.id, '❌ Verbindung fehlgeschlagen. Prüfe API_ID/API_HASH in .env')
    }
  } catch (e) {
    bot.sendMessage(msg.chat.id, `❌ Fehler: ${e.message}`)
  }
}))

bot.onText(/\/mtproto status/, adminOnly((msg) => {
  const st = getStatus()
  bot.sendMessage(msg.chat.id,
    `*MTProto Status*\n` +
    `Client erstellt: ${st.hasClient ? '✅' : '❌'}\n` +
    `Verbunden: ${st.connected ? '✅' : '❌'}`,
    { parse_mode: 'Markdown' }
  )
}))

bot.onText(/\/mtproto me/, adminOnly(async (msg) => {
  try {
    const me = await getMe()
    if (!me) {
      bot.sendMessage(msg.chat.id, '❌ Nicht verbunden. Nutze zuerst /mtproto connect')
      return
    }
    bot.sendMessage(msg.chat.id,
      `*Account Info*\n` +
      `Name: ${me.firstName} ${me.lastName || ''}\n` +
      `Username: @${me.username || '—'}\n` +
      `ID: \`${me.id}\``,
      { parse_mode: 'Markdown' }
    )
  } catch (e) {
    bot.sendMessage(msg.chat.id, `❌ Fehler: ${e.message}`)
  }
}))

bot.onText(/\/mtproto dialogs/, adminOnly(async (msg) => {
  try {
    const dialogs = await getDialogs(15)
    if (!dialogs.length) {
      bot.sendMessage(msg.chat.id, 'Keine Dialoge gefunden oder nicht verbunden.')
      return
    }
    const list = dialogs.map(d =>
      `- ${d.title} (ID: \`${d.id}\`, Unread: ${d.unread})`
    ).join('\n')
    bot.sendMessage(msg.chat.id, `*Chats/Gruppen:*\n${list}`, { parse_mode: 'Markdown' })
  } catch (e) {
    bot.sendMessage(msg.chat.id, `❌ Fehler: ${e.message}`)
  }
}))

bot.onText(/\/mtproto send (.+)/, adminOnly(async (msg, match) => {
  try {
    const args = match[1].trim()
    const spaceIdx = args.indexOf(' ')
    if (spaceIdx < 0) {
      bot.sendMessage(msg.chat.id, '⚠️ Nutzung: /mtproto send <chat_id|@username> <Nachricht>')
      return
    }
    const target = args.slice(0, spaceIdx).trim()
    const text = args.slice(spaceIdx + 1).trim()

    bot.sendMessage(msg.chat.id, `📤 Sende an \`${target}\`...`, { parse_mode: 'Markdown' })
    await sendMTMessage(target, text)
    bot.sendMessage(msg.chat.id, '✅ Nachricht gesendet!')
  } catch (e) {
    bot.sendMessage(msg.chat.id, `❌ Senden fehlgeschlagen: ${e.message}`)
  }
}))

setInterval(async () => {
  const events = await consumeEvents('control')
  for (const ev of events) {
    if (ev.type === 'user_joined') {
      bot.sendMessage(ADMIN_TELEGRAM_ID, `👤 Neuer User: @${ev.payload.username || ev.payload.user_id}`)
    } else if (ev.type === 'mtproto_event') {
      const p = ev.payload
      bot.sendMessage(ADMIN_TELEGRAM_ID,
        `📨 MTProto Nachricht\n` +
        `Von: ${p.from_name} (\`${p.from_id}\`)\n` +
        `Chat: \`${p.chat_id}\`\n` +
        `Text: ${p.text.slice(0, 200)}`,
        { parse_mode: 'Markdown' }
      )
    } else if (ev.type === 'webapp_data') {
      const data = JSON.stringify(ev.payload.data).slice(0, 200)
      bot.sendMessage(ADMIN_TELEGRAM_ID, `📥 WebApp Data von @${ev.payload.username || ev.payload.user_id}:\n\`${data}\``, { parse_mode: 'Markdown' })
    }
  }
}, 5000)

console.log('[ControlBot] Gestartet. Warte auf Admin-Befehle...')
