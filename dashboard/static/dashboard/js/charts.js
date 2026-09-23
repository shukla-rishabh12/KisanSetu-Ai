// ============================================================
// KisanBazaar AI — Dashboard Charts (Chart.js Wrappers)
// ============================================================
// Ye file Chart.js ke charts banane ke wrappers deti hai.
//
// FUNCTIONS:
//   renderPriceTrendChart(data)       → Line chart
//   renderMonthlyMovementChart(data)  → Bar chart
//   destroyChart(chartKey)            → Purana chart destroy
//   destroyAllCharts()                → Sab destroy
//
// WHY THIS FILE:
//   - Chart creation logic dashboard.js se alag
//   - Chart instances globally track hote hain (memory leak avoid)
//   - Consistent colors, tooltips, axis labels
//   - Ek jagah change karne se saare charts update
//
// DEPENDENCY:
//   Chart.js (CDN se index.html me load hota hai)
// ============================================================

// ============================================================
// GLOBAL CHART REGISTRY
// ============================================================
// Ek global object jo saare chart instances rakhta hai.
// Naya chart banane se pehle purana destroy karna zaroori hai,
// warna canvas pe overlap ho jata hai aur memory leak hota hai.
// ============================================================

const kbCharts = {
    priceTrend: null,
    monthlyMovement: null,
};


// ============================================================
// COLOR PALETTE (CSS variables se match karta hai)
// ============================================================
const CHART_COLORS = {
    primary: '#2e7d32',
    primaryDark: '#1b5e20',
    primaryLight: '#4caf50',
    min: '#1976d2',
    max: '#c62828',
    modal: '#2e7d32',
    grid: '#e0e0e0',
    text: '#666666',
};


// ============================================================
// HELPER: DESTROY A CHART
// ============================================================

/**
 * Purana chart destroy karta hai (agar exist karta ho).
 * Naya chart banane se pehle ye call karna MUST hai.
 *
 * @param {string} chartKey - Key in kbCharts object (e.g., "priceTrend")
 */
function destroyChart(chartKey) {
    if (kbCharts[chartKey]) {
        kbCharts[chartKey].destroy();
        kbCharts[chartKey] = null;
    }
}


/**
 * Saare charts destroy karta hai.
 * Reset button ya page unload pe useful.
 */
function destroyAllCharts() {
    Object.keys(kbCharts).forEach(key => destroyChart(key));
}


// ============================================================
// HELPER: NUMBER FORMATTER
// ============================================================

/**
 * Price ko readable format me convert karta hai.
 * Example: 2750 → "2,750"
 *
 * @param {number} value
 * @returns {string}
 */
function formatPrice(value) {
    if (value === null || value === undefined) return '—';
    return Number(value).toLocaleString('en-IN', {
        maximumFractionDigits: 2,
    });
}


// ============================================================
// CHART 1: PRICE TREND (LINE CHART)
// ============================================================
/**
 * Price trend line chart render karta hai.
 *
 * Expected data format (services.py se):
 *   [
 *     { date: "2026-09-01", modal_price: 2750, min_price: 2500, max_price: 3000 },
 *     { date: "2026-09-02", modal_price: 2780, min_price: 2520, max_price: 3010 },
 *     ...
 *   ]
 *
 * @param {Array<Object>} data - Trend data points
 */
function renderPriceTrendChart(data) {
    const canvasId = 'chart-price-trend';
    const canvas = document.getElementById(canvasId);
    if (!canvas) {
        console.warn('Chart canvas not found:', canvasId);
        return;
    }

    // Purana chart destroy karo
    destroyChart('priceTrend');

    // Data empty? To chart mat banao
    if (!data || data.length === 0) {
        console.warn('Price trend chart: koi data nahi hai');
        return;
    }

    // X-axis labels (dates)
    const labels = data.map(d => d.date);

    // Y-axis datasets
    const modalPrices = data.map(d => d.modal_price);
    const minPrices = data.map(d => d.min_price);
    const maxPrices = data.map(d => d.max_price);

    // Chart context
    const ctx = canvas.getContext('2d');

    // Chart create karo
    kbCharts.priceTrend = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Modal Price',
                    data: modalPrices,
                    borderColor: CHART_COLORS.modal,
                    backgroundColor: 'rgba(46, 125, 50, 0.1)',
                    borderWidth: 2.5,
                    fill: true,
                    tension: 0.3,
                    pointRadius: 3,
                    pointHoverRadius: 6,
                },
                {
                    label: 'Min Price',
                    data: minPrices,
                    borderColor: CHART_COLORS.min,
                    backgroundColor: 'transparent',
                    borderWidth: 1.5,
                    borderDash: [5, 4],
                    fill: false,
                    tension: 0.3,
                    pointRadius: 2,
                    pointHoverRadius: 5,
                },
                {
                    label: 'Max Price',
                    data: maxPrices,
                    borderColor: CHART_COLORS.max,
                    backgroundColor: 'transparent',
                    borderWidth: 1.5,
                    borderDash: [5, 4],
                    fill: false,
                    tension: 0.3,
                    pointRadius: 2,
                    pointHoverRadius: 5,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        boxWidth: 12,
                        padding: 12,
                        font: { size: 12 },
                        color: CHART_COLORS.text,
                    },
                },
                tooltip: {
                    backgroundColor: 'rgba(33, 33, 33, 0.9)',
                    titleColor: 'white',
                    bodyColor: 'white',
                    padding: 10,
                    cornerRadius: 6,
                    callbacks: {
                        label: function (context) {
                            const label = context.dataset.label || '';
                            const value = context.parsed.y;
                            return `${label}: ₹${formatPrice(value)}`;
                        },
                    },
                },
            },
            scales: {
                x: {
                    grid: {
                        color: CHART_COLORS.grid,
                        drawBorder: false,
                    },
                    ticks: {
                        color: CHART_COLORS.text,
                        font: { size: 11 },
                        maxRotation: 45,
                        minRotation: 0,
                    },
                },
                y: {
                    beginAtZero: false,
                    grid: {
                        color: CHART_COLORS.grid,
                        drawBorder: false,
                    },
                    ticks: {
                        color: CHART_COLORS.text,
                        font: { size: 11 },
                        callback: function (value) {
                            return '₹' + formatPrice(value);
                        },
                    },
                },
            },
        },
    });
}


// ============================================================
// CHART 2: MONTHLY MOVEMENT (BAR CHART)
// ============================================================
/**
 * Monthly movement bar chart render karta hai.
 *
 * Expected data format (services.py se):
 *   [
 *     { month: "2026-01", avg_modal_price: 2650, record_count: 22 },
 *     { month: "2026-02", avg_modal_price: 2700, record_count: 24 },
 *     ...
 *   ]
 *
 * @param {Array<Object>} data - Monthly data points
 */
function renderMonthlyMovementChart(data) {
    const canvasId = 'chart-monthly-movement';
    const canvas = document.getElementById(canvasId);
    if (!canvas) {
        console.warn('Chart canvas not found:', canvasId);
        return;
    }

    // Purana chart destroy karo
    destroyChart('monthlyMovement');

    // Data empty?
    if (!data || data.length === 0) {
        console.warn('Monthly movement chart: koi data nahi hai');
        return;
    }

    // X-axis labels (months)
    const labels = data.map(d => d.month);

    // Y-axis data
    const avgPrices = data.map(d => d.avg_modal_price);

    const ctx = canvas.getContext('2d');

    // Bar chart
    kbCharts.monthlyMovement = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Avg Modal Price',
                    data: avgPrices,
                    backgroundColor: 'rgba(46, 125, 50, 0.75)',
                    borderColor: CHART_COLORS.primary,
                    borderWidth: 1,
                    borderRadius: 4,
                    hoverBackgroundColor: CHART_COLORS.primaryDark,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false,  // Single dataset ke liye legend ki zaroorat nahi
                },
                tooltip: {
                    backgroundColor: 'rgba(33, 33, 33, 0.9)',
                    titleColor: 'white',
                    bodyColor: 'white',
                    padding: 10,
                    cornerRadius: 6,
                    callbacks: {
                        label: function (context) {
                            const value = context.parsed.y;
                            const recordCount = data[context.dataIndex].record_count;
                            return [
                                `Avg: ₹${formatPrice(value)}`,
                                `Records: ${recordCount}`,
                            ];
                        },
                    },
                },
            },
            scales: {
                x: {
                    grid: {
                        display: false,
                    },
                    ticks: {
                        color: CHART_COLORS.text,
                        font: { size: 11 },
                    },
                },
                y: {
                    beginAtZero: false,
                    grid: {
                        color: CHART_COLORS.grid,
                        drawBorder: false,
                    },
                    ticks: {
                        color: CHART_COLORS.text,
                        font: { size: 11 },
                        callback: function (value) {
                            return '₹' + formatPrice(value);
                        },
                    },
                },
            },
        },
    });
}


// ============================================================
// EXPOSE FUNCTIONS GLOBALLY
// ============================================================
// dashboard.js me ye functions use karne ke liye global scope
// me available hone chahiye. Ye script tag se load hoti hai,
// isliye default global scope me hai, lekin explicitly bhi rakh dete hain.
// ============================================================

window.kbCharts = kbCharts;
window.renderPriceTrendChart = renderPriceTrendChart;
window.renderMonthlyMovementChart = renderMonthlyMovementChart;
window.destroyChart = destroyChart;
window.destroyAllCharts = destroyAllCharts;