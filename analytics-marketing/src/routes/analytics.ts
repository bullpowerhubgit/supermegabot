import { Router, Request, Response } from 'express'
import axios from 'axios'
import { analyticsEventsTotal } from '../lib/metrics'
const router = Router()
router.post('/track/google-analytics', async (req: Request, res: Response) => {
  try {
    const { userId, eventName, eventParams } = req.body
    const measurementId = process.env.GOOGLE_ANALYTICS_MEASUREMENT_ID
    const apiSecret = process.env.GOOGLE_ANALYTICS_API_SECRET
    if (!measurementId || !apiSecret) return res.status(503).json({ error: 'GA not configured' })
    await axios.post(`https://www.google-analytics.com/mp/collect?measurement_id=${measurementId}&api_secret=${apiSecret}`,
      { client_id: userId || 'anonymous', events: [{ name: eventName, params: eventParams || {} }] })
    analyticsEventsTotal.inc({ provider: 'google_analytics', event: eventName })
    return res.json({ ok: true, provider: 'google_analytics', event: eventName })
  } catch (err: unknown) { return res.status(500).json({ error: err instanceof Error ? err.message : 'error' }) }
})
router.post('/track/mixpanel', async (req: Request, res: Response) => {
  try {
    const { distinctId, eventName, properties } = req.body
    const token = process.env.MIXPANEL_TOKEN
    if (!token) return res.status(503).json({ error: 'Mixpanel not configured' })
    const data = Buffer.from(JSON.stringify({ event: eventName, properties: { token, distinct_id: distinctId, ...properties } })).toString('base64')
    await axios.post(`https://api.mixpanel.com/track?data=${data}`)
    analyticsEventsTotal.inc({ provider: 'mixpanel', event: eventName })
    return res.json({ ok: true, provider: 'mixpanel', event: eventName })
  } catch (err: unknown) { return res.status(500).json({ error: err instanceof Error ? err.message : 'error' }) }
})
router.post('/track/plausible', async (req: Request, res: Response) => {
  try {
    const { domain, eventName, url, props } = req.body
    const plausibleDomain = domain || process.env.PLAUSIBLE_DOMAIN
    if (!plausibleDomain) return res.status(503).json({ error: 'Plausible not configured' })
    await axios.post('https://plausible.io/api/event', { name: eventName, url, domain: plausibleDomain, props: props || {} },
      { headers: { 'User-Agent': 'shopify-bot/1.0', 'Content-Type': 'application/json' } })
    analyticsEventsTotal.inc({ provider: 'plausible', event: eventName })
    return res.json({ ok: true, provider: 'plausible', event: eventName })
  } catch (err: unknown) { return res.status(500).json({ error: err instanceof Error ? err.message : 'error' }) }
})
export default router
