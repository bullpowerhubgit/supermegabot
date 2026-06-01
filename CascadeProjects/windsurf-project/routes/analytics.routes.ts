/**
 * Analytics Routes with Proper Queue Responses
 * Handles GA4 and Klaviyo analytics endpoints with accurate status reporting
 */

import { Router } from 'express';
import AnalyticsService from '../services/analytics.service.js';
import KlaviyoService from '../services/klaviyo.service.js';

const router = Router();

// Initialize services
let analyticsService: AnalyticsService | null = null;
let klaviyoService: KlaviyoService | null = null;

try {
  analyticsService = new AnalyticsService();
  klaviyoService = new KlaviyoService();
} catch (error) {
  console.error('[Analytics Routes] Service initialization failed:', error);
}

/**
 * Middleware to check service availability
 */
const checkServices = (req: any, res: any, next: any) => {
  if (!analyticsService) {
    return res.status(503).json({
      success: false,
      error: 'Analytics service not available',
      details: 'GOOGLE_ANALYTICS_MEASUREMENT_ID or GOOGLE_ANALYTICS_API_SECRET not configured'
    });
  }
  next();
};

/**
 * GA4 Purchase Event
 * POST /api/analytics/purchase
 */
router.post('/purchase', checkServices, async (req, res) => {
  try {
    const { transaction_id, value, currency, items, coupon, shipping, tax } = req.body;

    // Validate required fields
    if (!transaction_id || value === undefined || !currency || !items) {
      return res.status(400).json({
        success: false,
        error: 'Missing required fields: transaction_id, value, currency, items'
      });
    }

    // Validate items array
    if (!Array.isArray(items) || items.length === 0) {
      return res.status(400).json({
        success: false,
        error: 'Items must be a non-empty array'
      });
    }

    const result = await analyticsService!.trackPurchase({
      transaction_id,
      value: Number(value),
      currency,
      items,
      coupon,
      shipping: shipping ? Number(shipping) : undefined,
      tax: tax ? Number(tax) : undefined,
    });

    // Return accurate queue status
    res.status(result.success ? 200 : 500).json({
      success: result.success,
      queued: result.queued,
      eventId: result.eventId,
      error: result.error,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error('[Analytics Routes] Purchase error:', error);
    res.status(500).json({
      success: false,
      queued: false,
      error: error instanceof Error ? error.message : 'Internal server error',
      timestamp: new Date().toISOString(),
    });
  }
});

/**
 * GA4 Custom Event
 * POST /api/analytics/event
 */
router.post('/event', checkServices, async (req, res) => {
  try {
    const { name, params } = req.body;

    if (!name) {
      return res.status(400).json({
        success: false,
        error: 'Event name is required'
      });
    }

    const result = await analyticsService!.trackEvent(name, params || {});

    // Return accurate queue status
    res.status(result.success ? 200 : 500).json({
      success: result.success,
      queued: result.queued,
      eventId: result.eventId,
      error: result.error,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error('[Analytics Routes] Event error:', error);
    res.status(500).json({
      success: false,
      queued: false,
      error: error instanceof Error ? error.message : 'Internal server error',
      timestamp: new Date().toISOString(),
    });
  }
});

/**
 * Klaviyo Event Tracking
 * POST /api/analytics/klaviyo/event
 */
router.post('/klaviyo/event', async (req, res) => {
  try {
    if (!klaviyoService) {
      return res.status(503).json({
        success: false,
        queued: false,
        error: 'Klaviyo service not available',
        details: 'KLAVIYO_PUBLIC_KEY or KLAVIYO_API_KEY not configured'
      });
    }

    const { event, profile, properties } = req.body;

    if (!event) {
      return res.status(400).json({
        success: false,
        queued: false,
        error: 'Event name is required'
      });
    }

    const result = await klaviyoService.trackEvent(event, profile, properties);

    // Return accurate queue status with retry count
    res.status(result.success ? 200 : 500).json({
      success: result.success,
      queued: result.queued,
      eventId: result.eventId,
      retryCount: result.retryCount,
      error: result.error,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error('[Analytics Routes] Klaviyo event error:', error);
    res.status(500).json({
      success: false,
      queued: false,
      error: error instanceof Error ? error.message : 'Internal server error',
      timestamp: new Date().toISOString(),
    });
  }
});

/**
 * Klaviyo Profile Management
 * POST /api/analytics/klaviyo/profile
 */
router.post('/klaviyo/profile', async (req, res) => {
  try {
    if (!klaviyoService) {
      return res.status(503).json({
        success: false,
        queued: false,
        error: 'Klaviyo service not available',
        details: 'KLAVIYO_PUBLIC_KEY or KLAVIYO_API_KEY not configured'
      });
    }

    const profile = req.body;

    if (!profile) {
      return res.status(400).json({
        success: false,
        queued: false,
        error: 'Profile data is required'
      });
    }

    const result = await klaviyoService.createOrUpdateProfile(profile);

    // Return accurate queue status with retry count
    res.status(result.success ? 200 : 500).json({
      success: result.success,
      queued: result.queued,
      eventId: result.eventId,
      retryCount: result.retryCount,
      error: result.error,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error('[Analytics Routes] Klaviyo profile error:', error);
    res.status(500).json({
      success: false,
      queued: false,
      error: error instanceof Error ? error.message : 'Internal server error',
      timestamp: new Date().toISOString(),
    });
  }
});

/**
 * Get Queue Status
 * GET /api/analytics/queue/status
 */
router.get('/queue/status', async (req, res) => {
  try {
    const status: any = {
      timestamp: new Date().toISOString(),
    };

    if (analyticsService) {
      status.ga4 = analyticsService.getQueueStatus();
    } else {
      status.ga4 = { error: 'Analytics service not available' };
    }

    if (klaviyoService) {
      status.klaviyo = klaviyoService.getQueueStatus();
    } else {
      status.klaviyo = { error: 'Klaviyo service not available' };
    }

    res.json({
      success: true,
      status,
    });
  } catch (error) {
    console.error('[Analytics Routes] Queue status error:', error);
    res.status(500).json({
      success: false,
      error: error instanceof Error ? error.message : 'Internal server error',
    });
  }
});

/**
 * Health Check
 * GET /api/analytics/health
 */
router.get('/health', async (req, res) => {
  try {
    const health: any = {
      timestamp: new Date().toISOString(),
      services: {},
    };

    if (analyticsService) {
      health.services.ga4 = await analyticsService.healthCheck();
    } else {
      health.services.ga4 = { status: 'unavailable', error: 'Service not initialized' };
    }

    if (klaviyoService) {
      health.services.klaviyo = await klaviyoService.healthCheck();
    } else {
      health.services.klaviyo = { status: 'unavailable', error: 'Service not initialized' };
    }

    const allHealthy = Object.values(health.services).every((service: any) => 
      service.status === 'healthy' || service.status === 'unavailable'
    );

    res.status(allHealthy ? 200 : 503).json({
      success: allHealthy,
      health,
    });
  } catch (error) {
    console.error('[Analytics Routes] Health check error:', error);
    res.status(500).json({
      success: false,
      error: error instanceof Error ? error.message : 'Internal server error',
    });
  }
});

/**
 * Process Queues Manually (for testing/debugging)
 * POST /api/analytics/queue/process
 */
router.post('/queue/process', async (req, res) => {
  try {
    // This would trigger manual queue processing if needed
    // For now, just return current status
    const status: any = {
      timestamp: new Date().toISOString(),
      message: 'Queue processing is automatic. Use GET /queue/status to check current state.',
    };

    if (analyticsService) {
      status.ga4 = analyticsService.getQueueStatus();
    }

    if (klaviyoService) {
      status.klaviyo = klaviyoService.getQueueStatus();
    }

    res.json({
      success: true,
      status,
    });
  } catch (error) {
    console.error('[Analytics Routes] Manual queue processing error:', error);
    res.status(500).json({
      success: false,
      error: error instanceof Error ? error.message : 'Internal server error',
    });
  }
});

export default router;
