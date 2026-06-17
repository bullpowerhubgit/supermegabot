import { FreshdeskConfig, FreshdeskAction } from './types.js';
import axios from 'axios';

export class FreshdeskController {
  private config: FreshdeskConfig;
  private baseUrl: string;

  constructor(config: FreshdeskConfig) {
    this.config = config;
    this.baseUrl = `https://${config.domain}.freshdesk.com/api/v2`;
  }

  private getAuth() {
    return {
      auth: {
        username: this.config.apiKey,
        password: 'X',
      },
    };
  }

  async execute(action: FreshdeskAction): Promise<any> {
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
      case 'getContacts':
        return this.getContacts();
      default:
        throw new Error(`Unknown Freshdesk action: ${action.action}`);
    }
  }

  private async getTickets(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/tickets`, this.getAuth());
      return { success: true, tickets: response.data };
    } catch (error: any) {
      throw new Error(`Freshdesk getTickets failed: ${error.message}`);
    }
  }

  private async getTicket(ticketId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/tickets/${ticketId}`, this.getAuth());
      return { success: true, ticket: response.data };
    } catch (error: any) {
      throw new Error(`Freshdesk getTicket failed: ${error.message}`);
    }
  }

  private async createTicket(data: any): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/tickets`, data, this.getAuth());
      return { success: true, ticket: response.data };
    } catch (error: any) {
      throw new Error(`Freshdesk createTicket failed: ${error.message}`);
    }
  }

  private async updateTicket(ticketId: string, data: any): Promise<any> {
    try {
      const response = await axios.put(`${this.baseUrl}/tickets/${ticketId}`, data, this.getAuth());
      return { success: true, ticket: response.data };
    } catch (error: any) {
      throw new Error(`Freshdesk updateTicket failed: ${error.message}`);
    }
  }

  private async deleteTicket(ticketId: string): Promise<any> {
    try {
      await axios.delete(`${this.baseUrl}/tickets/${ticketId}`, this.getAuth());
      return { success: true, message: 'Ticket deleted' };
    } catch (error: any) {
      throw new Error(`Freshdesk deleteTicket failed: ${error.message}`);
    }
  }

  private async getContacts(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/contacts`, this.getAuth());
      return { success: true, contacts: response.data };
    } catch (error: any) {
      throw new Error(`Freshdesk getContacts failed: ${error.message}`);
    }
  }
}
