// RudiBot AI Assistant Backend API
// Vollständige Berechtigungen für alle System-Aktionen

// @ts-ignore
import axios from 'axios';

const API_BASE = 'http://localhost:3000/api';

interface AssistantCommand {
  command: string;
  params?: any;
  confirm?: boolean;
}

interface AssistantResponse {
  success: boolean;
  message: string;
  data?: any;
  action?: {
    type: string;
    status: 'pending' | 'success' | 'error';
    result?: any;
  };
}

export class AssistantAPI {
  // ═══════════════════════════════════════════════════════════════
  // SYSTEM-STEUERUNG (Vollständige Berechtigungen)
  // ═══════════════════════════════════════════════════════════════

  async executeCommand(command: AssistantCommand): Promise<AssistantResponse> {
    try {
      const response = await axios.post(`${API_BASE}/assistant/execute`, command);
      return response.data;
    } catch (error) {
      return {
        success: false,
        message: `Fehler bei Befehlsausführung: ${error}`,
      };
    }
  }

  async getSystemStatus(): Promise<AssistantResponse> {
    try {
      const response = await axios.get(`${API_BASE}/system/status`);
      return {
        success: true,
        message: 'System-Status abgerufen',
        data: response.data,
      };
    } catch (error) {
      return {
        success: false,
        message: 'Konnte System-Status nicht abrufen',
      };
    }
  }

  async restartService(serviceName: string): Promise<AssistantResponse> {
    try {
      const response = await axios.post(`${API_BASE}/system/restart`, { service: serviceName });
      return {
        success: true,
        message: `Service ${serviceName} wird neu gestartet`,
        action: { type: 'restart', status: 'pending' },
      };
    } catch (error) {
      return {
        success: false,
        message: `Konnte ${serviceName} nicht neu starten`,
      };
    }
  }

  async stopService(serviceName: string): Promise<AssistantResponse> {
    try {
      const response = await axios.post(`${API_BASE}/system/stop`, { service: serviceName });
      return {
        success: true,
        message: `Service ${serviceName} gestoppt`,
        action: { type: 'stop', status: 'success' },
      };
    } catch (error) {
      return {
        success: false,
        message: `Konnte ${serviceName} nicht stoppen`,
      };
    }
  }

  async startService(serviceName: string): Promise<AssistantResponse> {
    try {
      const response = await axios.post(`${API_BASE}/system/start`, { service: serviceName });
      return {
        success: true,
        message: `Service ${serviceName} gestartet`,
        action: { type: 'start', status: 'success' },
      };
    } catch (error) {
      return {
        success: false,
        message: `Konnte ${serviceName} nicht starten`,
      };
    }
  }

  // ═══════════════════════════════════════════════════════════════
  // SHOPIFY-AKTIONEN (Vollständige Berechtigungen)
  // ═══════════════════════════════════════════════════════════════

  async uploadProducts(products: any[]): Promise<AssistantResponse> {
    try {
      const response = await axios.post(`${API_BASE}/shopify/products/upload`, { products });
      return {
        success: true,
        message: `${products.length} Produkte werden hochgeladen`,
        action: { type: 'shopify_upload', status: 'pending' },
      };
    } catch (error) {
      return {
        success: false,
        message: 'Produkt-Upload fehlgeschlagen',
      };
    }
  }

  async syncOrders(): Promise<AssistantResponse> {
    try {
      const response = await axios.post(`${API_BASE}/shopify/orders/sync`);
      return {
        success: true,
        message: 'Bestellungen werden synchronisiert',
        action: { type: 'shopify_sync', status: 'pending' },
      };
    } catch (error) {
      return {
        success: false,
        message: 'Bestellungssynchronisierung fehlgeschlagen',
      };
    }
  }

  async updateInventory(items: any[]): Promise<AssistantResponse> {
    try {
      const response = await axios.post(`${API_BASE}/shopify/inventory/update`, { items });
      return {
        success: true,
        message: `${items.length} Artikel aktualisiert`,
        action: { type: 'inventory_update', status: 'success' },
      };
    } catch (error) {
      return {
        success: false,
        message: 'Inventar-Update fehlgeschlagen',
      };
    }
  }

  async createWebhook(topic: string, url: string): Promise<AssistantResponse> {
    try {
      const response = await axios.post(`${API_BASE}/shopify/webhooks/create`, { topic, url });
      return {
        success: true,
        message: `Webhook für ${topic} erstellt`,
        action: { type: 'webhook_create', status: 'success' },
      };
    } catch (error) {
      return {
        success: false,
        message: 'Webhook-Erstellung fehlgeschlagen',
      };
    }
  }

  // ═══════════════════════════════════════════════════════════════
  // AUTOMATION-KORREKTUR (Vollständige Berechtigungen)
  // ═══════════════════════════════════════════════════════════════

  async fixAutomation(automationId: string, issue: string): Promise<AssistantResponse> {
    try {
      const response = await axios.post(`${API_BASE}/automation/fix`, { 
        automationId, 
        issue 
      });
      return {
        success: true,
        message: `Automation ${automationId} wird korrigiert`,
        action: { type: 'automation_fix', status: 'pending' },
      };
    } catch (error) {
      return {
        success: false,
        message: 'Automations-Korrektur fehlgeschlagen',
      };
    }
  }

  async enableAutomation(automationId: string): Promise<AssistantResponse> {
    try {
      const response = await axios.post(`${API_BASE}/automation/enable`, { automationId });
      return {
        success: true,
        message: `Automation ${automationId} aktiviert`,
        action: { type: 'automation_enable', status: 'success' },
      };
    } catch (error) {
      return {
        success: false,
        message: 'Automations-Aktivierung fehlgeschlagen',
      };
    }
  }

  async disableAutomation(automationId: string): Promise<AssistantResponse> {
    try {
      const response = await axios.post(`${API_BASE}/automation/disable`, { automationId });
      return {
        success: true,
        message: `Automation ${automationId} deaktiviert`,
        action: { type: 'automation_disable', status: 'success' },
      };
    } catch (error) {
      return {
        success: false,
        message: 'Automations-Deaktivierung fehlgeschlagen',
      };
    }
  }

  async getAutomationStatus(): Promise<AssistantResponse> {
    try {
      const response = await axios.get(`${API_BASE}/automation/status`);
      return {
        success: true,
        message: 'Automations-Status abgerufen',
        data: response.data,
      };
    } catch (error) {
      return {
        success: false,
        message: 'Konnte Automations-Status nicht abrufen',
      };
    }
  }

  async configureAutomation(automationId: string, config: any): Promise<AssistantResponse> {
    try {
      const response = await axios.post(`${API_BASE}/automation/configure`, { 
        automationId, 
        config 
      });
      return {
        success: true,
        message: `Automation ${automationId} konfiguriert`,
        action: { type: 'automation_configure', status: 'success' },
      };
    } catch (error) {
      return {
        success: false,
        message: 'Automations-Konfiguration fehlgeschlagen',
      };
    }
  }

  // ═══════════════════════════════════════════════════════════════
  // EINSTELLUNGS-MANAGEMENT (Vollständige Berechtigungen)
  // ═══════════════════════════════════════════════════════════════

  async updateSetting(key: string, value: any): Promise<AssistantResponse> {
    try {
      const response = await axios.put(`${API_BASE}/settings/${key}`, { value });
      return {
        success: true,
        message: `Einstellung ${key} aktualisiert`,
        action: { type: 'setting_update', status: 'success' },
      };
    } catch (error) {
      return {
        success: false,
        message: 'Einstellungs-Update fehlgeschlagen',
      };
    }
  }

  async getSettings(): Promise<AssistantResponse> {
    try {
      const response = await axios.get(`${API_BASE}/settings`);
      return {
        success: true,
        message: 'Einstellungen abgerufen',
        data: response.data,
      };
    } catch (error) {
      return {
        success: false,
        message: 'Konnte Einstellungen nicht abrufen',
      };
    }
  }

  async resetSettings(): Promise<AssistantResponse> {
    try {
      const response = await axios.post(`${API_BASE}/settings/reset`);
      return {
        success: true,
        message: 'Einstellungen auf Standard zurückgesetzt',
        action: { type: 'settings_reset', status: 'success' },
      };
    } catch (error) {
      return {
        success: false,
        message: 'Einstellungs-Reset fehlgeschlagen',
      };
    }
  }

  // ═══════════════════════════════════════════════════════════════
  // MONITORING & ALERTS (Vollständige Berechtigungen)
  // ═══════════════════════════════════════════════════════════════

  async getAlerts(): Promise<AssistantResponse> {
    try {
      const response = await axios.get(`${API_BASE}/alerts`);
      return {
        success: true,
        message: 'Alerts abgerufen',
        data: response.data,
      };
    } catch (error) {
      return {
        success: false,
        message: 'Konnte Alerts nicht abrufen',
      };
    }
  }

  async acknowledgeAlert(alertId: string): Promise<AssistantResponse> {
    try {
      const response = await axios.post(`${API_BASE}/alerts/${alertId}/acknowledge`);
      return {
        success: true,
        message: `Alert ${alertId} bestätigt`,
        action: { type: 'alert_acknowledge', status: 'success' },
      };
    } catch (error) {
      return {
        success: false,
        message: 'Alert-Bestätigung fehlgeschlagen',
      };
    }
  }

  async configureAlert(alertId: string, config: any): Promise<AssistantResponse> {
    try {
      const response = await axios.put(`${API_BASE}/alerts/${alertId}`, { config });
      return {
        success: true,
        message: `Alert ${alertId} konfiguriert`,
        action: { type: 'alert_configure', status: 'success' },
      };
    } catch (error) {
      return {
        success: false,
        message: 'Alert-Konfiguration fehlgeschlagen',
      };
    }
  }

  // ═══════════════════════════════════════════════════════════════
  // PROFIT & MONETARISIERUNG (Vollständige Berechtigungen)
  // ═══════════════════════════════════════════════════════════════

  async getProfitReport(): Promise<AssistantResponse> {
    try {
      const response = await axios.get(`${API_BASE}/monetize/profit`);
      return {
        success: true,
        message: 'Profit-Report abgerufen',
        data: response.data,
      };
    } catch (error) {
      return {
        success: false,
        message: 'Konnte Profit-Report nicht abrufen',
      };
    }
  }

  async addRevenue(source: string, amount: number, customer?: string): Promise<AssistantResponse> {
    try {
      const response = await axios.post(`${API_BASE}/monetize/revenue`, { 
        source, 
        amount, 
        customer 
      });
      return {
        success: true,
        message: `Einnahme von ${amount}€ von ${source} erfasst`,
        action: { type: 'revenue_add', status: 'success' },
      };
    } catch (error) {
      return {
        success: false,
        message: 'Einnahmen-Erfassung fehlgeschlagen',
      };
    }
  }

  async addCost(category: string, amount: number, description?: string): Promise<AssistantResponse> {
    try {
      const response = await axios.post(`${API_BASE}/monetize/cost`, { 
        category, 
        amount, 
        description 
      });
      return {
        success: true,
        message: `Kosten von ${amount}€ für ${category} erfasst`,
        action: { type: 'cost_add', status: 'success' },
      };
    } catch (error) {
      return {
        success: false,
        message: 'Kosten-Erfassung fehlgeschlagen',
      };
    }
  }

  // ═══════════════════════════════════════════════════════════════
  // DIAGNOSTIK & REPAIR (Vollständige Berechtigungen)
  // ═══════════════════════════════════════════════════════════════

  async runDiagnostics(): Promise<AssistantResponse> {
    try {
      const response = await axios.post(`${API_BASE}/diagnostics/run`);
      return {
        success: true,
        message: 'Diagnose läuft...',
        action: { type: 'diagnostics', status: 'pending' },
      };
    } catch (error) {
      return {
        success: false,
        message: 'Diagnose-Start fehlgeschlagen',
      };
    }
  }

  async autoRepair(issueId: string): Promise<AssistantResponse> {
    try {
      const response = await axios.post(`${API_BASE}/diagnostics/repair`, { issueId });
      return {
        success: true,
        message: `Auto-Repair für ${issueId} gestartet`,
        action: { type: 'auto_repair', status: 'pending' },
      };
    } catch (error) {
      return {
        success: false,
        message: 'Auto-Repair fehlgeschlagen',
      };
    }
  }

  async getLogs(service: string, lines: number = 100): Promise<AssistantResponse> {
    try {
      const response = await axios.get(`${API_BASE}/logs/${service}`, { params: { lines } });
      return {
        success: true,
        message: `Logs für ${service} abgerufen`,
        data: response.data,
      };
    } catch (error) {
      return {
        success: false,
        message: 'Konnte Logs nicht abrufen',
      };
    }
  }

  async clearLogs(service: string): Promise<AssistantResponse> {
    try {
      await axios.delete(`${API_BASE}/logs/${service}`);
      return {
        success: true,
        message: `Logs für ${service} gelöscht`,
        action: { type: 'logs_clear', status: 'success' },
      };
    } catch (error) {
      return {
        success: false,
        message: 'Log-Löschung fehlgeschlagen',
      };
    }
  }
}

export const assistantAPI = new AssistantAPI();
