import dotenv from 'dotenv'
import gcpConfig from '../../lib/gcp-config.js'
dotenv.config()

export const PUBLIC_BOT_TOKEN = process.env.PUBLIC_BOT_TOKEN || ''
export const CONTROL_BOT_TOKEN = process.env.CONTROL_BOT_TOKEN || ''
export const ADMIN_TELEGRAM_ID = process.env.ADMIN_TELEGRAM_ID || ''
export const WEBAPP_URL = process.env.WEBAPP_URL || ''
export const MTProto_API_ID = process.env.MTPROTO_API_ID || ''
export const MTProto_API_HASH = process.env.MTPROTO_API_HASH || ''
export const SUPABASE_URL = process.env.SUPABASE_URL || ''
export const SUPABASE_ANON_KEY = process.env.SUPABASE_ANON_KEY || ''
export const GCP_PROJECT_ID = gcpConfig.projectId
export const GCP_APIS = gcpConfig.apiList

export function checkEnv() {
  const missing = []
  if (!PUBLIC_BOT_TOKEN) missing.push('PUBLIC_BOT_TOKEN')
  if (!CONTROL_BOT_TOKEN) missing.push('CONTROL_BOT_TOKEN')
  if (!ADMIN_TELEGRAM_ID) missing.push('ADMIN_TELEGRAM_ID')
  if (missing.length) {
    console.error('[Config] Fehlende Env-Variablen:', missing.join(', '))
    process.exit(1)
  }
}
