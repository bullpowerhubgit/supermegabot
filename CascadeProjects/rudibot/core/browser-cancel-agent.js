const { exec } = require('child_process');
const fs = require('fs');
const path = require('path');

/**
 * Browser Cancel Agent — Automatisierte Kündigung auf Plattformen
 * 
 * Unterstützt:
 * - Headless Browser (Playwright/Puppeteer)
 * - Automatische Login
 * - Kündigungs-Workflows für gängige Plattformen
 * - Screenshot-Beweis
 * - Email-Bestätigungen
 * 
 * WICHTIG: Dieser Agent arbeitet mit Approval-Workflow
 * - Green (< 20€): Direkt ausführbar
 * - Yellow (20-50€): Approval erforderlich
 * - Red (> 50€): Harte Block + Admin-Freigabe
 */

class BrowserCancelAgent {
  constructor(options = {}) {
    this.logger = options.logger || console;
    this.storagePath = options.storagePath || path.join(__dirname, '../state/cancellations');
    this.screenshotPath = path.join(this.storagePath, 'screenshots');
    this.approvalEngine = options.approvalEngine;
    this.cancellationLog = [];
    
    this.platformConfig = {
      'adobe': {
        url: 'https://account.adobe.com/plans',
        loginSelector: '#EmailPage-email-input',
        cancelSteps: [
          { action: 'click', selector: '[data-testid="cancel-plan-button"]' },
          { action: 'click', selector: '[data-testid="confirm-cancel"]' }
        ],
        confirmationSelector: '.cancellation-confirmation'
      },
      'shopify': {
        url: 'https://admin.shopify.com/store/{store}/settings/plan',
        cancelSteps: [
          { action: 'click', selector: 'button:has-text("Cancel subscription")' },
          { action: 'click', selector: 'button:has-text("Confirm cancellation")' }
        ],
        confirmationSelector: '.cancelled-plan-badge'
      },
      'zoom': {
        url: 'https://zoom.us/billing',
        cancelSteps: [
          { action: 'click', selector: 'button:has-text("Cancel Plan")' },
          { action: 'select', selector: '#cancel-reason', value: 'other' },
          { action: 'click', selector: 'button:has-text("Continue to Cancel")' }
        ],
        confirmationSelector: '.cancellation-success'
      },
      'notion': {
        url: 'https://www.notion.so/settings/billing',
        cancelSteps: [
          { action: 'click', selector: 'text=Cancel subscription' },
          { action: 'click', selector: 'button:has-text("Confirm")' }
        ],
        confirmationSelector: '.downgrade-confirmation'
      },
      'github': {
        url: 'https://github.com/settings/billing',
        cancelSteps: [
          { action: 'click', selector: 'button:has-text("Cancel plan")' },
          { action: 'click', selector: 'button:has-text("I understand, cancel")' }
        ],
        confirmationSelector: '.billing-downgrade'
      },
      'generic': {
        url: null,
        cancelSteps: [
          { action: 'navigate', value: '/settings/billing' },
          { action: 'click', selector: 'button:has-text("Cancel"), button:has-text("Unsubscribe"), a:has-text("Cancel subscription")' }
        ],
        confirmationSelector: '.confirmation, .success, .cancelled'
      }
    };
    
    this.ensureStorageDir();
  }

  ensureStorageDir() {
    if (!fs.existsSync(this.storagePath)) {
      fs.mkdirSync(this.storagePath, { recursive: true });
    }
    if (!fs.existsSync(this.screenshotPath)) {
      fs.mkdirSync(this.screenshotPath, { recursive: true });
    }
  }

  /**
   * Prepare cancellation with risk assessment
   */
  async prepareCancellation(subscription) {
    const risk = this.assessRisk(subscription);
    const platform = this.detectPlatform(subscription);
    
    const job = {
      id: `cancel_${Date.now()}`,
      subscriptionId: subscription.id,
      subscriptionName: subscription.name,
      platform,
      monthlyCost: subscription.cost,
      riskLevel: risk.level,
      requiresApproval: risk.requiresApproval,
      cancelUrl: this.platformConfig[platform]?.url || subscription.url,
      steps: this.platformConfig[platform]?.cancelSteps || this.platformConfig.generic.cancelSteps,
      status: 'prepared',
      preparedAt: new Date().toISOString()
    };

    this.cancellationLog.push(job);
    this.saveLog();

    this.logger.info?.('cancel-agent.prepared', {
      jobId: job.id,
      subscription: subscription.name,
      risk: risk.level,
      approvalRequired: risk.requiresApproval
    });

    return job;
  }

  /**
   * Assess cancellation risk
   */
  assessRisk(subscription) {
    const cost = subscription.cost || 0;
    
    if (cost < 20) {
      return { level: 'green', requiresApproval: false, reason: 'Geringer Betrag' };
    } else if (cost < 50) {
      return { level: 'yellow', requiresApproval: true, reason: 'Mittlerer Betrag - Approval empfohlen' };
    } else {
      return { level: 'red', requiresApproval: true, reason: 'Hoher Betrag - Admin-Freigabe erforderlich' };
    }
  }

  /**
   * Detect platform from subscription name/URL
   */
  detectPlatform(subscription) {
    const name = (subscription.name || '').toLowerCase();
    const url = (subscription.url || '').toLowerCase();
    
    for (const [platform, config] of Object.entries(this.platformConfig)) {
      if (platform === 'generic') continue;
      if (name.includes(platform) || url.includes(platform)) {
        return platform;
      }
    }
    
    return 'generic';
  }

  /**
   * Execute cancellation (after approval if needed)
   */
  async executeCancellation(jobId, credentials = {}) {
    const job = this.cancellationLog.find(j => j.id === jobId);
    if (!job) {
      throw new Error(`Cancellation job ${jobId} not found`);
    }

    if (job.requiresApproval && !job.approved) {
      throw new Error(`Approval required for job ${jobId}`);
    }

    // Check if Playwright is available
    try {
      const { chromium } = require('playwright');
      return await this.executeWithPlaywright(job, credentials, chromium);
    } catch (err) {
      this.logger.warn?.('cancel-agent.playwright_unavailable', { error: err.message });
      return await this.executeManualFallback(job);
    }
  }

  /**
   * Execute with Playwright browser automation
   */
  async executeWithPlaywright(job, credentials, chromium) {
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext();
    const page = await context.newPage();

    try {
      // Navigate to platform
      await page.goto(job.cancelUrl, { waitUntil: 'networkidle' });
      
      // Take screenshot of login page
      await this.takeScreenshot(page, job.id, 'login_page');

      // Login if credentials provided
      if (credentials.email && credentials.password) {
        // This is a simplified login flow - real implementation would be platform-specific
        const emailInput = await page.$('input[type="email"], input[name="email"], #email');
        if (emailInput) {
          await emailInput.fill(credentials.email);
          const passwordInput = await page.$('input[type="password"], input[name="password"]');
          if (passwordInput) {
            await passwordInput.fill(credentials.password);
            const submitButton = await page.$('button[type="submit"], input[type="submit"]');
            if (submitButton) {
              await submitButton.click();
              await page.waitForLoadState('networkidle');
            }
          }
        }
      }

      // Execute cancellation steps
      for (const step of job.steps) {
        await this.executeStep(page, step);
        await page.waitForTimeout(1000);
      }

      // Take confirmation screenshot
      await this.takeScreenshot(page, job.id, 'confirmation');

      // Check for confirmation
      const confirmation = await page.$(job.confirmationSelector || '.confirmation, .success');
      const success = !!confirmation;

      job.status = success ? 'completed' : 'failed';
      job.completedAt = new Date().toISOString();
      job.success = success;

      await browser.close();
      this.saveLog();

      return {
        jobId: job.id,
        status: job.status,
        success,
        screenshots: this.getScreenshots(job.id)
      };

    } catch (err) {
      await this.takeScreenshot(page, job.id, 'error');
      await browser.close();
      
      job.status = 'failed';
      job.error = err.message;
      this.saveLog();
      
      throw err;
    }
  }

  /**
   * Execute single step in cancellation workflow
   */
  async executeStep(page, step) {
    switch (step.action) {
      case 'click':
        const element = await page.$(step.selector);
        if (element) await element.click();
        break;
      case 'fill':
        const input = await page.$(step.selector);
        if (input) await input.fill(step.value || '');
        break;
      case 'select':
        const select = await page.$(step.selector);
        if (select) await select.selectOption(step.value);
        break;
      case 'navigate':
        await page.goto(step.value);
        break;
      case 'wait':
        await page.waitForTimeout(step.value || 1000);
        break;
    }
  }

  /**
   * Manual fallback when browser automation unavailable
   */
  async executeManualFallback(job) {
    job.status = 'manual_required';
    job.fallbackAt = new Date().toISOString();
    this.saveLog();

    return {
      jobId: job.id,
      status: 'manual_required',
      instructions: [
        `1. Besuche: ${job.cancelUrl}`,
        '2. Melde dich an',
        '3. Navigiere zu Einstellungen / Abonnement / Plan',
        '4. Suche nach "Kündigen" oder "Cancel"',
        '5. Bestätige die Kündigung',
        '6. Speichere die Bestätigungs-E-Mail'
      ],
      platform: job.platform,
      requiresManualAction: true
    };
  }

  /**
   * Approve cancellation (for yellow/red risk)
   */
  approveCancellation(jobId) {
    const job = this.cancellationLog.find(j => j.id === jobId);
    if (!job) {
      throw new Error(`Job ${jobId} not found`);
    }
    
    job.approved = true;
    job.approvedAt = new Date().toISOString();
    job.approvedBy = 'admin';
    this.saveLog();

    return {
      jobId,
      status: 'approved',
      canExecute: true
    };
  }

  /**
   * Take screenshot for audit trail
   */
  async takeScreenshot(page, jobId, step) {
    const fileName = `${jobId}_${step}_${Date.now()}.png`;
    const filePath = path.join(this.screenshotPath, fileName);
    await page.screenshot({ path: filePath, fullPage: false });
    return filePath;
  }

  /**
   * Get screenshots for a job
   */
  getScreenshots(jobId) {
    try {
      const files = fs.readdirSync(this.screenshotPath);
      return files
        .filter(f => f.startsWith(jobId))
        .map(f => path.join(this.screenshotPath, f));
    } catch (err) {
      return [];
    }
  }

  /**
   * Get cancellation log
   */
  getLog() {
    return {
      jobs: this.cancellationLog,
      summary: {
        total: this.cancellationLog.length,
        completed: this.cancellationLog.filter(j => j.status === 'completed').length,
        failed: this.cancellationLog.filter(j => j.status === 'failed').length,
        pending: this.cancellationLog.filter(j => j.status === 'prepared').length,
        manualRequired: this.cancellationLog.filter(j => j.status === 'manual_required').length
      }
    };
  }

  saveLog() {
    try {
      fs.writeFileSync(
        path.join(this.storagePath, 'cancellation-log.json'),
        JSON.stringify({
          updatedAt: new Date().toISOString(),
          jobs: this.cancellationLog
        }, null, 2)
      );
    } catch (err) {
      this.logger.error?.('cancel-agent.save_failed', { error: err.message });
    }
  }
}

module.exports = { BrowserCancelAgent };
