/**
 * Health Routes
 * System status, module readiness, last job runs
 */

function registerHealthRoutes(app, { context, scheduler }) {
  // Main health endpoint
  app.get('/health', async (req, res) => {
    try {
      const timestamp = new Date();
      
      // Basic system health
      const systemHealth = {
        status: 'healthy',
        timestamp: timestamp.toISOString(),
        uptime: process.uptime(),
        memory: process.memoryUsage(),
        version: process.env.npm_package_version || '1.0.0',
        node: process.version,
        platform: process.platform
      };

      // Context health
      let contextHealth = { status: 'ok', services: {} };
      if (context && context.healthCheck) {
        contextHealth = await context.healthCheck();
      }

      // Scheduler health
      let schedulerHealth = { status: 'ok', jobs: 0, running: 0 };
      if (scheduler) {
        schedulerHealth = {
          status: scheduler.status || 'ok',
          jobs: scheduler.jobRegistry?.size || 0,
          running: scheduler.runningJobs?.size || 0,
          pendingApprovals: scheduler.approvalQueue?.size || 0,
          lastJobRuns: scheduler.getRecentJobRuns?.() || []
        };
      }

      // Module health
      const moduleHealth = {};
      if (scheduler && scheduler.moduleRegistry) {
        for (const [moduleName, module] of scheduler.moduleRegistry) {
          moduleHealth[moduleName] = {
            status: module.status || 'ok',
            jobs: module.jobs?.size || 0,
            lastActivity: module.lastActivity || null,
            errors: module.errors || []
          };
        }
      }

      // Overall status
      let overallStatus = 'healthy';
      if (contextHealth.overall === 'degraded' || schedulerHealth.status !== 'ok') {
        overallStatus = 'degraded';
      }
      
      const hasCriticalErrors = Object.values(moduleHealth).some(m => 
    m.errors && m.errors.length > 0
  );
      if (hasCriticalErrors) {
        overallStatus = 'unhealthy';
      }

      const health = {
        status: overallStatus,
        timestamp: timestamp.toISOString(),
        system: systemHealth,
        context: contextHealth,
        scheduler: schedulerHealth,
        modules: moduleHealth
      };

      // HTTP status based on overall health
      const statusCode = overallStatus === 'healthy' ? 200 : 
                        overallStatus === 'degraded' ? 200 : 503;

      res.status(statusCode).json(health);
    } catch (error) {
      console.error('Health check failed:', error);
      res.status(500).json({
        status: 'error',
        timestamp: new Date().toISOString(),
        error: error.message
      });
    }
  });

  // Ready endpoint for Kubernetes/docker health checks
  app.get('/health/ready', async (req, res) => {
    try {
      const checks = {
        database: false,
        apis: false,
        scheduler: false
      };

      // Database check
      if (context && context.getClient) {
        try {
          const db = context.getClient('database');
          await db.query('SELECT 1');
          checks.database = true;
        } catch (error) {
          // Database not available
        }
      } else {
        checks.database = true; // No database configured
      }

      // API checks
      if (context && context.getService) {
        try {
          const shopify = context.getService('shopify');
          if (shopify.storeUrl && shopify.adminToken) {
            // Basic API connectivity test
            checks.apis = true;
          }
        } catch (error) {
          // API not available
        }
      } else {
        checks.apis = true; // No APIs configured
      }

      // Scheduler check
      if (scheduler && scheduler.status !== 'stopped') {
        checks.scheduler = true;
      }

      const allReady = Object.values(checks).every(check => check === true);
      const statusCode = allReady ? 200 : 503;

      res.status(statusCode).json({
        ready: allReady,
        checks,
        timestamp: new Date().toISOString()
      });
    } catch (error) {
      console.error('Readiness check failed:', error);
      res.status(500).json({
        ready: false,
        error: error.message,
        timestamp: new Date().toISOString()
      });
    }
  });

  // Live endpoint for Kubernetes/docker liveness
  app.get('/health/live', (req, res) => {
    res.json({
      alive: true,
      uptime: process.uptime(),
      timestamp: new Date().toISOString()
    });
  });

  // Detailed module health
  app.get('/health/modules', async (req, res) => {
    try {
      if (!scheduler || !scheduler.moduleRegistry) {
        return res.json({ modules: {}, message: 'No modules registered' });
      }

      const modules = {};
      
      for (const [moduleName, module] of scheduler.moduleRegistry) {
        const jobs = [];
        
        if (module.jobs) {
          for (const [jobName, job] of module.jobs) {
            jobs.push({
              name: jobName,
              class: job.class,
              schedule: job.schedule,
              requiresApproval: job.requiresApproval,
              lastRun: job.lastRun,
              runCount: job.runCount,
              status: job.status,
              errors: job.errors || []
            });
          }
        }

        modules[moduleName] = {
          name: module.name,
          status: module.status || 'ok',
          lastActivity: module.lastActivity,
          jobs,
          jobCount: jobs.length
        };
      }

      res.json({
        modules,
        timestamp: new Date().toISOString()
      });
    } catch (error) {
      console.error('Module health check failed:', error);
      res.status(500).json({
        error: error.message,
        timestamp: new Date().toISOString()
      });
    }
  });

  // Job execution history
  app.get('/health/jobs', async (req, res) => {
    try {
      const limit = parseInt(req.query.limit) || 50;
      const offset = parseInt(req.query.offset) || 0;

      let jobHistory = [];
      
      if (scheduler && scheduler.getRecentJobRuns) {
        jobHistory = scheduler.getRecentJobRuns(limit, offset);
      }

      res.json({
        jobs: jobHistory,
        total: jobHistory.length,
        limit,
        offset,
        timestamp: new Date().toISOString()
      });
    } catch (error) {
      console.error('Job history check failed:', error);
      res.status(500).json({
        error: error.message,
        timestamp: new Date().toISOString()
      });
    }
  });

  // System metrics
  app.get('/health/metrics', (req, res) => {
    try {
      const metrics = {
        timestamp: new Date().toISOString(),
        system: {
          uptime: process.uptime(),
          memory: process.memoryUsage(),
          cpu: process.cpuUsage(),
          loadAverage: require('os').loadavg(),
          platform: process.platform,
          nodeVersion: process.version
        },
        eventLoop: {
          delay: process.hrtime.bigint() - process.hrtime.bigint()
        }
      };

      // Add scheduler metrics if available
      if (scheduler) {
        metrics.scheduler = {
          registeredJobs: scheduler.jobRegistry?.size || 0,
          runningJobs: scheduler.runningJobs?.size || 0,
          pendingApprovals: scheduler.approvalQueue?.size || 0,
          eventHistorySize: scheduler.eventHistory?.length || 0
        };
      }

      res.json(metrics);
    } catch (error) {
      console.error('Metrics collection failed:', error);
      res.status(500).json({
        error: error.message,
        timestamp: new Date().toISOString()
      });
    }
  });

  // Environment info (sanitized)
  app.get('/health/env', (req, res) => {
    try {
      const env = {
        node: process.version,
        platform: process.platform,
        arch: process.arch,
        environment: process.env.NODE_ENV || 'development',
        port: process.env.PORT || 3200,
        configuredServices: {
          shopify: !!process.env.SHOPIFY_STORE_URL && !!process.env.SHOPIFY_ADMIN_TOKEN,
          printify: !!process.env.PRINTIFY_API_KEY && !!process.env.PRINTIFY_SHOP_ID,
          paypal: !!process.env.PAYPAL_CLIENT_ID && !!process.env.PAYPAL_CLIENT_SECRET,
          telegram: !!process.env.TELEGRAM_BOT_TOKEN,
          email: !!process.env.RESEND_API_KEY
        }
      };

      res.json(env);
    } catch (error) {
      console.error('Environment check failed:', error);
      res.status(500).json({
        error: error.message,
        timestamp: new Date().toISOString()
      });
    }
  });
}

module.exports = { registerHealthRoutes };
