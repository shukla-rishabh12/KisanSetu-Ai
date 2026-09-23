// ============================================================
// KisanBazaar AI — Chat Widget Frontend
// ============================================================
// Ye chat widget ka pura frontend logic hai.
//
// FEATURES:
//   - Open/close toggle (floating button)
//   - Session ID management (localStorage)
//   - Auto-insight (Dashboard se trigger)
//   - User messages + AI replies
//   - Typing indicator
//   - AI health check
//   - Unread badge
//
// GLOBAL API (dashboard.js isse call karega):
//   window.kbChat.showInsight({market, commodity, variety, state, district})
//   window.kbChat.open()
//   window.kbChat.close()
//   window.kbChat.clear()
//
// DEPENDENCY:
//   - chat_widget.html (DOM structure)
//   - chat.css (styling)
// ============================================================

(function () {
    'use strict';

    // ========================================================
    // SECTION 1: CONSTANTS & STATE
    // ========================================================

    const API_BASE = '/api/chat';
    const SESSION_KEY = 'kb_chat_session_id';

    const state = {
        sessionId: null,
        isOpen: false,
        isWaiting: false,       // AI response wait kar raha hai
        isOnline: true,         // AI available hai ya nahi
        unreadCount: 0,
        lastContext: null,      // Last applied filters
        hasWelcomeBeenShown: false,
    };

    // DOM elements (init ke baad set honge)
    let el = {};


    // ========================================================
    // SECTION 2: DOM INIT
    // ========================================================

    function cacheElements() {
        el = {
            widget: document.getElementById('kb-chat-widget'),
            toggle: document.getElementById('kb-chat-toggle'),
            panel: document.getElementById('kb-chat-panel'),
            close: document.getElementById('kb-chat-minimize'),
            clear: document.getElementById('kb-chat-clear'),
            messages: document.getElementById('kb-chat-messages'),
            welcome: document.getElementById('kb-chat-welcome'),
            typing: document.getElementById('kb-chat-typing'),
            offline: document.getElementById('kb-chat-offline'),
            offlineText: document.getElementById('kb-chat-offline-text'),
            input: document.getElementById('kb-chat-input'),
            send: document.getElementById('kb-chat-send'),
            badge: document.getElementById('kb-chat-badge'),
            status: document.getElementById('kb-chat-status'),
            inputArea: document.getElementById('kb-chat-input-area'),
        };

        // Sanity check
        if (!el.widget) {
            console.warn('[ChatWidget] Widget DOM not found. Include chat_widget.html first.');
            return false;
        }
        return true;
    }


    // ========================================================
    // SECTION 3: SESSION MANAGEMENT
    // ========================================================

    function getOrCreateSessionId() {
        let sid = null;
        try {
            sid = localStorage.getItem(SESSION_KEY);
        } catch (e) {
            // localStorage disabled
        }

        if (!sid) {
            sid = 'sess-' + Date.now() + '-' + Math.random().toString(36).substring(2, 10);
            try {
                localStorage.setItem(SESSION_KEY, sid);
            } catch (e) { /* ignore */ }
        }
        return sid;
    }

    function resetSessionId() {
        const sid = 'sess-' + Date.now() + '-' + Math.random().toString(36).substring(2, 10);
        try {
            localStorage.setItem(SESSION_KEY, sid);
        } catch (e) { /* ignore */ }
        state.sessionId = sid;
    }


    // ========================================================
    // SECTION 4: UI HELPERS
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
        const dotClass = type === 'offline' ? 'kb-offline'
                       : type === 'thinking' ? 'kb-thinking'
                       : '';
        el.status.innerHTML =
            `<span class="kb-chat-status-dot ${dotClass}"></span><span>${escapeHtml(text)}</span>`;
    }


    // ========================================================
    // SECTION 5: OPEN / CLOSE WIDGET
    // ========================================================

    function openWidget() {
        if (!el.widget) return;
        el.widget.setAttribute('data-state', 'open');
        state.isOpen = true;
        state.unreadCount = 0;
        updateBadge();

        // Focus input after animation
        setTimeout(() => {
            if (el.input) el.input.focus();
        }, 250);

        scrollToBottom();
    }

    function closeWidget() {
        if (!el.widget) return;
        el.widget.setAttribute('data-state', 'closed');
        state.isOpen = false;
    }

    function toggleWidget() {
        if (state.isOpen) closeWidget();
        else openWidget();
    }

    function updateBadge() {
        if (!el.badge) return;
        if (state.unreadCount > 0 && !state.isOpen) {
            el.badge.textContent = state.unreadCount > 9 ? '9+' : String(state.unreadCount);
            el.badge.style.display = 'flex';
            el.toggle.classList.add('kb-has-unread');
        } else {
            el.badge.style.display = 'none';
            el.toggle.classList.remove('kb-has-unread');
        }
    }

    function incrementUnread() {
        if (!state.isOpen) {
            state.unreadCount++;
            updateBadge();
        }
    }


    // ========================================================
    // SECTION 6: MESSAGE RENDERING
    // ========================================================

    function hideWelcome() {
        if (el.welcome && el.welcome.style.display !== 'none') {
            el.welcome.style.display = 'none';
            state.hasWelcomeBeenShown = true;
        }
    }

    function addMessage({ role, text, source = null, isInsight = false, timestamp = null }) {
        if (!el.messages) return;

        hideWelcome();

        const bubble = document.createElement('div');
        const time = timestamp ? new Date(timestamp) : new Date();

        // Bubble class
        if (isInsight) {
            bubble.className = 'kb-chat-bubble kb-chat-bubble-insight';

            const header = document.createElement('div');
            header.className = 'kb-chat-insight-header';
            header.textContent = '⚡ Auto Insight';
            bubble.appendChild(header);

            const textNode = document.createElement('div');
            textNode.textContent = text;
            bubble.appendChild(textNode);
        } else if (role === 'user') {
            bubble.className = 'kb-chat-bubble kb-chat-bubble-user';
            bubble.textContent = text;
        } else {
            bubble.className = 'kb-chat-bubble kb-chat-bubble-assistant';

            const textSpan = document.createElement('span');
            textSpan.textContent = text;
            bubble.appendChild(textSpan);

            // Source tag (AI / fallback)
            if (source) {
                const tag = document.createElement('span');
                tag.className = `kb-chat-source-tag ${
                    source === 'ai' ? 'kb-chat-source-ai' : 'kb-chat-source-fallback'
                }`;
                tag.textContent = source === 'ai' ? 'AI' : 'Fallback';
                bubble.appendChild(tag);
            }
        }

        // Timestamp
        const ts = document.createElement('div');
        ts.className = `kb-chat-timestamp ${role === 'user' ? 'kb-timestamp-user' : ''}`;
        ts.textContent = formatTime(time);

        el.messages.appendChild(bubble);
        el.messages.appendChild(ts);

        scrollToBottom();

        // Unread badge (agar closed hai)
        if (role !== 'user') {
            incrementUnread();
        }
    }

    function showTyping() {
        if (el.typing) {
            el.typing.style.display = 'block';
            scrollToBottom();
        }
        setStatus('Thinking...', 'thinking');
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
    // SECTION 7: API CALLS
    // ========================================================

    async function apiPost(endpoint, body) {
        try {
            const response = await fetch(`${API_BASE}${endpoint}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });

            const data = await response.json();

            if (!response.ok || !data.success) {
                throw new Error(
                    (data && (data.message || data.error)) || `HTTP ${response.status}`
                );
            }

            return data.data;
        } catch (err) {
            console.error(`[ChatWidget] API error (${endpoint}):`, err);
            throw err;
        }
    }


    // ========================================================
    // SECTION 8: HEALTH CHECK (page load pe)
    // ========================================================

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
            // Backend reachable nahi
            showOffline('Backend se connection nahi ho paya. Flask chalu hai?');
        }
    }


    // ========================================================
    // SECTION 9: AUTO-INSIGHT (Dashboard se call hoga)
    // ========================================================

    /**
     * Ye function dashboard.js se call hoga jab user filters apply kare.
     *
     * @param {Object} filters - {market, commodity, variety, state, district}
     */
    async function showInsight(filters) {
        if (!filters || !filters.market || !filters.commodity) {
            console.warn('[ChatWidget] showInsight called with invalid filters');
            return;
        }

        // Save context for later
        state.lastContext = { ...filters };

        // Clear existing messages (naya filter = naya conversation)
        clearMessages();

        // Show typing
        showTyping();

        try {
            const result = await apiPost('/insight', {
                session_id: state.sessionId,
                market: filters.market,
                commodity: filters.commodity,
                variety: filters.variety || null,
                state: filters.state || null,
                district: filters.district || null,
            });

            // Update session id (backend ne diya ya confirm kiya)
            if (result.session_id) {
                state.sessionId = result.session_id;
                try { localStorage.setItem(SESSION_KEY, result.session_id); } catch (e) {}
            }

            hideTyping();

            // Add insight message
            addMessage({
                role: 'assistant',
                text: result.insight || 'Insight generate nahi ho paya.',
                source: result.source,
                isInsight: true,
            });

            // Auto-open widget agar insight aayi (thoda delay ke saath)
            setTimeout(() => {
                if (!state.isOpen) {
                    openWidget();
                }
            }, 500);

        } catch (err) {
            hideTyping();
            addMessage({
                role: 'assistant',
                text: 'Insight load karne me problem aayi. Thodi der me try karo.',
                source: 'fallback',
            });
        }
    }


    // ========================================================
    // SECTION 10: SEND MESSAGE
    // ========================================================

    async function sendMessage() {
        if (state.isWaiting || !state.isOnline) return;

        const text = (el.input.value || '').trim();
        if (!text) return;

        // Clear input
        el.input.value = '';
        el.input.style.height = 'auto';
        updateSendButton();

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
            addMessage({
                role: 'assistant',
                text: result.reply || 'Koi reply nahi mila.',
                source: result.source,
            });

        } catch (err) {
            hideTyping();
            addMessage({
                role: 'assistant',
                text: 'Reply lene me problem aayi. Thodi der me try karo.',
                source: 'fallback',
            });
        } finally {
            state.isWaiting = false;
        }
    }


    // ========================================================
    // SECTION 11: CLEAR MESSAGES
    // ========================================================

    function clearMessages() {
        if (!el.messages) return;
        el.messages.innerHTML = '';
        // Welcome wapas dikhao? Nahi — kyunki ab filters ke saath conversation chal rahi
        state.unreadCount = 0;
        updateBadge();
    }

    function clearConversation() {
        // Confirm?
        if (!confirm('Chat conversation clear karein?')) return;

        clearMessages();
        resetSessionId();
        state.lastContext = null;

        // Welcome dikhao
        if (el.messages && el.welcome) {
            el.messages.appendChild(el.welcome);
            el.welcome.style.display = 'block';
        }

        setStatus('Ready', 'ready');
    }


    // ========================================================
    // SECTION 12: INPUT HANDLING
    // ========================================================

    function updateSendButton() {
        if (!el.send || !el.input) return;
        const hasText = (el.input.value || '').trim().length > 0;
        el.send.disabled = !hasText || state.isWaiting || !state.isOnline;
    }

    function autoResizeInput() {
        if (!el.input) return;
        el.input.style.height = 'auto';
        el.input.style.height = Math.min(el.input.scrollHeight, 100) + 'px';
    }


    // ========================================================
    // SECTION 13: EVENT BINDINGS
    // ========================================================

    function bindEvents() {
        // Toggle button
        el.toggle.addEventListener('click', toggleWidget);

        // Close / minimize
        if (el.close) el.close.addEventListener('click', closeWidget);
        if (el.clear) el.clear.addEventListener('click', clearConversation);

        // Send button
        if (el.send) el.send.addEventListener('click', sendMessage);

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

        // Escape key closes panel
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && state.isOpen) {
                closeWidget();
            }
        });
    }


    // ========================================================
    // SECTION 14: INIT
    // ========================================================

    function init() {
        if (!cacheElements()) return;

        // Session id set karo
        state.sessionId = getOrCreateSessionId();
        console.log('[ChatWidget] Session:', state.sessionId);

        // Welcome state default visible
        if (el.welcome) {
            el.welcome.style.display = 'block';
        }

        // Events bind karo
        bindEvents();

        // Send button initially disabled
        updateSendButton();

        // AI health check (async)
        checkHealth();

        console.log('[ChatWidget] Ready');
    }


    // ========================================================
    // SECTION 15: GLOBAL API
    // ========================================================
    // Ye window pe expose karte hain taaki dashboard.js
    // aur baaki modules isse call kar sakein.
    // ========================================================

    window.kbChat = {
        init: init,
        open: openWidget,
        close: closeWidget,
        toggle: toggleWidget,
        clear: clearConversation,
        showInsight: showInsight,
        checkHealth: checkHealth,
        addMessage: addMessage,
        // Debugging
        getState: () => ({ ...state }),
    };


    // ========================================================
    // SECTION 16: AUTO-INIT
    // ========================================================
    // DOMContentLoaded pe auto init ho jayega.
    // Agar widget baad me load hui ho to explicit init() call karna.

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        // DOM already loaded (agar script defer ke saath load hui hai)
        init();
    }

})();