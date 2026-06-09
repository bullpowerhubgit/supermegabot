import { ImapFlow } from 'imapflow';
import { simpleParser } from 'mailparser';
import OpenAI from 'openai';

export interface EmailAccount {
  email: string;
  imapHost: string;
  imapPort: number;
  imapSecure: boolean;
  smtpHost: string;
  smtpPort: number;
  smtpSecure: boolean;
  password: string;
}

export interface EmailRule {
  id: string;
  name: string;
  conditions: {
    from?: string[];
    subject?: string[];
    body?: string[];
    hasAttachments?: boolean;
    priority?: 'high' | 'normal' | 'low';
  };
  actions: {
    moveToFolder?: string;
    markAsRead?: boolean;
    markAsImportant?: boolean;
    autoReply?: string;
    delete?: boolean;
    forwardTo?: string;
    label?: string[];
  };
}

export class EmailAutomationController {
  private accounts: Map<string, EmailAccount> = new Map();
  private rules: EmailRule[] = [];
  private openai?: OpenAI;

  constructor(openaiApiKey?: string) {
    if (openaiApiKey) {
      this.openai = new OpenAI({ apiKey: openaiApiKey });
    }
  }

  addAccount(account: EmailAccount): void {
    this.accounts.set(account.email, account);
  }

  addRule(rule: EmailRule): void {
    this.rules.push(rule);
  }

  async connectToAccount(email: string): Promise<ImapFlow> {
    const account = this.accounts.get(email);
    if (!account) {
      throw new Error(`Account ${email} not found`);
    }

    const client = new ImapFlow({
      host: account.imapHost,
      port: account.imapPort,
      secure: account.imapSecure,
      auth: {
        user: account.email,
        pass: account.password,
      },
    });

    await client.connect();
    return client;
  }

  async fetchEmails(email: string, folder: string = 'INBOX', limit: number = 50): Promise<any[]> {
    const client = await this.connectToAccount(email);
    const mailbox = await client.mailboxOpen(folder);
    
    const emails = [];
    const messages = await client.search({ seen: false });
    
    if (Array.isArray(messages)) {
      for (const message of messages.slice(0, limit)) {
        const result = await client.fetchOne(message, { source: true });
        if (result && 'content' in result) {
          const { content } = result;
          const parsed = await simpleParser(content as Buffer);
          
          emails.push({
            id: message,
            from: parsed.from?.text,
            subject: parsed.subject,
            body: parsed.text,
            html: parsed.html,
            date: parsed.date,
            attachments: parsed.attachments?.map((a: any) => a.filename),
          });
        }
      }
    }
    
    await client.logout();
    return emails;
  }

  async classifyEmail(email: string, emailData: any): Promise<string> {
    if (!this.openai) {
      return 'uncategorized';
    }

    try {
      const response = await this.openai.chat.completions.create({
        model: 'gpt-4',
        messages: [
          {
            role: 'system',
            content: 'You are an email classifier. Classify emails into: important, work, personal, spam, newsletter, promotion, finance, social, other. Return only the category name.',
          },
          {
            role: 'user',
            content: `From: ${emailData.from}\nSubject: ${emailData.subject}\nBody: ${emailData.body?.substring(0, 500)}`,
          },
        ],
      });

      return response.choices[0].message.content?.toLowerCase() || 'other';
    } catch (error) {
      console.error('AI classification failed:', error);
      return 'other';
    }
  }

  async applyRules(email: string, emailData: any): Promise<any[]> {
    const appliedActions = [];

    for (const rule of this.rules) {
      if (this.matchesRule(emailData, rule)) {
        const client = await this.connectToAccount(email);
        
        if (rule.actions.moveToFolder) {
          await client.messageMove(emailData.id, rule.actions.moveToFolder);
          appliedActions.push({ action: 'move', folder: rule.actions.moveToFolder });
        }
        
        if (rule.actions.markAsRead) {
          await client.messageFlagsAdd(emailData.id, ['\\Seen']);
          appliedActions.push({ action: 'markAsRead' });
        }
        
        if (rule.actions.markAsImportant) {
          await client.messageFlagsAdd(emailData.id, ['\\Flagged']);
          appliedActions.push({ action: 'markAsImportant' });
        }
        
        if (rule.actions.delete) {
          await client.messageDelete(emailData.id);
          appliedActions.push({ action: 'delete' });
        }
        
        if (rule.actions.autoReply) {
          await this.sendAutoReply(email, emailData.from, rule.actions.autoReply);
          appliedActions.push({ action: 'autoReply', to: emailData.from });
        }
        
        await client.logout();
      }
    }

    return appliedActions;
  }

  private matchesRule(emailData: any, rule: EmailRule): boolean {
    const conditions = rule.conditions;
    
    if (conditions.from && conditions.from.length > 0) {
      const fromLower = emailData.from?.toLowerCase() || '';
      if (!conditions.from.some(f => fromLower.includes(f.toLowerCase()))) {
        return false;
      }
    }
    
    if (conditions.subject && conditions.subject.length > 0) {
      const subjectLower = emailData.subject?.toLowerCase() || '';
      if (!conditions.subject.some(s => subjectLower.includes(s.toLowerCase()))) {
        return false;
      }
    }
    
    if (conditions.body && conditions.body.length > 0) {
      const bodyLower = emailData.body?.toLowerCase() || '';
      if (!conditions.body.some(b => bodyLower.includes(b.toLowerCase()))) {
        return false;
      }
    }
    
    if (conditions.hasAttachments !== undefined) {
      const hasAttachments = emailData.attachments && emailData.attachments.length > 0;
      if (conditions.hasAttachments !== hasAttachments) {
        return false;
      }
    }
    
    return true;
  }

  async sendAutoReply(fromEmail: string, toEmail: string, message: string): Promise<void> {
    const account = this.accounts.get(fromEmail);
    if (!account) {
      throw new Error(`Account ${fromEmail} not found`);
    }

    // SMTP implementation would go here
    console.log(`Auto-reply sent to ${toEmail}: ${message}`);
  }

  async processAllAccounts(): Promise<{ email: string; processed: number; actions: any[] }[]> {
    const results = [];

    for (const [email] of this.accounts) {
      const emails = await this.fetchEmails(email);
      let processed = 0;
      const allActions = [];

      for (const emailData of emails) {
        const category = await this.classifyEmail(email, emailData);
        const actions = await this.applyRules(email, emailData);
        
        allActions.push({ emailId: emailData.id, category, actions });
        processed++;
      }

      results.push({ email, processed, actions: allActions });
    }

    return results;
  }

  async createFolder(email: string, folderName: string): Promise<void> {
    const client = await this.connectToAccount(email);
    await client.mailboxCreate(folderName);
    await client.logout();
  }

  async deleteSpam(email: string, threshold: number = 0.8): Promise<number> {
    const client = await this.connectToAccount(email);
    const mailbox = await client.mailboxOpen('INBOX');
    
    const messages = await client.search({ seen: false });
    let deleted = 0;

    if (Array.isArray(messages)) {
      for (const message of messages) {
        const result = await client.fetchOne(message, { source: true });
        if (result && 'content' in result) {
          const { content } = result;
          const parsed = await simpleParser(content as Buffer);
          
          const isSpam = await this.detectSpam(parsed);
          
          if (isSpam >= threshold) {
            await client.messageDelete(message);
            deleted++;
          }
        }
      }
    }

    await client.logout();
    return deleted;
  }

  private async detectSpam(emailData: any): Promise<number> {
    if (!this.openai) {
      return 0;
    }

    try {
      const response = await this.openai.chat.completions.create({
        model: 'gpt-4',
        messages: [
          {
            role: 'system',
            content: 'You are a spam detector. Rate emails from 0 (not spam) to 1 (definitely spam). Return only the number.',
          },
          {
            role: 'user',
            content: `From: ${emailData.from}\nSubject: ${emailData.subject}\nBody: ${emailData.body?.substring(0, 500)}`,
          },
        ],
      });

      const score = parseFloat(response.choices[0].message.content || '0');
      return score;
    } catch (error) {
      console.error('Spam detection failed:', error);
      return 0;
    }
  }
}
