const impactCharts = {};

function sendNotification(type, title, message, options = {}) {
    if (typeof window.notifyApp !== "function") return;
    window.notifyApp({
        type,
        title,
        message,
        id: options.id,
        duration: options.duration
    });
}

function toFiniteNumber(value) {
    if (value === null || value === undefined || value === "") return null;
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : null;
}

function formatNumber(value) {
    const numeric = toFiniteNumber(value);
    if (numeric === null) return "--";
    return new Intl.NumberFormat().format(Math.round(numeric));
}

function formatDecimal(value, decimals = 1) {
    const numeric = toFiniteNumber(value);
    if (numeric === null) return "--";
    return numeric.toFixed(decimals);
}

function setText(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = value;
}

async function fetchJSON(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Request failed: ${response.status}`);
    const payload = await response.json();
    return payload?.data || payload || {};
}

function destroyChart(id) {
    if (impactCharts[id]) {
        impactCharts[id].destroy();
        delete impactCharts[id];
    }
}

function normalize(values) {
    const finite = (values || []).map(toFiniteNumber).filter((value) => value !== null);
    if (!finite.length) return (values || []).map(() => 0);
    const min = Math.min(...finite);
    const max = Math.max(...finite);
    if (max === min) return (values || []).map((value) => toFiniteNumber(value) === null ? 0 : 0.5);
    return (values || []).map((value) => {
        const numeric = toFiniteNumber(value);
        return numeric === null ? 0 : (numeric - min) / (max - min);
    });
}

function getSeriesPointMap(labels, values) {
    const map = new Map();
    (labels || []).forEach((label, index) => {
        const numeric = toFiniteNumber((values || [])[index]);
        if (numeric !== null) map.set(String(label), numeric);
    });
    return map;
}

function getLatestYear(years) {
    const numericYears = (years || []).map(Number).filter(Number.isFinite);
    return numericYears.length ? Math.max(...numericYears) : new Date().getFullYear();
}

function chartDefaults(yTitle = "") {
    return {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                labels: { color: "#334155" }
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
                    display: Boolean(yTitle),
                    text: yTitle,
                    color: "#475569"
                }
            }
        }
    };
}

function renderBarChart(id, labels, values, label, color, yTitle = "") {
    const canvas = document.getElementById(id);
    if (!canvas) return;
    destroyChart(id);
    impactCharts[id] = new Chart(canvas, {
        type: "bar",
        data: {
            labels,
            datasets: [{
                label,
                data: values,
                backgroundColor: color,
                borderRadius: 8
            }]
        },
        options: chartDefaults(yTitle)
    });
}

function renderLineChart(id, labels, datasets, yTitle = "") {
    const canvas = document.getElementById(id);
    if (!canvas) return;
    destroyChart(id);
    impactCharts[id] = new Chart(canvas, {
        type: "line",
        data: { labels, datasets },
        options: {
            ...chartDefaults(yTitle),
            interaction: { mode: "index", intersect: false }
        }
    });
}

function renderComboBarLineChart(id, labels, barDataset, lineDataset, yTitle = "") {
    const canvas = document.getElementById(id);
    if (!canvas) return;
    destroyChart(id);
    impactCharts[id] = new Chart(canvas, {
        data: {
            labels,
            datasets: [
                { type: "bar", ...barDataset, borderRadius: 8 },
                { type: "line", ...lineDataset, tension: 0.25, pointRadius: 3, borderWidth: 3 }
            ]
        },
        options: chartDefaults(yTitle)
    });
}

function buildCombinedStress(years, rainfallMap, tempMap, droughtMap, floodMap) {
    const rainfallValues = years.map((year) => rainfallMap.get(String(year)));
    const tempValues = years.map((year) => tempMap.get(String(year)));
    const droughtValues = years.map((year) => droughtMap.get(String(year)));
    const floodValues = years.map((year) => floodMap.get(String(year)));

    const rainfallStress = normalize(rainfallValues).map((value) => 1 - value);
    const tempStress = normalize(tempValues);
    const droughtStress = normalize(droughtValues);
    const floodStress = normalize(floodValues);

    return years.map((year, index) => ({
        year,
        score: Number(((rainfallStress[index] + tempStress[index] + droughtStress[index] + floodStress[index]) * 25).toFixed(1)),
        rainfall: rainfallValues[index],
        temperature: tempValues[index],
        drought: droughtValues[index],
        floods: floodValues[index] || 0
    }));
}

function buildProvinceRisk(rainfallRankings, tempRankings, droughtRankings, floodHotspots) {
    const provinces = new Set();
    [rainfallRankings, tempRankings, droughtRankings].forEach((items) => {
        (items || []).forEach((item) => provinces.add(item.province));
    });
    (floodHotspots || []).forEach((item) => provinces.add(item.province));

    const rainfallMap = new Map((rainfallRankings || []).map((item) => [item.province, item.value]));
    const tempMap = new Map((tempRankings || []).map((item) => [item.province, item.value]));
    const droughtMap = new Map((droughtRankings || []).map((item) => [item.province, item.value]));
    const floodMap = new Map((floodHotspots || []).map((item) => [item.province, item.flood_events]));

    const provinceList = Array.from(provinces);
    const rainfallValues = provinceList.map((province) => rainfallMap.get(province));
    const tempValues = provinceList.map((province) => tempMap.get(province));
    const droughtValues = provinceList.map((province) => droughtMap.get(province));
    const floodValues = provinceList.map((province) => floodMap.get(province) || 0);

    const rainfallDeficit = normalize(rainfallValues).map((value) => 1 - value);
    const tempStress = normalize(tempValues);
    const droughtStress = normalize(droughtValues);
    const floodStress = normalize(floodValues);

    return provinceList
        .map((province, index) => ({
            province,
            score: Number(((rainfallDeficit[index] + tempStress[index] + droughtStress[index] + floodStress[index]) * 25).toFixed(1))
        }))
        .sort((a, b) => b.score - a.score)
        .slice(0, 10);
}

function renderInsights({ stressRows, provinceRisk, totalFloods, severeDroughtYears, peakRainFloodYear, peakDroughtYear }) {
    const container = document.getElementById("impactInsights");
    if (!container) return;

    const worstYear = stressRows.length ? stressRows.reduce((best, item) => item.score > best.score ? item : best, stressRows[0]) : null;
    const topProvince = provinceRisk[0];
    const items = [];

    if (worstYear) {
        items.push(`The most stressful combined year is <strong>${worstYear.year}</strong>, with a climate stress score of <strong>${formatDecimal(worstYear.score, 1)}</strong>.`);
    }
    if (topProvince) {
        items.push(`<strong>${topProvince.province}</strong> ranks highest for combined provincial climate risk in the latest year view.`);
    }
    if (totalFloods !== null) {
        items.push(`The flood signal counts <strong>${formatNumber(totalFloods)}</strong> flood-risk rainfall records across the available annual series.`);
    }
    if (severeDroughtYears !== null) {
        items.push(`<strong>${formatNumber(severeDroughtYears)}</strong> years show severe drought records in the national drought trend.`);
    }
    if (peakRainFloodYear) {
        items.push(`Rainfall and flood pressure are strongest together around <strong>${peakRainFloodYear}</strong>, where high rainfall aligns with elevated flood-risk records.`);
    }
    if (peakDroughtYear) {
        items.push(`The strongest drought-pressure year in the trend is <strong>${peakDroughtYear}</strong>, showing when low rainfall and drought severity most clearly overlap.`);
    }

    container.innerHTML = items.length
        ? items.map((item) => `<div class="insight-item"><p>${item}</p></div>`).join("")
        : '<div class="insight-item"><p>Not enough data is available to generate impact findings yet.</p></div>';
}

function setErrorState(message) {
    ["worstClimateYear", "mostAtRiskProvince", "totalFloodEvents", "severeDroughtYears"].forEach((id) => setText(id, "--"));
    ["combinedStressChart", "provinceRiskChart", "floodRainfallChart", "droughtRainfallChart", "seasonalVulnerabilityChart"].forEach(destroyChart);
    const container = document.getElementById("impactInsights");
    if (container) container.innerHTML = `<div class="insight-item"><p class="text-danger mb-0">${message}</p></div>`;
}

async function loadImpactPage() {
    try {
        const yearsPayload = await fetchJSON("/api/v1/years");
        const years = Array.isArray(yearsPayload) ? yearsPayload.map(String) : [];
        const latestYear = getLatestYear(years);

        const [rainfall, temperature, drought, allFloods, latestFloods, rainfallRanking, tempRanking, droughtRanking] = await Promise.all([
            fetchJSON("/api/v1/rainfall-trend"),
            fetchJSON("/api/v1/temperature-trend"),
            fetchJSON("/api/v1/drought-trend"),
            fetchJSON("/api/v1/flood-events"),
            fetchJSON(`/api/v1/flood-events?year=${latestYear}`),
            fetchJSON(`/api/v1/rankings/rainfall?year=${latestYear}`),
            fetchJSON(`/api/v1/rankings/temperature?year=${latestYear}`),
            fetchJSON(`/api/v1/rankings/drought?year=${latestYear}`)
        ]);

        const annualFloodResponses = await Promise.all(
            years.map((year) => fetchJSON(`/api/v1/flood-events?year=${year}`).catch(() => ({ summary: { flood_event_count: 0 } })))
        );

        const rainfallLabels = rainfall.labels || rainfall.years || [];
        const tempLabels = temperature.labels || temperature.years || [];
        const droughtLabels = drought.labels || drought.years || [];
        const allYears = Array.from(new Set([...rainfallLabels, ...tempLabels, ...droughtLabels, ...years].map(String))).sort();

        const rainfallMap = getSeriesPointMap(rainfallLabels, rainfall.avg_rainfall || rainfall.average_rainfall || []);
        const tempMap = getSeriesPointMap(tempLabels, temperature.avg_max_temp || temperature.avg_temperature || []);
        const droughtMap = getSeriesPointMap(droughtLabels, drought.avg_drought_score || []);
        const severeMap = getSeriesPointMap(droughtLabels, drought.severe_pct || []);
        const floodMap = new Map();
        annualFloodResponses.forEach((payload, index) => {
            floodMap.set(String(years[index]), toFiniteNumber(payload?.summary?.flood_event_count) || 0);
        });

        const stressRows = buildCombinedStress(allYears, rainfallMap, tempMap, droughtMap, floodMap);
        const totalFloods = Array.from(floodMap.values()).reduce((sum, value) => sum + (toFiniteNumber(value) || 0), 0);
        const severeDroughtYears = Array.from(severeMap.values()).filter((value) => (toFiniteNumber(value) || 0) > 0).length;
        const provinceRisk = buildProvinceRisk(
            rainfallRanking?.rankings || [],
            tempRanking?.rankings || [],
            droughtRanking?.rankings || [],
            latestFloods?.hotspots || []
        );

        const worstYear = stressRows.length ? stressRows.reduce((best, item) => item.score > best.score ? item : best, stressRows[0]) : null;
        const mostAtRisk = provinceRisk[0];

        setText("worstClimateYear", worstYear?.year || "--");
        setText("mostAtRiskProvince", mostAtRisk?.province || "--");
        setText("totalFloodEvents", formatNumber(totalFloods));
        setText("severeDroughtYears", formatNumber(severeDroughtYears));

        renderBarChart(
            "combinedStressChart",
            stressRows.map((item) => item.year),
            stressRows.map((item) => item.score),
            "Combined Climate Stress Score",
            "#15803d",
            "Stress score"
        );

        renderBarChart(
            "provinceRiskChart",
            provinceRisk.map((item) => item.province),
            provinceRisk.map((item) => item.score),
            "Combined Province Risk Score",
            "#0f766e",
            "Risk score"
        );

        renderComboBarLineChart(
            "floodRainfallChart",
            allYears,
            {
                label: "Average Rainfall (mm)",
                data: allYears.map((year) => rainfallMap.get(String(year)) || null),
                backgroundColor: "rgba(15, 118, 110, 0.45)"
            },
            {
                label: "Flood-risk records",
                data: allYears.map((year) => floodMap.get(String(year)) || 0),
                borderColor: "#1d4ed8",
                backgroundColor: "rgba(29, 78, 216, 0.12)"
            },
            "Rainfall / flood signal"
        );

        renderComboBarLineChart(
            "droughtRainfallChart",
            allYears,
            {
                label: "Average Rainfall (mm)",
                data: allYears.map((year) => rainfallMap.get(String(year)) || null),
                backgroundColor: "rgba(15, 118, 110, 0.42)"
            },
            {
                label: "Average Drought Score",
                data: allYears.map((year) => droughtMap.get(String(year)) || null),
                borderColor: "#b45309",
                backgroundColor: "rgba(180, 83, 9, 0.12)"
            },
            "Rainfall / drought signal"
        );

        const monthly = allFloods?.monthly_pattern || {};
        const monthLabels = monthly.labels || [];
        const monthlyFloods = monthly.flood_events || [];
        const monthlyRainfall = monthly.average_rainfall || [];
        const monthlyStress = normalize(monthlyRainfall).map((rainStress, index) => {
            const floodStress = normalize(monthlyFloods)[index] || 0;
            return Number(((rainStress + floodStress) * 50).toFixed(1));
        });

        renderLineChart(
            "seasonalVulnerabilityChart",
            monthLabels,
            [{
                label: "Seasonal Vulnerability Score",
                data: monthlyStress,
                borderColor: "#0284c7",
                backgroundColor: "rgba(2, 132, 199, 0.12)",
                tension: 0.25,
                pointRadius: 3,
                fill: true
            }],
            "Vulnerability score"
        );

        const peakRainFlood = stressRows.length
            ? stressRows.reduce((best, item) => ((item.rainfall || 0) + (item.floods || 0)) > ((best.rainfall || 0) + (best.floods || 0)) ? item : best, stressRows[0]).year
            : null;
        const peakDrought = stressRows.length
            ? stressRows.reduce((best, item) => (item.drought || 0) > (best.drought || 0) ? item : best, stressRows[0]).year
            : null;

        renderInsights({
            stressRows,
            provinceRisk,
            totalFloods,
            severeDroughtYears,
            peakRainFloodYear: peakRainFlood,
            peakDroughtYear: peakDrought
        });

        if (!stressRows.length) {
            setErrorState("No combined climate impact data is available right now.");
            sendNotification("info", "No impact data", "Combined climate impact analysis did not return any records.", {
                id: "impact-empty"
            });
        }
    } catch (error) {
        console.error("Failed to load impact page:", error);
        setErrorState("Combined climate impact analysis could not be loaded right now.");
        sendNotification("danger", "Impact analysis unavailable", "Combined climate impact analysis could not be loaded right now.", {
            id: "impact-load-error",
            duration: 6500
        });
    }
}

document.addEventListener("DOMContentLoaded", loadImpactPage);
