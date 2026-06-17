// ============================================
// RUDIBOT API VERSION PINNING
// Ensures backward compatibility
// ============================================

import { Request, Response, NextFunction } from 'express';

export const API_VERSIONS = {
  v1: {
    deprecated: false,
    sunset: null,
    features: ['basic_chat', 'shopify_sync', 'email_send'],
  },
  v2: {
    deprecated: false,
    sunset: null,
    features: ['all_v1', 'browser_automation', 'ai_assistant', 'webhook_automation'],
  },
};

export function apiVersionMiddleware(req: Request, res: Response, next: NextFunction) {
  const version = req.params.version || 'v1';
  
  if (!API_VERSIONS[version as keyof typeof API_VERSIONS]) {
    return res.status(400).json({
      error: 'Invalid API version',
      validVersions: Object.keys(API_VERSIONS),
      latest: 'v2',
    });
  }

  (req as any).apiVersion = version;
  next();
}

export function versionedRoute(path: string, router: any) {
  return [`/api/v1${path}`, `/api/v2${path}`];
}
