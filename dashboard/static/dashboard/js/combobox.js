
// ============================================================
// KisanBazaar AI — Custom Searchable Combobox
// ============================================================
// Native <select> me search nahi hota. Ye custom combobox
// prefix-based search deta hai.
//
// PREFIX SEARCH:
//   "la" likho → "Lakhimpur", "Latur", "Ludhiana" ✅
//                "Bilaspur" ❌ (la andar hai, shuru me nahi)
//
// FEATURES:
//   - Type karke search (prefix match)
//   - Keyboard: ↑ ↓ Enter Escape
//   - Clear button (×)
//   - Click outside pe close
//   - Highlight matched prefix
//
// USAGE:
//   initCombobox('combo-state');
//   setComboboxOptions('combo-state', ['UP', 'Bihar', ...]);
//   const value = getComboboxValue('combo-state');
//   clearCombobox('combo-state');
// ============================================================

// ============================================================
// GLOBAL STATE — Har combobox ka data
// ============================================================
// Har combobox ke liye:
//   - options: full list
//   - filtered: currently visible list (after filter)
//   - activeIndex: keyboard navigation ke liye
//   - inputEl, hiddenEl, dropdownEl: DOM elements
//   - onSelect: callback jab value select ho

const kbComboboxes = {};

// ============================================================
// SECTION 1: INITIALIZATION
// ============================================================

/**
 * Ek combobox initialize karta hai.
 *
 * @param {string} comboId - The id of the .kb-combobox container
 * @param {Object} opts - Optional settings
 * @param {Function} opts.onSelect - Callback when value selected (value)
 */
function initCombobox(comboId, opts = {}) {
    const container = document.getElementById(comboId);
    if (!container) {
        console.warn('Combobox not found:', comboId);
        return;
    }

    const inputEl = container.querySelector('.kb-combobox-input');
    const hiddenEl = container.querySelector('input[type="hidden"]');
    const clearBtn = container.querySelector('.kb-combobox-clear');
    const dropdownEl = container.querySelector('.kb-combobox-dropdown');

    if (!inputEl || !hiddenEl || !dropdownEl) {
        console.warn('Combobox missing parts:', comboId);
        return;
    }

    // State store
    kbComboboxes[comboId] = {
        options: [],           // Full options list
        filtered: [],          // Filtered options (search ke baad)
        activeIndex: -1,       // Keyboard navigation
        inputEl,
        hiddenEl,
        dropdownEl,
        clearBtn,
        container,
        onSelect: opts.onSelect || null,
        isOpen: false,
    };

    const state = kbComboboxes[comboId];

    // --------------------------------------------------------
    // EVENT: Input typing (search)
    // --------------------------------------------------------
    inputEl.addEventListener('input', () => {
        // Agar user type kar raha hai, hidden value clear karo
        // (kyunki wo naya option dhundh raha hai)
        state.hiddenEl.value = '';
        filterAndRender(comboId);
        openDropdown(comboId);
    });

    // --------------------------------------------------------
    // EVENT: Input focus
    // --------------------------------------------------------
    inputEl.addEventListener('focus', () => {
        // Focus pe saare options dikhao (ya jo filtered hain)
        filterAndRender(comboId);
        openDropdown(comboId);
    });

    // --------------------------------------------------------
    // EVENT: Keyboard navigation
    // --------------------------------------------------------
    inputEl.addEventListener('keydown', (e) => {
        handleKeydown(comboId, e);
    });

    // --------------------------------------------------------
    // EVENT: Clear button
    // --------------------------------------------------------
    if (clearBtn) {
        clearBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            clearCombobox(comboId);
            inputEl.focus();
        });
    }

    // --------------------------------------------------------
    // EVENT: Dropdown option click
    // --------------------------------------------------------
    // (Delegated — options dynamically bante hain)
    dropdownEl.addEventListener('mousedown', (e) => {
        // mousedown use kiya (click nahi) kyunki blur se pehle
        // event chahiye warna input blur ho jata hai
        const item = e.target.closest('.kb-combobox-option');
        if (!item) return;
        e.preventDefault();

        const value = item.dataset.value || '';
        selectOption(comboId, value);
    });

    // --------------------------------------------------------
    // EVENT: Click outside → close
    // --------------------------------------------------------
    document.addEventListener('mousedown', (e) => {
        if (!container.contains(e.target)) {
            closeDropdown(comboId);
        }
    });

    console.log(`[Combobox] Initialized: ${comboId}`);
}


// ============================================================
// SECTION 2: OPTIONS MANAGEMENT
// ============================================================

/**
 * Combobox me options set karta hai (cascading ke liye).
 * Ye call karne se purani options replace ho jaati hain.
 *
 * @param {string} comboId
 * @param {Array<string>} options - Naya options list
 * @param {boolean} keepValue - Agar true, current value preserve karo (agar exists)
 */
function setComboboxOptions(comboId, options, keepValue = false) {
    const state = kbComboboxes[comboId];
    if (!state) return;

    const previousValue = keepValue ? state.hiddenEl.value : '';

    state.options = Array.isArray(options) ? options.slice() : [];
    state.filtered = state.options.slice();
    state.activeIndex = -1;

    // Agar current value naye options me hai to preserve karo
    if (previousValue && state.options.includes(previousValue)) {
        state.hiddenEl.value = previousValue;
        state.inputEl.value = previousValue;
    } else if (previousValue) {
        // Value nahi mila to clear karo
        state.hiddenEl.value = '';
        state.inputEl.value = '';
    }

    // Agar dropdown open hai to re-render karo
    if (state.isOpen) {
        filterAndRender(comboId);
    }
}

/**
 * Combobox ki current selected value return karta hai.
 * @param {string} comboId
 * @returns {string}
 */
function getComboboxValue(comboId) {
    const state = kbComboboxes[comboId];
    return state ? (state.hiddenEl.value || '') : '';
}

/**
 * Combobox clear karta hai (value + input text).
 * @param {string} comboId
 * @param {boolean} silent - Agar true, onSelect callback nahi call hoga
 */
function clearCombobox(comboId, silent = false) {
    const state = kbComboboxes[comboId];
    if (!state) return;

    state.hiddenEl.value = '';
    state.inputEl.value = '';
    state.activeIndex = -1;

    if (!silent && typeof state.onSelect === 'function') {
        state.onSelect('');
    }

    // Agar dropdown open hai to full list dikhao
    if (state.isOpen) {
        filterAndRender(comboId);
    }
}


// ============================================================
// SECTION 3: SEARCH (PREFIX MATCH)
// ============================================================

/**
 * Prefix match check karta hai.
 * "la" → "Lakhimpur" ✅, "Bilaspur" ❌
 *
 * @param {string} option
 * @param {string} query
 * @returns {boolean}
 */
function matchesPrefix(option, query) {
    if (!query) return true;
    return option.toLowerCase().startsWith(query.toLowerCase());
}

/**
 * Input me jo type kiya, uske basis pe options filter karke render karta hai.
 *
 * @param {string} comboId
 */
function filterAndRender(comboId) {
    const state = kbComboboxes[comboId];
    if (!state) return;

    const query = state.inputEl.value.trim();

    // PREFIX FILTER (main requirement)
    state.filtered = state.options.filter(opt => matchesPrefix(opt, query));

    // Agar query exactly ek option se match karti hai, usse top pe rakho
    if (query) {
        const exactIndex = state.filtered.findIndex(
            opt => opt.toLowerCase() === query.toLowerCase()
        );
        if (exactIndex > 0) {
            // Move to top
            const [exact] = state.filtered.splice(exactIndex, 1);
            state.filtered.unshift(exact);
        }
    }

    state.activeIndex = -1;
    renderDropdown(comboId, query);
}


// ============================================================
// SECTION 4: RENDER DROPDOWN
// ============================================================

/**
 * Dropdown list render karta hai.
 *
 * @param {string} comboId
 * @param {string} query - Search query (highlight ke liye)
 */
function renderDropdown(comboId, query = '') {
    const state = kbComboboxes[comboId];
    if (!state) return;

    const dropdown = state.dropdownEl;
    dropdown.innerHTML = '';

    // Empty state
    if (state.filtered.length === 0) {
        const emptyItem = document.createElement('div');
        emptyItem.className = 'kb-combobox-empty';
        emptyItem.textContent = query
            ? `No match for "${query}"`
            : 'No options available';
        dropdown.appendChild(emptyItem);
        return;
    }

    // "All X" reset option (top pe) — sirf tab jab query khaali ho
    if (!query) {
        const allItem = document.createElement('div');
        allItem.className = 'kb-combobox-option kb-combobox-option-all';
        allItem.dataset.value = '';
        allItem.textContent = 'All / Any';
        dropdown.appendChild(allItem);
    }

    // Maximum 200 options dikhao (perf ke liye)
    const MAX_VISIBLE = 200;
    const visible = state.filtered.slice(0, MAX_VISIBLE);

    visible.forEach((option, idx) => {
        const item = document.createElement('div');
        item.className = 'kb-combobox-option';
        item.dataset.value = option;
        item.dataset.index = idx;

        // Highlight matched prefix
        if (query) {
            const matchLen = query.length;
            const matchedPart = option.substring(0, matchLen);
            const rest = option.substring(matchLen);

            const strong = document.createElement('strong');
            strong.textContent = matchedPart;
            item.appendChild(strong);
            item.appendChild(document.createTextNode(rest));
        } else {
            item.textContent = option;
        }

        dropdown.appendChild(item);
    });

    // Agar bahut zyada options hain to notice
    if (state.filtered.length > MAX_VISIBLE) {
        const moreItem = document.createElement('div');
        moreItem.className = 'kb-combobox-more';
        moreItem.textContent = `+ ${state.filtered.length - MAX_VISIBLE} more... (type to narrow)`;
        dropdown.appendChild(moreItem);
    }
}


// ============================================================
// SECTION 5: OPEN/CLOSE DROPDOWN
// ============================================================

function openDropdown(comboId) {
    const state = kbComboboxes[comboId];
    if (!state || state.isOpen) return;

    state.container.classList.add('kb-combobox-open');
    state.isOpen = true;
}

function closeDropdown(comboId) {
    const state = kbComboboxes[comboId];
    if (!state || !state.isOpen) return;

    state.container.classList.remove('kb-combobox-open');
    state.isOpen = false;

    // Agar input text exactly ek option se match karta hai,
    // to usse finalize kar do. Warna input ko wapas valid value pe reset.
    const typed = state.inputEl.value.trim();
    const currentValue = state.hiddenEl.value;

    if (!typed) {
        // Khaali chhod diya — hidden bhi khaali
        state.hiddenEl.value = '';
        return;
    }

    // Exact match dhundo
    const exact = state.options.find(
        opt => opt.toLowerCase() === typed.toLowerCase()
    );

    if (exact) {
        // Exact match — set as value
        state.hiddenEl.value = exact;
        state.inputEl.value = exact;
    } else if (currentValue) {
        // Kuch aur type kiya lekin valid nahi — purani value restore
        state.inputEl.value = currentValue;
    } else {
        // Kuch bhi match nahi — clear
        state.inputEl.value = '';
    }
}


// ============================================================
// SECTION 6: SELECT OPTION
// ============================================================

/**
 * Ek option select karta hai.
 *
 * @param {string} comboId
 * @param {string} value - Selected value ('' = clear)
 */
function selectOption(comboId, value) {
    const state = kbComboboxes[comboId];
    if (!state) return;

    state.hiddenEl.value = value;
    state.inputEl.value = value;

    closeDropdown(comboId);

    // Callback
    if (typeof state.onSelect === 'function') {
        state.onSelect(value);
    }
}


// ============================================================
// SECTION 7: KEYBOARD NAVIGATION
// ============================================================

function handleKeydown(comboId, e) {
    const state = kbComboboxes[comboId];
    if (!state) return;

    const { key } = e;

    // Dropdown band hai to Arrow Down pe open karo
    if (!state.isOpen && (key === 'ArrowDown' || key === 'ArrowUp')) {
        e.preventDefault();
        filterAndRender(comboId);
        openDropdown(comboId);
        return;
    }

    switch (key) {
        case 'ArrowDown':
            e.preventDefault();
            moveActive(comboId, 1);
            break;

        case 'ArrowUp':
            e.preventDefault();
            moveActive(comboId, -1);
            break;

        case 'Enter': {
            e.preventDefault();
            // Agar koi option active hai to select karo
            if (state.activeIndex >= 0 && state.activeIndex < state.filtered.length) {
                const selected = state.filtered[state.activeIndex];
                selectOption(comboId, selected);
            } else if (state.filtered.length === 1) {
                // Sirf ek option match hua to usse select karo
                selectOption(comboId, state.filtered[0]);
            } else {
                // Nahi to dropdown band karo (input finalize hoga)
                closeDropdown(comboId);
            }
            break;
        }

        case 'Escape':
            e.preventDefault();
            closeDropdown(comboId);
            state.inputEl.blur();
            break;

        case 'Tab':
            // Tab pe dropdown band karo, focus move hone do
            closeDropdown(comboId);
            break;
    }
}

/**
 * Active index ko move karta hai aur us option ko highlight + scroll into view.
 */
function moveActive(comboId, delta) {
    const state = kbComboboxes[comboId];
    if (!state || state.filtered.length === 0) return;

    let newIndex = state.activeIndex + delta;

    // Wrap-around
    if (newIndex < 0) newIndex = state.filtered.length - 1;
    if (newIndex >= state.filtered.length) newIndex = 0;

    state.activeIndex = newIndex;

    // DOM update
    const options = state.dropdownEl.querySelectorAll('.kb-combobox-option');
    options.forEach((opt, idx) => {
        // Note: options list me "All / Any" bhi ho sakta hai
        if (idx === newIndex) {
            opt.classList.add('kb-combobox-option-active');
            opt.scrollIntoView({ block: 'nearest' });
        } else {
            opt.classList.remove('kb-combobox-option-active');
        }
    });
}


// ============================================================
// SECTION 8: EXPORT TO WINDOW
// ============================================================

window.initCombobox = initCombobox;
window.setComboboxOptions = setComboboxOptions;
window.getComboboxValue = getComboboxValue;
window.clearCombobox = clearCombobox;