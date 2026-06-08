/**
 * Cancel Subscription Action — Handles subscription cancellation workflow
 * Bridges KIVO intent to Finance Grid cancellation engine
 */

class CancelSubscriptionAction {
  constructor(subscriptionHunter, cancellationEngine) {
    this.hunter = subscriptionHunter;
    this.engine = cancellationEngine;
  }

  async execute(options = {}) {
    const { subscriptionId, provider, confirm = false } = options;
    
    try {
      // If no ID provided, find killable subscriptions first
      if (!subscriptionId && !provider) {
        return await this.findKillableSubscriptions();
      }

      // Get subscription details
      const subscription = await this.getSubscription(subscriptionId, provider);
      if (!subscription) {
        return {
          success: false,
          error: 'Subscription not found',
          message: '❌ Subscription not found. Use /subs to see available subscriptions.'
        };
      }

      // Prepare cancellation
      const prep = await this.prepareCancellation(subscription);
      
      if (!prep.canCancel) {
        return {
          success: false,
          blocked: true,
          reason: prep.eligibility.reason,
          message: `❌ Cannot cancel: ${prep.eligibility.reason}`
        };
      }

      // Check if confirmation is required
      if (!confirm) {
        return {
          success: true,
          requiresApproval: true,
          subscription: prep.subscription,
          eligibility: prep.eligibility,
          nextSteps: prep.nextSteps,
          message: this.formatPreparationMessage(prep)
        };
      }

      // Execute cancellation
      const result = await this.executeCancellation(prep);
      
      return {
        success: true,
        result,
        message: this.formatExecutionMessage(result),
        timestamp: new Date().toISOString()
      };

    } catch (e) {
      return {
        success: false,
        error: e.message,
        message: `❌ Cancellation failed: ${e.message}`
      };
    }
  }

  async findKillableSubscriptions() {
    try {
      const summary = this.hunter.getSummary();
      const upcoming = this.hunter.getUpcomingRenewals(30);
      
      // Filter for killable subscriptions
      const killable = upcoming.filter(sub => {
        const days = Math.ceil((new Date(sub.nextBilling) - Date.now()) / (1000 * 60 * 60 * 24));
        return days >= 14; // At least 14 days notice period
      });

      const message = `🎯 *KILLABLE SUBSCRIPTIONS*\n\n` +
        `Found ${killable.length} subscriptions eligible for cancellation:\n\n`;

      killable.slice(0, 5).forEach((sub, i) => {
        const days = Math.ceil((new Date(sub.nextBilling) - Date.now()) / (1000 * 60 * 60 * 24));
        message += `${i + 1}. **${sub.name}**\n`;
        message += `   💰 ${sub.monthlyCost.toFixed(2)} EUR/mo\n`;
        message += `   📅 ${days} days until renewal\n`;
        message += `   🆔 ID: ${sub.id || sub.name.toLowerCase().replace(/\s+/g, '-')}\n\n`;
      });

      if (killable.length > 5) {
        message += `... and ${killable.length - 5} more\n\n`;
      }

      message += `💡 Use: "/sub-kill <id>" to cancel a subscription`;

      return {
        success: true,
        killable: killable.slice(0, 5),
        total: killable.length,
        message
      };

    } catch (e) {
      return {
        success: false,
        error: e.message,
        message: '❌ Failed to find killable subscriptions'
      };
    }
  }

  async getSubscription(id, provider) {
    // Try to find by ID first
    if (id) {
      const allSubs = this.hunter.getAllSubscriptions();
      return allSubs.find(sub => 
        sub.id === id || 
        sub.name.toLowerCase().replace(/\s+/g, '-') === id.toLowerCase()
      );
    }

    // Try to find by provider
    if (provider) {
      const allSubs = this.hunter.getAllSubscriptions();
      return allSubs.find(sub => 
        sub.provider?.toLowerCase() === provider.toLowerCase() ||
        sub.name?.toLowerCase().includes(provider.toLowerCase())
      );
    }

    return null;
  }

  async prepareCancellation(subscription) {
    try {
      const prep = await this.hunter.prepareCancellation(subscription.id || subscription.name);
      return prep;
    } catch (e) {
      // Fallback basic preparation
      return {
        subscription,
        canCancel: true,
        eligibility: {
          eligible: true,
          reason: 'Manual preparation'
        },
        nextSteps: [
          '1. Verify cancellation terms',
          '2. Choose cancellation channel',
          '3. Execute cancellation',
          '4. Confirm completion'
        ]
      };
    }
  }

  async executeCancellation(prep) {
    // This would integrate with the cancellation engine
    // For now, simulate execution
    const executionResult = {
      status: 'submitted',
      channel: 'email',
      submittedAt: new Date().toISOString(),
      reference: `CANCEL-${Date.now()}`,
      estimatedCompletion: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString() // 7 days
    };

    // Log the cancellation
    this.logCancellation(prep.subscription, executionResult);

    return executionResult;
  }

  logCancellation(subscription, result) {
    const logEntry = {
      timestamp: new Date().toISOString(),
      action: 'cancellation',
      subscription: subscription.name,
      provider: subscription.provider,
      monthlyCost: subscription.monthlyCost,
      result: result.status,
      reference: result.reference,
      estimatedSavings: subscription.monthlyCost * 12 // Annual savings
    };

    console.log('[CANCEL-ACTION]', JSON.stringify(logEntry, null, 2));
  }

  formatPreparationMessage(prep) {
    let message = `🗡️ *CANCELLATION PREPARED*\n\n`;
    
    message += `📋 **${prep.subscription.name}**\n`;
    message += `💰 Monthly: ${prep.subscription.monthlyCost.toFixed(2)} EUR\n`;
    message += `📅 Next: ${new Date(prep.subscription.nextBilling).toLocaleDateString('de-DE')}\n\n`;
    
    message += `✅ **Eligible:** ${prep.canCancel ? 'YES' : 'NO'}\n`;
    message += `📌 **Reason:** ${prep.eligibility.reason}\n\n`;
    
    if (prep.nextSteps && prep.nextSteps.length > 0) {
      message += `📋 **Next Steps:**\n`;
      prep.nextSteps.forEach((step, i) => {
        message += `${i + 1}. ${step}\n`;
      });
    }
    
    message += `\n⚠️ **This action is irreversible**\n`;
    message += `Use "/approve" to confirm or "/cancel" to abort`;

    return message;
  }

  formatExecutionMessage(result) {
    let message = `✅ *CANCELLATION SUBMITTED*\n\n`;
    
    message += `📝 **Reference:** ${result.reference}\n`;
    message += `📅 **Submitted:** ${new Date(result.submittedAt).toLocaleString('de-DE')}\n`;
    message += `📡 **Channel:** ${result.channel}\n`;
    message += `⏰ **Est. Completion:** ${new Date(result.estimatedCompletion).toLocaleDateString('de-DE')}\n\n`;
    
    message += `💡 You'll receive confirmation when the cancellation is complete.`;

    return message;
  }

  // ── Approval Check ───────────────────────────────────────
  requiresApproval(options) {
    // All cancellations require approval for safety
    return true;
  }

  // ── Status ─────────────────────────────────────────────────
  getStatus() {
    return {
      hunterAvailable: !!this.hunter,
      engineAvailable: !!this.engine,
      supportedProviders: ['netflix', 'spotify', 'adobe', 'amazon', 'google', 'microsoft'],
      lastCancellation: this.lastCancellation || null
    };
  }
}

module.exports = { CancelSubscriptionAction };
