document.addEventListener('DOMContentLoaded', async () => {
  const landing = document.getElementById('view-landing');
  const dashboard = document.getElementById('view-dashboard');
  const nav = document.getElementById('nav');

  // Check session
  try {
    const res = await fetch('/api/me');
    if (res.ok) {
      const user = await res.json();
      showDashboard(user);
    } else {
      showLanding();
    }
  } catch {
    showLanding();
  }

  function showLanding() {
    landing.classList.remove('hidden');
    dashboard.classList.add('hidden');
    nav.innerHTML = '<a href="/auth/google">Anmelden</a>';
  }

  async function showDashboard(user) {
    landing.classList.add('hidden');
    dashboard.classList.remove('hidden');
    nav.innerHTML = `<a href="/auth/logout">Abmelden (${escapeHtml(user.email)})</a>`;

    document.getElementById('user-pill').innerHTML = `
      ${user.photo ? `<img src="${escapeHtml(user.photo)}" alt="" />` : ''}
      <span>${escapeHtml(user.name || user.email)}</span>
    `;

    // Load accounts
    const accRes = await fetch('/api/accounts');
    const accounts = accRes.ok ? await accRes.json() : [];
    document.getElementById('accounts-grid').innerHTML = accounts.map(a => `
      <div class="account-row">
        <div>
          <div style="font-weight:600;">${escapeHtml(a.name)}</div>
          <div style="color:var(--text-2);font-size:12px;">${escapeHtml(a.email)}</div>
        </div>
        <span class="status ${a.connected ? 'connected' : 'pending'}">
          ${a.connected ? 'Verbunden' : 'Nicht verbunden'}
        </span>
      </div>
    `).join('');

    // Load dashboard stats
    const dashRes = await fetch('/api/dashboard');
    const dash = dashRes.ok ? await dashRes.json() : { totalPasswords: 0, clients: 0 };
    document.getElementById('sync-stats').innerHTML = `
      <div class="stat">Gespeicherte Passwörter: <span class="val">${dash.totalPasswords}</span></div>
      <div class="stat">Verbundene Browser: <span class="val">${dash.clients}</span></div>
    `;

    // Load password table
    const tbody = document.querySelector('#passwords-table tbody');
    tbody.innerHTML = '';
    // Note: server doesn't expose actual passwords, only metadata
    const allPw = [];
    // Extension sync data not directly exposed; fill with placeholder for UI
    if (!dash.totalPasswords) {
      tbody.innerHTML = '<tr><td colspan="3" style="color:var(--text-2)">Noch keine Passwörter synchronisiert.</td></tr>';
    } else {
      tbody.innerHTML = '<tr><td colspan="3" style="color:var(--text-2)">Passwörter werden über die Extension synchronisiert.</td></tr>';
    }
  }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = String(str ?? '');
    return div.innerHTML;
  }
});
