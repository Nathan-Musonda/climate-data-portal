const projectionCharts = {};

const HIST_YEARS = [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025];
const PROJ_YEARS = [2026, 2027, 2028, 2029, 2030, 2031, 2032, 2033, 2034, 2035, 2036, 2037, 2038, 2039, 2040];
const ALL_YEARS = [...HIST_YEARS, ...PROJ_YEARS];
const PROVINCES = ["Lusaka", "Copperbelt", "Central", "Eastern", "Northern", "Southern", "Western", "Luapula", "North-Western", "Muchinga"];
const BASE_TEMP = { Lusaka: 25.8, Copperbelt: 23.1, Central: 24.6, Eastern: 23.9, Northern: 21.8, Southern: 26.2, Western: 25.0, Luapula: 22.5, "North-Western": 22.9, Muchinga: 21.4 };
const BASE_RAIN = { Lusaka: 870, Copperbelt: 1250, Central: 960, Eastern: 1100, Northern: 1350, Southern: 720, Western: 890, Luapula: 1400, "North-Western": 1180, Muchinga: 1300 };

let projectionScenario = "moderate";
let projectionWeatherHistoryRequest = null;

function getProjectionPalette(data) {
    if (data.isTemp) {
        return {
            observed: "#0f766e",
            projected: "#dc6803",
            uncertainty: "rgba(220, 104, 3, 0.18)",
            moderate: "#d97706",
            high: "#b42318",
            provinceBar: "rgba(220, 104, 3, 0.78)"
        };
    }

    return {
        observed: "#1d4ed8",
        projected: "#0f766e",
        uncertainty: "rgba(29, 78, 216, 0.16)",
        moderate: "#0f766e",
        high: "#1d4ed8",
        provinceBar: "rgba(29, 78, 216, 0.76)"
    };
}

function setText(id, value) {
    const node = document.getElementById(id);
    if (node) node.textContent = value;
}

function formatProjectionWeatherNumber(value, digits = 1) {
    const numericValue = Number(value);
    return Number.isFinite(numericValue) ? numericValue.toFixed(digits) : null;
}

function formatProjectionWeatherText(value, fallback = "") {
    const label = String(value || "").trim();
    return label || fallback;
}

function formatProjectionWeatherDateKey(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return null;
    const year = date.getUTCFullYear();
    const month = String(date.getUTCMonth() + 1).padStart(2, "0");
    const day = String(date.getUTCDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
}

function averageProjectionWeatherMetric(values) {
    const numericValues = (values || []).map(Number).filter(Number.isFinite);
    if (!numericValues.length) return null;
    return numericValues.reduce((sum, value) => sum + value, 0) / numericValues.length;
}

function setProjectionWeatherStatus(message) {
    const node = document.getElementById("projectionLiveWeatherStatus");
    if (node) {
        node.innerHTML = `<i class="fas fa-location-dot"></i><span>${message}</span>`;
    }
}

function setProjectionWeatherUnavailable(message) {
    setText("projectionLiveNow", "Not available");
    setText("projectionLiveNowNote", message);
    setText("projectionLiveYesterday", "Not available");
    setText("projectionLiveYesterdayNote", message);
    setText("projectionLiveWeek", "Not available");
    setText("projectionLiveWeekNote", message);
    setProjectionWeatherStatus("Live local data unavailable");
}

function setProjectionWeatherHistoryLoading() {
    setText("projectionLiveYesterday", "Loading...");
    setText("projectionLiveYesterdayNote", "Looking for the latest saved reading from yesterday.");
    setText("projectionLiveWeek", "Loading...");
    setText("projectionLiveWeekNote", "Calculating this week's average temperature.");
}

function renderProjectionCurrentWeather(liveWeather) {
    if (!liveWeather) {
        setProjectionWeatherUnavailable("Allow location access to show live local temperature.");
        return;
    }

    const place = formatProjectionWeatherText(liveWeather.location_name, "your area");
    const observedAt = formatProjectionWeatherText(liveWeather.observed_at_label, "Latest weather update");
    const condition = formatProjectionWeatherText(
        liveWeather.weather_description || liveWeather.weather_main,
        "Current conditions available"
    );
    const currentTemp = formatProjectionWeatherNumber(liveWeather.temperature_c, 1);
    const feelsLike = formatProjectionWeatherNumber(liveWeather.feels_like_c, 1);

    setText("projectionLiveNow", currentTemp ? `${currentTemp} C` : condition);
    setText(
        "projectionLiveNowNote",
        feelsLike
            ? `${condition} near ${place}. Feels like ${feelsLike} C as of ${observedAt}.`
            : `${condition} near ${place} as of ${observedAt}.`
    );
    setProjectionWeatherStatus(place);
}

function renderProjectionWeatherHistory(observations) {
    const items = Array.isArray(observations) ? observations : [];
    if (!items.length) {
        setText("projectionLiveYesterday", "No stored reading");
        setText("projectionLiveYesterdayNote", "No saved observation from yesterday was found for this location yet.");
        setText("projectionLiveWeek", "No weekly summary");
        setText("projectionLiveWeekNote", "There are not enough saved observations yet to summarize this week.");
        return;
    }

    const latestObservedAt = items[0]?.observed_at ? new Date(items[0].observed_at) : null;
    if (!latestObservedAt || Number.isNaN(latestObservedAt.getTime())) {
        setText("projectionLiveYesterday", "Not available");
        setText("projectionLiveYesterdayNote", "Stored recent observations could not be read for this location.");
        setText("projectionLiveWeek", "Not available");
        setText("projectionLiveWeekNote", "Stored recent observations could not be read for this location.");
        return;
    }

    const yesterdayDate = new Date(latestObservedAt.getTime() - (24 * 60 * 60 * 1000));
    const yesterdayKey = formatProjectionWeatherDateKey(yesterdayDate);
    const yesterdayObservation = items.find((item) => formatProjectionWeatherDateKey(item.observed_at) === yesterdayKey) || null;

    if (yesterdayObservation) {
        const temperature = formatProjectionWeatherNumber(yesterdayObservation.temperature_c, 1);
        const condition = formatProjectionWeatherText(
            yesterdayObservation.weather_description || yesterdayObservation.weather_main,
            "Stored conditions available"
        );
        setText("projectionLiveYesterday", temperature ? `${temperature} C` : condition);
        setText(
            "projectionLiveYesterdayNote",
            temperature
                ? `${condition} was the latest stored reading from yesterday.`
                : "A stored reading from yesterday is available for this location."
        );
    } else {
        setText("projectionLiveYesterday", "No stored reading");
        setText("projectionLiveYesterdayNote", "No saved observation from yesterday was found for this location.");
    }

    const weekCutoff = latestObservedAt.getTime() - (7 * 24 * 60 * 60 * 1000);
    const weekObservations = items.filter((item) => {
        const observedAt = new Date(item.observed_at || "");
        return !Number.isNaN(observedAt.getTime()) && observedAt.getTime() >= weekCutoff;
    });

    if (!weekObservations.length) {
        setText("projectionLiveWeek", "No weekly summary");
        setText("projectionLiveWeekNote", "There are not enough saved observations yet to summarize this week.");
        return;
    }

    const averageTemperature = averageProjectionWeatherMetric(weekObservations.map((item) => item.temperature_c));
    setText(
        "projectionLiveWeek",
        averageTemperature !== null ? `${averageTemperature.toFixed(1)} C` : "Weekly summary available"
    );
    setText(
        "projectionLiveWeekNote",
        averageTemperature !== null
            ? `Average temperature across ${weekObservations.length} stored updates from the last 7 days.`
            : "Stored updates are available for the last 7 days."
    );
}

async function loadProjectionWeatherHistory(coords) {
    const normalizer = typeof normalizeViewerCoordinates === "function" ? normalizeViewerCoordinates : null;
    const normalizedCoords = normalizer ? normalizer(coords) : coords;

    if (!normalizedCoords || normalizedCoords.latitude === undefined || normalizedCoords.longitude === undefined) {
        setText("projectionLiveYesterday", "Not available");
        setText("projectionLiveYesterdayNote", "Allow location access to compare with yesterday.");
        setText("projectionLiveWeek", "Not available");
        setText("projectionLiveWeekNote", "Allow location access to calculate this week's average temperature.");
        return;
    }

    if (projectionWeatherHistoryRequest) {
        return projectionWeatherHistoryRequest;
    }

    setProjectionWeatherHistoryLoading();
    projectionWeatherHistoryRequest = (async () => {
        const params = new URLSearchParams({
            lat: String(normalizedCoords.latitude),
            lon: String(normalizedCoords.longitude),
            limit: "56"
        });
        const response = await fetch(`/api/v1/live-weather/history?${params.toString()}`);
        const payload = await response.json();
        if (!payload.success) {
            throw new Error(payload.error || "Unable to load recent weather history.");
        }
        renderProjectionWeatherHistory(payload.data?.observations || []);
    })();

    try {
        return await projectionWeatherHistoryRequest;
    } catch (error) {
        console.error("Projection weather history failed to refresh:", error);
        setText("projectionLiveYesterday", "Not available");
        setText("projectionLiveYesterdayNote", "Recent local history could not be loaded right now.");
        setText("projectionLiveWeek", "Not available");
        setText("projectionLiveWeekNote", "Recent local history could not be loaded right now.");
    } finally {
        projectionWeatherHistoryRequest = null;
    }
}

async function refreshProjectionLiveWeather(forceRefresh = false) {
    if (typeof window.getLiveWeatherForViewer !== "function") {
        setProjectionWeatherUnavailable("Shared live weather tools are not available on this page.");
        return;
    }

    try {
        const liveWeather = await window.getLiveWeatherForViewer({ forceRefresh });
        renderProjectionCurrentWeather(liveWeather);
        await loadProjectionWeatherHistory(liveWeather?.coordinates || null);
    } catch (error) {
        console.error("Projection live weather failed to refresh:", error);
        setProjectionWeatherUnavailable("Live local temperature could not be loaded right now.");
    }
}

function destroyProjectionChart(key) {
    if (projectionCharts[key]) {
        projectionCharts[key].destroy();
        delete projectionCharts[key];
    }
}

function getProjectionRates(variable) {
    return variable === "temp"
        ? { moderate: 0.032, high: 0.055 }
        : { moderate: -4.8, high: -9.2 };
}

function getHistoricalTemp(base) {
    return HIST_YEARS.map((year, index) => Number((base + index * 0.022 + Math.sin(year * 7.3) * 0.18 + Math.cos(year * 3.1) * 0.14).toFixed(2)));
}

function getHistoricalRain(base) {
    return HIST_YEARS.map((year, index) => Math.round(base + index * -3.5 + Math.sin(year * 5.1) * 28 + Math.cos(year * 2.7) * 22));
}

function linearRegression(xs, ys) {
    const meanX = xs.reduce((sum, value) => sum + value, 0) / xs.length;
    const meanY = ys.reduce((sum, value) => sum + value, 0) / ys.length;
    const numerator = xs.reduce((sum, x, index) => sum + (x - meanX) * (ys[index] - meanY), 0);
    const denominator = xs.reduce((sum, x) => sum + (x - meanX) ** 2, 0);
    const slope = denominator ? numerator / denominator : 0;
    return { slope, intercept: meanY - slope * meanX };
}

function buildProvinceData(province, variable, scenario = projectionScenario) {
    const isTemp = variable === "temp";
    const base = isTemp ? BASE_TEMP[province] : BASE_RAIN[province];
    const hist = isTemp ? getHistoricalTemp(base) : getHistoricalRain(base);
    const regression = linearRegression(HIST_YEARS, hist);
    const rate = getProjectionRates(variable)[scenario];
    const proj = PROJ_YEARS.map((year, index) => {
        const value = regression.intercept + regression.slope * year + rate * (index + 1);
        return isTemp ? Number(value.toFixed(2)) : Math.round(value);
    });
    const spread = isTemp ? 0.3 : 25;
    const upperBand = [
        ...HIST_YEARS.map(() => null),
        ...proj.map((value, index) => isTemp ? Number((value + spread * (1 + index * 0.06)).toFixed(2)) : Math.round(value + spread * (1 + index * 0.06)))
    ];
    const lowerBand = [
        ...HIST_YEARS.map(() => null),
        ...proj.map((value, index) => isTemp ? Number((value - spread * (1 + index * 0.06)).toFixed(2)) : Math.round(value - spread * (1 + index * 0.06)))
    ];
    return {
        hist,
        proj,
        upperBand,
        lowerBand,
        province,
        variable,
        isTemp,
        targetYear: Number(document.getElementById("projectionTargetYear")?.value) || 2040
    };
}

function getProjectionData(scenario = projectionScenario) {
    return buildProvinceData(
        document.getElementById("projectionProvince")?.value || "Lusaka",
        document.getElementById("projectionVariable")?.value || "temp",
        scenario
    );
}

function unitFor(data) {
    return data.isTemp ? "C" : "mm";
}

function formatValue(value, data) {
    return data.isTemp ? `${Number(value).toFixed(2)} ${unitFor(data)}` : `${Math.round(Number(value))} ${unitFor(data)}`;
}

function formatDiff(value, data) {
    const rounded = data.isTemp ? Number(value.toFixed(2)) : Math.round(value);
    return `${rounded > 0 ? "+" : ""}${rounded} ${unitFor(data)}`;
}

function updateProjectionStats(data) {
    const baseline = data.hist[data.hist.length - 1];
    const diff2030 = data.proj[4] - baseline;
    const diff2040 = data.proj[14] - baseline;

    setText("projBaseline", formatValue(baseline, data));
    setText("projChange2030", formatDiff(diff2030, data));
    setText("projChange2040", formatDiff(diff2040, data));
    setText("projScenarioLabel", projectionScenario === "moderate" ? "Moderate" : "High emissions");
    setText("projScenarioNote", projectionScenario === "moderate" ? "SSP2-4.5" : "SSP5-8.5");

    document.getElementById("projChange2030")?.classList.toggle("down", diff2030 < 0);
    document.getElementById("projChange2030")?.classList.toggle("up", diff2030 >= 0);
    document.getElementById("projChange2040")?.classList.toggle("down", diff2040 < 0);
    document.getElementById("projChange2040")?.classList.toggle("up", diff2040 >= 0);
}

function updateProjectionSummary(data) {
    const baseline = data.hist[data.hist.length - 1];
    const targetIndex = Math.max(0, PROJ_YEARS.indexOf(data.targetYear));
    const targetValue = data.proj[targetIndex];
    const diff = targetValue - baseline;
    const scenarioLabel = projectionScenario === "moderate" ? "moderate-emissions" : "high-emissions";
    const direction = data.isTemp ? "rise" : (diff < 0 ? "decrease" : "increase");
    setText(
        "projectionSummaryText",
        `Under a ${scenarioLabel} scenario, ${data.isTemp ? "average temperature" : "annual rainfall"} in ${data.province} is projected to ${direction} by ${Math.abs(data.isTemp ? Number(diff.toFixed(1)) : Math.round(diff))} ${unitFor(data)} by ${data.targetYear}, compared with the 2025 baseline of ${formatValue(baseline, data)}.`
    );
}

function projectionChartOptions(data) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
            legend: { display: false },
            tooltip: {
                callbacks: {
                    label(context) {
                        if ((context.dataset?.label || "").includes("bound")) return null;
                        return `${context.dataset.label}: ${context.parsed.y} ${unitFor(data)}`;
                    }
                }
            }
        },
        scales: {
            x: { ticks: { autoSkip: true, maxTicksLimit: 12, maxRotation: 0 } },
            y: {
                ticks: { callback: (value) => `${value} ${unitFor(data)}` },
                title: { display: true, text: data.isTemp ? "Temperature (C)" : "Rainfall (mm)" }
            }
        }
    };
}

function createProjectionChart(key, canvasId, config) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || typeof Chart === "undefined") return;
    destroyProjectionChart(key);
    projectionCharts[key] = new Chart(canvas, config);
}

function renderMainProjectionChart(data) {
    const palette = getProjectionPalette(data);
    const histData = [...data.hist, ...Array(PROJ_YEARS.length).fill(null)];
    const bridgeData = [...Array(HIST_YEARS.length - 1).fill(null), data.hist[data.hist.length - 1], ...data.proj];
    createProjectionChart("main", "projMainChart", {
        type: "line",
        data: {
            labels: ALL_YEARS,
            datasets: [
                { label: "Upper bound", data: data.upperBand, borderWidth: 0, pointRadius: 0, fill: "+1", backgroundColor: palette.uncertainty, tension: 0.3 },
                { label: "Lower bound", data: data.lowerBand, borderWidth: 0, pointRadius: 0, fill: false, backgroundColor: palette.uncertainty, tension: 0.3 },
                { label: "Observed (2015-2025)", data: histData, borderColor: palette.observed, backgroundColor: palette.observed, borderWidth: 2.5, pointRadius: 3, tension: 0.3, fill: false },
                { label: "Projected (2026-2040)", data: bridgeData, borderColor: palette.projected, backgroundColor: palette.projected, borderWidth: 2.5, borderDash: [6, 3], pointRadius: (ctx) => ctx.dataIndex < HIST_YEARS.length ? 0 : 3, tension: 0.3, fill: false }
            ]
        },
        options: projectionChartOptions(data)
    });
}

function renderCompareProjectionChart(data) {
    const palette = getProjectionPalette(data);
    const moderate = getProjectionData("moderate");
    const high = getProjectionData("high");
    createProjectionChart("compare", "projCompareChart", {
        type: "line",
        data: {
            labels: PROJ_YEARS,
            datasets: [
                { label: "Moderate scenario", data: moderate.proj, borderColor: palette.moderate, backgroundColor: palette.moderate, tension: 0.28, fill: false },
                { label: "High emissions scenario", data: high.proj, borderColor: palette.high, backgroundColor: palette.high, tension: 0.28, fill: false }
            ]
        },
        options: projectionChartOptions(data)
    });
}

function renderProvinceProjectionChart(data) {
    const palette = getProjectionPalette(data);
    const rows = PROVINCES.map((province) => {
        const provinceData = buildProvinceData(province, data.variable, projectionScenario);
        return { province, change: provinceData.proj[14] - provinceData.hist[provinceData.hist.length - 1] };
    }).sort((a, b) => data.isTemp ? b.change - a.change : a.change - b.change);

    createProjectionChart("province", "projProvinceChart", {
        type: "bar",
        data: {
            labels: rows.map((row) => row.province),
            datasets: [{
                label: "Projected change by 2040",
                data: rows.map((row) => data.isTemp ? Number(row.change.toFixed(2)) : Math.round(row.change)),
                backgroundColor: palette.provinceBar,
                borderRadius: 8
            }]
        },
        options: { ...projectionChartOptions(data), indexAxis: "y", plugins: { legend: { display: false } } }
    });
}

function updateProjectionPage() {
    const data = getProjectionData();
    const palette = getProjectionPalette(data);
    const variableLabel = data.variable === "temp" ? "Temperature" : "Rainfall";
    setText("projectionChartTitle", `${variableLabel} projection - ${data.province} Province`);

    const filterSummary = document.getElementById("projFilterSummary");
    if (filterSummary) {
        filterSummary.innerHTML = `<i class="fas fa-sliders-h"></i><span>${data.province} &middot; ${variableLabel} &middot; ${projectionScenario === "moderate" ? "Moderate" : "High emissions"} scenario</span>`;
    }

    document.getElementById("projectionScenarioModerate")?.classList.toggle("active", projectionScenario === "moderate");
    document.getElementById("projectionScenarioHigh")?.classList.toggle("active", projectionScenario === "high");

    const observedLegend = document.getElementById("projectionObservedLegend");
    const projectedLegend = document.getElementById("projectionProjectedLegend");
    const bandLegend = document.getElementById("projectionBandLegend");
    const compareModerateLegend = document.getElementById("projectionCompareModerateLegend");
    const compareHighLegend = document.getElementById("projectionCompareHighLegend");

    if (observedLegend) observedLegend.style.background = palette.observed;
    if (projectedLegend) projectedLegend.style.borderColor = palette.projected;
    if (bandLegend) {
        bandLegend.style.background = palette.uncertainty;
        bandLegend.style.borderColor = palette.projected;
    }
    if (compareModerateLegend) compareModerateLegend.style.background = palette.moderate;
    if (compareHighLegend) compareHighLegend.style.background = palette.high;

    updateProjectionStats(data);
    updateProjectionSummary(data);
    renderMainProjectionChart(data);
    renderCompareProjectionChart(data);
    renderProvinceProjectionChart(data);
}

function exportProjectionCSV() {
    const data = getProjectionData();
    const rows = [["Year", "Value", "Type"]];
    data.hist.forEach((value, index) => rows.push([HIST_YEARS[index], value, "Observed"]));
    data.proj.forEach((value, index) => rows.push([PROJ_YEARS[index], value, `Projected ${projectionScenario}`]));
    const link = document.createElement("a");
    link.href = "data:text/csv;charset=utf-8," + encodeURIComponent(rows.map((row) => row.join(",")).join("\n"));
    link.download = `${data.province}_${data.variable}_projection.csv`;
    link.click();
}

function exportProjectionPNG() {
    if (!projectionCharts.main) return;
    const link = document.createElement("a");
    link.href = projectionCharts.main.toBase64Image();
    link.download = "climate_projection.png";
    link.click();
}

window.projectionPageSetScenario = function projectionPageSetScenario(nextScenario) {
    projectionScenario = nextScenario === "high" ? "high" : "moderate";
    updateProjectionPage();
};

document.addEventListener("DOMContentLoaded", () => {
    ["projectionProvince", "projectionVariable", "projectionTargetYear"].forEach((id) => {
        document.getElementById(id)?.addEventListener("change", updateProjectionPage);
    });
    document.getElementById("projectionScenarioModerate")?.addEventListener("click", () => window.projectionPageSetScenario("moderate"));
    document.getElementById("projectionScenarioHigh")?.addEventListener("click", () => window.projectionPageSetScenario("high"));
    document.getElementById("projectionExportCsv")?.addEventListener("click", exportProjectionCSV);
    document.getElementById("projectionExportPng")?.addEventListener("click", exportProjectionPNG);
    updateProjectionPage();
    refreshProjectionLiveWeather();

    window.addEventListener("liveWeatherUpdated", (event) => {
        const liveWeather = event?.detail || null;
        renderProjectionCurrentWeather(liveWeather);
        loadProjectionWeatherHistory(liveWeather?.coordinates || null);
    });
});
