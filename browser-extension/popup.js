// RudiBot Popup Script
document.addEventListener('DOMContentLoaded', () => {
    const statusBadge = document.getElementById('status-badge');
    const statusText = document.getElementById('status-text');
    const messages = document.getElementById('messages');
    const chatInput = document.getElementById('chat-input');
    const sendBtn = document.getElementById('send-btn');
    const replyResult = document.getElementById('reply-result');

    // ── Status prüfen ─────────────────────────────────────────────────────────
    function checkStatus() {
        chrome.runtime.sendMessage({ type: 'GET_STATUS' }, (response) => {
            if (chrome.runtime.lastError) {
                setStatus(false, 'Fehler');
                return;
            }
            if (response?.connected) {
                setStatus(true, `Online · Port ${response.port}`);
            } else {
                setStatus(false, 'Server offline');
            }
        });
    }

    function setStatus(online, text) {
        statusBadge.className = online ? 'status-online' : 'status-offline';
        statusText.textContent = text;
    }

    checkStatus();
    setInterval(checkStatus, 10000);

    // ── Quick Buttons ─────────────────────────────────────────────────────────
    document.querySelectorAll('.qbtn').forEach(btn => {
        btn.addEventListener('click', () => {
            const cmd = btn.dataset.cmd;
            addMsg('user', btn.textContent.trim());
            btn.disabled = true;

            // Aktive Tab-URL holen
            chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
                const tabUrl = tabs[0]?.url || '';
                chrome.runtime.sendMessage(
                    { type: 'QUICK_COMMAND', command: cmd, tabUrl },
                    (response) => {
                        btn.disabled = false;
                        if (response?.reply) addMsg('bot', response.reply);
                        else if (response?.error) addMsg('bot', '❌ ' + response.error);
                    }
                );
            });
        });
    });

    // ── Chat senden ───────────────────────────────────────────────────────────
    function sendMessage() {
        const text = chatInput.value.trim();
        if (!text) return;
        addMsg('user', text);
        chatInput.value = '';

        chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
            const context = tabs[0] ? `Aktuelle Seite: ${tabs[0].title} (${tabs[0].url})` : '';
            addTyping();
            chrome.runtime.sendMessage(
                { type: 'SEND_MESSAGE', text, context },
                (response) => {
                    removeTyping();
                    if (response?.reply) addMsg('bot', response.reply);
                    else if (response?.error) addMsg('bot', '❌ ' + response.error);
                }
            );
        });
    }

    sendBtn.addEventListener('click', sendMessage);
    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') sendMessage();
    });

    // ── Dashboard öffnen ──────────────────────────────────────────────────────
    document.getElementById('open-dashboard').addEventListener('click', () => {
        chrome.runtime.sendMessage({ type: 'OPEN_DASHBOARD' });
        window.close();
    });

    // ── Helpers ───────────────────────────────────────────────────────────────
    function addMsg(type, text) {
        const typing = document.getElementById('rb-typing-popup');
        if (typing) typing.remove();

        const div = document.createElement('div');
        div.className = `msg ${type}`;
        const clean = text.replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>');
        div.innerHTML = `<span class="msg-icon">${type === 'bot' ? '🤖' : '👤'}</span><div class="msg-bubble">${clean}</div>`;
        messages.appendChild(div);
        messages.scrollTop = messages.scrollHeight;
    }

    function addTyping() {
        const div = document.createElement('div');
        div.className = 'msg';
        div.id = 'rb-typing-popup';
        div.innerHTML = `<span class="msg-icon">🤖</span><div class="msg-bubble"><div class="typing"><span></span><span></span><span></span></div></div>`;
        messages.appendChild(div);
        messages.scrollTop = messages.scrollHeight;
    }

    function removeTyping() {
        const t = document.getElementById('rb-typing-popup');
        if (t) t.remove();
    }
});
