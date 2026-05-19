let extremeRainfallChart;
let rainfallTrendChart;
let spiTrendChart;
let soilMoistureChart;
let provinceRainfallChart;
let monthlyPatternChart;
let currentProvince = '';
let currentYear = '';
let availableYears = [];
let currentLoadController = null;
const floodNotifier = typeof window.createPageNotifier === 'function'
    ? window.createPageNotifier('flood-events')
    : null;
const climateMonthly = window.ClimateMonthly || {};

function sendNotification(type, title, message, options = {}) {
    if (typeof window.notifyApp !== 'function') return;
    if (floodNotifier) {
        floodNotifier(type, title, message, {
            id: options.id,
            duration: options.duration,
            sticky: options.sticky,
            meta: options.meta || 'Flood risk',
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
        meta: options.meta || 'Flood risk',
        icon: options.icon
    });
}

function updateFilterSummary() {
    const summary = document.getElementById('floodFilterSummary');
    const provinceLabel = currentProvince || 'All Provinces';
    const yearLabel = currentYear || getSelectedYear() || 'Latest complete year';
    if (summary) {
        summary.innerHTML = `<i class="fas fa-sliders-h"></i><span>${provinceLabel}, ${yearLabel}</span>`;
    }

    const scopeLabel = document.getElementById('floodScopeLabel');
    if (scopeLabel) scopeLabel.textContent = provinceLabel;

    const yearPill = document.getElementById('floodYearLabel');
    if (yearPill) yearPill.textContent = yearLabel;
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

function formatDecimal(value, digits = 1) {
    const n = Number(value);
    return Number.isFinite(n) ? n.toFixed(digits) : '--';
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

function hasMultipleTrendPoints(trend, valueKey) {
    const labels = Array.isArray(trend?.labels) ? trend.labels : [];
    const values = Array.isArray(trend?.[valueKey]) ? trend[valueKey] : [];
    return labels.length > 1 && values.filter((value) => Number.isFinite(Number(value))).length > 1;
}

function buildMonthlyTrendPayload(monthlyPattern, valueKey, outputKey) {
    if (!monthlyPattern) return null;
    const labels = resolveMonthlyLabels(monthlyPattern);
    const values = alignMonthlyValues(monthlyPattern, valueKey);
    if (!values.some((value) => Number.isFinite(Number(value)))) return null;
    return {
        labels,
        [outputKey]: values
    };
}

function getSelectedYear() {
    if (currentYear) return currentYear;
    const defaultYear = Number(window.portalDefaultYear);
    if (Number.isFinite(defaultYear)) return String(defaultYear);
    if (availableYears.length) return String(Math.max(...availableYears.map(Number)));
    return '2024';
}

function getActiveFloodViewLabel() {
    return currentProvince || 'All Provinces';
}

function buildFloodStatusNotification(payload, year, reason = 'updated') {
    const summary = payload?.summary || {};
    const hotspots = Array.isArray(payload?.hotspots) ? payload.hotspots : [];
    const topHotspot = hotspots[0] || null;
    const topRainfall = payload?.extreme_rainfall?.top_rainfall_values?.[0] || null;
    const viewLabel = `${getActiveFloodViewLabel()}, ${year}`;
    const intro = reason === 'reset'
        ? `Filters reset to ${viewLabel}.`
        : `Updated to ${viewLabel}.`;

    if (topHotspot && Number(topHotspot.flood_events || 0) > 0) {
        return {
            type: Number(summary?.extreme_rainfall_count || 0) > 0 ? 'warning' : 'info',
            title: 'Flood hotspot updated',
            message: `${intro} ${topHotspot.province} leads the active view with ${formatNumber(topHotspot.flood_events)} flood-risk events.`,
            meta: 'Flood risk'
        };
    }

    if (topRainfall && Number(topRainfall.value || 0) >= 100) {
        return {
            type: 'warning',
            title: 'Extreme rainfall recorded',
            message: `${intro} The strongest provincial rainfall reading reaches ${formatDecimal(topRainfall.value, 1)} mm in ${topRainfall.province || topRainfall.location}.`,
            meta: 'Rainfall'
        };
    }

    if (summary?.avg_spi !== null && summary?.avg_spi !== undefined && Number(summary.avg_spi) >= 1) {
        return {
            type: 'info',
            title: 'Wet conditions elevated',
            message: `${intro} Average SPI is ${formatDecimal(summary.avg_spi, 2)}, indicating wetter-than-normal conditions.`,
            meta: 'Flood risk'
        };
    }

    return {
        type: 'success',
        title: reason === 'reset' ? 'Flood filters reset' : 'Flood view updated',
        message: `${intro} Flood-risk indicators refreshed successfully.`,
        meta: 'Flood risk'
    };
}

async function fetchJSON(url, signal) {
    const response = await fetch(url, signal ? { signal } : undefined);
    if (!response.ok) {
        throw new Error(`Flood events request failed with status ${response.status}`);
    }
    return response.json();
}

function renderFloodEmptyState(message = 'No flood-event data is available for this filter.', monthlyPayload = { period_type: 'month' }, extremeRainfallPayload = { period_type: 'month' }) {
    renderSummary({});
    renderExtremeRainfall({ ...extremeRainfallPayload, top_rainfall_values: [] }, {}, monthlyPayload);
    renderRainfallTrend({ labels: [], average_rainfall: [] }, monthlyPayload);
    renderSpiTrend({ labels: [], average_spi: [] }, monthlyPayload);
    renderSoilMoistureTrend({ labels: [], average_soil_moisture: [] }, monthlyPayload);
    renderProvinceRainfall({ labels: [], values: [] });
    renderMonthlyPattern(monthlyPayload);
    renderSeasonalSummary(monthlyPayload);
    renderHotspots([]);
    renderInsights([message]);
    renderSignalOverview({}, [], []);
}

function createLineChart(canvasId, labels, datasets, options = {}) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    const chartMap = {
        extremeRainfallChart,
        rainfallTrendChart,
        spiTrendChart,
        soilMoistureChart,
        provinceRainfallChart,
        monthlyPatternChart
    };
    const existing = chartMap[canvasId];
    if (existing) existing.destroy();

    const chart = new Chart(ctx, {
        type: options.type || 'line',
        data: { labels: labels || [], datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            ...options.config
        }
    });

    if (canvasId === 'extremeRainfallChart') extremeRainfallChart = chart;
    if (canvasId === 'rainfallTrendChart') rainfallTrendChart = chart;
    if (canvasId === 'spiTrendChart') spiTrendChart = chart;
    if (canvasId === 'soilMoistureChart') soilMoistureChart = chart;
    if (canvasId === 'provinceRainfallChart') provinceRainfallChart = chart;
    if (canvasId === 'monthlyPatternChart') monthlyPatternChart = chart;
}

async function initializeFilters() {
    const yearSelect = document.getElementById('floodYear');
    let years = Array.from(yearSelect?.options || [])
        .map(option => Number(option.value))
        .filter(Number.isFinite);

    try {
        const yearsResult = await fetchJSON('/api/v1/years');
        if (yearsResult?.success && Array.isArray(yearsResult.data)) {
            years = yearsResult.data.map(Number).filter(Number.isFinite);
        }
    } catch (error) {
        console.error('Failed to initialize flood-event years:', error);
        sendNotification('warning', 'Flood filters unavailable', 'Year options could not be refreshed for flood analysis. Using the best available fallback values.', {
            id: 'flood-filter-warning'
        });
    }

    availableYears = Array.from(new Set(years)).sort((a, b) => a - b);
    if (yearSelect) {
        yearSelect.innerHTML = '<option value="">Latest complete year</option>';
        availableYears.forEach(year => yearSelect.appendChild(new Option(year, year)));
        currentYear = yearSelect.value || getSelectedYear();
        yearSelect.value = currentYear;
    }

    currentProvince = document.getElementById('floodProvince')?.value || '';
}

function setupEventListeners() {
    const provinceSelect = document.getElementById('floodProvince');
    const yearSelect = document.getElementById('floodYear');
    const applyBtn = document.getElementById('floodApplyBtn');
    const resetBtn = document.getElementById('floodResetBtn');

    if (applyBtn) {
        applyBtn.addEventListener('click', () => {
            currentProvince = provinceSelect?.value || '';
            currentYear = yearSelect?.value || getSelectedYear();
            updateFilterSummary();
            loadFloodEvents({ notifyOnEmpty: true, notifyOnSuccess: true, notificationReason: 'applied' });
        });
    }

    if (resetBtn) {
        resetBtn.addEventListener('click', () => {
            if (provinceSelect) provinceSelect.value = '';
            currentYear = '';
            if (yearSelect) yearSelect.value = getSelectedYear();
            currentProvince = '';
            currentYear = yearSelect?.value || getSelectedYear();
            updateFilterSummary();
            loadFloodEvents({ notifyOnEmpty: true, notifyOnSuccess: true, notificationReason: 'reset' });
        });
    }
}

function renderSummary(summary) {
    document.getElementById('floodCount').textContent = formatNumber(summary?.flood_event_count);
    document.getElementById('extremeRainCount').textContent = formatNumber(summary?.extreme_rainfall_count);
    document.getElementById('avgSpiStat').textContent = summary?.avg_spi !== null && summary?.avg_spi !== undefined
        ? formatDecimal(summary.avg_spi, 2)
        : '--';
    document.getElementById('avgSoilMoistureStat').textContent = summary?.avg_soil_moisture !== null && summary?.avg_soil_moisture !== undefined
        ? `${formatDecimal(summary.avg_soil_moisture, 1)}%`
        : '--';
}

function setSignalLevel(level = 'stable', label = 'Monitoring') {
    const badge = document.getElementById('floodSignalLevel');
    if (!badge) return;
    const levelClass = level === 'alert'
        ? 'is-alert'
        : (level === 'watch' ? 'is-watch' : 'is-stable');
    const icon = level === 'alert'
        ? 'fa-triangle-exclamation'
        : (level === 'watch' ? 'fa-eye' : 'fa-circle-check');
    badge.className = `signal-level ${levelClass}`;
    badge.innerHTML = `<i class="fas ${icon}"></i><span>${label}</span>`;
}

function renderSignalOverview(summary = {}, hotspots = [], topRainfallValues = []) {
    const floodCount = Number(summary?.flood_event_count || 0);
    const extremeRainCount = Number(summary?.extreme_rainfall_count || 0);
    const avgSpi = Number(summary?.avg_spi);
    const peakMonth = summary?.peak_month || '--';
    const topHotspot = Array.isArray(hotspots) && hotspots.length ? hotspots[0] : null;
    const topRainfall = Array.isArray(topRainfallValues) && topRainfallValues.length ? topRainfallValues[0] : null;

    let leadValue = formatNumber(floodCount);
    let leadTitle = 'Flood-risk events identified';
    let leadNarrative = 'This view is currently centered on flagged flood-risk events and the places carrying the strongest wet-season pressure.';
    let signalState = 'stable';
    let signalLabel = 'Monitoring';

    if (extremeRainCount > 0 || (Number.isFinite(avgSpi) && avgSpi >= 1.2)) {
        signalState = 'alert';
        signalLabel = 'Elevated pressure';
        leadValue = formatNumber(extremeRainCount || floodCount);
        leadTitle = extremeRainCount > 0 ? 'Extreme rainfall is present' : 'Wet conditions are elevated';
        leadNarrative = extremeRainCount > 0
            ? 'The active view includes rainfall at the extreme threshold, which is the clearest sign that flood pressure needs attention.'
            : 'SPI is running high enough to suggest wetter-than-normal conditions even where the most extreme rainfall count is still limited.';
    } else if (floodCount > 0 || (Number.isFinite(avgSpi) && avgSpi >= 0.6)) {
        signalState = 'watch';
        signalLabel = 'Watch conditions';
        leadNarrative = 'The page is showing some wet-condition pressure, but the signal is better described as watch-level than peak flood stress.';
    }

    setSignalLevel(signalState, signalLabel);

    const leadValueNode = document.getElementById('floodLeadValue');
    if (leadValueNode) leadValueNode.textContent = leadValue;

    const leadTitleNode = document.getElementById('floodLeadTitle');
    if (leadTitleNode) leadTitleNode.textContent = leadTitle;

    const leadNarrativeNode = document.getElementById('floodLeadNarrative');
    if (leadNarrativeNode) {
        leadNarrativeNode.textContent = topHotspot
            ? `${leadNarrative} ${topHotspot.province} currently leads the hotspot ranking.`
            : leadNarrative;
    }

    const hotspotNode = document.getElementById('floodLeadHotspot');
    if (hotspotNode) hotspotNode.textContent = topHotspot ? topHotspot.province : '--';
    const hotspotNoteNode = document.getElementById('floodLeadHotspotNote');
    if (hotspotNoteNode) {
        hotspotNoteNode.textContent = topHotspot
            ? `${formatNumber(topHotspot.flood_events)} flagged records in the active view.`
            : 'Province with the strongest event concentration.';
    }

    const monthNode = document.getElementById('floodLeadMonth');
    if (monthNode) monthNode.textContent = peakMonth;
    const monthNoteNode = document.getElementById('floodLeadMonthNote');
    if (monthNoteNode) {
        monthNoteNode.textContent = peakMonth !== '--'
            ? `Flood-related activity is strongest in ${peakMonth}.`
            : 'Month where flood-like conditions are most active.';
    }

    const rainfallNode = document.getElementById('floodLeadRainfall');
    if (rainfallNode) {
        rainfallNode.textContent = topRainfall ? `${formatDecimal(topRainfall.value, 1)} mm` : '--';
    }
    const rainfallNoteNode = document.getElementById('floodLeadRainfallNote');
    if (rainfallNoteNode) {
        rainfallNoteNode.textContent = topRainfall
            ? topRainfall.location
            : 'Strongest rainfall record in the active view.';
    }
}

function renderExtremeRainfall(extremeRainfall, thresholds, monthlyPattern = null) {
    const labels = resolveMonthlyLabels(extremeRainfall);
    const floodRiskEvents = monthlyPattern
        ? alignMonthlyValues(monthlyPattern, 'flood_events')
        : [];
    const highRainfallEvents = alignMonthlyValues(extremeRainfall, 'high_rainfall_events');
    const veryHighRainfallEvents = alignMonthlyValues(extremeRainfall, 'very_high_rainfall_events');
    const extremeRainfallEvents = alignMonthlyValues(extremeRainfall, 'extreme_rainfall_events');
    const datasets = [];

    if (floodRiskEvents.some((value) => Number(value) > 0)) {
        datasets.push({
            label: `${thresholds?.rainfall_threshold_90p || '90th percentile'} mm flood-risk threshold`,
            data: floodRiskEvents,
            backgroundColor: 'rgba(16,42,67,0.72)',
            borderColor: '#102A43',
            borderWidth: 1,
            borderRadius: 8,
            maxBarThickness: 34
        });
    }

    datasets.push(
        {
            label: `${thresholds?.high_rainfall_mm || 50}+ mm`,
            data: highRainfallEvents,
            backgroundColor: 'rgba(43,108,176,0.45)',
            borderColor: '#2B6CB0',
            borderWidth: 1,
            borderRadius: 8,
            maxBarThickness: 34
        },
        {
            label: `${thresholds?.very_high_rainfall_mm || 100}+ mm`,
            data: veryHighRainfallEvents,
            backgroundColor: 'rgba(15,118,110,0.5)',
            borderColor: '#0F766E',
            borderWidth: 1,
            borderRadius: 8,
            maxBarThickness: 34
        },
        {
            label: `${thresholds?.extreme_rainfall_mm || 150}+ mm`,
            data: extremeRainfallEvents,
            backgroundColor: 'rgba(46,125,50,0.58)',
            borderColor: '#2E7D32',
            borderWidth: 1,
            borderRadius: 8,
            maxBarThickness: 34
        }
    );

    createLineChart(
        'extremeRainfallChart',
        labels,
        datasets,
        {
            type: 'bar',
            config: {
                plugins: {
                    legend: {
                        position: 'bottom'
                    }
                },
                scales: {
                    x: {
                        ticks: { autoSkip: false, maxRotation: 0, minRotation: 0 }
                    },
                    y: {
                        beginAtZero: true,
                        ticks: {
                            precision: 0
                        }
                    }
                }
            }
        }
    );

    const container = document.getElementById('topRainfallList');
    const topValues = extremeRainfall?.top_rainfall_values || [];
    if (!container) return;
    if (!topValues.length) {
        container.innerHTML = `
            <div class="ranking-item">
                <div class="ranking-copy">
                    <strong>No rainfall rankings</strong>
                    <span>No top rainfall records are available for this filter.</span>
                </div>
                <div class="ranking-value">--</div>
            </div>
        `;
        return;
    }
    container.innerHTML = topValues
        .map((item, index) => `
            <div class="ranking-item">
                <div class="ranking-copy">
                    <strong>${index + 1}. ${item.location}</strong>
                    <span>Highest provincial rainfall reading in this ranking slot.</span>
                </div>
                <div class="ranking-value">${formatDecimal(item.value, 1)} mm</div>
            </div>
        `)
        .join('');
}

function renderRainfallTrend(trend, monthlyPattern = null) {
    const chartData = hasMultipleTrendPoints(trend, 'average_rainfall')
        ? trend
        : (buildMonthlyTrendPayload(monthlyPattern, 'average_rainfall', 'average_rainfall') || trend || {});

    createLineChart('rainfallTrendChart', chartData?.labels || [], [{
        label: 'Average rainfall',
        data: chartData?.average_rainfall || [],
        borderColor: '#102A43',
        backgroundColor: 'rgba(16,42,67,0.12)',
        fill: true,
        tension: 0.25,
        pointRadius: 4,
        pointHoverRadius: 6
    }]);
}

function renderSpiTrend(trend, monthlyPattern = null) {
    const chartData = hasMultipleTrendPoints(trend, 'average_spi')
        ? trend
        : (buildMonthlyTrendPayload(monthlyPattern, 'average_spi', 'average_spi') || trend || {});

    createLineChart('spiTrendChart', chartData?.labels || [], [{
        label: 'Average SPI',
        data: chartData?.average_spi || [],
        borderColor: '#0F766E',
        backgroundColor: 'rgba(15,118,110,0.12)',
        fill: true,
        tension: 0.25,
        pointRadius: 4,
        pointHoverRadius: 6
    }], {
        config: {
            scales: {
                y: {
                    suggestedMin: -2,
                    suggestedMax: 2
                }
            }
        }
    });
}

function renderSoilMoistureTrend(trend, monthlyPattern = null) {
    const chartData = hasMultipleTrendPoints(trend, 'average_soil_moisture')
        ? trend
        : (buildMonthlyTrendPayload(monthlyPattern, 'average_soil_moisture', 'average_soil_moisture') || trend || {});

    createLineChart('soilMoistureChart', chartData?.labels || [], [{
        label: 'Average soil moisture',
        data: chartData?.average_soil_moisture || [],
        borderColor: '#2E7D32',
        backgroundColor: 'rgba(46,125,50,0.12)',
        fill: true,
        tension: 0.25,
        pointRadius: 4,
        pointHoverRadius: 6
    }]);
}

function renderProvinceRainfall(data) {
    createLineChart('provinceRainfallChart', data?.labels || [], [{
        label: 'Average rainfall',
        data: data?.values || [],
        backgroundColor: 'rgba(15,118,110,0.7)',
        borderColor: '#0F766E',
        borderWidth: 1,
        borderRadius: 8,
        minBarLength: 4
    }], {
        type: 'bar',
        config: {
            indexAxis: 'y',
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                x: {
                    beginAtZero: true
                }
            }
        }
    });
}

function renderMonthlyPattern(data) {
    const labels = resolveMonthlyLabels(data);
    const floodEvents = alignMonthlyValues(data, 'flood_events');

    createLineChart('monthlyPatternChart', labels, [
        {
            label: 'Flood risk events',
            data: floodEvents,
            backgroundColor: 'rgba(43,108,176,0.72)',
            borderColor: '#2B6CB0',
            borderWidth: 1,
            borderRadius: 8,
            maxBarThickness: 36
        }
    ], {
        type: 'bar',
        config: {
            scales: {
                x: {
                    ticks: { autoSkip: false, maxRotation: 0, minRotation: 0 }
                },
                y: {
                    beginAtZero: true,
                    title: { display: true, text: 'Flood risk events' }
                }
            }
        }
    });
}

function renderSeasonalSummary(data) {
    const labels = resolveMonthlyLabels(data);
    const floodEvents = alignMonthlyValues(data, 'flood_events');
    const averageRainfall = alignMonthlyValues(data, 'average_rainfall');

    let peakIndex = -1;
    let peakValue = -1;
    floodEvents.forEach((value, index) => {
        const count = Number(value);
        if (Number.isFinite(count) && count > peakValue) {
            peakValue = count;
            peakIndex = index;
        }
    });

    const activeMonths = floodEvents.filter((value) => Number(value) > 0).length;
    const peakMonthLabel = peakIndex >= 0 ? (labels[peakIndex] || '--') : '--';
    const peakRainfall = peakIndex >= 0 ? averageRainfall[peakIndex] : null;

    const peakNode = document.getElementById('floodSeasonPeak');
    if (peakNode) peakNode.textContent = peakMonthLabel;
    const peakNoteNode = document.getElementById('floodSeasonPeakNote');
    if (peakNoteNode) {
        peakNoteNode.textContent = peakIndex >= 0 && peakValue > 0
            ? `${formatNumber(peakValue)} flood-risk events are concentrated in this month.`
            : 'Month with the highest flood-risk activity.';
    }

    const activeNode = document.getElementById('floodSeasonActive');
    if (activeNode) activeNode.textContent = activeMonths ? `${activeMonths} months` : '--';
    const activeNoteNode = document.getElementById('floodSeasonActiveNote');
    if (activeNoteNode) {
        activeNoteNode.textContent = activeMonths
            ? `${activeMonths} months in the active view show at least one flood-risk event.`
            : 'Months where flood-risk events are present.';
    }

    const rainfallNode = document.getElementById('floodSeasonRainfall');
    if (rainfallNode) {
        rainfallNode.textContent = Number.isFinite(Number(peakRainfall))
            ? `${formatDecimal(peakRainfall, 1)} mm`
            : '--';
    }
    const rainfallNoteNode = document.getElementById('floodSeasonRainfallNote');
    if (rainfallNoteNode) {
        rainfallNoteNode.textContent = Number.isFinite(Number(peakRainfall))
            ? `Average rainfall during ${peakMonthLabel}, the strongest seasonal window.`
            : 'Average rainfall in the strongest seasonal window.';
    }
}

function renderHotspots(hotspots) {
    const container = document.getElementById('floodHotspots');
    if (!container) return;

    if (!Array.isArray(hotspots) || !hotspots.length) {
        container.innerHTML = `
            <div class="hotspot-item">
                <div class="hotspot-copy">
                    <strong>No hotspots identified</strong>
                    <span>The current flood filter does not surface a hotspot ranking.</span>
                </div>
                <div class="hotspot-value">--</div>
            </div>
        `;
        return;
    }

    container.innerHTML = hotspots
        .map((item, index) => `
            <div class="hotspot-item">
                <div class="hotspot-copy">
                    <strong>${index + 1}. ${item.province}</strong>
                    <span>Province hotspot in the active flood-risk view.</span>
                </div>
                <div class="hotspot-value">${formatNumber(item.flood_events)} events</div>
            </div>
        `)
        .join('');
}

function renderInsights(insights, summary = {}, hotspots = [], topRainfallValues = [], provinceRainfall = {}) {
    const container = document.getElementById('floodInsights');
    if (!container) return;

    const lines = [];
    if (Number(summary?.flood_event_count || 0) || Number(summary?.high_rainfall_count || 0) || Number(summary?.extreme_rainfall_count || 0)) {
        lines.push(
            `The active view contains ${formatNumber(summary?.flood_event_count || 0)} flood-risk events, ${formatNumber(summary?.high_rainfall_count || 0)} high-rainfall records, and ${formatNumber(summary?.extreme_rainfall_count || 0)} extreme-rainfall records.`
        );
    }
    if (summary?.peak_month) {
        lines.push(`Peak flood-related activity occurs in ${summary.peak_month}.`);
    }
    if (summary?.avg_spi !== null && summary?.avg_spi !== undefined) {
        lines.push(`Average SPI is ${formatDecimal(summary.avg_spi, 2)}, which helps show how unusually wet the period is.`);
    }
    if (summary?.avg_soil_moisture !== null && summary?.avg_soil_moisture !== undefined) {
        lines.push(`Average soil moisture is ${formatDecimal(summary.avg_soil_moisture, 1)}%, which indicates how saturated the ground may already be.`);
    }
    if (Array.isArray(hotspots) && hotspots.length) {
        lines.push(`${hotspots[0].province} has the highest concentration of flood-risk events with ${formatNumber(hotspots[0].flood_events)} flagged records.`);
    }
    if (Array.isArray(topRainfallValues) && topRainfallValues.length) {
        lines.push(`The strongest provincial rainfall reading in this view comes from ${topRainfallValues[0].province || topRainfallValues[0].location} at ${formatDecimal(topRainfallValues[0].value, 1)} mm.`);
    }
    if (provinceRainfall?.labels?.length && provinceRainfall?.values?.length) {
        lines.push(`${provinceRainfall.labels[0]} leads the province rainfall ranking at ${formatDecimal(provinceRainfall.values[0], 1)} mm on average.`);
    }
    if (Array.isArray(insights)) lines.push(...insights);

    if (!lines.length) {
        container.innerHTML = '<div class="insight-item"><p>No flood insights are available for this selection.</p></div>';
        return;
    }

    container.innerHTML = lines
        .map(line => `<div class="insight-item"><p>${line}</p></div>`)
        .join('');
}

async function loadFloodEvents({ notifyOnEmpty = false, notifyOnSuccess = false, notificationReason = 'updated' } = {}) {
    const selectedYear = getSelectedYear();
    currentYear = selectedYear;

    if (currentLoadController) currentLoadController.abort();
    currentLoadController = new AbortController();
    const signal = currentLoadController.signal;

    try {
        const result = await fetchJSON(`/api/v1/flood-events${buildQuery({ province: currentProvince, year: selectedYear })}`, signal);
        if (!result?.success) throw new Error('Flood events request failed');

        const payload = result.data || {};
        const hasData = Number(payload.monthly_pattern?.observed_month_count || 0) > 0
            || Number(payload.summary?.flood_event_count || 0) > 0
            || Number(payload.summary?.high_rainfall_count || 0) > 0
            || Number(payload.summary?.extreme_rainfall_count || 0) > 0;

        if (!hasData) {
            renderFloodEmptyState(
                'No flood-event data is available for this filter.',
                payload.monthly_pattern || { period_type: 'month' },
                payload.extreme_rainfall || { period_type: 'month' }
            );
            if (notifyOnEmpty) {
                sendNotification('info', 'No flood-event data', 'The current flood filters did not return any records.', {
                    id: 'flood-empty'
                });
            }
            return;
        }

        renderSummary(payload.summary || {});
        renderExtremeRainfall(
            payload.extreme_rainfall || {},
            payload.thresholds || {},
            payload.monthly_pattern || null
        );
        renderRainfallTrend(payload.rainfall_trend || {}, payload.monthly_pattern || null);
        renderSpiTrend(payload.spi_trend || {}, payload.monthly_pattern || null);
        renderSoilMoistureTrend(payload.soil_moisture_trend || {}, payload.monthly_pattern || null);
        renderProvinceRainfall(payload.province_rainfall || {});
        renderMonthlyPattern(payload.monthly_pattern || {});
        renderSeasonalSummary(payload.monthly_pattern || {});
        renderHotspots(payload.hotspots || []);
        renderSignalOverview(
            payload.summary || {},
            payload.hotspots || [],
            payload.extreme_rainfall?.top_rainfall_values || []
        );
        renderInsights(
            payload.insights || [],
            payload.summary || {},
            payload.hotspots || [],
            payload.extreme_rainfall?.top_rainfall_values || [],
            payload.province_rainfall || {}
        );

        if (notifyOnSuccess) {
            const statusNotification = buildFloodStatusNotification(payload, selectedYear, notificationReason);
            sendNotification(statusNotification.type, statusNotification.title, statusNotification.message, {
                id: `status-${currentProvince || 'all'}-${selectedYear}`,
                meta: statusNotification.meta,
                duration: 5200
            });
        }
    } catch (error) {
        if (error?.name === 'AbortError') return;
        console.error('Failed to load flood events:', error);
        renderFloodEmptyState('Could not load flood-event analysis right now.');
        sendNotification('danger', 'Flood analysis unavailable', 'Could not load flood-event analysis right now.', {
            id: 'flood-load-error',
            duration: 6500
        });
    } finally {
        if (currentLoadController?.signal === signal) currentLoadController = null;
    }
}

document.addEventListener('DOMContentLoaded', async () => {
    await initializeFilters();
    updateFilterSummary();
    setupEventListeners();
    await loadFloodEvents();
});
