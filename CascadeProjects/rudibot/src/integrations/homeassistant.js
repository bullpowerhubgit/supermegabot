/**
 * Home Assistant Integration — Smart home platform integration
 * Handles device control, state monitoring, and automation
 */

const HomeAssistantAction = require('../actions/homeassistant-action');

class HomeAssistantIntegration {
  constructor(config) {
    this.action = new HomeAssistantAction(config);
    this.config = {
      baseUrl: config.baseUrl || process.env.HOME_ASSISTANT_URL || 'http://homeassistant.local:8123',
      token: config.token || process.env.HOME_ASSISTANT_TOKEN,
      timeout: config.timeout || 5000
    };
    
    this.entities = new Map();
    this.automations = new Map();
    this.scenes = new Map();
  }

  // ── Device Management ───────────────────────────────────────
  async getDevices(type = null) {
    try {
      const states = await this.fetchStates();
      const devices = [];

      for (const state of states) {
        const entityType = state.entity_id.split('.')[0];
        
        if (!type || entityType === type) {
          devices.push({
            entityId: state.entity_id,
            friendlyName: state.attributes.friendly_name || state.entity_id,
            state: state.state,
            type: entityType,
            attributes: state.attributes,
            lastChanged: state.last_changed,
            lastUpdated: state.last_updated
          });
        }
      }

      return { success: true, devices };
    } catch (e) {
      return { success: false, error: e.message };
    }
  }

  async getDeviceState(entityId) {
    try {
      const state = await this.fetchState(entityId);
      return {
        success: true,
        entityId: state.entity_id,
        state: state.state,
        attributes: state.attributes,
        lastChanged: state.last_changed,
        lastUpdated: state.last_updated
      };
    } catch (e) {
      return { success: false, error: e.message };
    }
  }

  async setDeviceState(entityId, state, attributes = {}) {
    try {
      const entityType = entityId.split('.')[0];
      const service = this.determineService(entityType, state);
      
      const data = { entity_id: entityId, ...attributes };
      const result = await this.callService(service, data);
      
      return {
        success: true,
        entityId,
        state,
        result,
        message: `✅ ${entityId}: ${state}`
      };
    } catch (e) {
      return {
        success: false,
        error: e.message,
        message: `❌ Failed to set ${entityId}: ${e.message}`
      };
    }
  }

  determineService(entityType, state) {
    const serviceMap = {
      'light': {
        'on': 'light.turn_on',
        'off': 'light.turn_off',
        'toggle': 'light.toggle'
      },
      'switch': {
        'on': 'switch.turn_on',
        'off': 'switch.turn_off',
        'toggle': 'switch.toggle'
      },
      'cover': {
        'open': 'cover.open_cover',
        'close': 'cover.close_cover',
        'stop': 'cover.stop_cover',
        'toggle': 'cover.toggle'
      },
      'lock': {
        'unlock': 'lock.unlock',
        'lock': 'lock.lock'
      },
      'climate': {
        'heat': 'climate.set_hvac_mode',
        'cool': 'climate.set_hvac_mode',
        'off': 'climate.turn_off',
        'auto': 'climate.set_hvac_mode'
      },
      'media_player': {
        'on': 'media_player.turn_on',
        'off': 'media_player.turn_off',
        'play': 'media_player.media_play',
        'pause': 'media_player.media_pause',
        'stop': 'media_player.media_stop'
      }
    };

    return serviceMap[entityType]?.[state] || `${entityType}.turn_${state}`;
  }

  // ── Scene Management ───────────────────────────────────────
  async getScenes() {
    try {
      const states = await this.fetchStates();
      const scenes = [];

      for (const state of states) {
        if (state.entity_id.startsWith('scene.')) {
          scenes.push({
            entityId: state.entity_id,
            friendlyName: state.attributes.friendly_name || state.entity_id,
            icon: state.attributes.icon,
            id: state.attributes.id
          });
        }
      }

      return { success: true, scenes };
    } catch (e) {
      return { success: false, error: e.message };
    }
  }

  async activateScene(sceneId) {
    try {
      const result = await this.callService('scene.turn_on', { entity_id: sceneId });
      
      return {
        success: true,
        sceneId,
        result,
        message: `🎬 Scene activated: ${sceneId}`
      };
    } catch (e) {
      return {
        success: false,
        error: e.message,
        message: `❌ Failed to activate scene: ${e.message}`
      };
    }
  }

  // ── Automation Management ───────────────────────────────────
  async getAutomations() {
    try {
      const states = await this.fetchStates();
      const automations = [];

      for (const state of states) {
        if (state.entity_id.startsWith('automation.')) {
          automations.push({
            entityId: state.entity_id,
            friendlyName: state.attributes.friendly_name || state.entity_id,
            state: state.state,
            mode: state.attributes.mode,
            lastTriggered: state.attributes.last_triggered
          });
        }
      }

      return { success: true, automations };
    } catch (e) {
      return { success: false, error: e.message };
    }
  }

  async triggerAutomation(automationId) {
    try {
      const result = await this.callService('automation.trigger', { entity_id: automationId });
      
      return {
        success: true,
        automationId,
        result,
        message: `🤖 Automation triggered: ${automationId}`
      };
    } catch (e) {
      return {
        success: false,
        error: e.message,
        message: `❌ Failed to trigger automation: ${e.message}`
      };
    }
  }

  async toggleAutomation(automationId) {
    try {
      const result = await this.callService('automation.toggle', { entity_id: automationId });
      
      return {
        success: true,
        automationId,
        result,
        message: `🔄 Automation toggled: ${automationId}`
      };
    } catch (e) {
      return {
        success: false,
        error: e.message,
        message: `❌ Failed to toggle automation: ${e.message}`
      };
    }
  }

  // ── Climate Control ───────────────────────────────────────
  async setTemperature(entityId, temperature, hvacMode = null) {
    try {
      const data = { entity_id: entityId, temperature };
      
      if (hvacMode) {
        data.hvac_mode = hvacMode;
        const result = await this.callService('climate.set_temperature', data);
      } else {
        const result = await this.callService('climate.set_temperature', data);
      }

      return {
        success: true,
        entityId,
        temperature,
        hvacMode,
        message: `🌡️ ${entityId}: ${temperature}°C${hvacMode ? ` (${hvacMode})` : ''}`
      };
    } catch (e) {
      return {
        success: false,
        error: e.message,
        message: `❌ Failed to set temperature: ${e.message}`
      };
    }
  }

  async setClimateMode(entityId, hvacMode) {
    try {
      const result = await this.callService('climate.set_hvac_mode', {
        entity_id: entityId,
        hvac_mode: hvacMode
      });

      return {
        success: true,
        entityId,
        hvacMode,
        result,
        message: `🌡️ ${entityId}: ${hvacMode}`
      };
    } catch (e) {
      return {
        success: false,
        error: e.message,
        message: `❌ Failed to set climate mode: ${e.message}`
      };
    }
  }

  // ── Timer Management ───────────────────────────────────────
  async startTimer(entityId, duration) {
    try {
      const result = await this.callService('timer.start', {
        entity_id: entityId,
        duration: duration
      });

      return {
        success: true,
        entityId,
        duration,
        result,
        message: `⏰ Timer started: ${duration}`
      };
    } catch (e) {
      return {
        success: false,
        error: e.message,
        message: `❌ Failed to start timer: ${e.message}`
      };
    }
  }

  async cancelTimer(entityId) {
    try {
      const result = await this.callService('timer.cancel', {
        entity_id: entityId
      });

      return {
        success: true,
        entityId,
        result,
        message: `⏹️ Timer cancelled: ${entityId}`
      };
    } catch (e) {
      return {
        success: false,
        error: e.message,
        message: `❌ Failed to cancel timer: ${e.message}`
      };
    }
  }

  // ── System Information ─────────────────────────────────────
  async getSystemInfo() {
    try {
      const config = await this.fetchConfig();
      const states = await this.fetchStates();
      
      const entityCount = states.length;
      const deviceCount = new Set(states.map(s => s.attributes.device_id || s.entity_id.split('.')[0])).size;
      
      return {
        success: true,
        version: config.version,
        location: config.location,
        timezone: config.time_zone,
        unitSystem: config.unit_system,
        entityCount,
        deviceCount,
        message: `🏠 Home Assistant v${config.version} — ${config.location} (${entityCount} entities)`
      };
    } catch (e) {
      return {
        success: false,
        error: e.message,
        message: '❌ Failed to get system info'
      };
    }
  }

  async getHistory(entityId = null, startTime = null, endTime = null) {
    try {
      const url = new URL(`${this.config.baseUrl}/api/history/period`);
      
      if (startTime) {
        url.searchParams.append('start_time', startTime.toISOString());
      }
      
      if (endTime) {
        url.searchParams.append('end_time', endTime.toISOString());
      }
      
      if (entityId) {
        url.searchParams.append('filter_entity_id', entityId);
      }

      const response = await fetch(url.toString(), {
        headers: {
          'Authorization': `Bearer ${this.config.token}`,
          'Content-Type': 'application/json'
        },
        signal: AbortSignal.timeout(this.config.timeout)
      });

      if (!response.ok) {
        throw new Error(`History API error: ${response.status}`);
      }

      const history = await response.json();
      
      return {
        success: true,
        history,
        message: `📊 History retrieved for ${entityId || 'all entities'}`
      };
    } catch (e) {
      return {
        success: false,
        error: e.message,
        message: '❌ Failed to get history'
      };
    }
  }

  // ── API Helpers ───────────────────────────────────────────
  async fetchStates() {
    const response = await fetch(`${this.config.baseUrl}/api/states`, {
      headers: {
        'Authorization': `Bearer ${this.config.token}`,
        'Content-Type': 'application/json'
      },
      signal: AbortSignal.timeout(this.config.timeout)
    });

    if (!response.ok) {
      throw new Error(`States API error: ${response.status}`);
    }

    return await response.json();
  }

  async fetchState(entityId) {
    const response = await fetch(`${this.config.baseUrl}/api/states/${entityId}`, {
      headers: {
        'Authorization': `Bearer ${this.config.token}`,
        'Content-Type': 'application/json'
      },
      signal: AbortSignal.timeout(this.config.timeout)
    });

    if (!response.ok) {
      throw new Error(`State API error: ${response.status}`);
    }

    return await response.json();
  }

  async fetchConfig() {
    const response = await fetch(`${this.config.baseUrl}/api/config`, {
      headers: {
        'Authorization': `Bearer ${this.config.token}`,
        'Content-Type': 'application/json'
      },
      signal: AbortSignal.timeout(this.config.timeout)
    });

    if (!response.ok) {
      throw new Error(`Config API error: ${response.status}`);
    }

    return await response.json();
  }

  async callService(service, data) {
    const response = await fetch(`${this.config.baseUrl}/api/services/${service}`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.config.token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(data),
      signal: AbortSignal.timeout(this.config.timeout)
    });

    if (!response.ok) {
      throw new Error(`Service API error: ${response.status}`);
    }

    return await response.json();
  }

  // ── Status ─────────────────────────────────────────────────
  async getStatus() {
    const systemInfo = await this.getSystemInfo();
    const devices = await this.getDevices();
    const scenes = await this.getScenes();
    const automations = await this.getAutomations();

    return {
      configured: !!this.config.token,
      baseUrl: this.config.baseUrl,
      system: systemInfo.success ? systemInfo : null,
      devices: devices.success ? devices.devices.length : 0,
      scenes: scenes.success ? scenes.scenes.length : 0,
      automations: automations.success ? automations.automations.length : 0,
      lastAction: this.lastAction || null
    };
  }

  // ── Event Listening ───────────────────────────────────────
  async subscribeToEvents(callback) {
    // WebSocket connection for real-time events
    // This would require WebSocket implementation
    console.log('WebSocket event subscription not implemented yet');
  }

  // ── Cleanup ───────────────────────────────────────────────
  disconnect() {
    // Cleanup resources if needed
    console.log('Home Assistant integration disconnected');
  }
}

module.exports = { HomeAssistantIntegration };
