// ============================================================
// KisanBazaar AI — Forecast Chart (Chart.js Wrapper)
// ============================================================
// ML forecast page ka line chart wrapper.
// Dashboard ke charts.js jaisa pattern (consistency).
//
// FEATURES:
//   - Single forecast line chart
//   - Chart instance tracking (memory leak avoid)
//   - destroyChart() helper
//   - Consistent colors, tooltips, axis labels
// ============================================================

// ============================================================
// GLOBAL CHART REGISTRY
// ============================================================

const mlCharts = {
    forecast: null,
};

// Colors (Dashboard se match)
const ML_CHART_COLORS = {
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
// HELPER: DESTROY
// ============================================================

function destroyChart(chartKey) {
    if (mlCharts[chartKey]) {
        mlCharts[chartKey].destroy();
        mlCharts[chartKey] = null;
    }
}

function destroyAllCharts() {
    Object.keys(mlCharts).forEach(key => destroyChart(key));
}


// ============================================================
// HELPER: FORMAT
// ============================================================

function formatPrice(value) {
    if (value === null || value === undefined) return '—';
    return Number(value).toLocaleString('en-IN', {
        maximumFractionDigits: 2,
    });
}


// ============================================================
// MAIN: RENDER FORECAST CHART
// ============================================================

/**
 * Forecast line chart render karta hai.
 *
 * @param {Object} selectedDate - {date, min_price, max_price, modal_price}
 * @param {Array} forecast - [{date, min_price, max_price, modal_price}, ...]
 */
function renderForecastChart(selectedDate, forecast) {
    const canvasId = 'chart-forecast';
    const canvas = document.getElementById(canvasId);
    if (!canvas) {
        console.warn('Chart canvas not found:', canvasId);
        return;
    }

    destroyChart('forecast');

    // Combine selected + forecast into one series
    const allPoints = [];
    if (selectedDate) {
        allPoints.push({
            date: selectedDate.date,
            min_price: selectedDate.min_price,
            max_price: selectedDate.max_price,
            modal_price: selectedDate.modal_price,
            isSelected: true,
        });
    }
    (forecast || []).forEach(f => {
        allPoints.push({
            date: f.date,
            min_price: f.min_price,
            max_price: f.max_price,
            modal_price: f.modal_price,
            isSelected: false,
        });
    });

    if (allPoints.length === 0) {
        console.warn('Forecast chart: koi data nahi hai');
        return;
    }

    const labels = allPoints.map(p => p.date);
    const modalPrices = allPoints.map(p => p.modal_price);
    const minPrices = allPoints.map(p => p.min_price);
    const maxPrices = allPoints.map(p => p.max_price);

    // Point styles: selected date pe bada point
    const modalPointRadius = allPoints.map(p => p.isSelected ? 8 : 4);
    const modalPointBgColor = allPoints.map(p =>
        p.isSelected ? '#f57c00' : ML_CHART_COLORS.modal
    );

    const ctx = canvas.getContext('2d');

    mlCharts.forecast = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Modal Price',
                    data: modalPrices,
                    borderColor: ML_CHART_COLORS.modal,
                    backgroundColor: 'rgba(46, 125, 50, 0.1)',
                    borderWidth: 2.5,
                    fill: true,
                    tension: 0.3,
                    pointRadius: modalPointRadius,
                    pointBackgroundColor: modalPointBgColor,
                    pointBorderColor: '#fff',
                    pointBorderWidth: 2,
                    pointHoverRadius: 9,
                },
                {
                    label: 'Min Price',
                    data: minPrices,
                    borderColor: ML_CHART_COLORS.min,
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
                    borderColor: ML_CHART_COLORS.max,
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
                        color: ML_CHART_COLORS.text,
                    },
                },
                tooltip: {
                    backgroundColor: 'rgba(33, 33, 33, 0.9)',
                    titleColor: 'white',
                    bodyColor: 'white',
                    padding: 10,
                    cornerRadius: 6,
                    callbacks: {
                        title: function (context) {
                            const idx = context[0].dataIndex;
                            const isSelected = allPoints[idx].isSelected;
                            return context[0].label + (isSelected ? ' (Selected)' : '');
                        },
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
                        color: ML_CHART_COLORS.grid,
                        drawBorder: false,
                    },
                    ticks: {
                        color: ML_CHART_COLORS.text,
                        font: { size: 11 },
                        maxRotation: 45,
                        minRotation: 0,
                    },
                },
                y: {
                    beginAtZero: false,
                    grid: {
                        color: ML_CHART_COLORS.grid,
                        drawBorder: false,
                    },
                    ticks: {
                        color: ML_CHART_COLORS.text,
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
// EXPOSE TO WINDOW
// ============================================================

window.mlCharts = mlCharts;
window.renderForecastChart = renderForecastChart;
window.destroyChart = destroyChart;
window.destroyAllCharts = destroyAllCharts;