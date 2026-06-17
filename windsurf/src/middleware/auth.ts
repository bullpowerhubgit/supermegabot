import { Request, Response, NextFunction } from 'express';
import { createClient, SupabaseClient } from '@supabase/supabase-js';

// Extend Express Request type
declare global {
  namespace Express {
    interface Request {
      user?: {
        id: string;
        email: string;
        role: 'free' | 'starter' | 'pro' | 'enterprise';
        shop_id?: string;
      };
      supabase: SupabaseClient;
    }
  }
}

const supabaseUrl = process.env.SUPABASE_URL || '';
const supabaseServiceKey = process.env.SUPABASE_SERVICE_KEY || '';

export function createSupabaseClient() {
  return createClient(supabaseUrl, supabaseServiceKey, {
    auth: { autoRefreshToken: false, persistSession: false }
  });
}

export async function requireAuth(req: Request, res: Response, next: NextFunction) {
  try {
    const authHeader = req.headers.authorization;
    if (!authHeader) {
      return res.status(401).json({ error: 'Unauthorized', message: 'Missing Authorization header' });
    }

    const token = authHeader.replace('Bearer ', '');
    const supabase = createSupabaseClient();

    const { data: { user }, error } = await supabase.auth.getUser(token);

    if (error || !user) {
      return res.status(401).json({ error: 'Unauthorized', message: 'Invalid or expired token' });
    }

    // Fetch user profile with plan info
    const { data: profile } = await supabase
      .from('users')
      .select('role, shop_id')
      .eq('id', user.id)
      .single();

    req.user = {
      id: user.id,
      email: user.email || '',
      role: profile?.role || 'free',
      shop_id: profile?.shop_id,
    };
    req.supabase = supabase;

    next();
  } catch (err) {
    return res.status(500).json({ error: 'Auth error', message: (err as Error).message });
  }
}

export function requireRole(allowedRoles: string[]) {
  return (req: Request, res: Response, next: NextFunction) => {
    if (!req.user) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    if (!allowedRoles.includes(req.user.role)) {
      return res.status(403).json({
        error: 'Forbidden',
        message: `Requires role: ${allowedRoles.join(' or ')}. Current: ${req.user.role}`
      });
    }

    next();
  };
}

export function requireAuthOrApiKey(req: Request, res: Response, next: NextFunction) {
  // Check for API key in x-api-key header
  const apiKey = req.headers['x-api-key'] as string;
  if (apiKey && apiKey === process.env.API_GATEWAY_KEY) {
    req.user = {
      id: 'api-gateway',
      email: 'system@rudibot.com',
      role: 'enterprise',
    };
    req.supabase = createSupabaseClient();
    return next();
  }

  // Otherwise require normal auth
  requireAuth(req, res, next);
}
