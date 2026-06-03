/**
 * Home Assistant Action — Controls smart home devices
 * Bridges KIVO home intents to Home Assistant API
 */

class HomeAssistantAction {
  constructor(haConfig) {
    this.config = {
      baseUrl: haConfig.baseUrl || process.env.HOME_ASSISTANT_URL || 'http://homeassistant.local:8123',
      token: haConfig.token || process.env.HOME_ASSISTANT_TOKEN,
      timeout: haConfig.timeout || 5000
    };
    
    this.devices = new Map();
    this.initializeDevices();
  }

  initializeDevices() {
    // Register common devices
    this.devices.set('licht', {
      entityId: 'light.living_room',
      type: 'light',
      name: 'Wohnzimmer Licht'
    });
    
    this.devices.set('lampe', {
      entityId: 'light.bedroom',
      type: 'light', 
      name: 'Schlafzimmer Lampe'
    });
    
    this.devices.set('heizung', {
      entityId: 'climate.thermostat',
      type: 'climate',
      name: 'Heizung'
    });
    
    this.devices.set('tor', {
      entityId: 'cover.garage_door',
      type: 'cover',
      name: 'Garagentor'
    });
    
    this.devices.set('tür', {
      entityId: 'lock.front_door',
      type: 'lock',
      name: 'Haustür'
    });
  }

  async execute(action, options = {}) {
    const { device, value, chatId } = options;
    
    try {
      switch (action) {
        case 'control':
          return await this.controlDevice(device, value);
        case 'climate':
          return await this.setClimate(device, value);
        case 'timer':
          return await this.setTimer(value);
        case 'access':
          return await this.controlAccess(device, value);
        case 'scene':
          return await this.activateScene(value);
        default:
          return { success: false, error: 'Unknown action' };
      }
    } catch (e) {
      return {
        success: false,
        error: e.message,
        message: `❌ Home Assistant action failed: ${e.message}`
      };
    }
  }

  async controlDevice(device, action) {
    const deviceInfo = this.devices.get(device);
    if (!deviceInfo) {
      return {
        success: false,
        error: 'Device not found',
        message: `❌ Device "${device}" not found`
      };
    }

    const service = action === 'on' ? 'turn_on' : action === 'off' ? 'turn_off' : 'toggle';
    const result = await this.callService(`${deviceInfo.type}/${service}`, {
      entity_id: deviceInfo.entityId
    });

    return {
      success: true,
      device: deviceInfo.name,
      action,
      result,
      message: `🏠 ${deviceInfo.name}: ${action}`
    };
  }

  async setClimate(device, temperature) {
    const deviceInfo = this.devices.get(device) || this.devices.get('heizung');
    if (!deviceInfo || deviceInfo.type !== 'climate') {
      return {
        success: false,
        error: 'Climate device not found',
        message: '❌ Climate control not available'
      };
    }

    const result = await this.callService('climate/set_temperature', {
      entity_id: deviceInfo.entityId,
      temperature: temperature
    });

    return {
      success: true,
      device: deviceInfo.name,
      temperature,
      result,
      message: `🌡️ ${deviceInfo.name}: ${temperature}°C`
    };
  }

  async setTimer(minutes) {
    // This could integrate with Home Assistant timer entity
    const timerName = `kivo_timer_${Date.now()}`;
    const result = await this.callService('timer/start', {
      entity_id: 'timer.kivo_timer',
      duration: `${minutes}:00:00`,
      friendly_name: `KIVO Timer (${minutes}min)`
    });

    return {
      success: true,
      timer: { minutes, name: timerName },
      result,
      message: `⏰ Timer für ${minutes} Minuten gestellt`
    };
  }

  async controlAccess(device, action) {
    const deviceInfo = this.devices.get(device);
    if (!deviceInfo) {
      return {
        success: false,
        error: 'Access device not found',
        message: `❌ Access device "${device}" not found`
      };
    }

    let service;
    if (deviceInfo.type === 'cover') {
      service = action === 'open' ? 'open_cover' : action === 'close' ? 'close_cover' : 'toggle';
    } else if (deviceInfo.type === 'lock') {
      service = action === 'unlock' ? 'unlock' : action === 'lock' ? 'lock' : 'toggle';
    } else {
      service = 'toggle';
    }

    const result = await this.callService(`${deviceInfo.type}/${service}`, {
      entity_id: deviceInfo.entityId
    });

    return {
      success: true,
      device: deviceInfo.name,
      action,
      result,
      message: `🔓 ${deviceInfo.name}: ${action}`
    };
  }

  async activateScene(sceneName) {
    const sceneEntityId = `scene.${sceneName.toLowerCase().replace(/\s+/g, '_')}`;
    
    const result = await this.callService('scene/turn_on', {
      entity_id: sceneEntityId
    });

    return {
      success: true,
      scene: sceneName,
      result,
      message: `🎬 Scene "${sceneName}" activated`
    };
  }

  async callService(service, data) {
    if (!this.config.token) {
      throw new Error('HOME_ASSISTANT_TOKEN not configured');
    }

    const url = `${this.config.baseUrl}/api/services/${service}`;
    
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.config.token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
      signal: AbortSignal.timeout(this.config.timeout),
    });

    if (!response.ok) {
      throw new Error(`Home Assistant API error: ${response.status} ${response.statusText}`);
    }

    return await response.json();
  }

  // ── Device Discovery ───────────────────────────────────────
  async discoverDevices() {
    try {
      const response = await fetch(`${this.config.baseUrl}/api/states`, {
        headers: {
          'Authorization': `Bearer ${this.config.token}`,
        },
        signal: AbortSignal.timeout(this.config.timeout),
      });

      if (!response.ok) {
        throw new Error('Failed to fetch devices');
      }

      const states = await response.json();
      const devices = [];

      for (const state of states) {
        if (state.entity_id.startsWith('light.') || 
            state.entity_id.startsWith('switch.') ||
            state.entity_id.startsWith('climate.') ||
            state.entity_id.startsWith('cover.') ||
            state.entity_id.startsWith('lock.')) {
          devices.push({
            entityId: state.entity_id,
            friendlyName: state.attributes.friendly_name || state.entity_id,
            state: state.state,
            type: state.entity_id.split('.')[0]
          });
        }
      }

      return { success: true, devices };
    } catch (e) {
      return { success: false, error: e.message };
    }
  }

  // ── Status ─────────────────────────────────────────────────
  async getDeviceStatus(deviceId) {
    try {
      const response = await fetch(`${this.config.baseUrl}/api/states/${deviceId}`, {
        headers: {
          'Authorization': `Bearer ${this.config.token}`,
        },
        signal: AbortSignal.timeout(this.config.timeout),
      });

      if (!response.ok) {
        throw new Error(`Device ${deviceId} not found`);
      }

      return await response.json();
    } catch (e) {
      return { error: e.message };
    }
  }

  async getSystemStatus() {
    try {
      const response = await fetch(`${this.config.baseUrl}/api/config`, {
        headers: {
          'Authorization': `Bearer ${this.config.token}`,
        },
        signal: AbortSignal.timeout(this.config.timeout),
      });

      if (!response.ok) {
        throw new Error('Failed to get system status');
      }

      const config = await response.json();
      
      return {
        success: true,
        version: config.version,
        location: config.location,
        timezone: config.time_zone,
        units: config.unit_system,
        message: `🏠 Home Assistant v${config.version} — ${config.location}`
      };
    } catch (e) {
      return {
        success: false,
        error: e.message,
        message: '❌ Home Assistant not reachable'
      };
    }
  }

  // ── Approval Check ───────────────────────────────────────
  requiresApproval(action, options) {
    // Most home actions don't require approval for safety
    // But access control (garage, locks) might
    if (action === 'access') {
      return true; // Require approval for access control
    }
    return false;
  }

  // ── Helper Methods ───────────────────────────────────────
  registerDevice(id, config) {
    this.devices.set(id, config);
  }

  getDevice(id) {
    return this.devices.get(id);
  }

  listDevices() {
    return Array.from(this.devices.entries()).map(([id, config]) => ({
      id,
      ...config
    }));
  }

  getStatus() {
    return {
      configured: !!this.config.token,
      baseUrl: this.config.baseUrl,
      devicesRegistered: this.devices.size,
      lastAction: this.lastAction || null
    };
  }
}

module.exports = { HomeAssistantAction };
