import { MailgunConfig, MailgunAction } from './types.js';
import mailgun = require('mailgun-js');

export class MailgunController {
  private config: MailgunConfig;
  private client: any;

  constructor(config: MailgunConfig) {
    this.config = config;
    this.client = mailgun({ apiKey: config.apiKey, domain: config.domain });
  }

  async execute(action: MailgunAction): Promise<any> {
    switch (action.action) {
      case 'sendEmail':
        return this.sendEmail(action.data);
      case 'getMessages':
        return this.getMessages();
      case 'getMessage':
        return this.getMessage(action.messageId!);
      case 'deleteMessage':
        return this.deleteMessage(action.messageId!);
      case 'getStats':
        return this.getStats();
      default:
        throw new Error(`Unknown Mailgun action: ${action.action}`);
    }
  }

  private async sendEmail(data: any): Promise<any> {
    try {
      const result = await new Promise((resolve, reject) => {
        this.client.messages().send(data, (err: any, body: any) => {
          if (err) reject(err);
          else resolve(body);
        });
      });
      return { success: true, result: result as any };
    } catch (error: any) {
      throw new Error(`Mailgun sendEmail failed: ${error.message}`);
    }
  }

  private async getMessages(): Promise<any> {
    try {
      const result = await new Promise((resolve, reject) => {
        this.client.get(`/v3/${this.config.domain}/events`, (err: any, body: any) => {
          if (err) reject(err);
          else resolve(body);
        });
      });
      return { success: true, messages: (result as any).items };
    } catch (error: any) {
      throw new Error(`Mailgun getMessages failed: ${error.message}`);
    }
  }

  private async getMessage(messageId: string): Promise<any> {
    try {
      const result = await new Promise((resolve, reject) => {
        this.client.get(`/v3/${this.config.domain}/messages/${messageId}`, (err: any, body: any) => {
          if (err) reject(err);
          else resolve(body);
        });
      });
      return { success: true, message: result };
    } catch (error: any) {
      throw new Error(`Mailgun getMessage failed: ${error.message}`);
    }
  }

  private async deleteMessage(messageId: string): Promise<any> {
    try {
      await new Promise((resolve, reject) => {
        this.client.delete(`/v3/${this.config.domain}/messages/${messageId}`, (err: any, body: any) => {
          if (err) reject(err);
          else resolve(body);
        });
      });
      return { success: true, message: 'Message deleted' };
    } catch (error: any) {
      throw new Error(`Mailgun deleteMessage failed: ${error.message}`);
    }
  }

  private async getStats(): Promise<any> {
    try {
      const result = await new Promise((resolve, reject) => {
        this.client.get(`/v3/${this.config.domain}/stats`, (err: any, body: any) => {
          if (err) reject(err);
          else resolve(body);
        });
      });
      return { success: true, stats: result as any };
    } catch (error: any) {
      throw new Error(`Mailgun getStats failed: ${error.message}`);
    }
  }
}
