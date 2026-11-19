(function attachClimateMonthlyHelper(globalScope) {
    const CANONICAL_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const MONTH_NUMBERS = CANONICAL_MONTHS.map((_, index) => index + 1);
    const MONTH_INDEX_BY_LABEL = CANONICAL_MONTHS.reduce((lookup, month, index) => {
        lookup[month.toLowerCase()] = index;
        return lookup;
    }, {});

    function toFiniteNumber(value) {
        if (value === null || value === undefined || value === "") return null;
        const numericValue = Number(value);
        return Number.isFinite(numericValue) ? numericValue : null;
    }

    function getMonthIndex(label) {
        const normalizedLabel = String(label || "").trim().slice(0, 3).toLowerCase();
        return Object.prototype.hasOwnProperty.call(MONTH_INDEX_BY_LABEL, normalizedLabel)
            ? MONTH_INDEX_BY_LABEL[normalizedLabel]
            : null;
    }

    function isMonthlyPayload(payload) {
        if (!payload || typeof payload !== "object") return false;
        if (payload.period_type === "month") return true;
        return Array.isArray(payload.month_numbers) || Array.isArray(payload.month_labels);
    }

    function resolveLabels(payload) {
        if (isMonthlyPayload(payload)) return CANONICAL_MONTHS.slice();
        if (Array.isArray(payload?.years) && payload.years.length) return payload.years.slice();
        if (Array.isArray(payload?.labels) && payload.labels.length) return payload.labels.slice();
        return [];
    }

    function cloneArray(values) {
        return Array.isArray(values) ? values.slice() : [];
    }

    function alignSeries(values, { labels = [], monthNumbers = [] } = {}) {
        const alignedValues = Array(CANONICAL_MONTHS.length).fill(null);
        const sourceValues = Array.isArray(values) ? values : [];

        const assignValue = (monthIndex, rawValue) => {
            if (!Number.isInteger(monthIndex) || monthIndex < 0 || monthIndex >= CANONICAL_MONTHS.length) return;
            alignedValues[monthIndex] = toFiniteNumber(rawValue);
        };

        if (Array.isArray(monthNumbers) && monthNumbers.length === sourceValues.length) {
            monthNumbers.forEach((monthNumber, index) => {
                const numericMonth = Number(monthNumber);
                assignValue(Number.isInteger(numericMonth) ? numericMonth - 1 : null, sourceValues[index]);
            });
            return alignedValues;
        }

        if (Array.isArray(labels) && labels.length === sourceValues.length) {
            labels.forEach((label, index) => assignValue(getMonthIndex(label), sourceValues[index]));
            return alignedValues;
        }

        sourceValues.slice(0, CANONICAL_MONTHS.length).forEach((value, index) => assignValue(index, value));
        return alignedValues;
    }

    function getSeries(payload, key) {
        const sourceValues = Array.isArray(payload?.[key]) ? payload[key] : [];
        if (!isMonthlyPayload(payload)) return cloneArray(sourceValues);
        return alignSeries(sourceValues, {
            labels: payload?.years || payload?.labels || [],
            monthNumbers: payload?.month_numbers || []
        });
    }

    function normalizePayload(payload, seriesKeys = []) {
        const source = payload && typeof payload === "object" ? { ...payload } : {};
        if (!isMonthlyPayload(source)) {
            const labels = resolveLabels(source);
            const normalized = {
                ...source,
                labels,
                years: cloneArray(labels)
            };
            (seriesKeys || []).forEach((key) => {
                normalized[key] = cloneArray(source?.[key]);
            });
            return normalized;
        }

        const normalized = {
            ...source,
            period_type: "month",
            labels: CANONICAL_MONTHS.slice(),
            years: CANONICAL_MONTHS.slice(),
            month_numbers: MONTH_NUMBERS.slice(),
            month_labels: CANONICAL_MONTHS.slice()
        };
        (seriesKeys || []).forEach((key) => {
            normalized[key] = getSeries(source, key);
        });
        return normalized;
    }

    function buildSingleSeriesCoverage(values) {
        const missingMonthLabels = [];
        let observedMonthCount = 0;

        CANONICAL_MONTHS.forEach((month, index) => {
            if (toFiniteNumber(values?.[index]) === null) {
                missingMonthLabels.push(month);
                return;
            }
            observedMonthCount += 1;
        });

        return {
            observedMonthCount,
            missingMonthLabels,
            isCompletePeriod: observedMonthCount === CANONICAL_MONTHS.length
        };
    }

    function buildMultiSeriesCoverage(seriesDefinitions) {
        const missingMonthLabels = [];
        const partialMonthLabels = [];
        let observedMonthCount = 0;

        CANONICAL_MONTHS.forEach((month, index) => {
            const state = (seriesDefinitions || []).map((definition, definitionIndex) => {
                const label = definition?.label || `series ${definitionIndex + 1}`;
                const hasValue = toFiniteNumber(definition?.values?.[index]) !== null;
                return { label, hasValue };
            });
            const observedSeries = state.filter((item) => item.hasValue);
            const missingSeries = state.filter((item) => !item.hasValue);

            if (observedSeries.length) {
                observedMonthCount += 1;
            }

            if (!observedSeries.length) {
                missingMonthLabels.push(month);
                return;
            }

            if (missingSeries.length) {
                const suffix = missingSeries.map((item) => item.label).join(", ");
                partialMonthLabels.push(`${month} (${suffix})`);
            }
        });

        return {
            observedMonthCount,
            missingMonthLabels,
            partialMonthLabels,
            isCompletePeriod: observedMonthCount === CANONICAL_MONTHS.length && partialMonthLabels.length === 0
        };
    }

    globalScope.ClimateMonthly = {
        CANONICAL_MONTHS,
        alignSeries,
        buildMultiSeriesCoverage,
        buildSingleSeriesCoverage,
        getSeries,
        getMonthIndex,
        isMonthlyPayload,
        normalizePayload,
        resolveLabels,
        toFiniteNumber
    };
})(window);
