// ============================================
// RUDIBOT GLOBAL RATE LIMITING
// Production-grade rate limiting by plan
// ============================================

import rateLimit from 'express-rate-limit';
import { Request, Response } from 'express';

// Plan-based rate limit configs
const PLAN_LIMITS: Record<string, { windowMs: number; max: number }> = {
  free: { windowMs: 15 * 60 * 1000, max: 100 },
  starter: { windowMs: 15 * 60 * 1000, max: 1000 },
  pro: { windowMs: 15 * 60 * 1000, max: 10000 },
  enterprise: { windowMs: 15 * 60 * 1000, max: 100000 },
};

export const createRateLimiter = (plan: string = 'free') => {
  const config = PLAN_LIMITS[plan] || PLAN_LIMITS.free;
  return rateLimit({
    windowMs: config.windowMs,
    max: config.max,
    standardHeaders: true,
    legacyHeaders: false,
    keyGenerator: (req: Request) => {
      return (req as any).user?.id || req.ip || 'unknown';
    },
    handler: (req: Request, res: Response) => {
      res.status(429).json({
        error: 'Too Many Requests',
        retryAfter: Math.ceil(config.windowMs / 1000),
        plan,
        limit: config.max,
      });
    },
  });
};

// Strict limiter for auth endpoints (login, register)
export const authRateLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 5,
  standardHeaders: true,
  legacyHeaders: false,
  skipSuccessfulRequests: true,
  message: { error: 'Too many auth attempts. Please try again later.' },
});

// Default limiter for all routes
export const defaultRateLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 1000,
  standardHeaders: true,
  legacyHeaders: false,
});
