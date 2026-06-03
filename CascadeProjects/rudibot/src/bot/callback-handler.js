/**
 * Callback Handler — Processes inline keyboard callbacks
 * Handles approval/cancel actions for KIVO workflows
 */

class CallbackHandler {
  constructor(kivoCore, commandHandler) {
    this.kivo = kivoCore;
    this.commands = commandHandler;
    this.pendingApprovals = new Map();
  }

  async handleCallback(callback, chatId) {
    const { data, message } = callback;
    
    if (data.startsWith('approve_')) {
      return this.handleApprove(data, chatId);
    }
    
    if (data.startsWith('cancel_')) {
      return this.handleCancel(data, chatId);
    }
    
    if (data.startsWith('home_')) {
      return this.handleHomeAction(data, chatId);
    }
    
    return { handled: false, error: 'Unknown callback' };
  }

  async handleApprove(data, chatId) {
    const actionId = data.replace('approve_', '');
    const approval = this.pendingApprovals.get(actionId);
    
    if (!approval) {
      return { message: '❌ Approval expired or not found' };
    }

    try {
      // Execute the approved action
      const result = await this.executeApprovedAction(approval);
      
      // Remove from pending
      this.pendingApprovals.delete(actionId);
      
      return { 
        message: `✅ *APPROVED*\n\n${approval.description}\n\nResult: ${result.message || 'Success'}`,
        editMessage: approval.messageId
      };
    } catch (e) {
      return { message: `❌ Approval failed: ${e.message}` };
    }
  }

  async handleCancel(data, chatId) {
    const actionId = data.replace('cancel_', '');
    const approval = this.pendingApprovals.get(actionId);
    
    if (!approval) {
      return { message: '❌ Action not found' };
    }

    this.pendingApprovals.delete(actionId);
    
    return { 
      message: `❌ *CANCELLED*\n\n${approval.description}\n\nAction aborted.`,
      editMessage: approval.messageId
    };
  }

  async handleHomeAction(data, chatId) {
    const action = data.replace('home_', '');
    
    switch (action) {
      case 'lights_on':
        return this.executeHomeAction('lights', 'on', chatId);
      case 'lights_off':
        return this.executeHomeAction('lights', 'off', chatId);
      case 'timer_10':
        return this.executeHomeAction('timer', 10, chatId);
      case 'timer_30':
        return this.executeHomeAction('timer', 30, chatId);
      default:
        return { message: '❌ Unknown home action' };
    }
  }

  async executeHomeAction(device, action, chatId) {
    // TODO: Integrate with Home Assistant
    const actions = {
      'lights': { on: 'Licht eingeschaltet', off: 'Licht ausgeschaltet' },
      'timer': { 10: 'Timer 10 Minuten gestellt', 30: 'Timer 30 Minuten gestellt' }
    };

    const result = actions[device]?.[action];
    if (result) {
      return { message: `🏠 *HOME ACTION*\n\n${result}` };
    }

    return { message: '❌ Home action failed' };
  }

  async executeApprovedAction(approval) {
    switch (approval.type) {
      case 'subscription_kill':
        return this.commands.getHandler('/sub-kill')(approval.chatId, approval.args);
      case 'elster_export':
        return this.commands.getHandler('/elster')(approval.chatId);
      case 'deepscan':
        return this.commands.getHandler('/deepscan')(approval.chatId);
      default:
        throw new Error(`Unknown approval type: ${approval.type}`);
    }
  }

  createPendingApproval(type, description, args, chatId) {
    const id = `approval_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    
    this.pendingApprovals.set(id, {
      id,
      type,
      description,
      args,
      chatId,
      createdAt: Date.now()
    });

    // Auto-expire after 5 minutes
    setTimeout(() => {
      this.pendingApprovals.delete(id);
    }, 5 * 60 * 1000);

    return id;
  }

  getApprovalButtons(actionId) {
    return [
      { text: '✅ Approve', callback_data: `approve_${actionId}` },
      { text: '❌ Cancel', callback_data: `cancel_${actionId}` }
    ];
  }

  getHomeButtons() {
    return [
      [{ text: '💡 Lights On', callback_data: 'home_lights_on' }],
      [{ text: '🌑 Lights Off', callback_data: 'home_lights_off' }],
      [{ text: '⏰ Timer 10m', callback_data: 'home_timer_10' }],
      [{ text: '⏰ Timer 30m', callback_data: 'home_timer_30' }]
    ];
  }

  // Cleanup expired approvals
  cleanupExpiredApprovals() {
    const now = Date.now();
    const expired = [];
    
    for (const [id, approval] of this.pendingApprovals) {
      if (now - approval.createdAt > 5 * 60 * 1000) {
        expired.push(id);
      }
    }
    
    expired.forEach(id => this.pendingApprovals.delete(id));
    return expired.length;
  }

  getStatus() {
    return {
      pendingApprovals: this.pendingApprovals.size,
      totalProcessed: this.totalProcessed || 0
    };
  }
}

module.exports = { CallbackHandler };
