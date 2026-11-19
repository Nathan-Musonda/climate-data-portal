let droughtTrendChart;
let droughtSeverityChart;
let soilMoistureChart;
let droughtProvinceChart;
let currentDistrict = "";
let currentYear = "";
let currentMonth = "";
let availableYears = [];
let currentLoadController = null;
let districtProvinceLookup = {};
const droughtNotifier = typeof window.createPageNotifier === "function"
    ? window.createPageNotifier("drought")
    : null;
const climateMonthly = window.ClimateMonthly || {};
const FULL_MONTH_LABELS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

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

function getDistrictProvinceLabel(district = currentDistrict) {
    if (!district) return "";
    return districtProvinceLookup[district] || "";
}

function buildDroughtStatusNotification(summary, rankings, year, reason = "updated") {
    const viewLabel = `${getActiveDistrictLabel()}, ${year}, ${getSelectedMonthLabel()}`;
    const intro = reason === "reset"
        ? `Filters reset to ${viewLabel}.`
        : `Updated to ${viewLabel}.`;
    const dominant = Array.isArray(summary) && summary.length
        ? summary.reduce((best, item) => Number(item.count) > Number(best.count) ? item : best, summary[0])
        : null;
    const topProvince = Array.isArray(rankings) && rankings.length ? rankings[0] : null;
    const districtProvince = getDistrictProvinceLabel();

    if (currentDistrict && districtProvince) {
        return {
            type: "info",
            title: reason === "reset" ? "Drought filters reset" : "Drought view updated",
            message: `${intro} ${currentDistrict} belongs to ${districtProvince} Province.`,
            meta: "Drought"
        };
    }

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
            message: `${intro} ${dominant.severity} is the dominant drought level at ${formatDecimal(dominant.percentage, 1)}% of readings.`,
            meta: "Drought"
        };
    }

    return {
        type: "info",
        title: "Drought data limited",
        message: `${intro} No drought readings were returned for this selection.`,
        meta: "Drought"
    };
}

function updateFilterSummary() {
    const yearLabel = currentYear || "Latest complete year";
    const badge = document.getElementById("droughtFilterSummary");
    if (badge) {
        badge.innerHTML = `<i class="fas fa-sliders-h"></i><span>${getActiveDistrictLabel()}, ${yearLabel}, ${getSelectedMonthLabel()}</span>`;
    }
}

function getSelectedMonthLabel() {
    const monthNumber = Number(currentMonth);
    return Number.isInteger(monthNumber) && monthNumber >= 1 && monthNumber <= 12
        ? FULL_MONTH_LABELS[monthNumber - 1]
        : "All months";
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

function getDurationSentence(durationPayload, key) {
    const sentence = durationPayload?.[key]?.sentence;
    return typeof sentence === "string" && sentence.trim() ? sentence.trim() : "";
}

function buildAnnualSeries(years = [], values = []) {
    return (Array.isArray(years) ? years : [])
        .map((year, index) => ({
            year,
            value: Number(values?.[index])
        }))
        .filter(item => item.year !== null && item.year !== undefined && Number.isFinite(item.value));
}

function computeNormalValue(series = []) {
    if (!Array.isArray(series) || !series.length) return null;
    const total = series.reduce((sum, item) => sum + item.value, 0);
    return series.length ? total / series.length : null;
}

function formatPercentFromNormal(value, normalValue) {
    if (!Number.isFinite(value) || !Number.isFinite(normalValue) || normalValue === 0) return null;
    const change = ((value - normalValue) / normalValue) * 100;
    return `${change >= 0 ? "+" : ""}${change.toFixed(1)}%`;
}

function updateDroughtYearRecordCards(trendData = {}) {
    const annualSeries = buildAnnualSeries(trendData?.years, trendData?.avg_drought_score);
    const annualNormal = computeNormalValue(annualSeries);
    const highestValueNode = document.getElementById("droughtHighestYearValue");
    const highestNoteNode = document.getElementById("droughtHighestYearNote");
    const lowestValueNode = document.getElementById("droughtLowestYearValue");
    const lowestNoteNode = document.getElementById("droughtLowestYearNote");

    if (!annualSeries.length) {
        if (highestValueNode) highestValueNode.textContent = "--";
        if (highestNoteNode) highestNoteNode.textContent = "No annual drought record is available for this selection.";
        if (lowestValueNode) lowestValueNode.textContent = "--";
        if (lowestNoteNode) lowestNoteNode.textContent = "No annual drought record is available for this selection.";
        return;
    }

    const highestYear = annualSeries.reduce((best, item) => item.value > best.value ? item : best, annualSeries[0]);
    const lowestYear = annualSeries.reduce((best, item) => item.value < best.value ? item : best, annualSeries[0]);
    const highestPct = formatPercentFromNormal(highestYear.value, annualNormal);
    const lowestPct = formatPercentFromNormal(lowestYear.value, annualNormal);

    if (highestValueNode) highestValueNode.textContent = `${highestYear.year}`;
    if (highestNoteNode) {
        highestNoteNode.textContent = highestPct
            ? `${formatDecimal(highestYear.value, 2)} score, ${highestPct} relative to the normal of ${formatDecimal(annualNormal, 2)}.`
            : `${formatDecimal(highestYear.value, 2)} score.`;
    }

    if (lowestValueNode) lowestValueNode.textContent = `${lowestYear.year}`;
    if (lowestNoteNode) {
        lowestNoteNode.textContent = lowestPct
            ? `${formatDecimal(lowestYear.value, 2)} score, ${lowestPct} relative to the normal of ${formatDecimal(annualNormal, 2)}.`
            : `${formatDecimal(lowestYear.value, 2)} score.`;
    }
}

async function initializeFilters() {
    const districtSelect = document.getElementById("droughtDistrict");
    const yearSelect = document.getElementById("droughtYear");
    const monthSelect = document.getElementById("droughtMonth");

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

    try {
        const directoryResult = await fetchJSON("/api/v1/district-directory");
        if (directoryResult?.success && Array.isArray(directoryResult.data)) {
            districtProvinceLookup = directoryResult.data.reduce((lookup, row) => {
                const district = typeof row?.district === "string" ? row.district.trim() : "";
                const province = typeof row?.province === "string" ? row.province.trim() : "";
                if (district && province) lookup[district] = province;
                return lookup;
            }, {});
        }
    } catch (error) {
        console.error("Drought district directory load failed:", error);
    }

    availableYears = Array.from(new Set(years)).sort((a, b) => a - b);
    if (yearSelect) {
        yearSelect.innerHTML = '<option value="">Latest complete year</option>';
        availableYears.forEach(year => yearSelect.appendChild(new Option(year, year)));
        currentYear = yearSelect.value || getSelectedYear();
        yearSelect.value = currentYear;
    }

    currentDistrict = districtSelect?.value || "";
    currentMonth = monthSelect?.value || "";
    updateFilterSummary();
}

function setupEventListeners() {
    const districtSelect = document.getElementById("droughtDistrict");
    const yearSelect = document.getElementById("droughtYear");
    const monthSelect = document.getElementById("droughtMonth");
    const applyBtn = document.getElementById("droughtApplyBtn");
    const resetBtn = document.getElementById("droughtResetBtn");

    if (applyBtn) {
        applyBtn.addEventListener("click", () => {
            currentDistrict = districtSelect?.value || "";
            currentYear = yearSelect?.value || getSelectedYear();
            currentMonth = monthSelect?.value || "";
            updateFilterSummary();
            loadDroughtData("updated");
        });
    }

    if (resetBtn) {
        resetBtn.addEventListener("click", () => {
            if (districtSelect) districtSelect.value = "";
            if (monthSelect) monthSelect.value = "";
            currentYear = "";
            if (yearSelect) yearSelect.value = getSelectedYear();
            currentDistrict = "";
            currentYear = yearSelect?.value || getSelectedYear();
            currentMonth = "";
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

    if (monthSelect) {
        monthSelect.addEventListener("change", () => {
            currentMonth = monthSelect.value || "";
            updateFilterSummary();
        });
    }
}

function renderSummaryCards(overview, summary, rankings, durationData = {}) {
    const severePct = getSeverityPercentage(summary, "Severe");
    const moderatePct = getSeverityPercentage(summary, "Moderate");

    document.getElementById("severeDroughtPct").innerHTML = `${formatDecimal(severePct, 1)} <small>%</small>`;
    document.getElementById("moderateDroughtPct").innerHTML = `${formatDecimal(moderatePct, 1)} <small>%</small>`;
    document.getElementById("avgSoilMoisture").innerHTML = `${formatDecimal(overview?.avg_soil_moisture, 1)} <small>%</small>`;

    const mostAffectedProvince = Array.isArray(rankings) && rankings.length ? rankings[0] : null;
    const notes = document.getElementById("droughtNotes");
    if (notes) {
        const droughtDuration = getDurationSentence(durationData, "drought");
        notes.innerHTML = mostAffectedProvince
            ? `This drought view combines ground wetness, drought conditions, place, and time. In ${currentYear}, <strong>${mostAffectedProvince.province}</strong> is the most affected province in this ranking, with an average drought score of <strong>${formatDecimal(mostAffectedProvince.value, 2)}</strong>. ${droughtDuration}`
            : `This drought view combines ground wetness, drought conditions, place, and time. ${droughtDuration}`;
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
                            return `${item.severity}: ${item.count} readings (${formatDecimal(item.percentage, 1)}%)`;
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

function renderInsights(summary, trendData, soilData, rankings, durationData = {}) {
    const container = document.getElementById("droughtInsights");
    if (!container) return;

    const insights = [];
    const dominant = Array.isArray(summary) && summary.length
        ? summary.reduce((best, item) => Number(item.count) > Number(best.count) ? item : best, summary[0])
        : null;
    if (dominant) {
        insights.push(`${dominant.severity} is the most common drought level in this view at ${formatDecimal(dominant.percentage, 1)}% of readings.`);
    }

    const droughtDuration = getDurationSentence(durationData, "drought");
    if (droughtDuration) {
        insights.push(droughtDuration);
    }

    const mostAffectedProvince = Array.isArray(rankings) && rankings.length ? rankings[0] : null;
    if (mostAffectedProvince) {
        insights.push(`${mostAffectedProvince.province} currently ranks as the most drought-affected province in ${currentYear} with an average drought score of ${formatDecimal(mostAffectedProvince.value, 2)}.`);
    }

    const severeSeries = Array.isArray(trendData?.severe_pct) ? trendData.severe_pct : [];
    const trendYears = Array.isArray(trendData?.years) ? trendData.years : [];
    if (severeSeries.length && trendYears.length) {
        const highestSevereIndex = severeSeries.reduce((bestIndex, value, index, array) => Number(value) > Number(array[bestIndex]) ? index : bestIndex, 0);
        insights.push(`Severe drought pressure peaked in ${trendYears[highestSevereIndex]} at ${formatDecimal(severeSeries[highestSevereIndex], 1)}% of readings.`);
    }

    const annualSeries = buildAnnualSeries(trendYears, trendData?.avg_drought_score);
    const annualNormal = computeNormalValue(annualSeries);
    if (annualSeries.length) {
        const highestYear = annualSeries.reduce((best, item) => item.value > best.value ? item : best, annualSeries[0]);
        const lowestYear = annualSeries.reduce((best, item) => item.value < best.value ? item : best, annualSeries[0]);
        const highestPct = formatPercentFromNormal(highestYear.value, annualNormal);
        const lowestPct = formatPercentFromNormal(lowestYear.value, annualNormal);

        insights.push(
            highestPct
                ? `${highestYear.year} recorded the highest average drought score at ${formatDecimal(highestYear.value, 2)}, ${highestPct} relative to the long-run normal of ${formatDecimal(annualNormal, 2)}.`
                : `${highestYear.year} recorded the highest average drought score at ${formatDecimal(highestYear.value, 2)}.`
        );
        insights.push(
            lowestPct
                ? `${lowestYear.year} recorded the lowest average drought score at ${formatDecimal(lowestYear.value, 2)}, ${lowestPct} relative to the long-run normal of ${formatDecimal(annualNormal, 2)}.`
                : `${lowestYear.year} recorded the lowest average drought score at ${formatDecimal(lowestYear.value, 2)}.`
        );
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
    const selectedMonth = currentMonth || "";
    currentYear = selectedYear;
    updateFilterSummary();

    if (currentLoadController) currentLoadController.abort();
    currentLoadController = new AbortController();
    const signal = currentLoadController.signal;
    setLoadingState(true);

    try {
        const [overviewRes, summaryRes, trendRes, soilRes, rankingsRes, durationRes] = await Promise.all([
            fetchJSON(`/api/v1/overview${buildQuery({ district: currentDistrict, year: selectedYear, month: selectedMonth })}`, signal),
            fetchJSON(`/api/v1/drought-summary${buildQuery({ district: currentDistrict, year: selectedYear, month: selectedMonth })}`, signal),
            fetchJSON(`/api/v1/drought-trend${buildQuery({ district: currentDistrict, month: selectedMonth })}`, signal),
            fetchJSON(`/api/v1/soil-moisture-trend${buildQuery({ district: currentDistrict, month: selectedMonth })}`, signal),
            fetchJSON(`/api/v1/rankings/drought${buildQuery({ year: selectedYear, month: selectedMonth })}`, signal),
            fetchJSON(`/api/v1/event-duration${buildQuery({ district: currentDistrict, year: selectedYear, month: selectedMonth })}`, signal)
        ]);

        const overview = overviewRes?.success ? (overviewRes.data || {}) : {};
        const summary = summaryRes?.success ? (summaryRes.data || []) : [];
        const trendData = trendRes?.success ? (trendRes.data || { years: [], avg_drought_score: [], severe_pct: [], moderate_pct: [] }) : { years: [], avg_drought_score: [], severe_pct: [], moderate_pct: [] };
        const soilData = soilRes?.success ? (soilRes.data || { years: [], avg_soil_moisture: [] }) : { years: [], avg_soil_moisture: [] };
        const rankings = rankingsRes?.success ? (rankingsRes.data?.rankings || []) : [];
        const durationData = durationRes?.success ? (durationRes.data || {}) : {};

        renderSummaryCards(overview, summary, rankings, durationData);
        renderSeverityChart(summary);
        renderDroughtTrendChart(trendData);
        renderSoilMoistureChart(soilData);
        renderProvinceChart(rankings);
        updateDroughtYearRecordCards(trendData);
        renderInsights(summary, trendData, soilData, rankings, durationData);

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
        setText("droughtNotes", "Drought information could not be loaded right now. Please try again.");
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
