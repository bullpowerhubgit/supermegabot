#!/usr/bin/env node
import { spawn } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';
import os from 'os';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const isMac = os.platform() === 'darwin';
const isLinux = os.platform() === 'linux';

function openBrowser(url) {
  const cmd = isMac ? 'open' : isLinux ? 'xdg-open' : 'start';
  spawn(cmd, [url], { detached: true, stdio: 'ignore' });
}

function log(msg) {
  console.log(`[dashboard-cli] ${msg}`);
}

async function main() {
  log('=== Mega Dashboard CLI ===');
  log('Starting backend (super-server) and frontend...');

  const superServerPath = '/Users/rudolfsarkany/supermegabot-windsurf-agents/CascadeProjects/windsurf-project/super-server.js';

  const serverProc = spawn('/opt/homebrew/bin/node', [superServerPath], {
    detached: false,
    stdio: 'pipe',
  });

  let serverReady = false;
  serverProc.stdout.on('data', (data) => {
    const text = data.toString().trim();
    if (text) console.log(`[super-server] ${text}`);
    if (text.includes('Super Server running') || text.includes('port 9001')) {
      serverReady = true;
    }
  });

  serverProc.stderr.on('data', (data) => {
    const text = data.toString().trim();
    if (text) console.error(`[super-server] ${text}`);
  });

  await new Promise((resolve) => setTimeout(resolve, 2000));

  log('Starting Vite dev server...');
  const viteProc = spawn('npx', ['vite', '--port', '5173', '--host'], {
    cwd: __dirname,
    detached: false,
    stdio: 'pipe',
  });

  let viteReady = false;
  viteProc.stdout.on('data', (data) => {
    const text = data.toString().trim();
    if (text) console.log(`[vite] ${text}`);
    if (text.includes('Local:') || text.includes('http://localhost:5173')) {
      viteReady = true;
    }
  });

  viteProc.stderr.on('data', (data) => {
    const text = data.toString().trim();
    if (text) console.error(`[vite] ${text}`);
  });

  log('Waiting for servers to be ready...');
  let attempts = 0;
  while ((!serverReady || !viteReady) && attempts < 30) {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    attempts++;
  }

  const url = 'http://localhost:5173';
  log(`Opening browser: ${url}`);
  openBrowser(url);

  log('');
  log('Dashboard is running!');
  log('  Frontend: http://localhost:5173');
  log('  Backend:  http://localhost:9001/api/status');
  log('');
  log('Press Ctrl+C to stop both servers.');

  process.on('SIGINT', () => {
    log('Shutting down...');
    serverProc.kill();
    viteProc.kill();
    process.exit(0);
  });

  process.on('SIGTERM', () => {
    serverProc.kill();
    viteProc.kill();
    process.exit(0);
  });
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
