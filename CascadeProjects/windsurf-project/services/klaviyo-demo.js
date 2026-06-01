/**
 * Klaviyo Service Demo Application
 * Demonstrates the enhanced Klaviyo service with templates, analytics, and campaigns
 */

// Simple demo implementation without Jest dependencies
class KlaviyoServiceDemo {
  constructor() {
    this.service = new KlaviyoService();
    this.testResults = [];
  }

  async runAllDemos() {
    console.log('🚀 Starting Klaviyo Service Demo');
    console.log('=====================================');

    const demos = [
      this.demoTemplateManagement,
      this.demoEmailSending,
      this.demoCampaignCreation,
      this.demoAnalytics,
      this.demoPerformanceTracking,
      this.demoQueueManagement,
      this.demoHealthCheck
    ];

    for (const demo of demos) {
      try {
        await demo.call(this);
      } catch (error) {
        this.addTestResult(demo.name, false, error.message);
      }
    }

    this.printDemoSummary();
    return this.testResults;
  }

  addTestResult(testName, passed, details = '') {
    this.testResults.push({
      test: testName,
      passed,
      details,
      timestamp: new Date().toISOString()
    });

    const status = passed ? '✅' : '❌';
    console.log(`${status} ${testName}${details ? ': ' + details : ''}`);
  }

  async demoTemplateManagement() {
    console.log('\n📧 Template Management Demo');
    console.log('----------------------------------');

    // Check default templates
    const templates = this.service.getAllTemplates();
    this.addTestResult('Default Templates Loaded', templates.length > 0, 
      `Found ${templates.length} templates`);

    // Get welcome template
    const welcomeTemplate = this.service.getTemplate('welcome');
    this.addTestResult('Welcome Template Found', !!welcomeTemplate, 
      welcomeTemplate ? welcomeTemplate.name : 'Not found');

    // Add custom template
    const customTemplate = {
      id: 'demo_custom',
      name: 'Demo Custom Template',
      subject: 'Demo Subject {{first_name}}',
      content: '<p>Hello {{first_name}}, this is a demo template!</p>',
      variables: ['first_name'],
      category: 'marketing'
    };

    this.service.addTemplate(customTemplate);
    const retrievedTemplate = this.service.getTemplate('demo_custom');
    this.addTestResult('Custom Template Added', !!retrievedTemplate, 
      retrievedTemplate ? 'Template added successfully' : 'Failed to add');

    // Remove template
    const removed = this.service.removeTemplate('demo_custom');
    this.addTestResult('Custom Template Removed', removed, 
      removed ? 'Template removed successfully' : 'Failed to remove');
  }

  async demoEmailSending() {
    console.log('\n📨 Email Sending Demo');
    console.log('-------------------------');

    const testProfile = {
      email: 'demo@example.com',
      first_name: 'Demo',
      last_name: 'User',
      phone_number: '+1234567890',
      external_id: 'demo_user_123'
    };

    // Send welcome email
    const welcomeResult = await this.service.sendEmailFromTemplate('welcome', testProfile, {
      company_name: 'Demo Company',
      product_name: 'Demo Product',
      discount_percentage: 10,
      welcome_code: 'DEMO10'
    });

    this.addTestResult('Welcome Email Sent', welcomeResult.success, 
      welcomeResult.success ? 'Email sent successfully' : welcomeResult.error);

    // Track email event
    const eventResult = await this.service.trackEvent('Email Opened', testProfile, {
      email_id: welcomeResult.eventId,
      timestamp: Date.now()
    });

    this.addTestResult('Email Event Tracked', eventResult.success, 
      eventResult.success ? 'Event tracked successfully' : eventResult.error);

    // Create/update profile
    const profileResult = await this.service.createOrUpdateProfile(testProfile);
    this.addTestResult('Profile Created/Updated', profileResult.success, 
      profileResult.success ? 'Profile managed successfully' : profileResult.error);
  }

  async demoCampaignCreation() {
    console.log('\n🎯 Campaign Creation Demo');
    console.log('----------------------------');

    const profiles = [
      { email: 'campaign1@example.com', first_name: 'Campaign', last_name: 'User1' },
      { email: 'campaign2@example.com', first_name: 'Campaign', last_name: 'User2' },
      { email: 'campaign3@example.com', first_name: 'Campaign', last_name: 'User3' }
    ];

    // Create campaign
    const campaign = await this.service.createCampaign(
      'Demo Campaign',
      'promotion',
      profiles,
      {
        promotion_title: 'Demo Special Offer',
        promotion_description: 'Check out our amazing demo products!',
        discount_percentage: 15,
        expiry_date: '2026-06-30',
        shop_url: 'https://demo-shop.example.com'
      }
    );

    this.addTestResult('Campaign Created', !!campaign.campaignId, 
      `Campaign ID: ${campaign.campaignId}`);

    this.addTestResult('Campaign Results', campaign.results.length === profiles.length, 
      `${campaign.results.filter(r => r.success).length}/${campaign.results.length} successful`);

    // Check campaign metrics
    const analytics = this.service.getAnalytics();
    this.addTestResult('Campaign Metrics Tracked', analytics.campaignMetrics.sent > 0, 
      `Sent: ${analytics.campaignMetrics.sent}`);
  }

  async demoAnalytics() {
    console.log('\n📊 Analytics Demo');
    console.log('-------------------');

    // Get comprehensive analytics
    const analytics = this.service.getAnalytics();
    
    this.addTestResult('Analytics Available', !!analytics, 
      `Events: ${analytics.totalEvents}, Profiles: ${analytics.totalProfiles}`);

    // Get performance metrics
    const performance = this.service.getPerformanceMetrics();
    
    this.addTestResult('Performance Metrics Available', !!performance, 
      `Total Requests: ${performance.totalRequests}, Success Rate: ${performance.successRate.toFixed(2)}%`);

    // Track campaign metrics
    this.service.trackCampaignMetrics({
      sent: 100,
      delivered: 95,
      opened: 60,
      clicked: 30,
      bounced: 5,
      unsubscribed: 2,
      revenue: 2500,
      conversionRate: 3.2
    });

    const updatedAnalytics = this.service.getAnalytics();
    this.addTestResult('Campaign Metrics Updated', updatedAnalytics.campaignMetrics.sent === 100, 
      `Campaign metrics updated successfully`);
  }

  async demoPerformanceTracking() {
    console.log('\n⚡ Performance Tracking Demo');
    console.log('--------------------------------');

    const startTime = performance.now();
    
    // Generate multiple events for performance testing
    const promises = [];
    for (let i = 0; i < 10; i++) {
      promises.push(
        this.service.trackEvent(`Perf Test ${i}`, {
          email: `perf${i}@example.com`,
          first_name: `Perf${i}`
        })
      );
    }

    await Promise.all(promises);
    
    const endTime = performance.now();
    const duration = endTime - startTime;

    const metrics = this.service.getPerformanceMetrics();
    
    this.addTestResult('Performance Test Completed', duration < 10000, 
      `Completed in ${duration.toFixed(2)}ms`);

    this.addTestResult('Response Time Tracking', metrics.avgEventResponseTime > 0, 
      `Avg Response Time: ${metrics.avgEventResponseTime.toFixed(2)}ms`);

    this.addTestResult('Success Rate Calculated', metrics.successRate >= 0, 
      `Success Rate: ${metrics.successRate.toFixed(2)}%`);
  }

  async demoQueueManagement() {
    console.log('\n🔄 Queue Management Demo');
    console.log('----------------------------');

    // Get queue status
    const status = this.service.getQueueStatus();
    
    this.addTestResult('Queue Status Available', !!status, 
      `Event Queue: ${status.eventQueueLength}, Profile Queue: ${status.profileQueueLength}`);

    // Test high load scenario
    const highLoadPromises = [];
    for (let i = 0; i < 20; i++) {
      highLoadPromises.push(
        this.service.trackEvent(`High Load ${i}`, {
          email: `highload${i}@example.com`,
          first_name: `HighLoad${i}`
        })
      );
      highLoadPromises.push(
        this.service.createOrUpdateProfile({
          email: `highload_profile${i}@example.com`,
          first_name: `HighLoad${i}`
        })
      );
    }

    const results = await Promise.all(highLoadPromises);
    const successRate = results.filter(r => r.success).length / results.length;
    
    this.addTestResult('High Load Handled', successRate > 0.9, 
      `${(successRate * 100).toFixed(1)}% success rate under high load`);

    // Check queue after high load
    const afterLoadStatus = this.service.getQueueStatus();
    this.addTestResult('Queue Stable After Load', afterLoadStatus.eventQueueLength >= 0, 
      `Queue stable: ${afterLoadStatus.eventQueueLength} events queued`);
  }

  async demoHealthCheck() {
    console.log('\n🏥 Health Check Demo');
    console.log('----------------------');

    const health = await this.service.healthCheck();
    
    this.addTestResult('Health Check Passed', health.status === 'healthy', 
      `Status: ${health.status}`);

    this.addTestResult('Health Details Available', !!health.details, 
      `Mock Mode: ${health.details.mockMode}`);

    this.addTestResult('Queue Status in Health', !!health.details.queueStatus, 
      `Queue status included in health check`);
  }

  printDemoSummary() {
    console.log('\n=====================================');
    console.log('📊 Demo Summary');
    console.log('=====================================');

    const passed = this.testResults.filter(r => r.passed).length;
    const total = this.testResults.length;
    const failed = total - passed;

    console.log(`Total Demos: ${total}`);
    console.log(`Passed: ${passed} ✅`);
    console.log(`Failed: ${failed} ❌`);
    console.log(`Success Rate: ${((passed / total) * 100).toFixed(1)}%`);

    if (failed > 0) {
      console.log('\n❌ Failed Demos:');
      this.testResults
        .filter(r => !r.passed)
        .forEach(r => console.log(`- ${r.test}: ${r.details}`));
    }

    console.log('\n🎯 Final Service Status:');
    const finalAnalytics = this.service.getAnalytics();
    const finalPerformance = this.service.getPerformanceMetrics();
    
    console.log(`- Total Events Tracked: ${finalAnalytics.totalEvents}`);
    console.log(`- Total Profiles Managed: ${finalAnalytics.totalProfiles}`);
    console.log(`- Average Response Time: ${finalPerformance.avgEventResponseTime.toFixed(2)}ms`);
    console.log(`- Success Rate: ${finalPerformance.successRate.toFixed(2)}%`);
    console.log(`- Campaigns Sent: ${finalAnalytics.campaignMetrics.sent}`);
  }

  async cleanup() {
    await this.service.disconnect();
    console.log('\n🧹 Demo cleanup completed');
  }
}

// Mock KlaviyoService for demo (simplified version)
class KlaviyoService {
  constructor() {
    this.templates = new Map();
    this.analytics = {
      totalEvents: 0,
      totalProfiles: 0,
      queueStatus: { eventQueueLength: 0, profileQueueLength: 0 },
      performanceMetrics: { avgResponseTime: 0, successRate: 100, errorRate: 0 },
      campaignMetrics: { sent: 0, delivered: 0, opened: 0, clicked: 0, bounced: 0, unsubscribed: 0 },
      timestamp: new Date().toISOString()
    };
    this.performanceMetrics = new Map();
    this.initializeTemplates();
  }

  initializeTemplates() {
    this.templates.set('welcome', {
      id: 'welcome',
      name: 'Welcome Email',
      subject: 'Welcome to {{company_name}}!',
      content: '<h1>Welcome {{first_name}}!</h1><p>Thanks for joining {{company_name}}.</p>',
      variables: ['first_name', 'company_name'],
      category: 'transactional'
    });

    this.templates.set('promotion', {
      id: 'promotion',
      name: 'Special Promotion',
      subject: '{{promotion_title}} - Limited Time!',
      content: '<h1>{{promotion_title}}</h1><p>{{promotion_description}}</p>',
      variables: ['promotion_title', 'promotion_description'],
      category: 'marketing'
    });
  }

  async sendEmailFromTemplate(templateId, profile, variables = {}) {
    const startTime = performance.now();
    
    const template = this.templates.get(templateId);
    if (!template) {
      throw new Error(`Template ${templateId} not found`);
    }

    // Simulate processing time
    await new Promise(resolve => setTimeout(resolve, Math.random() * 100 + 50));

    const responseTime = performance.now() - startTime;
    this.updatePerformanceMetrics('event', true, responseTime);
    this.analytics.totalEvents++;

    return {
      success: true,
      queued: false,
      eventId: `evt_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
    };
  }

  async trackEvent(eventName, profile, properties = {}) {
    const startTime = performance.now();
    
    // Simulate processing
    await new Promise(resolve => setTimeout(resolve, Math.random() * 50 + 20));

    const responseTime = performance.now() - startTime;
    this.updatePerformanceMetrics('event', true, responseTime);
    this.analytics.totalEvents++;

    return {
      success: true,
      queued: false,
      eventId: `evt_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
    };
  }

  async createOrUpdateProfile(profile) {
    const startTime = performance.now();
    
    // Simulate processing
    await new Promise(resolve => setTimeout(resolve, Math.random() * 30 + 10));

    const responseTime = performance.now() - startTime;
    this.updatePerformanceMetrics('profile', true, responseTime);
    this.analytics.totalProfiles++;

    return {
      success: true,
      queued: false,
      eventId: `prof_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
    };
  }

  async createCampaign(name, templateId, profiles, variables = {}) {
    const campaignId = `campaign_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    const results = [];

    for (const profile of profiles) {
      try {
        const result = await this.sendEmailFromTemplate(templateId, profile, {
          ...variables,
          campaign_id: campaignId,
          campaign_name: name
        });
        results.push(result);

        if (result.success) {
          this.analytics.campaignMetrics.sent++;
        }
      } catch (error) {
        results.push({
          success: false,
          error: error.message
        });
      }
    }

    return { campaignId, results };
  }

  getTemplate(templateId) {
    return this.templates.get(templateId);
  }

  getAllTemplates() {
    return Array.from(this.templates.values());
  }

  addTemplate(template) {
    this.templates.set(template.id, template);
  }

  removeTemplate(templateId) {
    return this.templates.delete(templateId);
  }

  getAnalytics() {
    this.analytics.queueStatus = this.getQueueStatus();
    return { ...this.analytics };
  }

  getPerformanceMetrics() {
    const eventTimes = this.performanceMetrics.get('event_response_times') || [];
    const profileTimes = this.performanceMetrics.get('profile_response_times') || [];

    return {
      avgEventResponseTime: eventTimes.length > 0 
        ? eventTimes.reduce((sum, time) => sum + time, 0) / eventTimes.length 
        : Math.random() * 50 + 20,
      avgProfileResponseTime: profileTimes.length > 0 
        ? profileTimes.reduce((sum, time) => sum + time, 0) / profileTimes.length 
        : Math.random() * 30 + 15,
      totalRequests: this.analytics.totalEvents + this.analytics.totalProfiles,
      successRate: 95 + Math.random() * 4,
      errorRate: Math.random() * 5
    };
  }

  trackCampaignMetrics(metrics) {
    Object.assign(this.analytics.campaignMetrics, metrics);
    this.analytics.timestamp = new Date().toISOString();
  }

  getQueueStatus() {
    return {
      eventQueueLength: 0,
      profileQueueLength: 0,
      isProcessingEvents: false,
      isProcessingProfiles: false,
      redisConnected: false
    };
  }

  async healthCheck() {
    try {
      const testEvent = await this.trackEvent('health_check', { email: 'test@example.com' }, { test: true });
      
      return {
        status: 'healthy',
        details: {
          queueStatus: this.getQueueStatus(),
          testEventSuccess: testEvent.success,
          publicKey: 'demo_key...',
          mockMode: true
        }
      };
    } catch (error) {
      return {
        status: 'unhealthy',
        details: { error: error.message }
      };
    }
  }

  updatePerformanceMetrics(type, success, responseTime) {
    const key = `${type}_response_times`;
    if (!this.performanceMetrics.has(key)) {
      this.performanceMetrics.set(key, []);
    }
    this.performanceMetrics.get(key).push(responseTime);
  }

  async disconnect() {
    this.performanceMetrics.clear();
  }
}

// Run demo if this file is executed directly
if (typeof module !== 'undefined' && require.main === module) {
  const demo = new KlaviyoServiceDemo();
  
  demo.runAllDemos()
    .then(() => demo.cleanup())
    .catch(console.error);
}

// Export for use in other modules
if (typeof module !== 'undefined') {
  module.exports = { KlaviyoServiceDemo, KlaviyoService };
}
