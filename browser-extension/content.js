// RudiBot Content Script — Floating Assistant Widget
// Wird auf JEDER Website injiziert

(function() {
    'use strict';

    // Nicht doppelt injizieren
    if (document.getElementById('rudibot-widget')) return;
    // Nicht auf Bot-eigenen Seiten
    if (window.location.hostname === 'localhost') return;

    // ── Widget HTML erstellen ─────────────────────────────────────────────────
    const widgetContainer = document.createElement('div');
    widgetContainer.id = 'rudibot-widget';
    widgetContainer.innerHTML = `
        <div id="rudibot-fab" title="RudiBot Assistant öffnen">
            <div class="rudibot-fab-icon">
                <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
                    <circle cx="14" cy="14" r="13" fill="url(#rbGrad)" stroke="rgba(255,255,255,0.3)" stroke-width="1"/>
                    <text x="14" y="19" text-anchor="middle" font-size="14" fill="white">🤖</text>
                    <defs>
                        <linearGradient id="rbGrad" x1="0" y1="0" x2="28" y2="28">
                            <stop offset="0%" stop-color="#6366f1"/>
                            <stop offset="100%" stop-color="#8b5cf6"/>
                        </linearGradient>
                    </defs>
                </svg>
            </div>
            <div id="rudibot-status-dot" class="status-offline"></div>
        </div>

        <div id="rudibot-panel" class="rudibot-hidden">
            <div id="rudibot-header">
                <div class="rudibot-title">
                    <span class="rudibot-logo">🤖</span>
                    <div>
                        <div class="rudibot-name">RudiBot</div>
                        <div id="rudibot-status-text" class="rudibot-status">Verbinde...</div>
                    </div>
                </div>
                <div class="rudibot-header-btns">
                    <button id="rudibot-dashboard-btn" title="Dashboard öffnen">⬡</button>
                    <button id="rudibot-close-btn" title="Schließen">✕</button>
                </div>
            </div>

            <div id="rudibot-quick-btns">
                <button class="rb-qbtn" data-cmd="status">📊 Status</button>
                <button class="rb-qbtn" data-cmd="shopify">🛒 Shop</button>
                <button class="rb-qbtn" data-cmd="social">📱 Social</button>
                <button class="rb-qbtn" data-cmd="income">💰 Income</button>
                <button class="rb-qbtn" data-cmd="analyze_page">🔍 Seite</button>
            </div>

            <div id="rudibot-messages">
                <div class="rb-message rb-bot">
                    <span class="rb-avatar">🤖</span>
                    <div class="rb-bubble">Hallo! Ich bin RudiBot. Was kann ich für dich tun?</div>
                </div>
            </div>

            <div id="rudibot-input-area">
                <input id="rudibot-input" type="text" placeholder="Frage stellen..." autocomplete="off"/>
                <button id="rudibot-send-btn">▶</button>
            </div>

            <div id="rudibot-page-info">
                <span id="rudibot-page-domain"></span>
            </div>
        </div>
    `;

    document.body.appendChild(widgetContainer);

    // ── State ─────────────────────────────────────────────────────────────────
    let isOpen = false;
    let isConnected = false;
    let isLoading = false;

    const fab = document.getElementById('rudibot-fab');
    const panel = document.getElementById('rudibot-panel');
    const statusDot = document.getElementById('rudibot-status-dot');
    const statusText = document.getElementById('rudibot-status-text');
    const messages = document.getElementById('rudibot-messages');
    const input = document.getElementById('rudibot-input');
    const sendBtn = document.getElementById('rudibot-send-btn');

    // ── Connection Status prüfen ───────────────────────────────────────────────
    function checkStatus() {
        chrome.runtime.sendMessage({ type: 'GET_STATUS' }, (response) => {
            if (chrome.runtime.lastError) return;
            if (response) {
                isConnected = response.connected;
                if (isConnected) {
                    statusDot.className = 'status-online';
                    statusText.textContent = `Online · Port ${response.port}`;
                } else {
                    statusDot.className = 'status-offline';
                    statusText.textContent = 'Offline — Server starten';
                }
            }
        });
    }

    checkStatus();
    setInterval(checkStatus, 15000);

    // ── Page Domain anzeigen ──────────────────────────────────────────────────
    const domainEl = document.getElementById('rudibot-page-domain');
    if (domainEl) domainEl.textContent = '🌐 ' + window.location.hostname;

    // ── FAB Click ─────────────────────────────────────────────────────────────
    fab.addEventListener('click', () => {
        isOpen = !isOpen;
        panel.classList.toggle('rudibot-hidden', !isOpen);
        if (isOpen) {
            input.focus();
            checkStatus();
        }
    });

    // ── Close Button ──────────────────────────────────────────────────────────
    document.getElementById('rudibot-close-btn').addEventListener('click', () => {
        isOpen = false;
        panel.classList.add('rudibot-hidden');
    });

    // ── Dashboard Button ─────────────────────────────────────────────────────
    document.getElementById('rudibot-dashboard-btn').addEventListener('click', () => {
        chrome.runtime.sendMessage({ type: 'OPEN_DASHBOARD' });
    });

    // ── Quick Buttons ─────────────────────────────────────────────────────────
    document.querySelectorAll('.rb-qbtn').forEach(btn => {
        btn.addEventListener('click', () => {
            const cmd = btn.dataset.cmd;
            addMessage('user', btn.textContent.trim());
            btn.disabled = true;
            chrome.runtime.sendMessage(
                { type: 'QUICK_COMMAND', command: cmd, tabUrl: window.location.href },
                (response) => {
                    btn.disabled = false;
                    if (response?.reply) addMessage('bot', response.reply);
                    else if (response?.error) addMessage('bot', '❌ ' + response.error);
                }
            );
        });
    });

    // ── Nachricht senden ──────────────────────────────────────────────────────
    function sendMessage() {
        const text = input.value.trim();
        if (!text || isLoading) return;

        addMessage('user', text);
        input.value = '';
        setLoading(true);

        // Seiten-Kontext mitschicken
        const context = `Aktuelle Seite: ${document.title} (${window.location.href})`;

        chrome.runtime.sendMessage(
            { type: 'SEND_MESSAGE', text, context },
            (response) => {
                setLoading(false);
                if (response?.reply) addMessage('bot', response.reply);
                else if (response?.error) addMessage('bot', '❌ ' + response.error);
                else addMessage('bot', '❓ Keine Antwort vom Server');
            }
        );
    }

    sendBtn.addEventListener('click', sendMessage);
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
    });

    // ── Message anzeigen ─────────────────────────────────────────────────────
    function addMessage(type, text) {
        const div = document.createElement('div');
        div.className = `rb-message rb-${type}`;

        // Markdown basic rendering
        const formatted = text
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`(.*?)`/g, '<code>$1</code>')
            .replace(/\n/g, '<br>');

        div.innerHTML = `
            <span class="rb-avatar">${type === 'bot' ? '🤖' : '👤'}</span>
            <div class="rb-bubble">${formatted}</div>
        `;
        messages.appendChild(div);
        messages.scrollTop = messages.scrollHeight;
    }

    // ── Loading State ─────────────────────────────────────────────────────────
    function setLoading(state) {
        isLoading = state;
        sendBtn.textContent = state ? '⏳' : '▶';
        sendBtn.disabled = state;
        if (state) {
            const div = document.createElement('div');
            div.className = 'rb-message rb-bot rb-loading';
            div.id = 'rb-typing';
            div.innerHTML = `<span class="rb-avatar">🤖</span><div class="rb-bubble rb-typing-indicator"><span></span><span></span><span></span></div>`;
            messages.appendChild(div);
            messages.scrollTop = messages.scrollHeight;
        } else {
            const typing = document.getElementById('rb-typing');
            if (typing) typing.remove();
        }
    }

    // ── Drag & Drop für FAB ──────────────────────────────────────────────────
    let isDragging = false;
    let dragStartX, dragStartY, fabStartX, fabStartY;

    fab.addEventListener('mousedown', (e) => {
        isDragging = false;
        dragStartX = e.clientX;
        dragStartY = e.clientY;
        const rect = widgetContainer.getBoundingClientRect();
        fabStartX = rect.right;
        fabStartY = rect.bottom;

        const onMove = (e2) => {
            const dx = Math.abs(e2.clientX - dragStartX);
            const dy = Math.abs(e2.clientY - dragStartY);
            if (dx > 5 || dy > 5) {
                isDragging = true;
                const newRight = Math.max(10, window.innerWidth - e2.clientX - 28);
                const newBottom = Math.max(10, window.innerHeight - e2.clientY - 28);
                widgetContainer.style.right = newRight + 'px';
                widgetContainer.style.bottom = newBottom + 'px';
                widgetContainer.style.left = 'auto';
                widgetContainer.style.top = 'auto';
            }
        };

        const onUp = () => {
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
            if (isDragging) {
                // Save position
                chrome.storage.local.set({
                    widgetRight: widgetContainer.style.right,
                    widgetBottom: widgetContainer.style.bottom
                });
            }
        };

        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
    });

    // Gespeicherte Position laden
    chrome.storage.local.get(['widgetRight', 'widgetBottom'], (data) => {
        if (data.widgetRight) widgetContainer.style.right = data.widgetRight;
        if (data.widgetBottom) widgetContainer.style.bottom = data.widgetBottom;
    });

    // ── Keyboard Shortcut ─────────────────────────────────────────────────────
    document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'R') {
            e.preventDefault();
            isOpen = !isOpen;
            panel.classList.toggle('rudibot-hidden', !isOpen);
            if (isOpen) input.focus();
        }
    });

    // ── Rechtsklick Text analysieren ──────────────────────────────────────────
    document.addEventListener('contextmenu', (e) => {
        const selection = window.getSelection()?.toString().trim();
        if (selection && selection.length > 10) {
            // Store selection for context menu use
            chrome.storage.local.set({ lastSelection: selection.substring(0, 500) });
        }
    });

})();
