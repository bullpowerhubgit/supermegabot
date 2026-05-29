import fs from 'fs'
import path from 'path'
import { createClient } from '@supabase/supabase-js'
import { SUPABASE_URL, SUPABASE_ANON_KEY, GCP_PROJECT_ID, GCP_APIS } from './config.js'

let supabase = null
try {
  if (SUPABASE_URL && SUPABASE_ANON_KEY) {
    supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY)
  }
} catch (e) {
  console.warn('[Bridge] Supabase init fehlgeschlagen:', e.message)
}

const QUEUE_PATH = path.resolve('./bots/shared/queue.json')

function readQueue() {
  try { return JSON.parse(fs.readFileSync(QUEUE_PATH, 'utf8')) }
  catch (e) { return [] }
}

function writeQueue(queue) {
  fs.writeFileSync(QUEUE_PATH, JSON.stringify(queue, null, 2))
}

export async function publishEvent(target, type, payload = {}) {
  const event = {
    id: Date.now().toString(36) + Math.random().toString(36).slice(2, 5),
    target,
    type,
    payload,
    status: 'pending',
    created_at: new Date().toISOString()
  }

  if (supabase) {
    try {
      await supabase.from('bot_events').insert(event)
      return event
    } catch (e) {}
  }

  const queue = readQueue()
  queue.push(event)
  writeQueue(queue)
  return event
}

export async function consumeEvents(target) {
  if (supabase) {
    try {
      const { data, error } = await supabase
        .from('bot_events')
        .select('*')
        .eq('target', target)
        .eq('status', 'pending')
        .order('created_at', { ascending: true })

      if (error) throw error
      if (data?.length) {
        const ids = data.map(e => e.id)
        await supabase.from('bot_events').update({ status: 'done' }).in('id', ids)
      }
      return data || []
    } catch (e) {}
  }

  const queue = readQueue()
  const mine = queue.filter(e => e.target === target && e.status === 'pending')
  const rest = queue.filter(e => !(e.target === target && e.status === 'pending'))
  writeQueue(rest)
  return mine
}

export async function saveUser(user) {
  if (!supabase) return
  try {
    await supabase.from('telegram_users').upsert({
      id: user.id,
      username: user.username || null,
      first_name: user.first_name || null,
      last_name: user.last_name || null,
      updated_at: new Date().toISOString()
    }, { onConflict: 'id' })
  } catch (e) {}
}

export async function getUsers() {
  if (!supabase) return []
  try {
    const { data } = await supabase.from('telegram_users').select('*')
    return data || []
  } catch (e) { return [] }
}
