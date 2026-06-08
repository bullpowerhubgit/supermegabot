export interface Message {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export interface ToolCall {
  id: string;
  type: 'function';
  function: {
    name: string;
    arguments: string;
  };
}

export interface ToolResult {
  tool_call_id: string;
  output: string;
}

export interface AgentConfig {
  provider: 'openai' | 'anthropic' | 'vertexai';
  apiKey: string;
  projectId?: string;
  location?: string;
  model?: string;
  systemPrompt?: string;
  tools?: ToolDefinition[];
}

export interface ToolDefinition {
  name: string;
  description: string;
  parameters: object;
}

export interface BrowserAction {
  action: 'navigate' | 'click' | 'type' | 'screenshot' | 'scroll' | 'extract' | 'close';
  url?: string;
  selector?: string;
  text?: string;
  direction?: 'up' | 'down';
}

export interface MacAction {
  action: 'click' | 'type' | 'keyCombo' | 'moveMouse' | 'openApp' | 'screenshot' | 'getClipboard' | 'setClipboard' | 'getSystemInfo' | 'getCPUUsage' | 'getMemoryUsage' | 'getDiskUsage';
  x?: number;
  y?: number;
  text?: string;
  app?: string;
  keys?: string[];
}

export interface AgentResponse {
  content: string;
  toolCalls?: ToolCall[];
  toolResults?: ToolResult[];
}

export interface GCPConfig {
  projectId: string;
  keyFilename?: string;
  credentials?: any;
}

export interface NLAction {
  action: 'analyzeSentiment' | 'extractEntities' | 'classifyText';
  text: string;
}

export interface TranslationAction {
  action: 'translate';
  text: string;
  targetLanguage: string;
}

export interface VisionAction {
  action: 'detectLabels' | 'detectText' | 'detectFaces' | 'analyzeImage';
  image: string; // base64 or URL
}

export interface SpeechAction {
  action: 'transcribe' | 'synthesize';
  audio?: string; // base64 for transcribe
  text?: string; // for synthesize
  language?: string;
  voice?: string;
}

export interface StorageAction {
  action: 'upload' | 'download' | 'delete' | 'list';
  bucket?: string;
  file?: string;
  data?: string;
}

export interface FirestoreAction {
  action: 'add' | 'get' | 'update' | 'delete' | 'query';
  collection: string;
  document?: string;
  data?: any;
  query?: any;
}

export interface ShopifyConfig {
  shopDomain: string;
  accessToken: string;
  apiVersion?: string;
}

export interface ShopifyAction {
  action: 'getProducts' | 'getProduct' | 'createProduct' | 'updateProduct' | 'deleteProduct' |
           'getOrders' | 'getOrder' | 'createOrder' | 'updateOrder' |
           'getCustomers' | 'getCustomer' | 'createCustomer' | 'updateCustomer' |
           'getInventory' | 'updateInventory' |
           'createWebhook' | 'deleteWebhook' | 'getWebhooks';
  data?: any;
  id?: string;
  query?: any;
}

export interface EmailConfig {
  provider: 'sendgrid' | 'nodemailer';
  apiKey?: string;
  smtpConfig?: any;
  from?: string;
}

export interface EmailAction {
  action: 'send' | 'sendTemplate';
  to: string | string[];
  from?: string;
  subject?: string;
  text?: string;
  html?: string;
  templateId?: string;
  templateData?: any;
  attachments?: any[];
}

export interface SMSConfig {
  accountSid: string;
  authToken: string;
  fromNumber: string;
}

export interface SMSAction {
  action: 'send';
  to: string;
  body: string;
}

export interface StripeConfig {
  apiKey: string;
  apiVersion?: string;
}

export interface StripeAction {
  action: 'createPaymentIntent' | 'confirmPayment' | 'createCustomer' | 'getCustomer' |
           'createSubscription' | 'cancelSubscription' | 'getSubscription' |
           'createInvoice' | 'getInvoice' | 'listInvoices';
  data?: any;
  id?: string;
}

export interface QueueConfig {
  redisHost?: string;
  redisPort?: number;
  redisPassword?: string;
}

export interface QueueAction {
  action: 'addJob' | 'processJob' | 'getJob' | 'removeJob' | 'getQueueStats';
  queueName: string;
  jobName?: string;
  data?: any;
  jobId?: string;
}

export interface AuthConfig {
  jwtSecret: string;
  expiresIn?: string;
}

export interface AuthAction {
  action: 'generateToken' | 'verifyToken' | 'refreshToken';
  payload?: any;
  token?: string;
}

export interface DataImportAction {
  action: 'importCSV' | 'importExcel' | 'exportCSV' | 'exportExcel';
  filePath?: string;
  data?: any[];
  headers?: string[];
}

export interface GitHubConfig {
  token: string;
  owner?: string;
  repo?: string;
}

export interface GitHubAction {
  action: 'getRepos' | 'getRepo' | 'createRepo' | 'updateRepo' | 'deleteRepo' |
           'getIssues' | 'getIssue' | 'createIssue' | 'updateIssue' | 'closeIssue' |
           'getPullRequests' | 'createPullRequest' | 'mergePullRequest' |
           'getBranches' | 'createBranch' | 'deleteBranch' |
           'getCommits' | 'createCommit' | 'getFile' | 'createFile' | 'updateFile' | 'deleteFile';
  owner?: string;
  repo?: string;
  data?: any;
  id?: string;
  path?: string;
  ref?: string;
  query?: any;
}

export interface SlackConfig {
  token: string;
  channel?: string;
}

export interface SlackAction {
  action: 'sendMessage' | 'getChannels' | 'getUsers' | 'postMessage' | 'uploadFile';
  channel?: string;
  text?: string;
  data?: any;
  file?: string;
}

export interface DiscordConfig {
  token: string;
  guildId?: string;
  channelId?: string;
}

export interface DiscordAction {
  action: 'sendMessage' | 'getChannels' | 'getMessages' | 'createChannel' | 'deleteChannel';
  channelId?: string;
  text?: string;
  data?: any;
}

export interface TelegramConfig {
  token: string;
  chatId?: string;
}

export interface TelegramAction {
  action: 'sendMessage' | 'getUpdates' | 'getMe' | 'sendPhoto' | 'sendDocument';
  chatId?: string;
  text?: string;
  data?: any;
  file?: string;
}

export interface NotionConfig {
  token: string;
  databaseId?: string;
}

export interface NotionAction {
  action: 'getDatabases' | 'getDatabase' | 'queryDatabase' | 'getPage' | 'createPage' | 'updatePage' | 'deletePage';
  databaseId?: string;
  pageId?: string;
  data?: any;
  query?: any;
}

export interface AirtableConfig {
  apiKey: string;
  baseId: string;
  tableName?: string;
}

export interface AirtableAction {
  action: 'getRecords' | 'getRecord' | 'createRecord' | 'updateRecord' | 'deleteRecord' | 'listTables';
  tableName?: string;
  recordId?: string;
  data?: any;
}

export interface AWSConfig {
  accessKeyId: string;
  secretAccessKey: string;
  region?: string;
}

export interface S3Action {
  action: 'listBuckets' | 'listObjects' | 'upload' | 'download' | 'delete' | 'getPresignedUrl';
  bucket?: string;
  key?: string;
  data?: string;
  expiresIn?: number;
}

export interface LambdaAction {
  action: 'listFunctions' | 'getFunction' | 'invokeFunction' | 'createFunction' | 'updateFunction' | 'deleteFunction';
  functionName?: string;
  data?: any;
  payload?: any;
}

export interface AzureConfig {
  connectionString: string;
  containerName?: string;
}

export interface AzureAction {
  action: 'listContainers' | 'listBlobs' | 'upload' | 'download' | 'delete' | 'getBlobUrl';
  containerName?: string;
  blobName?: string;
  data?: string;
}

export interface GoogleDriveConfig {
  credentials: any;
  folderId?: string;
}

export interface GoogleDriveAction {
  action: 'listFiles' | 'getFile' | 'uploadFile' | 'downloadFile' | 'deleteFile' | 'createFolder';
  fileId?: string;
  data?: any;
  folderId?: string;
}

export interface GoogleAnalyticsConfig {
  credentials: any;
  propertyId?: string;
}

export interface GoogleAnalyticsAction {
  action: 'getReports' | 'getRealtime' | 'getEvents' | 'getUsers';
  propertyId?: string;
  dateRange?: string;
  metrics?: string[];
  dimensions?: string[];
}

export interface HerokuConfig {
  apiKey: string;
  appName?: string;
}

export interface HerokuAction {
  action: 'getApps' | 'getApp' | 'createApp' | 'deleteApp' | 'getDynos' | 'restartDynos' | 'getLogs';
  appName?: string;
  data?: any;
}

export interface CloudflareConfig {
  apiKey: string;
  email: string;
  zoneId?: string;
}

export interface CloudflareAction {
  action: 'listZones' | 'getZone' | 'getDNSRecords' | 'createDNSRecord' | 'updateDNSRecord' | 'deleteDNSRecord';
  zoneId?: string;
  recordId?: string;
  data?: any;
}

export interface MailchimpConfig {
  apiKey: string;
  server?: string;
}

export interface MailchimpAction {
  action: 'getLists' | 'getList' | 'createList' | 'addMember' | 'getMembers' | 'getMember' | 'updateMember' | 'deleteMember' | 'sendCampaign' | 'getCampaigns';
  listId?: string;
  memberId?: string;
  campaignId?: string;
  data?: any;
}

export interface HubSpotConfig {
  apiKey: string;
  portalId?: string;
}

export interface HubSpotAction {
  action: 'getContacts' | 'getContact' | 'createContact' | 'updateContact' | 'deleteContact' | 'getDeals' | 'getDeal' | 'createDeal' | 'updateDeal' | 'getCompanies' | 'createCompany';
  contactId?: string;
  dealId?: string;
  companyId?: string;
  data?: any;
}

export interface SalesforceConfig {
  loginUrl: string;
  username: string;
  password: string;
  securityToken: string;
}

export interface SalesforceAction {
  action: 'query' | 'create' | 'update' | 'delete' | 'getRecords' | 'getRecord';
  object?: string;
  recordId?: string;
  data?: any;
  query?: string;
}

export interface ZendeskConfig {
  subdomain: string;
  email: string;
  apiToken: string;
}

export interface ZendeskAction {
  action: 'getTickets' | 'getTicket' | 'createTicket' | 'updateTicket' | 'deleteTicket' | 'getUsers' | 'getUser' | 'createUser';
  ticketId?: string;
  userId?: string;
  data?: any;
}

export interface PayPalConfig {
  clientId: string;
  clientSecret: string;
  mode?: 'sandbox' | 'live';
}

export interface PayPalAction {
  action: 'createOrder' | 'captureOrder' | 'getOrder' | 'createPayment' | 'executePayment' | 'getPayment';
  orderId?: string;
  paymentId?: string;
  data?: any;
}

export interface JiraConfig {
  baseUrl: string;
  username: string;
  apiToken: string;
}

export interface JiraAction {
  action: 'getProjects' | 'getProject' | 'getIssues' | 'getIssue' | 'createIssue' | 'updateIssue' | 'deleteIssue' | 'getBoards' | 'getSprints';
  projectKey?: string;
  issueId?: string;
  boardId?: string;
  sprintId?: string;
  data?: any;
}

export interface TrelloConfig {
  apiKey: string;
  token: string;
}

export interface TrelloAction {
  action: 'getBoards' | 'getBoard' | 'getLists' | 'getList' | 'getCards' | 'getCard' | 'createCard' | 'updateCard' | 'deleteCard' | 'createList';
  boardId?: string;
  listId?: string;
  cardId?: string;
  data?: any;
}

export interface AsanaConfig {
  accessToken: string;
  workspaceId?: string;
}

export interface AsanaAction {
  action: 'getProjects' | 'getProject' | 'getTasks' | 'getTask' | 'createTask' | 'updateTask' | 'deleteTask' | 'getTeams';
  projectId?: string;
  taskId?: string;
  teamId?: string;
  data?: any;
}

export interface TwitterConfig {
  apiKey: string;
  apiSecret: string;
  accessToken: string;
  accessSecret: string;
}

export interface TwitterAction {
  action: 'getTweets' | 'getTweet' | 'createTweet' | 'deleteTweet' | 'getUser' | 'getTimeline';
  tweetId?: string;
  userId?: string;
  data?: any;
}

export interface FacebookConfig {
  accessToken: string;
  appId?: string;
  appSecret?: string;
}

export interface FacebookAction {
  action: 'getPosts' | 'getPost' | 'createPost' | 'deletePost' | 'getPages' | 'getPage' | 'getAds';
  postId?: string;
  pageId?: string;
  data?: any;
}

export interface SendinblueConfig {
  apiKey: string;
}

export interface SendinblueAction {
  action: 'getContacts' | 'getContact' | 'createContact' | 'updateContact' | 'deleteContact' | 'sendEmail' | 'getCampaigns' | 'sendSMS';
  contactId?: string;
  campaignId?: string;
  data?: any;
}

export interface MailgunConfig {
  apiKey: string;
  domain: string;
}

export interface MailgunAction {
  action: 'sendEmail' | 'getMessages' | 'getMessage' | 'deleteMessage' | 'getStats';
  messageId?: string;
  data?: any;
}

export interface PipedriveConfig {
  apiToken: string;
  companyDomain: string;
}

export interface PipedriveAction {
  action: 'getDeals' | 'getDeal' | 'createDeal' | 'updateDeal' | 'deleteDeal' | 'getContacts' | 'getContact' | 'createContact';
  dealId?: string;
  contactId?: string;
  data?: any;
}

export interface IntercomConfig {
  accessToken: string;
}

export interface IntercomAction {
  action: 'getConversations' | 'getConversation' | 'sendMessage' | 'getContacts' | 'getContact' | 'createContact';
  conversationId?: string;
  contactId?: string;
  data?: any;
}

export interface DocuSignConfig {
  clientId: string;
  userId: string;
  privateKey: string;
  basePath?: string;
}

export interface DocuSignAction {
  action: 'getEnvelopes' | 'getEnvelope' | 'createEnvelope' | 'sendEnvelope' | 'getDocuments';
  envelopeId?: string;
  data?: any;
}

export interface MicrosoftGraphConfig {
  clientId: string;
  clientSecret: string;
  tenantId: string;
}

export interface MicrosoftGraphAction {
  action: 'getFiles' | 'getFile' | 'uploadFile' | 'deleteFile' | 'getMessages' | 'sendMessage' | 'getEvents' | 'createEvent';
  driveId?: string;
  itemId?: string;
  folderId?: string;
  data?: any;
}

export interface MondayConfig {
  apiKey: string;
}

export interface MondayAction {
  action: 'getBoards' | 'getBoard' | 'getItems' | 'getItem' | 'createItem' | 'updateItem' | 'deleteItem' | 'getColumns';
  boardId?: string;
  itemId?: string;
  data?: any;
}

export interface LinearConfig {
  apiKey: string;
}

export interface LinearAction {
  action: 'getTeams' | 'getIssues' | 'getIssue' | 'createIssue' | 'updateIssue' | 'getProjects' | 'getProject';
  teamId?: string;
  issueId?: string;
  projectId?: string;
  data?: any;
}

export interface LinkedInConfig {
  accessToken: string;
}

export interface LinkedInAction {
  action: 'getProfile' | 'getPosts' | 'createPost' | 'getConnections' | 'sendMessage';
  postId?: string;
  data?: any;
}

export interface InstagramConfig {
  accessToken: string;
  businessAccountId?: string;
}

export interface InstagramAction {
  action: 'getPosts' | 'getPost' | 'createPost' | 'getStories' | 'getMedia';
  mediaId?: string;
  data?: any;
}

export interface YouTubeConfig {
  apiKey: string;
}

export interface YouTubeAction {
  action: 'getVideos' | 'getVideo' | 'getComments' | 'uploadVideo' | 'getChannels';
  videoId?: string;
  channelId?: string;
  data?: any;
}

export interface KlaviyoConfig {
  apiKey: string;
}

export interface KlaviyoAction {
  action: 'getLists' | 'getList' | 'createList' | 'getMembers' | 'addMember' | 'sendEmail' | 'getCampaigns';
  listId?: string;
  memberId?: string;
  campaignId?: string;
  data?: any;
}

export interface ActiveCampaignConfig {
  apiKey: string;
  apiUrl: string;
}

export interface ActiveCampaignAction {
  action: 'getContacts' | 'getContact' | 'createContact' | 'updateContact' | 'getCampaigns' | 'sendEmail';
  contactId?: string;
  campaignId?: string;
  data?: any;
}

export interface ConvertKitConfig {
  apiKey: string;
}

export interface ConvertKitAction {
  action: 'getSubscribers' | 'getSubscriber' | 'addSubscriber' | 'getForms' | 'getCampaigns';
  subscriberId?: string;
  formId?: string;
  data?: any;
}

export interface CopperConfig {
  apiKey: string;
  email: string;
}

export interface CopperAction {
  action: 'getLeads' | 'getLead' | 'createLead' | 'updateLead' | 'getContacts' | 'getContact';
  leadId?: string;
  contactId?: string;
  data?: any;
}

export interface ZohoConfig {
  accessToken: string;
  organizationId?: string;
}

export interface ZohoAction {
  action: 'getLeads' | 'getLead' | 'createLead' | 'updateLead' | 'getContacts' | 'getContact';
  leadId?: string;
  contactId?: string;
  data?: any;
}

export interface FreshdeskConfig {
  apiKey: string;
  domain: string;
}

export interface FreshdeskAction {
  action: 'getTickets' | 'getTicket' | 'createTicket' | 'updateTicket' | 'deleteTicket' | 'getContacts';
  ticketId?: string;
  contactId?: string;
  data?: any;
}

export interface HelpScoutConfig {
  apiKey: string;
}

export interface HelpScoutAction {
  action: 'getConversations' | 'getConversation' | 'createConversation' | 'getMailboxes' | 'getCustomers';
  conversationId?: string;
  mailboxId?: string;
  data?: any;
}

export interface PandaDocConfig {
  apiKey: string;
}

export interface PandaDocAction {
  action: 'getDocuments' | 'getDocument' | 'createDocument' | 'sendDocument' | 'getTemplates';
  documentId?: string;
  templateId?: string;
  data?: any;
}

export interface EmailAutomationConfig {
  openaiApiKey?: string;
}

export interface EmailAutomationAction {
  action: 'addAccount' | 'addRule' | 'fetchEmails' | 'processAll' | 'deleteSpam' | 'createFolder';
  account?: any;
  rule?: any;
  email?: string;
  folder?: string;
  limit?: number;
  threshold?: number;
}
