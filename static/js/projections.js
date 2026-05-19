const projectionCharts = {};

const variableConfig = {
    avg_temp: { label: "Average Temperature", unit: "C", color: "#C62828", icon: "fa-temperature-high" },
    rainfall: { label: "Rainfall", unit: "mm", color: "#1565C0", icon: "fa-cloud-rain" },
    humidity: { label: "Humidity", unit: "%", color: "#0F766E", icon: "fa-droplet" },
    wind_speed: { label: "Wind Speed", unit: "m/s", color: "#6B7280", icon: "fa-wind" }
};

function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function buildAnalysisQuery() {
    const query = new URLSearchParams();
    const province = document.getElementById("projectionProvince")?.value || "";
    const district = document.getElementById("projectionDistrict")?.value || "";
    const year = document.getElementById("projectionYear")?.value || "";
    const month = document.getElementById("projectionMonth")?.value || "";

    if (province) query.set("province", province);
    if (district) query.set("district", district);
    if (year) query.set("year", year);
    if (month) query.set("month", month);
    return query.toString();
}

function formatValue(value, unit = "", decimals = 1) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "--";
    const formatted = number.toLocaleString(undefined, {
        maximumFractionDigits: decimals,
        minimumFractionDigits: decimals === 0 ? 0 : undefined
    });
    return unit ? `${formatted} ${unit}` : formatted;
}

function destroyChart(key) {
    if (projectionCharts[key]) {
        projectionCharts[key].destroy();
        projectionCharts[key] = null;
    }
}

function createChart(key, canvasId, type, data, options = {}) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || typeof Chart === "undefined") return;
    destroyChart(key);
    projectionCharts[key] = new Chart(canvas.getContext("2d"), {
        type,
        data,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: "index", intersect: false },
            plugins: {
                legend: { position: "bottom" },
                tooltip: {
                    callbacks: {
                        label(context) {
                            const label = context.dataset?.label || context.label || "";
                            const value = context.parsed?.y ?? context.parsed;
                            return `${label}: ${Number.isFinite(Number(value)) ? Number(value).toLocaleString() : value}`;
                        }
                    }
                }
            },
            scales: type === "doughnut" ? undefined : {
                y: { beginAtZero: false, grid: { color: "rgba(148, 163, 184, 0.18)" } },
                x: { grid: { display: false } }
            },
            ...options
        }
    });
}

function updateCards(data) {
    const container = document.getElementById("projectionCards");
    if (!container) return;
    const summary = data.summary || {};
    const cards = [
        {
            icon: "fa-temperature-half",
            label: "Average Temperature",
            value: formatValue(summary.avg_temperature, "C"),
            note: summary.hottest_year ? `Hottest year: ${summary.hottest_year.year} at ${formatValue(summary.hottest_year.value, "C")}` : "Historical average in selected records."
        },
        {
            icon: "fa-cloud-rain",
            label: "Total Rainfall",
            value: formatValue(summary.total_rainfall, "mm"),
            note: summary.wettest_year ? `Wettest year: ${summary.wettest_year.year} with ${formatValue(summary.wettest_year.value, "mm")}` : "Total rainfall in selected records."
        },
        {
            icon: "fa-droplet",
            label: "Average Humidity",
            value: formatValue(summary.humidity, "%"),
            note: summary.hottest_month ? `Hottest month: ${summary.hottest_month.month}` : "Moisture level across selected records."
        },
        {
            icon: "fa-wind",
            label: "Average Wind Speed",
            value: formatValue(summary.wind_speed, "m/s"),
            note: `${Number(summary.record_count || 0).toLocaleString()} records used in this view.`
        }
    ];

    container.innerHTML = cards.map((card) => `
        <article class="projection-card">
            <div class="projection-card-icon"><i class="fas ${card.icon}"></i></div>
            <div class="projection-card-label">${escapeHtml(card.label)}</div>
            <div class="projection-card-value">${escapeHtml(card.value)}</div>
            <p class="projection-card-note">${escapeHtml(card.note)}</p>
        </article>
    `).join("");
}

function renderTrendChart(yearly = {}) {
    const labels = yearly.labels || [];
    createChart("trend", "trendChart", "line", {
        labels,
        datasets: [
            { label: "Avg Temp (C)", data: yearly.avg_temp || [], borderColor: variableConfig.avg_temp.color, backgroundColor: "rgba(198,40,40,0.12)", tension: 0.25, yAxisID: "y" },
            { label: "Rainfall (mm)", data: yearly.rainfall || [], borderColor: variableConfig.rainfall.color, backgroundColor: "rgba(21,101,192,0.12)", tension: 0.25, yAxisID: "y1" },
            { label: "Humidity (%)", data: yearly.humidity || [], borderColor: variableConfig.humidity.color, backgroundColor: "rgba(15,118,110,0.12)", tension: 0.25, yAxisID: "y" },
            { label: "Wind (m/s)", data: yearly.wind_speed || [], borderColor: variableConfig.wind_speed.color, backgroundColor: "rgba(107,114,128,0.12)", tension: 0.25, yAxisID: "y" }
        ]
    }, {
        scales: {
            y: { position: "left", beginAtZero: false, grid: { color: "rgba(148, 163, 184, 0.18)" } },
            y1: { position: "right", beginAtZero: true, grid: { drawOnChartArea: false } },
            x: { grid: { display: false } }
        }
    });
}

function renderVariableChart(yearly = {}) {
    const variable = document.getElementById("projectionVariable")?.value || "avg_temp";
    const config = variableConfig[variable] || variableConfig.avg_temp;
    createChart("variable", "variableChart", "line", {
        labels: yearly.labels || [],
        datasets: [{
            label: `${config.label} (${config.unit})`,
            data: yearly[variable] || [],
            borderColor: config.color,
            backgroundColor: `${config.color}22`,
            fill: true,
            tension: 0.28
        }]
    });
}

function renderSeasonalChart(monthly = []) {
    createChart("seasonal", "seasonalChart", "bar", {
        labels: monthly.map((item) => item.month_name),
        datasets: [
            { type: "bar", label: "Rainfall (mm)", data: monthly.map((item) => item.rainfall), backgroundColor: "rgba(21,101,192,0.72)", borderRadius: 6, yAxisID: "y1" },
            { type: "line", label: "Avg Temp (C)", data: monthly.map((item) => item.avg_temp), borderColor: variableConfig.avg_temp.color, backgroundColor: "rgba(198,40,40,0.12)", tension: 0.25, yAxisID: "y" },
            { type: "line", label: "Humidity (%)", data: monthly.map((item) => item.humidity), borderColor: variableConfig.humidity.color, backgroundColor: "rgba(15,118,110,0.12)", tension: 0.25, yAxisID: "y" }
        ]
    }, {
        scales: {
            y: { position: "left", beginAtZero: false, grid: { color: "rgba(148, 163, 184, 0.18)" } },
            y1: { position: "right", beginAtZero: true, grid: { drawOnChartArea: false } },
            x: { grid: { display: false } }
        }
    });
}

function renderDroughtShare(distribution = []) {
    createChart("drought", "droughtShareChart", "doughnut", {
        labels: distribution.map((item) => item.label),
        datasets: [{
            data: distribution.map((item) => item.count),
            backgroundColor: ["#2E7D32", "#80B918", "#B7791F", "#C62828", "#64748B"],
            borderWidth: 2,
            borderColor: "#ffffff"
        }]
    }, {
        cutout: "58%"
    });
}

function updateStationCards(station = {}) {
    const container = document.getElementById("stationCards");
    if (!container) return;
    const cards = [
        { label: "Hottest Station", item: station.hottest_station, unit: "C" },
        { label: "Coldest Station", item: station.coldest_station, unit: "C" },
        { label: "Wettest Station", item: station.wettest_station, unit: "mm" },
        { label: "Driest Station", item: station.driest_station, unit: "mm" }
    ];
    container.innerHTML = cards.map((card) => `
        <article class="projection-station-card">
            <strong>${escapeHtml(card.item?.name || "--")}</strong>
            <span>${escapeHtml(card.label)}${card.item ? `: ${formatValue(card.item.value, card.unit)}` : ""}</span>
        </article>
    `).join("");
}

function renderStationChart(station = {}) {
    createChart("station", "stationChart", "bar", {
        labels: station.labels || [],
        datasets: [
            { label: "Rainfall (mm)", data: station.rainfall || [], backgroundColor: "rgba(21,101,192,0.72)", borderRadius: 6, yAxisID: "y1" },
            { label: "Avg Temp (C)", data: station.avg_temp || [], backgroundColor: "rgba(198,40,40,0.72)", borderRadius: 6, yAxisID: "y" }
        ]
    }, {
        scales: {
            y: { position: "left", beginAtZero: false, grid: { color: "rgba(148, 163, 184, 0.18)" } },
            y1: { position: "right", beginAtZero: true, grid: { drawOnChartArea: false } },
            x: { grid: { display: false } }
        }
    });
}

function changeText(value, unit) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "Not enough yearly data to compare first and latest year.";
    if (Math.abs(number) < 0.05) return `No major change (${formatValue(number, unit)}).`;
    return `${number > 0 ? "Increased" : "Decreased"} by ${formatValue(Math.abs(number), unit)} from first available year to latest available year.`;
}

function updateIndicators(data) {
    const container = document.getElementById("indicatorList");
    if (!container) return;
    const indicators = data.indicators || {};
    const items = [
        { title: "Temperature direction", text: changeText(indicators.temperature_change, "C") },
        { title: "Rainfall direction", text: changeText(indicators.rainfall_change, "mm") },
        { title: "Humidity direction", text: changeText(indicators.humidity_change, "%") },
        { title: "Wind speed direction", text: changeText(indicators.wind_change, "m/s") },
        { title: "Extreme weather signal", text: `${Number(indicators.severe_drought_records || 0).toLocaleString()} severe drought records appear in the selected historical data.` }
    ];

    container.innerHTML = items.map((item) => `
        <div class="projection-insight">
            <strong>${escapeHtml(item.title)}</strong>
            <span>${escapeHtml(item.text)}</span>
        </div>
    `).join("");
}

function updateYearlyTable(rows = []) {
    const body = document.getElementById("yearlyComparisonRows");
    if (!body) return;
    if (!rows.length) {
        body.innerHTML = '<tr><td colspan="5">No yearly comparison data is available for this filter.</td></tr>';
        return;
    }
    body.innerHTML = rows.map((row) => `
        <tr>
            <td>${escapeHtml(row.year)}</td>
            <td>${escapeHtml(formatValue(row.avg_temp, "C"))}</td>
            <td>${escapeHtml(formatValue(row.rainfall, "mm"))}</td>
            <td>${escapeHtml(formatValue(row.humidity, "%"))}</td>
            <td>${escapeHtml(formatValue(row.wind_speed, "m/s"))}</td>
        </tr>
    `).join("");
}

function updateInsights(data) {
    const container = document.getElementById("projectionInsights");
    if (!container) return;
    const insights = data.insights || [];
    const summary = data.summary || {};
    const extra = [];
    if (summary.driest_year) extra.push(`The driest year in this view is ${summary.driest_year.year}, with ${formatValue(summary.driest_year.value, "mm")} rainfall.`);
    if (summary.coldest_month) extra.push(`The coldest month pattern is around ${summary.coldest_month.month}, averaging ${formatValue(summary.coldest_month.value, "C")}.`);
    const allInsights = [...insights, ...extra];

    container.innerHTML = allInsights.length
        ? allInsights.map((text) => `<div class="projection-insight"><strong>Observation</strong><span>${escapeHtml(text)}</span></div>`).join("")
        : '<div class="projection-insight"><strong>No observations</strong><span>No climate observations are available for this filter.</span></div>';
}

async function loadProjectionAnalysis() {
    const status = document.getElementById("projectionStatus");
    if (status) status.innerHTML = '<i class="fas fa-spinner fa-spin"></i><span>Loading historical trends...</span>';

    try {
        const response = await fetch(`/api/v1/climate-analysis?${buildAnalysisQuery()}`);
        const payload = await response.json();
        if (!payload.success) throw new Error(payload.error || "Trend analysis request failed");
        const data = payload.data || {};

        updateCards(data);
        renderTrendChart(data.yearly || {});
        renderVariableChart(data.yearly || {});
        renderSeasonalChart(data.monthly || []);
        renderDroughtShare(data.distribution || []);
        updateStationCards(data.station_analysis || {});
        renderStationChart(data.station_analysis || {});
        updateIndicators(data);
        updateYearlyTable(data.yearly_rows || []);
        updateInsights(data);

        const scope = data.scope || {};
        const place = scope.district || scope.province || "Zambia";
        if (status) status.innerHTML = `<i class="fas fa-check-circle"></i><span>${escapeHtml(place)} historical trend view</span>`;
    } catch (error) {
        console.error("Climate trend analysis failed:", error);
        if (status) status.innerHTML = '<i class="fas fa-triangle-exclamation"></i><span>Trend analysis unavailable</span>';
    }
}

document.addEventListener("DOMContentLoaded", () => {
    ["projectionProvince", "projectionDistrict", "projectionYear", "projectionMonth", "projectionVariable"].forEach((id) => {
        document.getElementById(id)?.addEventListener("change", loadProjectionAnalysis);
    });
    document.getElementById("projectionDistrict")?.addEventListener("input", () => {
        window.clearTimeout(window.projectionDistrictTimer);
        window.projectionDistrictTimer = window.setTimeout(loadProjectionAnalysis, 450);
    });
    loadProjectionAnalysis();
});
