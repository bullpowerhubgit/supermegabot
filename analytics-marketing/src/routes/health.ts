import { Router, Request, Response } from 'express'
import redisClient from '../lib/redis'
const router = Router()
router.get('/health', async (_req: Request, res: Response) => {
  res.json({ status: 'ok', service: 'analytics-marketing-service',
    timestamp: new Date().toISOString(),
    redis: redisClient.isOpen ? 'connected' : 'disconnected',
    uptime: process.uptime() })
})
export default router
