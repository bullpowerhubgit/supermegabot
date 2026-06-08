/**
 * KIVO Reply — Response formatting and delivery
 * Formats KIVO responses for Telegram with proper markdown and keyboards
 */

class KivoReply {
  constructor() {
    this.responseTemplates = new Map();
    this.setupTemplates();
  }

  setupTemplates() {
    // Home control responses
    this.responseTemplates.set('home.control', (result) => ({
      text: `🏠 *HOME CONTROL*\n\n${result.message}`,
      keyboard: this.getHomeKeyboard()
    }));

    this.responseTemplates.set('home.climate', (result) => ({
      text: `🌡️ *CLIMATE CONTROL*\n\n${result.message}`,
      keyboard: this.getClimateKeyboard()
    }));

    this.responseTemplates.set('home.timer', (result) => ({
      text: `⏰ *TIMER SET*\n\n${result.message}`,
      keyboard: null
    }));

    this.responseTemplates.set('home.access', (result) => ({
      text: `🔓 *ACCESS CONTROL*\n\n${result.message}`,
      keyboard: this.getAccessKeyboard()
    }));

    // Agent responses
    this.responseTemplates.set('agent.subscription', (result) => ({
      text: `💰 *SUBSCRIPTION MANAGEMENT*\n\n${result.message}`,
      keyboard: result.requiresApproval ? this.getApprovalKeyboard() : this.getSubscriptionKeyboard()
    }));

    this.responseTemplates.set('agent.finance', (result) => ({
      text: `📋 *FINANCE OPERATIONS*\n\n${result.message}`,
      keyboard: result.requiresApproval ? this.getApprovalKeyboard() : this.getFinanceKeyboard()
    }));

    this.responseTemplates.set('agent.security', (result) => ({
      text: `🔍 *SECURITY OPERATIONS*\n\n${result.message}`,
      keyboard: this.getSecurityKeyboard()
    }));

    this.responseTemplates.set('agent.report', (result) => ({
      text: `📊 *STATUS REPORT*\n\n${result.message}`,
      keyboard: this.getReportKeyboard()
    }));

    // Rudibot responses
    this.responseTemplates.set('rudibot.command', (result) => ({
      text: `🤖 *RUDIBOT COMMAND*\n\n${result.message}`,
      keyboard: this.getRudibotKeyboard()
    }));

    // Fallback
    this.responseTemplates.set('unknown', (result) => ({
      text: `🤔 *KIVO*\n\n${result.message}`,
      keyboard: this.getHelpKeyboard()
    }));
  }

  // ── Response Formatting ─────────────────────────────────────
  formatResponse(result, options = {}) {
    const template = this.responseTemplates.get(result.type) || this.responseTemplates.get('unknown');
    const response = template(result);

    // Add context if requested
    if (options.showContext && result.entities) {
      response.text += `\n\n*Detected:*\n${this.formatEntities(result.entities)}`;
    }

    // Add confidence if requested
    if (options.showConfidence && result.confidence) {
      response.text += `\n\n*Confidence: ${Math.round(result.confidence * 100)}%*`;
    }

    return response;
  }

  formatEntities(entities) {
    const parts = [];
    for (const [key, value] of Object.entries(entities)) {
      if (value) {
        parts.push(`• ${key}: ${value}`);
      }
    }
    return parts.join('\n') || 'None';
  }

  // ── Keyboard Definitions ───────────────────────────────────
  getHomeKeyboard() {
    return {
      inline_keyboard: [
        [
          { text: '💡 Lights On', callback_data: 'home_lights_on' },
          { text: '🌑 Lights Off', callback_data: 'home_lights_off' }
        ],
        [
          { text: '🌡️ Climate', callback_data: 'home_climate' },
          { text: '🔓 Access', callback_data: 'home_access' }
        ],
        [
          { text: '⏰ Timer', callback_data: 'home_timer' }
        ]
      ]
    };
  }

  getClimateKeyboard() {
    return {
      inline_keyboard: [
        [
          { text: '🌡️ 19°C', callback_data: 'climate_19' },
          { text: '🌡️ 21°C', callback_data: 'climate_21' },
          { text: '🌡️ 23°C', callback_data: 'climate_23' }
        ],
        [
          { text: '🔥 Auto', callback_data: 'climate_auto' },
          { text: '❄️ Off', callback_data: 'climate_off' }
        ]
      ]
    };
  }

  getAccessKeyboard() {
    return {
      inline_keyboard: [
        [
          { text: '🚗 Garage Open', callback_data: 'access_garage_open' },
          { text: '🚗 Garage Close', callback_data: 'access_garage_close' }
        ],
        [
          { text: '🚪 Front Door', callback_data: 'access_door' },
          { text: '🔒 All Locked', callback_data: 'access_lock_all' }
        ]
      ]
    };
  }

  getSubscriptionKeyboard() {
    return {
      inline_keyboard: [
        [
          { text: '📋 List All', callback_data: 'sub_list' },
          { text: '💰 Cost Summary', callback_data: 'sub_cost' }
        ],
        [
          { text: '🔍 Find Killable', callback_data: 'sub_killable' },
          { text: '📊 Analytics', callback_data: 'sub_analytics' }
        ]
      ]
    };
  }

  getFinanceKeyboard() {
    return {
      inline_keyboard: [
        [
          { text: '💰 Overview', callback_data: 'fin_overview' },
          { text: '📊 Expenses', callback_data: 'fin_expenses' }
        ],
        [
          { text: '📋 Tax Status', callback_data: 'fin_tax' },
          { text: '📤 ELSTER', callback_data: 'fin_elster' }
        ]
      ]
    };
  }

  getSecurityKeyboard() {
    return {
      inline_keyboard: [
        [
          { text: '🔍 Quick Scan', callback_data: 'sec_quick' },
          { text: '🔬 Deep Scan', callback_data: 'sec_deep' }
        ],
        [
          { text: '📊 Audit Report', callback_data: 'sec_audit' },
          { text: '🔐 API Keys', callback_data: 'sec_keys' }
        ]
      ]
    };
  }

  getReportKeyboard() {
    return {
      inline_keyboard: [
        [
          { text: '📊 System', callback_data: 'report_system' },
          { text: '🏠 Home', callback_data: 'report_home' }
        ],
        [
          { text: '💰 Finance', callback_data: 'report_finance' },
          { text: '🔒 Security', callback_data: 'report_security' }
        ],
        [
          { text: '📈 Full Report', callback_data: 'report_full' }
        ]
      ]
    };
  }

  getRudibotKeyboard() {
    return {
      inline_keyboard: [
        [
          { text: '📊 Status', callback_data: 'bot_status' },
          { text: '🩺 Health', callback_data: 'bot_health' }
        ],
        [
          { text: '🔄 Restart', callback_data: 'bot_restart' },
          { text: '📝 Logs', callback_data: 'bot_logs' }
        ]
      ]
    };
  }

  getHelpKeyboard() {
    return {
      inline_keyboard: [
        [
          { text: '🏠 Home', callback_data: 'help_home' },
          { text: '💰 Finance', callback_data: 'help_finance' }
        ],
        [
          { text: '🔒 Security', callback_data: 'help_security' },
          { text: '🤖 Commands', callback_data: 'help_commands' }
        ]
      ]
    };
  }

  getApprovalKeyboard() {
    return {
      inline_keyboard: [
        [
          { text: '✅ Approve', callback_data: 'approve_action' },
          { text: '❌ Cancel', callback_data: 'cancel_action' }
        ]
      ]
    };
  }

  // ── Special Responses ─────────────────────────────────────
  formatApprovalRequired(reason, action) {
    return {
      text: `⚠️ *APPROVAL REQUIRED*\n\n${reason}\n\nAction: ${action}`,
      keyboard: this.getApprovalKeyboard()
    };
  }

  formatSuccess(message, keyboard = null) {
    return {
      text: `✅ *SUCCESS*\n\n${message}`,
      keyboard
    };
  }

  formatError(message, keyboard = null) {
    return {
      text: `❌ *ERROR*\n\n${message}`,
      keyboard
    };
  }

  formatBlocked(reason) {
    return {
      text: `🚫 *BLOCKED*\n\n${reason}`,
      keyboard: this.getHelpKeyboard()
    };
  }

  // ── Voice Response ───────────────────────────────────────
  async formatVoiceResponse(result, voiceHandler) {
    const response = this.formatResponse(result);
    
    // Generate TTS if configured
    if (voiceHandler && result.message) {
      try {
        const tts = await voiceHandler.speak(result.message);
        if (tts.success && tts.audioPath) {
          response.audio = tts.audioPath;
        }
      } catch (e) {
        console.warn('TTS generation failed:', e.message);
      }
    }
    
    return response;
  }

  // ── Context Menu ───────────────────────────────────────
  getContextMenu(context) {
    switch (context) {
      case 'home':
        return this.getHomeKeyboard();
      case 'finance':
        return this.getFinanceKeyboard();
      case 'security':
        return this.getSecurityKeyboard();
      default:
        return this.getHelpKeyboard();
    }
  }
}

module.exports = { KivoReply };
