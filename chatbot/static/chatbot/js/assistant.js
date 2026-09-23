// ============================================================
// KisanBazaar AI — Assistant Page JavaScript
// ============================================================
// Ye "Kisan Mitra" assistant page ka pura frontend logic hai.
//
// FEATURES:
//   - Session management (localStorage)
//   - Message send/receive via /api/assistant/message
//   - Message rendering (bubbles with timestamp + source tag)
//   - Typing indicator
//   - Quick question chips
//   - Clear conversation
//   - Auto-resize textarea
//   - AI health check on load
//
// DEPENDENCIES:
//   - assistant.css
//   - assistant_routes.py (backend API)
// ============================================================

(function () {
    'use strict';

    // ========================================================
    // CONSTANTS
    // ========================================================

    const API_BASE = '/api/assistant';
    const SESSION_KEY = 'kb_assistant_session_id';

    const state = {
        sessionId: null,
        isWaiting: false,
        isOnline: true,
        hasWelcomeBeenShown: false,
    };

    let el = {};


    // ========================================================
    // DOM CACHE
    // ========================================================

    function cacheElements() {
        el = {
            messages: document.getElementById('assistant-messages'),
            welcome: document.getElementById('assistant-welcome'),
            typing: document.getElementById('assistant-typing'),
            offline: document.getElementById('assistant-offline'),
            offlineText: document.getElementById('assistant-offline-text'),
            input: document.getElementById('assistant-input'),
            send: document.getElementById('assistant-send'),
            clear: document.getElementById('btn-clear-chat'),
            status: document.getElementById('assistant-status'),
            inputArea: document.getElementById('assistant-input-area'),
            chips: document.querySelectorAll('.assistant-chip'),
        };

        return !!el.messages;
    }


    // ========================================================
    // SESSION MANAGEMENT
    // ========================================================

    function getOrCreateSessionId() {
        let sid = null;
        try {
            sid = localStorage.getItem(SESSION_KEY);
        } catch (e) { /* ignore */ }

        if (!sid) {
            sid = 'asst-' + Date.now() + '-' + Math.random().toString(36).substring(2, 10);
            try {
                localStorage.setItem(SESSION_KEY, sid);
            } catch (e) { /* ignore */ }
        }
        return sid;
    }

    function resetSessionId() {
        const sid = 'asst-' + Date.now() + '-' + Math.random().toString(36).substring(2, 10);
        try {
            localStorage.setItem(SESSION_KEY, sid);
        } catch (e) { /* ignore */ }
        state.sessionId = sid;
    }


    // ========================================================
    // HELPERS
    // ========================================================

    function escapeHtml(text) {
        if (text === null || text === undefined) return '';
        const div = document.createElement('div');
        div.textContent = String(text);
        return div.innerHTML;
    }

    function formatTime(date = new Date()) {
        return date.toLocaleTimeString('en-IN', {
            hour: '2-digit',
            minute: '2-digit',
        });
    }

    function scrollToBottom() {
        if (el.messages) {
            el.messages.scrollTop = el.messages.scrollHeight;
        }
    }

    function setStatus(text, type = 'ready') {
        if (!el.status) return;
        const dotClass = type === 'offline' ? 'offline'
                       : type === 'thinking' ? 'thinking'
                       : '';
        el.status.innerHTML =
            `<span class="assistant-status-dot ${dotClass}"></span><span>${escapeHtml(text)}</span>`;
    }

    function hideWelcome() {
        if (el.welcome && el.welcome.style.display !== 'none') {
            el.welcome.style.display = 'none';
            state.hasWelcomeBeenShown = true;
        }
    }


    // ========================================================
    // MESSAGE RENDERING
    // ========================================================

    function addMessage({ role, text, source = null, timestamp = null }) {
        if (!el.messages) return;

        hideWelcome();

        const bubble = document.createElement('div');
        const time = timestamp ? new Date(timestamp) : new Date();

        if (role === 'user') {
            bubble.className = 'assistant-bubble assistant-bubble-user';
            bubble.textContent = text;
        } else {
            bubble.className = 'assistant-bubble assistant-bubble-ai';

            const textSpan = document.createElement('span');
            textSpan.textContent = text;
            bubble.appendChild(textSpan);

            if (source) {
                const tag = document.createElement('span');
                tag.className = `assistant-source-tag ${
                    source === 'ai' ? 'assistant-source-ai' : 'assistant-source-fallback'
                }`;
                tag.textContent = source === 'ai' ? 'AI' : 'Fallback';
                bubble.appendChild(tag);
            }
        }

        const ts = document.createElement('div');
        ts.className = `assistant-timestamp ${role === 'user' ? 'ts-user' : ''}`;
        ts.textContent = formatTime(time);

        el.messages.appendChild(bubble);
        el.messages.appendChild(ts);

        scrollToBottom();
    }

    function showTyping() {
        if (el.typing) {
            el.typing.style.display = 'block';
            scrollToBottom();
        }
        setStatus('Soch raha hai...', 'thinking');
    }

    function hideTyping() {
        if (el.typing) {
            el.typing.style.display = 'none';
        }
        if (state.isOnline) {
            setStatus('Ready', 'ready');
        }
    }

    function showOffline(message) {
        state.isOnline = false;
        if (el.offline) {
            el.offline.style.display = 'block';
            if (message && el.offlineText) {
                el.offlineText.textContent = message;
            }
        }
        if (el.inputArea) {
            el.inputArea.style.display = 'none';
        }
        setStatus('Offline', 'offline');
    }

    function hideOffline() {
        state.isOnline = true;
        if (el.offline) el.offline.style.display = 'none';
        if (el.inputArea) el.inputArea.style.display = 'block';
        setStatus('Ready', 'ready');
    }


    // ========================================================
    // API CALLS
    // ========================================================

    async function apiPost(endpoint, body) {
        const response = await fetch(`${API_BASE}${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });

        const data = await response.json();

        if (!response.ok || !data.success) {
            const msg = (data && (data.message || data.error)) || `HTTP ${response.status}`;
            throw new Error(msg);
        }

        return data.data;
    }

    async function checkHealth() {
        try {
            const response = await fetch(`${API_BASE}/health`);
            const data = await response.json();

            if (data.success && data.data.available) {
                state.isOnline = true;
                hideOffline();
            } else {
                const errMsg = (data.data && data.data.error) || 'AI offline';
                showOffline(`AI assistant abhi available nahi hai. (${errMsg})`);
            }
        } catch (err) {
            showOffline('Backend se connection nahi ho paya. Flask chalu hai?');
        }
    }


    // ========================================================
    // SEND MESSAGE
    // ========================================================

    async function sendMessage(textOverride = null) {
        if (state.isWaiting || !state.isOnline) return;

        const text = (textOverride !== null ? textOverride : (el.input.value || '')).trim();
        if (!text) return;

        // Clear input
        if (textOverride === null) {
            el.input.value = '';
            el.input.style.height = 'auto';
            updateSendButton();
        }

        // Add user message
        addMessage({ role: 'user', text: text });

        // Show typing
        state.isWaiting = true;
        showTyping();

        try {
            const result = await apiPost('/message', {
                session_id: state.sessionId,
                message: text,
            });

            hideTyping();

            // Update session id if backend generated one
            if (result.session_id) {
                state.sessionId = result.session_id;
                try { localStorage.setItem(SESSION_KEY, result.session_id); } catch (e) {}
            }

            addMessage({
                role: 'assistant',
                text: result.reply || 'Koi reply nahi mila.',
                source: result.source,
            });

        } catch (err) {
            hideTyping();
            console.error('Send error:', err);
            addMessage({
                role: 'assistant',
                text: 'Reply lene me problem aayi. Thodi der me try karein.',
                source: 'fallback',
            });
        } finally {
            state.isWaiting = false;
        }
    }


    // ========================================================
    // CLEAR CONVERSATION
    // ========================================================

    function clearConversation() {
        if (!confirm('Chat conversation clear karein?')) return;

        // Clear DOM messages (except welcome)
        if (el.messages) {
            el.messages.innerHTML = '';
        }

        // Reset session
        resetSessionId();
        state.hasWelcomeBeenShown = false;

        // Show welcome again
        if (el.welcome && el.messages) {
            el.messages.appendChild(el.welcome);
            el.welcome.style.display = 'block';
        }

        setStatus('Ready', 'ready');
    }


    // ========================================================
    // INPUT HANDLING
    // ========================================================

    function updateSendButton() {
        if (!el.send || !el.input) return;
        const hasText = (el.input.value || '').trim().length > 0;
        el.send.disabled = !hasText || state.isWaiting || !state.isOnline;
    }

    function autoResizeInput() {
        if (!el.input) return;
        el.input.style.height = 'auto';
        el.input.style.height = Math.min(el.input.scrollHeight, 120) + 'px';
    }


    // ========================================================
    // EVENT BINDINGS
    // ========================================================

    function bindEvents() {
        // Send button
        if (el.send) {
            el.send.addEventListener('click', () => sendMessage());
        }

        // Clear button
        if (el.clear) {
            el.clear.addEventListener('click', clearConversation);
        }

        // Input: typing, enter, resize
        if (el.input) {
            el.input.addEventListener('input', () => {
                autoResizeInput();
                updateSendButton();
            });

            el.input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                }
            });
        }

        // Quick question chips
        if (el.chips && el.chips.length > 0) {
            el.chips.forEach(chip => {
                chip.addEventListener('click', () => {
                    const q = chip.getAttribute('data-question') || chip.textContent.trim();
                    if (q) sendMessage(q);
                });
            });
        }
    }


    // ========================================================
    // INIT
    // ========================================================

    function init() {
        if (!cacheElements()) {
            console.warn('[Assistant] Required DOM elements not found.');
            return;
        }

        state.sessionId = getOrCreateSessionId();
        console.log('[Assistant] Session:', state.sessionId);

        // Welcome default visible
        if (el.welcome) {
            el.welcome.style.display = 'block';
        }

        bindEvents();
        updateSendButton();
        checkHealth();

        console.log('[Assistant] Ready.');
    }


    // ========================================================
    // AUTO-INIT
    // ========================================================

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();