let extremeRainfallChart;
let rainfallTrendChart;
let soilMoistureChart;
let provinceRainfallChart;
let monthlyPatternChart;
let currentProvince = '';
let currentDistrict = '';
let currentYear = '';
let currentMonth = '';
let availableYears = [];
let districtDirectory = [];
let currentLoadController = null;
const floodNotifier = typeof window.createPageNotifier === 'function'
    ? window.createPageNotifier('flood-events')
    : null;
const climateMonthly = window.ClimateMonthly || {};
const FULL_MONTH_LABELS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

function isNationwideFloodView() {
    return !currentProvince && !currentDistrict;
}

function getFloodScopeLabel() {
    if (currentDistrict) return currentDistrict;
    if (currentProvince) return currentProvince;
    return 'Zambia (all provinces)';
}

function getFloodScopeNarrativeLabel() {
    if (currentDistrict) return `${currentDistrict} District`;
    if (currentProvince) return `${currentProvince} Province`;
    return 'Zambia nationwide';
}

function shouldUseAllFloodYears(province = currentProvince, district = currentDistrict, month = currentMonth) {
    return !province && !district && !month;
}

function syncFloodYearSelection(yearSelect, province = currentProvince, district = currentDistrict, month = currentMonth) {
    if (!yearSelect) return;
    if (shouldUseAllFloodYears(province, district, month)) {
        yearSelect.value = '';
    }
}

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
    const districtLabel = currentDistrict || 'All Districts';
    const yearLabel = currentYear || getSelectedYear() || 'All years';
    const monthLabel = getSelectedMonthLabel();
    const scopeLabelText = getFloodScopeLabel();
    if (summary) {
        summary.innerHTML = `<i class="fas fa-sliders-h"></i><span>${scopeLabelText}, ${districtLabel}, ${yearLabel}, ${monthLabel}</span>`;
    }

    const scopeLabel = document.getElementById('floodScopeLabel');
    if (scopeLabel) scopeLabel.textContent = scopeLabelText;

    const yearPill = document.getElementById('floodYearLabel');
    if (yearPill) yearPill.textContent = yearLabel;

    const monthPill = document.getElementById('floodMonthLabel');
    if (monthPill) monthPill.textContent = monthLabel;
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

function getDurationSentence(durationPayload, key) {
    const sentence = durationPayload?.[key]?.sentence;
    return typeof sentence === 'string' && sentence.trim() ? sentence.trim() : '';
}

function buildAnnualSeries(labels = [], values = []) {
    return (Array.isArray(labels) ? labels : [])
        .map((label, index) => ({
            year: label,
            value: Number(values?.[index])
        }))
        .filter((item) => item.year !== null && item.year !== undefined && Number.isFinite(item.value));
}

function computeNormalValue(series = []) {
    if (!Array.isArray(series) || !series.length) return null;
    const total = series.reduce((sum, item) => sum + item.value, 0);
    return series.length ? total / series.length : null;
}

function formatPercentFromNormal(value, normalValue) {
    if (!Number.isFinite(value) || !Number.isFinite(normalValue) || normalValue === 0) return null;
    const change = ((value - normalValue) / normalValue) * 100;
    return `${change >= 0 ? '+' : ''}${change.toFixed(1)}%`;
}

function updateFloodYearRecordCards(yearlyFloodTrend = {}) {
    const annualSeries = buildAnnualSeries(yearlyFloodTrend?.labels, yearlyFloodTrend?.flood_events);
    const annualNormal = computeNormalValue(annualSeries);
    const highestValueNode = document.getElementById('floodHighestYearValue');
    const highestNoteNode = document.getElementById('floodHighestYearNote');
    const lowestValueNode = document.getElementById('floodLowestYearValue');
    const lowestNoteNode = document.getElementById('floodLowestYearNote');

    if (!annualSeries.length) {
        if (highestValueNode) highestValueNode.textContent = '--';
        if (highestNoteNode) highestNoteNode.textContent = 'No annual flood-event record is available for this selection.';
        if (lowestValueNode) lowestValueNode.textContent = '--';
        if (lowestNoteNode) lowestNoteNode.textContent = 'No annual flood-event record is available for this selection.';
        return;
    }

    const highestYear = annualSeries.reduce((best, item) => item.value > best.value ? item : best, annualSeries[0]);
    const lowestYear = annualSeries.reduce((best, item) => item.value < best.value ? item : best, annualSeries[0]);
    const highestPct = formatPercentFromNormal(highestYear.value, annualNormal);
    const lowestPct = formatPercentFromNormal(lowestYear.value, annualNormal);

    if (highestValueNode) highestValueNode.textContent = `${highestYear.year}`;
    if (highestNoteNode) {
        highestNoteNode.textContent = highestPct
            ? `${formatNumber(highestYear.value)} events, ${highestPct} relative to the normal of ${formatDecimal(annualNormal, 1)} events.`
            : `${formatNumber(highestYear.value)} events.`;
    }

    if (lowestValueNode) lowestValueNode.textContent = `${lowestYear.year}`;
    if (lowestNoteNode) {
        lowestNoteNode.textContent = lowestPct
            ? `${formatNumber(lowestYear.value)} events, ${lowestPct} relative to the normal of ${formatDecimal(annualNormal, 1)} events.`
            : `${formatNumber(lowestYear.value)} events.`;
    }
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
    const selected = document.getElementById('floodYear')?.value;
    if (selected !== undefined && selected !== null) return selected;
    if (currentYear !== undefined && currentYear !== null) return currentYear;
    if (shouldUseAllFloodYears()) return '';
    const defaultYear = Number(window.portalDefaultYear);
    if (Number.isFinite(defaultYear)) return String(defaultYear);
    if (availableYears.length) return String(Math.max(...availableYears.map(Number)));
    return '';
}

function getSelectedMonthLabel() {
    const monthNumber = Number(currentMonth);
    return Number.isInteger(monthNumber) && monthNumber >= 1 && monthNumber <= 12
        ? FULL_MONTH_LABELS[monthNumber - 1]
        : 'All months';
}

function getActiveFloodViewLabel() {
    return getFloodScopeLabel();
}

function buildFloodStatusNotification(payload, year, reason = 'updated') {
    const summary = payload?.summary || {};
    const hotspots = Array.isArray(payload?.hotspots) ? payload.hotspots : [];
    const topHotspot = hotspots[0] || null;
    const topRainfall = payload?.extreme_rainfall?.top_rainfall_values?.[0] || null;
    const yearLabel = year || 'All years';
    const viewLabel = `${getActiveFloodViewLabel()}, ${yearLabel}, ${getSelectedMonthLabel()}`;
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

async function loadDistrictDirectory() {
    try {
        const result = await fetchJSON('/api/v1/district-directory');
        districtDirectory = result?.success && Array.isArray(result.data) ? result.data : [];
    } catch (error) {
        console.error('Flood district directory load failed:', error);
        districtDirectory = [];
    }
}

function getFallbackDistrictDirectory(districtSelect) {
    const seen = new Set();
    return Array.from(districtSelect?.options || [])
        .map((option) => {
            const district = (option.value || option.textContent || '').trim();
            if (!district || district.toLowerCase() === 'all districts') return null;
            const key = district.toLowerCase();
            if (seen.has(key)) return null;
            seen.add(key);
            return {
                district,
                province: ''
            };
        })
        .filter(Boolean);
}

function getFloodDistrictSearchTerm() {
    const input = document.getElementById('floodDistrictSearch');
    return (input?.value || '').trim().toLowerCase();
}

function updateDistrictOptionsForProvince(provinceSelect, districtSelect) {
    if (!districtSelect) return;
    const directory = districtDirectory.length
        ? districtDirectory
        : getFallbackDistrictDirectory(districtSelect);
    const province = provinceSelect?.value || '';
    const previous = districtSelect.value;
    const searchTerm = getFloodDistrictSearchTerm();
    const districts = directory
        .filter(item => !province || !item.province || item.province === province)
        .map(item => item.district)
        .filter((district, index, values) => district && values.indexOf(district) === index)
        .filter(district => !searchTerm || district.toLowerCase().includes(searchTerm))
        .sort((a, b) => a.localeCompare(b));

    districtSelect.innerHTML = '<option value="">All Districts</option>';
    if (searchTerm && !districts.length) {
        const emptyOption = document.createElement('option');
        emptyOption.value = '';
        emptyOption.textContent = 'No matching districts';
        emptyOption.disabled = true;
        districtSelect.appendChild(emptyOption);
    }
    districts.forEach(district => {
        const option = document.createElement('option');
        option.value = district;
        option.textContent = district;
        districtSelect.appendChild(option);
    });

    districtSelect.value = districts.includes(previous) ? previous : '';
}

function renderFloodEmptyState(message = 'No flood-event data is available for this filter.', monthlyPayload = { period_type: 'month' }, extremeRainfallPayload = { period_type: 'month' }) {
    renderSummary({});
    renderExtremeRainfall({ ...extremeRainfallPayload, top_rainfall_values: [] }, {}, monthlyPayload);
    renderRainfallTrend({ labels: [], average_rainfall: [] }, monthlyPayload);
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
    if (canvasId === 'soilMoistureChart') soilMoistureChart = chart;
    if (canvasId === 'provinceRainfallChart') provinceRainfallChart = chart;
    if (canvasId === 'monthlyPatternChart') monthlyPatternChart = chart;
}

async function initializeFilters() {
    const provinceSelect = document.getElementById('floodProvince');
    const districtSelect = document.getElementById('floodDistrict');
    const districtSearchInput = document.getElementById('floodDistrictSearch');
    const yearSelect = document.getElementById('floodYear');
    const monthSelect = document.getElementById('floodMonth');
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
        yearSelect.innerHTML = '<option value="">All years</option>';
        availableYears.forEach(year => yearSelect.appendChild(new Option(year, year)));
        currentYear = yearSelect.value || '';
        yearSelect.value = currentYear;
    }

    await loadDistrictDirectory();
    updateDistrictOptionsForProvince(provinceSelect, districtSelect);
    currentProvince = provinceSelect?.value || '';
    currentDistrict = districtSelect?.value || '';
    currentMonth = monthSelect?.value || '';
    if (districtSearchInput && currentDistrict) districtSearchInput.value = currentDistrict;
    syncFloodYearSelection(yearSelect, currentProvince, currentDistrict, currentMonth);
    currentYear = yearSelect?.value || '';
}

function setupEventListeners() {
    const provinceSelect = document.getElementById('floodProvince');
    const districtSelect = document.getElementById('floodDistrict');
    const districtSearchInput = document.getElementById('floodDistrictSearch');
    const yearSelect = document.getElementById('floodYear');
    const monthSelect = document.getElementById('floodMonth');
    const applyBtn = document.getElementById('floodApplyBtn');
    const resetBtn = document.getElementById('floodResetBtn');

    if (applyBtn) {
        applyBtn.addEventListener('click', () => {
            currentProvince = provinceSelect?.value || '';
            currentDistrict = districtSelect?.value || '';
            currentMonth = monthSelect?.value || '';
            syncFloodYearSelection(yearSelect, currentProvince, currentDistrict, currentMonth);
            currentYear = yearSelect?.value || getSelectedYear();
            updateFilterSummary();
            loadFloodEvents({ notifyOnEmpty: true, notifyOnSuccess: true, notificationReason: 'applied' });
        });
    }

    if (resetBtn) {
        resetBtn.addEventListener('click', () => {
            if (provinceSelect) provinceSelect.value = '';
            if (districtSearchInput) districtSearchInput.value = '';
            updateDistrictOptionsForProvince(provinceSelect, districtSelect);
            if (districtSelect) districtSelect.value = '';
            if (monthSelect) monthSelect.value = '';
            currentYear = '';
            if (yearSelect) yearSelect.value = '';
            currentProvince = '';
            currentDistrict = '';
            currentMonth = '';
            syncFloodYearSelection(yearSelect, currentProvince, currentDistrict, currentMonth);
            currentYear = yearSelect?.value || '';
            updateFilterSummary();
            loadFloodEvents({ notifyOnEmpty: true, notifyOnSuccess: true, notificationReason: 'reset' });
        });
    }

    if (provinceSelect) {
        provinceSelect.addEventListener('change', () => {
            currentProvince = provinceSelect.value || '';
            updateDistrictOptionsForProvince(provinceSelect, districtSelect);
            currentDistrict = districtSelect?.value || '';
            syncFloodYearSelection(yearSelect, currentProvince, currentDistrict, currentMonth);
            currentYear = yearSelect ? yearSelect.value : currentYear;
            updateFilterSummary();
        });
    }

    if (districtSearchInput) {
        districtSearchInput.addEventListener('input', () => {
            updateDistrictOptionsForProvince(provinceSelect, districtSelect);
            currentDistrict = districtSelect?.value || '';
            updateFilterSummary();
        });
    }

    if (districtSelect) {
        districtSelect.addEventListener('change', () => {
            currentDistrict = districtSelect.value || '';
            if (districtSearchInput) districtSearchInput.value = currentDistrict;
            syncFloodYearSelection(yearSelect, currentProvince, currentDistrict, currentMonth);
            currentYear = yearSelect ? yearSelect.value : currentYear;
            updateFilterSummary();
        });
    }

    if (yearSelect) {
        yearSelect.addEventListener('change', () => {
            currentYear = yearSelect.value || '';
            updateFilterSummary();
        });
    }

    if (monthSelect) {
        monthSelect.addEventListener('change', () => {
            currentMonth = monthSelect.value || '';
            syncFloodYearSelection(yearSelect, currentProvince, currentDistrict, currentMonth);
            currentYear = yearSelect ? yearSelect.value : currentYear;
            updateFilterSummary();
        });
    }
}

function renderSummary(summary) {
    document.getElementById('floodCount').textContent = formatNumber(summary?.flood_event_count);
    document.getElementById('extremeRainCount').textContent = formatNumber(summary?.extreme_rainfall_count);
    document.getElementById('peakFloodMonthStat').textContent = summary?.peak_month || '--';
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
    const peakMonth = summary?.peak_month || '--';
    const topHotspot = Array.isArray(hotspots) && hotspots.length ? hotspots[0] : null;
    const topRainfall = Array.isArray(topRainfallValues) && topRainfallValues.length ? topRainfallValues[0] : null;
    const scopeNarrative = getFloodScopeNarrativeLabel();
    const nationwide = isNationwideFloodView();

    let leadValue = formatNumber(floodCount);
    let leadTitle = nationwide ? 'Nationwide flood-risk events identified' : 'Flood-risk events identified';
    let leadNarrative = nationwide
        ? 'This nationwide summary combines all provinces in the selected period to show where wet-season flood pressure is building most strongly.'
        : `This view is centered on ${scopeNarrative} and the places carrying the strongest wet-season pressure around it.`;
    let signalState = 'stable';
    let signalLabel = 'Monitoring';

    if (extremeRainCount > 0) {
        signalState = 'alert';
        signalLabel = 'Elevated pressure';
        leadValue = formatNumber(extremeRainCount || floodCount);
        leadTitle = 'Extreme rainfall is present';
        leadNarrative = nationwide
            ? 'The nationwide view includes rainfall at the extreme threshold, which is the clearest sign that flood pressure needs attention.'
            : `The ${scopeNarrative} view includes rainfall at the extreme threshold, which is the clearest sign that flood pressure needs attention.`;
    } else if (floodCount > 0) {
        signalState = 'watch';
        signalLabel = 'Watch conditions';
        leadNarrative = nationwide
            ? 'The nationwide summary is showing some wet-condition pressure, but the signal is better described as watch-level than peak flood stress.'
            : `The ${scopeNarrative} view is showing some wet-condition pressure, but the signal is better described as watch-level than peak flood stress.`;
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
            : nationwide
            ? 'Province with the strongest event concentration across Zambia.'
            : 'Province with the strongest event concentration.';
    }

    const monthNode = document.getElementById('floodLeadMonth');
    if (monthNode) monthNode.textContent = peakMonth;
    const monthNoteNode = document.getElementById('floodLeadMonthNote');
    if (monthNoteNode) {
        monthNoteNode.textContent = peakMonth !== '--'
            ? `Flood-related activity is strongest in ${peakMonth}.`
            : nationwide
            ? 'Month where Zambia-wide flood-like conditions are most active.'
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
            : nationwide
            ? 'Strongest provincial rainfall record in the Zambia-wide view.'
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

function renderSeasonalSummary(data, durationData = {}) {
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
        const durationSentence = getDurationSentence(durationData, 'flood');
        activeNoteNode.textContent = durationSentence || (activeMonths
            ? `${activeMonths} months in ${getFloodScopeNarrativeLabel()} show at least one flood-risk event.`
            : isNationwideFloodView()
            ? 'Months where Zambia-wide flood-risk events are present.'
            : 'Months where flood-risk events are present.');
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
            : isNationwideFloodView()
            ? 'Average rainfall in the strongest Zambia-wide seasonal window.'
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
                    <span>${isNationwideFloodView() ? 'The Zambia-wide selection does not surface a province hotspot ranking.' : 'The current flood filter does not surface a hotspot ranking.'}</span>
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
                    <span>${isNationwideFloodView() ? 'Province hotspot across the current Zambia-wide flood-risk view.' : 'Province hotspot in the active flood-risk view.'}</span>
                </div>
                <div class="hotspot-value">${formatNumber(item.flood_events)} events</div>
            </div>
        `)
        .join('');
}

function renderInsights(insights, summary = {}, hotspots = [], topRainfallValues = [], provinceRainfall = {}, durationData = {}, yearlyFloodTrend = {}) {
    const container = document.getElementById('floodInsights');
    if (!container) return;

    const lines = [];
    const scopeNarrative = getFloodScopeNarrativeLabel();
    if (Number(summary?.flood_event_count || 0) || Number(summary?.high_rainfall_count || 0) || Number(summary?.extreme_rainfall_count || 0)) {
        lines.push(
            `${scopeNarrative} contains ${formatNumber(summary?.flood_event_count || 0)} flood-risk events, ${formatNumber(summary?.high_rainfall_count || 0)} high-rainfall records, and ${formatNumber(summary?.extreme_rainfall_count || 0)} extreme-rainfall records.`
        );
    }
    if (summary?.peak_month) {
        lines.push(`Peak flood-related activity for ${scopeNarrative} occurs in ${summary.peak_month}.`);
    }
    const floodDuration = getDurationSentence(durationData, 'flood');
    if (floodDuration) {
        lines.push(floodDuration);
    }
    const rainfallDuration = getDurationSentence(durationData, 'rainfall');
    if (rainfallDuration) {
        lines.push(rainfallDuration);
    }
    if (summary?.avg_soil_moisture !== null && summary?.avg_soil_moisture !== undefined) {
        lines.push(`Average soil moisture across ${scopeNarrative} is ${formatDecimal(summary.avg_soil_moisture, 1)}%, which indicates how saturated the ground may already be.`);
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
    const annualSeries = buildAnnualSeries(yearlyFloodTrend?.labels, yearlyFloodTrend?.flood_events);
    const annualNormal = computeNormalValue(annualSeries);
    if (annualSeries.length) {
        const highestYear = annualSeries.reduce((best, item) => item.value > best.value ? item : best, annualSeries[0]);
        const lowestYear = annualSeries.reduce((best, item) => item.value < best.value ? item : best, annualSeries[0]);
        const highestPct = formatPercentFromNormal(highestYear.value, annualNormal);
        const lowestPct = formatPercentFromNormal(lowestYear.value, annualNormal);
        lines.push(
            highestPct
                ? `${highestYear.year} recorded the highest flood-event count at ${formatNumber(highestYear.value)}, ${highestPct} relative to the long-run normal of ${formatDecimal(annualNormal, 1)} events.`
                : `${highestYear.year} recorded the highest flood-event count at ${formatNumber(highestYear.value)}.`
        );
        lines.push(
            lowestPct
                ? `${lowestYear.year} recorded the lowest flood-event count at ${formatNumber(lowestYear.value)}, ${lowestPct} relative to the long-run normal of ${formatDecimal(annualNormal, 1)} events.`
                : `${lowestYear.year} recorded the lowest flood-event count at ${formatNumber(lowestYear.value)}.`
        );
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
    const selectedMonth = currentMonth || '';
    currentYear = selectedYear;

    if (currentLoadController) currentLoadController.abort();
    currentLoadController = new AbortController();
    const signal = currentLoadController.signal;

    try {
        const [result, allYearsResult, durationResult] = await Promise.all([
            fetchJSON(`/api/v1/flood-events${buildQuery({ province: currentProvince, district: currentDistrict, year: selectedYear, month: selectedMonth })}`, signal),
            fetchJSON(`/api/v1/flood-events${buildQuery({ province: currentProvince, district: currentDistrict, month: selectedMonth })}`, signal),
            fetchJSON(`/api/v1/event-duration${buildQuery({ province: currentProvince, district: currentDistrict, year: selectedYear, month: selectedMonth })}`, signal)
        ]);
        if (!result?.success) throw new Error('Flood events request failed');

        const payload = result.data || {};
        const durationData = durationResult?.success ? (durationResult.data || {}) : {};
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
        renderSoilMoistureTrend(payload.soil_moisture_trend || {}, payload.monthly_pattern || null);
        renderProvinceRainfall(payload.province_rainfall || {});
        renderMonthlyPattern(payload.monthly_pattern || {});
        renderSeasonalSummary(payload.monthly_pattern || {}, durationData);
        renderHotspots(payload.hotspots || []);
        renderSignalOverview(
            payload.summary || {},
            payload.hotspots || [],
            payload.extreme_rainfall?.top_rainfall_values || []
        );
        const yearlyFloodTrend = allYearsResult?.success ? (allYearsResult.data?.yearly_flood_trend || {}) : {};
        updateFloodYearRecordCards(yearlyFloodTrend);
        renderInsights(
            payload.insights || [],
            payload.summary || {},
            payload.hotspots || [],
            payload.extreme_rainfall?.top_rainfall_values || [],
            payload.province_rainfall || {},
            durationData,
            yearlyFloodTrend
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
