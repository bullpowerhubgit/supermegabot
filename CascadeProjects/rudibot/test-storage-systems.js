#!/usr/bin/env node
/**
 * Test Script for Storage Systems
 * Tests internal storage, cloud storage, notes systems, IDE integration, and system monitoring
 */
require('dotenv').config();

const fs = require('fs');
const path = require('path');
const os = require('os');

const results = [];

function log(category, status, message) {
  const icon = status === 'OK' ? '✅' : status === 'FAIL' ? '❌' : '⚠️';
  console.log(`${icon} ${category.padEnd(25)} | ${status.padEnd(6)} | ${message}`);
  results.push({ category, status, message });
}

async function testAPI(name, url, headers = {}, body = null, method = 'GET') {
  try {
    const options = { method, headers };
    if (body) options.body = JSON.stringify(body);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 5000);
    const res = await fetch(url, { ...options, signal: controller.signal });
    clearTimeout(timer);
    const data = await res.json().catch(() => null);
    if (res.ok) return { ok: true, data };
    return { ok: false, error: data?.error?.message || `HTTP ${res.status}` };
  } catch (e) {
    return { ok: false, error: e.message };
  }
}

// Test Internal Storage Systems
async function testInternalStorage() {
  log('Internal Storage', 'INFO', 'Testing system directories...');
  
  try {
    // Test system directories
    const dirs = {
      desktop: path.join(os.homedir(), 'Desktop'),
      downloads: path.join(os.homedir(), 'Downloads'),
      documents: path.join(os.homedir(), 'Documents'),
      pictures: path.join(os.homedir(), 'Pictures'),
      music: path.join(os.homedir(), 'Music'),
      videos: path.join(os.homedir(), 'Videos'),
      applications: os.platform() === 'darwin' ? '/Applications' : 'C:\\Program Files',
      temp: os.tmpdir()
    };
    
    let accessibleDirs = 0;
    for (const [name, dirPath] of Object.entries(dirs)) {
      try {
        const stats = fs.statSync(dirPath);
        if (stats.isDirectory()) {
          accessibleDirs++;
        }
      } catch (e) {
        // Directory doesn't exist or no access
      }
    }
    
    log('System Directories', accessibleDirs >= 5 ? 'OK' : 'SKIP', `${accessibleDirs}/${Object.keys(dirs).length} accessible`);
    
    // Test API endpoints
    const dirsAPI = await testAPI('Storage Directories', 'http://localhost:3200/api/storage/directories');
    log('Storage API', dirsAPI.ok ? 'OK' : 'FAIL', dirsAPI.ok ? 'Connected' : dirsAPI.error);
    
    const desktopAPI = await testAPI('Desktop API', 'http://localhost:3200/api/storage/desktop');
    log('Desktop API', desktopAPI.ok ? 'OK' : 'FAIL', desktopAPI.ok ? 'Connected' : desktopAPI.error);
    
    const downloadsAPI = await testAPI('Downloads API', 'http://localhost:3200/api/storage/downloads');
    log('Downloads API', downloadsAPI.ok ? 'OK' : 'FAIL', downloadsAPI.ok ? 'Connected' : downloadsAPI.error);
    
  } catch (e) {
    log('Internal Storage', 'FAIL', e.message);
  }
}

// Test Cloud Storage Systems
async function testCloudStorage() {
  log('Cloud Storage', 'INFO', 'Testing cloud storage APIs...');
  
  // Google Drive
  const gdriveToken = process.env.GOOGLE_DRIVE_ACCESS_TOKEN;
  if (!gdriveToken || gdriveToken.includes('DEIN') || gdriveToken.includes('HERE')) {
    log('Google Drive', 'SKIP', 'No API key');
  } else {
    const r = await testAPI('Google Drive', 'http://localhost:3200/api/googledrive/files');
    log('Google Drive', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
  }
  
  // Dropbox
  const dropboxToken = process.env.DROPBOX_ACCESS_TOKEN;
  if (!dropboxToken || dropboxToken.includes('DEIN') || dropboxToken.includes('HERE')) {
    log('Dropbox', 'SKIP', 'No API key');
  } else {
    const r = await testAPI('Dropbox', 'http://localhost:3200/api/dropbox/files');
    log('Dropbox', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
  }
  
  // OneDrive
  const onedriveToken = process.env.ONEDRIVE_ACCESS_TOKEN;
  if (!onedriveToken || onedriveToken.includes('DEIN') || onedriveToken.includes('HERE')) {
    log('OneDrive', 'SKIP', 'No API key');
  } else {
    const r = await testAPI('OneDrive', 'http://localhost:3200/api/onedrive/files');
    log('OneDrive', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
  }
  
  // iCloud (placeholder)
  const icloudId = process.env.ICLOUD_APPLE_ID;
  if (!icloudId || icloudId.includes('DEIN') || icloudId.includes('HERE')) {
    log('iCloud', 'SKIP', 'No credentials');
  } else {
    const r = await testAPI('iCloud', 'http://localhost:3200/api/icloud/info');
    log('iCloud', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
  }
}

// Test Notes Systems
async function testNotesSystems() {
  log('Notes Systems', 'INFO', 'Testing notes APIs...');
  
  // OneNote
  const onenoteToken = process.env.ONENOTE_ACCESS_TOKEN;
  if (!onenoteToken || onenoteToken.includes('DEIN') || onenoteToken.includes('HERE')) {
    log('OneNote', 'SKIP', 'No API key');
  } else {
    const r = await testAPI('OneNote', 'http://localhost:3200/api/onenote/notebooks');
    log('OneNote', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
  }
  
  // Evernote (placeholder)
  const evernoteToken = process.env.EVERNOTE_TOKEN;
  if (!evernoteToken || evernoteToken.includes('DEIN') || evernoteToken.includes('HERE')) {
    log('Evernote', 'SKIP', 'No API key');
  } else {
    const r = await testAPI('Evernote', 'http://localhost:3200/api/evernote/notebooks');
    log('Evernote', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
  }
  
  // Apple Notes (always placeholder)
  const r = await testAPI('Apple Notes', 'http://localhost:3200/api/apple/notes');
  log('Apple Notes', r.ok ? 'OK' : 'FAIL', r.ok ? 'API available' : 'Not available');
}

// Test IDE Integration
async function testIDEIntegration() {
  log('IDE Integration', 'INFO', 'Testing development tools...');
  
  // Visual Studio Code
  const r = await testAPI('VS Code', 'http://localhost:3200/api/vscode/extensions');
  log('VS Code Marketplace', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
  
  // GitHub Codespaces
  const githubToken = process.env.GITHUB_TOKEN;
  if (!githubToken || githubToken.includes('DEIN') || githubToken.includes('HERE')) {
    log('GitHub Codespaces', 'SKIP', 'No API key');
  } else {
    const r = await testAPI('GitHub Codespaces', 'http://localhost:3200/api/codespaces/list');
    log('GitHub Codespaces', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
  }
  
  // Check for VS Code installation
  const vscodePath = os.platform() === 'darwin' 
    ? '/Applications/Visual Studio Code.app'
    : os.platform() === 'win32' 
    ? 'C:\\Program Files\\Microsoft VS Code\\Code.exe'
    : '/usr/bin/code';
  
  try {
    fs.accessSync(vscodePath);
    log('VS Code Installation', 'OK', 'VS Code installed');
  } catch (e) {
    log('VS Code Installation', 'SKIP', 'VS Code not found');
  }
}

// Test System Monitoring
async function testSystemMonitoring() {
  log('System Monitoring', 'INFO', 'Testing system APIs...');
  
  // Windsurf monitoring
  const r = await testAPI('Windsurf', 'http://localhost:3200/api/windsurf/status');
  log('Windsurf Monitoring', r.ok ? 'OK' : 'FAIL', r.ok ? 'Connected' : r.error);
  
  // System info
  const sys = await testAPI('System Info', 'http://localhost:3200/api/claude/desktop/system');
  log('System Information', sys.ok ? 'OK' : 'FAIL', sys.ok ? 'Connected' : sys.error);
  
  // Test file system access
  try {
    const testFile = path.join(os.tmpdir(), 'rudibot-test.txt');
    fs.writeFileSync(testFile, 'test');
    fs.unlinkSync(testFile);
    log('File System Access', 'OK', 'Read/Write permissions');
  } catch (e) {
    log('File System Access', 'FAIL', e.message);
  }
}

// Test Security Features
async function testSecurity() {
  log('Security Features', 'INFO', 'Testing security configurations...');
  
  // Check for environment variables
  const securityVars = [
    'FILE_SYSTEM_ACCESS_LEVEL',
    'ACCESS_CONTROL_ENABLED',
    'AUDIT_LOG_ENABLED',
    'FILE_ENCRYPTION_KEY'
  ];
  
  let configuredVars = 0;
  for (const varName of securityVars) {
    if (process.env[varName]) {
      configuredVars++;
    }
  }
  
  log('Security Configuration', configuredVars >= 2 ? 'OK' : 'SKIP', `${configuredVars}/${securityVars.length} variables configured`);
  
  // Test audit log directory
  const auditLogPath = process.env.AUDIT_LOG_PATH || path.join(__dirname, 'logs', 'audit.log');
  try {
    const auditDir = path.dirname(auditLogPath);
    fs.accessSync(auditDir, fs.constants.W_OK);
    log('Audit Log Directory', 'OK', 'Writable');
  } catch (e) {
    log('Audit Log Directory', 'FAIL', 'Not writable');
  }
}

// Main execution
async function main() {
  console.log('🔍 Testing Storage & System APIs...\n');
  
  await testInternalStorage();
  await testCloudStorage();
  await testNotesSystems();
  await testIDEIntegration();
  await testSystemMonitoring();
  await testSecurity();
  
  // Summary
  const ok = results.filter(r => r.status === 'OK').length;
  const fail = results.filter(r => r.status === 'FAIL').length;
  const skip = results.filter(r => r.status === 'SKIP').length;
  const info = results.filter(r => r.status === 'INFO').length;
  
  console.log('\n📊 SUMMARY');
  console.log(`✅ Working: ${ok}`);
  console.log(`❌ Failed: ${fail}`);
  console.log(`⚠️ Skipped: ${skip}`);
  console.log(`ℹ️ Info: ${info}`);
  console.log(`📈 Success Rate: ${ok > 0 ? Math.round((ok / (ok + fail)) * 100) : 0}%`);
  
  if (fail > 0) {
    console.log('\n❌ Failed Systems:');
    results.filter(r => r.status === 'FAIL').forEach(r => {
      console.log(`  - ${r.category}: ${r.message}`);
    });
  }
  
  if (skip > 0) {
    console.log('\n⚠️ Skipped Systems (no configuration):');
    results.filter(r => r.status === 'SKIP').forEach(r => {
      console.log(`  - ${r.category}`);
    });
  }
  
  console.log('\n🔧 Recommendations:');
  if (skip > 0) {
    console.log('  - Configure API keys in .env file for skipped services');
  }
  if (fail > 0) {
    console.log('  - Check server is running: node dev/server.js');
    console.log('  - Verify API configurations and permissions');
  }
  if (ok >= 10) {
    console.log('  - System is well configured! ✨');
  }
}

main().catch(console.error);
