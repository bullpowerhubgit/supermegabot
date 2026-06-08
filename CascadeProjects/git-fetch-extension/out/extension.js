"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const child_process = __importStar(require("child_process"));
const util = __importStar(require("util"));
const path = __importStar(require("path"));
const fs = __importStar(require("fs"));
const exec = util.promisify(child_process.exec);
let statusBarItem;
let fetchInterval = null;
let isRunning = false;
let lastFetchTime = null;
let gitRepos = [];
function activate(context) {
    // Create status bar item
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.command = 'gitFetchExtension.manual';
    context.subscriptions.push(statusBarItem);
    // Register commands
    context.subscriptions.push(vscode.commands.registerCommand('gitFetchExtension.start', startAutoFetch));
    context.subscriptions.push(vscode.commands.registerCommand('gitFetchExtension.stop', stopAutoFetch));
    context.subscriptions.push(vscode.commands.registerCommand('gitFetchExtension.manual', manualFetch));
    // Listen for configuration changes
    context.subscriptions.push(vscode.workspace.onDidChangeConfiguration(onConfigurationChange));
    // Listen for workspace folder changes
    context.subscriptions.push(vscode.workspace.onDidChangeWorkspaceFolders(onWorkspaceChange));
    // Initial scan and start if enabled
    scanForGitRepos().then(() => {
        const config = vscode.workspace.getConfiguration('gitFetchExtension');
        const enabled = config.get('enabled', true);
        if (enabled && gitRepos.length > 0) {
            startAutoFetch();
        }
        else {
            updateStatusBar('ready');
        }
    });
}
function deactivate() {
    stopAutoFetch();
}
async function scanForGitRepos() {
    gitRepos = [];
    if (!vscode.workspace.workspaceFolders || vscode.workspace.workspaceFolders.length === 0) {
        return;
    }
    const repoPromises = vscode.workspace.workspaceFolders.map(async (folder) => {
        const gitRoot = await findGitRoot(folder.uri.fsPath);
        if (gitRoot && !gitRepos.includes(gitRoot)) {
            const isValid = await verifyGitRepo(gitRoot);
            if (isValid) {
                gitRepos.push(gitRoot);
            }
        }
    });
    await Promise.all(repoPromises);
}
async function findGitRoot(dir) {
    try {
        // Check if current directory has .git
        const gitPath = path.join(dir, '.git');
        const stat = await fs.promises.stat(gitPath);
        if (stat.isDirectory()) {
            return dir;
        }
    }
    catch {
        // .git not found in this directory
    }
    return null;
}
async function verifyGitRepo(repoPath) {
    try {
        const { stdout, stderr } = await exec('git status --porcelain', { cwd: repoPath });
        // If git status runs without error, it's a valid git repo
        return true;
    }
    catch (error) {
        return false;
    }
}
async function startAutoFetch() {
    if (isRunning) {
        vscode.window.showInformationMessage('Git Fetch is already running');
        return;
    }
    // Re-scan for repos in case workspace changed
    await scanForGitRepos();
    if (gitRepos.length === 0) {
        vscode.window.showWarningMessage('No git repositories found in workspace');
        updateStatusBar('ready');
        return;
    }
    isRunning = true;
    updateStatusBar('running');
    const config = vscode.workspace.getConfiguration('gitFetchExtension');
    const interval = config.get('interval', 300000);
    // Run initial fetch
    await runGitFetch();
    // Set up periodic fetch
    fetchInterval = setInterval(async () => {
        if (isRunning) {
            await runGitFetch();
        }
    }, interval);
    vscode.window.showInformationMessage(`Git Fetch started - monitoring ${gitRepos.length} repository(s)`);
}
function stopAutoFetch() {
    if (!isRunning && !fetchInterval) {
        vscode.window.showInformationMessage('Git Fetch is not currently running');
        return;
    }
    isRunning = false;
    if (fetchInterval) {
        clearInterval(fetchInterval);
        fetchInterval = null;
    }
    updateStatusBar('stopped');
    vscode.window.showInformationMessage('Git Fetch stopped');
}
async function manualFetch() {
    // Re-scan for repos
    await scanForGitRepos();
    if (gitRepos.length === 0) {
        vscode.window.showWarningMessage('No git repositories found in workspace');
        return;
    }
    const wasRunning = isRunning;
    // Temporarily show running state
    const prevStatus = statusBarItem.text;
    statusBarItem.text = '$(sync~spin) Git Fetch Running...';
    statusBarItem.tooltip = 'Running manual git fetch...';
    await runGitFetch();
    // Restore status
    if (wasRunning) {
        updateStatusBar('running');
    }
    else {
        updateStatusBar('ready');
    }
}
async function runGitFetch() {
    const config = vscode.workspace.getConfiguration('gitFetchExtension');
    const showNotifications = config.get('showNotifications', true);
    let successCount = 0;
    let errorCount = 0;
    const errors = [];
    for (const repo of gitRepos) {
        try {
            await exec('git fetch --all', { cwd: repo });
            successCount++;
        }
        catch (error) {
            errorCount++;
            const repoName = path.basename(repo);
            errors.push(`${repoName}: ${error.message || 'Unknown error'}`);
        }
    }
    lastFetchTime = new Date();
    if (showNotifications) {
        if (errorCount === 0) {
            vscode.window.showInformationMessage(`Git Fetch completed: ${successCount} repository(s) updated`);
        }
        else if (successCount === 0) {
            vscode.window.showErrorMessage(`Git Fetch failed for all ${errorCount} repository(s)`);
        }
        else {
            vscode.window.showWarningMessage(`Git Fetch: ${successCount} success, ${errorCount} failed`);
        }
    }
    updateStatusBar('completed', successCount, errorCount);
}
function updateStatusBar(state, successCount, errorCount) {
    if (gitRepos.length === 0) {
        statusBarItem.text = '$(sync) Git Fetch';
        statusBarItem.tooltip = 'No git repositories found';
        statusBarItem.show();
        return;
    }
    switch (state) {
        case 'ready':
            statusBarItem.text = `$(sync) Git Fetch (${gitRepos.length} repos)`;
            statusBarItem.tooltip = 'Click to run manual git fetch';
            break;
        case 'running':
            statusBarItem.text = `$(sync~spin) Git Fetch Running (${gitRepos.length} repos)`;
            statusBarItem.tooltip = 'Automatic git fetch is active. Click to run manual fetch.';
            break;
        case 'completed':
            const timeStr = lastFetchTime ? formatTime(lastFetchTime) : '';
            let statusText = '';
            if (errorCount && errorCount > 0) {
                statusText = `${successCount}✓ ${errorCount}✗`;
            }
            else {
                statusText = `${gitRepos.length} repos`;
            }
            statusBarItem.text = `$(sync) Git Fetch (${timeStr}) - ${statusText}`;
            statusBarItem.tooltip = `Last fetch: ${lastFetchTime?.toLocaleString()}. Click to run manual fetch.`;
            break;
        case 'stopped':
            statusBarItem.text = `$(sync) Git Fetch (${gitRepos.length} repos) - Stopped`;
            statusBarItem.tooltip = 'Git fetch stopped. Click to run manual fetch.';
            break;
    }
    statusBarItem.show();
}
function formatTime(date) {
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    if (diff < 60000) {
        return 'just now';
    }
    else if (diff < 3600000) {
        const mins = Math.floor(diff / 60000);
        return `${mins}m ago`;
    }
    else {
        const hours = Math.floor(diff / 3600000);
        return `${hours}h ago`;
    }
}
async function onConfigurationChange(event) {
    if (event.affectsConfiguration('gitFetchExtension')) {
        const config = vscode.workspace.getConfiguration('gitFetchExtension');
        const enabled = config.get('enabled', true);
        // If interval changed while running, restart
        if (event.affectsConfiguration('gitFetchExtension.interval') && isRunning) {
            stopAutoFetch();
            if (enabled) {
                await startAutoFetch();
            }
        }
        // If enabled changed
        if (event.affectsConfiguration('gitFetchExtension.enabled')) {
            if (enabled && !isRunning) {
                await startAutoFetch();
            }
            else if (!enabled && isRunning) {
                stopAutoFetch();
            }
        }
    }
}
async function onWorkspaceChange(event) {
    // Re-scan when workspace changes
    await scanForGitRepos();
    // Update status bar
    if (isRunning) {
        updateStatusBar('running');
    }
    else {
        updateStatusBar('ready');
    }
    const added = event.added.length;
    const removed = event.removed.length;
    if (added > 0 || removed > 0) {
        vscode.window.showInformationMessage(`Workspace updated: ${added} folder(s) added, ${removed} folder(s) removed. Found ${gitRepos.length} git repo(s).`);
    }
}
//# sourceMappingURL=extension.js.map