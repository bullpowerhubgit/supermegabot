const { createOrchestratorRouter } = require('./router');
const { RiskEngine } = require('./risk-engine');
const { ApprovalEngine } = require('./approval-engine');
const { TaskQueue } = require('./task-queue');
const { WorkflowEngine } = require('./workflow-engine');
const { Scheduler } = require('../scheduler');
const { AssistantService } = require('../assistant-service');
const { CostMonitorService } = require('../cost-monitor-service');
const { SubscriptionOptimizer } = require('../subscription-optimizer');
const { PayPalImporter } = require('../importers/paypal-importer');
const { BankImporter } = require('../importers/bank-importer');
const { SubscriptionClassifier } = require('../subscription-classifier');
const { BrowserCancelAgent } = require('../browser-cancel-agent');
const { createDashboardRoutes } = require('../dashboard-routes');
const { InvoiceHunter } = require('../invoice-hunter');
const { ReminderService } = require('../reminder-service');
const { ProtectionList } = require('../protection-list');
const { CaseManager } = require('../case-manager');
const { ElsterAssistant } = require('../elster-assistant');
const { ExpenseRadar } = require('../expense-radar');
const { DemoOutput } = require('../demo-output');

class Orchestrator {
  constructor(options = {}) {
    this.logger = options.logger || console;
    
    // Initialize core components
    this.riskEngine = new RiskEngine({ logger: this.logger });
    this.approvalEngine = new ApprovalEngine({ 
      logger: this.logger,
      telegramBot: options.telegramBot
    });
    this.taskQueue = new TaskQueue({ logger: this.logger });
    this.workflowEngine = new WorkflowEngine({ 
      logger: this.logger,
      kivoCore: options.kivoCore
    });

    // Create router with all components
    this.router = createOrchestratorRouter({
      workflowEngine: this.workflowEngine,
      approvalEngine: this.approvalEngine,
      taskQueue: this.taskQueue,
      riskEngine: this.riskEngine,
      logger: this.logger
    });

    // Initialize scheduler (don't start yet)
    this.scheduler = new Scheduler({
      orchestrator: this,
      logger: this.logger
    });

    // Initialize assistant and cost monitor services
    this.assistantService = new AssistantService({
      orchestrator: this,
      logger: this.logger
    });
    this.costMonitorService = new CostMonitorService({
      orchestrator: this,
      logger: this.logger
    });
    this.subscriptionOptimizer = new SubscriptionOptimizer({
      orchestrator: this,
      logger: this.logger
    });

    // Initialize importers and classifier
    this.paypalImporter = new PayPalImporter({ logger: this.logger });
    this.bankImporter = new BankImporter({ logger: this.logger });
    this.subscriptionClassifier = new SubscriptionClassifier({ logger: this.logger });
    this.browserCancelAgent = new BrowserCancelAgent({
      logger: this.logger,
      approvalEngine: this.approvalEngine
    });
    this.invoiceHunter = new InvoiceHunter({ logger: this.logger });
    this.reminderService = new ReminderService({
      logger: this.logger,
      notificationChannels: ['console']
    });

    // Initialize new modules
    this.protectionList = new ProtectionList({ logger: this.logger });
    this.caseManager = new CaseManager({ logger: this.logger });
    this.elsterAssistant = new ElsterAssistant({ logger: this.logger });
    this.expenseRadar = new ExpenseRadar({ logger: this.logger });
    this.demoOutput = new DemoOutput({ logger: this.logger });
  }

  start() {
    // Start scheduler
    this.scheduler.start();
    
    // Start background processors
    this.startBackgroundProcessors();
    
    this.logger.info?.('orchestrator.started');
  }

  startBackgroundProcessors() {
    // Process queued tasks
    this.processQueue();
    
    // Cleanup expired approvals
    this.cleanupApprovals();
    
    // Cleanup old tasks
    this.cleanupTasks();
  }

  async processQueue() {
    setInterval(async () => {
      try {
        const task = await this.taskQueue.dequeue();
        if (task) {
          // Execute the job through workflow engine
          const result = await this.workflowEngine.execute(task.job);
          
          if (result.status === 'completed') {
            await this.taskQueue.complete(task.id, result);
          } else {
            await this.taskQueue.fail(task.id, new Error(result.error || 'Workflow execution failed'));
          }
        }
      } catch (err) {
        this.logger.error?.('orchestrator.queue.processing_failed', { error: err.message });
      }
    }, 5000); // Process every 5 seconds
  }

  async cleanupApprovals() {
    setInterval(async () => {
      try {
        await this.approvalEngine.cleanupExpired();
      } catch (err) {
        this.logger.error?.('orchestrator.approval.cleanup_failed', { error: err.message });
      }
    }, 60 * 60 * 1000); // Cleanup every hour
  }

  async cleanupTasks() {
    setInterval(async () => {
      try {
        await this.taskQueue.cleanup();
      } catch (err) {
        this.logger.error?.('orchestrator.task.cleanup_failed', { error: err.message });
      }
    }, 24 * 60 * 60 * 1000); // Cleanup daily
  }

  async submitCommand(command, source = 'unknown') {
    const response = await fetch('http://localhost:3200/orchestrator/command', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source,
        command,
        target: 'system'
      })
    });

    if (!response.ok) {
      throw new Error(`Command submission failed: ${response.status}`);
    }

    return response.json();
  }

  async submitEvent(event, source = 'system') {
    const response = await fetch('http://localhost:3200/orchestrator/event', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source,
        eventType: event,
        target: 'system'
      })
    });

    if (!response.ok) {
      throw new Error(`Event submission failed: ${response.status}`);
    }

    return response.json();
  }

  async getJobStatus(jobId) {
    const response = await fetch(`http://localhost:3200/orchestrator/jobs/${jobId}`);
    
    if (!response.ok) {
      throw new Error(`Job status fetch failed: ${response.status}`);
    }

    return response.json();
  }

  async approveJob(jobId, approvedBy, note = '') {
    const response = await fetch(`http://localhost:3200/orchestrator/approve/${jobId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approvedBy, note })
    });

    if (!response.ok) {
      throw new Error(`Job approval failed: ${response.status}`);
    }

    return response.json();
  }

  getRouter() {
    return this.router;
  }

  getDashboardRouter() {
    return createDashboardRoutes({
      subscriptionOptimizer: this.subscriptionOptimizer,
      subscriptionClassifier: this.subscriptionClassifier,
      costMonitorService: this.costMonitorService,
      assistantService: this.assistantService,
      paypalImporter: this.paypalImporter,
      bankImporter: this.bankImporter,
      browserCancelAgent: this.browserCancelAgent,
      invoiceHunter: this.invoiceHunter,
      reminderService: this.reminderService,
      protectionList: this.protectionList,
      caseManager: this.caseManager,
      elsterAssistant: this.elsterAssistant,
      expenseRadar: this.expenseRadar,
      demoOutput: this.demoOutput
    });
  }

  async getStatus() {
    const queueStats = await this.taskQueue.getQueueStats();
    const pendingApprovals = await this.approvalEngine.getPendingApprovals();
    const schedulerStatus = this.scheduler ? this.scheduler.getStatus() : null;
    
    return {
      orchestrator: 'running',
      components: {
        riskEngine: 'active',
        approvalEngine: 'active',
        taskQueue: 'active',
        workflowEngine: 'active',
        scheduler: schedulerStatus ? (schedulerStatus.isRunning ? 'running' : 'stopped') : 'unknown'
      },
      stats: {
        queue: queueStats,
        pendingApprovals: pendingApprovals.length,
        workflows: this.workflowEngine.getWorkflows().length,
        activeLoops: schedulerStatus ? schedulerStatus.activeLoops.length : 0
      }
    };
  }
}

module.exports = { Orchestrator };
