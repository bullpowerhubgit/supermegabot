import { ZendeskConfig, ZendeskAction } from './types.js';
import axios from 'axios';

export class ZendeskController {
  private config: ZendeskConfig;
  private baseUrl: string;

  constructor(config: ZendeskConfig) {
    this.config = config;
    this.baseUrl = `https://${config.subdomain}.zendesk.com/api/v2`;
  }

  private getAuth() {
    return {
      auth: {
        username: `${this.config.email}/token`,
        password: this.config.apiToken,
      },
    };
  }

  async execute(action: ZendeskAction): Promise<any> {
    switch (action.action) {
      case 'getTickets':
        return this.getTickets();
      case 'getTicket':
        return this.getTicket(action.ticketId!);
      case 'createTicket':
        return this.createTicket(action.data);
      case 'updateTicket':
        return this.updateTicket(action.ticketId!, action.data);
      case 'deleteTicket':
        return this.deleteTicket(action.ticketId!);
      case 'getUsers':
        return this.getUsers();
      case 'getUser':
        return this.getUser(action.userId!);
      case 'createUser':
        return this.createUser(action.data);
      default:
        throw new Error(`Unknown Zendesk action: ${action.action}`);
    }
  }

  private async getTickets(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/tickets.json`, this.getAuth());
      return { success: true, tickets: response.data.tickets };
    } catch (error: any) {
      throw new Error(`Zendesk getTickets failed: ${error.message}`);
    }
  }

  private async getTicket(ticketId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/tickets/${ticketId}.json`, this.getAuth());
      return { success: true, ticket: response.data.ticket };
    } catch (error: any) {
      throw new Error(`Zendesk getTicket failed: ${error.message}`);
    }
  }

  private async createTicket(data: any): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/tickets.json`, { ticket: data }, this.getAuth());
      return { success: true, ticket: response.data.ticket };
    } catch (error: any) {
      throw new Error(`Zendesk createTicket failed: ${error.message}`);
    }
  }

  private async updateTicket(ticketId: string, data: any): Promise<any> {
    try {
      const response = await axios.put(`${this.baseUrl}/tickets/${ticketId}.json`, { ticket: data }, this.getAuth());
      return { success: true, ticket: response.data.ticket };
    } catch (error: any) {
      throw new Error(`Zendesk updateTicket failed: ${error.message}`);
    }
  }

  private async deleteTicket(ticketId: string): Promise<any> {
    try {
      await axios.delete(`${this.baseUrl}/tickets/${ticketId}.json`, this.getAuth());
      return { success: true, message: 'Ticket deleted' };
    } catch (error: any) {
      throw new Error(`Zendesk deleteTicket failed: ${error.message}`);
    }
  }

  private async getUsers(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/users.json`, this.getAuth());
      return { success: true, users: response.data.users };
    } catch (error: any) {
      throw new Error(`Zendesk getUsers failed: ${error.message}`);
    }
  }

  private async getUser(userId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/users/${userId}.json`, this.getAuth());
      return { success: true, user: response.data.user };
    } catch (error: any) {
      throw new Error(`Zendesk getUser failed: ${error.message}`);
    }
  }

  private async createUser(data: any): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/users.json`, { user: data }, this.getAuth());
      return { success: true, user: response.data.user };
    } catch (error: any) {
      throw new Error(`Zendesk createUser failed: ${error.message}`);
    }
  }
}
