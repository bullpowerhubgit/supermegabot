import dotenv from 'dotenv'
import axios from 'axios'

dotenv.config()

const GOOGLE_CLIENT_ID = process.env.GOOGLE_CLIENT_ID
const GOOGLE_CLIENT_SECRET = process.env.GOOGLE_CLIENT_SECRET
const GMC_MERCHANT_ID = process.env.GMC_MERCHANT_ID

/**
 * Google OAuth2 Token erneuern
 */
export async function getGoogleAccessToken() {
  if (!GOOGLE_CLIENT_ID || !GOOGLE_CLIENT_SECRET) {
    throw new Error('GOOGLE_CLIENT_ID oder GOOGLE_CLIENT_SECRET fehlt in .env')
  }

  // TODO: Bei Bedarf Refresh Token Flow implementieren
  // Für jetzt: Direkter API-Zugriff mit API Keys wo möglich
  console.log('[GoogleAPI] Client bereit (OAuth2 Flow bei Bedarf erweiterbar)')
  return { clientId: GOOGLE_CLIENT_ID, merchantId: GMC_MERCHANT_ID }
}

/**
 * Google Merchant Center: Produkte abrufen
 */
export async function getMerchantProducts() {
  if (!GMC_MERCHANT_ID) {
    throw new Error('GMC_MERCHANT_ID fehlt')
  }

  try {
    const url = `https://shoppingcontent.googleapis.com/content/v2.1/${GMC_MERCHANT_ID}/products`
    const response = await axios.get(url, {
      headers: {
        Authorization: `Bearer ${await getAccessTokenFromServiceAccount()}`
      }
    })
    return response.data
  } catch (err) {
    console.warn('[GoogleAPI] Merchant Center Zugriff erfordert Service Account. Details:', err.message)
    return { items: [], warning: 'Service Account erforderlich' }
  }
}

/**
 * Google Search Console: Performance-Daten
 */
export async function getSearchConsoleData(siteUrl, days = 7) {
  const endDate = new Date().toISOString().split('T')[0]
  const startDate = new Date(Date.now() - days * 86400000).toISOString().split('T')[0]

  try {
    const response = await axios.post(
      'https://searchconsole.googleapis.com/webmasters/v3/sites/' + encodeURIComponent(siteUrl) + '/searchAnalytics/query',
      {
        startDate,
        endDate,
        dimensions: ['query'],
        rowLimit: 10
      },
      {
        headers: {
          Authorization: `Bearer ${await getAccessTokenFromServiceAccount()}`,
          'Content-Type': 'application/json'
        }
      }
    )
    return response.data
  } catch (err) {
    console.warn('[GoogleAPI] Search Console erfordert Service Account:', err.message)
    return { rows: [], warning: 'Service Account erforderlich' }
  }
}

/**
 * Google OAuth2 Device Flow für Desktop Apps
 */
export async function startDeviceAuthFlow() {
  if (!GOOGLE_CLIENT_ID) throw new Error('GOOGLE_CLIENT_ID fehlt')

  const scope = encodeURIComponent(
    'https://www.googleapis.com/auth/content ' +
    'https://www.googleapis.com/auth/webmasters.readonly'
  )

  try {
    const response = await axios.post(
      'https://oauth2.googleapis.com/device/code',
      {
        client_id: GOOGLE_CLIENT_ID,
        scope
      },
      { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }
    )
    return response.data
  } catch (err) {
    console.error('[GoogleAPI] Device Auth Fehler:', err.response?.data || err.message)
    throw err
  }
}

// Platzhalter für Service Account Token (bei Bedarf implementieren)
async function getAccessTokenFromServiceAccount() {
  // Für Produktion: Service Account JSON laden und JWT Token generieren
  // Für jetzt: Warnung ausgeben
  throw new Error('Service Account Authentifizierung noch nicht konfiguriert')
}

export default {
  getGoogleAccessToken,
  getMerchantProducts,
  getSearchConsoleData,
  startDeviceAuthFlow
}
