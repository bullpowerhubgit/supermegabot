import { EmailConfig, EmailAction } from './types.js';
import sgMail from '@sendgrid/mail';
import nodemailer from 'nodemailer';

export class EmailController {
  private config: EmailConfig;
  private transporter?: nodemailer.Transporter;

  constructor(config: EmailConfig) {
    this.config = config;
    
    if (config.provider === 'sendgrid' && config.apiKey) {
      sgMail.setApiKey(config.apiKey);
    }
    
    if (config.provider === 'nodemailer' && config.smtpConfig) {
      this.transporter = nodemailer.createTransport(config.smtpConfig);
    }
  }

  async execute(action: EmailAction): Promise<any> {
    switch (action.action) {
      case 'send':
        return this.send(action);
      case 'sendTemplate':
        return this.sendTemplate(action);
      default:
        throw new Error(`Unknown email action: ${action.action}`);
    }
  }

  private async send(action: EmailAction): Promise<any> {
    const from = action.from || this.config.from;
    if (!from) {
      throw new Error('From address is required');
    }

    if (this.config.provider === 'sendgrid') {
      const content: any[] = [];
      if (action.text) {
        content.push({ type: 'text/plain', value: action.text });
      }
      if (action.html) {
        content.push({ type: 'text/html', value: action.html });
      }

      const msg: any = {
        from,
        to: Array.isArray(action.to) ? action.to : [action.to],
        subject: action.subject || '',
        content,
      };

      if (action.attachments) {
        msg.attachments = action.attachments;
      }

      await sgMail.send(msg);
      return { success: true, message: 'Email sent via SendGrid' };
    }

    if (this.config.provider === 'nodemailer' && this.transporter) {
      const info = await this.transporter.sendMail({
        from,
        to: action.to,
        subject: action.subject,
        text: action.text,
        html: action.html,
        attachments: action.attachments,
      });

      return { success: true, messageId: info.messageId, message: 'Email sent via Nodemailer' };
    }

    throw new Error('Email provider not configured');
  }

  private async sendTemplate(action: EmailAction): Promise<any> {
    const from = action.from || this.config.from;
    if (!from) {
      throw new Error('From address is required');
    }

    if (this.config.provider === 'sendgrid' && action.templateId) {
      const msg = {
        from,
        to: Array.isArray(action.to) ? action.to : [action.to],
        templateId: action.templateId,
        dynamicTemplateData: action.templateData,
      };

      await sgMail.send(msg);
      return { success: true, message: 'Template email sent via SendGrid' };
    }

    throw new Error('Template sending only supported with SendGrid');
  }
}
