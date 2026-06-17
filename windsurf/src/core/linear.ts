import { LinearConfig, LinearAction } from './types.js';
import axios from 'axios';

export class LinearController {
  private config: LinearConfig;
  private baseUrl = 'https://api.linear.app/graphql';

  constructor(config: LinearConfig) {
    this.config = config;
  }

  async execute(action: LinearAction): Promise<any> {
    switch (action.action) {
      case 'getTeams':
        return this.getTeams();
      case 'getIssues':
        return this.getIssues(action.teamId);
      case 'getIssue':
        return this.getIssue(action.issueId!);
      case 'createIssue':
        return this.createIssue(action.data);
      case 'updateIssue':
        return this.updateIssue(action.issueId!, action.data);
      case 'getProjects':
        return this.getProjects(action.teamId);
      case 'getProject':
        return this.getProject(action.projectId!);
      default:
        throw new Error(`Unknown Linear action: ${action.action}`);
    }
  }

  private async getTeams(): Promise<any> {
    try {
      const response = await axios.post(this.baseUrl, { query: '{ teams { nodes { id name } } }' }, {
        headers: { Authorization: `Bearer ${this.config.apiKey}` },
      });
      return { success: true, teams: response.data.data.teams.nodes };
    } catch (error: any) {
      throw new Error(`Linear getTeams failed: ${error.message}`);
    }
  }

  private async getIssues(teamId?: string): Promise<any> {
    try {
      const query = teamId 
        ? `{ issues (filter: { team: { id: { eq: "${teamId}" } } }) { nodes { id title } } }`
        : '{ issues { nodes { id title } } }';
      const response = await axios.post(this.baseUrl, { query }, {
        headers: { Authorization: `Bearer ${this.config.apiKey}` },
      });
      return { success: true, issues: response.data.data.issues.nodes };
    } catch (error: any) {
      throw new Error(`Linear getIssues failed: ${error.message}`);
    }
  }

  private async getIssue(issueId: string): Promise<any> {
    try {
      const response = await axios.post(this.baseUrl, { query: `{ issue (id: "${issueId}") { id title } }` }, {
        headers: { Authorization: `Bearer ${this.config.apiKey}` },
      });
      return { success: true, issue: response.data.data.issue };
    } catch (error: any) {
      throw new Error(`Linear getIssue failed: ${error.message}`);
    }
  }

  private async createIssue(data: any): Promise<any> {
    try {
      const response = await axios.post(this.baseUrl, { 
        query: `mutation { issueCreate (input: { title: "${data.title}", teamId: "${data.teamId}" }) { issue { id title } } }` 
      }, {
        headers: { Authorization: `Bearer ${this.config.apiKey}` },
      });
      return { success: true, issue: response.data.data.issueCreate.issue };
    } catch (error: any) {
      throw new Error(`Linear createIssue failed: ${error.message}`);
    }
  }

  private async updateIssue(issueId: string, data: any): Promise<any> {
    try {
      const response = await axios.post(this.baseUrl, { 
        query: `mutation { issueUpdate (id: "${issueId}", input: { title: "${data.title}" }) { issue { id title } } }` 
      }, {
        headers: { Authorization: `Bearer ${this.config.apiKey}` },
      });
      return { success: true, issue: response.data.data.issueUpdate.issue };
    } catch (error: any) {
      throw new Error(`Linear updateIssue failed: ${error.message}`);
    }
  }

  private async getProjects(teamId?: string): Promise<any> {
    try {
      const query = teamId 
        ? `{ projects (filter: { team: { id: { eq: "${teamId}" } } }) { nodes { id name } } }`
        : '{ projects { nodes { id name } } }';
      const response = await axios.post(this.baseUrl, { query }, {
        headers: { Authorization: `Bearer ${this.config.apiKey}` },
      });
      return { success: true, projects: response.data.data.projects.nodes };
    } catch (error: any) {
      throw new Error(`Linear getProjects failed: ${error.message}`);
    }
  }

  private async getProject(projectId: string): Promise<any> {
    try {
      const response = await axios.post(this.baseUrl, { query: `{ project (id: "${projectId}") { id name } }` }, {
        headers: { Authorization: `Bearer ${this.config.apiKey}` },
      });
      return { success: true, project: response.data.data.project };
    } catch (error: any) {
      throw new Error(`Linear getProject failed: ${error.message}`);
    }
  }
}
