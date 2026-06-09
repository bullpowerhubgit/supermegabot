const express = require('express');
const crypto = require('crypto');

function createOrchestratorRouter({
  workflowEngine,
  approvalEngine,
  taskQueue,
  riskEngine,
  logger = console
}) {
  const router = express.Router();

  // Middleware for correlation ID and timestamp
  router.use((req, res, next) => {
    req.correlationId = req.headers['x-correlation-id'] || crypto.randomUUID();
    req.receivedAt = new Date().toISOString();
    next();
  });

  // Health endpoint
  router.get('/health', (req, res) => {
    res.json({
      ok: true,
      service: 'orchestrator-router',
      correlationId: req.correlationId,
      timestamp: req.receivedAt
    });
  });

  // Command endpoint (Telegram/Rudibot/KIVO commands)
  router.post('/command', async (req, res, next) => {
    try {
      const payload = req.body || {};
      if (!payload || typeof payload !== 'object') {
        return res.status(400).json({ ok: false, error: 'invalid_payload' });
      }

      const job = normalizeJob({
        type: 'command',
        source: payload.source || 'unknown',
        action: payload.action || payload.command || 'unknown_command',
        target: payload.target || 'system',
        payload,
        correlationId: req.correlationId
      });

      job.riskLevel = riskEngine?.classify?.(job) || 'yellow';

      logger.info?.('orchestrator.command.received', {
        correlationId: req.correlationId,
        jobId: job.jobId,
        action: job.action,
        riskLevel: job.riskLevel
      });

      const result = await dispatchJob({ job, workflowEngine, approvalEngine, taskQueue });

      res.json({
        ok: true,
        correlationId: req.correlationId,
        job,
        result
      });
    } catch (err) {
      next(err);
    }
  });

  // Event endpoint (internal system events/webhooks)
  router.post('/event', async (req, res, next) => {
    try {
      const payload = req.body || {};
      if (!payload || typeof payload !== 'object') {
        return res.status(400).json({ ok: false, error: 'invalid_payload' });
      }

      const job = normalizeJob({
        type: 'event',
        source: payload.source || 'system',
        action: payload.eventType || payload.action || 'unknown_event',
        target: payload.target || 'system',
        payload,
        correlationId: req.correlationId
      });

      job.riskLevel = riskEngine?.classify?.(job) || 'green';

      const result = await dispatchJob({ job, workflowEngine, approvalEngine, taskQueue });

      res.json({
        ok: true,
        correlationId: req.correlationId,
        jobId: job.jobId,
        status: result.status
      });
    } catch (err) {
      next(err);
    }
  });

  // Approval endpoint
  router.post('/approve/:jobId', async (req, res, next) => {
    try {
      if (!approvalEngine?.approve) {
        return res.status(501).json({ ok: false, error: 'approval_engine_not_available' });
      }

      const result = await approvalEngine.approve({
        jobId: req.params.jobId,
        approvedBy: req.body?.approvedBy || 'unknown',
        note: req.body?.note || '',
        correlationId: req.correlationId
      });

      res.json({
        ok: true,
        correlationId: req.correlationId,
        result
      });
    } catch (err) {
      next(err);
    }
  });

  // Job status endpoint
  router.get('/jobs/:jobId', async (req, res, next) => {
    try {
      if (!taskQueue?.getStatus) {
        return res.status(501).json({ ok: false, error: 'task_queue_status_not_available' });
      }

      const status = await taskQueue.getStatus(req.params.jobId);

      res.json({
        ok: true,
        correlationId: req.correlationId,
        status
      });
    } catch (err) {
      next(err);
    }
  });

  // Assistant endpoints
  router.post('/assistant/help', async (req, res, next) => {
    try {
      const { query, context } = req.body || {};
      
      if (!query) {
        return res.status(400).json({ ok: false, error: 'query_required' });
      }

      // This would integrate with the assistant service
      const result = {
        ok: true,
        correlationId: req.correlationId,
        response: `Assistant help for: ${query}`,
        suggestions: [
          'Check system health',
          'Review recent costs',
          'Validate current workflow'
        ],
        context: context || {}
      };

      res.json(result);
    } catch (err) {
      next(err);
    }
  });

  router.post('/assistant/validate-form', async (req, res, next) => {
    try {
      const { data, templateType } = req.body || {};
      
      if (!data || !templateType) {
        return res.status(400).json({ ok: false, error: 'data_and_template_required' });
      }

      // This would integrate with the assistant service
      const result = {
        ok: true,
        correlationId: req.correlationId,
        validation: {
          warnings: ['Sample warning'],
          suggestions: ['Sample suggestion'],
          autofill: { country: 'DE' },
          risk_level: 'yellow'
        }
      };

      res.json(result);
    } catch (err) {
      next(err);
    }
  });

  router.post('/assistant/suggest', async (req, res, next) => {
    try {
      const { context } = req.body || {};
      
      const result = {
        ok: true,
        correlationId: req.correlationId,
        suggestions: {
          immediate: ['Immediate suggestion'],
          proactive: ['Proactive suggestion'],
          optimization: ['Optimization suggestion']
        }
      };

      res.json(result);
    } catch (err) {
      next(err);
    }
  });

  // Dashboard endpoints
  router.get('/dashboard/revenue', async (req, res, next) => {
    try {
      // This would integrate with cost monitor service
      const result = {
        ok: true,
        correlationId: req.correlationId,
        revenue: {
          today: 1200,
          last7Days: { total: 8400, average: 1200, growth: 5.2 },
          last30Days: { total: 36000, average: 1200 }
        }
      };

      res.json(result);
    } catch (err) {
      next(err);
    }
  });

  router.get('/dashboard/costs', async (req, res, next) => {
    try {
      const result = {
        ok: true,
        correlationId: req.correlationId,
        costs: {
          grandTotal: 1030,
          breakdown: [
            { category: 'saas_tools', total: 450, percentage: 43.7 },
            { category: 'apis', total: 180, percentage: 17.5 },
            { category: 'infrastructure', total: 120, percentage: 11.7 },
            { category: 'marketing', total: 280, percentage: 27.2 }
          ],
          alerts: [
            { type: 'warning', message: 'Cost increase detected' }
          ]
        }
      };

      res.json(result);
    } catch (err) {
      next(err);
    }
  });

  router.get('/dashboard/health', async (req, res, next) => {
    try {
      const result = {
        ok: true,
        correlationId: req.correlationId,
        health: {
          score: 85,
          status: 'good',
          metrics: {
            monthlyRevenue: 1200,
            monthlyCosts: 1030,
            monthlyProfit: 170,
            profitMargin: 14.2
          },
          recommendations: [
            { priority: 'medium', message: 'Review SaaS tool usage' }
          ]
        }
      };

      res.json(result);
    } catch (err) {
      next(err);
    }
  });

  // Subscription Optimizer endpoints
  router.get('/subscriptions', async (req, res, next) => {
    try {
      // This would integrate with subscription optimizer service
      const result = {
        ok: true,
        correlationId: req.correlationId,
        subscriptions: [
          { id: 'sub_shopify', name: 'Shopify Basic', cost: 29, status: 'active' },
          { id: 'sub_hubspot', name: 'HubSpot Marketing', cost: 120, status: 'active' },
          { id: 'sub_adobe', name: 'Adobe Creative Cloud', cost: 60, status: 'active' }
        ],
        totalMonthly: 308
      };

      res.json(result);
    } catch (err) {
      next(err);
    }
  });

  router.get('/subscriptions/analyze', async (req, res, next) => {
    try {
      const result = {
        ok: true,
        correlationId: req.correlationId,
        analysis: {
          immediateCancel: [
            { id: 'sub_adobe', name: 'Adobe Creative Cloud', cost: 60, reason: 'Nicht genutzt seit 85 Tagen' }
          ],
          considerCancel: [
            { id: 'sub_hubspot', name: 'HubSpot Marketing', cost: 120, reason: 'Wenig genutzt: 19 Tage her' }
          ],
          potentialSavings: 180
        }
      };

      res.json(result);
    } catch (err) {
      next(err);
    }
  });

  router.post('/subscriptions/cancel/:id', async (req, res, next) => {
    try {
      const { id } = req.params;
      const { reason } = req.body || {};

      const result = {
        ok: true,
        correlationId: req.correlationId,
        cancellation: {
          id: `cancel_${Date.now()}`,
          subscriptionId: id,
          reason: reason || 'Automatisch: Wenig/Nicht genutzt',
          status: 'prepared',
          requiresApproval: true,
          message: 'Kündigung vorbereitet. Freigabe erforderlich für Kosten > 50€.'
        }
      };

      res.json(result);
    } catch (err) {
      next(err);
    }
  });

  router.get('/subscriptions/reminders', async (req, res, next) => {
    try {
      const result = {
        ok: true,
        correlationId: req.correlationId,
        reminders: [
          {
            id: 'rem_001',
            subscriptionId: 'sub_zoom',
            name: 'Zoom Pro',
            deadline: '2026-06-03',
            daysLeft: 0,
            action: 'Kündigungsfrist läuft heute ab!'
          }
        ]
      };

      res.json(result);
    } catch (err) {
      next(err);
    }
  });

  // Error handling middleware
  router.use((err, req, res, next) => {
    logger.error?.('orchestrator.error', {
      correlationId: req.correlationId,
      error: err.message,
      stack: err.stack
    });

    res.status(500).json({
      ok: false,
      correlationId: req.correlationId,
      error: 'internal_server_error'
    });
  });

  return router;
}

function normalizeJob({ type, source, action, target, payload, correlationId }) {
  return {
    jobId: crypto.randomUUID(),
    type,
    source,
    action,
    target,
    payload,
    correlationId,
    status: 'received',
    createdAt: new Date().toISOString()
  };
}

async function dispatchJob({ job, workflowEngine, approvalEngine, taskQueue }) {
  if (job.riskLevel === 'red') {
    if (!approvalEngine?.requestApproval) {
      return { status: 'blocked', reason: 'approval_engine_missing' };
    }

    return approvalEngine.requestApproval(job);
  }

  if (job.riskLevel === 'yellow') {
    if (approvalEngine?.requestApproval) {
      return approvalEngine.requestApproval(job);
    }

    if (taskQueue?.enqueue) {
      return taskQueue.enqueue(job);
    }

    return { status: 'queued_without_approval_engine' };
  }

  if (workflowEngine?.execute) {
    return workflowEngine.execute(job);
  }

  if (taskQueue?.enqueue) {
    return taskQueue.enqueue(job);
  }

  return { status: 'received_no_executor' };
}

module.exports = { createOrchestratorRouter };
