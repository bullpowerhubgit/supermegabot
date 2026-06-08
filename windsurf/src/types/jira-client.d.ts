declare module 'jira-client' {
  interface JiraClientOptions {
    protocol?: string;
    host: string;
    username: string;
    password: string;
    apiVersion?: string;
    strictSSL?: boolean;
  }

  class JiraClient {
    constructor(options: JiraClientOptions);
    listProjects(): Promise<any>;
    getProject(projectKey: string): Promise<any>;
    searchJira(jql: string): Promise<any>;
    findIssue(issueId: string): Promise<any>;
    addNewIssue(issue: any): Promise<any>;
    updateIssue(issueId: string, issue: any): Promise<any>;
    deleteIssue(issueId: string): Promise<any>;
    getAllBoards(): Promise<any>;
    getAllSprintsForBoard(boardId: string): Promise<any>;
  }

  export default JiraClient;
}
