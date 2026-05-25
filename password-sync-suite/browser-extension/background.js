chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.set({
    accounts: [],
    passwords: [],
    syncEndpoint: 'http://localhost:3005/api/sync',
    lastSync: null
  });
  console.log('[Password Sync] Extension installiert.');
});

chrome.alarms.create('auto-sync', { periodInMinutes: 15 });

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === 'auto-sync') {
    await performSync();
  }
});

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'sync-to-server') {
    performSync().then(sendResponse).catch(e => sendResponse({ ok: false, error: e.message }));
    return true;
  }
  if (request.action === 'get-password-for-domain') {
    getPasswordForDomain(request.domain).then(sendResponse);
    return true;
  }
});

async function performSync() {
  try {
    const { passwords, accounts, syncEndpoint } = await chrome.storage.local.get([
      'passwords', 'accounts', 'syncEndpoint'
    ]);

    const payload = {
      clientId: await getClientId(),
      accounts: accounts.map(a => ({ email: a.email, linkedAt: a.linkedAt })),
      passwords: passwords.map(p => ({ url: p.url, username: p.username, createdAt: p.createdAt })),
      timestamp: Date.now()
    };

    const res = await fetch(syncEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    await chrome.storage.local.set({ lastSync: Date.now() });
    return { ok: true };
  } catch (err) {
    console.error('[Password Sync] Sync fehlgeschlagen:', err);
    return { ok: false, error: err.message };
  }
}

async function getPasswordForDomain(domain) {
  const { passwords = [] } = await chrome.storage.local.get('passwords');
  return passwords.filter(p => p.url.includes(domain));
}

async function getClientId() {
  let { clientId } = await chrome.storage.local.get('clientId');
  if (!clientId) {
    clientId = crypto.randomUUID();
    await chrome.storage.local.set({ clientId });
  }
  return clientId;
}
