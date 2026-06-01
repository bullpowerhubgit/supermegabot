/**
 * Google Cloud / GenAI Configuration
 * Centralized configuration for Google Cloud services and AI models
 */

import dotenv from 'dotenv';

dotenv.config();

export interface GoogleCloudConfig {
  project: {
    id: string;
    number?: string;
    location: string;
  };
  apis: {
    genai: {
      enabled: boolean;
      models: {
        gemini: {
          '1.5-flash': string;
          '1.5-pro': string;
          '1.0-pro': string;
        };
      };
      endpoints: {
        generate: string;
        stream: string;
      };
    };
    vertexAI: {
      enabled: boolean;
      region: string;
      endpoint: string;
    };
    storage: {
      enabled: boolean;
      bucket?: string;
    };
    pubsub: {
      enabled: boolean;
      topicPrefix: string;
    };
  };
  auth: {
    serviceAccount?: {
      projectId: string;
      privateKey: string;
      clientEmail: string;
    };
    apiKey?: string;
  };
}

class GoogleCloudConfigManager {
  private static instance: GoogleCloudConfigManager;
  private config: GoogleCloudConfig;

  private constructor() {
    this.config = this.loadConfiguration();
    this.validateConfiguration();
  }

  public static getInstance(): GoogleCloudConfigManager {
    if (!GoogleCloudConfigManager.instance) {
      GoogleCloudConfigManager.instance = new GoogleCloudConfigManager();
    }
    return GoogleCloudConfigManager.instance;
  }

  private loadConfiguration(): GoogleCloudConfig {
    const projectId = process.env.GOOGLE_CLOUD_PROJECT || process.env.GOOGLE_PROJECT_ID;
    const projectNumber = process.env.GOOGLE_PROJECT_NUMBER;
    const location = process.env.GOOGLE_CLOUD_LOCATION || 'us-central1';

    if (!projectId) {
      console.warn('[Google Cloud] Project ID not configured. Set GOOGLE_CLOUD_PROJECT environment variable.');
    }

    return {
      project: {
        id: projectId || '',
        number: projectNumber,
        location,
      },
      apis: {
        genai: {
          enabled: !!projectId,
          models: {
            '1.5-flash': `projects/${projectId}/locations/${location}/publishers/google/models/gemini-1.5-flash`,
            '1.5-pro': `projects/${projectId}/locations/${location}/publishers/google/models/gemini-1.5-pro`,
            '1.0-pro': `projects/${projectId}/locations/${location}/publishers/google/models/gemini-1.0-pro`,
          },
          endpoints: {
            generate: `https://${location}-aiplatform.googleapis.com/v1/projects/${projectId}/locations/${location}/publishers/google/models`,
            stream: `https://${location}-aiplatform.googleapis.com/v1/projects/${projectId}/locations/${location}/publishers/google/models`,
          },
        },
        vertexAI: {
          enabled: !!projectId,
          region: location,
          endpoint: `https://${location}-aiplatform.googleapis.com`,
        },
        storage: {
          enabled: !!process.env.GOOGLE_CLOUD_STORAGE_BUCKET,
          bucket: process.env.GOOGLE_CLOUD_STORAGE_BUCKET,
        },
        pubsub: {
          enabled: !!projectId,
          topicPrefix: 'supermegabot',
        },
      },
      auth: {
        serviceAccount: this.loadServiceAccountConfig(),
        apiKey: process.env.GOOGLE_AI_API_KEY,
      },
    };
  }

  private loadServiceAccountConfig(): GoogleCloudConfig['auth']['serviceAccount'] {
    const serviceAccountPath = process.env.GOOGLE_APPLICATION_CREDENTIALS;
    
    if (serviceAccountPath) {
      try {
        // In a real implementation, you would load the JSON file
        // For now, we'll use environment variables
        return {
          projectId: process.env.GOOGLE_CLOUD_PROJECT || '',
          privateKey: process.env.GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY || '',
          clientEmail: process.env.GOOGLE_SERVICE_ACCOUNT_CLIENT_EMAIL || '',
        };
      } catch (error) {
        console.warn('[Google Cloud] Failed to load service account config:', error);
        return undefined;
      }
    }

    // Try to build from individual environment variables
    if (process.env.GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY && process.env.GOOGLE_SERVICE_ACCOUNT_CLIENT_EMAIL) {
      return {
        projectId: process.env.GOOGLE_CLOUD_PROJECT || '',
        privateKey: process.env.GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY,
        clientEmail: process.env.GOOGLE_SERVICE_ACCOUNT_CLIENT_EMAIL,
      };
    }

    return undefined;
  }

  private validateConfiguration(): void {
    const issues: string[] = [];

    if (!this.config.project.id) {
      issues.push('GOOGLE_CLOUD_PROJECT is required for GenAI and Vertex AI');
    }

    if (!this.config.auth.serviceAccount && !this.config.auth.apiKey) {
      issues.push('Either service account credentials or API key is required');
    }

    if (this.config.apis.storage.enabled && !this.config.apis.storage.bucket) {
      issues.push('GOOGLE_CLOUD_STORAGE_BUCKET is required when storage is enabled');
    }

    if (issues.length > 0) {
      console.warn('[Google Cloud] Configuration issues:');
      issues.forEach(issue => console.warn(`  - ${issue}`));
    } else {
      console.log('[Google Cloud] Configuration validated successfully');
    }
  }

  public getConfig(): GoogleCloudConfig {
    return this.config;
  }

  public getProjectId(): string {
    return this.config.project.id;
  }

  public getLocation(): string {
    return this.config.project.location;
  }

  public getGenAIModel(modelName: string): string | null {
    return this.config.apis.genai.models[modelName as keyof typeof this.config.apis.genai.models] || null;
  }

  public isGenAIEnabled(): boolean {
    return this.config.apis.genai.enabled && !!this.config.project.id;
  }

  public isVertexAIEnabled(): boolean {
    return this.config.apis.vertexAI.enabled && !!this.config.project.id;
  }

  public isStorageEnabled(): boolean {
    return this.config.apis.storage.enabled && !!this.config.apis.storage.bucket;
  }

  public getAuthConfig(): GoogleCloudConfig['auth'] {
    return this.config.auth;
  }

  public updateConfig(updates: Partial<GoogleCloudConfig>): void {
    this.config = { ...this.config, ...updates };
    this.validateConfiguration();
  }

  public getEnvironmentInfo(): {
    projectId: string;
    location: string;
    enabledServices: string[];
    authMethod: string;
  } {
    const enabledServices: string[] = [];
    
    if (this.isGenAIEnabled()) enabledServices.push('GenAI');
    if (this.isVertexAIEnabled()) enabledServices.push('Vertex AI');
    if (this.isStorageEnabled()) enabledServices.push('Storage');
    if (this.config.apis.pubsub.enabled) enabledServices.push('Pub/Sub');

    return {
      projectId: this.config.project.id,
      location: this.config.project.location,
      enabledServices,
      authMethod: this.config.auth.serviceAccount ? 'Service Account' : 'API Key',
    };
  }
}

// Export singleton instance
export const googleCloudConfig = GoogleCloudConfigManager.getInstance();

// Export types
export type { GoogleCloudConfig };

// Export convenience functions
export const getProjectId = () => googleCloudConfig.getProjectId();
export const getLocation = () => googleCloudConfig.getLocation();
export const getGenAIModel = (model: string) => googleCloudConfig.getGenAIModel(model);
export const isGenAIEnabled = () => googleCloudConfig.isGenAIEnabled();
export const isVertexAIEnabled = () => googleCloudConfig.isVertexAIEnabled();
export const getAuthConfig = () => googleCloudConfig.getAuthConfig();
