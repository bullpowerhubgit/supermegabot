import OpenAI from 'openai';
import Anthropic from '@anthropic-ai/sdk';
import { VertexAI } from '@google-cloud/vertexai';
import { Message, AgentConfig, AgentResponse, ToolCall, ToolResult } from './types.js';

export class AIClient {
  private openai?: OpenAI;
  private anthropic?: Anthropic;
  private vertexai?: VertexAI;
  private config: AgentConfig;

  constructor(config: AgentConfig) {
    this.config = config;
    if (config.provider === 'openai') {
      this.openai = new OpenAI({ apiKey: config.apiKey });
    } else if (config.provider === 'anthropic') {
      this.anthropic = new Anthropic({ apiKey: config.apiKey });
    } else if (config.provider === 'vertexai') {
      this.vertexai = new VertexAI({
        project: config.projectId || '',
        location: config.location || 'us-central1',
        googleAuthOptions: { credentials: JSON.parse(config.apiKey) },
      });
    }
  }

  async chat(messages: Message[], tools?: any[]): Promise<AgentResponse> {
    const model = this.config.model ?? (this.config.provider === 'openai' ? 'gpt-4o' : this.config.provider === 'anthropic' ? 'claude-3-opus-20240229' : 'gemini-1.5-pro');

    if (this.config.provider === 'openai' && this.openai) {
      const response = await this.openai.chat.completions.create({
        model,
        messages: messages as any,
        tools: tools?.length ? tools : undefined,
      });

      const choice = response.choices[0];
      const toolCalls = choice.message?.tool_calls?.map((tc: any) => ({
        id: tc.id,
        type: 'function' as const,
        function: {
          name: tc.function.name,
          arguments: tc.function.arguments,
        },
      }));

      return {
        content: choice.message?.content ?? '',
        toolCalls,
      };
    }

    if (this.config.provider === 'anthropic' && this.anthropic) {
      const systemMsg = messages.find(m => m.role === 'system')?.content ?? '';
      const conversation = messages.filter(m => m.role !== 'system');

      const response = await this.anthropic.messages.create({
        model,
        max_tokens: 4096,
        system: systemMsg || undefined,
        messages: conversation as any,
        tools: tools?.length ? tools as any : undefined,
      });

      const content = response.content
        .filter((c: any) => c.type === 'text')
        .map((c: any) => c.text)
        .join('');

      const toolCalls = response.content
        .filter((c: any) => c.type === 'tool_use')
        .map((c: any) => ({
          id: c.id,
          type: 'function' as const,
          function: {
            name: c.name,
            arguments: JSON.stringify(c.input),
          },
        }));

      return { content, toolCalls };
    }

    if (this.config.provider === 'vertexai' && this.vertexai) {
      const generativeModel = this.vertexai.getGenerativeModel({
        model: model,
        systemInstruction: messages.find(m => m.role === 'system')?.content,
      });

      const chatHistory = messages
        .filter(m => m.role !== 'system')
        .map(m => ({
          role: m.role === 'assistant' ? 'model' : 'user',
          parts: [{ text: m.content }],
        }));

      const chat = generativeModel.startChat({ history: chatHistory });
      const result = await chat.sendMessage(messages[messages.length - 1].content);
      const response = result.response;

      const content = response.candidates?.[0]?.content?.parts?.[0]?.text || '';

      return { content };
    }

    throw new Error('No AI provider initialized');
  }

  createToolDefinitions(): any[] {
    return [
      {
        type: 'function',
        function: {
          name: 'browser_control',
          description: 'Steuere einen Browser: navigiere zu URLs, klicke Elemente, tippe Text, mache Screenshots, scrolle, extrahiere Text.',
          parameters: {
            type: 'object',
            properties: {
              action: {
                type: 'string',
                enum: ['navigate', 'click', 'type', 'screenshot', 'scroll', 'extract', 'close'],
                description: 'Die auszuführende Browser-Aktion',
              },
              url: { type: 'string', description: 'URL für navigate' },
              selector: { type: 'string', description: 'CSS-Selektor für click/type/extract' },
              text: { type: 'string', description: 'Text für type' },
              direction: { type: 'string', enum: ['up', 'down'], description: 'Richtung für scroll' },
            },
            required: ['action'],
          },
        },
      },
      {
        type: 'function',
        function: {
          name: 'mac_control',
          description: 'Steuere macOS: Maus bewegen, klicken, Text tippen, Tastenkombinationen, Apps öffnen, Clipboard, sowie System-Ressourcen abfragen (CPU, Memory, Disk, System-Info).',
          parameters: {
            type: 'object',
            properties: {
              action: {
                type: 'string',
                enum: ['click', 'type', 'keyCombo', 'moveMouse', 'openApp', 'screenshot', 'getClipboard', 'setClipboard', 'getSystemInfo', 'getCPUUsage', 'getMemoryUsage', 'getDiskUsage'],
                description: 'Die auszuführende Mac-Aktion',
              },
              x: { type: 'number', description: 'X-Koordinate für moveMouse' },
              y: { type: 'number', description: 'Y-Koordinate für moveMouse' },
              text: { type: 'string', description: 'Text für type/setClipboard' },
              app: { type: 'string', description: 'App-Name für openApp' },
              keys: { type: 'array', items: { type: 'string' }, description: 'Tasten für keyCombo (z.B. ["cmd", "c"])' },
            },
            required: ['action'],
          },
        },
      },
      {
        type: 'function',
        function: {
          name: 'gcp_translation',
          description: 'Übersetze Text in verschiedene Sprachen mit Google Cloud Translation API.',
          parameters: {
            type: 'object',
            properties: {
              text: { type: 'string', description: 'Zu übersetzender Text' },
              targetLanguage: { type: 'string', description: 'Zielsprache (z.B. "de", "en", "fr", "es")' },
            },
            required: ['text', 'targetLanguage'],
          },
        },
      },
      {
        type: 'function',
        function: {
          name: 'gcp_vision',
          description: 'Analysiere Bilder mit Google Cloud Vision API: Labels, Text, Faces erkennen.',
          parameters: {
            type: 'object',
            properties: {
              action: {
                type: 'string',
                enum: ['detectLabels', 'detectText', 'detectFaces', 'analyzeImage'],
                description: 'Art der Bildanalyse',
              },
              image: { type: 'string', description: 'Bild als base64 oder URL' },
            },
            required: ['action', 'image'],
          },
        },
      },
      {
        type: 'function',
        function: {
          name: 'gcp_speech',
          description: 'Transkribiere Audio oder generiere Sprache mit Google Cloud Speech/TTS API.',
          parameters: {
            type: 'object',
            properties: {
              action: {
                type: 'string',
                enum: ['transcribe', 'synthesize'],
                description: 'Audio transkribieren oder Text in Sprache umwandeln',
              },
              audio: { type: 'string', description: 'Audio als base64 (für transcribe)' },
              text: { type: 'string', description: 'Zu sprechender Text (für synthesize)' },
              language: { type: 'string', description: 'Sprachcode (z.B. "de-DE", "en-US")' },
            },
            required: ['action'],
          },
        },
      },
      {
        type: 'function',
        function: {
          name: 'gcp_storage',
          description: 'Verwalte Dateien in Google Cloud Storage: upload, download, delete, list.',
          parameters: {
            type: 'object',
            properties: {
              action: {
                type: 'string',
                enum: ['upload', 'download', 'delete', 'list'],
                description: 'Storage-Aktion',
              },
              bucket: { type: 'string', description: 'Bucket-Name' },
              file: { type: 'string', description: 'Dateiname' },
              data: { type: 'string', description: 'Daten als base64 (für upload)' },
            },
            required: ['action'],
          },
        },
      },
      {
        type: 'function',
        function: {
          name: 'gcp_firestore',
          description: 'Verwalte Daten in Google Cloud Firestore: add, get, update, delete, query.',
          parameters: {
            type: 'object',
            properties: {
              action: {
                type: 'string',
                enum: ['add', 'get', 'update', 'delete', 'query'],
                description: 'Firestore-Aktion',
              },
              collection: { type: 'string', description: 'Collection-Name' },
              document: { type: 'string', description: 'Document-ID (für get, update, delete)' },
              data: { type: 'object', description: 'Daten (für add, update)' },
            },
            required: ['action', 'collection'],
          },
        },
      },
      {
        type: 'function',
        function: {
          name: 'shopify_products',
          description: 'Verwalte Shopify-Produkte: getProducts, getProduct, createProduct, updateProduct, deleteProduct.',
          parameters: {
            type: 'object',
            properties: {
              action: {
                type: 'string',
                enum: ['getProducts', 'getProduct', 'createProduct', 'updateProduct', 'deleteProduct'],
                description: 'Shopify Produkt-Aktion',
              },
              id: { type: 'string', description: 'Produkt-ID (für getProduct, updateProduct, deleteProduct)' },
              data: { type: 'object', description: 'Produktdaten (für createProduct, updateProduct)' },
              query: { type: 'object', description: 'Query-Parameter (für getProducts)' },
            },
            required: ['action'],
          },
        },
      },
      {
        type: 'function',
        function: {
          name: 'shopify_orders',
          description: 'Verwalte Shopify-Bestellungen: getOrders, getOrder, createOrder, updateOrder.',
          parameters: {
            type: 'object',
            properties: {
              action: {
                type: 'string',
                enum: ['getOrders', 'getOrder', 'createOrder', 'updateOrder'],
                description: 'Shopify Bestell-Aktion',
              },
              id: { type: 'string', description: 'Bestell-ID (für getOrder, updateOrder)' },
              data: { type: 'object', description: 'Bestelldaten (für createOrder, updateOrder)' },
              query: { type: 'object', description: 'Query-Parameter (für getOrders)' },
            },
            required: ['action'],
          },
        },
      },
      {
        type: 'function',
        function: {
          name: 'shopify_customers',
          description: 'Verwalte Shopify-Kunden: getCustomers, getCustomer, createCustomer, updateCustomer.',
          parameters: {
            type: 'object',
            properties: {
              action: {
                type: 'string',
                enum: ['getCustomers', 'getCustomer', 'createCustomer', 'updateCustomer'],
                description: 'Shopify Kunden-Aktion',
              },
              id: { type: 'string', description: 'Kunden-ID (für getCustomer, updateCustomer)' },
              data: { type: 'object', description: 'Kundendaten (für createCustomer, updateCustomer)' },
              query: { type: 'object', description: 'Query-Parameter (für getCustomers)' },
            },
            required: ['action'],
          },
        },
      },
      {
        type: 'function',
        function: {
          name: 'send_email',
          description: 'Sende E-Mails über SendGrid oder Nodemailer.',
          parameters: {
            type: 'object',
            properties: {
              to: { type: 'string', description: 'Empfänger-E-Mail' },
              subject: { type: 'string', description: 'Betreff' },
              text: { type: 'string', description: 'Text-Inhalt' },
              html: { type: 'string', description: 'HTML-Inhalt' },
              from: { type: 'string', description: 'Absender-E-Mail' },
            },
            required: ['to', 'subject'],
          },
        },
      },
      {
        type: 'function',
        function: {
          name: 'send_sms',
          description: 'Sende SMS über Twilio.',
          parameters: {
            type: 'object',
            properties: {
              to: { type: 'string', description: 'Empfänger-Telefonnummer' },
              body: { type: 'string', description: 'SMS-Inhalt' },
            },
            required: ['to', 'body'],
          },
        },
      },
      {
        type: 'function',
        function: {
          name: 'stripe_payment',
          description: 'Verarbeite Stripe-Zahlungen: createPaymentIntent, confirmPayment, createCustomer.',
          parameters: {
            type: 'object',
            properties: {
              action: {
                type: 'string',
                enum: ['createPaymentIntent', 'confirmPayment', 'createCustomer'],
                description: 'Stripe Zahlungs-Aktion',
              },
              data: { type: 'object', description: 'Zahlungsdaten' },
            },
            required: ['action', 'data'],
          },
        },
      },
      {
        type: 'function',
        function: {
          name: 'queue_job',
          description: 'Verwalte Queue-Jobs mit Bull/Redis: addJob, getJob, getQueueStats.',
          parameters: {
            type: 'object',
            properties: {
              action: {
                type: 'string',
                enum: ['addJob', 'getJob', 'getQueueStats'],
                description: 'Queue-Aktion',
              },
              queueName: { type: 'string', description: 'Queue-Name' },
              jobName: { type: 'string', description: 'Job-Name' },
              data: { type: 'object', description: 'Job-Daten' },
              jobId: { type: 'string', description: 'Job-ID (für getJob)' },
            },
            required: ['action', 'queueName'],
          },
        },
      },
      {
        type: 'function',
        function: {
          name: 'auth_token',
          description: 'Generiere oder verifiziere JWT-Tokens: generateToken, verifyToken.',
          parameters: {
            type: 'object',
            properties: {
              action: {
                type: 'string',
                enum: ['generateToken', 'verifyToken'],
                description: 'Auth-Aktion',
              },
              payload: { type: 'object', description: 'Token-Payload (für generateToken)' },
              token: { type: 'string', description: 'JWT-Token (für verifyToken)' },
            },
            required: ['action'],
          },
        },
      },
      {
        type: 'function',
        function: {
          name: 'data_import',
          description: 'Importiere/Exportiere CSV oder Excel Dateien.',
          parameters: {
            type: 'object',
            properties: {
              action: {
                type: 'string',
                enum: ['importCSV', 'importExcel', 'exportCSV', 'exportExcel'],
                description: 'Daten-Aktion',
              },
              filePath: { type: 'string', description: 'Dateipfad' },
              data: { type: 'array', description: 'Daten (für export)' },
              headers: { type: 'array', items: { type: 'string' }, description: 'Spaltenüberschriften' },
            },
            required: ['action', 'filePath'],
          },
        },
      },
    ];
  }
}
