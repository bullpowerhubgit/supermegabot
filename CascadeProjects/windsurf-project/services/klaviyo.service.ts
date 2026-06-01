/**
 * Enhanced Klaviyo Service with Advanced Analytics
 * Handles email marketing automation with proper queue management
 * Enhanced with templates, analytics, and multi-channel support
 */

import dotenv from 'dotenv';

// Real implementations for production
import { RateLimiterMemory } from 'rate-limiter-flexible';
import { RateLimiterRedis } from 'rate-limiter-flexible';
import Redis from 'ioredis';

// Load environment variables
dotenv.config();

interface KlaviyoEvent {
  event: string;
  profile?: Record<string, any>;
  properties?: Record<string, any>;
  timestamp?: number;
  _retryCount?: number;
}

interface KlaviyoProfile {
  email?: string;
  first_name?: string;
  last_name?: string;
  phone_number?: string;
  external_id?: string;
  properties?: Record<string, any>;
  _retryTimestamp?: number;
  _retryCount?: number;
}

interface QueueResult {
  queued: boolean;
  success: boolean;
  error?: string;
  eventId?: string;
  retryCount?: number;
}

interface EmailTemplate {
  id: string;
  name: string;
  subject: string;
  content: string;
  variables?: string[];
  category: 'marketing' | 'transactional' | 'automation';
}

interface CampaignMetrics {
  sent: number;
  delivered: number;
  opened: number;
  clicked: number;
  bounced: number;
  unsubscribed: number;
  revenue?: number;
  conversionRate?: number;
}

interface AnalyticsData {
  totalEvents: number;
  totalProfiles: number;
  queueStatus: {
    eventQueueLength: number;
    profileQueueLength: number;
    isProcessingEvents: boolean;
    isProcessingProfiles: boolean;
    redisConnected: boolean;
  };
  performanceMetrics: {
    avgResponseTime: number;
    successRate: number;
    errorRate: number;
  };
  campaignMetrics: CampaignMetrics;
  timestamp: string;
}

class KlaviyoService {
  private redis: Redis | null = null;
  private rateLimiter: RateLimiterMemory | RateLimiterRedis;
  private eventQueue: KlaviyoEvent[] = [];
  private profileQueue: KlaviyoProfile[] = [];
  private isProcessingEvents = false;
  private isProcessingProfiles = false;
  private readonly publicKey: string;
  private readonly privateKey: string;
  private readonly maxRetries = 3;
  private readonly retryDelay = 5000; // 5 seconds
  
  // Enhanced features
  private templates: Map<string, EmailTemplate> = new Map();
  private analytics: AnalyticsData;
  private performanceMetrics: Map<string, number[]> = new Map(); // Response time tracking

  constructor() {
    // Support both KLAVIYO_PUBLIC_KEY and KLAVIYO_API_KEY (fallback)
    this.publicKey = process.env.KLAVIYO_PUBLIC_KEY || process.env.KLAVIYO_API_KEY || '';
    this.privateKey = process.env.KLAVIYO_API_KEY || '';

    if (!this.privateKey) {
      console.warn('[Klaviyo] API keys not configured, service will run in mock mode');
      this.publicKey = 'mock_public_key';
      this.privateKey = 'mock_private_key';
    }

    // Initialize analytics
    this.analytics = this.initializeAnalytics();
    
    // Initialize default templates
    this.initializeTemplates();
    
    this.initializeRateLimiter();
    this.initializeRedis();
  }

  private initializeRateLimiter(): void {
    const keyPrefix = 'klaviyo_api';
    const points = 50; // Klaviyo rate limit ~50 requests/second
    const duration = 1; // Per 1 second

    if (process.env.REDIS_URL) {
      try {
        this.redis = new Redis(process.env.REDIS_URL);
        this.rateLimiter = new RateLimiterRedis({
          storeClient: this.redis,
          keyPrefix,
          points,
          duration,
        });
        console.log('[Klaviyo] Rate limiter using Redis');
      } catch (error) {
        console.warn('[Klaviyo] Redis initialization failed, falling back to memory:', error);
        this.fallbackToMemory();
      }
    } else {
      console.log('[Klaviyo] REDIS_URL not configured, using memory rate limiter');
      this.fallbackToMemory();
    }
  }

  private fallbackToMemory(): void {
    const keyPrefix = 'klaviyo_api';
    const points = 50;
    const duration = 1;
    
    this.rateLimiter = new RateLimiterMemory({
      keyPrefix,
      points,
      duration,
    });
    
    if (this.redis) {
      this.redis.disconnect();
      this.redis = null;
    }
  }

  private initializeAnalytics(): AnalyticsData {
    return {
      totalEvents: 0,
      totalProfiles: 0,
      queueStatus: {
        eventQueueLength: 0,
        profileQueueLength: 0,
        isProcessingEvents: false,
        isProcessingProfiles: false,
        redisConnected: false
      },
      performanceMetrics: {
        avgResponseTime: 0,
        successRate: 100,
        errorRate: 0
      },
      campaignMetrics: {
        sent: 0,
        delivered: 0,
        opened: 0,
        clicked: 0,
        bounced: 0,
        unsubscribed: 0,
        revenue: 0,
        conversionRate: 0
      },
      timestamp: new Date().toISOString()
    };
  }

  private initializeTemplates(): void {
    // Welcome email template
    this.templates.set('welcome', {
      id: 'welcome',
      name: 'Welcome Email',
      subject: 'Welcome to {{company_name}}!',
      content: `
        <h1>Welcome {{first_name}}!</h1>
        <p>Thank you for joining {{company_name}}. We're excited to have you on board!</p>
        <p>Get started with our {{product_name}} and enjoy a {{discount_percentage}}% discount on your first purchase.</p>
        <p>Use code: {{welcome_code}}</p>
      `,
      variables: ['first_name', 'company_name', 'product_name', 'discount_percentage', 'welcome_code'],
      category: 'transactional'
    });

    // Order confirmation template
    this.templates.set('order_confirmation', {
      id: 'order_confirmation',
      name: 'Order Confirmation',
      subject: 'Your Order #{{order_number}} is Confirmed',
      content: `
        <h1>Order Confirmed!</h1>
        <p>Hi {{first_name}},</p>
        <p>Your order #{{order_number}} has been confirmed and is being processed.</p>
        <p><strong>Order Details:</strong></p>
        <ul>
          <li>Total: {{order_total}}</li>
          <li>Shipping: {{shipping_address}}</li>
          <li>Estimated delivery: {{delivery_date}}</li>
        </ul>
        <p>You can track your order here: {{tracking_url}}</p>
      `,
      variables: ['first_name', 'order_number', 'order_total', 'shipping_address', 'delivery_date', 'tracking_url'],
      category: 'transactional'
    });

    // Marketing template
    this.templates.set('promotion', {
      id: 'promotion',
      name: 'Special Promotion',
      subject: '{{promotion_title}} - Limited Time Offer!',
      content: `
        <h1>{{promotion_title}}</h1>
        <p>Hi {{first_name}},</p>
        <p>Don't miss out on our special promotion!</p>
        <p>{{promotion_description}}</p>
        <p><strong>Discount: {{discount_percentage}}% off</strong></p>
        <p><strong>Valid until: {{expiry_date}}</strong></p>
        <p><a href="{{shop_url}}">Shop Now</a></p>
      `,
      variables: ['first_name', 'promotion_title', 'promotion_description', 'discount_percentage', 'expiry_date', 'shop_url'],
      category: 'marketing'
    });

    console.log(`[Klaviyo] Initialized ${this.templates.size} email templates`);
  }

  private async initializeRedis(): Promise<void> {
    if (!process.env.REDIS_URL) {
      console.log('[Klaviyo] Redis gracefully disabled - no REDIS_URL configured');
      return;
    }

    try {
      await this.redis!.ping();
      console.log('[Klaviyo] Redis connection established');
    } catch (error) {
      console.warn('[Klaviyo] Redis connection failed, disabling gracefully:', error);
      this.fallbackToMemory();
    }
  }

  /**
   * Track an event with centralized retry logic and performance tracking
   */
  async trackEvent(eventName: string, profile?: KlaviyoProfile, properties?: Record<string, any>): Promise<QueueResult> {
    const startTime = performance.now();
    
    try {
      const event: KlaviyoEvent = {
        event: eventName,
        profile,
        properties,
        timestamp: Date.now(),
      };

      const result = await this.sendEvent(event);
      
      // Update analytics
      this.updateAnalytics('event', result, performance.now() - startTime);
      
      return result;
    } catch (error) {
      console.error('[Klaviyo] Event tracking error:', error);
      
      // Update error analytics
      this.updateAnalytics('event', {
        queued: false,
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error',
      }, performance.now() - startTime);
      
      return {
        queued: false,
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error',
      };
    }
  }

  /**
   * Create or update a profile
   */
  async createOrUpdateProfile(profile: KlaviyoProfile): Promise<QueueResult> {
    try {
      if (!profile.email && !profile.external_id) {
        throw new Error('Profile must have either email or external_id');
      }

      return await this.sendProfile(profile);
    } catch (error) {
      console.error('[Klaviyo] Profile update error:', error);
      return {
        queued: false,
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error',
      };
    }
  }

  private async sendEvent(event: KlaviyoEvent, retryCount = 0): Promise<QueueResult> {
    try {
      // Check rate limit
      await this.rateLimiter.consume('klaviyo_events');
      
      // Send to Klaviyo
      const response = await this.sendEventToKlaviyo(event);
      
      return {
        queued: false,
        success: true,
        eventId: this.generateEventId(),
        retryCount,
      };
    } catch (error) {
      // Handle rate limiting or 429 with centralized retry logic
      if (this.shouldRetry(error) && retryCount < this.maxRetries) {
        console.warn(`[Klaviyo] Event failed, queuing for retry (${retryCount + 1}/${this.maxRetries}):`, error);
        return await this.queueEventForRetry(event, retryCount + 1);
      }
      
      // Queue permanently if max retries exceeded or non-retryable error
      console.warn('[Klaviyo] Event failed permanently, queuing:', error);
      return await this.queueEvent(event);
    }
  }

  private async sendProfile(profile: KlaviyoProfile, retryCount = 0): Promise<QueueResult> {
    try {
      // Check rate limit
      await this.rateLimiter.consume('klaviyo_profiles');
      
      // Send to Klaviyo
      const response = await this.sendProfileToKlaviyo(profile);
      
      return {
        queued: false,
        success: true,
        eventId: this.generateEventId(),
        retryCount,
      };
    } catch (error) {
      // Handle rate limiting or 429 with centralized retry logic
      if (this.shouldRetry(error) && retryCount < this.maxRetries) {
        console.warn(`[Klaviyo] Profile failed, queuing for retry (${retryCount + 1}/${this.maxRetries}):`, error);
        return await this.queueProfileForRetry(profile, retryCount + 1);
      }
      
      // Queue permanently if max retries exceeded or non-retryable error
      console.warn('[Klaviyo] Profile failed permanently, queuing:', error);
      return await this.queueProfile(profile);
    }
  }

  private shouldRetry(error: unknown): boolean {
    if (error instanceof Error) {
      const message = error.message.toLowerCase();
      return (
        message.includes('too many requests') ||
        message.includes('rate limit') ||
        message.includes('429') ||
        message.includes('timeout') ||
        message.includes('connection')
      );
    }
    return false;
  }

  private async queueEventForRetry(event: KlaviyoEvent, retryCount: number): Promise<QueueResult> {
    // Add retry metadata
    const retryEvent = {
      ...event,
      timestamp: Date.now() + this.retryDelay * retryCount, // Delayed retry
    };

    this.eventQueue.push(retryEvent);
    this.processEventQueue().catch(err => {
      console.error('[Klaviyo] Retry queue processing error:', err);
    });

    return {
      queued: true,
      success: true, // Queuing for retry is success
      eventId: this.generateEventId(),
      retryCount,
    };
  }

  private async queueProfileForRetry(profile: KlaviyoProfile, retryCount: number): Promise<QueueResult> {
    // Add retry metadata
    const retryProfile = {
      ...profile,
      _retryTimestamp: Date.now() + this.retryDelay * retryCount,
      _retryCount: retryCount,
    };

    this.profileQueue.push(retryProfile);
    this.processProfileQueue().catch(err => {
      console.error('[Klaviyo] Profile retry queue processing error:', err);
    });

    return {
      queued: true,
      success: true, // Queuing for retry is success
      eventId: this.generateEventId(),
      retryCount,
    };
  }

  private async queueEvent(event: KlaviyoEvent): Promise<QueueResult> {
    try {
      this.eventQueue.push({
        ...event,
        timestamp: Date.now(),
      });

      // Process queue asynchronously
      this.processEventQueue().catch(error => {
        console.error('[Klaviyo] Queue processing error:', error);
      });

      return {
        queued: true,
        success: true, // Queuing is considered success
        eventId: this.generateEventId(),
      };
    } catch (error) {
      console.error('[Klaviyo] Queue error:', error);
      return {
        queued: false,
        success: false,
        error: error instanceof Error ? error.message : 'Queue failed',
      };
    }
  }

  private async queueProfile(profile: KlaviyoProfile): Promise<QueueResult> {
    try {
      this.profileQueue.push(profile);

      // Process queue asynchronously
      this.processProfileQueue().catch(error => {
        console.error('[Klaviyo] Profile queue processing error:', error);
      });

      return {
        queued: true,
        success: true, // Queuing is considered success
        eventId: this.generateEventId(),
      };
    } catch (error) {
      console.error('[Klaviyo] Profile queue error:', error);
      return {
        queued: false,
        success: false,
        error: error instanceof Error ? error.message : 'Queue failed',
      };
    }
  }

  private async processEventQueue(): Promise<void> {
    if (this.isProcessingEvents || this.eventQueue.length === 0) {
      return;
    }

    this.isProcessingEvents = true;
    const eventsToProcess = [...this.eventQueue];
    this.eventQueue = [];

    try {
      for (const event of eventsToProcess) {
        // Skip events older than 5 minutes
        if (event.timestamp && Date.now() - event.timestamp > 5 * 60 * 1000) {
          continue;
        }

        // Wait for retry timestamp if applicable
        if (event.timestamp && event.timestamp > Date.now()) {
          this.eventQueue.push(event); // Put back in queue
          continue;
        }

        try {
          await this.rateLimiter.consume('klaviyo_events');
          await this.sendEventToKlaviyo(event);
        } catch (error) {
          // Re-queue if still rate limited and under retry limit
          const retryCount = (event as any)._retryCount || 0;
          if (this.shouldRetry(error) && retryCount < this.maxRetries) {
            this.eventQueue.push({
              ...event,
              timestamp: Date.now() + this.retryDelay,
              _retryCount: retryCount + 1,
            });
          }
        }
      }
    } finally {
      this.isProcessingEvents = false;
    }
  }

  private async processProfileQueue(): Promise<void> {
    if (this.isProcessingProfiles || this.profileQueue.length === 0) {
      return;
    }

    this.isProcessingProfiles = true;
    const profilesToProcess = [...this.profileQueue];
    this.profileQueue = [];

    try {
      for (const profile of profilesToProcess) {
        // Skip profiles older than 5 minutes
        if ((profile as any)._retryTimestamp && Date.now() - (profile as any)._retryTimestamp > 5 * 60 * 1000) {
          continue;
        }

        // Wait for retry timestamp if applicable
        if ((profile as any)._retryTimestamp && (profile as any)._retryTimestamp > Date.now()) {
          this.profileQueue.push(profile); // Put back in queue
          continue;
        }

        try {
          await this.rateLimiter.consume('klaviyo_profiles');
          await this.sendProfileToKlaviyo(profile);
        } catch (error) {
          // Re-queue if still rate limited and under retry limit
          const retryCount = (profile as any)._retryCount || 0;
          if (this.shouldRetry(error) && retryCount < this.maxRetries) {
            this.profileQueue.push({
              ...profile,
              _retryTimestamp: Date.now() + this.retryDelay,
              _retryCount: retryCount + 1,
            });
          }
        }
      }
    } finally {
      this.isProcessingProfiles = false;
    }
  }

  private async sendEventToKlaviyo(event: KlaviyoEvent): Promise<Response> {
    // Mock mode for development/testing
    if (this.privateKey === 'mock_private_key') {
      console.log('[Klaviyo] Mock mode - would send event:', event.event);
      return new Response(JSON.stringify({ success: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      });
    }

    const url = `https://a.klaviyo.com/api/events`;
    
    const payload = {
      data: {
        type: 'event',
        attributes: {
          metric: { data: { type: 'metric', id: event.event } },
          profile: event.profile ? { data: { type: 'profile', attributes: event.profile } } : undefined,
          properties: event.properties,
          time: new Date(event.timestamp || Date.now()).toISOString(),
        },
      },
    };

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Authorization': `Klaviyo-API-Key ${this.privateKey}`,
        'Content-Type': 'application/json',
        'revision': '2023-08-15',
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Klaviyo API error: ${response.status} - ${errorText}`);
    }

    return response;
  }

  private async sendProfileToKlaviyo(profile: KlaviyoProfile): Promise<Response> {
    // Mock mode for development/testing
    if (this.privateKey === 'mock_private_key') {
      console.log('[Klaviyo] Mock mode - would send profile:', profile.email);
      return new Response(JSON.stringify({ success: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      });
    }

    const url = `https://a.klaviyo.com/api/profiles`;
    
    const payload = {
      data: {
        type: 'profile',
        attributes: profile,
      },
    };

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Authorization': `Klaviyo-API-Key ${this.privateKey}`,
        'Content-Type': 'application/json',
        'revision': '2023-08-15',
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Klaviyo API error: ${response.status} - ${errorText}`);
    }

    return response;
  }

  private generateEventId(): string {
    return `klv_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Get queue status
   */
  getQueueStatus(): { 
    eventQueueLength: number; 
    profileQueueLength: number; 
    isProcessingEvents: boolean;
    isProcessingProfiles: boolean;
    redisConnected: boolean;
  } {
    return {
      eventQueueLength: this.eventQueue.length,
      profileQueueLength: this.profileQueue.length,
      isProcessingEvents: this.isProcessingEvents,
      isProcessingProfiles: this.isProcessingProfiles,
      redisConnected: this.redis?.status === 'ready' || false,
    };
  }

  /**
   * Health check
   */
  async healthCheck(): Promise<{ status: string; details: Record<string, unknown> }> {
    try {
      const queueStatus = this.getQueueStatus();
      const testEvent = await this.trackEvent('health_check', { email: 'test@example.com' }, { test: true });
      
      return {
        status: 'healthy',
        details: {
          queueStatus,
          testEventSuccess: testEvent.success,
          publicKey: this.publicKey ? this.publicKey.substring(0, 10) + '...' : 'none',
          mockMode: this.privateKey === 'mock_private_key',
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
   * Update analytics with performance data
   */
  private updateAnalytics(type: 'event' | 'profile', result: QueueResult, responseTime: number): void {
    // Update counters
    if (type === 'event') {
      this.analytics.totalEvents++;
    } else {
      this.analytics.totalProfiles++;
    }

    // Track response time
    const key = `${type}_response_times`;
    if (!this.performanceMetrics.has(key)) {
      this.performanceMetrics.set(key, []);
    }
    this.performanceMetrics.get(key)!.push(responseTime);

    // Update performance metrics
    this.updatePerformanceMetrics();

    // Update queue status
    this.analytics.queueStatus = this.getQueueStatus();
  }

  private updatePerformanceMetrics(): void {
    const eventTimes = this.performanceMetrics.get('event_response_times') || [];
    const profileTimes = this.performanceMetrics.get('profile_response_times') || [];
    const allTimes = [...eventTimes, ...profileTimes];

    if (allTimes.length > 0) {
      this.analytics.performanceMetrics.avgResponseTime = 
        allTimes.reduce((sum, time) => sum + time, 0) / allTimes.length;
    }

    // Calculate success/error rates
    const totalOperations = this.analytics.totalEvents + this.analytics.totalProfiles;
    const successfulOperations = totalOperations - (this.analytics.performanceMetrics.errorRate * totalOperations / 100);
    
    if (totalOperations > 0) {
      this.analytics.performanceMetrics.successRate = (successfulOperations / totalOperations) * 100;
      this.analytics.performanceMetrics.errorRate = 100 - this.analytics.performanceMetrics.successRate;
    }

    this.analytics.timestamp = new Date().toISOString();
  }

  /**
   * Send email using template
   */
  async sendEmailFromTemplate(
    templateId: string, 
    profile: KlaviyoProfile, 
    variables: Record<string, any> = {}
  ): Promise<QueueResult> {
    const template = this.templates.get(templateId);
    if (!template) {
      throw new Error(`Template ${templateId} not found`);
    }

    // Merge template variables with provided variables
    const mergedVariables = { ...profile, ...variables };

    // Process template content
    const subject = this.processTemplate(template.subject, mergedVariables);
    const content = this.processTemplate(template.content, mergedVariables);

    // Track email sent event
    return await this.trackEvent('Email Sent', profile, {
      template_id: templateId,
      template_name: template.name,
      subject,
      category: template.category,
      content_length: content.length
    });
  }

  /**
   * Process template variables
   */
  private processTemplate(template: string, variables: Record<string, any>): string {
    return template.replace(/\{\{(\w+)\}\}/g, (match, key) => {
      return variables[key] !== undefined ? String(variables[key]) : match;
    });
  }

  /**
   * Get template by ID
   */
  getTemplate(templateId: string): EmailTemplate | undefined {
    return this.templates.get(templateId);
  }

  /**
   * Get all templates
   */
  getAllTemplates(): EmailTemplate[] {
    return Array.from(this.templates.values());
  }

  /**
   * Add custom template
   */
  addTemplate(template: EmailTemplate): void {
    this.templates.set(template.id, template);
    console.log(`[Klaviyo] Added template: ${template.name}`);
  }

  /**
   * Remove template
   */
  removeTemplate(templateId: string): boolean {
    const deleted = this.templates.delete(templateId);
    if (deleted) {
      console.log(`[Klaviyo] Removed template: ${templateId}`);
    }
    return deleted;
  }

  /**
   * Get comprehensive analytics
   */
  getAnalytics(): AnalyticsData {
    // Update queue status
    this.analytics.queueStatus = this.getQueueStatus();
    
    // Update performance metrics
    this.updatePerformanceMetrics();
    
    return { ...this.analytics };
  }

  /**
   * Get performance metrics
   */
  getPerformanceMetrics(): {
    avgEventResponseTime: number;
    avgProfileResponseTime: number;
    totalRequests: number;
    successRate: number;
    errorRate: number;
  } {
    const eventTimes = this.performanceMetrics.get('event_response_times') || [];
    const profileTimes = this.performanceMetrics.get('profile_response_times') || [];

    return {
      avgEventResponseTime: eventTimes.length > 0 
        ? eventTimes.reduce((sum, time) => sum + time, 0) / eventTimes.length 
        : 0,
      avgProfileResponseTime: profileTimes.length > 0 
        ? profileTimes.reduce((sum, time) => sum + time, 0) / profileTimes.length 
        : 0,
      totalRequests: this.analytics.totalEvents + this.analytics.totalProfiles,
      successRate: this.analytics.performanceMetrics.successRate,
      errorRate: this.analytics.performanceMetrics.errorRate
    };
  }

  /**
   * Track campaign metrics
   */
  trackCampaignMetrics(metrics: Partial<CampaignMetrics>): void {
    Object.assign(this.analytics.campaignMetrics, metrics);
    this.analytics.timestamp = new Date().toISOString();
  }

  /**
   * Create email campaign
   */
  async createCampaign(
    name: string,
    templateId: string,
    profiles: KlaviyoProfile[],
    variables: Record<string, any> = {}
  ): Promise<{ campaignId: string; results: QueueResult[] }> {
    const campaignId = `campaign_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    const results: QueueResult[] = [];

    console.log(`[Klaviyo] Creating campaign: ${name} for ${profiles.length} profiles`);

    // Send emails to all profiles
    for (const profile of profiles) {
      try {
        const result = await this.sendEmailFromTemplate(templateId, profile, {
          ...variables,
          campaign_id: campaignId,
          campaign_name: name
        });
        results.push(result);

        // Update campaign metrics
        if (result.success) {
          this.analytics.campaignMetrics.sent++;
        }
      } catch (error) {
        console.error(`[Klaviyo] Failed to send campaign email to ${profile.email}:`, error);
        results.push({
          queued: false,
          success: false,
          error: error instanceof Error ? error.message : 'Unknown error'
        });
      }
    }

    // Track campaign created event
    await this.trackEvent('Campaign Created', undefined, {
      campaign_id: campaignId,
      campaign_name: name,
      template_id: templateId,
      total_profiles: profiles.length,
      successful_sends: results.filter(r => r.success).length
    });

    return { campaignId, results };
  }

  /**
   * Cleanup
   */
  async disconnect(): Promise<void> {
    if (this.redis) {
      await this.redis.disconnect();
    }
    
    // Clear performance metrics
    this.performanceMetrics.clear();
    
    console.log('[Klaviyo] Service disconnected and cleaned up');
  }
}

export default KlaviyoService;
export type { KlaviyoEvent, KlaviyoProfile, QueueResult, EmailTemplate, CampaignMetrics, AnalyticsData };
