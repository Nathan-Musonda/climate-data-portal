const impactCharts = {};
const districtDirectory = [];

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

function setDisplay(id, display) {
    const element = document.getElementById(id);
    if (element) element.style.display = display;
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

function renderBarChart(id, labels, values, label, color, yTitle = "", highlightedLabel = null) {
    const canvas = document.getElementById(id);
    if (!canvas) return;
    destroyChart(id);

    const backgroundColors = (labels || []).map((item) => {
        if (highlightedLabel !== null && String(item) === String(highlightedLabel)) {
            return "#1d4ed8";
        }
        return color;
    });

    impactCharts[id] = new Chart(canvas, {
        type: "bar",
        data: {
            labels,
            datasets: [{
                label,
                data: values,
                backgroundColor: backgroundColors,
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
        floods: floodValues[index] || 0,
        rainfall_stress: rainfallStress[index],
        temperature_stress: tempStress[index],
        drought_stress: droughtStress[index],
        flood_stress: floodStress[index]
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
        items.push(`The most difficult year overall is <strong>${worstYear.year}</strong>, with an overall climate pressure score of <strong>${formatDecimal(worstYear.score, 1)}</strong>.`);
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
        items.push(`Rainfall and flood pressure are strongest together around <strong>${peakRainFloodYear}</strong>.`);
    }
    if (peakDroughtYear) {
        items.push(`The strongest drought-pressure year in the trend is <strong>${peakDroughtYear}</strong>.`);
    }

    container.innerHTML = items.length
        ? items.map((item) => `<div class="insight-item"><p>${item}</p></div>`).join("")
        : '<div class="insight-item"><p>Not enough data is available to generate impact findings yet.</p></div>';
}

function describeStressLevel(score) {
    if (!Number.isFinite(score)) return "Unknown";
    if (score >= 70) return "Very high";
    if (score >= 55) return "High";
    if (score >= 40) return "Moderate";
    return "Lower";
}

function buildYearStressNarrative(row) {
    const signals = [];

    if (Number.isFinite(row.temperature_stress) && row.temperature_stress >= 0.66) signals.push("hotter-than-usual conditions");
    if (Number.isFinite(row.rainfall_stress) && row.rainfall_stress >= 0.66) signals.push("a strong rainfall deficit");
    if (Number.isFinite(row.drought_stress) && row.drought_stress >= 0.66) signals.push("elevated drought pressure");
    if (Number.isFinite(row.flood_stress) && row.flood_stress >= 0.66) signals.push("frequent flood-risk rainfall events");

    const metrics = [];
    if (row.temperature !== null && row.temperature !== undefined) metrics.push(`${formatDecimal(row.temperature, 1)} C avg max temperature`);
    if (row.rainfall !== null && row.rainfall !== undefined) metrics.push(`${formatDecimal(row.rainfall, 1)} mm average rainfall`);
    if (row.drought !== null && row.drought !== undefined) metrics.push(`${formatDecimal(row.drought, 2)} drought score`);
    metrics.push(`${formatNumber(row.floods || 0)} flood-risk records`);

    const signalText = signals.length
        ? `The main climate pressures were ${signals.join(", ")}.`
        : "This year showed comparatively lower overall climate pressure than the most difficult years in the series.";

    return `${signalText} Recorded values include ${metrics.join(", ")}.`;
}

function renderYearTimeline(stressRows) {
    const container = document.getElementById("impactYearTimeline");
    if (!container) return;

    if (!Array.isArray(stressRows) || !stressRows.length) {
        container.innerHTML = '<div class="timeline-item"><p class="timeline-text">No year-by-year climate summary is available yet.</p></div>';
        return;
    }

    container.innerHTML = stressRows
        .slice()
        .sort((a, b) => Number(a.year) - Number(b.year))
        .map((row) => `
            <div class="timeline-item">
                <div class="timeline-top">
                    <div class="timeline-year">${row.year}</div>
                    <div class="timeline-score">Overall climate pressure ${formatDecimal(row.score, 1)} - ${describeStressLevel(row.score)}</div>
                </div>
                <p class="timeline-text">${buildYearStressNarrative(row)}</p>
            </div>
        `)
        .join("");
}

function setErrorState(message) {
    ["worstClimateYear", "mostAtRiskProvince", "totalFloodEvents", "severeDroughtYears"].forEach((id) => setText(id, "--"));
    ["combinedStressChart", "provinceRiskChart", "floodRainfallChart", "droughtRainfallChart", "seasonalVulnerabilityChart"].forEach(destroyChart);
    const container = document.getElementById("impactInsights");
    if (container) container.innerHTML = `<div class="insight-item"><p class="text-danger mb-0">${message}</p></div>`;
    const timeline = document.getElementById("impactYearTimeline");
    if (timeline) timeline.innerHTML = `<div class="timeline-item"><p class="timeline-text text-danger mb-0">${message}</p></div>`;
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function getBadgeConfig(kind, value) {
    if (kind === "temperature") {
        const numeric = toFiniteNumber(value);
        if (numeric === null) return { text: "No reading", className: "badge-moderate" };
        if (numeric >= 34) return { text: "Very hot", className: "badge-bad" };
        if (numeric >= 31) return { text: "Warm", className: "badge-moderate" };
        return { text: "Milder", className: "badge-good" };
    }

    if (kind === "rainfall") {
        const numeric = toFiniteNumber(value);
        if (numeric === null) return { text: "No reading", className: "badge-moderate" };
        if (numeric < 700) return { text: "Low rainfall", className: "badge-bad" };
        if (numeric < 1000) return { text: "Moderate rainfall", className: "badge-moderate" };
        return { text: "High rainfall", className: "badge-good" };
    }

    if (kind === "drought") {
        const label = String(value || "").trim().toLowerCase();
        if (!label) return { text: "No reading", className: "badge-moderate" };
        if (label === "severe" || label === "extreme") return { text: "Severe drought", className: "badge-bad" };
        if (label === "moderate") return { text: "Moderate drought", className: "badge-moderate" };
        if (label === "mild") return { text: "Mild drought", className: "badge-moderate" };
        return { text: "No drought", className: "badge-good" };
    }

    if (kind === "flood") {
        const numeric = toFiniteNumber(value);
        if (numeric === null) return { text: "No reading", className: "badge-moderate" };
        if (numeric >= 6) return { text: "Frequent flood signals", className: "badge-bad" };
        if (numeric >= 2) return { text: "Some flood signals", className: "badge-moderate" };
        return { text: "Limited flood signals", className: "badge-good" };
    }

    if (kind === "population") {
        const numeric = toFiniteNumber(value);
        if (numeric === null) return { text: "No reading", className: "badge-moderate" };
        if (numeric >= 1000) return { text: "Many people affected", className: "badge-bad" };
        if (numeric > 0) return { text: "People affected recorded", className: "badge-moderate" };
        return { text: "No affected people recorded", className: "badge-good" };
    }

    if (kind === "crop_yield") {
        const numeric = toFiniteNumber(value);
        if (numeric === null) return { text: "No reading", className: "badge-moderate" };
        if (numeric < 1800) return { text: "Lower recorded yield", className: "badge-bad" };
        if (numeric < 2400) return { text: "Mid-range yield", className: "badge-moderate" };
        return { text: "Higher recorded yield", className: "badge-good" };
    }

    if (kind === "livestock_mortality") {
        const numeric = toFiniteNumber(value);
        if (numeric === null) return { text: "No reading", className: "badge-moderate" };
        if (numeric >= 5) return { text: "Higher mortality", className: "badge-bad" };
        if (numeric >= 2) return { text: "Moderate mortality", className: "badge-moderate" };
        return { text: "Lower mortality", className: "badge-good" };
    }

    if (kind === "food_price") {
        const numeric = toFiniteNumber(value);
        if (numeric === null) return { text: "No reading", className: "badge-moderate" };
        if (numeric >= 45) return { text: "Higher recorded price", className: "badge-bad" };
        if (numeric >= 35) return { text: "Mid-range price", className: "badge-moderate" };
        return { text: "Lower recorded price", className: "badge-good" };
    }

    if (kind === "lake_level") {
        const numeric = toFiniteNumber(value);
        if (numeric === null) return { text: "No reading", className: "badge-moderate" };
        if (numeric < 475) return { text: "Lower lake level", className: "badge-bad" };
        if (numeric < 480) return { text: "Mid-range lake level", className: "badge-moderate" };
        return { text: "Higher lake level", className: "badge-good" };
    }

    if (kind === "hydropower") {
        const numeric = toFiniteNumber(value);
        if (numeric === null) return { text: "No reading", className: "badge-moderate" };
        if (numeric < 800) return { text: "Lower output", className: "badge-bad" };
        if (numeric < 950) return { text: "Mid-range output", className: "badge-moderate" };
        return { text: "Higher output", className: "badge-good" };
    }

    return { text: "Unknown", className: "badge-moderate" };
}

function applyBadge(id, config) {
    const element = document.getElementById(id);
    if (!element) return;
    element.className = `cr-badge ${config.className}`;
    element.textContent = config.text;
}

function getImpactLevelClass(level) {
    if (level === "Severe") return "level-severe";
    if (level === "High") return "level-high";
    if (level === "Moderate") return "level-moderate";
    return "level-low";
}

function formatMetricValue(value, unit = "", decimals = 1) {
    const numeric = toFiniteNumber(value);
    if (numeric === null) return "--";
    const formatted = decimals === 0 ? formatNumber(numeric) : formatDecimal(numeric, decimals);
    return unit ? `${formatted} ${unit}` : formatted;
}

function renderObservedImpactCard(prefix, options) {
    setText(`impact${prefix}Value`, options.value);

    const levelElement = document.getElementById(`impact${prefix}Level`);
    if (levelElement) {
        levelElement.className = `impact-level ${getImpactLevelClass(options.level)}`;
        levelElement.innerHTML = `<i class="fas fa-circle-info"></i> ${escapeHtml(options.levelLabel)}`;
    }

    setText(`impact${prefix}Desc`, options.description);
}

function buildDistrictNarrative({ district, province, year, stressRow, droughtLabel, floodSummary }) {
    const pieces = [];
    const location = province ? `${district}, ${province}` : district;
    const populationAffected = toFiniteNumber(stressRow?.populationAffected) || 0;

    pieces.push(`${location} in ${year} showed ${describeStressLevel(stressRow?.score)} overall climate pressure.`);

    if (stressRow?.temperature !== null && stressRow?.temperature !== undefined) {
        pieces.push(`Average daytime temperatures were around ${formatDecimal(stressRow.temperature, 1)} C.`);
    }
    if (stressRow?.rainfall !== null && stressRow?.rainfall !== undefined) {
        pieces.push(`Average rainfall was about ${formatDecimal(stressRow.rainfall, 1)} mm.`);
    }
    if (droughtLabel) {
        pieces.push(`The dominant drought condition recorded was ${droughtLabel}.`);
    }
    if (toFiniteNumber(floodSummary?.flood_event_count) !== null) {
        pieces.push(`Flood-signal rainfall was recorded ${formatNumber(floodSummary.flood_event_count)} times.`);
    }
    if (populationAffected > 0) {
        pieces.push(`${formatNumber(populationAffected)} people were reported as affected.`);
    }
    if (toFiniteNumber(stressRow?.cropYield) !== null) {
        pieces.push(`Average crop yield was ${formatMetricValue(stressRow.cropYield, "kg/ha", 1)}.`);
    }
    if (toFiniteNumber(stressRow?.hydropowerMw) !== null) {
        pieces.push(`Average electricity output from the hydropower field was ${formatMetricValue(stressRow.hydropowerMw, "MW", 1)}.`);
    }
    if (toFiniteNumber(stressRow?.foodPrice) !== null) {
        pieces.push(`Average recorded food price was ${formatMetricValue(stressRow.foodPrice, "ZMW", 1)}.`);
    }

    if ((stressRow?.score || 0) >= 60) {
        pieces.push("This suggests a year where local planning, farming, and water access were likely under strong pressure.");
    } else if ((stressRow?.score || 0) >= 40) {
        pieces.push("This suggests a year with noticeable climate strain, but not among the district's most severe years.");
    } else {
        pieces.push("This suggests a comparatively less stressful year than the district's peak pressure periods.");
    }

    return pieces.join(" ");
}

function populateDistrictOptions(selectedProvince = "", selectedDistrict = "") {
    const districtSelect = document.getElementById("impactDistrict");
    if (!districtSelect) return;

    const rows = districtDirectory.length
        ? districtDirectory
        : Array.from(districtSelect.options)
            .map((option) => ({ district: option.value, province: "" }))
            .filter((item) => item.district);

    const filtered = rows.filter((item) => !selectedProvince || item.province === selectedProvince);
    const districtNames = filtered.map((item) => item.district).sort((a, b) => a.localeCompare(b));
    const finalDistrict = districtNames.includes(selectedDistrict) ? selectedDistrict : "";

    districtSelect.innerHTML = '<option value="">Select a district</option>';
    districtNames.forEach((district) => {
        const option = document.createElement("option");
        option.value = district;
        option.textContent = district;
        if (district === finalDistrict) option.selected = true;
        districtSelect.appendChild(option);
    });
}

async function loadDistrictDirectory() {
    try {
        const rows = await fetchJSON("/api/v1/district-directory");
        if (Array.isArray(rows)) {
            districtDirectory.splice(0, districtDirectory.length, ...rows);
        }
    } catch (error) {
        console.warn("Unable to load district directory", error);
    }
}

async function buildDistrictStressSeries(district, years) {
    const [rainfall, temperature, drought] = await Promise.all([
        fetchJSON(`/api/v1/rainfall-trend?district=${encodeURIComponent(district)}`),
        fetchJSON(`/api/v1/temperature-trend?district=${encodeURIComponent(district)}`),
        fetchJSON(`/api/v1/drought-trend?district=${encodeURIComponent(district)}`)
    ]);

    const annualFloodResponses = await Promise.all(
        years.map((year) =>
            fetchJSON(`/api/v1/flood-events?district=${encodeURIComponent(district)}&year=${encodeURIComponent(year)}`)
                .catch(() => ({ summary: { flood_event_count: 0 } }))
        )
    );

    const rainfallLabels = rainfall.labels || rainfall.years || [];
    const tempLabels = temperature.labels || temperature.years || [];
    const droughtLabels = drought.labels || drought.years || [];
    const allYears = Array.from(new Set([...rainfallLabels, ...tempLabels, ...droughtLabels, ...(years || [])].map(String))).sort();

    const rainfallMap = getSeriesPointMap(rainfallLabels, rainfall.avg_rainfall || rainfall.average_rainfall || []);
    const tempMap = getSeriesPointMap(tempLabels, temperature.avg_max_temp || temperature.avg_temperature || []);
    const droughtMap = getSeriesPointMap(droughtLabels, drought.avg_drought_score || []);
    const floodMap = new Map();

    annualFloodResponses.forEach((payload, index) => {
        floodMap.set(String(years[index]), toFiniteNumber(payload?.summary?.flood_event_count) || 0);
    });

    return buildCombinedStress(allYears, rainfallMap, tempMap, droughtMap, floodMap);
}

async function loadDistrictImpact() {
    const province = document.getElementById("impactProvince")?.value || "";
    const district = document.getElementById("impactDistrict")?.value || "";
    const year = document.getElementById("impactYear")?.value || "";

    if (!district || !year) {
        sendNotification("warning", "Selection needed", "Choose a district and year before loading local impact analysis.", {
            id: "impact-selection-required",
            duration: 4500
        });
        return;
    }

    try {
        const yearsPayload = await fetchJSON("/api/v1/years");
        const years = Array.isArray(yearsPayload) ? yearsPayload.map(String) : [];

        const [summary, floodYear, districtStressRows] = await Promise.all([
            fetchJSON(`/api/v1/district-summary?district=${encodeURIComponent(district)}&year=${encodeURIComponent(year)}`),
            fetchJSON(`/api/v1/flood-events?district=${encodeURIComponent(district)}&year=${encodeURIComponent(year)}`),
            buildDistrictStressSeries(district, years)
        ]);

        const provinceName = summary?.province || province || "";
        const matchedStressRow = districtStressRows.find((row) => String(row.year) === String(year));
        const stressRow = matchedStressRow ? {
            ...matchedStressRow,
            populationAffected: summary?.population_affected || 0,
            cropYield: summary?.avg_crop_yield,
            hydropowerMw: summary?.avg_hydropower_mw,
            foodPrice: summary?.avg_food_price
        } : {
            year,
            score: 0,
            rainfall: summary?.avg_rainfall,
            temperature: summary?.avg_temp_max,
            drought: null,
            floods: floodYear?.summary?.flood_event_count || 0,
            populationAffected: summary?.population_affected || 0,
            cropYield: summary?.avg_crop_yield,
            hydropowerMw: summary?.avg_hydropower_mw,
            foodPrice: summary?.avg_food_price
        };

        const droughtLabel = summary?.drought_severity || "";
        const floodCount = floodYear?.summary?.flood_event_count || 0;

        setText("impactFilterLabel", `${district} - ${year}`);
        setText("impactHeadlineTitle", `${district}, ${year}`);
        setText(
            "impactHeadlineDesc",
            provinceName
                ? `${district} District in ${provinceName} Province. Climate conditions and reported local impact information for communities, farming, food prices, water, and electricity.`
                : `Climate conditions and reported local impact information for communities, farming, food prices, water, and electricity in ${district}.`
        );

        const overallBadge = document.getElementById("impactOverallBadge");
        if (overallBadge) {
            overallBadge.innerHTML = `<i class="fas fa-circle-info"></i> ${escapeHtml(describeStressLevel(stressRow.score))} climate pressure year`;
        }

        setText("impactNarrativeYear", `${district} in ${year}:`);
        setText("impactNarrativeText", buildDistrictNarrative({
            district,
            province: provinceName,
            year,
            stressRow,
            droughtLabel,
            floodSummary: floodYear?.summary || {}
        }));

        setText("impactTempValue", summary?.avg_temp_max !== null && summary?.avg_temp_max !== undefined ? `${formatDecimal(summary.avg_temp_max, 1)} C` : "--");
        setText("impactRainfallValue", summary?.avg_rainfall !== null && summary?.avg_rainfall !== undefined ? `${formatDecimal(summary.avg_rainfall, 1)} mm` : "--");
        setText("impactDroughtValue", droughtLabel || "--");
        setText("impactFloodValue", formatNumber(floodCount));
        setText("impactPopulationValue", formatNumber(summary?.population_affected || 0));

        applyBadge("impactTempBadge", getBadgeConfig("temperature", summary?.avg_temp_max));
        applyBadge("impactRainfallBadge", getBadgeConfig("rainfall", summary?.avg_rainfall));
        applyBadge("impactDroughtBadge", getBadgeConfig("drought", droughtLabel));
        applyBadge("impactFloodBadge", getBadgeConfig("flood", floodCount));
        applyBadge("impactPopulationBadge", getBadgeConfig("population", summary?.population_affected || 0));

        renderObservedImpactCard("People", {
            value: formatNumber(summary?.population_affected || 0),
            level: (summary?.population_affected || 0) >= 1000 ? "Severe" : (summary?.population_affected || 0) > 0 ? "Moderate" : "Low",
            levelLabel: getBadgeConfig("population", summary?.population_affected || 0).text,
            description: (summary?.population_affected || 0) > 0
                ? "This is the total affected population reported for the selected district and year."
                : "No affected people were reported for the selected district and year."
        });

        renderObservedImpactCard("Crops", {
            value: formatMetricValue(summary?.avg_crop_yield, "kg/ha", 1),
            level: getBadgeConfig("crop_yield", summary?.avg_crop_yield).className === "badge-bad" ? "High" : getBadgeConfig("crop_yield", summary?.avg_crop_yield).className === "badge-moderate" ? "Moderate" : "Low",
            levelLabel: getBadgeConfig("crop_yield", summary?.avg_crop_yield).text,
            description: "This is the average crop yield reported for the selected district and year."
        });

        renderObservedImpactCard("Livestock", {
            value: formatMetricValue(summary?.avg_livestock_mortality, "%", 1),
            level: getBadgeConfig("livestock_mortality", summary?.avg_livestock_mortality).className === "badge-bad" ? "High" : getBadgeConfig("livestock_mortality", summary?.avg_livestock_mortality).className === "badge-moderate" ? "Moderate" : "Low",
            levelLabel: getBadgeConfig("livestock_mortality", summary?.avg_livestock_mortality).text,
            description: "This is the average livestock mortality percentage reported for the selected district and year."
        });

        renderObservedImpactCard("Water", {
            value: formatMetricValue(summary?.avg_food_price, "ZMW", 1),
            level: getBadgeConfig("food_price", summary?.avg_food_price).className === "badge-bad" ? "High" : getBadgeConfig("food_price", summary?.avg_food_price).className === "badge-moderate" ? "Moderate" : "Low",
            levelLabel: getBadgeConfig("food_price", summary?.avg_food_price).text,
            description: "This is the average food price reported for the selected district and year."
        });

        renderObservedImpactCard("Lake", {
            value: formatMetricValue(summary?.avg_lake_kariba_level, "m", 1),
            level: getBadgeConfig("lake_level", summary?.avg_lake_kariba_level).className === "badge-bad" ? "High" : getBadgeConfig("lake_level", summary?.avg_lake_kariba_level).className === "badge-moderate" ? "Moderate" : "Low",
            levelLabel: getBadgeConfig("lake_level", summary?.avg_lake_kariba_level).text,
            description: "This is the average Lake Kariba level reported for the selected district and year."
        });

        renderObservedImpactCard("Power", {
            value: formatMetricValue(summary?.avg_hydropower_mw, "MW", 1),
            level: getBadgeConfig("hydropower", summary?.avg_hydropower_mw).className === "badge-bad" ? "High" : getBadgeConfig("hydropower", summary?.avg_hydropower_mw).className === "badge-moderate" ? "Moderate" : "Low",
            levelLabel: getBadgeConfig("hydropower", summary?.avg_hydropower_mw).text,
            description: "This is the average hydropower output reported for the selected district and year."
        });

        renderBarChart(
            "impactDistrictChart",
            districtStressRows.map((item) => item.year),
            districtStressRows.map((item) => item.score),
            "District Overall Climate Pressure",
            "#0f766e",
            "Overall climate pressure",
            String(year)
        );
        setText("impactDistrictChartSubtitle", `Year-by-year overall climate pressure for ${district} - the selected year is highlighted.`);

        setDisplay("impactHeadline", "flex");
        setDisplay("impactNarrative", "block");
        setDisplay("impactClimateSection", "block");
        setDisplay("impactCardsSection", "block");
        setDisplay("impactDistrictChartSection", "block");
    } catch (error) {
        console.error("Failed to load district impact:", error);
        sendNotification("danger", "Impact analysis unavailable", "Local district impact analysis could not be loaded right now.", {
            id: "district-impact-load-error",
            duration: 6000
        });
    }
}

async function loadNationalImpactPage() {
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
            "Overall Climate Pressure",
            "#15803d",
            "Overall climate pressure"
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
        renderYearTimeline(stressRows);

        if (!stressRows.length) {
            setErrorState("No overall climate pressure data is available right now.");
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

function bindImpactControls() {
    const provinceSelect = document.getElementById("impactProvince");
    const districtSelect = document.getElementById("impactDistrict");
    const applyButton = document.getElementById("impactApplyBtn");

    if (provinceSelect) {
        provinceSelect.addEventListener("change", () => {
            populateDistrictOptions(provinceSelect.value, "");
        });
    }

    if (districtSelect && provinceSelect) {
        districtSelect.addEventListener("change", () => {
            const selected = districtDirectory.find((item) => item.district === districtSelect.value);
            if (selected && selected.province && provinceSelect.value !== selected.province) {
                provinceSelect.value = selected.province;
                populateDistrictOptions(selected.province, districtSelect.value);
            }
        });
    }

    if (applyButton) {
        applyButton.addEventListener("click", loadDistrictImpact);
    }
}

async function loadImpactPage() {
    await Promise.all([
        loadDistrictDirectory(),
        loadNationalImpactPage()
    ]);

    const provinceValue = document.getElementById("impactProvince")?.value || "";
    const districtValue = document.getElementById("impactDistrict")?.value || "";
    populateDistrictOptions(provinceValue, districtValue);
    bindImpactControls();
}

document.addEventListener("DOMContentLoaded", loadImpactPage);
