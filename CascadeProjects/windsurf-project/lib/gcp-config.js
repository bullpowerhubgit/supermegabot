/**
 * GCP Configuration Library
 * Shared configuration for all RudiBot tools
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const CONFIG_PATH = path.join(__dirname, '..', 'RudiBot-Secure-API', 'gcp-config.json');

class GCPConfig {
  constructor() {
    this.config = null;
    this.loadConfig();
  }

  loadConfig() {
    try {
      if (fs.existsSync(CONFIG_PATH)) {
        const data = fs.readFileSync(CONFIG_PATH, 'utf8');
        this.config = JSON.parse(data);
      } else {
        console.warn(`GCP config not found at ${CONFIG_PATH}`);
        this.config = this.getDefaultConfig();
      }
    } catch (error) {
      console.error('Error loading GCP config:', error.message);
      this.config = this.getDefaultConfig();
    }
  }

  getDefaultConfig() {
    return {
      project: {
        id: 'gen-lang-client-0895465231',
        number: '1023902745882',
        name: 'Shopy'
      },
      apis: {
        enabled: []
      }
    };
  }

  get projectId() {
    return this.config?.project?.id || '';
  }

  get projectNumber() {
    return this.config?.project?.number || '';
  }

  get projectName() {
    return this.config?.project?.name || '';
  }

  get apis() {
    return this.config?.apis?.enabled || [];
  }

  get billingAccount() {
    return this.config?.project?.billing_account || '';
  }

  get apiList() {
    return this.apis.map(api => api.name);
  }

  hasApi(apiName) {
    return this.apiList.includes(apiName);
  }

  getAuthMethod() {
    return this.config?.auth?.method || 'gcloud';
  }

  isCloudShell() {
    return this.config?.auth?.cloud_shell || false;
  }

  toJSON() {
    return this.config;
  }
}

// Singleton instance
const gcpConfig = new GCPConfig();

export default gcpConfig;
export { GCPConfig };
