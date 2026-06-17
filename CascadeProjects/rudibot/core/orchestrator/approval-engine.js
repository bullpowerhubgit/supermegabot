const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

class ApprovalEngine {
  constructor(options = {}) {
    this.storagePath = options.storagePath || path.join(__dirname, '../../state/approvals');
    this.logger = options.logger || console;
    this.telegramBot = options.telegramBot;
    this.ensureStorageDir();
  }

  ensureStorageDir() {
    if (!fs.existsSync(this.storagePath)) {
      fs.mkdirSync(this.storagePath, { recursive: true });
    }
  }

  async requestApproval(job) {
    const approval = {
      id: crypto.randomUUID(),
      jobId: job.jobId,
      job,
      status: 'pending',
      requestedAt: new Date().toISOString(),
      expiresAt: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(), // 24h expiry
      approvedBy: null,
      approvedAt: null,
      note: null,
      correlationId: job.correlationId
    };

    // Save to storage
    await this.saveApproval(approval);

    // Send notification if Telegram bot is available
    if (this.telegramBot) {
      await this.notifyTelegram(approval);
    }

    this.logger.info?.('approval.requested', {
      approvalId: approval.id,
      jobId: job.jobId,
      action: job.action,
      correlationId: job.correlationId
    });

    return {
      status: 'awaiting_approval',
      approvalId: approval.id,
      expiresAt: approval.expiresAt
    };
  }

  async approve({ jobId, approvedBy, note, correlationId }) {
    const approval = await this.getApprovalByJobId(jobId);
    
    if (!approval) {
      throw new Error(`No pending approval found for job ${jobId}`);
    }

    if (approval.status !== 'pending') {
      throw new Error(`Approval ${approval.id} is not pending (current: ${approval.status})`);
    }

    if (new Date() > new Date(approval.expiresAt)) {
      throw new Error(`Approval ${approval.id} has expired`);
    }

    // Update approval
    approval.status = 'approved';
    approval.approvedBy = approvedBy;
    approval.approvedAt = new Date().toISOString();
    approval.note = note;

    await this.saveApproval(approval);

    this.logger.info?.('approval.granted', {
      approvalId: approval.id,
      jobId,
      approvedBy,
      correlationId
    });

    return {
      status: 'approved',
      approvalId: approval.id,
      approvedAt: approval.approvedAt
    };
  }

  async reject({ jobId, rejectedBy, reason, correlationId }) {
    const approval = await this.getApprovalByJobId(jobId);
    
    if (!approval) {
      throw new Error(`No pending approval found for job ${jobId}`);
    }

    if (approval.status !== 'pending') {
      throw new Error(`Approval ${approval.id} is not pending (current: ${approval.status})`);
    }

    // Update approval
    approval.status = 'rejected';
    approval.rejectedBy = rejectedBy;
    approval.rejectedAt = new Date().toISOString();
    approval.reason = reason;

    await this.saveApproval(approval);

    this.logger.info?.('approval.rejected', {
      approvalId: approval.id,
      jobId,
      rejectedBy,
      reason,
      correlationId
    });

    return {
      status: 'rejected',
      approvalId: approval.id,
      rejectedAt: approval.rejectedAt
    };
  }

  async getStatus(jobId) {
    const approval = await this.getApprovalByJobId(jobId);
    
    if (!approval) {
      return { status: 'no_approval_required' };
    }

    return {
      status: approval.status,
      approvalId: approval.id,
      requestedAt: approval.requestedAt,
      expiresAt: approval.expiresAt,
      approvedAt: approval.approvedAt,
      approvedBy: approval.approvedBy
    };
  }

  async getApprovalByJobId(jobId) {
    try {
      const files = fs.readdirSync(this.storagePath);
      for (const file of files) {
        if (file.endsWith('.json')) {
          const content = fs.readFileSync(path.join(this.storagePath, file), 'utf8');
          const approval = JSON.parse(content);
          if (approval.jobId === jobId) {
            return approval;
          }
        }
      }
    } catch (err) {
      this.logger.error?.('approval.get_by_job_id.failed', { jobId, error: err.message });
    }
    
    return null;
  }

  async saveApproval(approval) {
    const filePath = path.join(this.storagePath, `${approval.id}.json`);
    fs.writeFileSync(filePath, JSON.stringify(approval, null, 2));
  }

  async notifyTelegram(approval) {
    if (!this.telegramBot) return;

    const message = `🔔 *Approval Required*

*Job ID:* \`${approval.jobId}\`
*Action:* ${approval.job.action}
*Source:* ${approval.job.source}
*Target:* ${approval.job.target}

*Expires:* ${new Date(approval.expiresAt).toLocaleString('de')}

Approve with: \`/approve ${approval.jobId}\`
Reject with: \`/reject ${approval.jobId}\`

*Correlation ID:* ${approval.correlationId}`;

    try {
      await this.telegramBot.sendMessage(process.env.ADMIN_CHAT_ID || process.env.AUTHORIZED_USER_ID, message);
    } catch (err) {
      this.logger.error?.('approval.telegram.notification_failed', {
        approvalId: approval.id,
        error: err.message
      });
    }
  }

  async cleanupExpired() {
    try {
      const files = fs.readdirSync(this.storagePath);
      const now = new Date();
      let cleaned = 0;

      for (const file of files) {
        if (file.endsWith('.json')) {
          const filePath = path.join(this.storagePath, file);
          const content = fs.readFileSync(filePath, 'utf8');
          const approval = JSON.parse(content);

          if (approval.status === 'pending' && new Date(approval.expiresAt) < now) {
            approval.status = 'expired';
            fs.writeFileSync(filePath, JSON.stringify(approval, null, 2));
            cleaned++;
          }
        }
      }

      if (cleaned > 0) {
        this.logger.info?.('approval.cleanup.completed', { expired: cleaned });
      }

      return cleaned;
    } catch (err) {
      this.logger.error?.('approval.cleanup.failed', { error: err.message });
      return 0;
    }
  }

  async getPendingApprovals() {
    try {
      const files = fs.readdirSync(this.storagePath);
      const pending = [];

      for (const file of files) {
        if (file.endsWith('.json')) {
          const content = fs.readFileSync(path.join(this.storagePath, file), 'utf8');
          const approval = JSON.parse(content);

          if (approval.status === 'pending') {
            pending.push(approval);
          }
        }
      }

      return pending;
    } catch (err) {
      this.logger.error?.('approval.get_pending.failed', { error: err.message });
      return [];
    }
  }
}

module.exports = { ApprovalEngine };
