// ============================================================
// KisanBazaar AI — Dashboard Main JavaScript (v2)
// ============================================================
// Ye file Dashboard ka main frontend logic hai.
//
// CHANGES (v2):
//   - Native <select> → custom combobox (prefix search)
//   - Cascading filters: state → district → market → commodity → variety
//   - Comparison table me commodity + variety columns
//   - Reset pe sab combobox clear
//
// DEPENDENCIES:
//   - charts.js         (chart render functions)
//   - combobox.js       (custom searchable dropdown)
//   - Chart.js (CDN)
// ============================================================


// ============================================================
// SECTION 1: DOM HELPERS
// ============================================================

const $ = (id) => document.getElementById(id);

function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

function formatPrice(value) {
    if (value === null || value === undefined) return '—';
    return Number(value).toLocaleString('en-IN', {
        maximumFractionDigits: 2,
    });
}


// ============================================================
// SECTION 2: UI STATE
// ============================================================

function setButtonLoading(button, isLoading, defaultText = 'Apply Filters') {
    if (!button) return;
    if (isLoading) {
        button.disabled = true;
        button.innerHTML = '<span class="kb-loading"></span> Loading...';
    } else {
        button.disabled = false;
        button.innerHTML = defaultText;
    }
}

function showChartsLoading(show) {
    const container = $('charts-container');
    if (!container) return;
    const existing = container.querySelector('.kb-loading-overlay');
    if (existing) existing.remove();
    if (show && container.style.display !== 'none') {
        const overlay = document.createElement('div');
        overlay.className = 'kb-loading-overlay';
        container.style.position = 'relative';
        container.appendChild(overlay);
    }
}

function showError(message) {
    console.error('[KisanBazaar]', message);
    alert('⚠️ ' + message);
}


// ============================================================
// SECTION 3: API WRAPPER
// ============================================================

async function apiGet(url) {
    try {
        const response = await fetch(url, {
            method: 'GET',
            headers: { 'Accept': 'application/json' },
        });
        const data = await response.json();
        if (!response.ok || !data.success) {
            const errMsg = (data && data.message) || (data && data.error) || 'API error';
            console.warn('API error:', url, errMsg, data);
            return null;
        }
        return data.data;
    } catch (err) {
        console.error('Network/API error:', url, err);
        return null;
    }
}

function buildQueryString(params) {
    const query = new URLSearchParams();
    Object.keys(params).forEach(key => {
        if (params[key]) query.append(key, params[key]);
    });
    return query.toString();
}


// ============================================================
// SECTION 4: COMBINED FILTER VALUES
// ============================================================
// Combobox se values uthate hain (getComboboxValue function
// combobox.js me define hai).
// ============================================================

function getFilterValues() {
    return {
        state: getComboboxValue('combo-state') || '',
        district: getComboboxValue('combo-district') || '',
        market: getComboboxValue('combo-market') || '',
        commodity: getComboboxValue('combo-commodity') || '',
        variety: getComboboxValue('combo-variety') || '',
        start_date: ($('filter-start-date') || {}).value || '',
        end_date: ($('filter-end-date') || {}).value || '',
    };
}

function validateFilters(filters) {
    if (!filters.market) {
        showError('Please select a Market / Mandi');
        return false;
    }
    if (!filters.commodity) {
        showError('Please select a Commodity');
        return false;
    }
    return true;
}


// ============================================================
// SECTION 5: CASCADING LOGIC
// ============================================================
// State change → districts fetch
// District change → markets fetch
// Market change → commodities fetch
// Commodity change → varieties fetch
// ============================================================

/**
 * Helper: combobox me loading message dikhao
 */
function setComboboxLoading(comboId) {
    setComboboxOptions(comboId, []);
    // Combobox empty state "No options available" dikhayega
}

/**
 * Districts fetch karke district combobox me set karo.
 */
async function loadDistricts(state) {
    setComboboxLoading('combo-district');

    const url = '/api/dashboard/districts?' + buildQueryString({ state });
    const data = await apiGet(url);

    if (data && Array.isArray(data)) {
        setComboboxOptions('combo-district', data);
    }
}

/**
 * Markets fetch karke market combobox me set karo.
 */
async function loadMarkets(state, district) {
    setComboboxLoading('combo-market');

    const url = '/api/dashboard/markets?' + buildQueryString({ state, district });
    const data = await apiGet(url);

    if (data && Array.isArray(data)) {
        setComboboxOptions('combo-market', data);
    }
}

/**
 * Commodities fetch karke commodity combobox me set karo.
 */
async function loadCommodities(state, district, market) {
    setComboboxLoading('combo-commodity');

    const url = '/api/dashboard/commodities?' + buildQueryString({
        state, district, market,
    });
    const data = await apiGet(url);

    if (data && Array.isArray(data)) {
        setComboboxOptions('combo-commodity', data);
    }
}

/**
 * Varieties fetch karke variety combobox me set karo.
 */
async function loadVarieties(state, district, market, commodity) {
    setComboboxLoading('combo-variety');

    const url = '/api/dashboard/varieties?' + buildQueryString({
        state, district, market, commodity,
    });
    const data = await apiGet(url);

    if (data && Array.isArray(data)) {
        setComboboxOptions('combo-variety', data);
    }
}

/**
 * Cascading chain ka main setup.
 * Har combobox ke onSelect callback me aage wala load hoga.
 */
function setupCascadingFilters() {
    // --------------------------------------------------------
    // STATE select hone pe: districts load + sab neeche reset
    // --------------------------------------------------------
    const stateCombo = kbComboboxes['combo-state'];
    if (stateCombo) {
        const originalOnSelect = stateCombo.onSelect;
        stateCombo.onSelect = (value) => {
            // Neeche ke saare filters clear
            clearCombobox('combo-district', true);
            clearCombobox('combo-market', true);
            clearCombobox('combo-commodity', true);
            clearCombobox('combo-variety', true);

            // Options reset
            setComboboxOptions('combo-district', []);
            setComboboxOptions('combo-market', []);
            setComboboxOptions('combo-commodity', []);
            setComboboxOptions('combo-variety', []);

            // Districts fetch
            loadDistricts(value);

            if (typeof originalOnSelect === 'function') originalOnSelect(value);
        };
    }

    // --------------------------------------------------------
    // DISTRICT select hone pe: markets load + neeche reset
    // --------------------------------------------------------
    const districtCombo = kbComboboxes['combo-district'];
    if (districtCombo) {
        const originalOnSelect = districtCombo.onSelect;
        districtCombo.onSelect = (value) => {
            clearCombobox('combo-market', true);
            clearCombobox('combo-commodity', true);
            clearCombobox('combo-variety', true);

            setComboboxOptions('combo-market', []);
            setComboboxOptions('combo-commodity', []);
            setComboboxOptions('combo-variety', []);

            const state = getComboboxValue('combo-state') || '';
            loadMarkets(state, value);

            if (typeof originalOnSelect === 'function') originalOnSelect(value);
        };
    }

    // --------------------------------------------------------
    // MARKET select hone pe: commodities load + neeche reset
    // --------------------------------------------------------
    const marketCombo = kbComboboxes['combo-market'];
    if (marketCombo) {
        const originalOnSelect = marketCombo.onSelect;
        marketCombo.onSelect = (value) => {
            clearCombobox('combo-commodity', true);
            clearCombobox('combo-variety', true);

            setComboboxOptions('combo-commodity', []);
            setComboboxOptions('combo-variety', []);

            const state = getComboboxValue('combo-state') || '';
            const district = getComboboxValue('combo-district') || '';
            loadCommodities(state, district, value);

            if (typeof originalOnSelect === 'function') originalOnSelect(value);
        };
    }

    // --------------------------------------------------------
    // COMMODITY select hone pe: varieties load
    // --------------------------------------------------------
    const commodityCombo = kbComboboxes['combo-commodity'];
    if (commodityCombo) {
        const originalOnSelect = commodityCombo.onSelect;
        commodityCombo.onSelect = (value) => {
            clearCombobox('combo-variety', true);
            setComboboxOptions('combo-variety', []);

            const state = getComboboxValue('combo-state') || '';
            const district = getComboboxValue('combo-district') || '';
            const market = getComboboxValue('combo-market') || '';
            loadVarieties(state, district, market, value);

            if (typeof originalOnSelect === 'function') originalOnSelect(value);
        };
    }
}


// ============================================================
// SECTION 6: UI UPDATE — CARDS
// ============================================================

function updateCards(latest) {
    const setVal = (id, val) => {
        const el = $(id);
        if (el) el.textContent = val === null || val === undefined
            ? '—'
            : '₹' + formatPrice(val);
    };

    setVal('card-modal-price', latest.modal_price);
    setVal('card-min-price', latest.min_price);
    setVal('card-max-price', latest.max_price);
    setVal('card-avg-price', latest.avg_price);

    const dateEl = $('latest-date');
    const mcEl = $('latest-market-commodity');
    if (dateEl) dateEl.textContent = 'As of ' + (latest.arrival_date || '—');
    if (mcEl) mcEl.textContent = `${latest.market || ''} · ${latest.commodity || ''}` +
        (latest.variety ? ' · ' + latest.variety : '');
}

function resetCards() {
    ['card-modal-price', 'card-min-price', 'card-max-price', 'card-avg-price'].forEach(id => {
        const el = $(id);
        if (el) el.textContent = '—';
    });
    const dateEl = $('latest-date');
    const mcEl = $('latest-market-commodity');
    if (dateEl) dateEl.textContent = 'Select filters to load prices';
    if (mcEl) mcEl.textContent = '';
}


// ============================================================
// SECTION 7: UI UPDATE — COMPARISON TABLE
// ============================================================
// Ab commodity aur variety columns bhi hain.
// ============================================================

function updateComparisonTable(rows) {
    const section = $('comparison-section');
    const tbody = $('comparison-tbody');
    if (!section || !tbody) return;

    if (!rows || rows.length === 0) {
        section.style.display = 'none';
        return;
    }

    tbody.innerHTML = '';

    rows.forEach((row, idx) => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${idx + 1}</td>
            <td><strong>${escapeHtml(row.market)}</strong></td>
            <td>${escapeHtml(row.district || '—')}</td>
            <td>${escapeHtml(row.state || '—')}</td>
            <td>${escapeHtml(row.commodity || '—')}</td>
            <td>${escapeHtml(row.variety || '—')}</td>
            <td>${escapeHtml(row.latest_date || '—')}</td>
            <td class="kb-price-cell">₹${formatPrice(row.modal_price)}</td>
            <td>₹${formatPrice(row.min_price)}</td>
            <td>₹${formatPrice(row.max_price)}</td>
            <td class="kb-price-cell">₹${formatPrice(row.avg_modal)}</td>
        `;
        tbody.appendChild(tr);
    });

    section.style.display = 'block';
}


// ============================================================
// SECTION 8: APPLY FILTERS
// ============================================================

async function applyFilters() {
    const filters = getFilterValues();

    if (!validateFilters(filters)) return;

    const applyBtn = $('btn-apply-filters');
    setButtonLoading(applyBtn, true);

    const emptyState = $('charts-empty');
    const chartsContainer = $('charts-container');
    if (emptyState) emptyState.style.display = 'none';
    if (chartsContainer) chartsContainer.style.display = 'grid';

    showChartsLoading(true);

    try {
        const latestUrl = '/api/dashboard/latest?' + buildQueryString({
            market: filters.market,
            commodity: filters.commodity,
            variety: filters.variety,
        });

        const trendUrl = '/api/dashboard/trend?' + buildQueryString({
            market: filters.market,
            commodity: filters.commodity,
            variety: filters.variety,
            start_date: filters.start_date,
            end_date: filters.end_date,
            limit: 365,
        });

        const monthlyUrl = '/api/dashboard/monthly?' + buildQueryString({
            market: filters.market,
            commodity: filters.commodity,
            variety: filters.variety,
            months: 12,
        });

        const comparisonUrl = '/api/dashboard/comparison?' + buildQueryString({
            commodity: filters.commodity,
            state: filters.state,
            variety: filters.variety,
            days: 7,
        });

        const [latest, trend, monthly, comparison] = await Promise.all([
            apiGet(latestUrl),
            apiGet(trendUrl),
            apiGet(monthlyUrl),
            apiGet(comparisonUrl),
        ]);

        if (latest) {
            updateCards(latest);
        } else {
            resetCards();
        }

        if (trend && trend.length > 0) {
            renderPriceTrendChart(trend);
        } else {
            destroyChart('priceTrend');
        }

        if (monthly && monthly.length > 0) {
            renderMonthlyMovementChart(monthly);
        } else {
            destroyChart('monthlyMovement');
        }

        if (comparison && comparison.length > 0) {
            updateComparisonTable(comparison);
        } else {
            updateComparisonTable([]);
        }

        if (!latest) {
            showError('Selected market/commodity ke liye koi data nahi mila.');
        }

        // ------------------------------------------------
        // Chat widget ko context bhejo → auto-insight
        // ------------------------------------------------
        if (window.kbChat && typeof window.kbChat.showInsight === 'function') {
            window.kbChat.showInsight({
                market: filters.market,
                commodity: filters.commodity,
                variety: filters.variety,
                state: filters.state,
                district: filters.district,
            });
        } else {
            console.warn('Chat widget not loaded');
        }

    } catch (err) {
        console.error('applyFilters error:', err);
        showError('Data load karne me problem aayi. Console check karo.');
    } finally {
        setButtonLoading(applyBtn, false);
        showChartsLoading(false);
    }
}


// ============================================================
// SECTION 9: RESET FILTERS
// ============================================================

function resetFilters() {
    // Saare combobox clear karo (silent — onSelect callback nahi call karna)
    ['combo-state', 'combo-district', 'combo-market',
     'combo-commodity', 'combo-variety'].forEach(comboId => {
        clearCombobox(comboId, true);
    });

    // District/market/commodity/variety ke options bhi clear
    ['combo-district', 'combo-market', 'combo-commodity', 'combo-variety'].forEach(comboId => {
        setComboboxOptions(comboId, []);
    });

    // Date inputs reset
    const startDate = $('filter-start-date');
    const endDate = $('filter-end-date');
    if (startDate) startDate.value = '';
    if (endDate) endDate.value = '';

    // Cards reset
    resetCards();

    // Charts hide
    const emptyState = $('charts-empty');
    const chartsContainer = $('charts-container');
    if (emptyState) emptyState.style.display = 'block';
    if (chartsContainer) chartsContainer.style.display = 'none';

    // Comparison table hide
    const comparisonSection = $('comparison-section');
    if (comparisonSection) comparisonSection.style.display = 'none';

    // Charts destroy
    if (typeof destroyAllCharts === 'function') {
        destroyAllCharts();
    }
}


// ============================================================
// SECTION 10: SUMMARY STATS
// ============================================================

async function refreshSummary() {
    const summary = await apiGet('/api/dashboard/summary');
    if (!summary) return;

    const set = (id, val) => {
        const el = $(id);
        if (el) el.textContent = val ?? '—';
    };

    set('stat-total-records', summary.total_records);
    set('stat-total-markets', summary.total_markets);
    set('stat-total-commodities', summary.total_commodities);

    if (summary.date_range && summary.date_range.min) {
        set('stat-date-range',
            `${summary.date_range.min} → ${summary.date_range.max}`);
    }

    if (summary.last_sync) {
        const el = $('last-sync-info');
        if (el) {
            el.textContent = `Last sync: ${summary.last_sync.sync_date} (${summary.last_sync.status})`;
        }
    }
}


// ============================================================
// SECTION 11: INITIAL LOAD — Pre-populate filters
// ============================================================
// Page load pe comboboxes ko initial options se bhar dete hain.
// State list turant dikhe.
// ============================================================

async function preloadFilters() {
    // State list fetch
    const filters = await apiGet('/api/dashboard/filters');
    if (!filters) return;

    // State options set karo
    if (filters.states && filters.states.length > 0) {
        setComboboxOptions('combo-state', filters.states);
    }

    // Initial districts (bina state filter ke, ya pehle state ke)
    // Best UX: agar sirf ek state hai (abhi ke data me), to auto-select kar do
    if (filters.states && filters.states.length === 1) {
        const onlyState = filters.states[0];
        selectOption('combo-state', onlyState);
        // selectOption onSelect call karega jo districts load karega
    }
}


// ============================================================
// SECTION 12: INIT
// ============================================================

document.addEventListener('DOMContentLoaded', async () => {
    console.log('[KisanBazaar] Dashboard v2 initializing...');

    // --------------------------------------------------------
    // 1. Saare comboboxes initialize karo
    // --------------------------------------------------------
    initCombobox('combo-state');
    initCombobox('combo-district');
    initCombobox('combo-market');
    initCombobox('combo-commodity');
    initCombobox('combo-variety');

    // --------------------------------------------------------
    // 2. Cascading logic wire karo
    // --------------------------------------------------------
    setupCascadingFilters();

    // --------------------------------------------------------
    // 3. Buttons
    // --------------------------------------------------------
    const applyBtn = $('btn-apply-filters');
    const resetBtn = $('btn-reset-filters');

    if (applyBtn) {
        applyBtn.addEventListener('click', (e) => {
            e.preventDefault();
            applyFilters();
        });
    }

    if (resetBtn) {
        resetBtn.addEventListener('click', (e) => {
            e.preventDefault();
            resetFilters();
        });
    }

    // --------------------------------------------------------
    // 4. Initial filter options load karo
    // --------------------------------------------------------
    await preloadFilters();

    // --------------------------------------------------------
    // 5. Summary refresh
    // --------------------------------------------------------
    refreshSummary();

    console.log('[KisanBazaar] Dashboard v2 ready.');
});