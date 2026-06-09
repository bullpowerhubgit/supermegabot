// RudiBot Browser Extension — Background Service Worker
// Verbindet sich mit dem lokalen Bot-Server auf Port 3200/8888

const BOT_PORTS = [3200, 8888, 3000];
let activeBotPort = null;
let botConnected = false;

// ── Bot-Server finden ─────────────────────────────────────────────────────────
async function findBotServer() {
    for (const port of BOT_PORTS) {
        try {
            const resp = await fetch(`http://localhost:${port}/api/status`, { signal: AbortSignal.timeout(2000) });
            if (resp.ok) {
                activeBotPort = port;
                botConnected = true;
                console.log(`✅ RudiBot gefunden auf Port ${port}`);
                return port;
            }
        } catch {}
    }
    botConnected = false;
    activeBotPort = null;
    return null;
}

// ── Beim Start verbinden ──────────────────────────────────────────────────────
findBotServer();
setInterval(findBotServer, 30000); // Alle 30s neu prüfen

// ── Context Menu einrichten ───────────────────────────────────────────────────
chrome.runtime.onInstalled.addListener(() => {
    chrome.contextMenus.create({
        id: 'rudibot-ask',
        title: 'RudiBot: "%s" analysieren',
        contexts: ['selection']
    });
    chrome.contextMenus.create({
        id: 'rudibot-page',
        title: 'RudiBot: Diese Seite analysieren',
        contexts: ['page']
    });
    chrome.contextMenus.create({
        id: 'rudibot-separator',
        type: 'separator',
        contexts: ['selection', 'page']
    });
    chrome.contextMenus.create({
        id: 'rudibot-shopify',
        title: 'RudiBot: Shopify Dashboard öffnen',
        contexts: ['page']
    });
    console.log('✅ RudiBot Context Menus erstellt');
});

// ── Context Menu Klick Handler ────────────────────────────────────────────────
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
    if (info.menuItemId === 'rudibot-ask' && info.selectionText) {
        await sendToBot(`Analysiere diesen Text von der Website "${tab.url}": "${info.selectionText}"`);
    } else if (info.menuItemId === 'rudibot-page') {
        await sendToBot(`Analysiere diese Website und gib mir wichtige Infos: ${tab.url}`);
    } else if (info.menuItemId === 'rudibot-shopify') {
        chrome.tabs.create({ url: `http://localhost:${activeBotPort || 3200}/` });
    }
});

// ── Message Handler (von Content Script und Popup) ───────────────────────────
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === 'GET_STATUS') {
        sendResponse({ connected: botConnected, port: activeBotPort });
        return true;
    }

    if (message.type === 'SEND_MESSAGE') {
        sendToBot(message.text, message.context).then(result => {
            sendResponse(result);
        });
        return true; // async response
    }

    if (message.type === 'GET_PAGE_INFO') {
        // Tab-Infos an Content Script senden
        sendResponse({ url: sender.tab?.url, title: sender.tab?.title });
        return true;
    }

    if (message.type === 'OPEN_DASHBOARD') {
        chrome.tabs.create({ url: `http://localhost:${activeBotPort || 3200}/` });
        sendResponse({ ok: true });
        return true;
    }

    if (message.type === 'QUICK_COMMAND') {
        executeQuickCommand(message.command, message.tabUrl).then(r => sendResponse(r));
        return true;
    }
});

// ── Bot API aufrufen ──────────────────────────────────────────────────────────
async function sendToBot(text, context = '') {
    if (!activeBotPort) {
        await findBotServer();
        if (!activeBotPort) return { error: 'RudiBot nicht erreichbar. Ist der Server gestartet?' };
    }

    try {
        const body = { message: text };
        if (context) body.context = context;

        const resp = await fetch(`http://localhost:${activeBotPort}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
            signal: AbortSignal.timeout(30000)
        });

        if (resp.ok) {
            const data = await resp.json();
            return { success: true, reply: data.reply || data.message || data.text || JSON.stringify(data) };
        }
        return { error: `Server Fehler: ${resp.status}` };
    } catch (e) {
        return { error: e.message };
    }
}

// ── Quick Commands ────────────────────────────────────────────────────────────
async function executeQuickCommand(command, tabUrl) {
    const commands = {
        'status': () => sendToBot('/status'),
        'shopify': () => sendToBot('/shopify'),
        'social': () => sendToBot('/social'),
        'income': () => sendToBot('/income'),
        'analyze_page': () => sendToBot(`Analysiere diese Seite: ${tabUrl}`),
        'post_product': () => sendToBot('/autopost'),
    };

    const fn = commands[command];
    if (fn) return await fn();
    return { error: 'Unbekannter Command' };
}

// ── Notifications anzeigen ────────────────────────────────────────────────────
async function showNotification(title, message) {
    chrome.notifications.create({
        type: 'basic',
        iconUrl: 'icons/icon48.png',
        title: title,
        message: message
    });
}

export { sendToBot, findBotServer };
