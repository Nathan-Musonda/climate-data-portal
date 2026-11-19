let extremeSignalsChart;
let impactPatternChart;
let currentProvince = '';
let currentYear = '';
let availableYears = [];
let currentLoadController = null;
const extremeNotifier = typeof window.createPageNotifier === 'function'
    ? window.createPageNotifier('extreme-events')
    : null;
const climateMonthly = window.ClimateMonthly || {};

function sendNotification(type, title, message, options = {}) {
    if (typeof window.notifyApp !== 'function') return;
    if (extremeNotifier) {
        extremeNotifier(type, title, message, {
            id: options.id,
            duration: options.duration,
            sticky: options.sticky,
            meta: options.meta || 'Extreme events',
            icon: options.icon
        });
        return;
    }
    window.notifyApp({
        type,
        title,
        message,
        id: options.id,
        duration: options.duration,
        sticky: options.sticky,
        meta: options.meta || 'Extreme events',
        icon: options.icon
    });
}

function buildQuery(params) {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
        if (value) query.set(key, value);
    });
    const asString = query.toString();
    return asString ? `?${asString}` : '';
}

function formatNumber(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n.toLocaleString() : '--';
}

function resolveMonthlyLabels(payload) {
    const normalized = typeof climateMonthly.normalizePayload === 'function'
        ? climateMonthly.normalizePayload(payload)
        : (payload || {});
    return Array.isArray(normalized?.labels) ? normalized.labels : [];
}

function alignMonthlyValues(payload, key) {
    if (typeof climateMonthly.getSeries === 'function') {
        return climateMonthly.getSeries(payload, key);
    }
    return Array.isArray(payload?.[key]) ? payload[key] : [];
}

function getSelectedYear() {
    if (currentYear) return currentYear;
    const defaultYear = Number(window.portalDefaultYear);
    if (Number.isFinite(defaultYear)) return String(defaultYear);
    if (availableYears.length) return String(Math.max(...availableYears.map(Number)));
    return '2024';
}

function getActiveExtremeViewLabel() {
    return currentProvince || 'All Provinces';
}

function updateExtremeFilterSummary() {
    const summary = document.getElementById('extremeFilterSummary');
    const scope = document.getElementById('extremeScopeLabel');
    const year = document.getElementById('extremeYearLabel');
    const scopeLabel = getActiveExtremeViewLabel();
    const yearLabel = currentYear || getSelectedYear() || 'Latest available year';

    if (summary) {
        summary.innerHTML = `<i class="fas fa-sliders-h"></i><span>${scopeLabel}, ${yearLabel}</span>`;
    }
    if (scope) scope.textContent = scopeLabel;
    if (year) year.textContent = yearLabel;
}

function buildExtremeStatusNotification(payload, year, reason = 'updated') {
    const summary = payload?.summary || {};
    const hotspots = Array.isArray(payload?.hotspots) ? payload.hotspots : [];
    const topHotspot = hotspots[0] || null;
    const viewLabel = `${getActiveExtremeViewLabel()}, ${year}`;
    const intro = reason === 'reset'
        ? `Filters reset to ${viewLabel}.`
        : `Updated to ${viewLabel}.`;

    if (topHotspot && Number(topHotspot.value || 0) > 0) {
        const hotspotType = String(topHotspot.type || 'Extreme-event hotspot');
        const loweredType = hotspotType.toLowerCase();
        return {
            type: loweredType.includes('heat') || loweredType.includes('drought') ? 'warning' : 'info',
            title: `${hotspotType} hotspot`,
            message: `${intro} ${topHotspot.province} leads with ${formatNumber(topHotspot.value)} flagged records.`,
            meta: 'Extreme events'
        };
    }

    if (summary?.max_temperature !== null && summary?.max_temperature !== undefined) {
        return {
            type: Number(summary.max_temperature) >= 35 ? 'warning' : 'info',
            title: 'Heat signal refreshed',
            message: `${intro} The highest maximum temperature in this selection is ${formatNumber(summary.max_temperature)} deg C.`,
            meta: 'Heat'
        };
    }

    return {
        type: 'success',
        title: reason === 'reset' ? 'Extreme-event filters reset' : 'Extreme-event view updated',
        message: `${intro} Extreme-event indicators refreshed successfully.`,
        meta: 'Extreme events'
    };
}

async function fetchJSON(url, signal) {
    const response = await fetch(url, signal ? { signal } : undefined);
    if (!response.ok) {
        throw new Error(`Extreme events request failed with status ${response.status}`);
    }
    return response.json();
}

function renderSummary(summary) {
    document.getElementById('heatCount').textContent = formatNumber(summary?.heat_event_count);
    document.getElementById('rainCount').textContent = formatNumber(summary?.heavy_rainfall_count);
    document.getElementById('droughtCount').textContent = formatNumber(summary?.severe_drought_count);
}

function renderSignalsChart(monthly) {
    const canvas = document.getElementById('extremeSignalsChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (extremeSignalsChart) extremeSignalsChart.destroy();

    const labels = resolveMonthlyLabels(monthly);
    const heatEvents = alignMonthlyValues(monthly, 'heat_events');
    const heavyRainfallEvents = alignMonthlyValues(monthly, 'heavy_rainfall_events');
    const severeDroughtEvents = alignMonthlyValues(monthly, 'severe_drought_events');

    extremeSignalsChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [
                {
                    label: 'Heat events',
                    data: heatEvents,
                    borderColor: '#dc3545',
                    backgroundColor: 'rgba(220,53,69,0.10)',
                    tension: 0,
                    spanGaps: false,
                    fill: false
                },
                {
                    label: 'Heavy rainfall events',
                    data: heavyRainfallEvents,
                    borderColor: '#0d6efd',
                    backgroundColor: 'rgba(13,110,253,0.10)',
                    tension: 0,
                    spanGaps: false,
                    fill: false
                },
                {
                    label: 'Severe drought records',
                    data: severeDroughtEvents,
                    borderColor: '#fd7e14',
                    backgroundColor: 'rgba(253,126,20,0.10)',
                    tension: 0,
                    spanGaps: false,
                    fill: false
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            scales: {
                x: { ticks: { autoSkip: false, maxRotation: 0, minRotation: 0 } },
                y: { beginAtZero: true }
            }
        }
    });
}

function renderImpactChart(monthly) {
    const canvas = document.getElementById('impactPatternChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (impactPatternChart) impactPatternChart.destroy();

    const labels = resolveMonthlyLabels(monthly);
    const averageRainfall = alignMonthlyValues(monthly, 'average_rainfall');

    impactPatternChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [
                {
                    label: 'Average rainfall',
                    data: averageRainfall,
                    backgroundColor: '#0F766E'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { ticks: { autoSkip: false, maxRotation: 0, minRotation: 0 } },
                y: { beginAtZero: true }
            }
        }
    });
}

function renderHotspots(hotspots) {
    const container = document.getElementById('extremeHotspots');
    if (!container) return;

    if (!Array.isArray(hotspots) || !hotspots.length) {
        container.innerHTML = `
            <div class="hotspot-item">
                <div class="hotspot-copy">
                    <strong>No hotspot provinces identified</strong>
                    <span>The current selection did not surface a province-level event hotspot.</span>
                </div>
                <div class="hotspot-value">--</div>
            </div>
        `;
        return;
    }

    container.innerHTML = hotspots.map(item => `
        <div class="hotspot-item">
            <div class="hotspot-copy">
                <strong>${item.type}</strong>
                <span>${item.province}</span>
            </div>
            <div class="hotspot-value">${formatNumber(item.value)}</div>
        </div>
    `).join('');
}

function renderExtremeInsights(insights, thresholds, summary = {}, hotspots = []) {
    const container = document.getElementById('extremeInsights');
    if (!container) return;

    const lines = [];
    if (thresholds?.temperature_threshold_90p !== null && thresholds?.temperature_threshold_90p !== undefined) {
        lines.push(`Heat events are based on temperature values at or above ${thresholds.temperature_threshold_90p} deg C (90th percentile).`);
    }
    if (thresholds?.rainfall_threshold_90p !== null && thresholds?.rainfall_threshold_90p !== undefined) {
        lines.push(`Heavy rainfall events are based on rainfall values at or above ${thresholds.rainfall_threshold_90p} mm (90th percentile).`);
    }
    if (Number(summary?.heat_event_count || 0) || Number(summary?.heavy_rainfall_count || 0) || Number(summary?.severe_drought_count || 0)) {
        lines.push(
            `This selection contains ${formatNumber(summary?.heat_event_count || 0)} heat-event records, ${formatNumber(summary?.heavy_rainfall_count || 0)} heavy-rainfall records, and ${formatNumber(summary?.severe_drought_count || 0)} severe-drought records.`
        );
    }
    if (summary?.max_temperature !== null && summary?.max_temperature !== undefined) {
        lines.push(`The highest maximum temperature in this selection is ${summary.max_temperature} deg C.`);
    }
    if (summary?.max_rainfall !== null && summary?.max_rainfall !== undefined) {
        lines.push(`The largest rainfall value in this selection is ${summary.max_rainfall} mm.`);
    }
    if (Array.isArray(hotspots) && hotspots.length) {
        const lead = hotspots[0];
        lines.push(`${lead.province} is the strongest current hotspot for ${lead.type.toLowerCase()} with ${formatNumber(lead.value)} flagged records.`);
    }
    if (Array.isArray(insights)) lines.push(...insights);

    if (!lines.length) {
        container.innerHTML = '<div class="insight-item"><p>No insights available for this selection.</p></div>';
        return;
    }

    container.innerHTML = lines.map(line => `<div class="insight-item"><p>${line}</p></div>`).join('');
}

function renderNoDataState(message = 'No extreme-event data is available for this filter.', monthly = { period_type: 'month' }) {
    updateExtremeFilterSummary();
    renderSummary({
        heat_event_count: 0,
        heavy_rainfall_count: 0,
        severe_drought_count: 0
    });
    renderSignalsChart(monthly);
    renderImpactChart(monthly);
    renderHotspots([]);
    const insightNode = document.getElementById('extremeInsights');
    if (insightNode) {
        insightNode.innerHTML = `<div class="insight-item"><p>${message}</p></div>`;
    }
}

async function initializeFilters() {
    const yearSelect = document.getElementById('extremeYear');
    let years = Array.from(yearSelect?.options || [])
        .map(option => Number(option.value))
        .filter(Number.isFinite);

    try {
        const yearsResult = await fetchJSON('/api/v1/years');
        if (yearsResult?.success && Array.isArray(yearsResult.data)) {
            years = yearsResult.data.map(Number).filter(Number.isFinite);
        }
    } catch (error) {
        console.error('Failed to initialize extreme-event years:', error);
        sendNotification('warning', 'Extreme-event filters unavailable', 'Year options could not be refreshed. Using the best available fallback values.', {
            id: 'extreme-filter-warning'
        });
    }

    availableYears = Array.from(new Set(years)).sort((a, b) => a - b);
    if (yearSelect) {
        yearSelect.innerHTML = '<option value="">Latest complete year</option>';
        availableYears.forEach(year => yearSelect.appendChild(new Option(year, year)));
        currentYear = yearSelect.value || getSelectedYear();
        yearSelect.value = currentYear;
    }

    currentProvince = document.getElementById('extremeProvince')?.value || '';
}

function setupEventListeners() {
    const provinceSelect = document.getElementById('extremeProvince');
    const yearSelect = document.getElementById('extremeYear');
    const applyBtn = document.getElementById('extremeApplyBtn');
    const resetBtn = document.getElementById('extremeResetBtn');

    if (applyBtn) {
        applyBtn.addEventListener('click', () => {
            currentProvince = provinceSelect?.value || '';
            currentYear = yearSelect?.value || getSelectedYear();
            loadExtremeEvents({ notifyOnEmpty: true, notifyOnSuccess: true, notificationReason: 'applied' });
        });
    }

    if (resetBtn) {
        resetBtn.addEventListener('click', () => {
            if (provinceSelect) provinceSelect.value = '';
            currentYear = '';
            if (yearSelect) yearSelect.value = getSelectedYear();
            currentProvince = '';
            currentYear = yearSelect?.value || getSelectedYear();
            loadExtremeEvents({ notifyOnEmpty: true, notifyOnSuccess: true, notificationReason: 'reset' });
        });
    }
}

async function loadExtremeEvents({ notifyOnEmpty = false, notifyOnSuccess = false, notificationReason = 'updated' } = {}) {
    const selectedYear = getSelectedYear();
    currentYear = selectedYear;
    updateExtremeFilterSummary();

    if (currentLoadController) currentLoadController.abort();
    currentLoadController = new AbortController();
    const signal = currentLoadController.signal;

    try {
        const result = await fetchJSON(`/api/v1/extreme-events${buildQuery({ province: currentProvince, year: selectedYear })}`, signal);
        if (!result?.success) throw new Error('Extreme events request failed');

        const payload = result.data || {};
        const monthly = payload.monthly || {};
        const hasData = Number(monthly?.observed_month_count || 0) > 0
            || Number(payload.summary?.heat_event_count || 0) > 0
            || Number(payload.summary?.heavy_rainfall_count || 0) > 0
            || Number(payload.summary?.severe_drought_count || 0) > 0;

        if (!hasData) {
            renderNoDataState('No extreme-event data is available for this filter.', monthly);
            if (notifyOnEmpty) {
                sendNotification('info', 'No extreme-event data', 'The current filters did not return any extreme-event records.', {
                    id: 'extreme-empty'
                });
            }
            return;
        }

        renderSummary(payload.summary || {});
        renderSignalsChart(monthly);
        renderImpactChart(monthly);
        renderHotspots(payload.hotspots || []);
        renderExtremeInsights(payload.insights || [], payload.thresholds || {}, payload.summary || {}, payload.hotspots || []);

        if (notifyOnSuccess) {
            const statusNotification = buildExtremeStatusNotification(payload, selectedYear, notificationReason);
            sendNotification(statusNotification.type, statusNotification.title, statusNotification.message, {
                id: `status-${currentProvince || 'all'}-${selectedYear}`,
                meta: statusNotification.meta,
                duration: 5200
            });
        }
    } catch (error) {
        if (error?.name === 'AbortError') return;
        console.error('Failed to load extreme events:', error);
        renderNoDataState('Could not load extreme-event analysis right now.', { period_type: 'month' });
        const insightNode = document.getElementById('extremeInsights');
        if (insightNode) {
            insightNode.innerHTML = '<div class="insight-item"><p>Could not load extreme-event analysis right now.</p></div>';
        }
        sendNotification('danger', 'Extreme-event analysis unavailable', 'Could not load extreme-event analysis right now.', {
            id: 'extreme-load-error',
            duration: 6500
        });
    } finally {
        if (currentLoadController?.signal === signal) currentLoadController = null;
    }
}

document.addEventListener('DOMContentLoaded', async () => {
    await initializeFilters();
    updateExtremeFilterSummary();
    setupEventListeners();
    await loadExtremeEvents();
});
