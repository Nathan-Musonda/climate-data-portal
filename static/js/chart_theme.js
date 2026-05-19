(function () {
    if (!window.Chart) return;

    const axisText = "#334155";
    const gridLine = "rgba(100, 116, 139, 0.16)";

    function getDatasetType(chart, dataset) {
        return dataset.type || chart.config.type || "line";
    }

    function styleDataset(chart, dataset) {
        const type = getDatasetType(chart, dataset);

        if (type === "bar") {
            dataset.borderRadius = dataset.borderRadius ?? 8;
            dataset.borderSkipped = dataset.borderSkipped ?? false;
            dataset.maxBarThickness = dataset.maxBarThickness ?? 38;
            dataset.barPercentage = dataset.barPercentage ?? 0.58;
            dataset.categoryPercentage = dataset.categoryPercentage ?? 0.72;
        }

        if (type === "line") {
            dataset.tension = dataset.tension ?? 0.25;
            dataset.borderWidth = dataset.borderWidth ?? 3;
            dataset.pointRadius = dataset.pointRadius ?? 3;
            dataset.pointHoverRadius = dataset.pointHoverRadius ?? 6;
            dataset.pointHitRadius = dataset.pointHitRadius ?? 12;
            dataset.fill = dataset.fill ?? false;
        }
    }

    Chart.defaults.color = axisText;
    Chart.defaults.font.family = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
    Chart.defaults.plugins.legend.position = "bottom";
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.plugins.legend.labels.boxWidth = 8;
    Chart.defaults.plugins.legend.labels.boxHeight = 8;
    Chart.defaults.plugins.legend.labels.padding = 16;
    Chart.defaults.plugins.tooltip.backgroundColor = "#0F172A";
    Chart.defaults.plugins.tooltip.titleColor = "#F8FAFC";
    Chart.defaults.plugins.tooltip.bodyColor = "#E2E8F0";
    Chart.defaults.plugins.tooltip.padding = 12;
    Chart.defaults.plugins.tooltip.cornerRadius = 8;
    Chart.defaults.plugins.tooltip.displayColors = true;
    Chart.defaults.elements.line.borderWidth = 3;
    Chart.defaults.elements.line.tension = 0.25;
    Chart.defaults.elements.point.radius = 3;
    Chart.defaults.elements.point.hoverRadius = 6;
    Chart.defaults.elements.bar.borderRadius = 8;
    Chart.defaults.elements.bar.borderSkipped = false;

    if (Chart.defaults.scales?.category) {
        Chart.defaults.scales.category.grid.display = false;
        Chart.defaults.scales.category.ticks.color = axisText;
        Chart.defaults.scales.category.ticks.padding = 10;
        Chart.defaults.scales.category.ticks.font = { size: 12, weight: "600" };
        Chart.defaults.scales.category.ticks.maxRotation = 35;
    }

    if (Chart.defaults.scales?.linear) {
        Chart.defaults.scales.linear.grid.color = gridLine;
        Chart.defaults.scales.linear.grid.drawBorder = false;
        Chart.defaults.scales.linear.ticks.color = axisText;
        Chart.defaults.scales.linear.ticks.padding = 8;
    }

    Chart.register({
        id: "portalChartTheme",
        beforeInit(chart) {
            (chart.data?.datasets || []).forEach((dataset) => styleDataset(chart, dataset));
        }
    });
})();
