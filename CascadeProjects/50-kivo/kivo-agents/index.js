/**
 * KIVO AGENTS — Complex Tasks, Multi-Step Workflows, Tool Calls
 * Agentic layer for sophisticated automation beyond simple commands
 */

const EventEmitter = require('events');

class KivoAgents extends EventEmitter {
  constructor() {
    super();
    this.workflows = new Map();
    this.activeRuns = new Map();
    this.tools = new Map();
    this.registerBuiltInTools();
  }

  // ── Tool Registry ──────────────────────────────────────────
  registerTool(name, handler, description = '') {
    this.tools.set(name, { name, handler, description });
  }

  registerBuiltInTools() {
    // Tool: summarize_subscriptions
    this.registerTool('summarize_subscriptions', async (ctx) => {
      // Calls subscription-hunter via Rudibot bridge
      return { action: 'call_rudibot', command: '/subs' };
    }, 'Lists all active subscriptions with costs');

    // Tool: find_killable_subscriptions
    this.registerTool('find_killable_subscriptions', async (ctx) => {
      return { action: 'call_rudibot', command: '/subs', filter: 'killable' };
    }, 'Finds subscriptions eligible for cancellation');

    // Tool: run_deepscan
    this.registerTool('run_deepscan', async (ctx) => {
      return { action: 'call_rudibot', command: '/deepscan' };
    }, 'Triggers a security deep scan');

    // Tool: generate_tax_report
    this.registerTool('generate_tax_report', async (ctx) => {
      const year = ctx.year || new Date().getFullYear();
      return { action: 'call_rudibot', command: '/tax', args: { year } };
    }, 'Generates tax status report');

    // Tool: export_elster
    this.registerTool('export_elster', async (ctx) => {
      const year = ctx.year || new Date().getFullYear();
      return { action: 'call_rudibot', command: '/elster', args: { year } };
    }, 'Prepares ELSTER export (requires approval)');

    // Tool: get_system_status
    this.registerTool('get_system_status', async (ctx) => {
      return { action: 'call_rudibot', command: '/status' };
    }, 'Gets overall system health status');
  }

  // ── Workflow Definition ────────────────────────────────────
  defineWorkflow(id, steps) {
    this.workflows.set(id, { id, steps, createdAt: new Date().toISOString() });
  }

  // ── Workflow Execution ─────────────────────────────────────
  async runWorkflow(workflowId, context = {}) {
    const workflow = this.workflows.get(workflowId);
    if (!workflow) throw new Error(`Workflow ${workflowId} not found`);

    const runId = `run-${Date.now()}`;
    const run = {
      id: runId,
      workflowId,
      status: 'running',
      startedAt: Date.now(),
      steps: [],
      context,
    };
    this.activeRuns.set(runId, run);
    this.emit('workflow:start', run);

    try {
      for (let i = 0; i < workflow.steps.length; i++) {
        const step = workflow.steps[i];
        const stepResult = await this.executeStep(step, run);
        run.steps.push({ step: i, ...stepResult });

        if (stepResult.requiresApproval) {
          run.status = 'awaiting_approval';
          this.emit('workflow:approval_required', { run, step: i, reason: stepResult.reason });
          return run; // Pause for approval
        }

        if (stepResult.error) {
          run.status = 'failed';
          run.error = stepResult.error;
          this.emit('workflow:failed', run);
          return run;
        }
      }

      run.status = 'completed';
      run.completedAt = Date.now();
      this.emit('workflow:complete', run);
    } catch (e) {
      run.status = 'failed';
      run.error = e.message;
      this.emit('workflow:failed', run);
    }

    return run;
  }

  async executeStep(step, run) {
    const start = Date.now();

    if (step.type === 'tool') {
      const tool = this.tools.get(step.tool);
      if (!tool) return { error: `Tool ${step.tool} not found`, duration: Date.now() - start };
      const result = await tool.handler({ ...run.context, ...step.args });
      return { type: 'tool', tool: step.tool, result, duration: Date.now() - start };
    }

    if (step.type === 'condition') {
      const condition = step.check(run.context);
      return { type: 'condition', result: condition, duration: Date.now() - start };
    }

    if (step.type === 'approval') {
      return { type: 'approval', requiresApproval: true, reason: step.reason || 'Approval required' };
    }

    if (step.type === 'notify') {
      return { type: 'notify', message: step.message, duration: Date.now() - start };
    }

    return { error: `Unknown step type: ${step.type}`, duration: Date.now() - start };
  }

  // ── Predefined Workflows ───────────────────────────────────
  setupDefaultWorkflows() {
    // Workflow: SaaS Cost Analysis
    this.defineWorkflow('saas_cost_analysis', [
      { type: 'tool', tool: 'summarize_subscriptions' },
      { type: 'condition', check: (ctx) => ctx.totalMonthly > 50 },
      { type: 'tool', tool: 'find_killable_subscriptions' },
      { type: 'approval', reason: 'Show top 3 most expensive killable subscriptions' },
    ]);

    // Workflow: Morning Briefing
    this.defineWorkflow('morning_briefing', [
      { type: 'tool', tool: 'get_system_status' },
      { type: 'tool', tool: 'summarize_subscriptions' },
      { type: 'notify', message: 'Morning briefing complete' },
    ]);

    // Workflow: Tax Preparation
    this.defineWorkflow('tax_preparation', [
      { type: 'tool', tool: 'generate_tax_report' },
      { type: 'approval', reason: 'Validate tax data before ELSTER export' },
      { type: 'tool', tool: 'export_elster' },
    ]);

    // Workflow: Security Audit
    this.defineWorkflow('security_audit', [
      { type: 'tool', tool: 'run_deepscan' },
      { type: 'notify', message: 'Deep scan initiated. Check /audit for results.' },
    ]);
  }

  // ── Status ─────────────────────────────────────────────────
  getStatus() {
    return {
      workflowsDefined: this.workflows.size,
      activeRuns: this.activeRuns.size,
      toolsRegistered: this.tools.size,
    };
  }
}

module.exports = { KivoAgents };
