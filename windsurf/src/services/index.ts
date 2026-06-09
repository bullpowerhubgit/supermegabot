// ============================================
// RUDIBOT KING OF TOOLS - Unified Services
// Alle Tools unter einem Export
// ============================================

export { AIClient } from '../core/ai.js';
export { BrowserController } from '../core/browser.js';
export { MacController } from '../core/mac.js';
export { GCPController } from '../core/gcp.js';
export { ShopifyController } from '../core/shopify.js';
export { EmailController } from '../core/email.js';
export { SMSController } from '../core/sms.js';
export { StripeController } from '../core/stripe.js';
export { QueueController } from '../core/queue.js';
export { AuthController } from '../core/auth.js';
export { DataController } from '../core/data.js';
export { GitHubController } from '../core/github.js';
export { SlackController } from '../core/slack.js';
export { DiscordController } from '../core/discord.js';
export { TelegramController } from '../core/telegram.js';
export { NotionController } from '../core/notion.js';
export { AirtableController } from '../core/airtable.js';
export { AWSController } from '../core/aws.js';
export { AzureController } from '../core/azure.js';
export { GoogleController } from '../core/google.js';
export { HerokuController } from '../core/heroku.js';
export { CloudflareController } from '../core/cloudflare.js';
export { MailchimpController } from '../core/mailchimp.js';
export { HubSpotController } from '../core/hubspot.js';
export { SalesforceController } from '../core/salesforce.js';
export { ZendeskController } from '../core/zendesk.js';
export { PayPalController } from '../core/paypal.js';
export { JiraController } from '../core/jira.js';
export { TrelloController } from '../core/trello.js';
export { AsanaController } from '../core/asana.js';
export { TwitterController } from '../core/twitter.js';
export { FacebookController } from '../core/facebook.js';
export { SendinblueController } from '../core/sendinblue.js';
export { MailgunController } from '../core/mailgun.js';
export { PipedriveController } from '../core/pipedrive.js';
export { IntercomController } from '../core/intercom.js';
export { DocuSignController } from '../core/docusign.js';
export { MicrosoftGraphController } from '../core/microsoft.js';
export { MondayController } from '../core/monday.js';
export { LinearController } from '../core/linear.js';
export { LinkedInController } from '../core/linkedin.js';
export { InstagramController } from '../core/instagram.js';
export { YouTubeController } from '../core/youtube.js';
export { KlaviyoController } from '../core/klaviyo.js';
export { ActiveCampaignController } from '../core/activecampaign.js';
export { ConvertKitController } from '../core/convertkit.js';
export { CopperController } from '../core/copper.js';
export { ZohoController } from '../core/zoho.js';
export { FreshdeskController } from '../core/freshdesk.js';
export { HelpScoutController } from '../core/helpscout.js';
export { PandaDocController } from '../core/pandadoc.js';
export { EmailAutomationController } from '../core/email-automation.js';

// Middleware exports
export { requireAuth, requireRole, requireAuthOrApiKey, createSupabaseClient } from '../middleware/auth.js';
export { checkPlanLimits, requireFeature, getBillingInfo } from '../middleware/billing.js';
export { verifyHmacWebhook, verifyStripeWebhook, verifyShopifyWebhook } from '../middleware/webhook.js';

// King of Tools metadata
export const RUDIBOT_SERVICES = {
  version: '3.0',
  total_apis: 50,
  total_platforms: 48,
  total_agents: 8,
  total_micro_bots: 5,
  categories: [
    'AI / LLM',
    'E-Commerce',
    'Email / SMS',
    'Payment',
    'CRM',
    'Project Management',
    'Social Media',
    'Cloud Storage',
    'Communication',
    'E-Signature',
    'Infrastructure',
    'Monitoring',
  ]
};
