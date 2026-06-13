// ── Chart rendering for session_detail.html ──────────────────────
// Depends on: Chart.js, chartjs-plugin-zoom, theme.js (getThemeColors)

const COLORS = ['#3b82f6','#ef4444','#10b981','#f59e0b','#8b5cf6','#06b6d4',
                '#f97316','#6366f1','#14b8a6','#e11d48','#a855f7','#0891b2',
                '#dc2626','#0d9488','#78716c','#eab308','#475569','#ec4899',
                '#22d3ee','#fb923c','#78350f','#64748b','#059669','#84cc16'];

const chartInstances = {};
let cachedData = null;

const CHART_TITLES = {
    lapTime: 'Lap Times',
    delta: 'Delta to Best',
    sector: 'Sector Breakdown',
    speed: 'Speed Trap',
    boxPlot: 'Lap Time Distribution',
    pitStops: 'Pit Stops',
    position: 'Position Progression',
    driverS1: 'S1 by Driver',
    driverS2: 'S2 by Driver',
    driverS3: 'S3 by Driver',
    driverLap: 'Lap Time by Driver',
    consistency: 'Lap Time Consistency (Std Dev)',
    strategy: 'Strategy (Stint Map)',
};

function fmtTime(seconds) {
    if (seconds == null || isNaN(seconds)) return '-';
    const m = Math.floor(seconds / 60);
    const s = (seconds % 60).toFixed(3);
    return m + ':' + s.padStart(6, '0');
}

// Color mode state
window.colorMode = 'number'; // 'number' | 'model'
window._carModelMap = {}; // car_number → car_model
window._carColorMap = {}; // car_number → series_color (explicit)
window._carModelColorMap = {}; // car_number → model_color (from DB, derived from model)

function buildCarModelMap(data) {
    window._carModelMap = {};
    window._carColorMap = {};
    window._carModelColorMap = {};
    (data.per_car || []).forEach(function(c) {
        if (c.car_model) window._carModelMap[c.car_number] = c.car_model;
        if (c.series_color) window._carColorMap[c.car_number] = c.series_color;
        if (c.model_color) window._carModelColorMap[c.car_number] = c.model_color;
    });
    (data.car_stints || []).forEach(function(c) {
        if (c.car_model && !window._carModelMap[c.car_number]) window._carModelMap[c.car_number] = c.car_model;
        if (c.series_color && !window._carColorMap[c.car_number]) window._carColorMap[c.car_number] = c.series_color;
        if (c.model_color && !window._carModelColorMap[c.car_number]) window._carModelColorMap[c.car_number] = c.model_color;
    });
}

function getModelColor(model) {
    if (!model) return '#64748b';
    var hash = 0;
    for (var i = 0; i < model.length; i++) {
        hash = ((hash << 5) - hash) + model.charCodeAt(i);
        hash |= 0;
    }
    return COLORS[Math.abs(hash) % COLORS.length];
}

function getCarColor(carNum, carModel) {
    // Check explicit series_color override first (applies to both modes)
    var explicitColor = window._carColorMap[carNum];
    if (explicitColor && explicitColor.match(/^#[0-9a-f]{6}$/i)) return explicitColor;

    if (window.colorMode === 'model') {
        // Use stored model_color from DB (derived from model name hash)
        var mc = window._carModelColorMap[carNum];
        if (mc && mc.match(/^#[0-9a-f]{6}$/i)) return mc;
        // Fall back to hash from model name
        var model = carModel || window._carModelMap[carNum] || '';
        return getModelColor(model);
    }
    var idx = parseInt(carNum) || 0;
    return COLORS[idx % COLORS.length];
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function lightenHex(hex, percent) {
    const num = parseInt(hex.replace('#', ''), 16);
    const amt = Math.round(2.55 * percent);
    const R = Math.min(255, Math.max(0, (num >> 16) + amt));
    const G = Math.min(255, Math.max(0, ((num >> 8) & 0x00FF) + amt));
    const B = Math.min(255, Math.max(0, (num & 0x0000FF) + amt));
    return 'rgb(' + R + ',' + G + ',' + B + ')';
}

function themeScales() {
    const tc = window.getThemeColors ? window.getThemeColors() : { grid: 'rgba(0,0,0,0.1)', gridMajor: 'rgba(0,0,0,0.2)', text: '#64748b' };
    return {
        x: {
            ticks: { color: tc.text, font: { family: 'JetBrains Mono', size: 10 } },
            grid: { color: tc.grid, lineWidth: 1.5 },
            border: { color: tc.gridMajor }
        },
        y: {
            ticks: { color: tc.text, font: { family: 'JetBrains Mono', size: 10 } },
            grid: { color: tc.grid, lineWidth: 1.5 },
            border: { color: tc.gridMajor }
        }
    };
}

function themeTooltip() {
    const tc = window.getThemeColors ? window.getThemeColors() : { tooltipBg: 'rgba(0,0,0,0.9)', tooltipText: '#fff', accentCyan: '#00e5ff' };
    return {
        backgroundColor: tc.tooltipBg,
        titleColor: tc.tooltipText,
        bodyColor: tc.tooltipText,
        borderColor: tc.accentCyan,
        borderWidth: 1,
        titleFont: { family: 'JetBrains Mono', size: 12 },
        bodyFont: { family: 'JetBrains Mono', size: 11 },
        padding: 10
    };
}

function chartZoomOptions() {
    return {
        zoom: {
            zoom: {
                wheel: { enabled: true },
                pinch: { enabled: true },
                drag: {
                    enabled: true,
                    mode: 'y'
                },
                mode: 'y'
            },
            pan: {
                enabled: true,
                mode: 'y',
                modifierKey: 'shift'
            }
        }
    };
}

function setupZoomReset(chart) {
    if (!chart || !chart.canvas) return;
    chart.canvas.addEventListener('dblclick', function(e) {
        if (e.button === 0) {
            chart.resetZoom();
        }
    });
}

async function loadChart() {
    const container = document.getElementById('chartCard');
    if (!container) return;
    const sessionId = container.dataset.sessionId;
    if (!sessionId) return;

    if (!cachedData) {
        const grid = document.getElementById('chartGrid');
        const placeholder = document.createElement('div');
        placeholder.id = 'chart-loading';
        placeholder.className = 'text-center py-8 text-theme-secondary';
        placeholder.innerHTML = '<svg class="animate-spin inline-block w-5 h-5 mr-2" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>Loading chart data\u2026';
        grid.appendChild(placeholder);
        try {
            const resp = await fetch(`/api/sessions/${sessionId}/analytics`);
            cachedData = await resp.json();
        } finally {
            const el = document.getElementById('chart-loading');
            if (el) el.remove();
        }
    }
    const data = cachedData;

    const posLabel = document.querySelector('.chart-cb-position');
    if (posLabel) posLabel.style.display = data.session_type === 'Race' ? '' : 'none';
    if (data.session_type !== 'Race') {
        const posCb = document.querySelector('.chart-cb[data-chart="position"]');
        if (posCb && posCb.checked) { posCb.checked = false; destroyChart('position'); removePanel('position'); }
    }

    renderCheckedCharts(data);
}

function cleanLapTimes(data) {
    return data.lap_times.filter(l => {
        if (l.out_lap || l.in_lap) return false;
        if (l.sc_lap) return false;
        return true;
    });
}

function destroyChart(type) {
    if (chartInstances[type]) { chartInstances[type].destroy(); delete chartInstances[type]; }
}

function removePanel(type) {
    const panel = document.getElementById('chartPanel-' + type);
    if (panel) panel.remove();
}

function ensurePanel(type) {
    if (document.getElementById('chartPanel-' + type)) return;
    const grid = document.getElementById('chartGrid');
    const panel = document.createElement('div');
    panel.id = 'chartPanel-' + type;
    panel.className = 'chart-panel';
    panel.innerHTML = `<div class="chart-panel-header">${CHART_TITLES[type] || type}</div>`
        + `<div class="p-4 chart-container"><canvas id="chartCanvas-${type}"></canvas></div>`;
    grid.appendChild(panel);
}

function computeBoxPlot(values) {
    const sorted = [...values].sort((a, b) => a - b);
    const n = sorted.length;
    if (n === 0) return null;
    return {
        min: sorted[0],
        q1: sorted[Math.floor(n * 0.25)],
        median: sorted[Math.floor(n * 0.5)],
        q3: sorted[Math.floor(n * 0.75)],
        max: sorted[n - 1],
        count: n
    };
}

function buildDriverBoxChart(ctx, data, field, title, yTitle, chartKey) {
    const ts = themeScales();
    const tt = themeTooltip();
    const tc = window.getThemeColors ? window.getThemeColors() : { text: '#64748b' };

    const useLapTime = field === 'lap_time';
    const drivers = {};
    (data.lap_times || []).forEach(l => {
        if (l.out_lap || l.in_lap || l.sc_lap) return;
        const val = useLapTime ? l.lap_time : l[field];
        if (!val || val <= 0) return;
        if (!drivers[l.driver_name]) drivers[l.driver_name] = [];
        drivers[l.driver_name].push(val);
    });

    const entries = Object.entries(drivers).map(([name, vals]) => ({
        name, stats: computeBoxPlot(vals)
    })).filter(e => e.stats && e.stats.count >= 2)
      .sort((a, b) => a.stats.median - b.stats.median);

    if (entries.length === 0) {
        chartInstances[chartKey] = new Chart(ctx, {
            type: 'bar', data: { datasets: [] },
            options: { responsive: true, plugins: { title: { display: true, text: 'No ' + title + ' data', color: tc.text } } }
        });
        return;
    }

    const labels = entries.map(e => e.name);
    const colors = entries.map((_, i) => COLORS[i % COLORS.length]);

    const minVals = entries.map(e => e.stats.min);
    const whiskerLow = entries.map(e => e.stats.q1 - e.stats.min);
    const boxLow = entries.map(e => e.stats.median - e.stats.q1);
    const boxHigh = entries.map(e => e.stats.q3 - e.stats.median);
    const whiskerHigh = entries.map(e => e.stats.max - e.stats.q3);

    chartInstances[chartKey] = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [
                { label: 'Min', data: minVals, backgroundColor: 'transparent', stack: 'box' },
                { label: '', data: whiskerLow, backgroundColor: 'rgba(180,180,180,0.4)',
                  stack: 'box', borderColor: '#999', borderWidth: { top: 1, right: 1, left: 1, bottom: 0 } },
                { label: '', data: boxLow, backgroundColor: colors.map(c => c + '99'),
                  stack: 'box', borderColor: colors, borderWidth: { top: 0, right: 1, left: 1, bottom: 0 } },
                { label: '', data: boxHigh, backgroundColor: colors.map(c => c + '66'),
                  stack: 'box', borderColor: colors, borderWidth: { top: 1, right: 1, left: 1, bottom: 1 } },
                { label: '', data: whiskerHigh, backgroundColor: 'rgba(180,180,180,0.4)',
                  stack: 'box', borderColor: '#999', borderWidth: { top: 1, right: 1, left: 1, bottom: 0 } },
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: { ...tt, callbacks: {
                    label: function(c) {
                        if (c.datasetIndex !== 2) return '';
                        const e = entries[c.dataIndex];
                        const fmt = useLapTime ? fmtTime : v => v.toFixed(3) + 's';
                        return [
                            e.name,
                            'Min: ' + (useLapTime ? fmtTime(e.stats.min) : e.stats.min.toFixed(3) + 's'),
                            'Q1: ' + (useLapTime ? fmtTime(e.stats.q1) : e.stats.q1.toFixed(3) + 's'),
                            'Median: ' + (useLapTime ? fmtTime(e.stats.median) : e.stats.median.toFixed(3) + 's'),
                            'Q3: ' + (useLapTime ? fmtTime(e.stats.q3) : e.stats.q3.toFixed(3) + 's'),
                            'Max: ' + (useLapTime ? fmtTime(e.stats.max) : e.stats.max.toFixed(3) + 's'),
                            'Laps: ' + e.stats.count,
                        ];
                    }
                } },
                ...chartZoomOptions()
            },
            scales: {
                x: { ...ts.x, stacked: true, ticks: { ...ts.x.ticks, maxRotation: 45 } },
                y: { ...ts.y, stacked: true, beginAtZero: false,
                     title: { display: true, text: yTitle, color: tc.text },
                     ticks: { ...ts.y.ticks, callback: v => useLapTime ? fmtTime(v) : v.toFixed(3) } }
            }
        }
    });
    setupZoomReset(chartInstances[chartKey]);
}

function renderCheckedCharts(data) {
    buildCarModelMap(data);
    document.querySelectorAll('.chart-cb').forEach(cb => {
        const type = cb.dataset.chart;
        if (cb.checked) {
            ensurePanel(type);
            const canvas = document.getElementById('chartCanvas-' + type);
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            destroyChart(type);
            renderers[type](ctx, data);
        } else {
            destroyChart(type);
            removePanel(type);
        }
    });
}

const renderers = {
    lapTime: function(ctx, data) {
        const ts = themeScales();
        const tt = themeTooltip();
        const tc = window.getThemeColors ? window.getThemeColors() : { text: '#64748b' };

        const laps = data.lap_times || [];
        const cars = {};
        laps.forEach(l => {
            if (!l.lap_time) return;
            if (!cars[l.car_number]) cars[l.car_number] = { laps: [] };
            cars[l.car_number].laps.push({ x: l.session_time, y: l.lap_time, driver: l.driver_name });
        });
        Object.values(cars).forEach(c => c.laps.sort((a, b) => a.x - b.x));

        const bestLine = data.overall_best_lap ? [{
            label: 'Session Best',
            data: Object.values(cars).flatMap(c => [{ x: c.laps[0]?.x, y: data.overall_best_lap },
                                                     { x: c.laps[c.laps.length-1]?.x, y: data.overall_best_lap }]).filter(p => p.x),
            borderColor: '#a78bfa', borderDash: [6, 3], borderWidth: 2, pointRadius: 0, fill: false
        }] : [];

        const datasets = Object.entries(cars).map(([car, info]) => ({
            label: `#${car}`,
            data: info.laps,
            borderColor: getCarColor(car),
            backgroundColor: 'transparent',
            tension: 0.1, pointRadius: 2, spanGaps: false,
        })).concat(bestLine);

        chartInstances.lapTime = new Chart(ctx, {
            type: 'line',
            data: { datasets },
            options: {
                responsive: true, maintainAspectRatio: false,
                interaction: { mode: 'nearest', intersect: false },
                plugins: {
                    legend: { labels: { color: tc.text, font: { family: 'JetBrains Mono', size: 10 } } },
                    tooltip: { ...tt, callbacks: { label: c => `${c.dataset.label} ${c.raw.driver || ''}: ${fmtTime(c.raw.y)}` } },
                    ...chartZoomOptions()
                },
                scales: {
                    x: { ...ts.x, title: { display: true, text: 'Session Time (min)', color: tc.text }, type: 'linear', ticks: { ...ts.x.ticks, callback: v => (v / 60).toFixed(1) }, offset: false },
                    y: { ...ts.y, title: { display: true, text: 'Lap Time', color: tc.text }, ticks: { ...ts.y.ticks, callback: v => fmtTime(v) }, beginAtZero: false }
                }
            }
        });
        setupZoomReset(chartInstances.lapTime);
    },

    delta: function(ctx, data) {
        const ts = themeScales();
        const tt = themeTooltip();
        const tc = window.getThemeColors ? window.getThemeColors() : { text: '#64748b' };

        if (!data.overall_best_lap) {
            chartInstances.delta = new Chart(ctx, { type: 'line', data: { datasets: [] },
                options: { responsive: true, plugins: { title: { display: true, text: 'No best lap data', color: tc.text } } } });
            return;
        }
        const laps = data.lap_times || [];
        const cars = {};
        laps.forEach(l => {
            if (!l.lap_time) return;
            if (!cars[l.car_number]) cars[l.car_number] = { laps: [] };
            cars[l.car_number].laps.push({ x: l.session_time, y: l.lap_time - data.overall_best_lap, driver: l.driver_name });
        });
        Object.values(cars).forEach(c => c.laps.sort((a, b) => a.x - b.x));

        const datasets = Object.entries(cars).map(([car, info]) => ({
            label: `#${car}`,
            data: info.laps,
            borderColor: getCarColor(car),
            backgroundColor: 'transparent',
            tension: 0.1, pointRadius: 2, spanGaps: false,
        }));

        chartInstances.delta = new Chart(ctx, {
            type: 'line',
            data: { datasets },
            options: {
                responsive: true, maintainAspectRatio: false,
                interaction: { mode: 'nearest', intersect: false },
                plugins: {
                    legend: { labels: { color: tc.text, font: { family: 'JetBrains Mono', size: 10 } } },
                    tooltip: { ...tt, callbacks: { label: c => {
                        const v = c.raw.y;
                        return `${c.dataset.label} ${c.raw.driver || ''}: ${v >= 0 ? '+' : ''}${v.toFixed(3)}s`;
                    } } },
                    ...chartZoomOptions()
                },
                scales: {
                    x: { ...ts.x, title: { display: true, text: 'Session Time (min)', color: tc.text }, type: 'linear', ticks: { callback: v => (v / 60).toFixed(1) } },
                    y: { ...ts.y, title: { display: true, text: 'Gap to Best (s)', color: tc.text },
                         ticks: { ...ts.y.ticks, callback: v => (v >= 0 ? '+' : '') + v.toFixed(3) }, beginAtZero: false }
                }
            }
        });
        setupZoomReset(chartInstances.delta);
    },

    sector: function(ctx, data) {
        const ts = themeScales();
        const tt = themeTooltip();
        const tc = window.getThemeColors ? window.getThemeColors() : { text: '#64748b' };

        const cars = data.per_car.filter(c => c.best_s1 || c.best_s2 || c.best_s3);
        const labels = cars.map(c => `#${c.car_number}`);
        const s1 = cars.map(c => c.best_s1 || 0);
        const s2 = cars.map(c => c.best_s2 || 0);
        const s3 = cars.map(c => c.best_s3 || 0);
        const actualBest = cars.map((c, i) => ({ x: i, y: c.best_lap || 0 }));

        chartInstances.sector = new Chart(ctx, {
            type: 'bar',
            data: {
                labels,
                datasets: [
                    { label: 'Sector 1', data: s1, backgroundColor: '#3498db', stack: 'sectors' },
                    { label: 'Sector 2', data: s2, backgroundColor: '#2ecc71', stack: 'sectors' },
                    { label: 'Sector 3', data: s3, backgroundColor: '#f39c12', stack: 'sectors' },
                    { label: 'Actual Best Lap', data: actualBest, type: 'line',
                      borderColor: '#e74c3c', backgroundColor: 'transparent',
                      pointRadius: 4, pointBorderColor: '#e74c3c', pointBackgroundColor: '#fff',
                      pointBorderWidth: 2, order: 0, tension: 0 },
                ]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: {
                    legend: { labels: { color: tc.text, font: { family: 'JetBrains Mono', size: 10 } } },
                    tooltip: { ...tt, callbacks: {
                        label: c => c.dataset.label === 'Actual Best Lap' ? `Best Lap: ${fmtTime(c.raw.y)}` : `${c.dataset.label}: ${c.raw.toFixed(3)}s`
                    } },
                    ...chartZoomOptions()
                },
                scales: {
                    x: { ...ts.x, stacked: true, ticks: { ...ts.x.ticks, maxRotation: 45 } },
                    y: { ...ts.y, stacked: true, title: { display: true, text: 'Time', color: tc.text }, ticks: { ...ts.y.ticks, callback: v => fmtTime(v) } }
                }
            }
        });
        setupZoomReset(chartInstances.sector);
    },

    speed: function(ctx, data) {
        const ts = themeScales();
        const tt = themeTooltip();
        const tc = window.getThemeColors ? window.getThemeColors() : { text: '#64748b' };

        const cars = data.per_car.filter(c => c.top_speed).sort((a, b) => b.top_speed - a.top_speed);
        const labels = cars.map(c => `#${c.car_number}`);
        const speeds = cars.map(c => c.top_speed);

        chartInstances.speed = new Chart(ctx, {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    label: 'Top Speed (km/h)',
                    data: speeds,
                    backgroundColor: cars.map(c => getCarColor(c.car_number)),
                    borderColor: cars.map(c => getCarColor(c.car_number)),
                    borderWidth: 1,
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                indexAxis: 'y',
                plugins: {
                    legend: { display: false },
                    tooltip: { ...tt, callbacks: { label: c => `${c.raw} km/h` } },
                    ...chartZoomOptions()
                },
                scales: {
                    x: { ...ts.x, title: { display: true, text: 'Speed (km/h)', color: tc.text }, beginAtZero: false },
                    y: { ...ts.y, title: { display: false } }
                }
            }
        });
        setupZoomReset(chartInstances.speed);
    },

    boxPlot: function(ctx, data) {
        const ts = themeScales();
        const tt = themeTooltip();
        const tc = window.getThemeColors ? window.getThemeColors() : { text: '#64748b' };

        const cars = data.per_car.filter(c => c.min_lap != null && c.q1 != null && c.median != null
                                              && c.q3 != null && c.max_lap != null);
        const labels = cars.map(c => `#${c.car_number}`);
        const carColors = cars.map(c => getCarColor(c.car_number));

        const minVals = cars.map(c => c.min_lap);
        const whiskerLow = cars.map(c => c.q1 - c.min_lap);
        const boxLow = cars.map(c => c.median - c.q1);
        const boxHigh = cars.map(c => c.q3 - c.median);
        const whiskerHigh = cars.map(c => c.max_lap - c.q3);

        chartInstances.boxPlot = new Chart(ctx, {
            type: 'bar',
            data: {
                labels,
                datasets: [
                    { label: 'Min', data: minVals, backgroundColor: 'transparent', stack: 'box' },
                    { label: '', data: whiskerLow, backgroundColor: 'rgba(180,180,180,0.4)',
                      stack: 'box', borderColor: '#999', borderWidth: { top: 1, right: 1, left: 1, bottom: 0 } },
                    { label: '', data: boxLow, backgroundColor: carColors.map(c => c + '99'),
                      stack: 'box', borderColor: carColors, borderWidth: { top: 0, right: 1, left: 1, bottom: 0 } },
                    { label: '', data: boxHigh, backgroundColor: carColors.map(c => c + '66'),
                      stack: 'box', borderColor: carColors, borderWidth: { top: 1, right: 1, left: 1, bottom: 1 } },
                    { label: '', data: whiskerHigh, backgroundColor: 'rgba(180,180,180,0.4)',
                      stack: 'box', borderColor: '#999', borderWidth: { top: 1, right: 1, left: 1, bottom: 0 } },
                ]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        ...tt,
                        callbacks: {
                            label: function(c) {
                                if (c.datasetIndex !== 2) return '';
                                const car = cars[c.dataIndex];
                                return [
                                    'Min: ' + fmtTime(car.min_lap),
                                    'Q1: ' + fmtTime(car.q1),
                                    'Median: ' + fmtTime(car.median),
                                    'Q3: ' + fmtTime(car.q3),
                                    'Max: ' + fmtTime(car.max_lap),
                                ];
                            }
                        }
                    },
                    ...chartZoomOptions()
                },
                scales: {
                    x: { ...ts.x, stacked: true, ticks: { ...ts.x.ticks, maxRotation: 45 } },
                    y: { ...ts.y, stacked: true, beginAtZero: false,
                         title: { display: true, text: 'Lap Time', color: tc.text },
                         ticks: { ...ts.y.ticks, callback: v => fmtTime(v) } }
                }
            }
        });
        setupZoomReset(chartInstances.boxPlot);
    },

    pitStops: function(ctx, data) {
        const ts = themeScales();
        const tt = themeTooltip();
        const tc = window.getThemeColors ? window.getThemeColors() : { text: '#64748b' };

        if (!data.pit_stops || data.pit_stops.length === 0) {
            chartInstances.pitStops = new Chart(ctx, {
                type: 'bar', data: { datasets: [] },
                options: { responsive: true, plugins: { title: { display: true, text: 'No pit stops recorded', color: tc.text } } }
            });
            return;
        }

        const labels = data.pit_stops.map(p => {
            const t = Number.isFinite(p.pit_time) ? p.pit_time.toFixed(1) + 's' : 'N/A';
            return `#${p.car_number} L${p.in_lap}→L${p.out_lap} (${t})`;
        });
        const pitTimes = data.pit_stops.map(p => Number.isFinite(p.pit_time) ? Math.max(0, p.pit_time) : 0);
        const barColors = data.pit_stops.map(p => getCarColor(p.car_number));

        chartInstances.pitStops = new Chart(ctx, {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    label: 'Pit Lane Time (s)',
                    data: pitTimes,
                    backgroundColor: barColors,
                    borderColor: barColors.map(c => c + 'cc'),
                    borderWidth: 1,
                    barPercentage: 0.65,
                    categoryPercentage: 0.8,
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                indexAxis: 'y',
                plugins: {
                    legend: { display: false },
                    tooltip: { ...tt, callbacks: {
                        label: c => {
                            const p = data.pit_stops[c.dataIndex];
                            return [
                                `Car: #${p.car_number} / ${p.driver_name}`,
                                `In Lap: ${p.in_lap} → Out Lap: ${p.out_lap}`,
                                `Pit Lane Time: ${Number.isFinite(p.pit_time) ? p.pit_time.toFixed(1) + 's' : 'N/A'}`,
                            ];
                        }
                    } },
                    ...chartZoomOptions()
                },
                scales: {
                    x: { ...ts.x, title: { display: true, text: 'Pit Lane Time (s)', color: tc.text }, beginAtZero: true },
                    y: { ...ts.y, ticks: { ...ts.y.ticks, font: { family: 'JetBrains Mono', size: 10 } } }
                }
            }
        });

        const panel = document.getElementById('chartPanel-pitStops');
        if (panel) {
            const container = panel.querySelector('.chart-container');
            if (container) container.style.minHeight = '600px';
        }

        setupZoomReset(chartInstances.pitStops);
    },

    position: function(ctx, data) {
        const ts = themeScales();
        const tt = themeTooltip();
        const tc = window.getThemeColors ? window.getThemeColors() : { text: '#64748b', grid: 'rgba(0,0,0,0.1)' };

        if (!data.position_progression) {
            chartInstances.position = new Chart(ctx, {
                type: 'line', data: { datasets: [] },
                options: { responsive: true, plugins: { title: { display: true, text: 'Position chart only available for Race sessions', color: tc.text } } }
            });
            return;
        }

        const pp = data.position_progression;
        // Pre-build O(1) lookup map for driver names
        const lapDriverMap = {};
        (data.lap_times || []).forEach(l => {
            lapDriverMap[l.car_number + ':' + l.lap_number] = l.driver_name;
        });

        const datasets = Object.entries(pp.cars).map(([car, positions]) => ({
            label: `#${car}`,
            data: positions.map(p => ({
                x: p.lap,
                y: p.position,
                driver: lapDriverMap[car + ':' + p.lap] || '',
            })),
            borderColor: getCarColor(car),
            backgroundColor: 'transparent',
            tension: 0, pointRadius: 3,
        }));

        chartInstances.position = new Chart(ctx, {
            type: 'line',
            data: { datasets },
            options: {
                responsive: true, maintainAspectRatio: false,
                interaction: { mode: 'nearest', intersect: false },
                plugins: {
                    legend: { labels: { color: tc.text, font: { family: 'JetBrains Mono', size: 10 } } },
                    tooltip: { ...tt, callbacks: { label: c => `${c.dataset.label} ${c.raw.driver || ''}: P${c.raw.y}` } },
                    ...chartZoomOptions()
                },
                scales: {
                    x: { ...ts.x, title: { display: true, text: 'Lap Number', color: tc.text }, type: 'linear', ticks: { stepSize: 1 } },
                    y: { ...ts.y, title: { display: true, text: 'Position', color: tc.text }, reverse: true,
                         ticks: { stepSize: 1 }, min: 1,
                         grid: { color: c => c.tick.value === 1 ? 'rgba(231,76,60,0.5)' : tc.grid } }
                }
            }
        });
        setupZoomReset(chartInstances.position);
    },
    driverS1: function(ctx, data) { buildDriverBoxChart(ctx, data, 'sector_1', 'Sector 1', 'Sector 1 Time', 'driverS1'); },
    driverS2: function(ctx, data) { buildDriverBoxChart(ctx, data, 'sector_2', 'Sector 2', 'Sector 2 Time', 'driverS2'); },
    driverS3: function(ctx, data) { buildDriverBoxChart(ctx, data, 'sector_3', 'Sector 3', 'Sector 3 Time', 'driverS3'); },
    driverLap: function(ctx, data) { buildDriverBoxChart(ctx, data, 'lap_time', 'Lap Time', 'Lap Time', 'driverLap'); },

    consistency: function(ctx, data) {
        const ts = themeScales();
        const tt = themeTooltip();
        const tc = window.getThemeColors ? window.getThemeColors() : { text: '#64748b' };

        const entries = (data.driver_consistency || [])
            .filter(d => d.std_dev > 0 && d.lap_count >= 2);

        if (entries.length === 0) {
            chartInstances.consistency = new Chart(ctx, {
                type: 'bar', data: { datasets: [] },
                options: { responsive: true, plugins: { title: { display: true, text: 'No consistency data (need 2+ laps per driver)', color: tc.text } } }
            });
            return;
        }

        const labels = entries.map(d => d.driver_name);
        const stdDevs = entries.map(d => d.std_dev);
        const colors = entries.map((_, i) => COLORS[i % COLORS.length]);

        chartInstances.consistency = new Chart(ctx, {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    label: 'Std Dev (s)',
                    data: stdDevs,
                    backgroundColor: colors.map(c => c + '99'),
                    borderColor: colors,
                    borderWidth: 1,
                    barPercentage: 0.65,
                    categoryPercentage: 0.8,
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                indexAxis: 'y',
                plugins: {
                    legend: { display: false },
                    tooltip: { ...tt, callbacks: {
                        label: function(c) {
                            const d = entries[c.dataIndex];
                            return [
                                `Driver: ${d.driver_name}`,
                                `Std Dev: ${d.std_dev.toFixed(3)}s`,
                                `Avg Lap: ${fmtTime(d.avg_lap)}`,
                                `Laps: ${d.lap_count}`,
                            ];
                        }
                    } },
                    ...chartZoomOptions()
                },
                scales: {
                    x: { ...ts.x, title: { display: true, text: 'Standard Deviation (s)', color: tc.text }, beginAtZero: true },
                    y: { ...ts.y, ticks: { ...ts.y.ticks, font: { family: 'JetBrains Mono', size: 10 } } }
                }
            }
        });

        const panel = document.getElementById('chartPanel-consistency');
        if (panel) {
            const container = panel.querySelector('.chart-container');
            if (container) container.style.minHeight = '400px';
        }

        setupZoomReset(chartInstances.consistency);
    },

    // ── Strategy Gantt Chart (HTML-based, no Chart.js canvas) ──────
    strategy: function(ctx, data) {
        const container = document.getElementById('chartPanel-strategy');
        if (!container) return;
        const chartContainer = container.querySelector('.chart-container');
        if (!chartContainer) return;

        chartContainer.scrollLeft = 0;
        chartContainer.style.minHeight = 'auto';
        chartContainer.style.overflowX = 'auto';
        chartContainer.style.overflowY = 'visible';

        const carStints = data.car_stints || [];
        if (carStints.length === 0) {
            chartContainer.innerHTML = '<div class="strategy-empty">No stint data available</div>';
            chartInstances.strategy = { destroy: function() {} };
            return;
        }

        // Compute global time range across all stints
        let globalMin = Infinity, globalMax = -Infinity;
        var hasTime = false;
        carStints.forEach(function(car) {
            (car.stints || []).forEach(function(s) {
                if (s.start_time != null && s.end_time != null) {
                    if (s.start_time < globalMin) globalMin = s.start_time;
                    if (s.end_time > globalMax) globalMax = s.end_time;
                    hasTime = true;
                }
            });
        });

        if (!hasTime || globalMax <= globalMin) {
            chartContainer.innerHTML = '<div class="strategy-empty">Session time data not available for stint chart</div>';
            chartInstances.strategy = { destroy: function() {} };
            return;
        }

        var duration = globalMax - globalMin;
        if (duration <= 0) duration = 1;

        // Time axis ticks: every 5 minutes
        var tickInterval = 300;
        var firstTick = Math.floor(globalMin / tickInterval) * tickInterval;
        var ticks = [];
        for (var t = firstTick; t <= globalMax; t += tickInterval) {
            ticks.push(t);
        }

        var tc = window.getThemeColors ? window.getThemeColors() : { text: '#64748b' };

        var html = '<div class="strategy-chart">';

        // ── Time axis ──
        html += '<div class="strategy-time-axis">';
        for (var ti = 0; ti < ticks.length; ti++) {
            var pct = ((ticks[ti] - globalMin) / duration * 100).toFixed(1);
            html += '<div class="strategy-tick" style="left:' + pct + '%">' + (ticks[ti] / 60).toFixed(0) + 'm</div>';
        }
        html += '</div>';

        // ── Car rows ──
        for (var ci = 0; ci < carStints.length; ci++) {
            var car = carStints[ci];
            var baseColor = getCarColor(car.car_number);
            var posLabel = (car.position != null && car.position > 0) ? 'P' + car.position : 'NC';

            html += '<div class="strategy-row">';
            html += '<div class="strategy-car-label">#' + escapeHtml(car.car_number) + ' <span style="color:' + tc.text + ';font-weight:400">' + posLabel + '</span></div>';
            html += '<div class="strategy-track">';

            for (var si = 0; si < car.stints.length; si++) {
                var stint = car.stints[si];
                if (stint.start_time == null || stint.end_time == null) continue;

                var left = ((stint.start_time - globalMin) / duration * 100).toFixed(1);
                var width = ((stint.end_time - stint.start_time) / duration * 100).toFixed(1);
                if (width < 0.5) width = 0.5;

                // Alternate color lightness per stint
                var stintColor = lightenHex(baseColor, (si % 2 === 0) ? 0 : -15);

                html += '<div class="strategy-block" style="left:' + left + '%;width:' + width + '%;background:' + stintColor + ';"';
                html += ' title="Stint ' + (si + 1) + ': ' + escapeHtml(stint.driver) + ' | ' + stint.lap_count + ' laps | Best: ' + fmtTime(stint.fastest_lap) + '">';
                html += '<div class="strategy-block-driver">' + escapeHtml(stint.driver) + '</div>';
                html += '<div class="strategy-block-stats">' + stint.lap_count + ' laps &middot; ' + fmtTime(stint.fastest_lap) + '</div>';
                html += '</div>';

                // Pit stop label centered in the gap between stint blocks
                if (si > 0 && stint.pit_time != null && stint.pit_time > 0) {
                    var prevStint = car.stints[si - 1];
                    var prevEndPct = prevStint.end_time != null ? ((prevStint.end_time - globalMin) / duration * 100) : 0;
                    var currStartPct = parseFloat(left);
                    var midPct = ((prevEndPct + currStartPct) / 2).toFixed(1);
                    html += '<div class="strategy-block-pit" style="left:' + midPct + '%;">';
                    html += '<span class="strategy-block-pit-label">&#x2B07; ' + stint.pit_time.toFixed(1) + 's</span>';
                    html += '</div>';
                }
            }

            html += '</div></div>';
        }

        html += '</div>';

        chartContainer.innerHTML = html;

        // Set minimum height based on number of cars
        var rowCount = carStints.length;
        chartContainer.style.minHeight = Math.max(100, rowCount * 56 + 40) + 'px';

        chartInstances.strategy = { destroy: function() {} };
    },
};

// Checkbox change → render/remove charts
document.querySelectorAll('.chart-cb').forEach(cb => {
    cb.addEventListener('change', () => {
        if (!cachedData) { loadChart(); return; }
        renderCheckedCharts(cachedData);
    });
});

// Theme change → re-render charts
window.updateChartTheme = function() {
    if (cachedData) renderCheckedCharts(cachedData);
};

// Color mode toggle
window.toggleColorMode = function() {
    window.colorMode = (window.colorMode === 'number') ? 'model' : 'number';
    var btn = document.getElementById('colorModeToggle');
    if (btn) {
        btn.textContent = (window.colorMode === 'number') ? 'By Car #' : 'By Model';
        btn.classList.toggle('btn-ghost-active', window.colorMode === 'model');
    }
    if (cachedData) renderCheckedCharts(cachedData);
};
