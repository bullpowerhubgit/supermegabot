import { GitHubConfig, GitHubAction } from './types.js';
import { Octokit } from '@octokit/rest';

export class GitHubController {
  private config: GitHubConfig;
  private octokit: Octokit;

  constructor(config: GitHubConfig) {
    this.config = config;
    this.octokit = new Octokit({ auth: config.token });
  }

  async execute(action: GitHubAction): Promise<any> {
    const owner = action.owner || this.config.owner;
    const repo = action.repo || this.config.repo;

    switch (action.action) {
      case 'getRepos':
        return this.getRepos();
      case 'getRepo':
        return this.getRepo(owner!, repo!);
      case 'createRepo':
        return this.createRepo(action.data);
      case 'updateRepo':
        return this.updateRepo(owner!, repo!, action.data);
      case 'deleteRepo':
        return this.deleteRepo(owner!, repo!);
      case 'getIssues':
        return this.getIssues(owner!, repo!, action.query);
      case 'getIssue':
        return this.getIssue(owner!, repo!, action.id!);
      case 'createIssue':
        return this.createIssue(owner!, repo!, action.data);
      case 'updateIssue':
        return this.updateIssue(owner!, repo!, action.id!, action.data);
      case 'closeIssue':
        return this.closeIssue(owner!, repo!, action.id!);
      case 'getPullRequests':
        return this.getPullRequests(owner!, repo!, action.query);
      case 'createPullRequest':
        return this.createPullRequest(owner!, repo!, action.data);
      case 'mergePullRequest':
        return this.mergePullRequest(owner!, repo!, action.id!, action.data);
      case 'getBranches':
        return this.getBranches(owner!, repo!);
      case 'createBranch':
        return this.createBranch(owner!, repo!, action.data);
      case 'deleteBranch':
        return this.deleteBranch(owner!, repo!, action.ref!);
      case 'getCommits':
        return this.getCommits(owner!, repo!, action.ref);
      case 'getFile':
        return this.getFile(owner!, repo!, action.path!, action.ref);
      case 'createFile':
        return this.createFile(owner!, repo!, action.path!, action.data, action.ref);
      case 'updateFile':
        return this.updateFile(owner!, repo!, action.path!, action.data, action.ref);
      case 'deleteFile':
        return this.deleteFile(owner!, repo!, action.path!, action.data, action.ref);
      default:
        throw new Error(`Unknown GitHub action: ${action.action}`);
    }
  }

  private async getRepos(): Promise<any> {
    const { data } = await this.octokit.rest.repos.listForAuthenticatedUser();
    return { success: true, repos: data };
  }

  private async getRepo(owner: string, repo: string): Promise<any> {
    const { data } = await this.octokit.rest.repos.get({ owner, repo });
    return { success: true, repo: data };
  }

  private async createRepo(data: any): Promise<any> {
    const { data: repo } = await this.octokit.rest.repos.createForAuthenticatedUser(data);
    return { success: true, repo };
  }

  private async updateRepo(owner: string, repo: string, data: any): Promise<any> {
    const { data: updatedRepo } = await this.octokit.rest.repos.update({ owner, repo, ...data });
    return { success: true, repo: updatedRepo };
  }

  private async deleteRepo(owner: string, repo: string): Promise<any> {
    await this.octokit.rest.repos.delete({ owner, repo });
    return { success: true, message: 'Repository deleted' };
  }

  private async getIssues(owner: string, repo: string, query?: any): Promise<any> {
    const { data } = await this.octokit.rest.issues.listForRepo({ owner, repo, ...query });
    return { success: true, issues: data };
  }

  private async getIssue(owner: string, repo: string, issueNumber: string): Promise<any> {
    const { data } = await this.octokit.rest.issues.get({ owner, repo, issue_number: parseInt(issueNumber) });
    return { success: true, issue: data };
  }

  private async createIssue(owner: string, repo: string, data: any): Promise<any> {
    const { data: issue } = await this.octokit.rest.issues.create({ owner, repo, ...data });
    return { success: true, issue };
  }

  private async updateIssue(owner: string, repo: string, issueNumber: string, data: any): Promise<any> {
    const { data: issue } = await this.octokit.rest.issues.update({ owner, repo, issue_number: parseInt(issueNumber), ...data });
    return { success: true, issue };
  }

  private async closeIssue(owner: string, repo: string, issueNumber: string): Promise<any> {
    const { data: issue } = await this.octokit.rest.issues.update({ owner, repo, issue_number: parseInt(issueNumber), state: 'closed' });
    return { success: true, issue };
  }

  private async getPullRequests(owner: string, repo: string, query?: any): Promise<any> {
    const { data } = await this.octokit.rest.pulls.list({ owner, repo, ...query });
    return { success: true, pullRequests: data };
  }

  private async createPullRequest(owner: string, repo: string, data: any): Promise<any> {
    const { data: pr } = await this.octokit.rest.pulls.create({ owner, repo, ...data });
    return { success: true, pullRequest: pr };
  }

  private async mergePullRequest(owner: string, repo: string, pullNumber: string, data: any): Promise<any> {
    const { data: pr } = await this.octokit.rest.pulls.merge({ owner, repo, pull_number: parseInt(pullNumber), ...data });
    return { success: true, pullRequest: pr };
  }

  private async getBranches(owner: string, repo: string): Promise<any> {
    const { data } = await this.octokit.rest.repos.listBranches({ owner, repo });
    return { success: true, branches: data };
  }

  private async createBranch(owner: string, repo: string, data: any): Promise<any> {
    const { data: ref } = await this.octokit.rest.git.createRef({ owner, repo, ...data });
    return { success: true, ref };
  }

  private async deleteBranch(owner: string, repo: string, ref: string): Promise<any> {
    await this.octokit.rest.git.deleteRef({ owner, repo, ref: `heads/${ref}` });
    return { success: true, message: 'Branch deleted' };
  }

  private async getCommits(owner: string, repo: string, ref?: string): Promise<any> {
    const { data } = await this.octokit.rest.repos.listCommits({ owner, repo, sha: ref });
    return { success: true, commits: data };
  }

  private async getFile(owner: string, repo: string, path: string, ref?: string): Promise<any> {
    const { data } = await this.octokit.rest.repos.getContent({ owner, repo, path, ref });
    return { success: true, file: data };
  }

  private async createFile(owner: string, repo: string, path: string, data: any, ref?: string): Promise<any> {
    const { data: file } = await this.octokit.rest.repos.createOrUpdateFileContents({ 
      owner, 
      repo, 
      path, 
      message: data.message || 'Create file',
      content: data.content,
      branch: ref 
    });
    return { success: true, file };
  }

  private async updateFile(owner: string, repo: string, path: string, data: any, ref?: string): Promise<any> {
    const { data: file } = await this.octokit.rest.repos.createOrUpdateFileContents({ 
      owner, 
      repo, 
      path, 
      message: data.message || 'Update file',
      content: data.content,
      sha: data.sha,
      branch: ref 
    });
    return { success: true, file };
  }

  private async deleteFile(owner: string, repo: string, path: string, data: any, ref?: string): Promise<any> {
    await this.octokit.rest.repos.deleteFile({ 
      owner, 
      repo, 
      path, 
      message: data.message || 'Delete file',
      sha: data.sha,
      branch: ref 
    });
    return { success: true, message: 'File deleted' };
  }
}
