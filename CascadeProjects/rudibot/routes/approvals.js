/**
 * Approvals Routes
 * Approval management, review, and action endpoints
 */

function registerApprovalRoutes(app, { context }) {
  // List pending approvals
  app.get('/approvals', async (req, res) => {
    try {
      const { status = 'pending', limit = 50, offset = 0 } = req.query;

      if (!context || !context.getService) {
        return res.json({
          approvals: [],
          total: 0,
          limit,
          offset,
          timestamp: new Date().toISOString()
        });
      }

      const approvalService = context.getService('approval');
      if (!approvalService) {
        return res.json({
          approvals: [],
          total: 0,
          limit,
          offset,
          timestamp: new Date().toISOString()
        });
      }

      const approvals = await approvalService.getApprovals(status, limit, offset);

      res.json({
        approvals,
        total: approvals.length,
        limit,
        offset,
        timestamp: new Date().toISOString()
      });
    } catch (error) {
      console.error('List approvals failed:', error);
      res.status(500).json({
        error: error.message,
        timestamp: new Date().toISOString()
      });
    }
  });

  // Get specific approval details
  app.get('/approvals/:approvalId', async (req, res) => {
    try {
      const { approvalId } = req.params;

      if (!context || !context.getService) {
        return res.status(500).json({
          error: 'Context not available',
          timestamp: new Date().toISOString()
        });
      }

      const approvalService = context.getService('approval');
      if (!approvalService) {
        return res.status(500).json({
          error: 'Approval service not available',
          timestamp: new Date().toISOString()
        });
      }

      const approval = await approvalService.getApproval(approvalId);
      if (!approval) {
        return res.status(404).json({
          error: `Approval not found: ${approvalId}`,
          timestamp: new Date().toISOString()
        });
      }

      res.json(approval);
    } catch (error) {
      console.error('Get approval failed:', error);
      res.status(500).json({
        error: error.message,
        timestamp: new Date().toISOString()
      });
    }
  });

  // Approve a request
  app.post('/approvals/:approvalId/approve', async (req, res) => {
    try {
      const { approvalId } = req.params;
      const { approver, notes = '', force = false } = req.body;

      if (!approver) {
        return res.status(400).json({
          error: 'approver is required',
          timestamp: new Date().toISOString()
        });
      }

      if (!context || !context.getService) {
        return res.status(500).json({
          error: 'Context not available',
          timestamp: new Date().toISOString()
        });
      }

      const approvalService = context.getService('approval');
      if (!approvalService) {
        return res.status(500).json({
          error: 'Approval service not available',
          timestamp: new Date().toISOString()
        });
      }

      // Get approval details first
      const approval = await approvalService.getApproval(approvalId);
      if (!approval) {
        return res.status(404).json({
          error: `Approval not found: ${approvalId}`,
          timestamp: new Date().toISOString()
        });
      }

      // Check if approval is still pending
      if (approval.status !== 'pending' && !force) {
        return res.status(400).json({
          error: `Approval already ${approval.status}`,
          timestamp: new Date().toISOString()
        });
      }

      // Approve the request
      const result = await approvalService.approve(approvalId, {
        approver,
        notes,
        approvedAt: new Date(),
        ipAddress: req.ip,
        userAgent: req.get('User-Agent')
      });

      // Execute the approved job if applicable
      let executionResult = null;
      if (result.jobName && context.orchestrator) {
        try {
          executionResult = await context.orchestrator.executeJob(result.jobName, {
            ...approval.context,
            approvedBy: approver,
            approvalId
          });
        } catch (execError) {
          console.error('Approved job execution failed:', execError);
          executionResult = {
            error: execError.message,
            status: 'execution_failed'
          };
        }
      }

      // Send notification
      if (context.getService && context.getService('notification')) {
        const notification = context.getService('notification');
        await notification.telegram.sendMessage(
          `✅ Approval granted: ${approval.jobName}\n` +
          `Approved by: ${approver}\n` +
          `Notes: ${notes}`
        );
      }

      res.json({
        success: true,
        approvalId,
        jobName: approval.jobName,
        approvedBy: approver,
        approvedAt: result.approvedAt,
        executionResult,
        timestamp: new Date().toISOString()
      });
    } catch (error) {
      console.error('Approve request failed:', error);
      res.status(500).json({
        error: error.message,
        timestamp: new Date().toISOString()
      });
    }
  });

  // Reject a request
  app.post('/approvals/:approvalId/reject', async (req, res) => {
    try {
      const { approvalId } = req.params;
      const { approver, reason = '', force = false } = req.body;

      if (!approver) {
        return res.status(400).json({
          error: 'approver is required',
          timestamp: new Date().toISOString()
        });
      }

      if (!reason && !force) {
        return res.status(400).json({
          error: 'reason is required for rejection',
          timestamp: new Date().toISOString()
        });
      }

      if (!context || !context.getService) {
        return res.status(500).json({
          error: 'Context not available',
          timestamp: new Date().toISOString()
        });
      }

      const approvalService = context.getService('approval');
      if (!approvalService) {
        return res.status(500).json({
          error: 'Approval service not available',
          timestamp: new Date().toISOString()
        });
      }

      // Get approval details first
      const approval = await approvalService.getApproval(approvalId);
      if (!approval) {
        return res.status(404).json({
          error: `Approval not found: ${approvalId}`,
          timestamp: new Date().toISOString()
        });
      }

      // Check if approval is still pending
      if (approval.status !== 'pending' && !force) {
        return res.status(400).json({
          error: `Approval already ${approval.status}`,
          timestamp: new Date().toISOString()
        });
      }

      // Reject the request
      const result = await approvalService.reject(approvalId, {
        approver,
        reason,
        rejectedAt: new Date(),
        ipAddress: req.ip,
        userAgent: req.get('User-Agent')
      });

      // Send notification
      if (context.getService && context.getService('notification')) {
        const notification = context.getService('notification');
        await notification.telegram.sendMessage(
          `❌ Approval rejected: ${approval.jobName}\n` +
          `Rejected by: ${approver}\n` +
          `Reason: ${reason}`
        );
      }

      res.json({
        success: true,
        approvalId,
        jobName: approval.jobName,
        rejectedBy: approver,
        rejectedAt: result.rejectedAt,
        reason,
        timestamp: new Date().toISOString()
      });
    } catch (error) {
      console.error('Reject request failed:', error);
      res.status(500).json({
        error: error.message,
        timestamp: new Date().toISOString()
      });
    }
  });

  // Create approval request
  app.post('/approvals', async (req, res) => {
    try {
      const { 
        jobName, 
        context: jobContext = {}, 
        requestedBy, 
        description = '',
        approvers = [],
        expiresAt 
      } = req.body;

      if (!jobName) {
        return res.status(400).json({
          error: 'jobName is required',
          timestamp: new Date().toISOString()
        });
      }

      if (!requestedBy) {
        return res.status(400).json({
          error: 'requestedBy is required',
          timestamp: new Date().toISOString()
        });
      }

      if (!context || !context.getService) {
        return res.status(500).json({
          error: 'Context not available',
          timestamp: new Date().toISOString()
        });
      }

      const approvalService = context.getService('approval');
      if (!approvalService) {
        return res.status(500).json({
          error: 'Approval service not available',
          timestamp: new Date().toISOString()
        });
      }

      // Create approval request
      const approval = await approvalService.createRequest({
        jobName,
        context: jobContext,
        requestedBy,
        description,
        approvers,
        expiresAt: expiresAt || new Date(Date.now() + 24 * 60 * 60 * 1000), // 24 hours default
        createdAt: new Date(),
        ipAddress: req.ip,
        userAgent: req.get('User-Agent')
      });

      // Send notification to approvers
      if (approvers.length > 0 && context.getService && context.getService('notification')) {
        const notification = context.getService('notification');
        await notification.telegram.sendMessage(
          `🔔 Approval required: ${jobName}\n` +
          `Requested by: ${requestedBy}\n` +
          `Description: ${description}\n` +
          `Approval ID: ${approval.id}`
        );
      }

      res.status(201).json({
        success: true,
        approval,
        timestamp: new Date().toISOString()
      });
    } catch (error) {
      console.error('Create approval failed:', error);
      res.status(500).json({
        error: error.message,
        timestamp: new Date().toISOString()
      });
    }
  });

  // Get approval statistics
  app.get('/approvals/stats', async (req, res) => {
    try {
      if (!context || !context.getService) {
        return res.json({
          stats: {
            total: 0,
            pending: 0,
            approved: 0,
            rejected: 0,
            expired: 0
          },
          timestamp: new Date().toISOString()
        });
      }

      const approvalService = context.getService('approval');
      if (!approvalService) {
        return res.json({
          stats: {
            total: 0,
            pending: 0,
            approved: 0,
            rejected: 0,
            expired: 0
          },
          timestamp: new Date().toISOString()
        });
      }

      const stats = await approvalService.getStatistics();

      res.json({
        stats,
        timestamp: new Date().toISOString()
      });
    } catch (error) {
      console.error('Get approval stats failed:', error);
      res.status(500).json({
        error: error.message,
        timestamp: new Date().toISOString()
      });
    }
  });

  // Get approval history
  app.get('/approvals/history', async (req, res) => {
    try {
      const { limit = 50, offset = 0, jobName, approver } = req.query;

      if (!context || !context.getService) {
        return res.json({
          history: [],
          total: 0,
          limit,
          offset,
          timestamp: new Date().toISOString()
        });
      }

      const approvalService = context.getService('approval');
      if (!approvalService) {
        return res.json({
          history: [],
          total: 0,
          limit,
          offset,
          timestamp: new Date().toISOString()
        });
      }

      const history = await approvalService.getHistory({
        limit: parseInt(limit),
        offset: parseInt(offset),
        jobName,
        approver
      });

      res.json({
        history,
        total: history.length,
        limit,
        offset,
        timestamp: new Date().toISOString()
      });
    } catch (error) {
      console.error('Get approval history failed:', error);
      res.status(500).json({
        error: error.message,
        timestamp: new Date().toISOString()
      });
    }
  });

  // Cancel approval request
  app.delete('/approvals/:approvalId', async (req, res) => {
    try {
      const { approvalId } = req.params;
      const { cancelledBy, reason = '' } = req.body;

      if (!cancelledBy) {
        return res.status(400).json({
          error: 'cancelledBy is required',
          timestamp: new Date().toISOString()
        });
      }

      if (!context || !context.getService) {
        return res.status(500).json({
          error: 'Context not available',
          timestamp: new Date().toISOString()
        });
      }

      const approvalService = context.getService('approval');
      if (!approvalService) {
        return res.status(500).json({
          error: 'Approval service not available',
          timestamp: new Date().toISOString()
        });
      }

      // Get approval details first
      const approval = await approvalService.getApproval(approvalId);
      if (!approval) {
        return res.status(404).json({
          error: `Approval not found: ${approvalId}`,
          timestamp: new Date().toISOString()
        });
      }

      // Check if approval is still pending
      if (approval.status !== 'pending') {
        return res.status(400).json({
          error: `Cannot cancel approval in ${approval.status} status`,
          timestamp: new Date().toISOString()
        });
      }

      // Cancel the approval
      const result = await approvalService.cancel(approvalId, {
        cancelledBy,
        reason,
        cancelledAt: new Date()
      });

      // Send notification
      if (context.getService && context.getService('notification')) {
        const notification = context.getService('notification');
        await notification.telegram.sendMessage(
          `🚫 Approval cancelled: ${approval.jobName}\n` +
          `Cancelled by: ${cancelledBy}\n` +
          `Reason: ${reason}`
        );
      }

      res.json({
        success: true,
        approvalId,
        jobName: approval.jobName,
        cancelledBy,
        cancelledAt: result.cancelledAt,
        reason,
        timestamp: new Date().toISOString()
      });
    } catch (error) {
      console.error('Cancel approval failed:', error);
      res.status(500).json({
        error: error.message,
        timestamp: new Date().toISOString()
      });
    }
  });

  // Escalate approval
  app.post('/approvals/:approvalId/escalate', async (req, res) => {
    try {
      const { approvalId } = req.params;
      const { escalatedBy, reason = '', level = 'high' } = req.body;

      if (!escalatedBy) {
        return res.status(400).json({
          error: 'escalatedBy is required',
          timestamp: new Date().toISOString()
        });
      }

      if (!context || !context.getService) {
        return res.status(500).json({
          error: 'Context not available',
          timestamp: new Date().toISOString()
        });
      }

      const approvalService = context.getService('approval');
      if (!approvalService) {
        return res.status(500).json({
          error: 'Approval service not available',
          timestamp: new Date().toISOString()
        });
      }

      // Get approval details first
      const approval = await approvalService.getApproval(approvalId);
      if (!approval) {
        return res.status(404).json({
          error: `Approval not found: ${approvalId}`,
          timestamp: new Date().toISOString()
        });
      }

      // Escalate the approval
      const result = await approvalService.escalate(approvalId, {
        escalatedBy,
        reason,
        level,
        escalatedAt: new Date()
      });

      // Send notification
      if (context.getService && context.getService('notification')) {
        const notification = context.getService('notification');
        await notification.telegram.sendMessage(
          `🚨 Approval escalated: ${approval.jobName}\n` +
          `Escalated by: ${escalatedBy}\n` +
          `Level: ${level}\n` +
          `Reason: ${reason}`
        );
      }

      res.json({
        success: true,
        approvalId,
        jobName: approval.jobName,
        escalatedBy,
        escalatedAt: result.escalatedAt,
        level,
        reason,
        timestamp: new Date().toISOString()
      });
    } catch (error) {
      console.error('Escalate approval failed:', error);
      res.status(500).json({
        error: error.message,
        timestamp: new Date().toISOString()
      });
    }
  });
}

module.exports = { registerApprovalRoutes };
