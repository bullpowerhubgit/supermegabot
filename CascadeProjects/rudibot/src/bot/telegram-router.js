/**
 * Telegram Router — Routes messages to appropriate handlers
 * Distinguishes between normal commands and KIVO requests
 */

class TelegramRouter {
  constructor(kivoCore, commandHandler) {
    this.kivo = kivoCore;
    this.commands = commandHandler;
  }

  async routeMessage(msg, chatId) {
    const text = msg.text || '';
    const voice = msg.voice;

    // Voice message → KIVO processing
    if (voice) {
      return this.handleVoiceMessage(msg, chatId);
    }

    // Check if it's a KIVO conversational request (not a command)
    if (!text.startsWith('/') && this.isKivoRequest(text)) {
      return this.handleKivoText(text, chatId);
    }

    // Normal command handling
    const command = text.split(' ')[0];
    const handler = this.commands[command];
    if (handler) {
      const args = text.slice(command.length).trim();
      return handler(chatId, args);
    }

    // Fallback to KIVO for unknown text
    if (text.length > 0) {
      return this.handleKivoText(text, chatId);
    }

    return { handled: false, message: 'Unknown request' };
  }

  isKivoRequest(text) {
    const kivoTriggers = [
      'kivo', 'hey kivo', 'okay kivo',
      'licht', 'lampe', 'steckdose', 'heizung', 'temperatur',
      'timer', 'wecker', 'alarm', 'tor', 'garage', 'tür',
      'abo', 'vertrag', 'kündig', 'steuer', 'tax', 'scan',
      'report', 'status', 'übersicht', 'was ist'
    ];

    const lower = text.toLowerCase();
    return kivoTriggers.some(trigger => lower.includes(trigger));
  }

  async handleVoiceMessage(msg, chatId) {
    // TODO: Download voice file, transcribe with Whisper
    // For now, simulate
    const simulatedTranscript = this.simulateVoiceTranscription();
    return this.handleKivoText(simulatedTranscript, chatId);
  }

  simulateVoiceTranscription() {
    const examples = [
      'Hey Kivo, Licht an',
      'KIVO, Timer 10 Minuten',
      'Hey Kivo, prüf meine Abos',
      'KIVO, starte Deepscan',
      'Hey Kivo, was ist der Systemstatus'
    ];
    return examples[Math.floor(Math.random() * examples.length)];
  }

  async handleKivoText(text, chatId) {
    try {
      const result = await this.kivo.processText(text);
      
      // Format response for Telegram
      if (result.blocked && result.requiresApproval) {
        return this.sendApprovalRequest(chatId, result);
      }

      if (result.success || result.intent) {
        return this.sendKivoResponse(chatId, result);
      }

      return { handled: false, message: 'KIVO could not understand' };
    } catch (e) {
      return { handled: false, error: e.message };
    }
  }

  sendApprovalRequest(chatId, result) {
    // TODO: Send Telegram inline keyboard with Approve/Cancel buttons
    const message = `⚠️ *Freigabe erforderlich*\n\n${result.reason}\n\nAktion: ${result.action}`;
    
    return {
      handled: true,
      message,
      requiresApproval: true,
      action: result.action,
      chatId
    };
  }

  sendKivoResponse(chatId, result) {
    let message = '🎙️ *KIVO*\n\n';
    
    if (result.device) {
      message += `🏠 Home: ${result.device} ${result.action}\n`;
    }
    
    if (result.timer) {
      message += `⏰ Timer: ${result.timer.minutes} Minuten\n`;
    }
    
    if (result.workflow) {
      message += `🤖 Workflow: ${result.workflow.status}\n`;
    }
    
    if (result.message) {
      message += `💬 ${result.message}\n`;
    }

    return { handled: true, message };
  }
}

module.exports = { TelegramRouter };
