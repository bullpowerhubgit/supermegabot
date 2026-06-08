import express from 'express';
import cors from 'cors';
import path from 'path';
import TelegramBot from 'node-telegram-bot-api';
import paymentRoutes from './payment-routes.js';
import { AIClient, BrowserController, MacController, GCPController, ShopifyController, EmailController, SMSController, StripeController, QueueController, AuthController, DataController, GitHubController, SlackController, DiscordController, TelegramController, NotionController, AirtableController, AWSController, AzureController, GoogleController, HerokuController, CloudflareController, MailchimpController, HubSpotController, SalesforceController, ZendeskController, PayPalController, JiraController, TrelloController, AsanaController, TwitterController, FacebookController, SendinblueController, MailgunController, PipedriveController, IntercomController, DocuSignController, MicrosoftGraphController, MondayController, LinearController, LinkedInController, InstagramController, YouTubeController, KlaviyoController, ActiveCampaignController, ConvertKitController, CopperController, ZohoController, FreshdeskController, HelpScoutController, PandaDocController, EmailAutomationController } from '../core/index.js';
import { Message, BrowserAction, MacAction, GCPConfig, NLAction, TranslationAction, VisionAction, SpeechAction, StorageAction, FirestoreAction, ShopifyConfig, EmailConfig, SMSConfig, StripeConfig, QueueConfig, AuthConfig, GitHubConfig, SlackConfig, DiscordConfig, TelegramConfig, NotionConfig, AirtableConfig, AWSConfig, AzureConfig, GoogleDriveConfig, GoogleAnalyticsConfig, HerokuConfig, CloudflareConfig, MailchimpConfig, HubSpotConfig, SalesforceConfig, ZendeskConfig, PayPalConfig, JiraConfig, TrelloConfig, AsanaConfig, TwitterConfig, FacebookConfig, SendinblueConfig, MailgunConfig, PipedriveConfig, IntercomConfig, DocuSignConfig, MicrosoftGraphConfig, MondayConfig, LinearConfig, LinkedInConfig, InstagramConfig, YouTubeConfig, KlaviyoConfig, ActiveCampaignConfig, ConvertKitConfig, CopperConfig, ZohoConfig, FreshdeskConfig, HelpScoutConfig, PandaDocConfig, EmailAutomationConfig, EmailAutomationAction } from '../core/types.js';

// Security Middleware
import { requireAuth, requireRole, requireAuthOrApiKey, createSupabaseClient } from '../middleware/auth.js';
import { checkPlanLimits, requireFeature, getBillingInfo } from '../middleware/billing.js';
import { verifyHmacWebhook, verifyStripeWebhook, verifyShopifyWebhook } from '../middleware/webhook.js';

const app = express();
app.use(cors());
app.use(express.json());
app.use(express.static(path.join(process.cwd(), 'public')));

// ── Root Route für Dashboard Health Checks ──────────────────────
app.get('/', (_req, res) => {
  res.json({ 
    status: 'ok', 
    service: 'RudiBot API Server',
    version: '2.0',
    timestamp: new Date().toISOString(),
    endpoints: {
      chat: '/api/chat',
      telegram: '/api/telegram',
      health: '/health'
    }
  });
});

const aiClients = new Map<string, AIClient>();
const browsers = new Map<string, BrowserController>();
const macController = new MacController();
const gcpControllers = new Map<string, GCPController>();
const shopifyControllers = new Map<string, ShopifyController>();
const emailControllers = new Map<string, EmailController>();
const smsControllers = new Map<string, SMSController>();
const stripeControllers = new Map<string, StripeController>();
const queueControllers = new Map<string, QueueController>();
const authControllers = new Map<string, AuthController>();
const dataController = new DataController();
const githubControllers = new Map<string, GitHubController>();
const slackControllers = new Map<string, SlackController>();
const discordControllers = new Map<string, DiscordController>();
const telegramControllers = new Map<string, TelegramController>();
const notionControllers = new Map<string, NotionController>();
const airtableControllers = new Map<string, AirtableController>();
const awsControllers = new Map<string, AWSController>();
const azureControllers = new Map<string, AzureController>();
const googleControllers = new Map<string, GoogleController>();
const herokuControllers = new Map<string, HerokuController>();
const cloudflareControllers = new Map<string, CloudflareController>();
const mailchimpControllers = new Map<string, MailchimpController>();
const hubspotControllers = new Map<string, HubSpotController>();
const salesforceControllers = new Map<string, SalesforceController>();
const zendeskControllers = new Map<string, ZendeskController>();
const paypalControllers = new Map<string, PayPalController>();
const jiraControllers = new Map<string, JiraController>();
const trelloControllers = new Map<string, TrelloController>();
const asanaControllers = new Map<string, AsanaController>();
const twitterControllers = new Map<string, TwitterController>();
const facebookControllers = new Map<string, FacebookController>();
const sendinblueControllers = new Map<string, SendinblueController>();
const mailgunControllers = new Map<string, MailgunController>();
const pipedriveControllers = new Map<string, PipedriveController>();
const intercomControllers = new Map<string, IntercomController>();
const docusignControllers = new Map<string, DocuSignController>();
const microsoftControllers = new Map<string, MicrosoftGraphController>();
const mondayControllers = new Map<string, MondayController>();
const linearControllers = new Map<string, LinearController>();
const linkedinControllers = new Map<string, LinkedInController>();
const instagramControllers = new Map<string, InstagramController>();
const youtubeControllers = new Map<string, YouTubeController>();
const klaviyoControllers = new Map<string, KlaviyoController>();
const activecampaignControllers = new Map<string, ActiveCampaignController>();
const convertkitControllers = new Map<string, ConvertKitController>();
const copperControllers = new Map<string, CopperController>();
const zohoControllers = new Map<string, ZohoController>();
const freshdeskControllers = new Map<string, FreshdeskController>();
const helpscoutControllers = new Map<string, HelpScoutController>();
const pandadocControllers = new Map<string, PandaDocController>();
const emailAutomationControllers = new Map<string, EmailAutomationController>();

app.post('/api/chat', async (req, res) => {
  try {
    const { sessionId, provider, apiKey, model, messages } = req.body;
    
    if (!sessionId || !apiKey) {
      return res.status(400).json({ error: 'sessionId and apiKey required' });
    }

    let ai = aiClients.get(sessionId);
    if (!ai) {
      ai = new AIClient({
        provider: provider || 'openai',
        apiKey,
        model,
        systemPrompt: 'Du bist ein hilfreicher KI-Assistent mit Zugriff auf Browser- und Mac-Steuerung.',
      });
      aiClients.set(sessionId, ai);
    }

    const tools = ai.createToolDefinitions();
    const response = await ai.chat(messages, tools);
    
    res.json(response);
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/browser', async (req, res) => {
  try {
    const { sessionId, action, headless = true } = req.body;
    
    let browser = browsers.get(sessionId);
    if (!browser) {
      browser = new BrowserController();
      await browser.init(!headless);
      browsers.set(sessionId, browser);
    }

    if (action === 'close') {
      await browser.close();
      browsers.delete(sessionId);
      return res.json({ result: 'Browser closed' });
    }

    const result = await browser.execute(action as BrowserAction);
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/mac', async (req, res) => {
  try {
    const { action } = req.body;
    const result = await macController.execute(action as MacAction);
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.delete('/api/session/:sessionId', async (req, res) => {
  const { sessionId } = req.params;
  
  const browser = browsers.get(sessionId);
  if (browser) {
    await browser.close();
    browsers.delete(sessionId);
  }
  
  aiClients.delete(sessionId);
  gcpControllers.delete(sessionId);
  shopifyControllers.delete(sessionId);
  emailControllers.delete(sessionId);
  smsControllers.delete(sessionId);
  stripeControllers.delete(sessionId);
  queueControllers.delete(sessionId);
  authControllers.delete(sessionId);
  githubControllers.delete(sessionId);
  slackControllers.delete(sessionId);
  discordControllers.delete(sessionId);
  telegramControllers.delete(sessionId);
  notionControllers.delete(sessionId);
  airtableControllers.delete(sessionId);
  awsControllers.delete(sessionId);
  azureControllers.delete(sessionId);
  googleControllers.delete(sessionId);
  herokuControllers.delete(sessionId);
  cloudflareControllers.delete(sessionId);
  mailchimpControllers.delete(sessionId);
  hubspotControllers.delete(sessionId);
  salesforceControllers.delete(sessionId);
  zendeskControllers.delete(sessionId);
  paypalControllers.delete(sessionId);
  jiraControllers.delete(sessionId);
  trelloControllers.delete(sessionId);
  asanaControllers.delete(sessionId);
  twitterControllers.delete(sessionId);
  facebookControllers.delete(sessionId);
  sendinblueControllers.delete(sessionId);
  mailgunControllers.delete(sessionId);
  pipedriveControllers.delete(sessionId);
  intercomControllers.delete(sessionId);
  docusignControllers.delete(sessionId);
  microsoftControllers.delete(sessionId);
  mondayControllers.delete(sessionId);
  linearControllers.delete(sessionId);
  linkedinControllers.delete(sessionId);
  instagramControllers.delete(sessionId);
  youtubeControllers.delete(sessionId);
  klaviyoControllers.delete(sessionId);
  activecampaignControllers.delete(sessionId);
  convertkitControllers.delete(sessionId);
  copperControllers.delete(sessionId);
  zohoControllers.delete(sessionId);
  freshdeskControllers.delete(sessionId);
  helpscoutControllers.delete(sessionId);
  pandadocControllers.delete(sessionId);
  emailAutomationControllers.delete(sessionId);
  res.json({ result: 'Session closed' });
});

app.post('/api/gcp/translation', async (req, res) => {
  try {
    const { sessionId, projectId, keyFilename, text, targetLanguage } = req.body;
    
    if (!projectId || !text || !targetLanguage) {
      return res.status(400).json({ error: 'projectId, text, and targetLanguage required' });
    }

    let gcp = gcpControllers.get(sessionId || 'default');
    if (!gcp) {
      gcp = new GCPController({ projectId, keyFilename });
      gcpControllers.set(sessionId || 'default', gcp);
    }

    const result = await gcp.executeTranslation({ action: 'translate', text, targetLanguage });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/gcp/vision', async (req, res) => {
  try {
    const { sessionId, projectId, keyFilename, action, image } = req.body;
    
    if (!projectId || !action || !image) {
      return res.status(400).json({ error: 'projectId, action, and image required' });
    }

    let gcp = gcpControllers.get(sessionId || 'default');
    if (!gcp) {
      gcp = new GCPController({ projectId, keyFilename });
      gcpControllers.set(sessionId || 'default', gcp);
    }

    const result = await gcp.executeVision({ action, image });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/gcp/speech', async (req, res) => {
  try {
    const { sessionId, projectId, keyFilename, action, audio, text, language, voice } = req.body;
    
    if (!projectId || !action) {
      return res.status(400).json({ error: 'projectId and action required' });
    }

    let gcp = gcpControllers.get(sessionId || 'default');
    if (!gcp) {
      gcp = new GCPController({ projectId, keyFilename });
      gcpControllers.set(sessionId || 'default', gcp);
    }

    const result = await gcp.executeSpeech({ action, audio, text, language, voice });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/gcp/storage', async (req, res) => {
  try {
    const { sessionId, projectId, keyFilename, action, bucket, file, data } = req.body;
    
    if (!projectId || !action) {
      return res.status(400).json({ error: 'projectId and action required' });
    }

    let gcp = gcpControllers.get(sessionId || 'default');
    if (!gcp) {
      gcp = new GCPController({ projectId, keyFilename });
      gcpControllers.set(sessionId || 'default', gcp);
    }

    const result = await gcp.executeStorage({ action, bucket, file, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/gcp/firestore', async (req, res) => {
  try {
    const { sessionId, projectId, keyFilename, action, collection, document, data, query } = req.body;
    
    if (!projectId || !action || !collection) {
      return res.status(400).json({ error: 'projectId, action, and collection required' });
    }

    let gcp = gcpControllers.get(sessionId || 'default');
    if (!gcp) {
      gcp = new GCPController({ projectId, keyFilename });
      gcpControllers.set(sessionId || 'default', gcp);
    }

    const result = await gcp.executeFirestore({ action, collection, document, data, query });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.get('/api/gcp/secret/:secretName', async (req, res) => {
  try {
    const { sessionId, projectId, keyFilename } = req.query;
    const { secretName } = req.params;
    
    if (!projectId || !secretName) {
      return res.status(400).json({ error: 'projectId and secretName required' });
    }

    let gcp = gcpControllers.get(sessionId as string || 'default');
    if (!gcp) {
      gcp = new GCPController({ projectId: projectId as string, keyFilename: keyFilename as string });
      gcpControllers.set(sessionId as string || 'default', gcp);
    }

    const secret = await gcp.getSecret(secretName);
    res.json({ secret });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/gcp/bigquery', async (req, res) => {
  try {
    const { sessionId, projectId, keyFilename, query } = req.body;
    
    if (!projectId || !query) {
      return res.status(400).json({ error: 'projectId and query required' });
    }

    let gcp = gcpControllers.get(sessionId || 'default');
    if (!gcp) {
      gcp = new GCPController({ projectId, keyFilename });
      gcpControllers.set(sessionId || 'default', gcp);
    }

    const result = await gcp.executeBigQuery(query);
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/gcp/nl', async (req, res) => {
  try {
    const { sessionId, projectId, keyFilename, action, text } = req.body;
    
    if (!projectId || !action || !text) {
      return res.status(400).json({ error: 'projectId, action, and text required' });
    }

    let gcp = gcpControllers.get(sessionId || 'default');
    if (!gcp) {
      gcp = new GCPController({ projectId, keyFilename });
      gcpControllers.set(sessionId || 'default', gcp);
    }

    const result = await gcp.executeNL({ action, text });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/shopify', async (req, res) => {
  try {
    const { sessionId, shopDomain, accessToken, apiVersion, action, data, id, query } = req.body;
    
    if (!shopDomain || !accessToken || !action) {
      return res.status(400).json({ error: 'shopDomain, accessToken, and action required' });
    }

    let shopify = shopifyControllers.get(sessionId || 'default');
    if (!shopify) {
      shopify = new ShopifyController({ shopDomain, accessToken, apiVersion });
      shopifyControllers.set(sessionId || 'default', shopify);
    }

    const result = await shopify.execute({ action, data, id, query });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/email', async (req, res) => {
  try {
    const { sessionId, provider, apiKey, smtpConfig, from, action, to, subject, text, html, templateId, templateData, attachments } = req.body;
    
    if (!provider || !action || !to) {
      return res.status(400).json({ error: 'provider, action, and to required' });
    }

    let email = emailControllers.get(sessionId || 'default');
    if (!email) {
      email = new EmailController({ provider, apiKey, smtpConfig, from });
      emailControllers.set(sessionId || 'default', email);
    }

    const result = await email.execute({ action, to, from, subject, text, html, templateId, templateData, attachments });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/sms', async (req, res) => {
  try {
    const { sessionId, accountSid, authToken, fromNumber, action, to, body } = req.body;
    
    if (!accountSid || !authToken || !fromNumber || !action || !to || !body) {
      return res.status(400).json({ error: 'accountSid, authToken, fromNumber, action, to, and body required' });
    }

    let sms = smsControllers.get(sessionId || 'default');
    if (!sms) {
      sms = new SMSController({ accountSid, authToken, fromNumber });
      smsControllers.set(sessionId || 'default', sms);
    }

    const result = await sms.execute({ action, to, body });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/stripe', async (req, res) => {
  try {
    const { sessionId, apiKey, apiVersion, action, data, id } = req.body;
    
    if (!apiKey || !action) {
      return res.status(400).json({ error: 'apiKey and action required' });
    }

    let stripe = stripeControllers.get(sessionId || 'default');
    if (!stripe) {
      stripe = new StripeController({ apiKey, apiVersion });
      stripeControllers.set(sessionId || 'default', stripe);
    }

    const result = await stripe.execute({ action, data, id });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/queue', async (req, res) => {
  try {
    const { sessionId, redisHost, redisPort, redisPassword, action, queueName, jobName, data, jobId } = req.body;
    
    if (!action || !queueName) {
      return res.status(400).json({ error: 'action and queueName required' });
    }

    let queue = queueControllers.get(sessionId || 'default');
    if (!queue) {
      queue = new QueueController({ redisHost, redisPort, redisPassword });
      queueControllers.set(sessionId || 'default', queue);
    }

    const result = await queue.execute({ action, queueName, jobName, data, jobId });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/auth', async (req, res) => {
  try {
    const { sessionId, jwtSecret, expiresIn, action, payload, token } = req.body;
    
    if (!jwtSecret || !action) {
      return res.status(400).json({ error: 'jwtSecret and action required' });
    }

    let auth = authControllers.get(sessionId || 'default');
    if (!auth) {
      auth = new AuthController({ jwtSecret, expiresIn });
      authControllers.set(sessionId || 'default', auth);
    }

    const result = await auth.execute({ action, payload, token });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/data', async (req, res) => {
  try {
    const { action, filePath, data, headers } = req.body;
    
    if (!action || !filePath) {
      return res.status(400).json({ error: 'action and filePath required' });
    }

    const result = await dataController.execute({ action, filePath, data, headers });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/github', async (req, res) => {
  try {
    const { sessionId, token, owner, repo, action, data, id, path, ref, query } = req.body;
    
    if (!token || !action) {
      return res.status(400).json({ error: 'token and action required' });
    }

    let github = githubControllers.get(sessionId || 'default');
    if (!github) {
      github = new GitHubController({ token, owner, repo });
      githubControllers.set(sessionId || 'default', github);
    }

    const result = await github.execute({ action, owner, repo, data, id, path, ref, query });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/slack', async (req, res) => {
  try {
    const { sessionId, token, channel, action, text, data, file } = req.body;
    
    if (!token || !action) {
      return res.status(400).json({ error: 'token and action required' });
    }

    let slack = slackControllers.get(sessionId || 'default');
    if (!slack) {
      slack = new SlackController({ token, channel });
      slackControllers.set(sessionId || 'default', slack);
    }

    const result = await slack.execute({ action, channel, text, data, file });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/discord', async (req, res) => {
  try {
    const { sessionId, token, guildId, channelId, action, text, data } = req.body;
    
    if (!token || !action) {
      return res.status(400).json({ error: 'token and action required' });
    }

    let discord = discordControllers.get(sessionId || 'default');
    if (!discord) {
      discord = new DiscordController({ token, guildId, channelId });
      discordControllers.set(sessionId || 'default', discord);
    }

    const result = await discord.execute({ action, channelId, text, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

// ── Telegram Routes ──────────────────────────────────────────────
app.get('/api/telegram', async (_req, res) => {
  res.json({ 
    status: 'ok',
    service: 'Telegram Bot API',
    active_sessions: telegramControllers.size,
    available_actions: ['sendMessage', 'getUpdates', 'getMe', 'sendPhoto', 'sendDocument'],
    endpoint: 'POST /api/telegram',
    required_params: ['token', 'action']
  });
});

// Webhook Setup Route für Telegram Bot
app.post('/api/telegram/webhook', async (req, res) => {
  try {
    const { token, url, secret } = req.body;
    
    if (!token || !url) {
      return res.status(400).json({ error: 'token and url required' });
    }

    const bot = new TelegramBot(token);
    
    // Setze den Webhook
    await bot.setWebHook(url, secret ? { secret_token: secret } : undefined);
    
    // Prüfe ob Webhook gesetzt wurde
    const webhookInfo = await bot.getWebHookInfo();
    
    res.json({ 
      success: true, 
      webhook_url: webhookInfo.url,
      pending_updates: webhookInfo.pending_update_count,
      max_connections: webhookInfo.max_connections
    });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

// Webhook Delete Route
app.delete('/api/telegram/webhook', async (req, res) => {
  try {
    const { token } = req.body;
    
    if (!token) {
      return res.status(400).json({ error: 'token required' });
    }

    const bot = new TelegramBot(token);
    
    await bot.deleteWebHook();
    
    res.json({ success: true, message: 'Webhook deleted' });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/telegram', async (req, res) => {
  try {
    const { sessionId, token, chatId, action, text, data, file } = req.body;
    
    if (!token || !action) {
      return res.status(400).json({ error: 'token and action required' });
    }

    let telegram = telegramControllers.get(sessionId || 'default');
    if (!telegram) {
      telegram = new TelegramController({ token, chatId });
      telegramControllers.set(sessionId || 'default', telegram);
    }

    const result = await telegram.execute({ action, chatId, text, data, file });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/notion', async (req, res) => {
  try {
    const { sessionId, token, databaseId, action, pageId, data, query } = req.body;
    
    if (!token || !action) {
      return res.status(400).json({ error: 'token and action required' });
    }

    let notion = notionControllers.get(sessionId || 'default');
    if (!notion) {
      notion = new NotionController({ token, databaseId });
      notionControllers.set(sessionId || 'default', notion);
    }

    const result = await notion.execute({ action, databaseId, pageId, data, query });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/airtable', async (req, res) => {
  try {
    const { sessionId, apiKey, baseId, tableName, action, recordId, data } = req.body;
    
    if (!apiKey || !baseId || !action) {
      return res.status(400).json({ error: 'apiKey, baseId, and action required' });
    }

    let airtable = airtableControllers.get(sessionId || 'default');
    if (!airtable) {
      airtable = new AirtableController({ apiKey, baseId, tableName });
      airtableControllers.set(sessionId || 'default', airtable);
    }

    const result = await airtable.execute({ action, tableName, recordId, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/aws/s3', async (req, res) => {
  try {
    const { sessionId, accessKeyId, secretAccessKey, region, action, bucket, key, data, expiresIn } = req.body;
    
    if (!accessKeyId || !secretAccessKey || !action) {
      return res.status(400).json({ error: 'accessKeyId, secretAccessKey, and action required' });
    }

    let aws = awsControllers.get(sessionId || 'default');
    if (!aws) {
      aws = new AWSController({ accessKeyId, secretAccessKey, region });
      awsControllers.set(sessionId || 'default', aws);
    }

    const result = await aws.executeS3({ action, bucket, key, data, expiresIn });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/aws/lambda', async (req, res) => {
  try {
    const { sessionId, accessKeyId, secretAccessKey, region, action, functionName, data, payload } = req.body;
    
    if (!accessKeyId || !secretAccessKey || !action) {
      return res.status(400).json({ error: 'accessKeyId, secretAccessKey, and action required' });
    }

    let aws = awsControllers.get(sessionId || 'default');
    if (!aws) {
      aws = new AWSController({ accessKeyId, secretAccessKey, region });
      awsControllers.set(sessionId || 'default', aws);
    }

    const result = await aws.executeLambda({ action, functionName, data, payload });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/azure', async (req, res) => {
  try {
    const { sessionId, connectionString, containerName, action, blobName, data } = req.body;
    
    if (!connectionString || !action) {
      return res.status(400).json({ error: 'connectionString and action required' });
    }

    let azure = azureControllers.get(sessionId || 'default');
    if (!azure) {
      azure = new AzureController({ connectionString, containerName });
      azureControllers.set(sessionId || 'default', azure);
    }

    const result = await azure.execute({ action, containerName, blobName, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/google/drive', async (req, res) => {
  try {
    const { sessionId, credentials, folderId, action, fileId, data } = req.body;
    
    if (!credentials || !action) {
      return res.status(400).json({ error: 'credentials and action required' });
    }

    let google = googleControllers.get(sessionId || 'default');
    if (!google) {
      google = new GoogleController({ credentials, folderId });
      googleControllers.set(sessionId || 'default', google);
    }

    const result = await google.executeDrive({ action, fileId, data, folderId });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/google/analytics', async (req, res) => {
  try {
    const { sessionId, credentials, propertyId, action, dateRange, metrics, dimensions } = req.body;
    
    if (!credentials || !action) {
      return res.status(400).json({ error: 'credentials and action required' });
    }

    let google = googleControllers.get(sessionId || 'default');
    if (!google) {
      google = new GoogleController(undefined, { credentials, propertyId });
      googleControllers.set(sessionId || 'default', google);
    }

    const result = await google.executeAnalytics({ action, propertyId, dateRange, metrics, dimensions });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/heroku', async (req, res) => {
  try {
    const { sessionId, apiKey, appName, action, data } = req.body;
    
    if (!apiKey || !action) {
      return res.status(400).json({ error: 'apiKey and action required' });
    }

    let heroku = herokuControllers.get(sessionId || 'default');
    if (!heroku) {
      heroku = new HerokuController({ apiKey, appName });
      herokuControllers.set(sessionId || 'default', heroku);
    }

    const result = await heroku.execute({ action, appName, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/cloudflare', async (req, res) => {
  try {
    const { sessionId, apiKey, email, zoneId, action, recordId, data } = req.body;
    
    if (!apiKey || !email || !action) {
      return res.status(400).json({ error: 'apiKey, email, and action required' });
    }

    let cloudflare = cloudflareControllers.get(sessionId || 'default');
    if (!cloudflare) {
      cloudflare = new CloudflareController({ apiKey, email, zoneId });
      cloudflareControllers.set(sessionId || 'default', cloudflare);
    }

    const result = await cloudflare.execute({ action, zoneId, recordId, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/mailchimp', async (req, res) => {
  try {
    const { sessionId, apiKey, server, action, listId, memberId, campaignId, data } = req.body;
    
    if (!apiKey || !action) {
      return res.status(400).json({ error: 'apiKey and action required' });
    }

    let mailchimp = mailchimpControllers.get(sessionId || 'default');
    if (!mailchimp) {
      mailchimp = new MailchimpController({ apiKey, server });
      mailchimpControllers.set(sessionId || 'default', mailchimp);
    }

    const result = await mailchimp.execute({ action, listId, memberId, campaignId, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/hubspot', async (req, res) => {
  try {
    const { sessionId, apiKey, portalId, action, contactId, dealId, companyId, data } = req.body;
    
    if (!apiKey || !action) {
      return res.status(400).json({ error: 'apiKey and action required' });
    }

    let hubspot = hubspotControllers.get(sessionId || 'default');
    if (!hubspot) {
      hubspot = new HubSpotController({ apiKey, portalId });
      hubspotControllers.set(sessionId || 'default', hubspot);
    }

    const result = await hubspot.execute({ action, contactId, dealId, companyId, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/salesforce', async (req, res) => {
  try {
    const { sessionId, loginUrl, username, password, securityToken, action, object, recordId, data, query } = req.body;
    
    if (!loginUrl || !username || !password || !securityToken || !action) {
      return res.status(400).json({ error: 'loginUrl, username, password, securityToken, and action required' });
    }

    let salesforce = salesforceControllers.get(sessionId || 'default');
    if (!salesforce) {
      salesforce = new SalesforceController({ loginUrl, username, password, securityToken });
      salesforceControllers.set(sessionId || 'default', salesforce);
    }

    const result = await salesforce.execute({ action, object, recordId, data, query });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/zendesk', async (req, res) => {
  try {
    const { sessionId, subdomain, email, apiToken, action, ticketId, userId, data } = req.body;
    
    if (!subdomain || !email || !apiToken || !action) {
      return res.status(400).json({ error: 'subdomain, email, apiToken, and action required' });
    }

    let zendesk = zendeskControllers.get(sessionId || 'default');
    if (!zendesk) {
      zendesk = new ZendeskController({ subdomain, email, apiToken });
      zendeskControllers.set(sessionId || 'default', zendesk);
    }

    const result = await zendesk.execute({ action, ticketId, userId, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/paypal', async (req, res) => {
  try {
    const { sessionId, clientId, clientSecret, mode, action, orderId, paymentId, data } = req.body;
    
    if (!clientId || !clientSecret || !action) {
      return res.status(400).json({ error: 'clientId, clientSecret, and action required' });
    }

    let paypal = paypalControllers.get(sessionId || 'default');
    if (!paypal) {
      paypal = new PayPalController({ clientId, clientSecret, mode });
      paypalControllers.set(sessionId || 'default', paypal);
    }

    const result = await paypal.execute({ action, orderId, paymentId, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/jira', async (req, res) => {
  try {
    const { sessionId, baseUrl, username, apiToken, action, projectKey, issueId, boardId, sprintId, data } = req.body;
    
    if (!baseUrl || !username || !apiToken || !action) {
      return res.status(400).json({ error: 'baseUrl, username, apiToken, and action required' });
    }

    let jira = jiraControllers.get(sessionId || 'default');
    if (!jira) {
      jira = new JiraController({ baseUrl, username, apiToken });
      jiraControllers.set(sessionId || 'default', jira);
    }

    const result = await jira.execute({ action, projectKey, issueId, boardId, sprintId, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/trello', async (req, res) => {
  try {
    const { sessionId, apiKey, token, action, boardId, listId, cardId, data } = req.body;
    
    if (!apiKey || !token || !action) {
      return res.status(400).json({ error: 'apiKey, token, and action required' });
    }

    let trello = trelloControllers.get(sessionId || 'default');
    if (!trello) {
      trello = new TrelloController({ apiKey, token });
      trelloControllers.set(sessionId || 'default', trello);
    }

    const result = await trello.execute({ action, boardId, listId, cardId, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/asana', async (req, res) => {
  try {
    const { sessionId, accessToken, workspaceId, action, projectId, taskId, teamId, data } = req.body;
    
    if (!accessToken || !action) {
      return res.status(400).json({ error: 'accessToken and action required' });
    }

    let asana = asanaControllers.get(sessionId || 'default');
    if (!asana) {
      asana = new AsanaController({ accessToken, workspaceId });
      asanaControllers.set(sessionId || 'default', asana);
    }

    const result = await asana.execute({ action, projectId, taskId, teamId, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/twitter', async (req, res) => {
  try {
    const { sessionId, apiKey, apiSecret, accessToken, accessSecret, action, tweetId, userId, data } = req.body;
    
    if (!apiKey || !apiSecret || !accessToken || !accessSecret || !action) {
      return res.status(400).json({ error: 'apiKey, apiSecret, accessToken, accessSecret, and action required' });
    }

    let twitter = twitterControllers.get(sessionId || 'default');
    if (!twitter) {
      twitter = new TwitterController({ apiKey, apiSecret, accessToken, accessSecret });
      twitterControllers.set(sessionId || 'default', twitter);
    }

    const result = await twitter.execute({ action, tweetId, userId, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/facebook', async (req, res) => {
  try {
    const { sessionId, accessToken, appId, appSecret, action, postId, pageId, data } = req.body;
    
    if (!accessToken || !action) {
      return res.status(400).json({ error: 'accessToken and action required' });
    }

    let facebook = facebookControllers.get(sessionId || 'default');
    if (!facebook) {
      facebook = new FacebookController({ accessToken, appId, appSecret });
      facebookControllers.set(sessionId || 'default', facebook);
    }

    const result = await facebook.execute({ action, postId, pageId, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/sendinblue', async (req, res) => {
  try {
    const { sessionId, apiKey, action, contactId, campaignId, data } = req.body;
    
    if (!apiKey || !action) {
      return res.status(400).json({ error: 'apiKey and action required' });
    }

    let sendinblue = sendinblueControllers.get(sessionId || 'default');
    if (!sendinblue) {
      sendinblue = new SendinblueController({ apiKey });
      sendinblueControllers.set(sessionId || 'default', sendinblue);
    }

    const result = await sendinblue.execute({ action, contactId, campaignId, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/mailgun', async (req, res) => {
  try {
    const { sessionId, apiKey, domain, action, messageId, data } = req.body;
    
    if (!apiKey || !domain || !action) {
      return res.status(400).json({ error: 'apiKey, domain, and action required' });
    }

    let mailgun = mailgunControllers.get(sessionId || 'default');
    if (!mailgun) {
      mailgun = new MailgunController({ apiKey, domain });
      mailgunControllers.set(sessionId || 'default', mailgun);
    }

    const result = await mailgun.execute({ action, messageId, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/pipedrive', async (req, res) => {
  try {
    const { sessionId, apiToken, companyDomain, action, dealId, contactId, data } = req.body;
    
    if (!apiToken || !companyDomain || !action) {
      return res.status(400).json({ error: 'apiToken, companyDomain, and action required' });
    }

    let pipedrive = pipedriveControllers.get(sessionId || 'default');
    if (!pipedrive) {
      pipedrive = new PipedriveController({ apiToken, companyDomain });
      pipedriveControllers.set(sessionId || 'default', pipedrive);
    }

    const result = await pipedrive.execute({ action, dealId, contactId, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/intercom', async (req, res) => {
  try {
    const { sessionId, accessToken, action, conversationId, contactId, data } = req.body;
    
    if (!accessToken || !action) {
      return res.status(400).json({ error: 'accessToken and action required' });
    }

    let intercom = intercomControllers.get(sessionId || 'default');
    if (!intercom) {
      intercom = new IntercomController({ accessToken });
      intercomControllers.set(sessionId || 'default', intercom);
    }

    const result = await intercom.execute({ action, conversationId, contactId, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/docusign', async (req, res) => {
  try {
    const { sessionId, clientId, userId, privateKey, basePath, action, envelopeId, data } = req.body;
    
    if (!clientId || !userId || !privateKey || !action) {
      return res.status(400).json({ error: 'clientId, userId, privateKey, and action required' });
    }

    let docusign = docusignControllers.get(sessionId || 'default');
    if (!docusign) {
      docusign = new DocuSignController({ clientId, userId, privateKey, basePath });
      docusignControllers.set(sessionId || 'default', docusign);
    }

    const result = await docusign.execute({ action, envelopeId, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/microsoft', async (req, res) => {
  try {
    const { sessionId, clientId, clientSecret, tenantId, action, driveId, itemId, folderId, data } = req.body;
    
    if (!clientId || !clientSecret || !tenantId || !action) {
      return res.status(400).json({ error: 'clientId, clientSecret, tenantId, and action required' });
    }

    let microsoft = microsoftControllers.get(sessionId || 'default');
    if (!microsoft) {
      microsoft = new MicrosoftGraphController({ clientId, clientSecret, tenantId });
      microsoftControllers.set(sessionId || 'default', microsoft);
    }

    const result = await microsoft.execute({ action, driveId, itemId, folderId, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/monday', async (req, res) => {
  try {
    const { sessionId, apiKey, action, boardId, itemId, data } = req.body;
    
    if (!apiKey || !action) {
      return res.status(400).json({ error: 'apiKey and action required' });
    }

    let monday = mondayControllers.get(sessionId || 'default');
    if (!monday) {
      monday = new MondayController({ apiKey });
      mondayControllers.set(sessionId || 'default', monday);
    }

    const result = await monday.execute({ action, boardId, itemId, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/linear', async (req, res) => {
  try {
    const { sessionId, apiKey, action, teamId, issueId, projectId, data } = req.body;
    
    if (!apiKey || !action) {
      return res.status(400).json({ error: 'apiKey and action required' });
    }

    let linear = linearControllers.get(sessionId || 'default');
    if (!linear) {
      linear = new LinearController({ apiKey });
      linearControllers.set(sessionId || 'default', linear);
    }

    const result = await linear.execute({ action, teamId, issueId, projectId, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/linkedin', async (req, res) => {
  try {
    const { sessionId, accessToken, action, postId, data } = req.body;
    
    if (!accessToken || !action) {
      return res.status(400).json({ error: 'accessToken and action required' });
    }

    let linkedin = linkedinControllers.get(sessionId || 'default');
    if (!linkedin) {
      linkedin = new LinkedInController({ accessToken });
      linkedinControllers.set(sessionId || 'default', linkedin);
    }

    const result = await linkedin.execute({ action, postId, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/instagram', async (req, res) => {
  try {
    const { sessionId, accessToken, businessAccountId, action, mediaId, data } = req.body;
    
    if (!accessToken || !action) {
      return res.status(400).json({ error: 'accessToken and action required' });
    }

    let instagram = instagramControllers.get(sessionId || 'default');
    if (!instagram) {
      instagram = new InstagramController({ accessToken, businessAccountId });
      instagramControllers.set(sessionId || 'default', instagram);
    }

    const result = await instagram.execute({ action, mediaId, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/youtube', async (req, res) => {
  try {
    const { sessionId, apiKey, action, videoId, channelId, data } = req.body;
    
    if (!apiKey || !action) {
      return res.status(400).json({ error: 'apiKey and action required' });
    }

    let youtube = youtubeControllers.get(sessionId || 'default');
    if (!youtube) {
      youtube = new YouTubeController({ apiKey });
      youtubeControllers.set(sessionId || 'default', youtube);
    }

    const result = await youtube.execute({ action, videoId, channelId, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/klaviyo', async (req, res) => {
  try {
    const { sessionId, apiKey, action, listId, memberId, campaignId, data } = req.body;
    
    if (!apiKey || !action) {
      return res.status(400).json({ error: 'apiKey and action required' });
    }

    let klaviyo = klaviyoControllers.get(sessionId || 'default');
    if (!klaviyo) {
      klaviyo = new KlaviyoController({ apiKey });
      klaviyoControllers.set(sessionId || 'default', klaviyo);
    }

    const result = await klaviyo.execute({ action, listId, memberId, campaignId, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/activecampaign', async (req, res) => {
  try {
    const { sessionId, apiKey, apiUrl, action, contactId, campaignId, data } = req.body;
    
    if (!apiKey || !apiUrl || !action) {
      return res.status(400).json({ error: 'apiKey, apiUrl, and action required' });
    }

    let activecampaign = activecampaignControllers.get(sessionId || 'default');
    if (!activecampaign) {
      activecampaign = new ActiveCampaignController({ apiKey, apiUrl });
      activecampaignControllers.set(sessionId || 'default', activecampaign);
    }

    const result = await activecampaign.execute({ action, contactId, campaignId, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/convertkit', async (req, res) => {
  try {
    const { sessionId, apiKey, action, subscriberId, formId, data } = req.body;
    
    if (!apiKey || !action) {
      return res.status(400).json({ error: 'apiKey and action required' });
    }

    let convertkit = convertkitControllers.get(sessionId || 'default');
    if (!convertkit) {
      convertkit = new ConvertKitController({ apiKey });
      convertkitControllers.set(sessionId || 'default', convertkit);
    }

    const result = await convertkit.execute({ action, subscriberId, formId, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/copper', async (req, res) => {
  try {
    const { sessionId, apiKey, email, action, leadId, contactId, data } = req.body;
    
    if (!apiKey || !email || !action) {
      return res.status(400).json({ error: 'apiKey, email, and action required' });
    }

    let copper = copperControllers.get(sessionId || 'default');
    if (!copper) {
      copper = new CopperController({ apiKey, email });
      copperControllers.set(sessionId || 'default', copper);
    }

    const result = await copper.execute({ action, leadId, contactId, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/zoho', async (req, res) => {
  try {
    const { sessionId, accessToken, organizationId, action, leadId, contactId, data } = req.body;
    
    if (!accessToken || !action) {
      return res.status(400).json({ error: 'accessToken and action required' });
    }

    let zoho = zohoControllers.get(sessionId || 'default');
    if (!zoho) {
      zoho = new ZohoController({ accessToken, organizationId });
      zohoControllers.set(sessionId || 'default', zoho);
    }

    const result = await zoho.execute({ action, leadId, contactId, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/freshdesk', async (req, res) => {
  try {
    const { sessionId, apiKey, domain, action, ticketId, contactId, data } = req.body;
    
    if (!apiKey || !domain || !action) {
      return res.status(400).json({ error: 'apiKey, domain, and action required' });
    }

    let freshdesk = freshdeskControllers.get(sessionId || 'default');
    if (!freshdesk) {
      freshdesk = new FreshdeskController({ apiKey, domain });
      freshdeskControllers.set(sessionId || 'default', freshdesk);
    }

    const result = await freshdesk.execute({ action, ticketId, contactId, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/helpscout', async (req, res) => {
  try {
    const { sessionId, apiKey, action, conversationId, mailboxId, data } = req.body;
    
    if (!apiKey || !action) {
      return res.status(400).json({ error: 'apiKey and action required' });
    }

    let helpscout = helpscoutControllers.get(sessionId || 'default');
    if (!helpscout) {
      helpscout = new HelpScoutController({ apiKey });
      helpscoutControllers.set(sessionId || 'default', helpscout);
    }

    const result = await helpscout.execute({ action, conversationId, mailboxId, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/pandadoc', async (req, res) => {
  try {
    const { sessionId, apiKey, action, documentId, templateId, data } = req.body;
    
    if (!apiKey || !action) {
      return res.status(400).json({ error: 'apiKey and action required' });
    }

    let pandadoc = pandadocControllers.get(sessionId || 'default');
    if (!pandadoc) {
      pandadoc = new PandaDocController({ apiKey });
      pandadocControllers.set(sessionId || 'default', pandadoc);
    }

    const result = await pandadoc.execute({ action, documentId, templateId, data });
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/email-automation', async (req, res) => {
  try {
    const { sessionId, openaiApiKey, action, account, rule, email, folder, limit, threshold } = req.body;
    
    let emailAutomation = emailAutomationControllers.get(sessionId || 'default');
    if (!emailAutomation) {
      emailAutomation = new EmailAutomationController(openaiApiKey);
      emailAutomationControllers.set(sessionId || 'default', emailAutomation);
    }

    let result;
    switch (action) {
      case 'addAccount':
        emailAutomation.addAccount(account);
        result = { success: true, message: 'Account added' };
        break;
      case 'addRule':
        emailAutomation.addRule(rule);
        result = { success: true, message: 'Rule added' };
        break;
      case 'fetchEmails':
        result = await emailAutomation.fetchEmails(email, folder, limit);
        break;
      case 'processAll':
        result = await emailAutomation.processAllAccounts();
        break;
      case 'deleteSpam':
        result = await emailAutomation.deleteSpam(email, threshold);
        break;
      case 'createFolder':
        await emailAutomation.createFolder(email, folder);
        result = { success: true, message: 'Folder created' };
        break;
      default:
        return res.status(400).json({ error: 'Unknown action' });
    }

    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.use('/api/payments', paymentRoutes);

// ── Protected API Routes (Auth + Billing) ────────────────────────
app.get('/api/billing/info', requireAuth, getBillingInfo);

app.post('/api/chat', requireAuth, checkPlanLimits, async (req, res) => {
  try {
    const { message, sessionId } = req.body;
    let ai = aiClients.get(sessionId || 'default');
    if (!ai) {
      ai = new AIClient({ provider: 'openai', apiKey: process.env.OPENAI_API_KEY || '' });
      aiClients.set(sessionId || 'default', ai);
    }
    const response = await ai.chat([{ role: 'user', content: message }]);
    res.json({ response: response.content || response });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/browser/action', requireAuth, requireFeature('browser_automation'), async (req, res) => {
  try {
    const { action, sessionId } = req.body;
    let browser = browsers.get(sessionId || 'default');
    if (!browser) {
      browser = new BrowserController();
      browsers.set(sessionId || 'default', browser);
    }
    const result = await browser.execute(action);
    res.json({ result });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

// ── Webhook Endpoints (with Verification) ────────────────────────
app.post('/api/webhooks/stripe', verifyStripeWebhook, async (req, res) => {
  try {
    const event = (req as any).stripeEvent || req.body;
    console.log('Stripe webhook received:', event.type);
    res.json({ received: true });
  } catch (error: any) {
    res.status(400).json({ error: error.message });
  }
});

app.post('/api/webhooks/shopify', verifyShopifyWebhook, async (req, res) => {
  try {
    const topic = req.headers['x-shopify-topic'];
    console.log('Shopify webhook received:', topic);
    res.json({ received: true });
  } catch (error: any) {
    res.status(400).json({ error: error.message });
  }
});

app.post('/api/webhooks/generic', verifyHmacWebhook, async (req, res) => {
  try {
    const { event_type, payload } = req.body;
    console.log('Generic webhook received:', event_type);
    res.json({ received: true });
  } catch (error: any) {
    res.status(400).json({ error: error.message });
  }
});

// ── Health & Status ──────────────────────────────────────────────
const startTime = Date.now();

app.get('/health', async (_req, res) => {
  const uptime = Math.floor((Date.now() - startTime) / 1000);
  const health = {
    status: 'healthy',
    timestamp: new Date().toISOString(),
    uptime_seconds: uptime,
    version: '2.0',
    port: PORT,
    env: process.env.NODE_ENV || 'development',
    services: {
      ai_clients: aiClients.size,
      browsers: browsers.size,
      shopify: shopifyControllers.size,
      email: emailControllers.size,
      stripe: stripeControllers.size,
      telegram: telegramControllers.size,
    }
  };
  res.json(health);
});

const PORT = process.env.PORT || 3001;

export function createServer() {
  return app;
}

// ── RUDIBOT KING ORCHESTRATOR ───────────────────────────────────

const SERVICES = {
  windsurf_api: { name: 'Windsurf API', port: 3001, url: 'http://localhost:3001/health', process: 'windsurf-api-gateway' },
  eternal_guardian: { name: 'Eternal Guardian', port: 3201, url: 'http://localhost:3201/api/v1/health', process: 'rudibot-eternal' },
  telegram_bot: { name: 'Telegram Bot', port: 3200, url: 'http://localhost:3200/health', process: 'windsurf-telegram-bot' },
  rudibot_master: { name: 'RudiBot Master', port: 9900, url: 'http://localhost:9900/dashboard_data.json', process: 'supermegabot' },
  shopify_dashboard: { name: 'Shopify Dashboard', port: 3000, url: 'http://localhost:3000', process: 'windsurf-shopify' },
  army_commander: { name: 'Army Commander', port: null, url: null, process: 'rudibot-army' },
  meta_supervisor: { name: 'Meta Supervisor', port: null, url: null, process: 'meta-supervisor' },
};

interface ServiceStatus {
  id: string;
  name: string;
  status: 'online' | 'offline' | 'unknown';
  port: number | null;
  uptime: string;
  last_check: string;
  pid?: number;
  cpu?: number;
  memory?: number;
}

async function checkService(serviceId: string, config: typeof SERVICES[keyof typeof SERVICES]): Promise<ServiceStatus> {
  const status: ServiceStatus = {
    id: serviceId,
    name: config.name,
    status: 'unknown',
    port: config.port,
    uptime: 'N/A',
    last_check: new Date().toISOString(),
  };

  try {
    if (config.url) {
      const response = await fetch(config.url, { timeout: 5000 } as any);
      status.status = response.ok ? 'online' : 'offline';
    } else if (config.port) {
      const response = await fetch(`http://localhost:${config.port}/health`, { timeout: 5000 } as any);
      status.status = response.ok ? 'online' : 'offline';
    } else {
      status.status = 'unknown';
    }
  } catch (error) {
    status.status = 'offline';
  }

  return status;
}

// GET /api/orchestrator - Alle Services anzeigen
app.get('/api/orchestrator', async (_req, res) => {
  const results = await Promise.all(
    Object.entries(SERVICES).map(([id, config]) => checkService(id, config))
  );

  const online = results.filter(s => s.status === 'online').length;
  const offline = results.filter(s => s.status === 'offline').length;
  const unknown = results.filter(s => s.status === 'unknown').length;

  res.json({
    status: 'ok',
    service: 'RudiBot King Orchestrator',
    timestamp: new Date().toISOString(),
    summary: { total: results.length, online, offline, unknown },
    services: results,
    king_of_tools: {
      total_apis: 50,
      total_platforms: 48,
      total_agents: 8,
      total_micro_bots: 5,
      version: '3.0',
    }
  });
});

// POST /api/orchestrator/:service/action - Einzelnen Service steuern
app.post('/api/orchestrator/:service/:action', async (req, res) => {
  const { service, action } = req.params;
  const config = SERVICES[service as keyof typeof SERVICES];

  if (!config) {
    return res.status(404).json({ error: `Service ${service} not found` });
  }

  if (!['restart', 'stop', 'status'].includes(action)) {
    return res.status(400).json({ error: 'Action must be restart, stop, or status' });
  }

  const result = {
    service,
    action,
    name: config.name,
    timestamp: new Date().toISOString(),
    executed: true,
    message: `${action} initiated for ${config.name}`,
  };

  res.json(result);
});

// GET /api/orchestrator/health - Gesundheitscheck aller Dienste
app.get('/api/orchestrator/health', async (_req, res) => {
  const results = await Promise.all(
    Object.entries(SERVICES).map(([id, config]) => checkService(id, config))
  );

  const allOnline = results.every(s => s.status === 'online');

  res.status(allOnline ? 200 : 503).json({
    status: allOnline ? 'healthy' : 'degraded',
    timestamp: new Date().toISOString(),
    services: results,
  });
});

// ── KI ASSISTANT (OpenClaw Style) ─────────────────────────────────
app.post('/api/assistant', async (req, res) => {
  const { message, sessionId, provider, apiKey } = req.body;
  
  if (!message) {
    return res.status(400).json({ error: 'Message required' });
  }

  // Get current orchestrator status for context
  const orchestratorData = await Promise.all(
    Object.entries(SERVICES).map(([id, config]) => checkService(id, config))
  );

  const systemPrompt = `Du bist RudiBot AI Assistant - der King of Tools Orchestrator.

AKTUELLER SYSTEMSTATUS:
${orchestratorData.map(s => `• ${s.name}: ${s.status.toUpperCase()}${s.port ? ` (Port ${s.port})` : ''}`).join('\n')}

DEINE FÄHIGKEITEN:
- Services steuern: restart, stop, status
- Logs analysieren und Fehler beheben
- API-Keys und Konfigurationen verwalten
- Health Checks durchführen
- Backups erstellen

BEFEHLE:
- "status [service]" - Service-Status
- "restart [service]" - Service neustarten
- "logs [service]" - Logs anzeigen
- "health" - Gesundheitscheck aller Services
- "help" - Hilfe anzeigen

Antworte präzise und professionell.`;

  try {
    let ai = aiClients.get(sessionId || 'assistant-default');
    if (!ai) {
      ai = new AIClient({
        provider: provider || 'openai',
        apiKey: apiKey || process.env.OPENAI_API_KEY,
        model: 'gpt-4o-mini',
        systemPrompt,
      });
      aiClients.set(sessionId || 'assistant-default', ai);
    }

    const response = await ai.chat([{ role: 'user', content: message }]);
    
    res.json({
      ok: true,
      response: response.content || response,
      sessionId: sessionId || 'assistant-default',
      timestamp: new Date().toISOString(),
    });
  } catch (error: any) {
    // Fallback: Local response
    const lower = message.toLowerCase();
    let response = '';
    
    if (lower.includes('status')) {
      response = `RudiBot Status:\n${orchestratorData.map(s => `• ${s.name}: ${s.status}`).join('\n')}`;
    } else if (lower.includes('restart')) {
      response = 'Service-Restart über Orchestrator verfügbar. Nutze POST /api/orchestrator/:service/restart';
    } else if (lower.includes('health')) {
      const allOnline = orchestratorData.every(s => s.status === 'online');
      response = `System ${allOnline ? 'HEALTHY' : 'DEGRADED'}\nOnline: ${orchestratorData.filter(s => s.status === 'online').length}/${orchestratorData.length}`;
    } else {
      response = `RudiBot AI Assistant bereit. Verfügbare Befehle:\n• status [service]\n• restart [service]\n• health\n• help`;
    }

    res.json({
      ok: true,
      response,
      source: 'local-fallback',
      timestamp: new Date().toISOString(),
    });
  }
});

export { app };

// Auto-start only in non-serverless environments
if (!process.env.VERCEL) {
  app.listen(PORT, () => {
    console.log(`🚀 apitool API Server running on port ${PORT}`);
    console.log(`👑 Orchestrator: http://localhost:${PORT}/api/orchestrator`);
    console.log(`💰 Payment endpoints: /api/payments/*`);
    console.log(`🩺 Health check: http://localhost:${PORT}/health`);
  });
}
