let rainfallTrendChart;
let rainfallYearlyTotalsChart;
let monthlyRainfallChart;
let rainfallByProvinceChart;
let rainfallDistributionChart;
let currentProvince = "";
let currentYear = "";
let availableYears = [];
let currentLoadController = null;
const rainfallNotifier = typeof window.createPageNotifier === "function"
    ? window.createPageNotifier("rainfall")
    : null;
const climateMonthly = window.ClimateMonthly || {};
const CANONICAL_MONTHS = Array.isArray(climateMonthly.CANONICAL_MONTHS)
    ? climateMonthly.CANONICAL_MONTHS.slice()
    : ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const valueLabelPlugin = {
    id: "valueLabelPlugin",
    afterDatasetsDraw(chart, args, pluginOptions) {
        if (!pluginOptions?.enabled) return;
        const datasetIndex = pluginOptions.datasetIndex ?? 0;
        const dataset = chart.data.datasets?.[datasetIndex];
        const meta = chart.getDatasetMeta(datasetIndex);

        if (!dataset || !meta?.data?.length) return;

        const ctx = chart.ctx;
        ctx.save();
        ctx.font = "600 11px system-ui";
        ctx.fillStyle = pluginOptions.color || "#334155";
        ctx.textAlign = "center";
        ctx.textBaseline = "bottom";

        meta.data.forEach((element, index) => {
            const rawValue = dataset.data?.[index];
            if (rawValue === null || rawValue === undefined || rawValue === "") return;
            const numericValue = Number(rawValue);
            if (!Number.isFinite(numericValue)) return;

            const label = pluginOptions.formatter
                ? pluginOptions.formatter(numericValue, index, chart)
                : String(numericValue);

            if (!label) return;

            const { x, y } = element.tooltipPosition();
            ctx.fillText(label, x, y - (pluginOptions.offset || 8));
        });

        ctx.restore();
    }
};

if (window.Chart && !Chart.registry.plugins.get("valueLabelPlugin")) {
    Chart.register(valueLabelPlugin);
}

function sendNotification(type, title, message, options = {}) {
    if (typeof window.notifyApp !== "function") return;
    if (rainfallNotifier) {
        rainfallNotifier(type, title, message, {
            id: options.id,
            duration: options.duration,
            sticky: options.sticky,
            meta: options.meta || "Rainfall",
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
        meta: options.meta || "Rainfall",
        icon: options.icon
    });
}

function buildQuery(params) {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== "") query.set(key, value);
    });
    const asString = query.toString();
    return asString ? `?${asString}` : "";
}

function formatDecimal(value, digits = 1) {
    if (value === null || value === undefined || value === "") return "--";
    const n = Number(value);
    return Number.isFinite(n) ? n.toFixed(digits) : "--";
}

function toFiniteNumber(value) {
    if (typeof climateMonthly.toFiniteNumber === "function") {
        return climateMonthly.toFiniteNumber(value);
    }
    if (value === null || value === undefined || value === "") return null;
    const numericValue = Number(value);
    return Number.isFinite(numericValue) ? numericValue : null;
}

function getCanonicalMonthIndex(label) {
    if (typeof climateMonthly.getMonthIndex === "function") {
        return climateMonthly.getMonthIndex(label);
    }
    const normalizedLabel = String(label || "").trim().slice(0, 3).toLowerCase();
    const lookup = CANONICAL_MONTHS.map((month) => month.toLowerCase());
    const index = lookup.indexOf(normalizedLabel);
    return index >= 0 ? index : null;
}

function alignMonthlySeries(values, { labels = [], monthNumbers = [] } = {}) {
    if (typeof climateMonthly.alignSeries === "function") {
        return climateMonthly.alignSeries(values, { labels, monthNumbers });
    }
    const alignedValues = Array(CANONICAL_MONTHS.length).fill(null);
    const sourceValues = Array.isArray(values) ? values : [];
    sourceValues.slice(0, CANONICAL_MONTHS.length).forEach((value, index) => {
        alignedValues[index] = toFiniteNumber(value);
    });
    return alignedValues;
}

function buildMonthlyCoverage(values) {
    if (typeof climateMonthly.buildSingleSeriesCoverage === "function") {
        return climateMonthly.buildSingleSeriesCoverage(values);
    }
    const observedMonthLabels = [];
    const missingMonthLabels = [];

    CANONICAL_MONTHS.forEach((month, index) => {
        if (toFiniteNumber(values[index]) === null) {
            missingMonthLabels.push(month);
        } else {
            observedMonthLabels.push(month);
        }
    });

    return {
        observedMonthCount: observedMonthLabels.length,
        missingMonthLabels,
        isCompletePeriod: observedMonthLabels.length === CANONICAL_MONTHS.length
    };
}

function buildRainfallPalette(values) {
    const numericValues = values.map(toFiniteNumber);
    const finiteValues = numericValues.filter(value => value !== null);
    const maxValue = finiteValues.length ? Math.max(...finiteValues) : null;
    const minValue = finiteValues.length ? Math.min(...finiteValues) : 0;
    const spread = maxValue === null ? 1 : Math.max(maxValue - minValue, 1);
    const peakIndexes = new Set(
        numericValues
            .map((value, index) => (value !== null && value === maxValue ? index : null))
            .filter(index => index !== null)
    );

    const backgroundColors = numericValues.map((value, index) => {
        if (value === null) return "rgba(148, 163, 184, 0.18)";
        if (peakIndexes.has(index)) return "rgba(15, 118, 110, 0.92)";
        const intensity = (value - minValue) / spread;
        const alpha = 0.42 + (intensity * 0.38);
        const hue = 198 - Math.round(intensity * 16);
        return `hsla(${hue}, 84%, 49%, ${alpha.toFixed(2)})`;
    });

    const borderColors = numericValues.map((value, index) => {
        if (value === null) return "rgba(148, 163, 184, 0.26)";
        if (peakIndexes.has(index)) return "#0f766e";
        return "#0f5c67";
    });

    const hoverColors = numericValues.map((value, index) => {
        if (value === null) return "rgba(148, 163, 184, 0.24)";
        if (peakIndexes.has(index)) return "#115e59";
        return "#0284c7";
    });

    const borderWidths = numericValues.map((value, index) => {
        if (value === null) return 0;
        return peakIndexes.has(index) ? 2 : 1;
    });

    return {
        backgroundColors,
        borderColors,
        hoverColors,
        borderWidths
    };
}

function setText(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = value;
}

function getActiveProvinceLabel() {
    return currentProvince || "All Provinces";
}

function buildRainfallStatusNotification(overview, rankings, year, reason = "updated") {
    const viewLabel = `${getActiveProvinceLabel()}, ${year}`;
    const intro = reason === "reset"
        ? `Filters reset to ${viewLabel}.`
        : `Updated to ${viewLabel}.`;
    const topProvince = Array.isArray(rankings) && rankings.length ? rankings[0] : null;
    const averageRainfall = Number(overview?.avg_rainfall);

    if (topProvince && Number.isFinite(Number(topProvince.value))) {
        return {
            type: "info",
            title: reason === "reset" ? "Rainfall filters reset" : "Rainfall view updated",
            message: `${intro} ${topProvince.province} leads the current ranking at ${formatDecimal(topProvince.value, 1)} mm.`,
            meta: "Rainfall"
        };
    }

    if (Number.isFinite(averageRainfall)) {
        return {
            type: "success",
            title: reason === "reset" ? "Rainfall filters reset" : "Rainfall view updated",
            message: `${intro} Average rainfall for the active view is ${formatDecimal(averageRainfall, 1)} mm.`,
            meta: "Rainfall"
        };
    }

    return {
        type: "info",
        title: "Rainfall data limited",
        message: `${intro} No rainfall records were returned for this selection.`,
        meta: "Rainfall"
    };
}

function updateFilterSummary() {
    const yearLabel = currentYear || "Latest complete year";
    const badge = document.getElementById("rainfallFilterSummary");
    if (badge) {
        badge.innerHTML = `<i class="fas fa-sliders-h"></i><span>${getActiveProvinceLabel()}, ${yearLabel}</span>`;
    }
}

function setLoadingState(isLoading) {
    const applyBtn = document.getElementById("rainfallApplyBtn");
    const resetBtn = document.getElementById("rainfallResetBtn");

    if (applyBtn) {
        applyBtn.disabled = isLoading;
        applyBtn.innerHTML = isLoading
            ? '<i class="fas fa-spinner fa-spin me-2"></i>Loading'
            : '<i class="fas fa-filter me-2"></i>Apply';
    }

    if (resetBtn) resetBtn.disabled = isLoading;
}

function getSelectedYear() {
    if (currentYear) return currentYear;
    const defaultYear = Number(window.portalDefaultYear);
    if (Number.isFinite(defaultYear)) return String(defaultYear);
    if (availableYears.length) return String(Math.max(...availableYears.map(Number)));
    return "2024";
}

function getPercentShareLabel(value, allValues, digits = 1) {
    const numericValues = (allValues || []).map(Number).filter(Number.isFinite);
    const total = numericValues.reduce((sum, item) => sum + item, 0);
    if (!Number.isFinite(value) || total <= 0) return "";
    return `${((value / total) * 100).toFixed(digits)}%`;
}

function computePercentChange(values) {
    const numericValues = (values || []).map(Number).filter(Number.isFinite);
    if (numericValues.length < 2) return null;
    const first = numericValues[0];
    const last = numericValues[numericValues.length - 1];
    if (first === 0) return null;
    return ((last - first) / Math.abs(first)) * 100;
}

function createCommonOptions({ showPercentLabels = false, percentSource = [], yLabel = "Rainfall (mm)", indexAxis = "x", forceAllXTicks = false } = {}) {
    const isHorizontal = indexAxis === "y";
    const scales = isHorizontal
        ? {
            x: {
                beginAtZero: true,
                grid: { color: "rgba(148, 163, 184, 0.16)" },
                ticks: { color: "#475569" },
                title: {
                    display: true,
                    text: yLabel,
                    color: "#475569"
                }
            },
            y: {
                grid: { display: false },
                ticks: {
                    color: "#475569",
                    maxRotation: 0,
                    minRotation: 0
                }
            }
        }
        : {
            x: {
                grid: { display: false },
                ticks: {
                    color: "#475569",
                    autoSkip: !forceAllXTicks,
                    maxRotation: forceAllXTicks ? 0 : 45,
                    minRotation: 0
                }
            },
            y: {
                beginAtZero: true,
                grid: { color: "rgba(148, 163, 184, 0.16)" },
                ticks: { color: "#475569" },
                title: {
                    display: true,
                    text: yLabel,
                    color: "#475569"
                }
            }
        };

    return {
        responsive: true,
        maintainAspectRatio: false,
        indexAxis,
        interaction: {
            mode: "index",
            intersect: false
        },
        scales,
        plugins: {
            legend: {
                display: true,
                labels: { color: "#334155" }
            },
            tooltip: {
                callbacks: {
                    label(context) {
                        if (context.raw === null || context.raw === undefined || context.raw === "") {
                            return `${context.dataset.label}: No data`;
                        }
                        const value = Number(context.raw);
                        const percent = getPercentShareLabel(value, percentSource);
                        return percent
                            ? `${context.dataset.label}: ${formatDecimal(value, 1)} mm (${percent})`
                            : `${context.dataset.label}: ${formatDecimal(value, 1)} mm`;
                    }
                }
            },
            valueLabelPlugin: {
                enabled: showPercentLabels,
                datasetIndex: 0,
                color: "#0f172a",
                offset: 6,
                formatter(value) {
                    return getPercentShareLabel(value, percentSource);
                }
            }
        }
    };
}

async function fetchJSON(url, signal) {
    const response = await fetch(url, signal ? { signal } : undefined);
    return response.json();
}

async function initializeFilters() {
    const provinceSelect = document.getElementById("rainfallProvince");
    const yearSelect = document.getElementById("rainfallYear");

    let years = Array.from(yearSelect?.options || [])
        .map(option => Number(option.value))
        .filter(Number.isFinite);

    try {
        const yearsResult = await fetchJSON("/api/v1/years");
        if (yearsResult?.success && Array.isArray(yearsResult.data)) {
            years = yearsResult.data.map(Number).filter(Number.isFinite);
        }
    } catch (error) {
        console.error("Rainfall years load failed:", error);
    }

    availableYears = Array.from(new Set(years)).sort((a, b) => a - b);
    if (yearSelect) {
        yearSelect.innerHTML = '<option value="">Latest complete year</option>';
        availableYears.forEach(year => yearSelect.appendChild(new Option(year, year)));
        currentYear = yearSelect.value || getSelectedYear();
        yearSelect.value = currentYear;
    }

    currentProvince = provinceSelect?.value || "";
    updateFilterSummary();
}

function setupEventListeners() {
    const provinceSelect = document.getElementById("rainfallProvince");
    const yearSelect = document.getElementById("rainfallYear");
    const applyBtn = document.getElementById("rainfallApplyBtn");
    const resetBtn = document.getElementById("rainfallResetBtn");

    if (applyBtn) {
        applyBtn.addEventListener("click", () => {
            currentProvince = provinceSelect?.value || "";
            currentYear = yearSelect?.value || getSelectedYear();
            updateFilterSummary();
            loadRainfallData("updated");
        });
    }

    if (resetBtn) {
        resetBtn.addEventListener("click", () => {
            if (provinceSelect) provinceSelect.value = "";
            currentYear = "";
            if (yearSelect) yearSelect.value = getSelectedYear();
            currentProvince = "";
            currentYear = yearSelect?.value || getSelectedYear();
            updateFilterSummary();
            loadRainfallData("reset");
        });
    }

    if (provinceSelect) {
        provinceSelect.addEventListener("change", () => {
            currentProvince = provinceSelect.value || "";
            updateFilterSummary();
        });
    }

    if (yearSelect) {
        yearSelect.addEventListener("change", () => {
            currentYear = yearSelect.value || getSelectedYear();
            updateFilterSummary();
        });
    }
}

function renderSummaryCards(overview, trendData) {
    const rainfallValues = trendData?.avg_rainfall || [];
    const rainfallYears = trendData?.years || [];
    const yearlySeries = rainfallYears.map((year, index) => ({
        year,
        value: Number(rainfallValues[index] || 0)
    })).filter(item => Number.isFinite(item.value));

    const wettestYear = yearlySeries.length
        ? yearlySeries.reduce((best, item) => item.value > best.value ? item : best, yearlySeries[0])
        : null;
    const driestYear = yearlySeries.length
        ? yearlySeries.reduce((best, item) => item.value < best.value ? item : best, yearlySeries[0])
        : null;

    document.getElementById("avgRainfall").innerHTML = `${formatDecimal(overview?.avg_rainfall, 1)} <small>mm</small>`;
    document.getElementById("highestRainfall").textContent = wettestYear ? `${formatDecimal(wettestYear.value, 1)} mm` : "--";
    document.getElementById("highestRainfallLabel").textContent = wettestYear ? `${wettestYear.year} recorded the highest yearly average rainfall.` : "No yearly rainfall averages available.";
    document.getElementById("lowestRainfall").textContent = driestYear ? `${formatDecimal(driestYear.value, 1)} mm` : "--";
    document.getElementById("lowestRainfallLabel").textContent = driestYear ? `${driestYear.year} recorded the lowest yearly average rainfall.` : "No yearly rainfall averages available.";

    if (!rainfallValues.length) {
        document.getElementById("rainfallVariability").textContent = "--";
        document.getElementById("rainfallTrendDirection").textContent = "No trend data";
        return;
    }

    const mean = rainfallValues.reduce((sum, val) => sum + Number(val || 0), 0) / rainfallValues.length;
    const variance = rainfallValues.reduce((sum, val) => {
        const x = Number(val || 0) - mean;
        return sum + (x * x);
    }, 0) / rainfallValues.length;
    const stdDev = Math.sqrt(variance);
    const cv = mean === 0 ? null : (stdDev / mean) * 100;
    const trendChange = computePercentChange(rainfallValues);
    const trendDirection = trendChange === null ? "Stable" : (trendChange >= 0 ? "Increasing" : "Decreasing");
    const startYear = rainfallYears[0] || "start";
    const endYear = rainfallYears[rainfallValues.length - 1] || "end";

    document.getElementById("rainfallVariability").textContent = Number.isFinite(cv) ? `${cv.toFixed(1)}%` : "--";
    document.getElementById("rainfallTrendDirection").textContent = trendChange === null
        ? `${trendDirection} (${startYear}-${endYear})`
        : `${trendDirection} ${trendChange > 0 ? "+" : ""}${trendChange.toFixed(1)}% (${startYear}-${endYear})`;
}

function renderTrendChart(data) {
    const canvas = document.getElementById("rainfallTrendChart");
    const container = canvas?.parentElement;
    if (!canvas || !container) return;

    if (rainfallTrendChart) {
        rainfallTrendChart.destroy();
        rainfallTrendChart = null;
    }

    const width = Math.max(Math.floor(container.clientWidth), 320);
    const height = Math.max(Math.floor(container.clientHeight), 260);
    canvas.width = width;
    canvas.height = height;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;

    const ctx = canvas.getContext("2d");
    const rainfallValues = data?.avg_rainfall || [];
    const labels = data?.years || data?.labels || [];
    const trendOptions = createCommonOptions({ showPercentLabels: false, percentSource: rainfallValues });
    rainfallTrendChart = new Chart(ctx, {
        type: "line",
        data: {
            labels,
            datasets: [{
                label: "Average Rainfall (mm)",
                data: rainfallValues,
                borderColor: "#1565C0",
                backgroundColor: "rgba(21, 101, 192, 0.12)",
                pointBackgroundColor: "#1565C0",
                pointRadius: 4,
                pointHoverRadius: 6,
                fill: false,
                spanGaps: false,
                tension: 0.25
            }]
        },
        options: {
            ...trendOptions,
            responsive: false,
            maintainAspectRatio: false,
            animation: false,
            plugins: {
                ...trendOptions.plugins,
                tooltip: {
                    callbacks: {
                        label(context) {
                            const value = Number(context.raw);
                            const periodAverage = rainfallValues.length
                                ? rainfallValues.reduce((sum, item) => sum + Number(item || 0), 0) / rainfallValues.length
                                : null;
                            const relative = periodAverage ? ((value / periodAverage) * 100).toFixed(1) : null;
                            return relative
                                ? `Average Rainfall (mm): ${formatDecimal(value, 1)} mm (${relative}% of period average)`
                                : `Average Rainfall (mm): ${formatDecimal(value, 1)} mm`;
                        }
                    }
                }
            }
        }
    });
}

function renderYearlyTotalsChart(data) {
    const ctx = document.getElementById("rainfallYearlyTotalsChart").getContext("2d");
    if (rainfallYearlyTotalsChart) rainfallYearlyTotalsChart.destroy();

    const values = data?.avg_rainfall || [];
    rainfallYearlyTotalsChart = new Chart(ctx, {
        type: "bar",
        data: {
            labels: data?.years || [],
            datasets: [{
                label: "Yearly Rainfall (mm)",
                data: values,
                backgroundColor: "#4FC3F7",
                borderColor: "#1565C0",
                borderWidth: 1,
                borderRadius: 8
            }]
        },
        options: createCommonOptions({
            showPercentLabels: true,
            percentSource: values
        })
    });
}

function renderMonthlyPattern(data) {
    const ctx = document.getElementById("monthlyRainfallChart").getContext("2d");
    if (monthlyRainfallChart) monthlyRainfallChart.destroy();

    const normalizedData = typeof climateMonthly.normalizePayload === "function"
        ? climateMonthly.normalizePayload(data, ["avg_rainfall"])
        : (data || {});
    const labels = normalizedData?.labels || CANONICAL_MONTHS.slice();
    const values = normalizedData?.avg_rainfall || alignMonthlySeries(data?.avg_rainfall || [], {
        labels: data?.years || data?.labels || [],
        monthNumbers: data?.month_numbers || []
    });
    const coverage = buildMonthlyCoverage(values);
    const observedMonthCount = coverage.observedMonthCount;
    const missingMonthLabels = coverage.missingMonthLabels;
    const hasCompleteCoverage = coverage.isCompletePeriod;
    const showShareLabels = hasCompleteCoverage && observedMonthCount === CANONICAL_MONTHS.length;
    const palette = buildRainfallPalette(values);
    const monthlyOptions = createCommonOptions({
        showPercentLabels: showShareLabels,
        percentSource: showShareLabels ? values : [],
        forceAllXTicks: true
    });

    monthlyRainfallChart = new Chart(ctx, {
        type: "bar",
        data: {
            labels,
            datasets: [{
                label: "Monthly Rainfall (mm)",
                data: values,
                backgroundColor: palette.backgroundColors,
                hoverBackgroundColor: palette.hoverColors,
                borderColor: palette.borderColors,
                borderWidth: palette.borderWidths,
                borderRadius: 10,
                borderSkipped: false,
                maxBarThickness: 28
            }]
        },
        options: {
            ...monthlyOptions,
            plugins: {
                ...monthlyOptions.plugins,
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        label(context) {
                            const value = toFiniteNumber(context.raw);
                            if (value === null) {
                                return "Rainfall: No monthly record";
                            }
                            const percent = showShareLabels ? getPercentShareLabel(value, values) : "";
                            return percent
                                ? `Rainfall: ${formatDecimal(value, 1)} mm (${percent} of plotted monthly total)`
                                : `Rainfall: ${formatDecimal(value, 1)} mm`;
                        }
                    }
                },
                valueLabelPlugin: {
                    enabled: showShareLabels,
                    datasetIndex: 0,
                    color: "#0f172a",
                    offset: 6,
                    formatter(value) {
                        return getPercentShareLabel(value, values);
                    }
                }
            },
            scales: {
                ...monthlyOptions.scales,
                y: {
                    ...monthlyOptions.scales.y,
                    title: {
                        display: true,
                        text: "Rainfall (mm)",
                        color: "#475569"
                    }
                }
            }
        }
    });

    const subtitle = document.getElementById("monthlyRainfallSubtitle");
    if (!subtitle) return;

    const seasonalTop = Array.isArray(labels) && Array.isArray(values)
        ? labels
            .map((month, index) => {
                const rawValue = values[index];
                if (rawValue === null || rawValue === undefined || rawValue === "") return null;
                const value = Number(rawValue);
                return Number.isFinite(value) ? { month, value } : null;
            })
            .filter(Boolean)
            .sort((a, b) => b.value - a.value)
            .slice(0, 3)
            .map(item => item.month)
            .join(", ")
        : "";

    if (hasCompleteCoverage) {
        subtitle.innerHTML = `<i class="fas fa-info-circle"></i> Zambia's strongest rainfall months in this view are ${seasonalTop || "not available yet"}. Percent labels show each month's share of the selected year's rainfall.`;
        return;
    }

    const coverageText = observedMonthCount
        ? `Data is available for ${observedMonthCount} of 12 months.`
        : "No monthly rainfall records are available for this year.";
    const missingText = missingMonthLabels.length
        ? ` Missing months: ${missingMonthLabels.join(", ")}.`
        : "";
    const strongestText = seasonalTop
        ? ` Highest observed rainfall months: ${seasonalTop}.`
        : "";

    subtitle.innerHTML = `<i class="fas fa-info-circle"></i> ${coverageText}${missingText}${strongestText} Share labels are hidden because the monthly coverage is incomplete.`;
}

function renderProvincialComparison(rankings) {
    const ctx = document.getElementById("rainfallByProvinceChart").getContext("2d");
    if (rainfallByProvinceChart) rainfallByProvinceChart.destroy();

    const chartData = (rankings || []).slice(0, 10);
    const values = chartData.map(item => Number(item.value || 0));

    rainfallByProvinceChart = new Chart(ctx, {
        type: "bar",
        data: {
            labels: chartData.map(item => item.province),
            datasets: [{
                label: "Average Rainfall (mm)",
                data: values,
                backgroundColor: chartData.map(item => item.province === currentProvince ? "#0EA5E9" : "#29B6F6"),
                borderColor: "#1565C0",
                borderWidth: 1,
                borderRadius: 8
            }]
        },
        options: createCommonOptions({
            showPercentLabels: true,
            percentSource: values,
            indexAxis: "y"
        })
    });
}

function renderDistributionChart(distributionData) {
    const ctx = document.getElementById("rainfallDistributionChart").getContext("2d");
    if (rainfallDistributionChart) rainfallDistributionChart.destroy();

    const counts = distributionData?.counts || [];
    rainfallDistributionChart = new Chart(ctx, {
        type: "bar",
        data: {
            labels: distributionData?.bins || [],
            datasets: [{
                label: "Frequency",
                data: counts,
                backgroundColor: "#90CAF9",
                borderColor: "#1565C0",
                borderWidth: 1,
                borderRadius: 6
            }]
        },
        options: {
            ...createCommonOptions({
                showPercentLabels: true,
                percentSource: counts,
                yLabel: "Number of Records"
            }),
            plugins: {
                ...createCommonOptions({
                    showPercentLabels: true,
                    percentSource: counts,
                    yLabel: "Number of Records"
                }).plugins,
                tooltip: {
                    callbacks: {
                        label(context) {
                            const value = Number(context.raw);
                            const percent = getPercentShareLabel(value, counts);
                            return percent
                                ? `Frequency: ${value} records (${percent})`
                                : `Frequency: ${value} records`;
                        }
                    }
                }
            }
        }
    });
}

async function loadRainfallData(reason = "updated") {
    const selectedYear = getSelectedYear();
    currentYear = selectedYear;
    updateFilterSummary();

    if (currentLoadController) currentLoadController.abort();
    currentLoadController = new AbortController();
    const signal = currentLoadController.signal;
    setLoadingState(true);

    try {
        const [overviewRes, trendRes, monthlyRes, rankingsRes, distributionRes] = await Promise.all([
            fetchJSON(`/api/v1/overview${buildQuery({ province: currentProvince, year: selectedYear })}`, signal),
            fetchJSON(`/api/v1/rainfall-trend${buildQuery({ province: currentProvince })}`, signal),
            fetchJSON(`/api/v1/rainfall-trend${buildQuery({ province: currentProvince, year: selectedYear })}`, signal),
            fetchJSON(`/api/v1/rankings/rainfall?year=${selectedYear}`, signal),
            fetchJSON(`/api/v1/rainfall-distribution${buildQuery({ province: currentProvince, year: selectedYear })}`, signal)
        ]);

        const overview = overviewRes?.success ? (overviewRes.data || {}) : {};
        const trendData = trendRes?.success ? (trendRes.data || { years: [], avg_rainfall: [] }) : { years: [], avg_rainfall: [] };
        const monthlyData = monthlyRes?.success ? (monthlyRes.data || { years: [], avg_rainfall: [] }) : { years: [], avg_rainfall: [] };
        const rankings = rankingsRes?.success ? (rankingsRes.data?.rankings || []) : [];
        const distributionData = distributionRes?.success ? (distributionRes.data || { bins: [], counts: [] }) : { bins: [], counts: [] };

        renderSummaryCards(overview, trendData);
        renderTrendChart(trendData);
        renderYearlyTotalsChart(trendData);
        renderProvincialComparison(rankings);
        renderMonthlyPattern(monthlyData);
        renderDistributionChart(distributionData);

        const trendSubtitle = document.getElementById("rainfallTrendSubtitle");
        if (trendSubtitle) {
            const change = computePercentChange(trendData?.avg_rainfall || []);
            const changeText = change === null ? "Trend percentage is not available yet." : `${change > 0 ? "+" : ""}${change.toFixed(1)}% change across the period.`;
            trendSubtitle.innerHTML = `<i class="fas fa-info-circle"></i> Rainfall trend for ${getActiveProvinceLabel()} across the available coverage period. ${changeText}`;
        }

        const yearlyTotalsSubtitle = document.getElementById("rainfallYearlyTotalsSubtitle");
        if (yearlyTotalsSubtitle) {
            yearlyTotalsSubtitle.innerHTML = `<i class="fas fa-info-circle"></i> Yearly rainfall totals help reveal the wettest and driest years in the record. Percent labels show each year's share of the full rainfall total.`;
        }

        const provinceSubtitle = document.getElementById("rainfallProvinceSubtitle");
        if (provinceSubtitle) {
            provinceSubtitle.innerHTML = `<i class="fas fa-info-circle"></i> Province comparison for ${currentYear}. Percent labels show each province's share of rainfall in the displayed ranking.`;
        }

        const distributionSubtitle = document.getElementById("rainfallDistributionSubtitle");
        if (distributionSubtitle) {
            const minValue = formatDecimal(distributionData?.min, 1);
            const maxValue = formatDecimal(distributionData?.max, 1);
            distributionSubtitle.innerHTML = `<i class="fas fa-info-circle"></i> Rainfall values in this view range from ${minValue} mm to ${maxValue} mm. Percent labels show the share of records in each rainfall band.`;
        }

        const hasData = Number.isFinite(Number(overview?.avg_rainfall)) || rankings.length > 0;
        if (reason !== "initial" || !hasData) {
            const notification = buildRainfallStatusNotification(overview, rankings, selectedYear, reason);
            sendNotification(notification.type, notification.title, notification.message, {
                id: hasData ? "rainfall-status" : "rainfall-empty",
                duration: 4200,
                meta: notification.meta
            });
        }
    } catch (error) {
        if (error?.name === "AbortError") return;
        console.error("Error loading rainfall analysis:", error);
        setText("rainfallNotes", "Rainfall analysis could not be loaded right now. Please check the dataset connection and try again.");
        sendNotification("danger", "Rainfall analysis unavailable", "Rainfall analysis could not be loaded right now.", {
            id: "rainfall-load-error",
            duration: 6500
        });
    } finally {
        if (currentLoadController?.signal === signal) currentLoadController = null;
        setLoadingState(false);
    }
}

document.addEventListener("DOMContentLoaded", async () => {
    await initializeFilters();
    setupEventListeners();
    await loadRainfallData("initial");
});
