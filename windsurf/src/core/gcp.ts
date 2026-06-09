import { GCPConfig, NLAction, TranslationAction, VisionAction, SpeechAction, StorageAction, FirestoreAction } from './types.js';
import { TranslationServiceClient } from '@google-cloud/translate/build/src/v3';
import { ImageAnnotatorClient } from '@google-cloud/vision';
import { SpeechClient } from '@google-cloud/speech';
import { TextToSpeechClient } from '@google-cloud/text-to-speech';
import { Storage } from '@google-cloud/storage';
import { Firestore } from '@google-cloud/firestore';
import { SecretManagerServiceClient } from '@google-cloud/secret-manager';
import { BigQuery } from '@google-cloud/bigquery';
import { Logging } from '@google-cloud/logging';
import { LanguageServiceClient } from '@google-cloud/language';

export class GCPController {
  private config: GCPConfig;
  private translationClient?: TranslationServiceClient;
  private visionClient?: ImageAnnotatorClient;
  private speechClient?: SpeechClient;
  private ttsClient?: TextToSpeechClient;
  private storage?: Storage;
  private firestore?: Firestore;
  private secretManager?: SecretManagerServiceClient;
  private bigquery?: BigQuery;
  private logging?: Logging;
  private languageClient?: LanguageServiceClient;
  // private monitoring?: any; // Monitoring API requires different setup

  constructor(config: GCPConfig) {
    this.config = config;
  }

  private initClients() {
    const clientConfig = {
      projectId: this.config.projectId,
      keyFilename: this.config.keyFilename,
      credentials: this.config.credentials,
    };

    if (!this.translationClient) {
      this.translationClient = new TranslationServiceClient(clientConfig);
    }
    if (!this.visionClient) {
      this.visionClient = new ImageAnnotatorClient(clientConfig);
    }
    if (!this.speechClient) {
      this.speechClient = new SpeechClient(clientConfig);
    }
    if (!this.ttsClient) {
      this.ttsClient = new TextToSpeechClient(clientConfig);
    }
    if (!this.storage) {
      this.storage = new Storage(clientConfig);
    }
    if (!this.firestore) {
      this.firestore = new Firestore(clientConfig);
    }
    if (!this.secretManager) {
      this.secretManager = new SecretManagerServiceClient(clientConfig);
    }
    if (!this.bigquery) {
      this.bigquery = new BigQuery(clientConfig);
    }
    if (!this.logging) {
      this.logging = new Logging(clientConfig);
    }
    if (!this.languageClient) {
      this.languageClient = new LanguageServiceClient(clientConfig);
    }
    // Monitoring API requires different setup - skipped for now
  }

  async executeNL(action: NLAction): Promise<any> {
    this.initClients();
    
    if (!this.languageClient) {
      throw new Error('Language client not initialized');
    }

    try {
      const document = {
        content: action.text,
        type: 'PLAIN_TEXT' as const,
      };

      switch (action.action) {
        case 'analyzeSentiment':
          const [sentimentResult] = await this.languageClient.analyzeSentiment({ document });
          return {
            sentiment: sentimentResult.documentSentiment,
            sentences: sentimentResult.sentences,
          };

        case 'extractEntities':
          const [entitiesResult] = await this.languageClient.analyzeEntities({ document });
          return {
            entities: entitiesResult.entities,
          };

        case 'classifyText':
          const [classifyResult] = await this.languageClient.classifyText({ document });
          return {
            categories: classifyResult.categories,
          };

        default:
          throw new Error(`Unknown NL action: ${action.action}`);
      }
    } catch (error: any) {
      throw new Error(`Natural Language API failed: ${error.message}`);
    }
  }

  async executeTranslation(action: TranslationAction): Promise<any> {
    this.initClients();
    
    if (!this.translationClient) {
      throw new Error('Translation client not initialized');
    }

    try {
      const request = {
        parent: `projects/${this.config.projectId}/locations/global`,
        contents: [action.text],
        targetLanguageCode: action.targetLanguage,
      };

      const [response] = await this.translationClient.translateText(request);
      
      return {
        originalText: action.text,
        translatedText: response.translations?.[0]?.translatedText,
        targetLanguage: action.targetLanguage,
      };
    } catch (error: any) {
      throw new Error(`Translation failed: ${error.message}`);
    }
  }

  async executeVision(action: VisionAction): Promise<any> {
    this.initClients();
    
    if (!this.visionClient) {
      throw new Error('Vision client not initialized');
    }

    try {
      const imageBuffer = Buffer.from(action.image, 'base64');
      
      let result: any;
      
      switch (action.action) {
        case 'detectLabels':
          [result] = await this.visionClient.labelDetection({ image: { content: imageBuffer } });
          return { labels: result.labelAnnotations };
        
        case 'detectText':
          [result] = await this.visionClient.textDetection({ image: { content: imageBuffer } });
          return { text: result.fullTextAnnotation?.text, annotations: result.textAnnotations };
        
        case 'detectFaces':
          [result] = await this.visionClient.faceDetection({ image: { content: imageBuffer } });
          return { faces: result.faceAnnotations };
        
        case 'analyzeImage':
          [result] = await this.visionClient.labelDetection({ image: { content: imageBuffer } });
          return { labels: result.labelAnnotations };
        
        default:
          throw new Error(`Unknown vision action: ${action.action}`);
      }
    } catch (error: any) {
      throw new Error(`Vision API failed: ${error.message}`);
    }
  }

  async executeSpeech(action: SpeechAction): Promise<any> {
    this.initClients();
    
    try {
      if (action.action === 'transcribe' && this.speechClient) {
        const audioBuffer = Buffer.from(action.audio!, 'base64');
        
        const request = {
          audio: { content: audioBuffer },
          config: {
            encoding: 'LINEAR16' as const,
            sampleRateHertz: 16000,
            languageCode: action.language || 'en-US',
          },
        };

        const [response] = await this.speechClient.recognize(request);
        
        return {
          transcript: response.results?.[0]?.alternatives?.[0]?.transcript,
          confidence: response.results?.[0]?.alternatives?.[0]?.confidence,
        };
      }
      
      if (action.action === 'synthesize' && this.ttsClient) {
        const request = {
          input: { text: action.text },
          voice: {
            languageCode: action.language || 'en-US',
            ssmlGender: 'NEUTRAL' as const,
          },
          audioConfig: { audioEncoding: 'MP3' as const },
        };

        const [response] = await this.ttsClient.synthesizeSpeech(request);
        
        return {
          audioContent: response.audioContent ? Buffer.from(response.audioContent).toString('base64') : undefined,
          language: action.language,
        };
      }
      
      throw new Error('Speech client not initialized or invalid action');
    } catch (error: any) {
      throw new Error(`Speech API failed: ${error.message}`);
    }
  }

  async executeStorage(action: StorageAction): Promise<any> {
    this.initClients();
    
    if (!this.storage) {
      throw new Error('Storage client not initialized');
    }

    try {
      const bucket = this.storage.bucket(action.bucket || `${this.config.projectId}.appspot.com`);
      
      switch (action.action) {
        case 'upload':
          const file = bucket.file(action.file!);
          await file.save(Buffer.from(action.data!));
          return { message: `Uploaded ${action.file} to ${action.bucket}` };
        
        case 'download':
          const downloadFile = bucket.file(action.file!);
          const [contents] = await downloadFile.download();
          return { data: contents.toString('base64'), file: action.file };
        
        case 'delete':
          await bucket.file(action.file!).delete();
          return { message: `Deleted ${action.file}` };
        
        case 'list':
          const [files] = await bucket.getFiles();
          return { files: files.map(f => f.name) };
        
        default:
          throw new Error(`Unknown storage action: ${action.action}`);
      }
    } catch (error: any) {
      throw new Error(`Storage API failed: ${error.message}`);
    }
  }

  async executeFirestore(action: FirestoreAction): Promise<any> {
    this.initClients();
    
    if (!this.firestore) {
      throw new Error('Firestore client not initialized');
    }

    try {
      const collection = this.firestore.collection(action.collection);
      
      switch (action.action) {
        case 'add':
          const docRef = await collection.add(action.data);
          return { id: docRef.id, message: 'Document added' };
        
        case 'get':
          const doc = await collection.doc(action.document!).get();
          return { exists: doc.exists, data: doc.data() };
        
        case 'update':
          await collection.doc(action.document!).update(action.data);
          return { message: 'Document updated' };
        
        case 'delete':
          await collection.doc(action.document!).delete();
          return { message: 'Document deleted' };
        
        case 'query':
          const snapshot = await collection.get();
          return { documents: snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() })) };
        
        default:
          throw new Error(`Unknown firestore action: ${action.action}`);
      }
    } catch (error: any) {
      throw new Error(`Firestore API failed: ${error.message}`);
    }
  }

  async getSecret(secretName: string): Promise<string> {
    this.initClients();
    
    if (!this.secretManager) {
      throw new Error('Secret Manager client not initialized');
    }

    try {
      const name = `projects/${this.config.projectId}/secrets/${secretName}/versions/latest`;
      const [version] = await this.secretManager.accessSecretVersion({ name });
      
      return version.payload?.data?.toString() || '';
    } catch (error: any) {
      throw new Error(`Secret Manager failed: ${error.message}`);
    }
  }

  async executeBigQuery(query: string): Promise<any> {
    this.initClients();
    
    if (!this.bigquery) {
      throw new Error('BigQuery client not initialized');
    }

    try {
      const [rows] = await this.bigquery.query({ query });
      return { rows };
    } catch (error: any) {
      throw new Error(`BigQuery failed: ${error.message}`);
    }
  }

  async logEntry(message: string, severity: string = 'INFO'): Promise<void> {
    this.initClients();
    
    if (!this.logging) {
      throw new Error('Logging client not initialized');
    }

    try {
      const log = this.logging.log('apitool');
      const entry = log.entry({ severity }, message);
      await log.write(entry);
    } catch (error: any) {
      console.error(`Logging failed: ${error.message}`);
    }
  }
}
