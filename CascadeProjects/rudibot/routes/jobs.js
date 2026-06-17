/**
 * Jobs Routes
 * Job execution, status, and management endpoints
 */

function registerJobRoutes(app, { scheduler }) {
  // List all registered jobs
  app.get('/jobs', async (req, res) => {
    try {
      const jobs = [];
      
      if (scheduler && scheduler.moduleRegistry) {
        for (const [moduleName, module] of scheduler.moduleRegistry) {
          if (module.jobs) {
            for (const [jobName, job] of module.jobs) {
              jobs.push({
                id: `${moduleName}.${jobName}`,
                name: jobName,
                module: moduleName,
                class: job.class,
                schedule: job.schedule,
                requiresApproval: job.requiresApproval,
                description: job.description,
                timeout: job.timeout,
                lastRun: job.lastRun,
                runCount: job.runCount,
                status: job.status,
                errors: job.errors || []
              });
            }
          }
        }
      }

      res.json({
        jobs,
        total: jobs.length,
        timestamp: new Date().toISOString()
      });
    } catch (error) {
      console.error('List jobs failed:', error);
      res.status(500).json({
        error: error.message,
        timestamp: new Date().toISOString()
      });
    }
  });

  // Get specific job details
  app.get('/jobs/:jobId', async (req, res) => {
    try {
      const { jobId } = req.params;
      const [moduleName, jobName] = jobId.split('.');
      
      if (!scheduler || !scheduler.moduleRegistry) {
        return res.status(404).json({
          error: 'No modules registered',
          timestamp: new Date().toISOString()
        });
      }

      const module = scheduler.moduleRegistry.get(moduleName);
      if (!module) {
        return res.status(404).json({
          error: `Module not found: ${moduleName}`,
          timestamp: new Date().toISOString()
        });
      }

      const job = module.jobs?.get(jobName);
      if (!job) {
        return res.status(404).json({
          error: `Job not found: ${jobName}`,
          timestamp: new Date().toISOString()
        });
      }

      const jobDetails = {
        id: jobId,
        name: jobName,
        module: moduleName,
        class: job.class,
        schedule: job.schedule,
        requiresApproval: job.requiresApproval,
        description: job.description,
        timeout: job.timeout,
        lastRun: job.lastRun,
        runCount: job.runCount,
        status: job.status,
        errors: job.errors || [],
        statistics: job.statistics || {},
        nextRun: job.nextRun
      };

      res.json(jobDetails);
    } catch (error) {
      console.error('Get job details failed:', error);
      res.status(500).json({
        error: error.message,
        timestamp: new Date().toISOString()
      });
    }
  });

  // Execute a job
  app.post('/jobs/:jobName/execute', async (req, res) => {
    try {
      const { jobName } = req.params;
      const { context = {}, force = false } = req.body;

      if (!scheduler) {
        return res.status(500).json({
          error: 'Scheduler not available',
          timestamp: new Date().toISOString()
        });
      }

      // Check if job exists
      const jobInfo = scheduler.findJob(jobName);
      if (!jobInfo) {
        return res.status(404).json({
          error: `Job not found: ${jobName}`,
          timestamp: new Date().toISOString()
        });
      }

      // Check if job requires approval
      if (jobInfo.job.requiresApproval && !force) {
        // Create approval request
        const approval = await scheduler.createApprovalRequest(jobName, {
          triggeredBy: 'api',
          context,
          requestedAt: new Date()
        });

        return res.json({
          approvalRequired: true,
          approvalId: approval.id,
          jobName,
          message: 'Job requires approval before execution',
          timestamp: new Date().toISOString()
        });
      }

      // Execute job directly
      const executionId = `exec_${Date.now()}`;
      const result = await scheduler.executeJob(jobName, {
        ...context,
        triggeredBy: 'api',
        executionId
      });

      res.json({
        success: true,
        executionId,
        jobName,
        result,
        timestamp: new Date().toISOString()
      });
    } catch (error) {
      console.error('Execute job failed:', error);
      res.status(500).json({
        error: error.message,
        timestamp: new Date().toISOString()
      });
    }
  });

  // Get job execution history
  app.get('/jobs/:jobName/history', async (req, res) => {
    try {
      const { jobName } = req.params;
      const limit = parseInt(req.query.limit) || 20;
      const offset = parseInt(req.query.offset) || 0;

      if (!scheduler || !scheduler.getJobHistory) {
        return res.json({
          history: [],
          total: 0,
          limit,
          offset,
          timestamp: new Date().toISOString()
        });
      }

      const history = scheduler.getJobHistory(jobName, limit, offset);

      res.json({
        history,
        total: history.length,
        limit,
        offset,
        timestamp: new Date().toISOString()
      });
    } catch (error) {
      console.error('Get job history failed:', error);
      res.status(500).json({
        error: error.message,
        timestamp: new Date().toISOString()
      });
    }
  });

  // Get running jobs
  app.get('/jobs/running', async (req, res) => {
    try {
      let runningJobs = [];
      
      if (scheduler && scheduler.runningJobs) {
        for (const [jobId, execution] of scheduler.runningJobs) {
          runningJobs.push({
            id: jobId,
            startTime: execution.startTime,
            status: execution.status,
            progress: execution.progress,
            context: execution.context
          });
        }
      }

      res.json({
        runningJobs,
        total: runningJobs.length,
        timestamp: new Date().toISOString()
      });
    } catch (error) {
      console.error('Get running jobs failed:', error);
      res.status(500).json({
        error: error.message,
        timestamp: new Date().toISOString()
      });
    }
  });

  // Cancel a running job
  app.post('/jobs/:jobId/cancel', async (req, res) => {
    try {
      const { jobId } = req.params;

      if (!scheduler || !scheduler.runningJobs) {
        return res.status(500).json({
          error: 'Scheduler not available',
          timestamp: new Date().toISOString()
        });
      }

      const execution = scheduler.runningJobs.get(jobId);
      if (!execution) {
        return res.status(404).json({
          error: `Job execution not found: ${jobId}`,
          timestamp: new Date().toISOString()
        });
      }

      // Cancel the job
      execution.status = 'cancelled';
      scheduler.runningJobs.delete(jobId);

      res.json({
        success: true,
        jobId,
        message: 'Job cancelled',
        timestamp: new Date().toISOString()
      });
    } catch (error) {
      console.error('Cancel job failed:', error);
      res.status(500).json({
        error: error.message,
        timestamp: new Date().toISOString()
      });
    }
  });

  // Get job statistics
  app.get('/jobs/stats', async (req, res) => {
    try {
      const stats = {
        total: 0,
        byClass: { AUTO: 0, APPROVE: 0, BLOCK: 0 },
        byModule: {},
        byStatus: { running: 0, completed: 0, failed: 0, idle: 0 },
        scheduled: 0,
        requiresApproval: 0
      };

      if (scheduler && scheduler.moduleRegistry) {
        for (const [moduleName, module] of scheduler.moduleRegistry) {
          if (module.jobs) {
            stats.byModule[moduleName] = 0;
            
            for (const [jobName, job] of module.jobs) {
              stats.total++;
              stats.byModule[moduleName]++;
              
              if (job.class) {
                stats.byClass[job.class] = (stats.byClass[job.class] || 0) + 1;
              }
              
              if (job.schedule) {
                stats.scheduled++;
              }
              
              if (job.requiresApproval) {
                stats.requiresApproval++;
              }
              
              // Count by current status
              const isRunning = scheduler.runningJobs?.has(`${moduleName}.${jobName}`);
              if (isRunning) {
                stats.byStatus.running++;
              } else if (job.lastRun) {
                const hasErrors = job.errors && job.errors.length > 0;
                stats.byStatus[hasErrors ? 'failed' : 'completed']++;
              } else {
                stats.byStatus.idle++;
              }
            }
          }
        }
      }

      res.json({
        stats,
        timestamp: new Date().toISOString()
      });
    } catch (error) {
      console.error('Get job stats failed:', error);
      res.status(500).json({
        error: error.message,
        timestamp: new Date().toISOString()
      });
    }
  });

  // Schedule a job
  app.post('/jobs/:jobName/schedule', async (req, res) => {
    try {
      const { jobName } = req.params;
      const { schedule, context = {} } = req.body;

      if (!scheduler) {
        return res.status(500).json({
          error: 'Scheduler not available',
          timestamp: new Date().toISOString()
        });
      }

      // Check if job exists
      const jobInfo = scheduler.findJob(jobName);
      if (!jobInfo) {
        return res.status(404).json({
          error: `Job not found: ${jobName}`,
          timestamp: new Date().toISOString()
        });
      }

      // Schedule the job
      const success = scheduler.scheduleJob(jobName, schedule, context);
      
      if (!success) {
        return res.status(400).json({
          error: 'Failed to schedule job',
          timestamp: new Date().toISOString()
        });
      }

      res.json({
        success: true,
        jobName,
        schedule,
        message: 'Job scheduled successfully',
        timestamp: new Date().toISOString()
      });
    } catch (error) {
      console.error('Schedule job failed:', error);
      res.status(500).json({
        error: error.message,
        timestamp: new Date().toISOString()
      });
    }
  });

  // Unschedule a job
  app.delete('/jobs/:jobName/schedule', async (req, res) => {
    try {
      const { jobName } = req.params;

      if (!scheduler) {
        return res.status(500).json({
          error: 'Scheduler not available',
          timestamp: new Date().toISOString()
        });
      }

      // Check if job exists
      const jobInfo = scheduler.findJob(jobName);
      if (!jobInfo) {
        return res.status(404).json({
          error: `Job not found: ${jobName}`,
          timestamp: new Date().toISOString()
        });
      }

      // Unschedule the job
      const success = scheduler.unscheduleJob(jobName);
      
      if (!success) {
        return res.status(400).json({
          error: 'Failed to unschedule job',
          timestamp: new Date().toISOString()
        });
      }

      res.json({
        success: true,
        jobName,
        message: 'Job unscheduled successfully',
        timestamp: new Date().toISOString()
      });
    } catch (error) {
      console.error('Unschedule job failed:', error);
      res.status(500).json({
        error: error.message,
        timestamp: new Date().toISOString()
      });
    }
  });

  // Get job logs
  app.get('/jobs/:jobName/logs', async (req, res) => {
    try {
      const { jobName } = req.params;
      const limit = parseInt(req.query.limit) || 50;
      const level = req.query.level || 'all'; // all, error, info, debug

      if (!scheduler || !scheduler.getJobLogs) {
        return res.json({
          logs: [],
          total: 0,
          limit,
          level,
          timestamp: new Date().toISOString()
        });
      }

      const logs = scheduler.getJobLogs(jobName, limit, level);

      res.json({
        logs,
        total: logs.length,
        limit,
        level,
        timestamp: new Date().toISOString()
      });
    } catch (error) {
      console.error('Get job logs failed:', error);
      res.status(500).json({
        error: error.message,
        timestamp: new Date().toISOString()
      });
    }
  });
}

module.exports = { registerJobRoutes };
