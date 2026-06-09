import { exec } from 'child_process';
import { promisify } from 'util';
import { MacAction } from './types.js';

const execAsync = promisify(exec);

export class MacController {
  async execute(action: MacAction): Promise<string> {
    switch (action.action) {
      case 'click':
        await execAsync('osascript -e \'tell application "System Events" to click at {0, 0}\'');
        return 'Clicked at current position';

      case 'moveMouse':
        if (action.x === undefined || action.y === undefined) {
          throw new Error('X and Y coordinates required for moveMouse');
        }
        await execAsync(`osascript -e 'tell application "System Events" to set mouseLocation to {${action.x}, ${action.y}}'`);
        return `Moved mouse to ${action.x}, ${action.y}`;

      case 'type':
        if (!action.text) throw new Error('Text required for type');
        const escapedText = action.text.replace(/"/g, '\\"');
        await execAsync(`osascript -e 'tell application "System Events" to keystroke "${escapedText}"'`);
        return `Typed: ${action.text}`;

      case 'keyCombo':
        if (!action.keys || action.keys.length === 0) {
          throw new Error('Keys array required for keyCombo');
        }
        const keys = action.keys.map(k => {
          const map: Record<string, string> = { cmd: 'command', ctrl: 'control', alt: 'option', shift: 'shift' };
          return map[k.toLowerCase()] || k.toLowerCase();
        });
        const keyCombo = keys.join(' + ');
        await execAsync(`osascript -e 'tell application "System Events" to key code 0 using {${keys.slice(0, -1).map(k => k + ' down').join(', ')}}'`);
        return `Pressed key combo: ${keyCombo}`;

      case 'openApp':
        if (!action.app) throw new Error('App name required for openApp');
        await execAsync(`open -a "${action.app}"`);
        return `Opened app: ${action.app}`;

      case 'screenshot':
        await execAsync('screencapture -x /tmp/apitool_screenshot.png');
        return 'Screenshot saved to /tmp/apitool_screenshot.png';

      case 'getClipboard':
        const { stdout: clipboardText } = await execAsync('pbpaste');
        return `Clipboard: ${clipboardText}`;

      case 'setClipboard':
        if (!action.text) throw new Error('Text required for setClipboard');
        await execAsync(`echo "${action.text.replace(/"/g, '\\"')}" | pbcopy`);
        return `Clipboard set to: ${action.text}`;

      case 'getSystemInfo': {
        try {
          const { stdout: cpuInfo } = await execAsync('sysctl -n machdep.cpu.brand_string 2>/dev/null || echo "Unknown"');
          const { stdout: cpuCores } = await execAsync('sysctl -n hw.ncpu 2>/dev/null || echo "0"');
          const { stdout: totalMem } = await execAsync('sysctl -n hw.memsize 2>/dev/null || echo "0"');
          const totalMemGB = Math.round(parseInt(totalMem.trim()) / 1024 / 1024 / 1024);
          const { stdout: osVersion } = await execAsync('sw_vers -productVersion 2>/dev/null || echo "Unknown"');
          const { stdout: hostname } = await execAsync('hostname 2>/dev/null || echo "Unknown"');
          return JSON.stringify({
            cpu: cpuInfo.trim(),
            cores: parseInt(cpuCores.trim()),
            memoryGB: totalMemGB,
            osVersion: osVersion.trim(),
            hostname: hostname.trim(),
            source: 'macOS_system_profiler',
            timestamp: new Date().toISOString()
          });
        } catch (e: any) {
          return `System info unavailable: ${e.message}`;
        }
      }

      case 'getCPUUsage': {
        try {
          const { stdout } = await execAsync('top -l 1 -n 0 -F 2>/dev/null | head -5 || echo "CPU usage unavailable"');
          const lines = stdout.split('\n');
          const cpuLine = lines.find(l => l.includes('CPU usage')) || lines.find(l => l.includes('CPU')) || 'N/A';
          return JSON.stringify({
            raw: cpuLine.trim(),
            source: 'top',
            timestamp: new Date().toISOString()
          });
        } catch (e: any) {
          return `CPU usage unavailable: ${e.message}`;
        }
      }

      case 'getMemoryUsage': {
        try {
          const { stdout: vmStat } = await execAsync('vm_stat 2>/dev/null || echo "Memory stats unavailable"');
          const { stdout: totalMem } = await execAsync('sysctl -n hw.memsize 2>/dev/null || echo "0"');
          const totalMB = Math.round(parseInt(totalMem.trim()) / 1024 / 1024);
          const wired = parseInt((vmStat.match(/wired down: +([0-9]+)/) || [0, '0'])[1].replace('.', '')) * 4 / 1024;
          const active = parseInt((vmStat.match(/active: +([0-9]+)/) || [0, '0'])[1].replace('.', '')) * 4 / 1024;
          const usedMB = Math.round(wired + active);
          const freeMB = totalMB - usedMB;
          return JSON.stringify({
            totalMB,
            usedMB,
            freeMB,
            percentUsed: totalMB > 0 ? Math.round((usedMB / totalMB) * 100) : 0,
            source: 'vm_stat',
            timestamp: new Date().toISOString()
          });
        } catch (e: any) {
          return `Memory usage unavailable: ${e.message}`;
        }
      }

      case 'getDiskUsage': {
        try {
          const { stdout } = await execAsync('df -h / 2>/dev/null || echo "Disk info unavailable"');
          const lines = stdout.split('\n');
          const dataLine = lines[1] || '';
          const parts = dataLine.trim().split(/\s+/);
          return JSON.stringify({
            filesystem: parts[0] || 'N/A',
            size: parts[1] || 'N/A',
            used: parts[2] || 'N/A',
            available: parts[3] || 'N/A',
            percentUsed: parts[4] || 'N/A',
            source: 'df',
            timestamp: new Date().toISOString()
          });
        } catch (e: any) {
          return `Disk usage unavailable: ${e.message}`;
        }
      }

      default:
        throw new Error(`Unknown action: ${action.action}`);
    }
  }
}
