import { SMSConfig, SMSAction } from './types.js';
import twilio from 'twilio';

export class SMSController {
  private config: SMSConfig;
  private client: twilio.Twilio;

  constructor(config: SMSConfig) {
    this.config = config;
    this.client = twilio(config.accountSid, config.authToken);
  }

  async execute(action: SMSAction): Promise<any> {
    switch (action.action) {
      case 'send':
        return this.sendSMS(action);
      default:
        throw new Error(`Unknown SMS action: ${action.action}`);
    }
  }

  private async sendSMS(action: SMSAction): Promise<any> {
    try {
      const message = await this.client.messages.create({
        body: action.body,
        from: this.config.fromNumber,
        to: action.to,
      });

      return {
        success: true,
        messageId: message.sid,
        status: message.status,
        message: 'SMS sent successfully',
      };
    } catch (error: any) {
      throw new Error(`SMS sending failed: ${error.message}`);
    }
  }
}
