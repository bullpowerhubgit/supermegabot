import { TelegramClient } from 'telegram'
import { StringSession } from 'telegram/sessions'
import input from 'input'
import fs from 'fs'
import path from 'path'
import { MTProto_API_ID, MTProto_API_HASH, ADMIN_TELEGRAM_ID } from './shared/config.js'
import { publishEvent } from './shared/supabase-bridge.js'

const SESSION_PATH = path.resolve('./bots/shared/mtproto_session.txt')

function loadSession() {
  try { return fs.readFileSync(SESSION_PATH, 'utf8') }
  catch (e) { return '' }
}

function saveSession(session) {
  fs.writeFileSync(SESSION_PATH, session)
}

let client = null
let isConnected = false

async function createClient() {
  const stringSession = new StringSession(loadSession())
  client = new TelegramClient(stringSession, parseInt(MTProto_API_ID), MTProto_API_HASH, {
    connectionRetries: 5,
  })

  await client.start({
    phoneNumber: async () => await input.text('Telefonnummer (+49123...): '),
    password: async () => await input.text('2FA-Passwort (falls vorhanden): '),
    phoneCode: async () => await input.text('Code von Telegram: '),
    onError: (err) => console.error('[MTProto] Auth Error:', err.message),
  })

  saveSession(client.session.save())
  isConnected = true
  console.log('[MTProto] Verbunden als', (await client.getMe()).firstName)

  // Event Listener
  client.addEventHandler(async (event) => {
    const msg = event.message
    if (!msg) return

    const sender = await msg.getSender()
    const eventData = {
      type: 'mtproto_message',
      from_id: sender?.id?.toString() || 'unknown',
      from_name: sender?.firstName || 'unknown',
      chat_id: msg.chatId?.toString() || 'unknown',
      text: msg.text || '',
      timestamp: new Date().toISOString()
    }

    await publishEvent('control', 'mtproto_event', eventData)
    console.log('[MTProto] Nachricht empfangen:', eventData.text.slice(0, 50))
  })

  return client
}

export async function startMTProto() {
  if (!MTProto_API_ID || !MTProto_API_HASH) {
    console.error('[MTProto] Fehlende API_ID oder API_HASH in .env')
    return null
  }
  try {
    return await createClient()
  } catch (e) {
    console.error('[MTProto] Verbindung fehlgeschlagen:', e.message)
    return null
  }
}

export async function sendMTMessage(chatId, text) {
  if (!client || !isConnected) {
    throw new Error('MTProto Client nicht verbunden')
  }
  try {
    const result = await client.sendMessage(chatId, { message: text })
    return result
  } catch (e) {
    console.error('[MTProto] Senden fehlgeschlagen:', e.message)
    throw e
  }
}

export async function getDialogs(limit = 20) {
  if (!client || !isConnected) return []
  try {
    const dialogs = await client.getDialogs({ limit })
    return dialogs.map(d => ({
      id: d.id?.toString(),
      title: d.title || d.name || 'Unbekannt',
      unread: d.unreadCount || 0
    }))
  } catch (e) {
    console.error('[MTProto] Dialogs fehlgeschlagen:', e.message)
    return []
  }
}

export async function resolveUsername(username) {
  if (!client || !isConnected) return null
  try {
    const entity = await client.getEntity(username)
    return { id: entity.id?.toString(), username: entity.username }
  } catch (e) {
    console.error('[MTProto] Resolve fehlgeschlagen:', e.message)
    return null
  }
}

export async function joinChannel(inviteLinkOrUsername) {
  if (!client || !isConnected) return false
  try {
    await client.invoke(
      new (await import('telegram')).Api.channels.JoinChannel({
        channel: inviteLinkOrUsername.startsWith('@')
          ? inviteLinkOrUsername
          : await client.getEntity(inviteLinkOrUsername)
      })
    )
    return true
  } catch (e) {
    console.error('[MTProto] Join fehlgeschlagen:', e.message)
    return false
  }
}

export async function getMe() {
  if (!client || !isConnected) return null
  try {
    return await client.getMe()
  } catch (e) {
    return null
  }
}

export function getStatus() {
  return { connected: isConnected, hasClient: !!client }
}

// Auto-Start wenn direkt ausgeführt
if (import.meta.url === `file://${process.argv[1]}`) {
  startMTProto().catch(console.error)
}
