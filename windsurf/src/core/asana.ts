import { AsanaConfig, AsanaAction } from './types.js';
import axios from 'axios';

export class AsanaController {
  private config: AsanaConfig;
  private baseUrl = 'https://app.asana.com/api/1.0';

  constructor(config: AsanaConfig) {
    this.config = config;
  }

  async execute(action: AsanaAction): Promise<any> {
    switch (action.action) {
      case 'getProjects':
        return this.getProjects();
      case 'getProject':
        return this.getProject(action.projectId!);
      case 'getTasks':
        return this.getTasks(action.projectId);
      case 'getTask':
        return this.getTask(action.taskId!);
      case 'createTask':
        return this.createTask(action.data);
      case 'updateTask':
        return this.updateTask(action.taskId!, action.data);
      case 'deleteTask':
        return this.deleteTask(action.taskId!);
      case 'getTeams':
        return this.getTeams();
      default:
        throw new Error(`Unknown Asana action: ${action.action}`);
    }
  }

  private async getProjects(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/projects`, {
        headers: { Authorization: `Bearer ${this.config.accessToken}` },
      });
      return { success: true, projects: response.data.data };
    } catch (error: any) {
      throw new Error(`Asana getProjects failed: ${error.message}`);
    }
  }

  private async getProject(projectId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/projects/${projectId}`, {
        headers: { Authorization: `Bearer ${this.config.accessToken}` },
      });
      return { success: true, project: response.data.data };
    } catch (error: any) {
      throw new Error(`Asana getProject failed: ${error.message}`);
    }
  }

  private async getTasks(projectId?: string): Promise<any> {
    try {
      const url = projectId 
        ? `${this.baseUrl}/projects/${projectId}/tasks`
        : `${this.baseUrl}/tasks`;
      const response = await axios.get(url, {
        headers: { Authorization: `Bearer ${this.config.accessToken}` },
      });
      return { success: true, tasks: response.data.data };
    } catch (error: any) {
      throw new Error(`Asana getTasks failed: ${error.message}`);
    }
  }

  private async getTask(taskId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/tasks/${taskId}`, {
        headers: { Authorization: `Bearer ${this.config.accessToken}` },
      });
      return { success: true, task: response.data.data };
    } catch (error: any) {
      throw new Error(`Asana getTask failed: ${error.message}`);
    }
  }

  private async createTask(data: any): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/tasks`, { data }, {
        headers: { Authorization: `Bearer ${this.config.accessToken}` },
      });
      return { success: true, task: response.data.data };
    } catch (error: any) {
      throw new Error(`Asana createTask failed: ${error.message}`);
    }
  }

  private async updateTask(taskId: string, data: any): Promise<any> {
    try {
      const response = await axios.put(`${this.baseUrl}/tasks/${taskId}`, { data }, {
        headers: { Authorization: `Bearer ${this.config.accessToken}` },
      });
      return { success: true, task: response.data.data };
    } catch (error: any) {
      throw new Error(`Asana updateTask failed: ${error.message}`);
    }
  }

  private async deleteTask(taskId: string): Promise<any> {
    try {
      await axios.delete(`${this.baseUrl}/tasks/${taskId}`, {
        headers: { Authorization: `Bearer ${this.config.accessToken}` },
      });
      return { success: true, message: 'Task deleted' };
    } catch (error: any) {
      throw new Error(`Asana deleteTask failed: ${error.message}`);
    }
  }

  private async getTeams(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/teams`, {
        headers: { Authorization: `Bearer ${this.config.accessToken}` },
      });
      return { success: true, teams: response.data.data };
    } catch (error: any) {
      throw new Error(`Asana getTeams failed: ${error.message}`);
    }
  }
}
