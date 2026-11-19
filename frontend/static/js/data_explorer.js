const explorerState = {
    chart: null,
    districtDirectory: [],
    variables: {},
    filters: null
};
const explorerNotifier = typeof window.createPageNotifier === 'function'
    ? window.createPageNotifier('data-explorer')
    : null;
const climateMonthly = window.ClimateMonthly || {};

const variableDefaults = {
    Rainfall_mm: { label: 'Rainfall', unit: 'mm' },
    Temp_Max_C: { label: 'Maximum Temperature', unit: '\u00B0C' },
    Temp_Min_C: { label: 'Minimum Temperature', unit: '\u00B0C' },
    SoilMoisture_pct: { label: 'Soil Moisture', unit: '%' }
};

function sendNotification(type, title, message, options = {}) {
    if (typeof window.notifyApp !== 'function') return;
    if (explorerNotifier) {
        explorerNotifier(type, title, message, {
            id: options.id,
            duration: options.duration,
            sticky: options.sticky,
            meta: options.meta || 'Data explorer',
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
        meta: options.meta || 'Data explorer',
        icon: options.icon
    });
}

document.addEventListener('DOMContentLoaded', () => {
    initialiseExplorer().catch((error) => {
        console.error('Failed to initialize explorer:', error);
        renderExplorerError('Unable to load the Climate Data Explorer right now.');
        sendNotification('danger', 'Climate Data Explorer unavailable', 'Unable to load the Climate Data Explorer right now.', {
            id: 'explorer-init-error',
            duration: 6500
        });
    });
});

async function initialiseExplorer() {
    syncInitialYearRange();
    setupExplorerListeners();
    await loadDistrictDirectory();
    updateDistrictOptions();
    await refreshExplorer();
}

function syncInitialYearRange() {
    const years = (window.explorerConfig?.years || []).map(Number).filter(Number.isFinite).sort((a, b) => a - b);
    const start = document.getElementById('explorerStartYear');
    const end = document.getElementById('explorerEndYear');
    if (!start || !end || years.length === 0) return;
    start.value = String(years[0]);
    end.value = String(years[years.length - 1]);
}

function setupExplorerListeners() {
    const province = document.getElementById('explorerProvince');
    const district = document.getElementById('explorerDistrict');
    const startYear = document.getElementById('explorerStartYear');
    const endYear = document.getElementById('explorerEndYear');
    const variable = document.getElementById('explorerVariable');
    const chartType = document.getElementById('explorerChartType');
    const downloadButton = document.getElementById('downloadExplorerData');

    province?.addEventListener('change', async () => {
        updateDistrictOptions();
        await refreshExplorer();
    });

    [district, startYear, endYear, variable, chartType].forEach((element) => {
        element?.addEventListener('change', refreshExplorer);
    });

    downloadButton?.addEventListener('click', () => {
        const params = buildExplorerQuery(getExplorerFilters());
        sendNotification('info', 'Download starting', 'Your selected climate view is being prepared for download.', {
            id: 'explorer-export-started',
            duration: 3500
        });
        window.location.href = `/api/v1/explorer/export?${params.toString()}`;
    });
}

async function loadDistrictDirectory() {
    const response = await fetch('/api/v1/district-directory');
    const payload = await response.json();
    explorerState.districtDirectory = payload.success ? payload.data : [];
}

function updateDistrictOptions() {
    const province = document.getElementById('explorerProvince')?.value || 'all';
    const districtSelect = document.getElementById('explorerDistrict');
    if (!districtSelect) return;

    const previous = districtSelect.value;
    const options = explorerState.districtDirectory
        .filter((item) => province === 'all' || item.province === province)
        .map((item) => item.district)
        .filter((value, index, array) => value && array.indexOf(value) === index)
        .sort((a, b) => a.localeCompare(b));

    districtSelect.innerHTML = '<option value="all">All Districts</option>';
    options.forEach((district) => {
        const option = document.createElement('option');
        option.value = district;
        option.textContent = district;
        districtSelect.appendChild(option);
    });

    districtSelect.value = options.includes(previous) ? previous : 'all';
}

function getExplorerFilters() {
    const startYear = Number(document.getElementById('explorerStartYear')?.value);
    const endYear = Number(document.getElementById('explorerEndYear')?.value);
    const safeStart = Number.isFinite(startYear) ? startYear : undefined;
    const safeEnd = Number.isFinite(endYear) ? endYear : undefined;

    return {
        province: document.getElementById('explorerProvince')?.value || 'all',
        district: document.getElementById('explorerDistrict')?.value || 'all',
        start_year: safeStart,
        end_year: safeEnd && safeStart && safeEnd < safeStart ? safeStart : safeEnd,
        variable: document.getElementById('explorerVariable')?.value || 'Rainfall_mm'
    };
}

function buildExplorerQuery(filters) {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
        if (value === undefined || value === null || value === '') return;
        params.set(key, value);
    });
    return params;
}

async function refreshExplorer() {
    const filters = getExplorerFilters();
    explorerState.filters = filters;
    setLoadingState();

    try {
        const params = buildExplorerQuery(filters);
        const response = await fetch(`/api/v1/explorer?${params.toString()}`);
        const payload = await response.json();

        if (!payload.success) {
            throw new Error(payload.error || 'Unable to load this climate view.');
        }

        const data = payload.data || {};
        explorerState.variables = buildVariableLookup(data.variables || []);
        updateSelectionLabel(filters);
        renderSummary(data.summary || {}, filters);
        renderInsights(data, filters);
        renderChart(data.chart || {});
        renderTable(data.table || {});

        const recordCount = Number(data?.summary?.record_count || 0);
        const shownRows = Number(data?.table?.shown_rows || 0);
        if (recordCount === 0 || shownRows === 0) {
            sendNotification('info', 'No results found', `No climate readings matched this selection for ${buildLocationLabel(filters)}.`, {
                id: 'explorer-empty',
                duration: 4200
            });
        }
    } catch (error) {
        console.error('Explorer refresh failed:', error);
        renderExplorerError(error?.message || 'Unable to load this climate view.');
        sendNotification('danger', 'Climate view unavailable', error?.message || 'Unable to load this climate view.', {
            id: 'explorer-load-error',
            duration: 6500
        });
    }
}

function buildVariableLookup(variables) {
    const lookup = { ...variableDefaults };
    variables.forEach((item) => {
        lookup[item.key] = {
            label: item.label,
            unit: item.unit
        };
    });
    return lookup;
}

function setLoadingState() {
    const chartSubtitle = document.getElementById('explorerChartSubtitle');
    const tableBody = document.getElementById('explorerTableBody');
    if (chartSubtitle) chartSubtitle.textContent = 'Loading climate information...';
    if (tableBody) {
        tableBody.innerHTML = '<tr><td colspan="8" class="empty-state">Loading climate readings...</td></tr>';
    }
}

function renderSummary(summary, filters) {
    const variableMeta = explorerState.variables[filters.variable] || variableDefaults[filters.variable] || { label: filters.variable, unit: '' };
    const unitSuffix = variableMeta.unit ? ` ${variableMeta.unit}` : '';

    setText('summaryAverage', formatMetric(summary.average_value, variableMeta.unit));
    setText('summaryAverageLabel', summary.summary_label || `Average ${variableMeta.label.toLowerCase()}`);
    setText('summaryRecords', formatInteger(summary.record_count));
    setText('summaryCoverage', `${formatInteger(summary.province_count)} provinces, ${formatInteger(summary.district_count)} districts`);

    const minimum = formatMetric(summary.minimum_value, variableMeta.unit);
    const maximum = formatMetric(summary.maximum_value, variableMeta.unit);
    setText('summaryRange', minimum === 'N/A' && maximum === 'N/A' ? '--' : `${minimum} to ${maximum}`);
    setText('summaryRangeDetail', `${variableMeta.label} values in this view${unitSuffix ? ` (${variableMeta.unit})` : ''}`);
    setText('summaryDrought', summary.most_common_drought_severity || 'N/A');
}

function renderInsights(data, filters) {
    const insightBox = document.getElementById('explorerInsightBox');
    const variableMeta = explorerState.variables[filters.variable] || variableDefaults[filters.variable] || { label: filters.variable, unit: '' };
    const summary = data.summary || {};
    const chart = data.chart || {};
    if (!insightBox) return;

    const locationLabel = buildLocationLabel(filters);
    const periodLabel = `${filters.start_year || 'start'}-${filters.end_year || 'end'}`;
    const average = formatMetric(summary.average_value, variableMeta.unit);
    const minimum = formatMetric(summary.minimum_value, variableMeta.unit);
    const maximum = formatMetric(summary.maximum_value, variableMeta.unit);
    const frequencyLabel = chart.period_type === 'month' ? 'monthly' : 'yearly';

    if (filters.variable === 'Rainfall_mm') {
        const normalizedChart = typeof climateMonthly.normalizePayload === 'function'
            ? climateMonthly.normalizePayload(chart, ['values'])
            : (chart || {});
        const stats = computeRainfallStats(normalizedChart.labels || [], normalizedChart.values || []);
        insightBox.innerHTML = buildRainfallInsightHtml(locationLabel, periodLabel, summary, stats, variableMeta.unit, frequencyLabel);
        return;
    }

    insightBox.innerHTML = [
        `<p><strong>${variableMeta.label}</strong> is shown for <strong>${locationLabel}</strong> across <strong>${periodLabel}</strong>.</p>`,
        `<p>This view includes <strong>${formatInteger(summary.record_count)}</strong> climate readings shown in a ${frequencyLabel} trend.</p>`,
        `<p>Average ${variableMeta.label.toLowerCase()}: <strong>${average}</strong>. Range: <strong>${minimum}</strong> to <strong>${maximum}</strong>.</p>`,
        `<p>Most common drought severity: <strong>${summary.most_common_drought_severity || 'N/A'}</strong>.</p>`
    ].join('');
}

function renderChart(chartData) {
    const chartTitle = document.getElementById('explorerChartTitle');
    const chartSubtitle = document.getElementById('explorerChartSubtitle');
    const canvas = document.getElementById('explorerChart');
    if (!canvas) return;

    const chartType = document.getElementById('explorerChartType')?.value || 'line';
    const normalizedChart = typeof climateMonthly.normalizePayload === 'function'
        ? climateMonthly.normalizePayload(chartData, ['values'])
        : (chartData || {});
    const isMonthly = normalizedChart?.period_type === 'month';
    const labels = normalizedChart?.labels || [];
    const values = normalizedChart?.values || [];
    const unit = normalizedChart.unit || '';
    const metricLabel = normalizedChart.label || 'Climate Variable';
    const isRainfall = normalizedChart.variable === 'Rainfall_mm';
    const rainfallStats = isRainfall ? computeRainfallStats(labels, values) : null;
    const periodAverage = rainfallStats?.average ?? null;
    const showRainfallTrendLine = isRainfall && chartType === 'bar';
    const chartPanel = canvas.closest('.explorer-panel');
    chartPanel?.classList.toggle('chart-rainfall', isRainfall);
    updateRainfallStatChips(rainfallStats, unit);

    if (chartTitle) chartTitle.textContent = `${metricLabel} Trend`;
    if (chartSubtitle) {
        chartSubtitle.textContent = labels.length > 0
            ? isRainfall
                ? buildRainfallSubtitle(rainfallStats, isMonthly, unit)
                : isMonthly
                    ? `${metricLabel} aggregated by month using a fixed Jan-Dec calendar. Missing monthly records stay empty.`
                    : `${metricLabel} aggregated by year.`
            : 'No chart data available for the selected filters.';
    }

    if (explorerState.chart) {
        explorerState.chart.destroy();
        explorerState.chart = null;
    }

    const ctx = canvas.getContext('2d');
    const baseColor = isRainfall ? '#0F6FB6' : (normalizedChart.color || '#1565C0');
    const rainfallFill = createVerticalGradient(ctx, '#38BDF8', '#EFF6FF');
    const rainfallBarColors = buildRainfallBarColors(values);
    const datasets = [{
        label: metricLabel,
        data: values,
        borderColor: baseColor,
        backgroundColor: isRainfall
            ? (chartType === 'bar' ? rainfallBarColors : rainfallFill)
            : addAlpha(normalizedChart.color || '#1565C0', chartType === 'bar' ? 0.75 : 0.18),
        borderRadius: isRainfall && chartType === 'bar' ? 8 : 0,
        borderSkipped: false,
        tension: isRainfall ? 0.38 : (isMonthly ? 0 : 0.32),
        borderWidth: isRainfall ? 3.5 : 3,
        fill: chartType === 'line',
        pointRadius: chartType === 'line' ? (isRainfall ? 4 : 3) : 0,
        pointHoverRadius: isRainfall ? 7 : 5,
        pointBackgroundColor: isRainfall ? '#FFFFFF' : baseColor,
        pointBorderColor: baseColor,
        pointBorderWidth: isRainfall ? 2 : 1,
        pointHitRadius: 12,
        barPercentage: isRainfall ? 0.5 : 0.82,
        categoryPercentage: isRainfall ? 0.66 : 0.86,
        maxBarThickness: isRainfall ? 34 : undefined,
        spanGaps: false
    }];

    if (showRainfallTrendLine && rainfallStats?.trendValues?.length > 1) {
        datasets.push({
            label: 'Trend line',
            data: rainfallStats.trendValues,
            borderColor: '#B45309',
            backgroundColor: 'transparent',
            borderWidth: 2.5,
            pointRadius: 0,
            pointHitRadius: 0,
            fill: false,
            tension: 0,
            type: 'line'
        });
    }

    explorerState.chart = new Chart(ctx, {
        type: chartType,
        data: {
            labels,
            datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false
            },
            plugins: {
                legend: {
                    display: isRainfall && datasets.length > 1,
                    position: 'bottom',
                    labels: {
                        usePointStyle: true,
                        boxWidth: 8,
                        boxHeight: 8
                    }
                },
                tooltip: {
                    backgroundColor: '#0F172A',
                    padding: 12,
                    displayColors: true,
                    callbacks: {
                        label(context) {
                            const value = context.parsed.y ?? context.parsed;
                            if (context.dataset.label === 'Trend line') {
                                return `Trend estimate: ${formatMetric(value, unit)}`;
                            }
                            const averageText = isRainfall && periodAverage
                                ? ` (${Math.round((Number(value) / periodAverage) * 100)}% of average)`
                                : '';
                            return `${metricLabel}: ${formatMetric(value, unit)}${averageText}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    offset: chartType === 'bar',
                    grid: {
                        display: false
                    },
                    ticks: buildXAxisTicks(labels, isMonthly, isRainfall)
                },
                y: {
                    beginAtZero: chartType === 'bar' || isRainfall,
                    grid: {
                        color: isRainfall ? 'rgba(15, 111, 182, 0.12)' : 'rgba(100, 116, 139, 0.16)',
                        drawBorder: false
                    },
                    ticks: {
                        color: '#475569',
                        callback(value) {
                            return unit ? `${value} ${unit}` : value;
                        }
                    }
                }
            }
        }
    });
}

function buildRainfallSubtitle(stats, isMonthly, unit) {
    if (!stats?.validPairs?.length) {
        return 'No rainfall trend is available for this selection.';
    }

    const periodLabel = isMonthly ? 'month' : 'year';
    const changeText = stats.changePercent === null
        ? 'Change is not available for a single point.'
        : `${formatSignedMetric(stats.change, unit)} (${stats.changePercent >= 0 ? '+' : ''}${stats.changePercent.toFixed(1)}%) from first to last point.`;
    return `Rainfall by ${periodLabel}. ${stats.direction} trend, ${changeText} Wettest ${periodLabel}: ${stats.wettest.label}; driest: ${stats.driest.label}.`;
}

function computeRainfallStats(labels, values) {
    const validPairs = values
        .map((value, index) => ({ value: Number(value), label: labels[index] }))
        .filter((item) => Number.isFinite(item.value));

    if (!validPairs.length) {
        return null;
    }

    const wettest = validPairs.reduce((max, item) => item.value > max.value ? item : max, validPairs[0]);
    const driest = validPairs.reduce((min, item) => item.value < min.value ? item : min, validPairs[0]);
    const first = validPairs[0];
    const last = validPairs[validPairs.length - 1];
    const average = validPairs.reduce((sum, item) => sum + item.value, 0) / validPairs.length;
    const change = last.value - first.value;
    const changePercent = first.value === 0 ? null : (change / first.value) * 100;
    const direction = Math.abs(change) < 0.05
        ? 'Stable'
        : change > 0 ? 'Increasing' : 'Decreasing';
    const regression = buildLinearTrend(values);

    return {
        validPairs,
        wettest,
        driest,
        first,
        last,
        average,
        change,
        changePercent,
        direction,
        trendValues: regression
    };
}

function buildLinearTrend(values) {
    const points = values
        .map((value, index) => ({ x: index, y: Number(value) }))
        .filter((point) => Number.isFinite(point.y));
    if (points.length < 2) return [];

    const xMean = points.reduce((sum, point) => sum + point.x, 0) / points.length;
    const yMean = points.reduce((sum, point) => sum + point.y, 0) / points.length;
    const numerator = points.reduce((sum, point) => sum + ((point.x - xMean) * (point.y - yMean)), 0);
    const denominator = points.reduce((sum, point) => sum + ((point.x - xMean) ** 2), 0);
    if (denominator === 0) return [];

    const slope = numerator / denominator;
    const intercept = yMean - slope * xMean;
    return values.map((_, index) => Number((intercept + slope * index).toFixed(1)));
}

function updateRainfallStatChips(stats, unit) {
    const container = document.getElementById('rainfallChartStats');
    if (!container) return;

    if (!stats) {
        setText('rainfallStatTrend', '--');
        setText('rainfallStatChange', '--');
        setText('rainfallStatWettest', '--');
        setText('rainfallStatDriest', '--');
        return;
    }

    setText('rainfallStatTrend', `${stats.direction} (${stats.first.label}-${stats.last.label})`);
    setText('rainfallStatChange', stats.changePercent === null
        ? formatSignedMetric(stats.change, unit)
        : `${formatSignedMetric(stats.change, unit)} / ${stats.changePercent >= 0 ? '+' : ''}${stats.changePercent.toFixed(1)}%`);
    setText('rainfallStatWettest', `${stats.wettest.label}: ${formatMetric(stats.wettest.value, unit)}`);
    setText('rainfallStatDriest', `${stats.driest.label}: ${formatMetric(stats.driest.value, unit)}`);
}

function buildRainfallInsightHtml(locationLabel, periodLabel, summary, stats, unit, frequencyLabel) {
    if (!stats) {
        return [
            `<p><strong>Rainfall</strong> is shown for <strong>${locationLabel}</strong> across <strong>${periodLabel}</strong>.</p>`,
            `<p>No rainfall trend points are available for the current filter selection.</p>`
        ].join('');
    }

    const changeText = stats.changePercent === null
        ? formatSignedMetric(stats.change, unit)
        : `${formatSignedMetric(stats.change, unit)} (${stats.changePercent >= 0 ? '+' : ''}${stats.changePercent.toFixed(1)}%)`;

    return [
        `<p><strong>Rainfall</strong> is shown for <strong>${locationLabel}</strong> across <strong>${periodLabel}</strong>.</p>`,
        `<p>The chart uses a ${frequencyLabel} view with observed rainfall bars and one gold trend line. The average is kept in the chart summary so the plot stays readable.</p>`,
        `<p>From <strong>${stats.first.label}</strong> to <strong>${stats.last.label}</strong>, rainfall changed by <strong>${changeText}</strong>, giving a <strong>${stats.direction.toLowerCase()}</strong> signal.</p>`,
        `<p>Wettest point: <strong>${stats.wettest.label}</strong> at <strong>${formatMetric(stats.wettest.value, unit)}</strong>. Driest point: <strong>${stats.driest.label}</strong> at <strong>${formatMetric(stats.driest.value, unit)}</strong>.</p>`,
        `<p>This view includes <strong>${formatInteger(summary.record_count)}</strong> climate readings.</p>`
    ].join('');
}

function buildXAxisTicks(labels, isMonthly, isRainfall) {
    const base = {
        color: '#334155',
        font: {
            size: isRainfall ? 12 : 11,
            weight: isRainfall ? '700' : '500'
        },
        padding: 10
    };

    if (isMonthly || labels.length <= 14) {
        return {
            ...base,
            autoSkip: false,
            maxRotation: 0,
            minRotation: 0
        };
    }

    return {
        ...base,
        autoSkip: true,
        maxTicksLimit: 12,
        maxRotation: 35,
        minRotation: 35
    };
}

function createVerticalGradient(ctx, topColor, bottomColor) {
    const gradient = ctx.createLinearGradient(0, 0, 0, ctx.canvas.height || 360);
    gradient.addColorStop(0, addAlpha(topColor, 0.34));
    gradient.addColorStop(0.72, addAlpha(topColor, 0.1));
    gradient.addColorStop(1, addAlpha(bottomColor, 0.02));
    return gradient;
}

function buildRainfallBarColors(values) {
    const numericValues = values.map((value) => Number(value)).filter(Number.isFinite);
    const min = numericValues.length ? Math.min(...numericValues) : 0;
    const max = numericValues.length ? Math.max(...numericValues) : 0;
    return values.map((value) => {
        const number = Number(value);
        if (!Number.isFinite(number) || max === min) return '#38BDF8';
        const ratio = (number - min) / (max - min);
        if (ratio >= 0.72) return '#075985';
        if (ratio >= 0.42) return '#0EA5E9';
        return '#7DD3FC';
    });
}

function renderTable(table) {
    const tableBody = document.getElementById('explorerTableBody');
    const tableMeta = document.getElementById('explorerTableMeta');
    if (!tableBody) return;

    const rows = table.rows || [];
    if (tableMeta) {
        const shown = Number(table.shown_rows || 0);
        const total = Number(table.total_rows || 0);
        tableMeta.textContent = shown === total
            ? `Showing all ${formatInteger(total)} climate readings across the selected years.`
            : `Showing ${formatInteger(shown)} of ${formatInteger(total)} climate readings.`;
    }

    if (rows.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="8" class="empty-state">No climate readings match this selection.</td></tr>';
        return;
    }

    tableBody.innerHTML = rows.map((row) => `
        <tr>
            <td>${escapeHtml(row.date || buildFallbackDate(row))}</td>
            <td>${escapeHtml(row.province || 'N/A')}</td>
            <td>${escapeHtml(row.district || 'N/A')}</td>
            <td>${formatMetric(row.Rainfall_mm, 'mm')}</td>
            <td>${formatMetric(row.Temp_Max_C, 'C')}</td>
            <td>${formatMetric(row.Temp_Min_C, 'C')}</td>
            <td>${formatMetric(row.SoilMoisture_pct, '%')}</td>
            <td>${renderSeverityPill(row.DroughtSeverity)}</td>
        </tr>
    `).join('');
}

function renderSeverityPill(value) {
    if (!value) return 'N/A';
    const slug = String(value).trim().toLowerCase().replace(/\s+/g, '-');
    return `<span class="severity-pill ${slug}">${escapeHtml(value)}</span>`;
}

function renderExplorerError(message) {
    if (explorerState.chart) {
        explorerState.chart.destroy();
        explorerState.chart = null;
    }
    setText('explorerChartSubtitle', message);
    setText('summaryAverage', '--');
    setText('summaryRecords', '--');
    setText('summaryRange', '--');
    setText('summaryDrought', '--');
    const tableBody = document.getElementById('explorerTableBody');
    if (tableBody) {
        tableBody.innerHTML = `<tr><td colspan="8" class="empty-state">${escapeHtml(message)}</td></tr>`;
    }
}

function updateSelectionLabel(filters) {
    const label = document.getElementById('explorerSelectionLabel');
    const variableMeta = explorerState.variables[filters.variable] || variableDefaults[filters.variable] || { label: filters.variable };
    const locationLabel = buildLocationLabel(filters);
    const yearsLabel = `${filters.start_year} to ${filters.end_year}`;

    if (label) {
        label.textContent = `Showing ${variableMeta.label.toLowerCase()} for ${locationLabel} from ${yearsLabel}.`;
    }

    setText('explorerSelectionVariable', variableMeta.label || 'Climate variable');
    setText('explorerSelectionScope', locationLabel);
    setText('explorerSelectionYears', yearsLabel);
}

function buildLocationLabel(filters) {
    if (filters.district && filters.district !== 'all') return `${filters.district}${filters.province && filters.province !== 'all' ? `, ${filters.province}` : ''}`;
    if (filters.province && filters.province !== 'all') return filters.province;
    return 'All provinces and districts';
}

function buildFallbackDate(row) {
    if (row.year && row.month) return `${row.year}-${String(row.month).padStart(2, '0')}`;
    if (row.year) return String(row.year);
    return 'N/A';
}

function formatMetric(value, unit) {
    if (value === null || value === undefined || value === '') return 'N/A';
    const number = Number(value);
    if (!Number.isFinite(number)) return escapeHtml(String(value));
    return unit ? `${number.toLocaleString()} ${unit}` : number.toLocaleString();
}

function formatSignedMetric(value, unit) {
    const number = Number(value);
    if (!Number.isFinite(number)) return 'N/A';
    const prefix = number > 0 ? '+' : '';
    return unit ? `${prefix}${number.toLocaleString(undefined, { maximumFractionDigits: 1 })} ${unit}` : `${prefix}${number.toLocaleString(undefined, { maximumFractionDigits: 1 })}`;
}

function formatInteger(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number.toLocaleString() : '0';
}

function addAlpha(hex, alpha) {
    const normalized = hex.replace('#', '');
    if (normalized.length !== 6) return hex;
    const r = parseInt(normalized.slice(0, 2), 16);
    const g = parseInt(normalized.slice(2, 4), 16);
    const b = parseInt(normalized.slice(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function setText(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = value;
}

function escapeHtml(value) {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}
