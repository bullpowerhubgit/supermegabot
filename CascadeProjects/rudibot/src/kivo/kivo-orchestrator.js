/**
 * KIVO Orchestrator — Central workflow coordinator
 * Manages multi-step workflows, tool calls, and session continuity
 */

const EventEmitter = require('events');

class KivoOrchestrator extends EventEmitter {
  constructor(kivoCore, sessionStore, actions) {
    super();
    this.core = kivoCore;
    this.sessions = sessionStore;
    this.actions = actions;
    this.workflows = new Map();
    this.activeRuns = new Map();
    this.setupDefaultWorkflows();
  }

  setupDefaultWorkflows() {
    // Workflow: Morning Briefing
    this.workflows.set('morning_briefing', {
      id: 'morning_briefing',
      name: 'Morning Briefing',
      steps: [
        { type: 'action', action: 'dashboard', method: 'getStatusReport', args: { scope: 'all' } },
        { type: 'action', action: 'dashboard', method: 'getHealthReport', args: { scope: 'all' } },
        { type: 'condition', check: (ctx) => ctx.finance.upcomingRenewals > 0 },
        { type: 'action', action: 'finance', method: 'getUpcomingRenewals', condition: true },
        { type: 'notify', message: 'Morning briefing complete' }
      ]
    });

    // Workflow: SaaS Cost Analysis
    this.workflows.set('saas_cost_analysis', {
      id: 'saas_cost_analysis',
      name: 'SaaS Cost Analysis',
      steps: [
        { type: 'action', action: 'finance', method: 'getAllSubscriptions' },
        { type: 'condition', check: (ctx) => ctx.totalMonthly > 50 },
        { type: 'action', action: 'finance', method: 'findKillableSubscriptions', condition: true },
        { type: 'approval', reason: 'Show top 3 most expensive killable subscriptions' }
      ]
    });

    // Workflow: Tax Preparation
    this.workflows.set('tax_preparation', {
      id: 'tax_preparation',
      name: 'Tax Preparation',
      steps: [
        { type: 'action', action: 'finance', method: 'getTaxStatus' },
        { type: 'condition', check: (ctx) => ctx.documents.length > 0 },
        { type: 'approval', reason: 'Validate tax data before ELSTER export' },
        { type: 'action', action: 'tax', method: 'prepareExport', condition: true }
      ]
    });

    // Workflow: Security Audit
    this.workflows.set('security_audit', {
      id: 'security_audit',
      name: 'Security Audit',
      steps: [
        { type: 'action', action: 'security', method: 'runQuickScan' },
        { type: 'condition', check: (ctx) => ctx.findings.length > 0 },
        { type: 'action', action: 'security', method: 'runFullScan', condition: true },
        { type: 'notify', message: 'Deep scan completed. Check /audit for results.' }
      ]
    });

    // Workflow: Home Evening Mode
    this.workflows.set('home_evening_mode', {
      id: 'home_evening_mode',
      name: 'Home Evening Mode',
      steps: [
        { type: 'action', action: 'home', method: 'turnOffAllLights' },
        { type: 'action', action: 'home', method: 'setTemperature', args: { temp: 19 } },
        { type: 'action', action: 'home', method: 'lockAllDoors' },
        { type: 'notify', message: 'Evening mode activated' }
      ]
    });

    // Workflow: Subscription Cleanup
    this.workflows.set('subscription_cleanup', {
      id: 'subscription_cleanup',
      name: 'Subscription Cleanup',
      steps: [
        { type: 'action', action: 'finance', method: 'getAllSubscriptions' },
        { type: 'action', action: 'finance', method: 'findUnusedSubscriptions' },
        { type: 'approval', reason: 'Cancel unused subscriptions to save money' }
      ]
    });
  }

  // ── Workflow Execution ─────────────────────────────────────
  async runWorkflow(workflowId, chatId, context = {}) {
    const workflow = this.workflows.get(workflowId);
    if (!workflow) {
      throw new Error(`Workflow ${workflowId} not found`);
    }

    const runId = `run_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    
    const run = {
      id: runId,
      workflowId,
      chatId,
      status: 'running',
      startedAt: Date.now(),
      steps: [],
      context,
      currentStep: 0
    };

    this.activeRuns.set(runId, run);
    this.emit('workflow:start', run);
    this.sessions.addToHistory(chatId, { type: 'workflow_start', workflowId });

    try {
      for (let i = 0; i < workflow.steps.length; i++) {
        run.currentStep = i;
        const step = workflow.steps[i];
        const stepResult = await this.executeStep(step, run);
        
        run.steps.push({
          step: i,
          type: step.type,
          result: stepResult,
          timestamp: Date.now()
        });

        // Handle approval requirement
        if (stepResult.requiresApproval) {
          run.status = 'awaiting_approval';
          this.emit('workflow:approval_required', { run, step: i, reason: stepResult.reason });
          
          // Store workflow state for resume
          this.sessions.setContext(chatId, 'pendingWorkflow', {
            runId,
            stepIndex: i,
            workflowId
          });
          
          return this.formatPendingResponse(run, stepResult);
        }

        // Handle errors
        if (stepResult.error) {
          run.status = 'failed';
          run.error = stepResult.error;
          this.emit('workflow:failed', run);
          this.sessions.addToHistory(chatId, { type: 'workflow_failed', workflowId, error: stepResult.error });
          return this.formatErrorResponse(run, stepResult);
        }

        // Update context with step results
        Object.assign(run.context, stepResult.data || {});
      }

      run.status = 'completed';
      run.completedAt = Date.now();
      this.emit('workflow:complete', run);
      this.sessions.addToHistory(chatId, { type: 'workflow_complete', workflowId });
      this.activeRuns.delete(runId);
      
      return this.formatSuccessResponse(run);

    } catch (e) {
      run.status = 'failed';
      run.error = e.message;
      this.emit('workflow:failed', run);
      this.sessions.addToHistory(chatId, { type: 'workflow_error', workflowId, error: e.message });
      return this.formatErrorResponse(run, { error: e.message });
    }
  }

  async executeStep(step, run) {
    const start = Date.now();

    switch (step.type) {
      case 'action':
        return await this.executeActionStep(step, run);
      
      case 'condition':
        const conditionResult = step.check(run.context);
        return {
          type: 'condition',
          result: conditionResult,
          skipped: !conditionResult && step.condition,
          duration: Date.now() - start
        };
      
      case 'approval':
        return {
          type: 'approval',
          requiresApproval: true,
          reason: step.reason,
          duration: Date.now() - start
        };
      
      case 'notify':
        return {
          type: 'notify',
          message: step.message,
          duration: Date.now() - start
        };
      
      default:
        return { error: `Unknown step type: ${step.type}`, duration: Date.now() - start };
    }
  }

  async executeActionStep(step, run) {
    const { action, method, args = {} } = step;
    const actionModule = this.actions[action];
    
    if (!actionModule) {
      return { error: `Action module ${action} not found` };
    }

    if (!actionModule[method]) {
      return { error: `Method ${method} not found in ${action}` };
    }

    try {
      const result = await actionModule[method]({ ...args, chatId: run.chatId, context: run.context });
      return {
        type: 'action',
        action,
        method,
        success: true,
        data: result,
        duration: Date.now() - 0 // placeholder
      };
    } catch (e) {
      return {
        type: 'action',
        action,
        method,
        success: false,
        error: e.message
      };
    }
  }

  // ── Resume Workflow After Approval ─────────────────────────
  async resumeWorkflow(runId, chatId, approved = true) {
    const run = this.activeRuns.get(runId);
    if (!run) {
      return { error: 'Workflow not found or expired' };
    }

    if (!approved) {
      run.status = 'cancelled';
      this.activeRuns.delete(runId);
      this.sessions.addToHistory(chatId, { type: 'workflow_cancelled', runId });
      return { status: 'cancelled', message: 'Workflow cancelled by user' };
    }

    // Resume from next step
    run.currentStep++;
    
    // Continue execution
    const workflow = this.workflows.get(run.workflowId);
    
    for (let i = run.currentStep; i < workflow.steps.length; i++) {
      run.currentStep = i;
      const step = workflow.steps[i];
      const stepResult = await this.executeStep(step, run);
      
      run.steps.push({
        step: i,
        type: step.type,
        result: stepResult,
        timestamp: Date.now()
      });

      if (stepResult.requiresApproval) {
        run.status = 'awaiting_approval';
        return this.formatPendingResponse(run, stepResult);
      }

      if (stepResult.error) {
        run.status = 'failed';
        return this.formatErrorResponse(run, stepResult);
      }

      Object.assign(run.context, stepResult.data || {});
    }

    run.status = 'completed';
    run.completedAt = Date.now();
    this.activeRuns.delete(runId);
    return this.formatSuccessResponse(run);
  }

  // ── Workflow Management ──────────────────────────────────
  defineWorkflow(id, config) {
    this.workflows.set(id, { id, ...config });
  }

  getWorkflow(id) {
    return this.workflows.get(id);
  }

  listWorkflows() {
    return Array.from(this.workflows.values()).map(w => ({
      id: w.id,
      name: w.name,
      steps: w.steps.length
    }));
  }

  getActiveRun(runId) {
    return this.activeRuns.get(runId);
  }

  getActiveRuns() {
    return Array.from(this.activeRuns.values());
  }

  cancelRun(runId) {
    const run = this.activeRuns.get(runId);
    if (run) {
      run.status = 'cancelled';
      this.activeRuns.delete(runId);
      return { cancelled: true, runId };
    }
    return { error: 'Run not found' };
  }

  // ── Response Formatters ──────────────────────────────────
  formatSuccessResponse(run) {
    const workflow = this.workflows.get(run.workflowId);
    const stepResults = run.steps
      .filter(s => s.result.success || s.result.message)
      .map(s => s.result.message || s.result.data?.message || '')
      .filter(Boolean);

    return {
      success: true,
      workflow: workflow.name,
      status: 'completed',
      steps: run.steps.length,
      duration: run.completedAt - run.startedAt,
      results: stepResults,
      message: `✅ *${workflow.name} completed*\n\n${stepResults.join('\n\n')}`
    };
  }

  formatPendingResponse(run, stepResult) {
    const workflow = this.workflows.get(run.workflowId);
    
    return {
      success: true,
      workflow: workflow.name,
      status: 'awaiting_approval',
      step: run.currentStep,
      reason: stepResult.reason,
      message: `⏸️ *${workflow.name} paused*\n\n${stepResult.reason}\n\nUse /approve to continue or /cancel to abort.`,
      runId: run.id
    };
  }

  formatErrorResponse(run, stepResult) {
    const workflow = this.workflows.get(run.workflowId);
    
    return {
      success: false,
      workflow: workflow.name,
      status: 'failed',
      error: stepResult.error,
      step: run.currentStep,
      message: `❌ *${workflow.name} failed*\n\nStep ${run.currentStep + 1}: ${stepResult.error}`,
      runId: run.id
    };
  }

  // ── Status ───────────────────────────────────────────────
  getStatus() {
    return {
      workflowsDefined: this.workflows.size,
      activeRuns: this.activeRuns.size,
      completedRuns: this.sessions.getStats().totalHistoryEntries || 0
    };
  }
}

module.exports = { KivoOrchestrator };
