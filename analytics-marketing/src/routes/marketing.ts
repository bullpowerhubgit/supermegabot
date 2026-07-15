import { Router, Request, Response } from 'express'
import axios from 'axios'
import { marketingEmailsTotal } from '../lib/metrics'
const router = Router()
router.post('/marketing/klaviyo/subscribe', async (req: Request, res: Response) => {
  try {
    const { email, firstName, lastName, listId, properties } = req.body
    const apiKey = process.env.KLAVIYO_API_KEY
    if (!apiKey) return res.status(503).json({ error: 'Klaviyo not configured' })
    await axios.post('https://a.klaviyo.com/api/profiles/',
      { data: { type: 'profile', attributes: { email, first_name: firstName || '', last_name: lastName || '', properties: properties || {} } } },
      { headers: { 'Authorization': `Klaviyo-API-Key ${apiKey}`, 'revision': '2024-02-15', 'Content-Type': 'application/json' } })
    if (listId) {
      await axios.post(`https://a.klaviyo.com/api/lists/${listId}/relationships/profiles/`,
        { data: [{ type: 'profile', attributes: { email } }] },
        { headers: { 'Authorization': `Klaviyo-API-Key ${apiKey}`, 'revision': '2024-02-15', 'Content-Type': 'application/json' } })
    }
    marketingEmailsTotal.inc({ provider: 'klaviyo', type: 'subscribe' })
    return res.json({ ok: true, provider: 'klaviyo', email })
  } catch (err: unknown) { return res.status(500).json({ error: err instanceof Error ? err.message : 'error' }) }
})
router.post('/marketing/klaviyo/event', async (req: Request, res: Response) => {
  try {
    const { email, eventName, properties } = req.body
    const apiKey = process.env.KLAVIYO_API_KEY
    if (!apiKey) return res.status(503).json({ error: 'Klaviyo not configured' })
    await axios.post('https://a.klaviyo.com/api/events/',
      { data: { type: 'event', attributes: {
        metric: { data: { type: 'metric', attributes: { name: eventName } } },
        profile: { data: { type: 'profile', attributes: { email } } },
        properties: properties || {} }}},
      { headers: { 'Authorization': `Klaviyo-API-Key ${apiKey}`, 'revision': '2024-02-15', 'Content-Type': 'application/json' } })
    marketingEmailsTotal.inc({ provider: 'klaviyo', type: eventName })
    return res.json({ ok: true, provider: 'klaviyo', event: eventName })
  } catch (err: unknown) { return res.status(500).json({ error: err instanceof Error ? err.message : 'error' }) }
})
router.post('/marketing/mailchimp/subscribe', async (req: Request, res: Response) => {
  try {
    const { email, firstName, lastName, listId, tags } = req.body
    const apiKey = process.env.MAILCHIMP_API_KEY
    const serverPrefix = process.env.MAILCHIMP_SERVER_PREFIX
    const audienceId = listId || process.env.MAILCHIMP_AUDIENCE_ID
    if (!apiKey || !serverPrefix) return res.status(503).json({ error: 'Mailchimp not configured' })
    if (!audienceId) return res.status(400).json({ error: 'listId required' })
    await axios.post(`https://${serverPrefix}.api.mailchimp.com/3.0/lists/${audienceId}/members`,
      { email_address: email, status: 'subscribed', merge_fields: { FNAME: firstName || '', LNAME: lastName || '' }, tags: tags || [] },
      { auth: { username: 'anystring', password: apiKey } })
    marketingEmailsTotal.inc({ provider: 'mailchimp', type: 'subscribe' })
    return res.json({ ok: true, provider: 'mailchimp', email })
  } catch (err: unknown) { return res.status(500).json({ error: err instanceof Error ? err.message : 'error' }) }
})
export default router
