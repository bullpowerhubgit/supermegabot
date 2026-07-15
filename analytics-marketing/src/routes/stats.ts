import { Router, Request, Response } from 'express'
import { cacheGet, cacheSet } from '../lib/redis'
import { register } from '../lib/metrics'
const router = Router()
router.get('/analytics/stats', async (_req: Request, res: Response) => {
  const cached = await cacheGet<object>('stats:overview')
  if (cached) return res.json(cached)
  const stats = { service: 'analytics-marketing-service', timestamp: new Date().toISOString(), uptime: process.uptime(),
    endpoints: { analytics: ['/track/google-analytics', '/track/mixpanel', '/track/plausible'],
      marketing: ['/marketing/klaviyo/subscribe', '/marketing/klaviyo/event', '/marketing/mailchimp/subscribe'] } }
  await cacheSet('stats:overview', stats, 60)
  return res.json(stats)
})
router.get('/metrics', async (_req: Request, res: Response) => {
  res.set('Content-Type', register.contentType)
  res.end(await register.metrics())
})
export default router
