(function () {
  'use strict';

  const FORM_SELECTORS = [
    'input[type="password"]',
    'input[name*="pass" i]',
    'input[id*="pass" i]',
    'input[autocomplete="current-password"]',
    'input[autocomplete="new-password"]'
  ];

  function detectPasswordForms() {
    const inputs = document.querySelectorAll(FORM_SELECTORS.join(', '));
    if (!inputs.length) return;

    inputs.forEach(pwInput => {
      const form = pwInput.closest('form');
      if (!form || form.dataset.pssInjected) return;
      form.dataset.pssInjected = 'true';

      const usernameInput = findUsernameInput(form, pwInput);
      injectAutofillButton(pwInput, usernameInput);
    });
  }

  function findUsernameInput(form, pwInput) {
    const candidates = form.querySelectorAll(
      'input[type="email"], input[type="text"], input[name*="user" i], input[name*="email" i], input[id*="user" i], input[id*="email" i], input[autocomplete="username"], input[autocomplete="email"]'
    );
    for (const c of candidates) {
      if (c !== pwInput) return c;
    }
    return null;
  }

  function injectAutofillButton(pwInput, userInput) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.textContent = '🔑';
    btn.title = 'Password Sync: Passwort auswählen';
    btn.style.cssText = `
      position: absolute;
      right: 8px;
      top: 50%;
      transform: translateY(-50%);
      background: #38bdf8;
      border: none;
      border-radius: 4px;
      color: #0f172a;
      cursor: pointer;
      font-size: 14px;
      padding: 2px 6px;
      z-index: 999999;
    `;

    const wrapper = document.createElement('div');
    wrapper.style.cssText = 'position: relative; display: inline-block; width: 100%;';
    pwInput.parentNode.insertBefore(wrapper, pwInput);
    wrapper.appendChild(pwInput);
    wrapper.appendChild(btn);

    btn.addEventListener('click', async (e) => {
      e.preventDefault();
      const domain = location.hostname;
      const matches = await chrome.runtime.sendMessage({ action: 'get-password-for-domain', domain });
      showPicker(matches, wrapper, userInput, pwInput);
    });
  }

  function showPicker(matches, wrapper, userInput, pwInput) {
    const existing = wrapper.querySelector('.pss-picker');
    if (existing) existing.remove();

    const picker = document.createElement('div');
    picker.className = 'pss-picker';
    picker.style.cssText = `
      position: absolute;
      top: calc(100% + 4px);
      left: 0;
      right: 0;
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 8px;
      padding: 8px;
      z-index: 9999999;
      max-height: 200px;
      overflow-y: auto;
      box-shadow: 0 10px 30px rgba(0,0,0,.4);
    `;

    if (!matches || !matches.length) {
      picker.innerHTML = '<div style="color:#94a3b8;font-size:12px;padding:8px;">Keine Passwörter für diese Seite.</div>';
    } else {
      matches.forEach(m => {
        const row = document.createElement('div');
        row.style.cssText = `
          padding: 8px;
          border-radius: 6px;
          cursor: pointer;
          color: #e2e8f0;
          font-size: 13px;
          margin-bottom: 4px;
        `;
        row.innerHTML = `<div style="font-weight:600;">${escapeHtml(m.url)}</div><div style="color:#94a3b8;font-size:11px;">${escapeHtml(m.username)}</div>`;
        row.addEventListener('mouseenter', () => row.style.background = '#334155');
        row.addEventListener('mouseleave', () => row.style.background = 'transparent');
        row.addEventListener('click', () => {
          if (userInput) userInput.value = m.username;
          pwInput.value = m.password;
          picker.remove();
          pwInput.dispatchEvent(new Event('input', { bubbles: true }));
        });
        picker.appendChild(row);
      });
    }

    wrapper.appendChild(picker);
    const close = (ev) => { if (!wrapper.contains(ev.target)) picker.remove(); };
    document.addEventListener('click', close, { once: true });
  }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = String(str ?? '');
    return div.innerHTML;
  }

  // Initial + MutationObserver
  detectPasswordForms();
  const observer = new MutationObserver(() => detectPasswordForms());
  observer.observe(document.body, { childList: true, subtree: true });
})();
