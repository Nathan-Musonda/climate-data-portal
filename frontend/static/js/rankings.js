let districtComparisonChart;
let districtTrendChart;
let comparisonAbortController = null;
let districtDirectory = [];
let latestComparisonPayload = null;
let comparisonIsLoading = false;
const DISTRICT_SELECT_IDS = ["districtA", "districtB", "districtC", "districtD"];
const comparisonNotifier = typeof window.createPageNotifier === "function"
    ? window.createPageNotifier("comparison")
    : null;

const DISTRICT_COMPARE_METRICS = {
    rainfall: { label: "Average Rainfall", unit: "mm", digits: 1 },
    temperature: { label: "Average Max Temperature", unit: "\u00B0C", digits: 1 },
    soil_moisture: { label: "Average Soil Moisture", unit: "%", digits: 1 },
    drought: { label: "Average Drought Score", unit: "score", digits: 2 }
};

const DISTRICT_COMPARE_COLORS = ["#0f766e", "#0ea5e9", "#f97316", "#7c3aed"];

function escapeHTML(value) {
    return String(value ?? "").replace(/[&<>"']/g, character => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
    }[character]));
}

function sendNotification(type, title, message, options = {}) {
    if (typeof window.notifyApp !== "function") return;
    if (comparisonNotifier) {
        comparisonNotifier(type, title, message, {
            id: options.id,
            duration: options.duration,
            sticky: options.sticky,
            meta: options.meta || "Comparison",
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
        meta: options.meta || "Comparison",
        icon: options.icon
    });
}

function getMetricMeta(metricKey) {
    return DISTRICT_COMPARE_METRICS[metricKey] || DISTRICT_COMPARE_METRICS.rainfall;
}

function formatMetricValue(metricKey, value) {
    const meta = getMetricMeta(metricKey);
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return "--";
    if (meta.digits === 0) return Math.round(numeric).toLocaleString();
    return numeric.toFixed(meta.digits);
}

function withUnit(metricKey, value) {
    const formatted = formatMetricValue(metricKey, value);
    const unit = getMetricMeta(metricKey).unit;
    if (formatted === "--") return formatted;
    return unit ? `${formatted} ${unit}` : formatted;
}

function getSelectedDistricts() {
    const districts = DISTRICT_SELECT_IDS
        .map(id => document.getElementById(id)?.value?.trim() || "")
        .filter(Boolean);
    return Array.from(new Set(districts));
}

function getDistrictSelects() {
    return DISTRICT_SELECT_IDS
        .map(id => document.getElementById(id))
        .filter(Boolean);
}

function getProvinceFilter() {
    return document.getElementById("comparisonProvince")?.value || "";
}

function getVisibleDistrictOptions() {
    const province = getProvinceFilter();
    const districts = districtDirectory.length
        ? districtDirectory
            .filter(item => !province || item.province === province)
            .map(item => item.district)
        : Array.from(document.getElementById("districtA")?.options || [])
            .map(option => option.value)
            .filter(Boolean);
    return Array.from(new Set(districts)).sort((a, b) => a.localeCompare(b));
}

function rebuildDistrictSelectOptions() {
    const availableDistricts = getVisibleDistrictOptions();
    getDistrictSelects().forEach((select, index) => {
        const currentValue = select.value;
        const placeholder = index < 2 ? "Select district" : "Optional district";
        select.innerHTML = `<option value="">${placeholder}</option>`;
        availableDistricts.forEach(district => {
            select.appendChild(new Option(district, district));
        });
        if (availableDistricts.includes(currentValue)) {
            select.value = currentValue;
        }
    });
    refreshComparisonControls();
}

async function loadDistrictDirectory() {
    try {
        const result = await fetchJSON("/api/v1/district-directory");
        if (result?.success && Array.isArray(result.data)) {
            districtDirectory = result.data
                .filter(item => item?.district && item?.province)
                .map(item => ({ district: item.district, province: item.province }));
            rebuildDistrictSelectOptions();
        }
    } catch (error) {
        console.warn("District directory could not be loaded:", error);
    }
}

function syncDistrictOptionAvailability() {
    const selectedValues = getSelectedDistricts();
    getDistrictSelects().forEach(select => {
        Array.from(select.options).forEach(option => {
            option.disabled = Boolean(option.value && option.value !== select.value && selectedValues.includes(option.value));
        });
    });
}

function renderSelectionPills() {
    const strip = document.getElementById("districtSelectionStrip");
    if (!strip) return;

    const districts = getSelectedDistricts();
    strip.innerHTML = "";

    if (!districts.length) {
        const empty = document.createElement("span");
        empty.className = "district-selection-empty";
        empty.innerHTML = '<i class="fas fa-circle-info me-1"></i>No districts selected.';
        strip.appendChild(empty);
        return;
    }

    districts.forEach(district => {
        const pill = document.createElement("span");
        pill.className = "district-selection-pill";
        pill.appendChild(document.createTextNode(district));

        const removeButton = document.createElement("button");
        removeButton.type = "button";
        removeButton.className = "district-selection-remove";
        removeButton.setAttribute("aria-label", `Remove ${district}`);
        removeButton.innerHTML = '<i class="fas fa-xmark"></i>';
        removeButton.addEventListener("click", () => {
            getDistrictSelects().forEach(select => {
                if (select.value === district) select.value = "";
            });
            refreshComparisonControls();
            resetComparisonWorkspace(getPendingSelectionMessage());
        });

        pill.appendChild(removeButton);
        strip.appendChild(pill);
    });
}

function highlightFocusMetricColumn() {
    const focusMetric = document.getElementById("focusMetric")?.value || "rainfall";
    document.querySelectorAll(".compare-table [data-metric]").forEach(cell => {
        cell.classList.toggle("is-focus", cell.dataset.metric === focusMetric);
    });
    document.querySelectorAll("#comparisonTableBody [data-metric]").forEach(cell => {
        cell.classList.toggle("is-focus", cell.dataset.metric === focusMetric);
    });
}

function refreshComparisonControls() {
    syncDistrictOptionAvailability();
    renderSelectionPills();
    setSelectionSummary();
    setLoadingState(comparisonIsLoading);
    highlightFocusMetricColumn();
}

function getPendingSelectionMessage() {
    return getSelectedDistricts().length >= 2
        ? "Apply the current selection to load charts, table, and insights."
        : "Select at least two districts to compare variables side by side.";
}

function buildComparisonStatusNotification(payload, reason = "updated") {
    const focusMetric = payload?.focus_metric || "rainfall";
    const rows = Array.isArray(payload?.table) ? payload.table : [];
    const validRows = rows.filter(row => Number.isFinite(Number(row?.metrics?.[focusMetric])));
    const districtsLabel = `${getSelectedDistricts().length} districts`;
    const intro = reason === "reset"
        ? `Selection reset for ${districtsLabel} in ${payload?.year || "--"}.`
        : `Comparison refreshed for ${districtsLabel} in ${payload?.year || "--"}.`;

    if (!validRows.length) {
        return {
            type: "info",
            title: "Comparison data limited",
            message: `${intro} No ${getMetricMeta(focusMetric).label.toLowerCase()} values were returned for the current selection.`,
            meta: "Comparison"
        };
    }

    const leader = validRows.reduce((best, row) => Number(row.metrics[focusMetric]) > Number(best.metrics[focusMetric]) ? row : best, validRows[0]);
    return {
        type: "info",
        title: reason === "reset" ? "Comparison filters reset" : "Comparison updated",
        message: `${intro} ${leader.district} leads ${getMetricMeta(focusMetric).label.toLowerCase()} at ${withUnit(focusMetric, leader.metrics[focusMetric])}.`,
        meta: "Comparison"
    };
}

function setSelectionSummary() {
    const year = document.getElementById("comparisonYear")?.value || "--";
    const focusMetric = document.getElementById("focusMetric")?.value || "rainfall";
    const districts = getSelectedDistricts();
    const province = getProvinceFilter();
    const summary = document.getElementById("comparisonSelectionSummary");
    const actionsNote = document.getElementById("comparisonActionsNote");
    if (!summary) return;
    const districtLabel = districts.length === 1 ? "1 district" : `${districts.length} districts`;
    summary.innerHTML = `<i class="fas fa-sliders-h"></i><span>${province || "All Provinces"} | ${districtLabel} | ${getMetricMeta(focusMetric).label} | ${year}</span>`;
    if (actionsNote) {
        actionsNote.textContent = districts.length >= 2
            ? `Ready to compare ${districtLabel.toLowerCase()} for ${getMetricMeta(focusMetric).label.toLowerCase()} in ${year}.`
            : `Select 2 to 4 districts to compare ${getMetricMeta(focusMetric).label.toLowerCase()} side by side.`;
    }
}

function setLoadingState(isLoading) {
    comparisonIsLoading = isLoading;
    const applyBtn = document.getElementById("comparisonApplyBtn");
    const resetBtn = document.getElementById("comparisonResetBtn");
    const clearBtn = document.getElementById("comparisonClearDistrictsBtn");
    const exportBtn = document.getElementById("comparisonExportBtn");
    const selectedCount = getSelectedDistricts().length;

    if (applyBtn) {
        applyBtn.disabled = isLoading || selectedCount < 2;
        applyBtn.innerHTML = isLoading
            ? '<i class="fas fa-spinner fa-spin me-2"></i>Loading'
            : '<i class="fas fa-filter me-2"></i>Apply';
    }
    if (resetBtn) resetBtn.disabled = isLoading;
    if (clearBtn) clearBtn.disabled = isLoading || selectedCount === 0;
    if (exportBtn) exportBtn.disabled = isLoading || !latestComparisonPayload;
}

function setChartEmptyState(elementId, message, isVisible) {
    const element = document.getElementById(elementId);
    if (!element) return;
    element.textContent = message;
    element.classList.toggle("is-hidden", !isVisible);
}

function destroyCanvasChart(canvasId, localChart) {
    const canvas = document.getElementById(canvasId);
    const registeredChart = window.Chart && typeof Chart.getChart === "function"
        ? Chart.getChart(canvas || canvasId)
        : null;

    if (registeredChart && registeredChart !== localChart) {
        registeredChart.destroy();
    }
    if (localChart) {
        localChart.destroy();
    }
}

function resetComparisonWorkspace(message, options = {}) {
    if (options.clearPayload !== false) {
        latestComparisonPayload = null;
    }
    renderComparisonEmptyState(message);
    refreshComparisonControls();
}

function renderComparisonEmptyState(message) {
    destroyCanvasChart("districtComparisonChart", districtComparisonChart);
    districtComparisonChart = null;
    destroyCanvasChart("districtTrendChart", districtTrendChart);
    districtTrendChart = null;

    setChartEmptyState("districtComparisonEmpty", message, true);
    setChartEmptyState("districtTrendEmpty", message, true);

    const comparisonTableBody = document.getElementById("comparisonTableBody");
    if (comparisonTableBody) {
        comparisonTableBody.innerHTML = `<tr><td colspan="6" class="empty-state">${escapeHTML(message)}</td></tr>`;
    }

    const comparisonInsights = document.getElementById("comparisonInsights");
    if (comparisonInsights) {
        comparisonInsights.innerHTML = `
            <div class="insight-item">
                <p>${escapeHTML(message)}</p>
            </div>
        `;
    }

    document.getElementById("leadingDistrictValue").textContent = "--";
    document.getElementById("leadingDistrictNote").textContent = message;
    document.getElementById("comparisonGapValue").textContent = "--";
    document.getElementById("comparisonGapNote").textContent = message;
    document.getElementById("comparisonYearsValue").textContent = "--";
    document.getElementById("comparisonYearsNote").textContent = message;

    document.getElementById("comparisonChartTitle").textContent = "Selected Year District Comparison";
    document.getElementById("comparisonChartSubtitle").textContent = message;
    document.getElementById("trendChartTitle").textContent = "Focus Metric Trend Over Time";
    document.getElementById("trendChartSubtitle").textContent = message;
    highlightFocusMetricColumn();
}

async function fetchJSON(url, signal) {
    const response = await fetch(url, signal ? { signal } : undefined);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(payload?.error || "The comparison request could not be completed.");
    }
    return payload;
}

async function initializeComparisonFilters() {
    await loadDistrictDirectory();
    resetComparisonWorkspace(getPendingSelectionMessage());

    ["comparisonYear", "focusMetric", "districtA", "districtB", "districtC", "districtD"].forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.addEventListener("change", () => {
                refreshComparisonControls();
                resetComparisonWorkspace(getPendingSelectionMessage());
            });
        }
    });

    const provinceSelect = document.getElementById("comparisonProvince");
    if (provinceSelect) {
        provinceSelect.addEventListener("change", () => {
            rebuildDistrictSelectOptions();
            getDistrictSelects().forEach(select => { select.value = ""; });
            resetComparisonWorkspace(getPendingSelectionMessage());
        });
    }

    const applyBtn = document.getElementById("comparisonApplyBtn");
    if (applyBtn) {
        applyBtn.addEventListener("click", () => {
            loadDistrictComparison("updated");
        });
    }

    const resetBtn = document.getElementById("comparisonResetBtn");
    if (resetBtn) {
        resetBtn.addEventListener("click", () => {
            const yearSelect = document.getElementById("comparisonYear");
            const focusMetric = document.getElementById("focusMetric");
            const provinceSelect = document.getElementById("comparisonProvince");
            if (yearSelect && yearSelect.options.length) yearSelect.selectedIndex = yearSelect.options.length - 1;
            if (focusMetric) focusMetric.value = "rainfall";
            if (provinceSelect) provinceSelect.value = "";
            rebuildDistrictSelectOptions();
            DISTRICT_SELECT_IDS.forEach(id => {
                const element = document.getElementById(id);
                if (element) element.value = "";
            });
            resetComparisonWorkspace(getPendingSelectionMessage());
            sendNotification("info", "Comparison reset", "The comparison workspace is ready for a fresh district selection.", {
                id: "comparison-reset",
                duration: 3000
            });
        });
    }

    const clearBtn = document.getElementById("comparisonClearDistrictsBtn");
    if (clearBtn) {
        clearBtn.addEventListener("click", () => {
            getDistrictSelects().forEach(select => { select.value = ""; });
            resetComparisonWorkspace(getPendingSelectionMessage());
        });
    }

    const exportBtn = document.getElementById("comparisonExportBtn");
    if (exportBtn) {
        exportBtn.addEventListener("click", exportComparisonCsv);
    }
}

function updateSummaryCards(payload) {
    const focusMetric = payload?.focus_metric || "rainfall";
    const rows = Array.isArray(payload?.table) ? payload.table : [];
    const validRows = rows.filter(row => Number.isFinite(Number(row?.metrics?.[focusMetric])));
    const years = Array.isArray(payload?.trend?.years) ? payload.trend.years : [];

    if (!validRows.length) {
        document.getElementById("leadingDistrictValue").textContent = "--";
        document.getElementById("leadingDistrictNote").textContent = "No focus metric values are available for the selected districts.";
        document.getElementById("comparisonGapValue").textContent = "--";
        document.getElementById("comparisonGapNote").textContent = "No gap could be calculated from the current selection.";
    } else {
        const leader = validRows.reduce((best, row) => Number(row.metrics[focusMetric]) > Number(best.metrics[focusMetric]) ? row : best, validRows[0]);
        const trailer = validRows.reduce((best, row) => Number(row.metrics[focusMetric]) < Number(best.metrics[focusMetric]) ? row : best, validRows[0]);
        const gap = Number(leader.metrics[focusMetric]) - Number(trailer.metrics[focusMetric]);
        document.getElementById("leadingDistrictValue").textContent = leader.district;
        document.getElementById("leadingDistrictNote").textContent = `${withUnit(focusMetric, leader.metrics[focusMetric])} in ${payload.year}.`;
        document.getElementById("comparisonGapValue").textContent = withUnit(focusMetric, gap);
        document.getElementById("comparisonGapNote").textContent = `${leader.district} versus ${trailer.district} for the active focus metric.`;
    }

    document.getElementById("comparisonYearsValue").textContent = years.length ? `${years.length} years` : "--";
    document.getElementById("comparisonYearsNote").textContent = years.length
        ? `${years[0]} to ${years[years.length - 1]} trend coverage for the selected districts.`
        : "Trend years are not available for the current selection.";
}

function renderComparisonChart(payload) {
    const canvas = document.getElementById("districtComparisonChart");
    const ctx = canvas.getContext("2d");
    destroyCanvasChart("districtComparisonChart", districtComparisonChart);
    districtComparisonChart = null;

    const focusMetric = payload?.focus_metric || "rainfall";
    const comparison = payload?.comparison || { labels: [], values: [] };
    const labels = comparison.labels || [];
    const values = comparison.values || [];

    if (!labels.length || !values.some(value => Number.isFinite(Number(value)))) {
        setChartEmptyState("districtComparisonEmpty", "No chart values are available for the current selection.", true);
        document.getElementById("comparisonChartTitle").textContent = `${getMetricMeta(focusMetric).label} Across Selected Districts`;
        document.getElementById("comparisonChartSubtitle").textContent = "No selected-year values were returned.";
        return;
    }

    setChartEmptyState("districtComparisonEmpty", "", false);

    districtComparisonChart = new Chart(ctx, {
        type: "bar",
        data: {
            labels,
            datasets: [{
                label: `${getMetricMeta(focusMetric).label} (${getMetricMeta(focusMetric).unit || "value"})`,
                data: values,
                backgroundColor: DISTRICT_COMPARE_COLORS.slice(0, labels.length),
                borderRadius: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label(context) {
                            return withUnit(focusMetric, context.raw);
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { color: "#475569" }
                },
                y: {
                    beginAtZero: true,
                    grid: { color: "rgba(148, 163, 184, 0.16)" },
                    ticks: { color: "#475569" },
                    title: {
                        display: true,
                        text: getMetricMeta(focusMetric).unit ? `${getMetricMeta(focusMetric).label} (${getMetricMeta(focusMetric).unit})` : getMetricMeta(focusMetric).label,
                        color: "#475569"
                    }
                }
            }
        }
    });

    document.getElementById("comparisonChartTitle").textContent = `${getMetricMeta(focusMetric).label} Across Selected Districts`;
    document.getElementById("comparisonChartSubtitle").textContent = `Selected year comparison for ${payload.year}.`;
}

function renderTrendChart(payload) {
    const canvas = document.getElementById("districtTrendChart");
    const ctx = canvas.getContext("2d");
    destroyCanvasChart("districtTrendChart", districtTrendChart);
    districtTrendChart = null;

    const focusMetric = payload?.focus_metric || "rainfall";
    const trend = payload?.trend || { years: [], series: [] };
    const hasTrendValues = (trend.series || []).some(series =>
        (series.values || []).some(value => Number.isFinite(Number(value)))
    );

    if (!(trend.years || []).length || !(trend.series || []).length || !hasTrendValues) {
        setChartEmptyState("districtTrendEmpty", "No trend values are available for the current selection.", true);
        document.getElementById("trendChartTitle").textContent = `${getMetricMeta(focusMetric).label} Trend`;
        document.getElementById("trendChartSubtitle").textContent = "Trend values were not returned for the selected districts.";
        return;
    }

    setChartEmptyState("districtTrendEmpty", "", false);

    districtTrendChart = new Chart(ctx, {
        type: "line",
        data: {
            labels: trend.years || [],
            datasets: (trend.series || []).map((series, index) => ({
                label: series.district,
                data: series.values || [],
                borderColor: DISTRICT_COMPARE_COLORS[index % DISTRICT_COMPARE_COLORS.length],
                backgroundColor: DISTRICT_COMPARE_COLORS[index % DISTRICT_COMPARE_COLORS.length],
                tension: 0.25,
                pointRadius: 3,
                fill: false
            }))
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: { color: "#334155" }
                },
                tooltip: {
                    callbacks: {
                        label(context) {
                            return `${context.dataset.label}: ${withUnit(focusMetric, context.raw)}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { color: "#475569" }
                },
                y: {
                    beginAtZero: false,
                    grid: { color: "rgba(148, 163, 184, 0.16)" },
                    ticks: { color: "#475569" },
                    title: {
                        display: true,
                        text: getMetricMeta(focusMetric).unit ? `${getMetricMeta(focusMetric).label} (${getMetricMeta(focusMetric).unit})` : getMetricMeta(focusMetric).label,
                        color: "#475569"
                    }
                }
            }
        }
    });

    document.getElementById("trendChartTitle").textContent = `${getMetricMeta(focusMetric).label} Trend`;
    document.getElementById("trendChartSubtitle").textContent = "Year-by-year change for each selected district.";
}

function renderComparisonTable(payload) {
    const tbody = document.getElementById("comparisonTableBody");
    if (!tbody) return;

    const rows = Array.isArray(payload?.table) ? payload.table : [];
    if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No district comparison values are available for the current selection.</td></tr>';
        highlightFocusMetricColumn();
        return;
    }

    tbody.innerHTML = rows.map(row => `
        <tr>
            <td><span class="district-chip">${escapeHTML(row.district)}</span></td>
            <td>${escapeHTML(row.province || "--")}</td>
            <td data-metric="rainfall">${escapeHTML(withUnit("rainfall", row.metrics?.rainfall))}</td>
            <td data-metric="temperature">${escapeHTML(withUnit("temperature", row.metrics?.temperature))}</td>
            <td data-metric="soil_moisture">${escapeHTML(withUnit("soil_moisture", row.metrics?.soil_moisture))}</td>
            <td data-metric="drought">${escapeHTML(withUnit("drought", row.metrics?.drought))}</td>
        </tr>
    `).join("");
    highlightFocusMetricColumn();
}

function renderInsights(payload) {
    const container = document.getElementById("comparisonInsights");
    if (!container) return;

    const insights = Array.isArray(payload?.insights) ? payload.insights : [];
    if (!insights.length) {
        container.innerHTML = `
            <div class="insight-item">
                <p>No comparison insights are available yet for the current selection.</p>
            </div>
        `;
        return;
    }

    container.innerHTML = insights.map(item => `
        <div class="insight-item">
            <p>${escapeHTML(item)}</p>
        </div>
    `).join("");
}

function escapeCsvValue(value) {
    const text = value === null || value === undefined ? "" : String(value);
    return `"${text.replace(/"/g, '""')}"`;
}

function exportComparisonCsv() {
    const payload = latestComparisonPayload;
    const rows = Array.isArray(payload?.table) ? payload.table : [];
    if (!payload || !rows.length) {
        sendNotification("info", "No comparison to export", "Load a district comparison before exporting CSV.", {
            id: "comparison-export-empty",
            duration: 3600
        });
        return;
    }

    const headers = [
        "Year",
        "District",
        "Province",
        "Rainfall_mm",
        "Temp_Max_C",
        "SoilMoisture_pct",
        "DroughtScore"
    ];
    const csvRows = [
        headers.map(escapeCsvValue).join(","),
        ...rows.map(row => [
            payload.year,
            row.district,
            row.province || "",
            row.metrics?.rainfall ?? "",
            row.metrics?.temperature ?? "",
            row.metrics?.soil_moisture ?? "",
            row.metrics?.drought ?? ""
        ].map(escapeCsvValue).join(","))
    ];

    const blob = new Blob([csvRows.join("\n")], { type: "text/csv;charset=utf-8;" });
    const link = document.createElement("a");
    const districts = getSelectedDistricts().join("-") || "districts";
    link.href = URL.createObjectURL(blob);
    link.download = `district-comparison-${payload.year}-${districts}`.toLowerCase().replace(/[^a-z0-9]+/g, "-") + ".csv";
    document.body.appendChild(link);
    link.click();
    URL.revokeObjectURL(link.href);
    link.remove();

    sendNotification("success", "Comparison exported", "The district comparison table was downloaded as CSV.", {
        id: "comparison-export-success",
        duration: 3200
    });
}

async function loadDistrictComparison(reason = "updated") {
    const selectedDistricts = getSelectedDistricts();
    refreshComparisonControls();
    if (selectedDistricts.length < 2) {
        resetComparisonWorkspace("Select at least two districts to compare variables side by side.");
        if (reason !== "initial") {
            sendNotification("info", "More districts needed", "Select at least two districts to compare variables side by side.", {
                id: "comparison-too-few-districts",
                duration: 4200
            });
        }
        return;
    }

    const year = document.getElementById("comparisonYear")?.value || "";
    const focusMetric = document.getElementById("focusMetric")?.value || "rainfall";
    refreshComparisonControls();

    if (comparisonAbortController) comparisonAbortController.abort();
    comparisonAbortController = new AbortController();
    const signal = comparisonAbortController.signal;
    setLoadingState(true);

    const query = new URLSearchParams({
        year,
        focus_metric: focusMetric,
        districts: selectedDistricts.join(",")
    });

    try {
        const result = await fetchJSON(`/api/v1/district-comparison?${query.toString()}`, signal);
        const payload = result?.success ? result.data : null;
        if (!payload) throw new Error(result?.error || "District comparison could not be loaded.");
        latestComparisonPayload = payload;

        updateSummaryCards(payload);
        renderComparisonChart(payload);
        renderTrendChart(payload);
        renderComparisonTable(payload);
        renderInsights(payload);
        refreshComparisonControls();

        const notification = buildComparisonStatusNotification(payload, reason);
        if (reason !== "initial" || notification.title === "Comparison data limited") {
            sendNotification(notification.type, notification.title, notification.message, {
                id: notification.title === "Comparison data limited" ? "comparison-empty" : "comparison-status",
                duration: 4200,
                meta: notification.meta
            });
        }
    } catch (error) {
        if (error?.name === "AbortError") return;
        latestComparisonPayload = null;
        resetComparisonWorkspace(error?.message || "District comparison could not be loaded right now.");
        sendNotification("danger", "District comparison unavailable", error?.message || "District comparison could not be loaded right now.", {
            id: "comparison-load-error",
            duration: 6500
        });
    } finally {
        if (comparisonAbortController?.signal === signal) comparisonAbortController = null;
        setLoadingState(false);
    }
}

document.addEventListener("DOMContentLoaded", () => {
    initializeComparisonFilters().then(() => {
        refreshComparisonControls();
    });
});
