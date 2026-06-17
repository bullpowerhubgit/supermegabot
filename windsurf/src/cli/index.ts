#!/usr/bin/env node
import { Command } from 'commander';
import { AIClient, BrowserController, MacController } from '../core/index.js';
import { Message } from '../core/types.js';

const program = new Command();

program
  .name('apitool')
  .description('Universal KI-Assistent mit Browser- und Mac-Steuerung')
  .version('1.0.0');

program
  .command('chat')
  .description('Chat mit dem KI-Assistenten')
  .option('-p, --provider <provider>', 'AI Provider (openai|anthropic|vertexai)', 'openai')
  .option('-k, --key <key>', 'API Key (oder GCP Config JSON für vertexai)')
  .option('--project-id <projectId>', 'GCP Project ID (für vertexai)')
  .option('--location <location>', 'GCP Location (für vertexai, default: us-central1)')
  .option('-m, --model <model>', 'Model name')
  .option('--headless', 'Browser im Headless-Modus starten', true)
  .action(async (options) => {
    const apiKey = options.key || process.env.OPENAI_API_KEY || process.env.ANTHROPIC_API_KEY || process.env.GCP_CONFIG;
    if (!apiKey) {
      console.error('API Key erforderlich (via --key oder Umgebungsvariable)');
      process.exit(1);
    }

    const ai = new AIClient({
      provider: options.provider,
      apiKey,
      projectId: options.projectId,
      location: options.location,
      model: options.model,
      systemPrompt: 'Du bist ein hilfreicher KI-Assistent mit Zugriff auf Browser- und Mac-Steuerung.',
    });

    const browser = new BrowserController();
    const mac = new MacController();

    await browser.init(!options.headless);

    const tools = ai.createToolDefinitions();
    const messages: Message[] = [];

    console.log('🤖 apitool gestartet. Tippe deine Nachricht oder "exit" zum Beenden.\n');

    const readline = require('readline');
    const rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout,
    });

    const ask = (query: string): Promise<string> => {
      return new Promise((resolve) => rl.question(query, resolve));
    };

    while (true) {
      const input = await ask('> ');
      if (input === 'exit') break;

      messages.push({ role: 'user', content: input });

      const response = await ai.chat(messages, tools);
      console.log(`\n🤖 ${response.content}\n`);

      if (response.toolCalls) {
        for (const toolCall of response.toolCalls) {
          const args = JSON.parse(toolCall.function.arguments);
          let result = '';

          if (toolCall.function.name === 'browser_control') {
            result = await browser.execute(args);
          } else if (toolCall.function.name === 'mac_control') {
            result = await mac.execute(args);
          }

          console.log(`🔧 ${toolCall.function.name}: ${result}\n`);
          messages.push({
            role: 'assistant',
            content: '',
            toolCalls: [toolCall],
          } as any);
          messages.push({
            role: 'tool',
            content: result,
            tool_call_id: toolCall.id,
          } as any);
        }

        const followUp = await ai.chat(messages, tools);
        console.log(`🤖 ${followUp.content}\n`);
        messages.push({ role: 'assistant', content: followUp.content });
      } else {
        messages.push({ role: 'assistant', content: response.content });
      }
    }

    await browser.close();
    rl.close();
  });

program
  .command('browser')
  .description('Browser-Steuerung direkt')
  .option('--headless', 'Headless-Modus', true)
  .action(async (options) => {
    const browser = new BrowserController();
    await browser.init(!options.headless);
    console.log('Browser gestartet. Verwende die KI oder implementiere direkte Steuerung.');
  });

program
  .command('mac')
  .description('Mac-Steuerung direkt')
  .option('--action <action>', 'Aktion: click|type|moveMouse|openApp|screenshot|getClipboard|setClipboard|getSystemInfo|getCPUUsage|getMemoryUsage|getDiskUsage')
  .option('--x <x>', 'X-Koordinate')
  .option('--y <y>', 'Y-Koordinate')
  .option('--text <text>', 'Text für type/setClipboard')
  .option('--app <app>', 'App-Name für openApp')
  .action(async (options) => {
    const mac = new MacController();
    const action = options.action || 'getSystemInfo';
    try {
      const result = await mac.execute({
        action,
        x: options.x ? parseInt(options.x) : undefined,
        y: options.y ? parseInt(options.y) : undefined,
        text: options.text,
        app: options.app,
      } as any);
      console.log(result);
    } catch (e: any) {
      console.error('Fehler:', e.message);
      process.exit(1);
    }
  });

program
  .command('gcp:translate')
  .description('Text übersetzen mit Google Cloud Translation')
  .option('--project-id <projectId>', 'GCP Project ID')
  .option('--key-file <keyFile>', 'GCP Service Account Key File')
  .option('--text <text>', 'Zu übersetzender Text')
  .option('--target <target>', 'Zielsprache (z.B. de, en, fr, es)')
  .action(async (options) => {
    const { GCPController } = await import('../core/index.js');
    const gcp = new GCPController({
      projectId: options.projectId || process.env.GCP_PROJECT_ID || '',
      keyFilename: options.keyFile,
    });
    const result = await gcp.executeTranslation({
      action: 'translate',
      text: options.text,
      targetLanguage: options.target,
    });
    console.log(JSON.stringify(result, null, 2));
  });

program
  .command('gcp:vision')
  .description('Bildanalyse mit Google Cloud Vision')
  .option('--project-id <projectId>', 'GCP Project ID')
  .option('--key-file <keyFile>', 'GCP Service Account Key File')
  .option('--action <action>', 'Aktion (detectLabels, detectText, detectFaces, analyzeImage)')
  .option('--image <image>', 'Bild als base64 oder Dateipfad')
  .action(async (options) => {
    const { GCPController } = await import('../core/index.js');
    const gcp = new GCPController({
      projectId: options.projectId || process.env.GCP_PROJECT_ID || '',
      keyFilename: options.keyFile,
    });
    let imageData = options.image;
    if (imageData && !imageData.startsWith('data:')) {
      const fs = await import('fs');
      imageData = fs.readFileSync(imageData, 'base64');
    }
    const result = await gcp.executeVision({
      action: options.action,
      image: imageData,
    });
    console.log(JSON.stringify(result, null, 2));
  });

program
  .command('gcp:speech')
  .description('Audio transkribieren oder Text in Sprache umwandeln')
  .option('--project-id <projectId>', 'GCP Project ID')
  .option('--key-file <keyFile>', 'GCP Service Account Key File')
  .option('--action <action>', 'Aktion (transcribe, synthesize)')
  .option('--audio <audio>', 'Audio als base64 (für transcribe)')
  .option('--text <text>', 'Zu sprechender Text (für synthesize)')
  .option('--language <language>', 'Sprachcode (z.B. de-DE, en-US)')
  .action(async (options) => {
    const { GCPController } = await import('../core/index.js');
    const gcp = new GCPController({
      projectId: options.projectId || process.env.GCP_PROJECT_ID || '',
      keyFilename: options.keyFile,
    });
    const result = await gcp.executeSpeech({
      action: options.action,
      audio: options.audio,
      text: options.text,
      language: options.language,
    });
    console.log(JSON.stringify(result, null, 2));
  });

program
  .command('gcp:storage')
  .description('Google Cloud Storage verwalten')
  .option('--project-id <projectId>', 'GCP Project ID')
  .option('--key-file <keyFile>', 'GCP Service Account Key File')
  .option('--action <action>', 'Aktion (upload, download, delete, list)')
  .option('--bucket <bucket>', 'Bucket-Name')
  .option('--file <file>', 'Dateiname')
  .option('--data <data>', 'Daten als base64 (für upload)')
  .action(async (options) => {
    const { GCPController } = await import('../core/index.js');
    const gcp = new GCPController({
      projectId: options.projectId || process.env.GCP_PROJECT_ID || '',
      keyFilename: options.keyFile,
    });
    const result = await gcp.executeStorage({
      action: options.action,
      bucket: options.bucket,
      file: options.file,
      data: options.data,
    });
    console.log(JSON.stringify(result, null, 2));
  });

program
  .command('gcp:firestore')
  .description('Google Cloud Firestore verwalten')
  .option('--project-id <projectId>', 'GCP Project ID')
  .option('--key-file <keyFile>', 'GCP Service Account Key File')
  .option('--action <action>', 'Aktion (add, get, update, delete, query)')
  .option('--collection <collection>', 'Collection-Name')
  .option('--document <document>', 'Document-ID')
  .option('--data <data>', 'Daten als JSON (für add, update)')
  .action(async (options) => {
    const { GCPController } = await import('../core/index.js');
    const gcp = new GCPController({
      projectId: options.projectId || process.env.GCP_PROJECT_ID || '',
      keyFilename: options.keyFile,
    });
    const data = options.data ? JSON.parse(options.data) : undefined;
    const result = await gcp.executeFirestore({
      action: options.action,
      collection: options.collection,
      document: options.document,
      data,
    });
    console.log(JSON.stringify(result, null, 2));
  });

program
  .command('gcp:secret')
  .description('Secret aus Google Secret Manager abrufen')
  .option('--project-id <projectId>', 'GCP Project ID')
  .option('--key-file <keyFile>', 'GCP Service Account Key File')
  .option('--name <name>', 'Secret-Name')
  .action(async (options) => {
    const { GCPController } = await import('../core/index.js');
    const gcp = new GCPController({
      projectId: options.projectId || process.env.GCP_PROJECT_ID || '',
      keyFilename: options.keyFile,
    });
    const secret = await gcp.getSecret(options.name);
    console.log(`Secret: ${secret}`);
  });

program
  .command('gcp:bigquery')
  .description('SQL Query auf Google BigQuery ausführen')
  .option('--project-id <projectId>', 'GCP Project ID')
  .option('--key-file <keyFile>', 'GCP Service Account Key File')
  .option('--query <query>', 'SQL Query')
  .action(async (options) => {
    const { GCPController } = await import('../core/index.js');
    const gcp = new GCPController({
      projectId: options.projectId || process.env.GCP_PROJECT_ID || '',
      keyFilename: options.keyFile,
    });
    const result = await gcp.executeBigQuery(options.query);
    console.log(JSON.stringify(result, null, 2));
  });

program
  .command('shopify:products')
  .description('Shopify Produkte abrufen')
  .option('--shop-domain <shopDomain>', 'Shop Domain (z.B. myshop.myshopify.com)')
  .option('--access-token <accessToken>', 'Shopify Access Token')
  .option('--query <query>', 'Query Parameter als JSON')
  .action(async (options) => {
    const { ShopifyController } = await import('../core/index.js');
    const shopify = new ShopifyController({
      shopDomain: options.shopDomain || process.env.SHOPIFY_SHOP_DOMAIN || '',
      accessToken: options.accessToken || process.env.SHOPIFY_ACCESS_TOKEN || '',
    });
    const query = options.query ? JSON.parse(options.query) : undefined;
    const result = await shopify.execute({ action: 'getProducts', query });
    console.log(JSON.stringify(result, null, 2));
  });

program
  .command('shopify:orders')
  .description('Shopify Bestellungen abrufen')
  .option('--shop-domain <shopDomain>', 'Shop Domain')
  .option('--access-token <accessToken>', 'Shopify Access Token')
  .option('--query <query>', 'Query Parameter als JSON')
  .action(async (options) => {
    const { ShopifyController } = await import('../core/index.js');
    const shopify = new ShopifyController({
      shopDomain: options.shopDomain || process.env.SHOPIFY_SHOP_DOMAIN || '',
      accessToken: options.accessToken || process.env.SHOPIFY_ACCESS_TOKEN || '',
    });
    const query = options.query ? JSON.parse(options.query) : undefined;
    const result = await shopify.execute({ action: 'getOrders', query });
    console.log(JSON.stringify(result, null, 2));
  });

program
  .command('email:send')
  .description('E-Mail senden')
  .option('--provider <provider>', 'Email Provider (sendgrid|nodemailer)', 'sendgrid')
  .option('--api-key <apiKey>', 'API Key (für SendGrid)')
  .option('--to <to>', 'Empfänger-E-Mail')
  .option('--from <from>', 'Absender-E-Mail')
  .option('--subject <subject>', 'Betreff')
  .option('--text <text>', 'Text-Inhalt')
  .option('--html <html>', 'HTML-Inhalt')
  .action(async (options) => {
    const { EmailController } = await import('../core/index.js');
    const email = new EmailController({
      provider: options.provider,
      apiKey: options.apiKey || process.env.SENDGRID_API_KEY,
      from: options.from,
    });
    const result = await email.execute({
      action: 'send',
      to: options.to,
      from: options.from,
      subject: options.subject,
      text: options.text,
      html: options.html,
    });
    console.log(JSON.stringify(result, null, 2));
  });

program
  .command('sms:send')
  .description('SMS senden')
  .option('--account-sid <accountSid>', 'Twilio Account SID')
  .option('--auth-token <authToken>', 'Twilio Auth Token')
  .option('--from-number <fromNumber>', 'Absender-Nummer')
  .option('--to <to>', 'Empfänger-Nummer')
  .option('--body <body>', 'Nachricht')
  .action(async (options) => {
    const { SMSController } = await import('../core/index.js');
    const sms = new SMSController({
      accountSid: options.accountSid || process.env.TWILIO_ACCOUNT_SID || '',
      authToken: options.authToken || process.env.TWILIO_AUTH_TOKEN || '',
      fromNumber: options.fromNumber || process.env.TWILIO_FROM_NUMBER || '',
    });
    const result = await sms.execute({
      action: 'send',
      to: options.to,
      body: options.body,
    });
    console.log(JSON.stringify(result, null, 2));
  });

program
  .command('stripe:payment')
  .description('Stripe Payment Intent erstellen')
  .option('--api-key <apiKey>', 'Stripe API Key')
  .option('--amount <amount>', 'Betrag in Cents')
  .option('--currency <currency>', 'Währung (default: usd)', 'usd')
  .action(async (options) => {
    const { StripeController } = await import('../core/index.js');
    const stripe = new StripeController({
      apiKey: options.apiKey || process.env.STRIPE_API_KEY || '',
    });
    const result = await stripe.execute({
      action: 'createPaymentIntent',
      data: { amount: parseInt(options.amount), currency: options.currency },
    });
    console.log(JSON.stringify(result, null, 2));
  });

program
  .command('queue:add')
  .description('Job zu Queue hinzufügen')
  .option('--queue-name <queueName>', 'Queue Name')
  .option('--job-name <jobName>', 'Job Name')
  .option('--data <data>', 'Job Daten als JSON')
  .action(async (options) => {
    const { QueueController } = await import('../core/index.js');
    const queue = new QueueController({});
    const data = options.data ? JSON.parse(options.data) : undefined;
    const result = await queue.execute({
      action: 'addJob',
      queueName: options.queueName,
      jobName: options.jobName,
      data,
    });
    console.log(JSON.stringify(result, null, 2));
  });

program
  .command('auth:token')
  .description('JWT Token generieren')
  .option('--secret <secret>', 'JWT Secret')
  .option('--payload <payload>', 'Payload als JSON')
  .action(async (options) => {
    const { AuthController } = await import('../core/index.js');
    const auth = new AuthController({
      jwtSecret: options.secret || process.env.JWT_SECRET || 'secret',
    });
    const payload = options.payload ? JSON.parse(options.payload) : { user: 'test' };
    const result = await auth.execute({
      action: 'generateToken',
      payload,
    });
    console.log(JSON.stringify(result, null, 2));
  });

program
  .command('data:import')
  .description('CSV/Excel Datei importieren')
  .option('--file-path <filePath>', 'Dateipfad')
  .option('--format <format>', 'Format (csv|excel)', 'csv')
  .action(async (options) => {
    const { DataController } = await import('../core/index.js');
    const data = new DataController();
    const result = await data.execute({
      action: options.format === 'csv' ? 'importCSV' : 'importExcel',
      filePath: options.filePath,
    });
    console.log(JSON.stringify(result, null, 2));
  });

program.parse();
