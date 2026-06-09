import { Request, Response, NextFunction } from 'express';

interface PlanLimits {
  max_shops: number;
  max_products: number;
  max_api_calls_daily: number;
  features: string[];
}

const PLAN_LIMITS: Record<string, PlanLimits> = {
  free: {
    max_shops: 1,
    max_products: 100,
    max_api_calls_daily: 1000,
    features: ['basic_chat', 'health_check']
  },
  starter: {
    max_shops: 3,
    max_products: 1000,
    max_api_calls_daily: 10000,
    features: ['basic_chat', 'health_check', 'shopify_sync', 'email_automation']
  },
  pro: {
    max_shops: 10,
    max_products: 10000,
    max_api_calls_daily: 100000,
    features: ['basic_chat', 'health_check', 'shopify_sync', 'email_automation', 'ai_assistant', 'webhook_automation']
  },
  enterprise: {
    max_shops: 999,
    max_products: 999999,
    max_api_calls_daily: 999999,
    features: ['*'] // all features
  }
};

export async function checkPlanLimits(req: Request, res: Response, next: NextFunction) {
  try {
    if (!req.user) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    const userPlan = req.user.role || 'free';
    const limits = PLAN_LIMITS[userPlan];

    if (!limits) {
      return res.status(403).json({ error: 'Invalid plan' });
    }

    // Check today's API usage
    const today = new Date().toISOString().split('T')[0];
    const { data: usage } = await req.supabase
      .from('usage_daily')
      .select('api_calls')
      .eq('user_id', req.user.id)
      .eq('date', today)
      .single();

    const currentCalls = usage?.api_calls || 0;

    if (currentCalls >= limits.max_api_calls_daily) {
      return res.status(429).json({
        error: 'Rate limit exceeded',
        message: `Daily API limit reached for ${userPlan} plan (${limits.max_api_calls_daily} calls)`,
        upgrade_url: '/api/billing/upgrade'
      });
    }

    // Increment usage (fire and forget)
    req.supabase.from('usage_daily').upsert({
      user_id: req.user.id,
      date: today,
      api_calls: currentCalls + 1,
    }, { onConflict: 'user_id,date' }).then(() => {});

    // Attach limits to request
    (req as any).planLimits = limits;

    next();
  } catch (err) {
    return res.status(500).json({ error: 'Billing check failed', message: (err as Error).message });
  }
}

export function requireFeature(feature: string) {
  return (req: Request, res: Response, next: NextFunction) => {
    if (!req.user) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    const limits = (req as any).planLimits || PLAN_LIMITS[req.user.role || 'free'];

    const hasFeature = limits.features.includes('*') || limits.features.includes(feature);

    if (!hasFeature) {
      return res.status(403).json({
        error: 'Feature not available',
        message: `Feature "${feature}" requires a higher plan. Current: ${req.user.role}`,
        upgrade_url: '/api/billing/upgrade'
      });
    }

    next();
  };
}

export async function getBillingInfo(req: Request, res: Response) {
  try {
    if (!req.user) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    const userPlan = req.user.role || 'free';
    const limits = PLAN_LIMITS[userPlan];

    const today = new Date().toISOString().split('T')[0];
    const { data: usage } = await req.supabase
      .from('usage_daily')
      .select('api_calls, shop_syncs, emails_sent')
      .eq('user_id', req.user.id)
      .eq('date', today)
      .single();

    res.json({
      plan: userPlan,
      limits,
      usage_today: usage || { api_calls: 0, shop_syncs: 0, emails_sent: 0 },
      upgrade_options: ['starter', 'pro', 'enterprise'].filter(p => p !== userPlan)
    });
  } catch (err) {
    res.status(500).json({ error: (err as Error).message });
  }
}
