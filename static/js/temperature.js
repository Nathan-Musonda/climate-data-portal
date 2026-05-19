let temperatureTrendChart;
let temperatureYearlyChart;
let temperatureDistrictChart;
let temperatureRangeChart;
let temperatureDistributionChart;
let currentDistrict = "";
let currentYear = "";
let availableYears = [];
let currentLoadController = null;
const temperatureNotifier = typeof window.createPageNotifier === "function"
    ? window.createPageNotifier("temperature")
    : null;
const DEGREE_C = "\u00B0C";
const climateMonthly = window.ClimateMonthly || {};
const CANONICAL_MONTHS = Array.isArray(climateMonthly.CANONICAL_MONTHS)
    ? climateMonthly.CANONICAL_MONTHS.slice()
    : ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function sendNotification(type, title, message, options = {}) {
    if (typeof window.notifyApp !== "function") return;
    if (temperatureNotifier) {
        temperatureNotifier(type, title, message, {
            id: options.id,
            duration: options.duration,
            sticky: options.sticky,
            meta: options.meta || "Temperature",
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
        meta: options.meta || "Temperature",
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

function buildTemperatureCoverage(maxValues, minValues) {
    if (typeof climateMonthly.buildMultiSeriesCoverage === "function") {
        return climateMonthly.buildMultiSeriesCoverage([
            { label: "max only", values: maxValues },
            { label: "min only", values: minValues }
        ]);
    }
    const missingMonthLabels = [];
    const partialMonthLabels = [];
    let observedMonthCount = 0;

    CANONICAL_MONTHS.forEach((month, index) => {
        const hasMax = toFiniteNumber(maxValues[index]) !== null;
        const hasMin = toFiniteNumber(minValues[index]) !== null;

        if (hasMax || hasMin) {
            observedMonthCount += 1;
        }

        if (!hasMax && !hasMin) {
            missingMonthLabels.push(month);
            return;
        }

        if (hasMax !== hasMin) {
            partialMonthLabels.push(`${month} (${hasMax ? "max only" : "min only"})`);
        }
    });

    return {
        observedMonthCount,
        missingMonthLabels,
        partialMonthLabels,
        isCompletePeriod: observedMonthCount === CANONICAL_MONTHS.length && partialMonthLabels.length === 0
    };
}

function setText(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = value;
}

function getActiveDistrictLabel() {
    return currentDistrict || "All Districts";
}

function buildTemperatureStatusNotification(overview, rankings, year, reason = "updated") {
    const viewLabel = `${getActiveDistrictLabel()}, ${year}`;
    const intro = reason === "reset"
        ? `Filters reset to ${viewLabel}.`
        : `Updated to ${viewLabel}.`;
    const hottestDistrict = Array.isArray(rankings) && rankings.length ? rankings[0] : null;
    const avgMax = Number(overview?.avg_temp_max);

    if (hottestDistrict && Number.isFinite(Number(hottestDistrict.value))) {
        return {
            type: Number(hottestDistrict.value) >= 35 ? "warning" : "info",
            title: reason === "reset" ? "Temperature filters reset" : "Temperature view updated",
            message: `${intro} ${hottestDistrict.province} is currently the hottest district at ${formatDecimal(hottestDistrict.value, 1)} ${DEGREE_C}.`,
            meta: "Temperature"
        };
    }

    if (Number.isFinite(avgMax)) {
        return {
            type: "success",
            title: reason === "reset" ? "Temperature filters reset" : "Temperature view updated",
            message: `${intro} Average maximum temperature for the active view is ${formatDecimal(avgMax, 1)} ${DEGREE_C}.`,
            meta: "Temperature"
        };
    }

    return {
        type: "info",
        title: "Temperature data limited",
        message: `${intro} No temperature records were returned for this selection.`,
        meta: "Temperature"
    };
}

function updateFilterSummary() {
    const yearLabel = currentYear || "Latest complete year";
    const badge = document.getElementById("temperatureFilterSummary");
    if (badge) {
        badge.innerHTML = `<i class="fas fa-sliders-h"></i><span>${getActiveDistrictLabel()}, ${yearLabel}</span>`;
    }
}

function setLoadingState(isLoading) {
    const applyBtn = document.getElementById("temperatureApplyBtn");
    const resetBtn = document.getElementById("temperatureResetBtn");

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

function createCommonOptions(yLabel, indexAxis = "x", { forceAllXTicks = false } = {}) {
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
        plugins: {
            legend: {
                labels: { color: "#334155" }
            }
        },
        scales
    };
}

async function fetchJSON(url, signal) {
    const response = await fetch(url, signal ? { signal } : undefined);
    return response.json();
}

async function initializeFilters() {
    const districtSelect = document.getElementById("temperatureDistrict");
    const yearSelect = document.getElementById("temperatureYear");

    let years = Array.from(yearSelect?.options || [])
        .map(option => Number(option.value))
        .filter(Number.isFinite);

    try {
        const yearsResult = await fetchJSON("/api/v1/years");
        if (yearsResult?.success && Array.isArray(yearsResult.data)) {
            years = yearsResult.data.map(Number).filter(Number.isFinite);
        }
    } catch (error) {
        console.error("Temperature years load failed:", error);
    }

    availableYears = Array.from(new Set(years)).sort((a, b) => a - b);
    if (yearSelect) {
        yearSelect.innerHTML = '<option value="">Latest complete year</option>';
        availableYears.forEach(year => yearSelect.appendChild(new Option(year, year)));
        currentYear = yearSelect.value || getSelectedYear();
        yearSelect.value = currentYear;
    }

    currentDistrict = districtSelect?.value || "";
    updateFilterSummary();
}

function setupEventListeners() {
    const districtSelect = document.getElementById("temperatureDistrict");
    const yearSelect = document.getElementById("temperatureYear");
    const applyBtn = document.getElementById("temperatureApplyBtn");
    const resetBtn = document.getElementById("temperatureResetBtn");

    if (applyBtn) {
        applyBtn.addEventListener("click", () => {
            currentDistrict = districtSelect?.value || "";
            currentYear = yearSelect?.value || getSelectedYear();
            updateFilterSummary();
            loadTemperatureData("updated");
        });
    }

    if (resetBtn) {
        resetBtn.addEventListener("click", () => {
            if (districtSelect) districtSelect.value = "";
            currentYear = "";
            if (yearSelect) yearSelect.value = getSelectedYear();
            currentDistrict = "";
            currentYear = yearSelect?.value || getSelectedYear();
            updateFilterSummary();
            loadTemperatureData("reset");
        });
    }

    if (districtSelect) {
        districtSelect.addEventListener("change", () => {
            currentDistrict = districtSelect.value || "";
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

function computeYearlyMeanSeries(data) {
    const years = data?.years || [];
    const maxValues = data?.avg_max_temp || [];
    const minValues = data?.avg_min_temp || [];
    return years.map((year, index) => ({
        year,
        value: (Number(maxValues[index] || 0) + Number(minValues[index] || 0)) / 2
    })).filter(item => Number.isFinite(item.value));
}

function renderSummaryCards(overview, trendData, rankings) {
    document.getElementById("avgMaxTemperature").innerHTML = `${formatDecimal(overview?.avg_temp_max, 1)} <small>C</small>`;
    document.getElementById("avgMinTemperature").innerHTML = `${formatDecimal(overview?.avg_temp_min, 1)} <small>C</small>`;

    const yearlyMeanSeries = computeYearlyMeanSeries(trendData);
    const hottestYear = yearlyMeanSeries.length
        ? yearlyMeanSeries.reduce((best, item) => item.value > best.value ? item : best, yearlyMeanSeries[0])
        : null;
    const coolestYear = yearlyMeanSeries.length
        ? yearlyMeanSeries.reduce((best, item) => item.value < best.value ? item : best, yearlyMeanSeries[0])
        : null;

    document.getElementById("hottestYearValue").textContent = hottestYear ? hottestYear.year : "--";
    document.getElementById("hottestYearNote").textContent = hottestYear
        ? `${formatDecimal(hottestYear.value, 1)} ${DEGREE_C} annual average temperature.`
        : "No yearly temperature series available.";

    document.getElementById("coolestYearValue").textContent = coolestYear ? coolestYear.year : "--";
    document.getElementById("coolestYearNote").textContent = coolestYear
        ? `${formatDecimal(coolestYear.value, 1)} ${DEGREE_C} annual average temperature.`
        : "No yearly temperature series available.";

    const hottestDistrict = Array.isArray(rankings) && rankings.length ? rankings[0] : null;
    const notes = document.getElementById("temperatureNotes");
    if (notes) {
        notes.innerHTML = hottestDistrict
            ? `Temperature values are summarized from the Zambia climate dataset using <code>Temp_Max_C</code>, <code>Temp_Min_C</code>, <code>Date</code>, and district-level records. In ${currentYear}, the hottest district in this comparison is <strong>${hottestDistrict.province}</strong> at <strong>${formatDecimal(hottestDistrict.value, 1)} ${DEGREE_C}</strong>.`
            : `Temperature values are summarized from the Zambia climate dataset using <code>Temp_Max_C</code>, <code>Temp_Min_C</code>, <code>Date</code>, and district-level records, with a district filter for focused analysis.`;
    }
}

function renderTrendChart(data) {
    const ctx = document.getElementById("temperatureTrendChart").getContext("2d");
    if (temperatureTrendChart) temperatureTrendChart.destroy();

    temperatureTrendChart = new Chart(ctx, {
        type: "line",
        data: {
            labels: data?.years || [],
            datasets: [
                {
                    label: `Average Max Temperature (${DEGREE_C})`,
                    data: data?.avg_max_temp || [],
                    borderColor: "#dc2626",
                    backgroundColor: "rgba(220, 38, 38, 0.12)",
                    fill: false,
                    tension: 0.25,
                    pointRadius: 3
                },
                {
                    label: `Average Min Temperature (${DEGREE_C})`,
                    data: data?.avg_min_temp || [],
                    borderColor: "#2563eb",
                    backgroundColor: "rgba(37, 99, 235, 0.12)",
                    fill: false,
                    tension: 0.25,
                    pointRadius: 3
                }
            ]
        },
        options: createCommonOptions(`Temperature (${DEGREE_C})`)
    });
}

function renderYearlyChart(data) {
    const ctx = document.getElementById("temperatureYearlyChart").getContext("2d");
    if (temperatureYearlyChart) temperatureYearlyChart.destroy();

    temperatureYearlyChart = new Chart(ctx, {
        type: "bar",
        data: {
            labels: data?.years || [],
            datasets: [
                {
                    label: `Average Max Temperature (${DEGREE_C})`,
                    data: data?.avg_max_temp || [],
                    backgroundColor: "#fb923c",
                    borderRadius: 8
                },
                {
                    label: `Average Min Temperature (${DEGREE_C})`,
                    data: data?.avg_min_temp || [],
                    backgroundColor: "#60a5fa",
                    borderRadius: 8
                }
            ]
        },
        options: createCommonOptions(`Temperature (${DEGREE_C})`)
    });
}

function renderDistrictChart(rankings) {
    const ctx = document.getElementById("temperatureDistrictChart").getContext("2d");
    if (temperatureDistrictChart) temperatureDistrictChart.destroy();

    const topDistricts = Array.isArray(rankings) ? rankings.slice(0, 10) : [];
    if (currentDistrict && Array.isArray(rankings) && rankings.length) {
        const selected = rankings.find(item => item.province === currentDistrict);
        const alreadyIncluded = topDistricts.some(item => item.province === currentDistrict);
        if (selected && !alreadyIncluded) {
            topDistricts[topDistricts.length - 1] = selected;
        }
    }

    temperatureDistrictChart = new Chart(ctx, {
        type: "bar",
        data: {
            labels: topDistricts.map(item => item.province),
            datasets: [{
                label: `Average Max Temperature (${DEGREE_C})`,
                data: topDistricts.map(item => item.value),
                backgroundColor: topDistricts.map(item => item.province === currentDistrict ? "#ea580c" : "#fdba74"),
                borderRadius: 8
            }]
        },
        options: createCommonOptions(`Temperature (${DEGREE_C})`, "y")
    });
}

function renderRangeChart(data) {
    const ctx = document.getElementById("temperatureRangeChart").getContext("2d");
    if (temperatureRangeChart) temperatureRangeChart.destroy();

    const normalizedData = typeof climateMonthly.normalizePayload === "function"
        ? climateMonthly.normalizePayload(data, ["avg_max_temp", "avg_min_temp"])
        : (data || {});
    const labels = normalizedData?.labels || CANONICAL_MONTHS.slice();
    const maxValues = normalizedData?.avg_max_temp || alignMonthlySeries(data?.avg_max_temp || [], {
        labels: data?.years || data?.labels || [],
        monthNumbers: data?.month_numbers || []
    });
    const minValues = normalizedData?.avg_min_temp || alignMonthlySeries(data?.avg_min_temp || [], {
        labels: data?.years || data?.labels || [],
        monthNumbers: data?.month_numbers || []
    });
    const coverage = buildTemperatureCoverage(maxValues, minValues);
    const observedMonthCount = coverage.observedMonthCount;
    const missingMonthLabels = coverage.missingMonthLabels;
    const partialMonthLabels = coverage.partialMonthLabels;
    const monthlyOptions = createCommonOptions(`Temperature (${DEGREE_C})`, "x", { forceAllXTicks: true });

    temperatureRangeChart = new Chart(ctx, {
        type: "line",
        data: {
            labels,
            datasets: [
                {
                    label: `Monthly Max Temperature (${DEGREE_C})`,
                    data: maxValues,
                    borderColor: "#dc2626",
                    backgroundColor: "rgba(220, 38, 38, 0.08)",
                    tension: 0,
                    pointRadius: 4,
                    pointHoverRadius: 6,
                    pointBackgroundColor: "#dc2626",
                    spanGaps: false,
                    fill: false
                },
                {
                    label: `Monthly Min Temperature (${DEGREE_C})`,
                    data: minValues,
                    borderColor: "#2563eb",
                    backgroundColor: "rgba(37, 99, 235, 0.08)",
                    tension: 0,
                    pointRadius: 4,
                    pointHoverRadius: 6,
                    pointBackgroundColor: "#2563eb",
                    spanGaps: false,
                    fill: false
                }
            ]
        },
        options: {
            ...monthlyOptions,
            plugins: {
                ...monthlyOptions.plugins,
                tooltip: {
                    callbacks: {
                        label(context) {
                            const value = toFiniteNumber(context.raw);
                            if (value === null) {
                                return `${context.dataset.label}: No monthly record`;
                            }
                            return `${context.dataset.label}: ${formatDecimal(value, 1)} ${DEGREE_C}`;
                        }
                    }
                }
            },
            scales: {
                ...monthlyOptions.scales,
                y: {
                    ...monthlyOptions.scales.y,
                    title: {
                        display: true,
                        text: `Temperature (${DEGREE_C})`,
                        color: "#475569"
                    }
                }
            }
        }
    });

    const subtitle = document.getElementById("temperatureRangeSubtitle");
    if (!subtitle) return;

    const monthlyPairs = labels.map((month, index) => {
        const max = toFiniteNumber(maxValues[index]);
        const min = toFiniteNumber(minValues[index]);
        return {
            month,
            max,
            min,
            range: max - min
        };
    }).filter(item => Number.isFinite(item.max) && Number.isFinite(item.min));

    const hottestMonth = monthlyPairs.length
        ? monthlyPairs.reduce((best, item) => item.max > best.max ? item : best, monthlyPairs[0])
        : null;
    const avgRange = monthlyPairs.length
        ? monthlyPairs.reduce((sum, item) => sum + item.range, 0) / monthlyPairs.length
        : null;

    if (missingMonthLabels.length || partialMonthLabels.length) {
        const missingText = missingMonthLabels.length
            ? ` Missing months: ${missingMonthLabels.join(", ")}.`
            : "";
        const partialText = partialMonthLabels.length
            ? ` Partial months: ${partialMonthLabels.join(", ")}.`
            : "";
        const hottestObservedText = hottestMonth
            ? ` Hottest observed month: ${hottestMonth.month} at ${formatDecimal(hottestMonth.max, 1)} ${DEGREE_C}.`
            : "";
        subtitle.innerHTML = `<i class="fas fa-info-circle"></i> Monthly temperature coverage is available for ${observedMonthCount} of 12 months.${missingText}${partialText} Lines break where records are unavailable.${hottestObservedText}`;
        return;
    }

    subtitle.innerHTML = hottestMonth
        ? `<i class="fas fa-info-circle"></i> ${hottestMonth.month} is the hottest month in this view at ${formatDecimal(hottestMonth.max, 1)} ${DEGREE_C}, with an average max-min range of ${formatDecimal(avgRange, 1)} ${DEGREE_C}.`
        : `<i class="fas fa-info-circle"></i> Monthly maximum and minimum temperatures reveal seasonal heat and temperature range.`;
}

function renderDistributionChart(distributionData) {
    const ctx = document.getElementById("temperatureDistributionChart").getContext("2d");
    if (temperatureDistributionChart) temperatureDistributionChart.destroy();

    temperatureDistributionChart = new Chart(ctx, {
        type: "bar",
        data: {
            labels: distributionData?.bins || [],
            datasets: [{
                label: "Frequency",
                data: distributionData?.counts || [],
                backgroundColor: "#cbd5e1",
                borderRadius: 6
            }]
        },
        options: createCommonOptions("Number of Records")
    });
}

async function loadTemperatureData(reason = "updated") {
    const selectedYear = getSelectedYear();
    currentYear = selectedYear;
    updateFilterSummary();

    if (currentLoadController) currentLoadController.abort();
    currentLoadController = new AbortController();
    const signal = currentLoadController.signal;
    setLoadingState(true);

    try {
        const [overviewRes, trendRes, monthlyRes, rankingsRes, distributionRes] = await Promise.all([
            fetchJSON(`/api/v1/overview${buildQuery({ district: currentDistrict, year: selectedYear })}`, signal),
            fetchJSON(`/api/v1/temperature-trend${buildQuery({ district: currentDistrict })}`, signal),
            fetchJSON(`/api/v1/temperature-trend${buildQuery({ district: currentDistrict, year: selectedYear })}`, signal),
            fetchJSON(`/api/v1/rankings/temperature?year=${selectedYear}&scope=district`, signal),
            fetchJSON(`/api/v1/temperature-distribution${buildQuery({ district: currentDistrict, year: selectedYear })}`, signal)
        ]);

        const overview = overviewRes?.success ? (overviewRes.data || {}) : {};
        const trendData = trendRes?.success ? (trendRes.data || { years: [], avg_max_temp: [], avg_min_temp: [] }) : { years: [], avg_max_temp: [], avg_min_temp: [] };
        const monthlyData = monthlyRes?.success ? (monthlyRes.data || { years: [], avg_max_temp: [], avg_min_temp: [] }) : { years: [], avg_max_temp: [], avg_min_temp: [] };
        const rankings = rankingsRes?.success ? (rankingsRes.data?.rankings || []) : [];
        const distributionData = distributionRes?.success ? (distributionRes.data || { bins: [], counts: [] }) : { bins: [], counts: [] };

        renderSummaryCards(overview, trendData, rankings);
        renderTrendChart(trendData);
        renderYearlyChart(trendData);
        renderDistrictChart(rankings);
        renderRangeChart(monthlyData);
        renderDistributionChart(distributionData);

        const trendSubtitle = document.getElementById("temperatureTrendSubtitle");
        if (trendSubtitle) {
            const maxTemps = trendData?.avg_max_temp || [];
            const warmingText = maxTemps.length >= 2 && Number.isFinite(Number(maxTemps[0])) && Number.isFinite(Number(maxTemps[maxTemps.length - 1]))
                ? `${formatDecimal(Number(maxTemps[maxTemps.length - 1]) - Number(maxTemps[0]), 1)} ${DEGREE_C} change across the period.`
                : "Trend change is not available yet.";
            trendSubtitle.innerHTML = `<i class="fas fa-info-circle"></i> Temperature trend for ${getActiveDistrictLabel()} across the available coverage period. ${warmingText}`;
        }

        const yearlySubtitle = document.getElementById("temperatureYearlySubtitle");
        if (yearlySubtitle) {
            yearlySubtitle.innerHTML = `<i class="fas fa-info-circle"></i> Yearly maximum and minimum temperature averages help identify the hottest and coolest years in the record.`;
        }

        const districtSubtitle = document.getElementById("temperatureDistrictSubtitle");
        if (districtSubtitle) {
            const hottestDistrict = rankings.length ? rankings[0] : null;
            districtSubtitle.innerHTML = hottestDistrict
                ? `<i class="fas fa-info-circle"></i> District comparison for ${currentYear}. ${hottestDistrict.province} is currently the hottest district in this ranking at ${formatDecimal(hottestDistrict.value, 1)} ${DEGREE_C}.`
                : `<i class="fas fa-info-circle"></i> District comparison for ${currentYear}.`;
        }

        const distributionSubtitle = document.getElementById("temperatureDistributionSubtitle");
        if (distributionSubtitle) {
            const minValue = formatDecimal(distributionData?.min, 1);
            const maxValue = formatDecimal(distributionData?.max, 1);
            distributionSubtitle.innerHTML = `<i class="fas fa-info-circle"></i> Maximum temperatures in this view range from ${minValue} ${DEGREE_C} to ${maxValue} ${DEGREE_C}.`;
        }

        const hasData = Number.isFinite(Number(overview?.avg_temp_max)) || rankings.length > 0;
        if (reason !== "initial" || !hasData) {
            const notification = buildTemperatureStatusNotification(overview, rankings, selectedYear, reason);
            sendNotification(notification.type, notification.title, notification.message, {
                id: hasData ? "temperature-status" : "temperature-empty",
                duration: 4200,
                meta: notification.meta
            });
        }
    } catch (error) {
        if (error?.name === "AbortError") return;
        console.error("Error loading temperature analysis:", error);
        setText("temperatureNotes", "Temperature analysis could not be loaded right now. Please check the dataset connection and try again.");
        sendNotification("danger", "Temperature analysis unavailable", "Temperature analysis could not be loaded right now.", {
            id: "temperature-load-error",
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
    await loadTemperatureData("initial");
});
