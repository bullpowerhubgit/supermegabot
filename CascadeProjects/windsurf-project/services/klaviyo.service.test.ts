/**
 * Enhanced Klaviyo Service Test Suite
 * Tests templates, analytics, campaigns, and performance tracking
 */

import KlaviyoService, { EmailTemplate, KlaviyoProfile } from './klaviyo.service';

describe('Enhanced KlaviyoService', () => {
  let service: KlaviyoService;
  let testProfile: KlaviyoProfile;

  beforeEach(() => {
    service = new KlaviyoService();
    testProfile = {
      email: 'test@example.com',
      first_name: 'John',
      last_name: 'Doe',
      phone_number: '+1234567890',
      external_id: 'test_user_123'
    };
  });

  afterEach(async () => {
    await service.disconnect();
  });

  describe('Template Management', () => {
    test('should initialize with default templates', () => {
      const templates = service.getAllTemplates();
      expect(templates.length).toBeGreaterThan(0);
      
      const welcomeTemplate = service.getTemplate('welcome');
      expect(welcomeTemplate).toBeDefined();
      expect(welcomeTemplate?.name).toBe('Welcome Email');
      expect(welcomeTemplate?.category).toBe('transactional');
    });

    test('should add custom template', () => {
      const customTemplate: EmailTemplate = {
        id: 'custom_test',
        name: 'Custom Test Template',
        subject: 'Test Subject {{first_name}}',
        content: '<p>Hello {{first_name}}, this is a test!</p>',
        variables: ['first_name'],
        category: 'marketing'
      };

      service.addTemplate(customTemplate);
      
      const retrieved = service.getTemplate('custom_test');
      expect(retrieved).toEqual(customTemplate);
    });

    test('should remove template', () => {
      const initialCount = service.getAllTemplates().length;
      
      const removed = service.removeTemplate('welcome');
      expect(removed).toBe(true);
      
      const afterCount = service.getAllTemplates().length;
      expect(afterCount).toBe(initialCount - 1);
      
      const template = service.getTemplate('welcome');
      expect(template).toBeUndefined();
    });

    test('should process template variables', async () => {
      const result = await service.sendEmailFromTemplate('welcome', testProfile, {
        company_name: 'Test Company',
        product_name: 'Test Product',
        discount_percentage: 10,
        welcome_code: 'WELCOME10'
      });

      expect(result.success).toBe(true);
      expect(result.queued).toBe(false);
    });
  });

  describe('Analytics and Performance', () => {
    test('should track analytics for events', async () => {
      const initialAnalytics = service.getAnalytics();
      
      await service.trackEvent('Test Event', testProfile, { test_property: 'test_value' });
      
      const updatedAnalytics = service.getAnalytics();
      expect(updatedAnalytics.totalEvents).toBe(initialAnalytics.totalEvents + 1);
      expect(updatedAnalytics.timestamp).not.toBe(initialAnalytics.timestamp);
    });

    test('should track performance metrics', async () => {
      await service.trackEvent('Test Event 1', testProfile);
      await service.trackEvent('Test Event 2', testProfile);
      await service.createOrUpdateProfile(testProfile);

      const metrics = service.getPerformanceMetrics();
      expect(metrics.totalRequests).toBe(3);
      expect(metrics.avgEventResponseTime).toBeGreaterThan(0);
      expect(metrics.successRate).toBeGreaterThan(0);
    });

    test('should track campaign metrics', () => {
      const initialMetrics = service.getAnalytics().campaignMetrics;
      
      service.trackCampaignMetrics({
        sent: 100,
        opened: 50,
        clicked: 25,
        revenue: 1000
      });

      const updatedMetrics = service.getAnalytics().campaignMetrics;
      expect(updatedMetrics.sent).toBe(100);
      expect(updatedMetrics.opened).toBe(50);
      expect(updatedMetrics.clicked).toBe(25);
      expect(updatedMetrics.revenue).toBe(1000);
    });
  });

  describe('Email Campaigns', () => {
    test('should create email campaign', async () => {
      const profiles: KlaviyoProfile[] = [
        testProfile,
        { email: 'test2@example.com', first_name: 'Jane' },
        { email: 'test3@example.com', first_name: 'Bob' }
      ];

      const campaign = await service.createCampaign(
        'Test Campaign',
        'welcome',
        profiles,
        { company_name: 'Test Company' }
      );

      expect(campaign.campaignId).toMatch(/^campaign_\d+_[a-z0-9]+$/);
      expect(campaign.results).toHaveLength(3);
      expect(campaign.results.every(r => r.success || r.queued)).toBe(true);
    });

    test('should handle campaign with invalid template', async () => {
      await expect(
        service.createCampaign('Invalid Campaign', 'nonexistent', [testProfile])
      ).rejects.toThrow('Template nonexistent not found');
    });

    test('should track campaign metrics during creation', async () => {
      const profiles: KlaviyoProfile[] = [testProfile, { email: 'test2@example.com' }];
      
      await service.createCampaign('Metrics Test', 'welcome', profiles);
      
      const analytics = service.getAnalytics();
      expect(analytics.campaignMetrics.sent).toBe(2);
      expect(analytics.totalEvents).toBeGreaterThan(0); // Campaign Created event
    });
  });

  describe('Queue Management', () => {
    test('should provide queue status', () => {
      const status = service.getQueueStatus();
      
      expect(status).toHaveProperty('eventQueueLength');
      expect(status).toHaveProperty('profileQueueLength');
      expect(status).toHaveProperty('isProcessingEvents');
      expect(status).toHaveProperty('isProcessingProfiles');
      expect(status).toHaveProperty('redisConnected');
      
      expect(typeof status.eventQueueLength).toBe('number');
      expect(typeof status.profileQueueLength).toBe('number');
    });

    test('should handle queue processing during high load', async () => {
      const promises = [];
      
      // Create multiple concurrent requests
      for (let i = 0; i < 10; i++) {
        promises.push(service.trackEvent(`Event ${i}`, testProfile, { index: i }));
        promises.push(service.createOrUpdateProfile({ ...testProfile, email: `test${i}@example.com` }));
      }

      const results = await Promise.all(promises);
      
      // All requests should succeed or be queued
      expect(results.every(r => r.success || r.queued)).toBe(true);
      
      // Analytics should reflect all operations
      const analytics = service.getAnalytics();
      expect(analytics.totalEvents).toBe(10);
      expect(analytics.totalProfiles).toBe(10);
    });
  });

  describe('Error Handling', () => {
    test('should handle invalid template gracefully', async () => {
      const result = await service.sendEmailFromTemplate('nonexistent', testProfile);
      expect(result.success).toBe(false);
      expect(result.error).toContain('Template nonexistent not found');
    });

    test('should handle profile validation', async () => {
      const invalidProfile = {} as KlaviyoProfile;
      const result = await service.createOrUpdateProfile(invalidProfile);
      expect(result.success).toBe(false);
      expect(result.error).toContain('must have either email or external_id');
    });

    test('should maintain performance during errors', async () => {
      // Mix of valid and invalid operations
      const promises = [
        service.trackEvent('Valid Event', testProfile),
        service.sendEmailFromTemplate('nonexistent', testProfile),
        service.createOrUpdateProfile({ email: 'valid@example.com' }),
        service.createOrUpdateProfile({} as KlaviyoProfile)
      ];

      await Promise.all(promises);
      
      const metrics = service.getPerformanceMetrics();
      expect(metrics.totalRequests).toBe(4);
      expect(metrics.successRate).toBeLessThan(100);
      expect(metrics.errorRate).toBeGreaterThan(0);
    });
  });

  describe('Health Check', () => {
    test('should return healthy status', async () => {
      const health = await service.healthCheck();
      
      expect(health.status).toBe('healthy');
      expect(health.details).toHaveProperty('queueStatus');
      expect(health.details).toHaveProperty('testEventSuccess');
      expect(health.details).toHaveProperty('publicKey');
      expect(health.details).toHaveProperty('mockMode');
    });

    test('should include analytics in health check', async () => {
      await service.trackEvent('Health Test', testProfile);
      
      const health = await service.healthCheck();
      expect(health.status).toBe('healthy');
      expect(health.details.testEventSuccess).toBe(true);
    });
  });

  describe('Integration Tests', () => {
    test('should handle complete email workflow', async () => {
      // 1. Create profile
      const profileResult = await service.createOrUpdateProfile(testProfile);
      expect(profileResult.success).toBe(true);

      // 2. Send welcome email
      const emailResult = await service.sendEmailFromTemplate('welcome', testProfile, {
        company_name: 'Workflow Test',
        product_name: 'Test Product',
        discount_percentage: 15,
        welcome_code: 'WORKFLOW15'
      });
      expect(emailResult.success).toBe(true);

      // 3. Track user activity
      const activityResult = await service.trackEvent('Welcome Email Opened', testProfile, {
        email_id: emailResult.eventId,
        timestamp: Date.now()
      });
      expect(activityResult.success).toBe(true);

      // 4. Check analytics
      const analytics = service.getAnalytics();
      expect(analytics.totalProfiles).toBe(1);
      expect(analytics.totalEvents).toBe(2); // Email Sent + Welcome Email Opened
      expect(analytics.campaignMetrics.sent).toBe(1);
    });

    test('should handle bulk operations efficiently', async () => {
      const profiles: KlaviyoProfile[] = Array.from({ length: 50 }, (_, i) => ({
        email: `bulk${i}@example.com`,
        first_name: `User${i}`,
        external_id: `bulk_user_${i}`
      }));

      const startTime = performance.now();
      
      // Bulk profile creation
      const profilePromises = profiles.map(p => service.createOrUpdateProfile(p));
      const profileResults = await Promise.all(profilePromises);

      // Bulk campaign
      const campaign = await service.createCampaign('Bulk Test', 'promotion', profiles, {
        promotion_title: 'Bulk Promotion',
        discount_percentage: 20
      });

      const endTime = performance.now();
      const duration = endTime - startTime;

      expect(profileResults.every(r => r.success || r.queued)).toBe(true);
      expect(campaign.results.every(r => r.success || r.queued)).toBe(true);
      expect(duration).toBeLessThan(10000); // Should complete within 10 seconds

      const analytics = service.getAnalytics();
      expect(analytics.totalProfiles).toBe(50);
      expect(analytics.campaignMetrics.sent).toBe(50);
    });
  });
});

// Performance Benchmark Test
describe('KlaviyoService Performance', () => {
  let service: KlaviyoService;

  beforeAll(() => {
    service = new KlaviyoService();
  });

  afterAll(async () => {
    await service.disconnect();
  });

  test('should handle 1000 concurrent operations', async () => {
    const operations = [];
    
    for (let i = 0; i < 1000; i++) {
      operations.push(
        service.trackEvent(`Perf Event ${i}`, {
          email: `perf${i}@example.com`,
          first_name: `Perf${i}`
        })
      );
    }

    const startTime = performance.now();
    const results = await Promise.all(operations);
    const endTime = performance.now();

    const duration = endTime - startTime;
    const successRate = results.filter(r => r.success).length / results.length;

    expect(successRate).toBeGreaterThan(0.95); // At least 95% success rate
    expect(duration).toBeLessThan(30000); // Within 30 seconds

    const metrics = service.getPerformanceMetrics();
    expect(metrics.totalRequests).toBe(1000);
    expect(metrics.avgEventResponseTime).toBeLessThan(100); // Average under 100ms
  });
});
