/**
 * RUDIBOT Core Orchestrator
 * Zentrale Steuerung: Scheduler, Event-Bus, Job Queue, Approval-Flows
 */

const EventEmitter = require('events');
const cron = require('node-cron');
const fs = require('fs').promises;
const path = require('path');

class Orchestrator extends EventEmitter {
  constructor(options = {}) {
    super();
    this.logger = options.logger || console;
    this.telegramBot = options.telegramBot || null;
    
    // Core Systems
    this.jobQueue = new Map();
    this.approvalQueue = new Map();
    this.eventHistory = [];
    this.runningJobs = new Set();
    this.moduleRegistry = new Map();
    
    // Job Classes
    this.JOB_CLASSES = {
      AUTO: 'auto',      // Lesen, prüfen, importieren, klassifizieren
      APPROVE: 'approve', // Kündigen, refunden, Mails senden, Live-Änderungen
      BLOCK: 'block'     // Kritische Aktionen ohne Freigabe
    };
    
    // Module Registry
    this.registerModules();
    
    // Start Scheduler
    this.startScheduler();
  }

  // Module Registration
  registerModules() {
    const modules = [
      'commerce', 'finance', 'legal_tax', 'security', 'orchestrator'
    ];
    
    modules.forEach(module => {
      this.moduleRegistry.set(module, {
        name: module,
        status: 'registered',
        jobs: new Map(),
        lastActivity: new Date()
      });
    });
  }

  // Job Registration
  registerJob(moduleName, jobName, jobConfig) {
    if (!this.moduleRegistry.has(moduleName)) {
      throw new Error(`Module ${moduleName} nicht registriert`);
    }

    const job = {
      id: `${moduleName}.${jobName}`,
      name: jobName,
      module: moduleName,
      class: jobConfig.class || this.JOB_CLASSES.AUTO,
      schedule: jobConfig.schedule || null,
      handler: jobConfig.handler,
      requiresApproval: jobConfig.requiresApproval || false,
      timeout: jobConfig.timeout || 30000,
      retries: jobConfig.retries || 3,
      status: 'registered',
      lastRun: null,
      runCount: 0,
      errors: []
    };

    this.moduleRegistry.get(moduleName).jobs.set(jobName, job);
    this.logger.info(`📋 Job registriert: ${job.id} (${job.class})`);
  }

  // Job Execution
  async executeJob(jobId, context = {}) {
    const job = this.findJob(jobId);
    if (!job) {
      throw new Error(`Job ${jobId} nicht gefunden`);
    }

    // Security Check
    if (job.class === this.JOB_CLASSES.BLOCK) {
      return await this.handleBlockJob(job, context);
    }

    // Approval Check
    if (job.requiresApproval && job.class === this.JOB_CLASSES.APPROVE) {
      return await this.handleApprovalJob(job, context);
    }

    // Auto Job - direkte Ausführung
    return await this.handleAutoJob(job, context);
  }

  // Auto Jobs (lesen, prüfen, importieren)
  async handleAutoJob(job, context) {
    const executionId = this.generateExecutionId();
    this.runningJobs.add(executionId);

    try {
      this.logger.info(`🔄 Auto-Job startet: ${job.id} (${executionId})`);
      
      const result = await this.runJobWithTimeout(job, context, executionId);
      
      // Event emittieren
      this.emit('job:completed', {
        jobId: job.id,
        executionId,
        class: job.class,
        result,
        timestamp: new Date()
      });

      return { success: true, result, executionId };
    } catch (error) {
      this.logger.error(`❌ Auto-Job fehlgeschlagen: ${job.id}`, error);
      
      this.emit('job:failed', {
        jobId: job.id,
        executionId,
        class: job.class,
        error: error.message,
        timestamp: new Date()
      });

      return { success: false, error: error.message, executionId };
    } finally {
      this.runningJobs.delete(executionId);
    }
  }

  // Approval Jobs (kritische Aktionen)
  async handleApprovalJob(job, context) {
    const approvalId = this.generateApprovalId();
    
    const approvalRequest = {
      id: approvalId,
      jobId: job.id,
      class: job.class,
      context,
      status: 'pending',
      createdAt: new Date(),
      expiresAt: new Date(Date.now() + 24 * 60 * 60 * 1000), // 24h
      approvers: this.getApprovers(job),
      approvals: [],
      rejections: []
    };

    this.approvalQueue.set(approvalId, approvalRequest);

    // Notification senden
    await this.sendApprovalNotification(approvalRequest);

    this.logger.info(`⏳ Approval-Job wartet: ${job.id} (${approvalId})`);
    
    // Event emittieren
    this.emit('approval:requested', approvalRequest);

    return { 
      success: true, 
      approvalRequired: true, 
      approvalId,
      message: 'Job wartet auf Freigabe'
    };
  }

  // Block Jobs (nur mit manuellem Eingriff)
  async handleBlockJob(job, context) {
    this.logger.warn(`🚫 Block-Job blockiert: ${job.id}`);
    
    this.emit('job:blocked', {
      jobId: job.id,
      class: job.class,
      reason: 'Block-Job erfordert manuelle Freigabe',
      timestamp: new Date()
    });

    return { 
      success: false, 
      blocked: true,
      message: 'Block-Job erfordert manuelle Freigabe'
    };
  }

  // Job mit Timeout ausführen
  async runJobWithTimeout(job, context, executionId) {
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error(`Job Timeout nach ${job.timeout}ms`));
      }, job.timeout);

      job.handler(context, executionId)
        .then(result => {
          clearTimeout(timeout);
          job.lastRun = new Date();
          job.runCount++;
          resolve(result);
        })
        .catch(error => {
          clearTimeout(timeout);
          job.errors.push({
            timestamp: new Date(),
            error: error.message,
            executionId
          });
          reject(error);
        });
    });
  }

  // Approval System
  async approveJob(approvalId, approver, notes = '') {
    const approval = this.approvalQueue.get(approvalId);
    if (!approval) {
      throw new Error(`Approval ${approvalId} nicht gefunden`);
    }

    if (!approval.approvers.includes(approver)) {
      throw new Error(`${approver} ist kein berechtigter Approver`);
    }

    approval.approvals.push({ approver, notes, timestamp: new Date() });
    approval.status = this.calculateApprovalStatus(approval);

    if (approval.status === 'approved') {
      // Job ausführen
      const job = this.findJob(approval.jobId);
      const result = await this.handleAutoJob(job, approval.context);
      
      this.emit('approval:approved', { approval, result });
      return { success: true, result };
    }

    this.emit('approval:updated', approval);
    return { success: true, approval };
  }

  async rejectJob(approvalId, approver, reason = '') {
    const approval = this.approvalQueue.get(approvalId);
    if (!approval) {
      throw new Error(`Approval ${approvalId} nicht gefunden`);
    }

    approval.rejections.push({ approver, reason, timestamp: new Date() });
    approval.status = 'rejected';

    this.emit('approval:rejected', approval);
    return { success: true, approval };
  }

  // Scheduler
  startScheduler() {
    // Jede Minute prüfen
    cron.schedule('* * * * *', () => {
      this.checkScheduledJobs();
    });

    this.logger.info('⏰ Scheduler gestartet');
  }

  checkScheduledJobs() {
    for (const [moduleName, module] of this.moduleRegistry) {
      for (const [jobName, job] of module.jobs) {
        if (job.schedule && this.shouldRunJob(job)) {
          this.executeJob(job.id);
        }
      }
    }
  }

  shouldRunJob(job) {
    if (!job.schedule) return false;
    
    // Cron-Check
    return cron.validate(job.schedule) && cron.schedule(job.schedule, () => {});
  }

  // Helper Functions
  findJob(jobId) {
    const [moduleName, jobName] = jobId.split('.');
    const module = this.moduleRegistry.get(moduleName);
    return module ? module.jobs.get(jobName) : null;
  }

  generateExecutionId() {
    return `exec_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  generateApprovalId() {
    return `appr_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  getApprovers(job) {
    // Basierend auf Job-Klasse und Modul
    const baseApprovers = ['admin'];
    
    if (job.module === 'finance') {
      baseApprovers.push('finance_lead');
    }
    
    if (job.module === 'security') {
      baseApprovers.push('security_lead');
    }
    
    return baseApprovers;
  }

  calculateApprovalStatus(approval) {
    const requiredApprovers = approval.approvers.length;
    const approvalCount = approval.approvals.length;
    const rejectionCount = approval.rejections.length;

    if (rejectionCount > 0) return 'rejected';
    if (approvalCount >= requiredApprovers) return 'approved';
    return 'pending';
  }

  async sendApprovalNotification(approval) {
    if (this.telegramBot) {
      const message = `🔔 *Approval Required*\n\n` +
        `Job: ${approval.jobId}\n` +
        `Class: ${approval.class}\n` +
        `Approvers: ${approval.approvers.join(', ')}\n\n` +
        `Use: /approve ${approval.id} or /reject ${approval.id}`;
      
      await this.telegramBot.sendMessage(message);
    }
  }

  // Router für Express
  getRouter() {
    const express = require('express');
    const router = express.Router();

    // Job ausführen
    router.post('/jobs/:jobId/execute', async (req, res) => {
      try {
        const result = await this.executeJob(req.params.jobId, req.body);
        res.json(result);
      } catch (error) {
        res.status(500).json({ error: error.message });
      }
    });

    // Approval erteilen
    router.post('/approvals/:approvalId/approve', async (req, res) => {
      try {
        const { approver, notes } = req.body;
        const result = await this.approveJob(req.params.approvalId, approver, notes);
        res.json(result);
      } catch (error) {
        res.status(500).json({ error: error.message });
      }
    });

    // Approval ablehnen
    router.post('/approvals/:approvalId/reject', async (req, res) => {
      try {
        const { approver, reason } = req.body;
        const result = await this.rejectJob(req.params.approvalId, approver, reason);
        res.json(result);
      } catch (error) {
        res.status(500).json({ error: error.message });
      }
    });

    // Status abfragen
    router.get('/status', (req, res) => {
      const status = {
        modules: Array.from(this.moduleRegistry.entries()).map(([name, module]) => ({
          name,
          status: module.status,
          jobs: module.jobs.size,
          lastActivity: module.lastActivity
        })),
        runningJobs: this.runningJobs.size,
        pendingApprovals: this.approvalQueue.size,
        eventHistory: this.eventHistory.slice(-10)
      };
      res.json(status);
    });

    return router;
  }

  // Dashboard Router
  getDashboardRouter() {
    const express = require('express');
    const router = express.Router();

    // Dashboard HTML
    router.get('/', (req, res) => {
      res.send(this.generateDashboardHTML());
    });

    return router;
  }

  generateDashboardHTML() {
    return `
<!DOCTYPE html>
<html>
<head>
    <title>RUDIBOT Orchestrator Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-900 text-white p-6">
    <div class="max-w-7xl mx-auto">
        <h1 class="text-3xl font-bold mb-6">🤖 RUDIBOT Orchestrator</h1>
        
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            <div class="bg-gray-800 p-4 rounded">
                <h3 class="text-lg font-semibold mb-2">Module</h3>
                <div id="modules" class="space-y-2"></div>
            </div>
            
            <div class="bg-gray-800 p-4 rounded">
                <h3 class="text-lg font-semibold mb-2">Laufende Jobs</h3>
                <div id="running-jobs" class="space-y-2"></div>
            </div>
            
            <div class="bg-gray-800 p-4 rounded">
                <h3 class="text-lg font-semibold mb-2">Approvals</h3>
                <div id="approvals" class="space-y-2"></div>
            </div>
        </div>
        
        <div class="bg-gray-800 p-4 rounded">
            <h3 class="text-lg font-semibold mb-4">Event History</h3>
            <div id="events" class="space-y-2"></div>
        </div>
    </div>
    
    <script>
        // WebSocket oder Polling für Live-Updates
        setInterval(() => updateDashboard(), 5000);
        
        async function updateDashboard() {
            const response = await fetch('/orchestrator/status');
            const data = await response.json();
            
            updateModules(data.modules);
            updateRunningJobs(data.runningJobs);
            updateApprovals(data.pendingApprovals);
            updateEvents(data.eventHistory);
        }
        
        function updateModules(modules) {
            const container = document.getElementById('modules');
            container.innerHTML = modules.map(m => 
                \`<div class="flex justify-between">
                    <span>\${m.name}</span>
                    <span class="text-green-400">\${m.jobs} jobs</span>
                </div>\`
            ).join('');
        }
        
        function updateRunningJobs(count) {
            document.getElementById('running-jobs').innerHTML = 
                \`<div class="text-yellow-400">\${count} Jobs laufen</div>\`;
        }
        
        function updateApprovals(count) {
            document.getElementById('approvals').innerHTML = 
                \`<div class="text-orange-400">\${count} Approvals pending</div>\`;
        }
        
        function updateEvents(events) {
            const container = document.getElementById('events');
            container.innerHTML = events.map(e => 
                \`<div class="text-sm text-gray-300">
                    \${new Date(e.timestamp).toLocaleTimeString()}: \${e.type}
                </div>\`
            ).join('');
        }
        
        updateDashboard();
    </script>
</body>
</html>`;
  }
}

module.exports = { Orchestrator };
