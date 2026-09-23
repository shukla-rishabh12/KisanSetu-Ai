// ============================================================
// KisanBazaar AI — ML Forecast Page JavaScript
// ============================================================
// Ye ML forecast page ka pura frontend logic hai.
//
// FEATURES:
//   - 5 comboboxes with cascading (Dashboard jaisa)
//   - Predict button → /api/ml/predict
//   - Results render (selected card, expected value, table, chart)
//   - Reset button
//   - Chat widget integration (prediction context)
//   - Data availability pre-check
//
// DEPENDENCIES:
//   - combobox.js (Dashboard se — global combobox library)
//   - forecast_chart.js (chart wrapper)
//   - Chart.js (CDN)
// ============================================================


// ============================================================
// SECTION 1: HELPERS
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

function formatDate(dateStr) {
    if (!dateStr) return '—';
    try {
        const d = new Date(dateStr);
        return d.toLocaleDateString('en-IN', {
            day: '2-digit',
            month: 'short',
            year: 'numeric',
        });
    } catch (e) {
        return dateStr;
    }
}


// ============================================================
// SECTION 2: API WRAPPER
// ============================================================

async function apiGet(url) {
    try {
        const response = await fetch(url, {
            headers: { 'Accept': 'application/json' },
        });
        const data = await response.json();
        if (!response.ok || !data.success) return null;
        return data.data;
    } catch (err) {
        console.error('API error:', url, err);
        return null;
    }
}

async function apiPost(url, body) {
    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        const data = await response.json();
        if (!response.ok || !data.success) {
            const msg = (data && (data.error || data.message)) || 'API error';
            const err = new Error(msg);
            err.details = data && data.details;
            throw err;
        }
        return data.data;
    } catch (err) {
        console.error('POST error:', url, err);
        throw err;
    }
}


// ============================================================
// SECTION 3: UI STATE HELPERS
// ============================================================

function setButtonLoading(button, isLoading, defaultText = '🔮 Predict') {
    if (!button) return;
    if (isLoading) {
        button.disabled = true;
        button.innerHTML = '<span style="display:inline-block;width:14px;height:14px;border:2px solid rgba(255,255,255,0.3);border-top-color:white;border-radius:50%;animation:ml-spin 0.8s linear infinite;margin-right:6px;vertical-align:middle;"></span> Predicting...';
    } else {
        button.disabled = false;
        button.innerHTML = defaultText;
    }
}

function showLoading(show) {
    const el = $('ml-loading');
    if (el) el.style.display = show ? 'block' : 'none';
}

function showResults(show) {
    const el = $('ml-results');
    if (el) el.style.display = show ? 'block' : 'none';
}

function showWarning(message) {
    const banner = $('data-warning');
    const textEl = $('data-warning-text');
    if (!banner || !textEl) return;
    if (message) {
        textEl.textContent = message;
        banner.style.display = 'flex';
    } else {
        banner.style.display = 'none';
    }
}

function showError(message) {
    console.error('[ML]', message);
    alert('⚠️ ' + message);
}


// ============================================================
// SECTION 4: FILTER VALUES
// ============================================================

function getFilterValues() {
    return {
        state: (window.getComboboxValue ? getComboboxValue('combo-state') : '') || '',
        district: (window.getComboboxValue ? getComboboxValue('combo-district') : '') || '',
        market: (window.getComboboxValue ? getComboboxValue('combo-market') : '') || '',
        commodity: (window.getComboboxValue ? getComboboxValue('combo-commodity') : '') || '',
        variety: (window.getComboboxValue ? getComboboxValue('combo-variety') : '') || '',
        start_date: ($('filter-start-date') || {}).value || '',
        days: parseInt(($('filter-days') || {}).value || '10', 10),
        quantity_kg: ($('filter-quantity') || {}).value || '',
    };
}

function validateFilters(f) {
    if (!f.market) { showError('Please select a Market / Mandi'); return false; }
    if (!f.commodity) { showError('Please select a Commodity'); return false; }
    if (!f.start_date) { showError('Please select a Prediction Date'); return false; }
    return true;
}


// ============================================================
// SECTION 5: CASCADING FILTERS (same as Dashboard)
// ============================================================

function setComboboxLoading(comboId) {
    setComboboxOptions(comboId, []);
}

async function loadDistricts(state) {
    setComboboxLoading('combo-district');
    const data = await apiGet('/api/dashboard/districts?state=' + encodeURIComponent(state));
    if (data) setComboboxOptions('combo-district', data);
}

async function loadMarkets(state, district) {
    setComboboxLoading('combo-market');
    const params = new URLSearchParams();
    if (state) params.append('state', state);
    if (district) params.append('district', district);
    const data = await apiGet('/api/dashboard/markets?' + params.toString());
    if (data) setComboboxOptions('combo-market', data);
}

async function loadCommodities(state, district, market) {
    setComboboxLoading('combo-commodity');
    const params = new URLSearchParams();
    if (state) params.append('state', state);
    if (district) params.append('district', district);
    if (market) params.append('market', market);
    const data = await apiGet('/api/dashboard/commodities?' + params.toString());
    if (data) setComboboxOptions('combo-commodity', data);
}

async function loadVarieties(state, district, market, commodity) {
    setComboboxLoading('combo-variety');
    const params = new URLSearchParams();
    if (state) params.append('state', state);
    if (district) params.append('district', district);
    if (market) params.append('market', market);
    if (commodity) params.append('commodity', commodity);
    const data = await apiGet('/api/dashboard/varieties?' + params.toString());
    if (data) setComboboxOptions('combo-variety', data);
}

function setupCascading() {
    // State → districts + reset below
    const stateCombo = kbComboboxes['combo-state'];
    if (stateCombo) {
        stateCombo.onSelect = (value) => {
            ['combo-district', 'combo-market', 'combo-commodity', 'combo-variety'].forEach(id => {
                clearCombobox(id, true);
                setComboboxOptions(id, []);
            });
            loadDistricts(value);
        };
    }

    // District → markets + reset below
    const districtCombo = kbComboboxes['combo-district'];
    if (districtCombo) {
        districtCombo.onSelect = (value) => {
            ['combo-market', 'combo-commodity', 'combo-variety'].forEach(id => {
                clearCombobox(id, true);
                setComboboxOptions(id, []);
            });
            const state = getComboboxValue('combo-state') || '';
            loadMarkets(state, value);
        };
    }

    // Market → commodities + reset below
    const marketCombo = kbComboboxes['combo-market'];
    if (marketCombo) {
        marketCombo.onSelect = (value) => {
            ['combo-commodity', 'combo-variety'].forEach(id => {
                clearCombobox(id, true);
                setComboboxOptions(id, []);
            });
            const state = getComboboxValue('combo-state') || '';
            const district = getComboboxValue('combo-district') || '';
            loadCommodities(state, district, value);
        };
    }

    // Commodity → varieties
    const commodityCombo = kbComboboxes['combo-commodity'];
    if (commodityCombo) {
        commodityCombo.onSelect = (value) => {
            clearCombobox('combo-variety', true);
            setComboboxOptions('combo-variety', []);
            const state = getComboboxValue('combo-state') || '';
            const district = getComboboxValue('combo-district') || '';
            const market = getComboboxValue('combo-market') || '';
            loadVarieties(state, district, market, value);
        };
    }
}


// ============================================================
// SECTION 6: DATA AVAILABILITY PRE-CHECK
// ============================================================

async function checkDataAvailability() {
    const f = getFilterValues();
    if (!f.market || !f.commodity) {
        showWarning(null);
        return;
    }

    const params = new URLSearchParams({
        market: f.market,
        commodity: f.commodity,
    });
    if (f.variety) params.append('variety', f.variety);

    const data = await apiGet('/api/ml/check?' + params.toString());
    if (!data) {
        showWarning(null);
        return;
    }

    if (data.warning) {
        showWarning(data.warning);
    } else {
        showWarning(null);
    }
}


// ============================================================
// SECTION 7: RENDER RESULTS
// ============================================================

function renderSelectedCard(selected) {
    const setTxt = (id, val) => {
        const el = $(id);
        if (el) el.textContent = val;
    };

    setTxt('selected-date', formatDate(selected.date));
    setTxt('selected-modal', '₹' + formatPrice(selected.modal_price));
    setTxt('selected-min', '₹' + formatPrice(selected.min_price));
    setTxt('selected-max', '₹' + formatPrice(selected.max_price));
}

function renderExpectedValue(expected) {
    const card = $('expected-card');
    if (!card) return;

    if (!expected) {
        card.style.display = 'none';
        return;
    }

    card.style.display = 'block';
    const setTxt = (id, val) => {
        const el = $(id);
        if (el) el.textContent = val;
    };

    setTxt('exp-quantity', expected.quantity_kg + ' kg');
    setTxt('exp-price-kg', '₹' + formatPrice(expected.price_per_kg));
    setTxt('exp-total', '₹' + formatPrice(expected.expected_value));
}

function renderForecastTable(forecast) {
    const tbody = $('forecast-tbody');
    if (!tbody) return;
    tbody.innerHTML = '';

    if (!forecast || forecast.length === 0) {
        const tr = document.createElement('tr');
        tr.innerHTML = '<td colspan="5" style="text-align:center;color:#999;">Koi forecast data nahi</td>';
        tbody.appendChild(tr);
        return;
    }

    forecast.forEach((f, idx) => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${idx + 1}</td>
            <td>${formatDate(f.date)}</td>
            <td>₹${formatPrice(f.min_price)}</td>
            <td class="ml-price-modal-cell">₹${formatPrice(f.modal_price)}</td>
            <td>₹${formatPrice(f.max_price)}</td>
        `;
        tbody.appendChild(tr);
    });
}

function renderModelInfo(info) {
    if (!info) return;
    const setTxt = (id, val) => {
        const el = $(id);
        if (el) el.textContent = val;
    };
    setTxt('model-name', info.name || '—');
    setTxt('model-r2', info.test_r2 != null ? info.test_r2.toFixed(4) : '—');
    setTxt('model-mape', info.test_mape != null ? info.test_mape.toFixed(2) + '%' : '—');
}

function renderResultMeta(data) {
    const meta = $('result-meta');
    if (!meta) return;
    const inp = data.input || {};
    const count = (data.data_info && data.data_info.record_count) || 0;
    meta.textContent = `${inp.market} · ${inp.commodity}${inp.variety ? ' · ' + inp.variety : ''} · ${count} records`;
}


// ============================================================
// SECTION 8: PREDICT (MAIN FLOW)
// ============================================================

async function predict() {
    const f = getFilterValues();
    if (!validateFilters(f)) return;

    const predictBtn = $('btn-predict');
    setButtonLoading(predictBtn, true);
    showWarning(null);
    showResults(false);
    showLoading(true);

    try {
        const payload = {
            state: f.state,
            district: f.district,
            market: f.market,
            commodity: f.commodity,
            variety: f.variety || null,
            start_date: f.start_date,
            days: f.days,
        };

        if (f.quantity_kg) {
            payload.quantity_kg = parseFloat(f.quantity_kg);
        }

        const data = await apiPost('/api/ml/predict', payload);

        showLoading(false);

        // Render all sections
        renderResultMeta(data);
        renderSelectedCard(data.selected_date);
        renderExpectedValue(data.expected_value);
        renderForecastTable(data.forecast);
        renderModelInfo(data.model_info);

        // Chart
        if (typeof renderForecastChart === 'function') {
            renderForecastChart(data.selected_date, data.forecast);
        }

        showResults(true);

        // Scroll to results
        const resultsEl = $('ml-results');
        if (resultsEl) {
            resultsEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }

        // ------------------------------------------------
        // Chat widget ko context bhejo
        // (prediction ke baare me sawaal kar sake user)
        // ------------------------------------------------
        // ------------------------------------------------
        // Chat widget ko context bhejo + auto-insight
        // ------------------------------------------------












        
        if (window.kbChat && typeof window.kbChat.showInsight === 'function') {
            window.kbChat.showInsight({
                market: f.market,
                commodity: f.commodity,
                variety: f.variety,
                state: f.state,
                district: f.district,
            });
        }



















    } catch (err) {
        showLoading(false);
        console.error('Predict error:', err);
        const msg = err.message || 'Prediction fail hui.';
        if (err.details) {
            console.warn('Details:', err.details);
        }
        showError(msg);
        // Warning banner me bhi dikha do agar data issue hai
        if (err.details && err.details.record_count != null) {
            showWarning(`Sirf ${err.details.record_count} records hain. ${msg}`);
        }
    } finally {
        setButtonLoading(predictBtn, false);
    }
}


// ============================================================
// SECTION 9: RESET
// ============================================================

function resetForm() {
    // Clear comboboxes
    ['combo-state', 'combo-district', 'combo-market', 'combo-commodity', 'combo-variety'].forEach(id => {
        if (window.clearCombobox) clearCombobox(id, true);
        if (window.setComboboxOptions) setComboboxOptions(id, []);
    });

    // Reset date and days and quantity
    const dateEl = $('filter-start-date');
    if (dateEl) {
        const tomorrow = new Date();
        tomorrow.setDate(tomorrow.getDate() + 1);
        dateEl.value = tomorrow.toISOString().split('T')[0];
    }

    const daysEl = $('filter-days');
    if (daysEl) daysEl.value = '10';

    const qtyEl = $('filter-quantity');
    if (qtyEl) qtyEl.value = '';

    // Hide results/warning
    showWarning(null);
    showResults(false);
    showLoading(false);

    // Destroy chart
    if (typeof destroyAllCharts === 'function') destroyAllCharts();
}


// ============================================================
// SECTION 10: INIT
// ============================================================

document.addEventListener('DOMContentLoaded', async () => {
    console.log('[ML] Forecast page initializing...');

    // Check combobox library loaded
    if (typeof initCombobox !== 'function') {
        console.error('[ML] combobox.js load nahi hui. Script order check karo.');
        return;
    }

    // 1. Init 5 comboboxes
    initCombobox('combo-state');
    initCombobox('combo-district');
    initCombobox('combo-market');
    initCombobox('combo-commodity');
    initCombobox('combo-variety');

    // 2. Cascading setup
    setupCascading();

    // 3. Buttons
    const predictBtn = $('btn-predict');
    const resetBtn = $('btn-reset-forecast');

    if (predictBtn) predictBtn.addEventListener('click', (e) => {
        e.preventDefault();
        predict();
    });

    if (resetBtn) resetBtn.addEventListener('click', (e) => {
        e.preventDefault();
        resetForm();
    });

    // 4. Preload state options
    const filters = await apiGet('/api/dashboard/filters');
    if (filters && filters.states && filters.states.length > 0) {
        setComboboxOptions('combo-state', filters.states);

        // Agar sirf ek state hai to auto-select
        if (filters.states.length === 1 && typeof selectOption === 'function') {
            selectOption('combo-state', filters.states[0]);
        }
    }

    console.log('[ML] Forecast page ready.');
});