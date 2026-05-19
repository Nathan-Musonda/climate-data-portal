let droughtTrendChart;
let droughtSeverityChart;
let soilMoistureChart;
let droughtProvinceChart;
let currentDistrict = "";
let currentYear = "";
let availableYears = [];
let currentLoadController = null;
const droughtNotifier = typeof window.createPageNotifier === "function"
    ? window.createPageNotifier("drought")
    : null;
const climateMonthly = window.ClimateMonthly || {};

function sendNotification(type, title, message, options = {}) {
    if (typeof window.notifyApp !== "function") return;
    if (droughtNotifier) {
        droughtNotifier(type, title, message, {
            id: options.id,
            duration: options.duration,
            sticky: options.sticky,
            meta: options.meta || "Drought",
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
        meta: options.meta || "Drought",
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
    const n = Number(value);
    return Number.isFinite(n) ? n.toFixed(digits) : "--";
}

function resolveTrendLabels(payload) {
    const normalized = typeof climateMonthly.normalizePayload === "function"
        ? climateMonthly.normalizePayload(payload)
        : (payload || {});
    return Array.isArray(normalized?.labels) ? normalized.labels : [];
}

function resolveTrendValues(payload, key) {
    if (typeof climateMonthly.getSeries === "function") {
        return climateMonthly.getSeries(payload, key);
    }
    return Array.isArray(payload?.[key]) ? payload[key] : [];
}

function setText(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = value;
}

function getActiveDistrictLabel() {
    return currentDistrict || "All Districts";
}

function buildDroughtStatusNotification(summary, rankings, year, reason = "updated") {
    const viewLabel = `${getActiveDistrictLabel()}, ${year}`;
    const intro = reason === "reset"
        ? `Filters reset to ${viewLabel}.`
        : `Updated to ${viewLabel}.`;
    const dominant = Array.isArray(summary) && summary.length
        ? summary.reduce((best, item) => Number(item.count) > Number(best.count) ? item : best, summary[0])
        : null;
    const topProvince = Array.isArray(rankings) && rankings.length ? rankings[0] : null;

    if (topProvince && Number.isFinite(Number(topProvince.value))) {
        return {
            type: Number(topProvince.value) >= 1.5 ? "warning" : "info",
            title: reason === "reset" ? "Drought filters reset" : "Drought view updated",
            message: `${intro} ${topProvince.province} currently records the highest drought score at ${formatDecimal(topProvince.value, 2)}.`,
            meta: "Drought"
        };
    }

    if (dominant) {
        return {
            type: String(dominant.severity || "").toLowerCase() === "severe" ? "warning" : "info",
            title: reason === "reset" ? "Drought filters reset" : "Drought view updated",
            message: `${intro} ${dominant.severity} is the dominant drought category at ${formatDecimal(dominant.percentage, 1)}% of records.`,
            meta: "Drought"
        };
    }

    return {
        type: "info",
        title: "Drought data limited",
        message: `${intro} No drought records were returned for this selection.`,
        meta: "Drought"
    };
}

function updateFilterSummary() {
    const yearLabel = currentYear || "Latest complete year";
    const badge = document.getElementById("droughtFilterSummary");
    if (badge) {
        badge.innerHTML = `<i class="fas fa-sliders-h"></i><span>${getActiveDistrictLabel()}, ${yearLabel}</span>`;
    }
}

function setLoadingState(isLoading) {
    const applyBtn = document.getElementById("droughtApplyBtn");
    const resetBtn = document.getElementById("droughtResetBtn");

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

function createCommonOptions(yLabel, indexAxis = "x", beginAtZero = true) {
    const isHorizontal = indexAxis === "y";
    const scales = isHorizontal
        ? {
            x: {
                beginAtZero,
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
                    maxRotation: 45,
                    minRotation: 0
                }
            },
            y: {
                beginAtZero,
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

function getSeverityPercentage(summary, severity) {
    const match = (summary || []).find(item => String(item.severity).toLowerCase() === severity.toLowerCase());
    return match ? Number(match.percentage) : null;
}

async function initializeFilters() {
    const districtSelect = document.getElementById("droughtDistrict");
    const yearSelect = document.getElementById("droughtYear");

    let years = Array.from(yearSelect?.options || [])
        .map(option => Number(option.value))
        .filter(Number.isFinite);

    try {
        const yearsResult = await fetchJSON("/api/v1/years");
        if (yearsResult?.success && Array.isArray(yearsResult.data)) {
            years = yearsResult.data.map(Number).filter(Number.isFinite);
        }
    } catch (error) {
        console.error("Drought years load failed:", error);
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
    const districtSelect = document.getElementById("droughtDistrict");
    const yearSelect = document.getElementById("droughtYear");
    const applyBtn = document.getElementById("droughtApplyBtn");
    const resetBtn = document.getElementById("droughtResetBtn");

    if (applyBtn) {
        applyBtn.addEventListener("click", () => {
            currentDistrict = districtSelect?.value || "";
            currentYear = yearSelect?.value || getSelectedYear();
            updateFilterSummary();
            loadDroughtData("updated");
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
            loadDroughtData("reset");
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

function renderSummaryCards(overview, summary, rankings) {
    const severePct = getSeverityPercentage(summary, "Severe");
    const moderatePct = getSeverityPercentage(summary, "Moderate");

    document.getElementById("severeDroughtPct").innerHTML = `${formatDecimal(severePct, 1)} <small>%</small>`;
    document.getElementById("moderateDroughtPct").innerHTML = `${formatDecimal(moderatePct, 1)} <small>%</small>`;
    document.getElementById("avgSoilMoisture").innerHTML = `${formatDecimal(overview?.avg_soil_moisture, 1)} <small>%</small>`;

    const mostAffectedProvince = Array.isArray(rankings) && rankings.length ? rankings[0] : null;
    const notes = document.getElementById("droughtNotes");
    if (notes) {
        notes.innerHTML = mostAffectedProvince
            ? `Drought analysis uses <code>SoilMoisture_pct</code>, <code>DroughtSeverity</code>, <code>Province</code>, and <code>Date</code> from the Zambia climate dataset. In ${currentYear}, the most affected province in this ranking is <strong>${mostAffectedProvince.province}</strong> with an average drought score of <strong>${formatDecimal(mostAffectedProvince.value, 2)}</strong>.`
            : `Drought analysis uses <code>SoilMoisture_pct</code>, <code>DroughtSeverity</code>, <code>Province</code>, and <code>Date</code> from the Zambia climate dataset.`;
    }
}

function renderDroughtTrendChart(data) {
    const ctx = document.getElementById("droughtTrendChart").getContext("2d");
    if (droughtTrendChart) droughtTrendChart.destroy();
    const isMonthly = data?.period_type === "month";
    const labels = resolveTrendLabels(data);
    const values = resolveTrendValues(data, "avg_drought_score");

    droughtTrendChart = new Chart(ctx, {
        type: "line",
        data: {
            labels,
            datasets: [{
                label: "Average Drought Score",
                data: values,
                borderColor: "#b45309",
                backgroundColor: "rgba(180, 83, 9, 0.12)",
                tension: isMonthly ? 0 : 0.25,
                spanGaps: false,
                pointRadius: 3,
                fill: true
            }]
        },
        options: {
            ...createCommonOptions("Average Drought Score", "x", true),
            scales: {
                ...createCommonOptions("Average Drought Score", "x", true).scales,
                x: {
                    ...createCommonOptions("Average Drought Score", "x", true).scales.x,
                    ticks: isMonthly
                        ? { color: "#475569", autoSkip: false, maxRotation: 0, minRotation: 0 }
                        : createCommonOptions("Average Drought Score", "x", true).scales.x.ticks
                }
            }
        }
    });
}

function renderSeverityChart(summary) {
    const ctx = document.getElementById("droughtSeverityChart").getContext("2d");
    if (droughtSeverityChart) droughtSeverityChart.destroy();

    const colorMap = {
        "Severe": "#dc2626",
        "Moderate": "#f59e0b",
        "Mild": "#facc15",
        "No Drought": "#16a34a"
    };

    droughtSeverityChart = new Chart(ctx, {
        type: "doughnut",
        data: {
            labels: (summary || []).map(item => item.severity),
            datasets: [{
                data: (summary || []).map(item => item.count),
                backgroundColor: (summary || []).map(item => colorMap[item.severity] || "#94a3b8"),
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: "bottom",
                    labels: { color: "#334155" }
                },
                tooltip: {
                    callbacks: {
                        label(context) {
                            const item = (summary || [])[context.dataIndex];
                            if (!item) return context.label;
                            return `${item.severity}: ${item.count} records (${formatDecimal(item.percentage, 1)}%)`;
                        }
                    }
                }
            }
        }
    });

    const subtitle = document.getElementById("droughtSeveritySubtitle");
    if (subtitle) {
        const dominant = Array.isArray(summary) && summary.length
            ? summary.reduce((best, item) => Number(item.count) > Number(best.count) ? item : best, summary[0])
            : null;
        subtitle.innerHTML = dominant
            ? `<i class="fas fa-info-circle"></i> ${dominant.severity} is the dominant drought category in this view at ${formatDecimal(dominant.percentage, 1)}%.`
            : `<i class="fas fa-info-circle"></i> Shows the balance between no drought, moderate drought, and severe drought in the selected view.`;
    }
}

function renderProvinceChart(rankings) {
    const ctx = document.getElementById("droughtProvinceChart").getContext("2d");
    if (droughtProvinceChart) droughtProvinceChart.destroy();

    const chartData = Array.isArray(rankings) ? rankings.slice(0, 10) : [];

    droughtProvinceChart = new Chart(ctx, {
        type: "bar",
        data: {
            labels: chartData.map(item => item.province),
            datasets: [{
                label: "Average Drought Score",
                data: chartData.map(item => item.value),
                backgroundColor: "#fbbf24",
                borderRadius: 8
            }]
        },
        options: createCommonOptions("Drought Score", "y")
    });
}

function renderSoilMoistureChart(data) {
    const ctx = document.getElementById("soilMoistureChart").getContext("2d");
    if (soilMoistureChart) soilMoistureChart.destroy();
    const isMonthly = data?.period_type === "month";
    const labels = resolveTrendLabels(data);
    const values = resolveTrendValues(data, "avg_soil_moisture");

    soilMoistureChart = new Chart(ctx, {
        type: "line",
        data: {
            labels,
            datasets: [{
                label: "Average Soil Moisture (%)",
                data: values,
                borderColor: "#0284c7",
                backgroundColor: "rgba(2, 132, 199, 0.10)",
                tension: isMonthly ? 0 : 0.25,
                spanGaps: false,
                pointRadius: 3,
                fill: true
            }]
        },
        options: {
            ...createCommonOptions("Soil Moisture (%)"),
            scales: {
                ...createCommonOptions("Soil Moisture (%)").scales,
                x: {
                    ...createCommonOptions("Soil Moisture (%)").scales.x,
                    ticks: isMonthly
                        ? { color: "#475569", autoSkip: false, maxRotation: 0, minRotation: 0 }
                        : createCommonOptions("Soil Moisture (%)").scales.x.ticks
                }
            }
        }
    });
}

function renderInsights(summary, trendData, soilData, rankings) {
    const container = document.getElementById("droughtInsights");
    if (!container) return;

    const insights = [];
    const dominant = Array.isArray(summary) && summary.length
        ? summary.reduce((best, item) => Number(item.count) > Number(best.count) ? item : best, summary[0])
        : null;
    if (dominant) {
        insights.push(`${dominant.severity} is the most common drought class in the active view at ${formatDecimal(dominant.percentage, 1)}% of records.`);
    }

    const mostAffectedProvince = Array.isArray(rankings) && rankings.length ? rankings[0] : null;
    if (mostAffectedProvince) {
        insights.push(`${mostAffectedProvince.province} currently ranks as the most drought-affected province in ${currentYear} with an average drought score of ${formatDecimal(mostAffectedProvince.value, 2)}.`);
    }

    const severeSeries = Array.isArray(trendData?.severe_pct) ? trendData.severe_pct : [];
    const trendYears = Array.isArray(trendData?.years) ? trendData.years : [];
    if (severeSeries.length && trendYears.length) {
        const highestSevereIndex = severeSeries.reduce((bestIndex, value, index, array) => Number(value) > Number(array[bestIndex]) ? index : bestIndex, 0);
        insights.push(`Severe drought pressure peaked in ${trendYears[highestSevereIndex]} at ${formatDecimal(severeSeries[highestSevereIndex], 1)}% of records.`);
    }

    const latestSoil = Array.isArray(soilData?.avg_soil_moisture) && soilData.avg_soil_moisture.length ? soilData.avg_soil_moisture[soilData.avg_soil_moisture.length - 1] : null;
    if (latestSoil !== null) {
        insights.push(`The latest soil moisture signal in this view is ${formatDecimal(latestSoil, 1)}%, helping explain how dry the land conditions are.`);
    }

    if (!insights.length) {
        container.innerHTML = `
            <div class="insight-item">
                <p>No drought insights are available yet for the current selection.</p>
            </div>
        `;
        return;
    }

    container.innerHTML = insights.map(item => `
        <div class="insight-item">
            <p>${item}</p>
        </div>
    `).join("");
}

async function loadDroughtData(reason = "updated") {
    const selectedYear = getSelectedYear();
    currentYear = selectedYear;
    updateFilterSummary();

    if (currentLoadController) currentLoadController.abort();
    currentLoadController = new AbortController();
    const signal = currentLoadController.signal;
    setLoadingState(true);

    try {
        const [overviewRes, summaryRes, trendRes, soilRes, rankingsRes] = await Promise.all([
            fetchJSON(`/api/v1/overview${buildQuery({ district: currentDistrict, year: selectedYear })}`, signal),
            fetchJSON(`/api/v1/drought-summary${buildQuery({ district: currentDistrict, year: selectedYear })}`, signal),
            fetchJSON(`/api/v1/drought-trend${buildQuery({ district: currentDistrict })}`, signal),
            fetchJSON(`/api/v1/soil-moisture-trend${buildQuery({ district: currentDistrict })}`, signal),
            fetchJSON(`/api/v1/rankings/drought?year=${selectedYear}`, signal)
        ]);

        const overview = overviewRes?.success ? (overviewRes.data || {}) : {};
        const summary = summaryRes?.success ? (summaryRes.data || []) : [];
        const trendData = trendRes?.success ? (trendRes.data || { years: [], avg_drought_score: [], severe_pct: [], moderate_pct: [] }) : { years: [], avg_drought_score: [], severe_pct: [], moderate_pct: [] };
        const soilData = soilRes?.success ? (soilRes.data || { years: [], avg_soil_moisture: [] }) : { years: [], avg_soil_moisture: [] };
        const rankings = rankingsRes?.success ? (rankingsRes.data?.rankings || []) : [];

        renderSummaryCards(overview, summary, rankings);
        renderSeverityChart(summary);
        renderDroughtTrendChart(trendData);
        renderSoilMoistureChart(soilData);
        renderProvinceChart(rankings);
        renderInsights(summary, trendData, soilData, rankings);

        const trendSubtitle = document.getElementById("droughtTrendSubtitle");
        if (trendSubtitle) {
            const scores = trendData?.avg_drought_score || [];
            const changeText = scores.length >= 2
                ? `${formatDecimal(Number(scores[scores.length - 1]) - Number(scores[0]), 2)} score change across the period.`
                : "Trend change is not available yet.";
            trendSubtitle.innerHTML = `<i class="fas fa-info-circle"></i> Drought trend for ${getActiveDistrictLabel()} across the available coverage period. ${changeText}`;
        }

        const soilSubtitle = document.getElementById("soilMoistureSubtitle");
        if (soilSubtitle) {
            soilSubtitle.innerHTML = `<i class="fas fa-info-circle"></i> ${getActiveDistrictLabel()} soil moisture pattern from 2015 to 2025. Lower soil moisture often aligns with stronger drought conditions.`;
        }

        const provinceSubtitle = document.getElementById("droughtProvinceSubtitle");
        if (provinceSubtitle) {
            const topProvince = rankings.length ? rankings[0] : null;
            provinceSubtitle.innerHTML = topProvince
                ? `<i class="fas fa-info-circle"></i> Province comparison for ${currentYear}. ${topProvince.province} records the highest drought score in this year view at ${formatDecimal(topProvince.value, 2)}.`
                : `<i class="fas fa-info-circle"></i> Shows which provinces are most affected by drought in the selected year.`;
        }

        const hasData = summary.length > 0 || rankings.length > 0;
        if (reason !== "initial" || !hasData) {
            const notification = buildDroughtStatusNotification(summary, rankings, selectedYear, reason);
            sendNotification(notification.type, notification.title, notification.message, {
                id: hasData ? "drought-status" : "drought-empty",
                duration: 4500,
                meta: notification.meta
            });
        }
    } catch (error) {
        if (error?.name === "AbortError") return;
        console.error("Error loading drought analysis:", error);
        setText("droughtNotes", "Drought analysis could not be loaded right now. Please check the dataset connection and try again.");
        sendNotification("danger", "Drought analysis unavailable", "Drought analysis could not be loaded right now.", {
            id: "drought-load-error",
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
    await loadDroughtData("initial");
});
