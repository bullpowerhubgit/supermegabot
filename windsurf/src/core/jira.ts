import { JiraConfig, JiraAction } from './types.js';
import JiraClient from 'jira-client';

export class JiraController {
  private config: JiraConfig;
  private client: JiraClient;

  constructor(config: JiraConfig) {
    this.config = config;
    this.client = new JiraClient({
      protocol: 'https',
      host: config.baseUrl,
      username: config.username,
      password: config.apiToken,
      apiVersion: '3',
      strictSSL: true,
    });
  }

  async execute(action: JiraAction): Promise<any> {
    switch (action.action) {
      case 'getProjects':
        return this.getProjects();
      case 'getProject':
        return this.getProject(action.projectKey!);
      case 'getIssues':
        return this.getIssues(action.projectKey!);
      case 'getIssue':
        return this.getIssue(action.issueId!);
      case 'createIssue':
        return this.createIssue(action.data);
      case 'updateIssue':
        return this.updateIssue(action.issueId!, action.data);
      case 'deleteIssue':
        return this.deleteIssue(action.issueId!);
      case 'getBoards':
        return this.getBoards();
      case 'getSprints':
        return this.getSprints(action.boardId!);
      default:
        throw new Error(`Unknown Jira action: ${action.action}`);
    }
  }

  private async getProjects(): Promise<any> {
    try {
      const projects = await this.client.listProjects();
      return { success: true, projects };
    } catch (error: any) {
      throw new Error(`Jira getProjects failed: ${error.message}`);
    }
  }

  private async getProject(projectKey: string): Promise<any> {
    try {
      const project = await this.client.getProject(projectKey);
      return { success: true, project };
    } catch (error: any) {
      throw new Error(`Jira getProject failed: ${error.message}`);
    }
  }

  private async getIssues(projectKey: string): Promise<any> {
    try {
      const issues = await this.client.searchJira(`project=${projectKey}`);
      return { success: true, issues: issues.issues };
    } catch (error: any) {
      throw new Error(`Jira getIssues failed: ${error.message}`);
    }
  }

  private async getIssue(issueId: string): Promise<any> {
    try {
      const issue = await this.client.findIssue(issueId);
      return { success: true, issue };
    } catch (error: any) {
      throw new Error(`Jira getIssue failed: ${error.message}`);
    }
  }

  private async createIssue(data: any): Promise<any> {
    try {
      const issue = await this.client.addNewIssue(data);
      return { success: true, issue };
    } catch (error: any) {
      throw new Error(`Jira createIssue failed: ${error.message}`);
    }
  }

  private async updateIssue(issueId: string, data: any): Promise<any> {
    try {
      const issue = await this.client.updateIssue(issueId, data);
      return { success: true, issue };
    } catch (error: any) {
      throw new Error(`Jira updateIssue failed: ${error.message}`);
    }
  }

  private async deleteIssue(issueId: string): Promise<any> {
    try {
      await this.client.deleteIssue(issueId);
      return { success: true, message: 'Issue deleted' };
    } catch (error: any) {
      throw new Error(`Jira deleteIssue failed: ${error.message}`);
    }
  }

  private async getBoards(): Promise<any> {
    try {
      const boards = await this.client.getAllBoards();
      return { success: true, boards: boards.values };
    } catch (error: any) {
      throw new Error(`Jira getBoards failed: ${error.message}`);
    }
  }

  private async getSprints(boardId: string): Promise<any> {
    try {
      const sprints = await this.client.getAllSprintsForBoard(boardId);
      return { success: true, sprints: sprints.values };
    } catch (error: any) {
      throw new Error(`Jira getSprints failed: ${error.message}`);
    }
  }
}
