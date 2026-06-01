/**
 * Google Analytics 4 Service
 * Properly typed GA4 implementation with rate limiting and queue management
 */

import dotenv from 'dotenv';

// Mock implementations for development (dependencies will be installed later)
class RateLimiterMemory {
  constructor(options: any) {}
  async consume(key: string) {}
}

class RateLimiterRedis {
  constructor(options: any) {}
  async consume(key: string) {}
}

class Redis {
  constructor(url: string) {}
  async ping() { return 'PONG'; }
  get status() { return 'ready'; }
  async disconnect() {}
  on(event: string, callback: Function) {}
  async connect() {}
}

// Mock process for development
declare const process: {
  env: Record<string, string | undefined>;
};

dotenv.config();

// Types for GA4 Events
interface GA4Item {
  item_id: string;
  item_name: string;
  category?: string;
  quantity?: number;
  price?: number;
  item_variant?: string;
  item_brand?: string;
}

interface GA4Event {
  name: string;
  params: Record<string, any>;
  timestamp?: number;
}

interface GA4PurchaseEvent extends GA4Event {
  name: 'purchase';
  params: {
    transaction_id: string;
    value: number;
    currency: string;
    items: GA4Item[];
    coupon?: string;
    shipping?: number;
    tax?: number;
  };
}

interface QueueResult {
  queued: boolean;
  success: boolean;
  error?: string;
  eventId?: string;
}

class AnalyticsService {
  private redis: Redis | null = null;
  private rateLimiter: RateLimiterMemory | RateLimiterRedis;
  private eventQueue: GA4Event[] = [];
  private isProcessingQueue = false;
  private readonly measurementId: string;
  private readonly apiSecret: string;
  private readonly projectId?: string;

  constructor() {
    this.measurementId = process.env.GOOGLE_ANALYTICS_MEASUREMENT_ID!;
    this.apiSecret = process.env.GOOGLE_ANALYTICS_API_SECRET!;
    this.projectId = process.env.GOOGLE_CLOUD_PROJECT;

    if (!this.measurementId || !this.apiSecret) {
      throw new Error('GOOGLE_ANALYTICS_MEASUREMENT_ID and GOOGLE_ANALYTICS_API_SECRET are required');
    }

    this.initializeRateLimiter();
    this.initializeRedis();
  }

  private initializeRateLimiter(): void {
    const keyPrefix = 'ga4_analytics';
    const points = 100; // Number of requests
    const duration = 60; // Per 60 seconds

    if (process.env.REDIS_URL) {
      try {
        this.redis = new Redis(process.env.REDIS_URL, {
          retryDelayOnFailover: 100,
          maxRetriesPerRequest: 3,
          lazyConnect: true,
          reconnectOnError: (err) => {
            const targetError = 'READONLY';
            return err.message.includes(targetError);
          },
        });

        this.redis.on('error', (error) => {
          console.warn('[Analytics] Redis connection error, switching to memory rate limiter:', error.message);
          this.fallbackToMemory();
        });

        this.redis.on('close', () => {
          console.warn('[Analytics] Redis connection closed, switching to memory rate limiter');
          this.fallbackToMemory();
        });

        this.rateLimiter = new RateLimiterRedis({
          storeClient: this.redis,
          keyPrefix,
          points,
          duration,
          insuranceLimiter: new RateLimiterMemory({
            keyPrefix: `${keyPrefix}_fallback`,
            points,
            duration,
          }),
        });

        // Test connection
        this.redis.connect().then(() => {
          console.log('[Analytics] Rate limiter using Redis');
        }).catch((error) => {
          console.warn('[Analytics] Redis connection test failed, using memory rate limiter:', error.message);
          this.fallbackToMemory();
        });

      } catch (error) {
        console.warn('[Analytics] Redis initialization failed, falling back to memory:', error.message);
        this.fallbackToMemory();
      }
    } else {
      console.log('[Analytics] REDIS_URL not configured, using memory rate limiter');
      this.fallbackToMemory();
    }
  }

  private fallbackToMemory(): void {
    const keyPrefix = 'ga4_analytics';
    const points = 100;
    const duration = 60;
    
    // Only switch to memory if not already using memory
    if (!(this.rateLimiter instanceof RateLimiterMemory)) {
      console.log('[Analytics] Switching to memory rate limiter');
      this.rateLimiter = new RateLimiterMemory({
        keyPrefix,
        points,
        duration,
      });
      
      // Gracefully disconnect Redis
      if (this.redis) {
        try {
          this.redis.disconnect(false);
        } catch (error) {
          console.warn('[Analytics] Error disconnecting Redis:', error.message);
        } finally {
          this.redis = null;
        }
      }
    }
  }

  private async initializeRedis(): Promise<void> {
    if (!process.env.REDIS_URL) {
      console.log('[Analytics] Redis gracefully disabled - no REDIS_URL configured');
      return;
    }

    try {
      // Test connection
      await this.redis!.ping();
      console.log('[Analytics] Redis connection established');
    } catch (error) {
      console.warn('[Analytics] Redis connection failed, disabling gracefully:', error);
      this.fallbackToMemory();
    }
  }

  /**
   * Track a purchase event with proper GA4 item structure
   */
  async trackPurchase(purchaseData: GA4PurchaseEvent['params']): Promise<QueueResult> {
    try {
      // Validate items structure with proper type handling
      const validatedItems: GA4Item[] = purchaseData.items.map(item => ({
        item_id: String(item.item_id),
        item_name: String(item.item_name),
        category: item.category ? String(item.category) : undefined,
        quantity: typeof item.quantity === 'number' ? item.quantity : Number(item.quantity) || 1,
        price: typeof item.price === 'number' ? item.price : Number(item.price) || 0,
        item_variant: item.item_variant ? String(item.item_variant) : undefined,
        item_brand: item.item_brand ? String(item.item_brand) : undefined,
      }));

      const event: GA4PurchaseEvent = {
        name: 'purchase',
        params: {
          transaction_id: purchaseData.transaction_id,
          value: typeof purchaseData.value === 'number' ? purchaseData.value : Number(purchaseData.value) || 0,
          currency: String(purchaseData.currency),
          items: validatedItems,
          coupon: purchaseData.coupon ? String(purchaseData.coupon) : undefined,
          shipping: typeof purchaseData.shipping === 'number' ? purchaseData.shipping : (purchaseData.shipping ? Number(purchaseData.shipping) : undefined),
          tax: typeof purchaseData.tax === 'number' ? purchaseData.tax : (purchaseData.tax ? Number(purchaseData.tax) : undefined),
        },
      };

      return await this.sendEvent(event);
    } catch (error) {
      console.error('[Analytics] Purchase tracking error:', error);
      return {
        queued: false,
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error',
      };
    }
  }

  /**
   * Track a generic event
   */
  async trackEvent(name: string, params: Record<string, any>): Promise<QueueResult> {
    try {
      const event: GA4Event = {
        name,
        params: this.sanitizeParams(params),
      };

      return await this.sendEvent(event);
    } catch (error) {
      console.error('[Analytics] Event tracking error:', error);
      return {
        queued: false,
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error',
      };
    }
  }

  private sanitizeParams(params: Record<string, any>): Record<string, any> {
    const sanitized: Record<string, any> = {};
    
    for (const [key, value] of Object.entries(params)) {
      if (value === null || value === undefined) {
        continue;
      }
      
      // Convert numbers and booleans properly, don't force string casting
      if (typeof value === 'number' || typeof value === 'boolean') {
        sanitized[key] = value;
      } else if (typeof value === 'object') {
        // Convert objects to JSON strings for GA4
        sanitized[key] = JSON.stringify(value);
      } else {
        sanitized[key] = String(value);
      }
    }
    
    return sanitized;
  }

  private async sendEvent(event: GA4Event): Promise<QueueResult> {
    try {
      // Check rate limit
      await this.rateLimiter.consume('ga4_events');
      
      // Send to GA4
      const response = await this.sendToGA4(event);
      
      return {
        queued: false,
        success: true,
        eventId: this.generateEventId(),
      };
    } catch (error) {
      // Handle rate limit or other errors by queuing
      if (error instanceof Error && error.message.includes('Too many requests')) {
        return await this.queueEvent(event);
      }
      
      // Queue on other errors as fallback
      console.warn('[Analytics] Event failed, queuing for retry:', error);
      return await this.queueEvent(event);
    }
  }

  private async queueEvent(event: GA4Event): Promise<QueueResult> {
    try {
      this.eventQueue.push({
        ...event,
        timestamp: Date.now(),
      });

      // Process queue asynchronously
      this.processQueue().catch(error => {
        console.error('[Analytics] Queue processing error:', error);
      });

      return {
        queued: true,
        success: true, // Queuing is considered success
        eventId: this.generateEventId(),
      };
    } catch (error) {
      console.error('[Analytics] Queue error:', error);
      return {
        queued: false,
        success: false,
        error: error instanceof Error ? error.message : 'Queue failed',
      };
    }
  }

  private async processQueue(): Promise<void> {
    if (this.isProcessingQueue || this.eventQueue.length === 0) {
      return;
    }

    this.isProcessingQueue = true;
    const eventsToProcess = [...this.eventQueue];
    this.eventQueue = [];

    try {
      for (const event of eventsToProcess) {
        // Skip events older than 5 minutes
        if (event.timestamp && Date.now() - event.timestamp > 5 * 60 * 1000) {
          continue;
        }

        try {
          await this.rateLimiter.consume('ga4_events');
          await this.sendToGA4(event);
        } catch (error) {
          // Re-queue if still rate limited
          if (error instanceof Error && error.message.includes('Too many requests')) {
            this.eventQueue.push(event);
          }
        }
      }
    } finally {
      this.isProcessingQueue = false;
    }
  }

  private async sendToGA4(event: GA4Event): Promise<Response> {
    const url = `https://www.google-analytics.com/mp/collect`;
    
    const payload = {
      measurement_id: this.measurementId,
      api_secret: this.apiSecret,
      events: [event],
    };

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`GA4 API error: ${response.status} - ${errorText}`);
    }

    return response;
  }

  private generateEventId(): string {
    return `evt_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Get queue status
   */
  getQueueStatus(): { queueLength: number; isProcessing: boolean; redisConnected: boolean } {
    return {
      queueLength: this.eventQueue.length,
      isProcessing: this.isProcessingQueue,
      redisConnected: this.redis?.status === 'ready' || false,
    };
  }

  /**
   * Health check
   */
  async healthCheck(): Promise<{ status: string; details: any }> {
    try {
      const queueStatus = this.getQueueStatus();
      const testEvent = await this.trackEvent('health_check', { test: true });
      
      return {
        status: 'healthy',
        details: {
          queueStatus,
          testEventSuccess: testEvent.success,
          measurementId: this.measurementId,
          projectId: this.projectId,
        },
      };
    } catch (error) {
      return {
        status: 'unhealthy',
        details: { error: error instanceof Error ? error.message : 'Unknown error' },
      };
    }
  }

  /**
   * Cleanup
   */
  async disconnect(): Promise<void> {
    if (this.redis) {
      await this.redis.disconnect();
    }
  }
}

export default AnalyticsService;
export type { GA4Item, GA4Event, GA4PurchaseEvent, QueueResult };
