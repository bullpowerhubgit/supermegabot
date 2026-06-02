document.addEventListener('DOMContentLoaded', () => {
  const $ = (id) => document.getElementById(id);
  const statusBadge = $('sync-status');
  const accountsList = $('accounts-list');
  const passwordsList = $('passwords-list');

  const ACCOUNTS = [
    { email: 'dragonadnp@gmail.com', name: 'DragonADNP' },
    { email: 'aiitecbuuss@gmail.com', name: 'AiitecBuuss' },
    { email: 'bullpowersrtkennels@gmail.com', name: 'BullPowerSRT' }
  ];

  function setStatus(text, type = 'ready') {
    statusBadge.textContent = text;
    statusBadge.className = 'badge' + (type === 'syncing' ? ' syncing' : type === 'error' ? ' error' : '');
  }

  async function loadData() {
    const { accounts = [], passwords = [] } = await chrome.storage.local.get(['accounts', 'passwords']);

    // Render accounts
    const storedEmails = new Set(accounts.map(a => a.email));
    accountsList.innerHTML = ACCOUNTS.map(acc => {
      const isLinked = storedEmails.has(acc.email);
      return `
        <div class="item">
          <div>
            <div>${escapeHtml(acc.name)}</div>
            <div class="meta">${escapeHtml(acc.email)} ${isLinked ? '✓ verbunden' : ''}</div>
          </div>
          <div class="actions">
            <button data-email="${escapeHtml(acc.email)}" class="btn-toggle">${isLinked ? 'Trennen' : 'Verbinden'}</button>
          </div>
        </div>
      `;
    }).join('');

    accountsList.querySelectorAll('.btn-toggle').forEach(btn => {
      btn.addEventListener('click', () => toggleAccount(btn.dataset.email));
    });

    // Render passwords
    if (!passwords.length) {
      passwordsList.innerHTML = '<div class="empty">Noch keine Passwörter gespeichert.</div>';
    } else {
      passwordsList.innerHTML = passwords.map((p, i) => `
        <div class="item">
          <div>
            <div>${escapeHtml(p.url)}</div>
            <div class="meta">${escapeHtml(p.username)}</div>
          </div>
          <div class="actions">
            <button data-idx="${i}" class="btn-copy">Kopieren</button>
            <button data-idx="${i}" class="btn-delete">Löschen</button>
          </div>
        </div>
      `).join('');

      passwordsList.querySelectorAll('.btn-copy').forEach(btn => {
        btn.addEventListener('click', () => copyPassword(Number(btn.dataset.idx)));
      });
      passwordsList.querySelectorAll('.btn-delete').forEach(btn => {
        btn.addEventListener('click', () => deletePassword(Number(btn.dataset.idx)));
      });
    }
  }

  async function toggleAccount(email) {
    setStatus('Authentifiziere...', 'syncing');
    try {
      const { accounts = [] } = await chrome.storage.local.get('accounts');
      const idx = accounts.findIndex(a => a.email === email);
      if (idx >= 0) {
        accounts.splice(idx, 1);
        await chrome.storage.local.set({ accounts });
        setStatus('Bereit');
        loadData();
      } else {
        // Öffne Web-App OAuth-Flow in neuem Tab
        chrome.tabs.create({ url: 'http://localhost:3005/auth/google' });
        setStatus('Login im Browser...');
        setTimeout(() => setStatus('Bereit'), 2000);
      }
    } catch (e) {
      setStatus('Fehler', 'error');
      console.error(e);
    }
  }

  async function copyPassword(idx) {
    const { passwords = [] } = await chrome.storage.local.get('passwords');
    const p = passwords[idx];
    if (p) {
      const ta = document.createElement('textarea');
      ta.value = p.password;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      setStatus('Kopiert!');
      setTimeout(() => setStatus('Bereit'), 1200);
    }
  }

  async function deletePassword(idx) {
    const { passwords = [] } = await chrome.storage.local.get('passwords');
    passwords.splice(idx, 1);
    await chrome.storage.local.set({ passwords });
    loadData();
  }

  async function syncNow() {
    setStatus('Synchronisiere...', 'syncing');
    try {
      // Demo: Sende an Web-App
      await chrome.runtime.sendMessage({ action: 'sync-to-server' });
      setStatus('Synchronisiert');
      setTimeout(() => setStatus('Bereit'), 1500);
    } catch (e) {
      setStatus('Sync-Fehler', 'error');
    }
  }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = String(str ?? '');
    return div.innerHTML;
  }

  $('btn-add-password').addEventListener('click', () => {
    $('add-password-form').classList.remove('hidden');
    $('passwords-section').classList.add('hidden');
  });

  $('btn-cancel').addEventListener('click', () => {
    $('add-password-form').classList.add('hidden');
    $('passwords-section').classList.remove('hidden');
  });

  $('btn-save-password').addEventListener('click', async () => {
    const url = $('inp-url').value.trim();
    const username = $('inp-username').value.trim();
    const password = $('inp-password').value;
    if (!url || !password) return;

    const { passwords = [] } = await chrome.storage.local.get('passwords');
    passwords.push({ url, username, password, createdAt: Date.now() });
    await chrome.storage.local.set({ passwords });

    $('inp-url').value = '';
    $('inp-username').value = '';
    $('inp-password').value = '';
    $('add-password-form').classList.add('hidden');
    $('passwords-section').classList.remove('hidden');
    loadData();
  });

  $('btn-sync-now').addEventListener('click', syncNow);
  $('btn-open-web').addEventListener('click', () => {
    chrome.tabs.create({ url: 'http://localhost:3005' });
  });

  $('btn-add-account').addEventListener('click', () => {
    chrome.tabs.create({ url: 'http://localhost:3005/auth/google' });
  });

  loadData();
});
