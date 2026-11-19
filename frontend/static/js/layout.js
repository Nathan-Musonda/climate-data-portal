// Shared layout, notifications, live weather and ticker logic.
// Page-specific config (window.portal*) is set inline in base.html.
        let currentFilters = { province: 'all', startYear: 2015, endYear: 2025 };
        const SITE_SUMMARY_CACHE_KEY = 'climatePortalSiteSummaryV4';
        const SITE_SUMMARY_CACHE_TTL_MS = 5 * 60 * 1000;
        const LIVE_WEATHER_CACHE_KEY = 'climatePortalLiveWeatherV2';
        const LIVE_WEATHER_CACHE_TTL_MS = 5 * 60 * 1000;
        const VIEWER_COORDINATES_KEY = 'climatePortalViewerCoordinates';
        const VIEWER_COORDINATES_MAX_AGE_MS = 24 * 60 * 60 * 1000;
        const SIDEBAR_PINNED_KEY = 'climatePortalSidebarPinned';
        const LEGACY_SITE_SUMMARY_CACHE_PREFIX = 'climatePortalSiteSummary';
        const LEGACY_LIVE_WEATHER_CACHE_KEY = 'climatePortalLiveWeather';
        
        document.addEventListener('DOMContentLoaded', function() {
            if (hasGlobalFilterControls()) {
                loadGlobalFilters();
            }
            setupGlobalListeners();
        });

        function hasGlobalFilterControls() {
            return Boolean(
                document.getElementById('globalProvince') &&
                document.getElementById('globalStartYear') &&
                document.getElementById('globalEndYear')
            );
        }

        function purgeLegacyPortalCaches() {
            try {
                const keysToRemove = [];
                for (let index = 0; index < localStorage.length; index += 1) {
                    const key = localStorage.key(index);
                    if (!key) continue;
                    if (
                        key === LEGACY_LIVE_WEATHER_CACHE_KEY ||
                        key === LEGACY_SITE_SUMMARY_CACHE_PREFIX ||
                        key.startsWith(`${LEGACY_SITE_SUMMARY_CACHE_PREFIX}:`)
                    ) {
                        keysToRemove.push(key);
                    }
                }

                keysToRemove.forEach((key) => localStorage.removeItem(key));
            } catch (error) {
                console.warn('Unable to purge legacy portal caches:', error);
            }
        }
        
        async function loadGlobalFilters() {
            try {
                const provincesRes = await fetch('/api/v1/provinces');
                const provincesData = await provincesRes.json();
                if (provincesData.success) {
                    const select = document.getElementById('globalProvince');
                    provincesData.data.forEach(province => {
                        const option = document.createElement('option');
                        option.value = province;
                        option.textContent = province;
                        select.appendChild(option);
                    });
                }
                
                const yearsRes = await fetch('/api/v1/years');
                const yearsData = await yearsRes.json();
                if (yearsData.success) {
                    const startSelect = document.getElementById('globalStartYear');
                    const endSelect = document.getElementById('globalEndYear');
                    yearsData.data.forEach(year => {
                        startSelect.add(new Option(year, year));
                        endSelect.add(new Option(year, year));
                    });
                    endSelect.value = yearsData.data[yearsData.data.length - 1];
                    currentFilters.endYear = yearsData.data[yearsData.data.length - 1];
                }
            } catch (error) {
                console.error('Error loading filters:', error);
                notifyApp({
                    id: 'global-filter-error',
                    type: 'warning',
                    title: 'Filters unavailable',
                    message: 'Global filters could not be loaded right now. Default page filters will still be used where possible.'
                });
            }
        }
        
        function setupGlobalListeners() {
            const applyBtn = document.getElementById('applyFilters');
            if (applyBtn) {
                applyBtn.addEventListener('click', function() {
                    currentFilters = {
                        province: document.getElementById('globalProvince').value,
                        startYear: parseInt(document.getElementById('globalStartYear').value),
                        endYear: parseInt(document.getElementById('globalEndYear').value)
                    };
                    window.dispatchEvent(new CustomEvent('filtersChanged', { detail: currentFilters }));
                });
            }
        }
        
        function getCurrentFilters() { return currentFilters; }
        
        function notifyApp(options, fallback = {}) {
            const config = typeof options === 'string'
                ? { message: options, ...fallback }
                : { ...(options || {}) };
            const stack = document.getElementById('appNotificationStack');

            if (!stack || typeof bootstrap === 'undefined') {
                return null;
            }

            const type = config.type || 'info';
            const title = config.title || ({
                success: 'Completed',
                warning: 'Check this',
                danger: 'Something went wrong',
                info: 'Update'
            }[type] || 'Update');
            const message = config.message || '';
            const meta = config.meta || ({
                success: 'Success',
                warning: 'Warning',
                danger: 'Attention',
                info: 'Info'
            }[type] || 'Info');
            const delay = Number.isFinite(Number(config.duration)) ? Number(config.duration) : ({
                success: 3600,
                info: 4600,
                warning: 5600,
                danger: 7000
            }[type] || 4600);
            const autohide = config.sticky ? false : config.autohide !== false;
            const iconClass = config.icon || ({
                success: 'fas fa-circle-check',
                warning: 'fas fa-triangle-exclamation',
                danger: 'fas fa-circle-exclamation',
                info: 'fas fa-circle-info'
            }[type] || 'fas fa-circle-info');

            if (config.id) {
                const existing = stack.querySelector(`[data-notification-id="${config.id}"]`);
                if (existing) {
                    const existingToast = bootstrap.Toast.getInstance(existing);
                    if (existingToast) {
                        existingToast.hide();
                    } else {
                        existing.remove();
                    }
                }
            }

            const toast = document.createElement('div');
            toast.className = `toast app-toast app-toast-${type}`;
            toast.role = 'status';
            toast.ariaLive = type === 'danger' ? 'assertive' : 'polite';
            toast.ariaAtomic = 'true';
            if (config.id) {
                toast.dataset.notificationId = config.id;
            }

            const header = document.createElement('div');
            header.className = 'toast-header';

            const icon = document.createElement('div');
            icon.className = 'app-toast-icon';
            icon.innerHTML = `<i class="${iconClass}"></i>`;

            const heading = document.createElement('div');
            heading.className = 'me-auto';

            const metaNode = document.createElement('div');
            metaNode.className = 'app-toast-meta';
            metaNode.textContent = meta;

            const titleNode = document.createElement('div');
            titleNode.className = 'app-toast-title';
            titleNode.textContent = title;

            heading.appendChild(metaNode);
            heading.appendChild(titleNode);

            const closeButton = document.createElement('button');
            closeButton.type = 'button';
            closeButton.className = 'btn-close';
            closeButton.setAttribute('data-bs-dismiss', 'toast');
            closeButton.setAttribute('aria-label', 'Close');

            header.appendChild(icon);
            header.appendChild(heading);
            header.appendChild(closeButton);

            const body = document.createElement('div');
            body.className = 'toast-body';
            body.textContent = message;

            toast.appendChild(header);
            toast.appendChild(body);
            stack.appendChild(toast);

            toast.addEventListener('hidden.bs.toast', function () {
                toast.remove();
            }, { once: true });

            const instance = bootstrap.Toast.getOrCreateInstance(toast, {
                autohide,
                delay
            });
            instance.show();
            return instance;
        }

        window.notifyApp = notifyApp;
        window.notifyApiError = function notifyApiError(context, error, options = {}) {
            const message = options.message || (error && error.message) || 'A request could not be completed.';
            return notifyApp({
                type: 'danger',
                title: options.title || `${context} unavailable`,
                message,
                id: options.id || `${String(context || 'request').toLowerCase().replace(/\s+/g, '-')}-error`,
                sticky: options.sticky || false,
                duration: options.duration
            });
        };
        window.createPageNotifier = function createPageNotifier(pageId) {
            const normalizedPageId = String(pageId || 'page')
                .toLowerCase()
                .replace(/[^a-z0-9]+/g, '-')
                .replace(/^-+|-+$/g, '') || 'page';

            return function pageNotify(type, title, message, options = {}) {
                const normalizedId = options.id
                    ? `${normalizedPageId}-${String(options.id)
                        .toLowerCase()
                        .replace(/[^a-z0-9]+/g, '-')
                        .replace(/^-+|-+$/g, '')}`
                    : undefined;

                return notifyApp({
                    type,
                    title,
                    message,
                    id: normalizedId,
                    duration: options.duration,
                    sticky: options.sticky,
                    meta: options.meta,
                    icon: options.icon
                });
            };
        };

function slugifyExportName(value) {
    return String(value || 'climate-chart')
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '')
        .slice(0, 80) || 'climate-chart';
}

function getChartExportTitle(canvas) {
    const panel = canvas.closest('.chart-card-lg, .chart-card, .projection-panel, .card, section, article');
    const titleNode = panel?.querySelector('.chart-title, h3, h4, .card-title');
    const ariaLabel = canvas.getAttribute('aria-label');
    return (titleNode?.textContent || ariaLabel || canvas.id || 'Climate chart').trim();
}

function getCanvasDataUrl(canvas) {
    const chart = window.Chart && typeof Chart.getChart === 'function'
        ? Chart.getChart(canvas)
        : null;
    if (chart && typeof chart.toBase64Image === 'function') {
        return chart.toBase64Image('image/png', 1);
    }
    return canvas.toDataURL('image/png');
}

function downloadChartCanvas(canvas) {
    try {
        const title = getChartExportTitle(canvas);
        const link = document.createElement('a');
        link.href = getCanvasDataUrl(canvas);
        link.download = `${slugifyExportName(title)}.png`;
        document.body.appendChild(link);
        link.click();
        link.remove();

        if (typeof window.notifyApp === 'function') {
            window.notifyApp({
                id: `chart-export-${canvas.id || slugifyExportName(title)}`,
                type: 'success',
                title: 'Chart exported',
                message: `${title} was downloaded as a PNG image.`,
                duration: 3200,
                meta: 'Export'
            });
        }
    } catch (error) {
        console.error('Chart export failed:', error);
        if (typeof window.notifyApp === 'function') {
            window.notifyApp({
                id: `chart-export-error-${canvas.id || 'canvas'}`,
                type: 'danger',
                title: 'Chart export failed',
                message: 'This chart could not be exported right now.',
                duration: 5000,
                meta: 'Export'
            });
        }
    }
}

function addChartExportButton(canvas) {
    if (!canvas || !canvas.id || canvas.dataset.exportReady === 'true') return;

    const title = getChartExportTitle(canvas);
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'chart-export-button';
    button.setAttribute('aria-label', `Download ${title} as PNG`);
    button.innerHTML = '<i class="fas fa-download" aria-hidden="true"></i><span>PNG</span>';
    button.addEventListener('click', () => downloadChartCanvas(canvas));

    const panel = canvas.closest('.chart-card-lg, .chart-card, .projection-panel, .card, section, article');
    const header = panel?.querySelector('.chart-header, .projection-panel-header, .card-header');

    if (header) {
        header.classList.add('gap-2');
        const toolbar = document.createElement('div');
        toolbar.className = 'chart-export-toolbar';
        toolbar.appendChild(button);
        header.appendChild(toolbar);
    } else {
        const fallback = document.createElement('div');
        fallback.className = 'chart-export-fallback';
        fallback.appendChild(button);
        canvas.parentElement?.insertBefore(fallback, canvas);
    }

    canvas.dataset.exportReady = 'true';
}

function initializeChartExports() {
    document.querySelectorAll('canvas[id]').forEach(addChartExportButton);
}

document.addEventListener('DOMContentLoaded', function() {
    initializeChartExports();
    setTimeout(initializeChartExports, 800);
    setTimeout(initializeChartExports, 2200);

    const observer = new MutationObserver(function(mutations) {
        if (mutations.some(mutation => mutation.addedNodes.length > 0)) {
            initializeChartExports();
        }
    });
    observer.observe(document.body, { childList: true, subtree: true });
});

function formatNumber(value) {
    const numericValue = Number(value);
    return Number.isFinite(numericValue) ? numericValue.toLocaleString() : 'N/A';
}

function buildYearRangeLabel(years) {
    if (!Array.isArray(years) || years.length === 0) return 'No year coverage available';
    const sortedYears = years.map(Number).filter(Number.isFinite).sort((a, b) => a - b);
    if (sortedYears.length === 0) return 'No year coverage available';
    if (sortedYears.length === 1) return `Data coverage: ${sortedYears[0]}`;
    return `Data coverage: ${sortedYears[0]}-${sortedYears[sortedYears.length - 1]}`;
}

function updateFooterCoverage({ totalRecords, provinces, years }) {
    const recordNode = document.getElementById('footerRecordCount');
    const provinceNode = document.getElementById('footerProvinceCount');
    const yearNode = document.getElementById('footerYearCoverage');

    if (recordNode) {
        recordNode.textContent = Number.isFinite(Number(totalRecords))
            ? `${formatNumber(totalRecords)} Records`
            : 'Records unavailable';
    }

    if (provinceNode) {
        provinceNode.textContent = Array.isArray(provinces)
            ? `${provinces.length} Provinces`
            : 'Provinces unavailable';
    }

    if (yearNode) {
        const label = buildYearRangeLabel(years);
        yearNode.textContent = label.startsWith('Data coverage: ')
            ? label.replace('Data coverage: ', '')
            : label;
    }
}

function updateLiveClock() {
    const fullClockNode = document.getElementById('liveClockFull');
    const compactClockNode = document.getElementById('liveClockCompact');
    if (!fullClockNode || !compactClockNode) return;
    const now = new Date();
    const datePart = new Intl.DateTimeFormat(undefined, {
        weekday: 'short',
        month: 'short',
        day: 'numeric'
    }).format(now);
    const timePart = new Intl.DateTimeFormat(undefined, {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    }).format(now);
    const compactTime = new Intl.DateTimeFormat(undefined, {
        hour: '2-digit',
        minute: '2-digit'
    }).format(now);
    fullClockNode.textContent = `${datePart} ${timePart}`;
    compactClockNode.textContent = compactTime;
}

function syncSidebarLayout() {
    const appShell = document.getElementById('appShell');
    const appSidebar = document.getElementById('appSidebar');
    const sidebarPinned = document.getElementById('sidebarPinned');
    if (!appShell || !appSidebar) return;

    const mobile = window.innerWidth <= 991;
    const isExpandedDesktop = !mobile && Boolean(sidebarPinned?.checked);

    appShell.classList.toggle('sidebar-expanded', isExpandedDesktop);
    appShell.classList.toggle('sidebar-open', mobile && appSidebar.classList.contains('is-open'));
}

function applySidebarPinnedState(isPinned) {
    const appSidebar = document.getElementById('appSidebar');
    const sidebarPinned = document.getElementById('sidebarPinned');
    if (!appSidebar || !sidebarPinned) return;
    sidebarPinned.checked = Boolean(isPinned);
    appSidebar.classList.toggle('is-expanded', Boolean(isPinned));
    syncSidebarLayout();
}

let siteSummaryRequest = {};
let liveWeatherRequest = null;
let viewerCoordinatesRequest = null;
let geolocationPermissionDenied = false;
let viewerLocationStatus = {
    code: 'idle',
    message: 'Waiting for browser location access.'
};

function setViewerLocationStatus(code, message) {
    viewerLocationStatus = { code, message };
    return viewerLocationStatus;
}

function getViewerLocationStatus() {
    return viewerLocationStatus;
}

function normalizeViewerCoordinates(coords) {
    if (!coords) return null;
    const latitude = Number(coords.latitude);
    const longitude = Number(coords.longitude);

    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
        return null;
    }

    if (latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) {
        return null;
    }

    return {
        latitude: Number(latitude.toFixed(6)),
        longitude: Number(longitude.toFixed(6))
    };
}

function buildViewerLocationKey(coords) {
    const normalized = normalizeViewerCoordinates(coords);
    if (!normalized) return null;
    return `${normalized.latitude.toFixed(3)},${normalized.longitude.toFixed(3)}`;
}

function buildSiteSummaryCacheKey(coords = null) {
    const locationKey = buildViewerLocationKey(coords);
    return locationKey
        ? `${SITE_SUMMARY_CACHE_KEY}:${locationKey}`
        : SITE_SUMMARY_CACHE_KEY;
}

function getStoredViewerCoordinates() {
    try {
        const raw = localStorage.getItem(VIEWER_COORDINATES_KEY);
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        if (!parsed || !parsed.coords || !parsed.savedAt) return null;
        if ((Date.now() - Number(parsed.savedAt)) > VIEWER_COORDINATES_MAX_AGE_MS) {
            return null;
        }
        return normalizeViewerCoordinates(parsed.coords);
    } catch (error) {
        console.warn('Unable to read stored viewer coordinates:', error);
        return null;
    }
}

function storeViewerCoordinates(coords) {
    const normalized = normalizeViewerCoordinates(coords);
    if (!normalized) return;

    try {
        localStorage.setItem(VIEWER_COORDINATES_KEY, JSON.stringify({
            savedAt: Date.now(),
            coords: normalized
        }));
    } catch (error) {
        console.warn('Unable to store viewer coordinates:', error);
    }
}

function requestCurrentBrowserCoordinates() {
    if (window.isSecureContext === false) {
        setViewerLocationStatus(
            'insecure-context',
            'Current location needs HTTPS or localhost in most browsers.'
        );
        return Promise.resolve(null);
    }

    if (!navigator.geolocation) {
        setViewerLocationStatus(
            'unsupported',
            'This browser does not support current location access.'
        );
        return Promise.resolve(null);
    }

    setViewerLocationStatus('prompting', 'Waiting for browser location permission.');
    return new Promise((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(
            (position) => {
                setViewerLocationStatus('available', 'Current location is available.');
                resolve(normalizeViewerCoordinates({
                    latitude: position.coords.latitude,
                    longitude: position.coords.longitude
                }));
            },
            reject,
            {
                enableHighAccuracy: false,
                timeout: 8000,
                maximumAge: 120000
            }
        );
    });
}

async function getPreferredViewerCoordinates(options = {}) {
    const forceRefresh = Boolean(options && options.forceRefresh);
    const storedCoords = getStoredViewerCoordinates();

    if (geolocationPermissionDenied && !forceRefresh) {
        setViewerLocationStatus(
            storedCoords ? 'cached-after-denied' : 'permission-denied',
            storedCoords
                ? 'Using the last saved location because browser location access was denied.'
                : 'Browser location access was denied.'
        );
        return storedCoords;
    }

    if (viewerCoordinatesRequest) {
        return viewerCoordinatesRequest;
    }

    viewerCoordinatesRequest = (async () => {
        try {
            const currentCoords = await requestCurrentBrowserCoordinates();
            if (currentCoords) {
                storeViewerCoordinates(currentCoords);
                geolocationPermissionDenied = false;
                return currentCoords;
            }
        } catch (error) {
            if (error && Number(error.code) === 1) {
                geolocationPermissionDenied = true;
                setViewerLocationStatus('permission-denied', 'Browser location access was denied.');
            } else if (error && Number(error.code) === 2) {
                setViewerLocationStatus('position-unavailable', 'The browser could not determine this location.');
            } else if (error && Number(error.code) === 3) {
                setViewerLocationStatus('timeout', 'Current location lookup timed out.');
            } else {
                setViewerLocationStatus('unavailable', 'Current location is unavailable right now.');
            }
            console.warn('Viewer geolocation unavailable:', error);
        }

        if (storedCoords) {
            setViewerLocationStatus('cached', 'Using the last saved browser location.');
        }
        return storedCoords;
    })();

    try {
        return await viewerCoordinatesRequest;
    } finally {
        viewerCoordinatesRequest = null;
    }
}

function getStoredLiveWeather(locationKey) {
    if (!locationKey) return null;

    try {
        const raw = localStorage.getItem(LIVE_WEATHER_CACHE_KEY);
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        if (
            parsed &&
            parsed.locationKey === locationKey &&
            parsed.expiresAt > Date.now() &&
            parsed.data
        ) {
            return parsed.data;
        }
    } catch (error) {
        console.warn('Unable to read cached live weather:', error);
    }

    return null;
}

async function getCachedLiveWeather(coords, options = {}) {
    const normalized = normalizeViewerCoordinates(coords);
    if (!normalized) return null;

    const forceRefresh = Boolean(options && options.forceRefresh);
    const locationKey = buildViewerLocationKey(normalized);
    const stored = getStoredLiveWeather(locationKey);
    if (stored && !forceRefresh) {
        return stored;
    }

    if (liveWeatherRequest && liveWeatherRequest.locationKey === locationKey) {
        return liveWeatherRequest.promise;
    }

    const params = new URLSearchParams({
        lat: String(normalized.latitude),
        lon: String(normalized.longitude)
    });

    const promise = (async () => {
        const response = await fetch(`/api/v1/live-weather?${params.toString()}`);
        const payload = await response.json();
        if (!payload.success) {
            throw new Error(payload.error || 'Failed to load live weather');
        }

        try {
            localStorage.setItem(LIVE_WEATHER_CACHE_KEY, JSON.stringify({
                locationKey,
                expiresAt: Date.now() + LIVE_WEATHER_CACHE_TTL_MS,
                data: payload.data
            }));
        } catch (error) {
            console.warn('Unable to cache live weather:', error);
        }

        return payload.data;
    })();

    liveWeatherRequest = {
        locationKey,
        promise
    };

    try {
        return await promise;
    } finally {
        if (liveWeatherRequest && liveWeatherRequest.locationKey === locationKey) {
            liveWeatherRequest = null;
        }
    }
}

async function getLiveWeatherForViewer(options = {}) {
    const coords = await getPreferredViewerCoordinates(options);
    if (!coords) {
        return null;
    }

    try {
        return await getCachedLiveWeather(coords, options);
    } catch (error) {
        console.warn('Live weather refresh unavailable:', error);
        return null;
    }
}

window.getLiveWeatherForViewer = getLiveWeatherForViewer;
window.getViewerLocationStatus = getViewerLocationStatus;

const GLOBAL_NAV_TARGETS = [
    { label: 'Home', url: '/', terms: ['home', 'start'] },
    { label: 'Overview', url: '/overview', terms: ['overview', 'dashboard', 'summary'] },
    { label: 'Interactive Map', url: '/interactive-map', terms: ['map', 'district map', 'location'] },
    { label: 'Flood Events', url: '/flood-events', terms: ['flood', 'floods', 'events'] },
    { label: 'Temperature', url: '/temperature', terms: ['temperature', 'heat', 'temp'] },
    { label: 'Rainfall', url: '/rainfall', terms: ['rainfall', 'rain', 'precipitation'] },
    { label: 'Drought Indicators', url: '/drought', terms: ['drought', 'dry', 'spi', 'spei'] },
    { label: 'Projections', url: '/projections', terms: ['projection', 'projections', 'forecast', 'future'] },
    { label: 'Impact Analysis', url: '/impacts', terms: ['impact', 'impacts', 'stress'] },
    { label: 'District Comparison', url: '/comparison', terms: ['comparison', 'compare', 'rankings'] },
    { label: 'Data Explorer', url: '/data-explorer', terms: ['data', 'explorer', 'records', 'table'] },
    { label: 'About', url: '/about', terms: ['about', 'sources', 'methodology'] }
];

function normalizeNavSearchText(value) {
    return String(value || '').toLowerCase().trim();
}

async function buildGlobalNavSearchIndex() {
    const index = GLOBAL_NAV_TARGETS.map(item => ({
        type: 'page',
        label: item.label,
        url: item.url,
        terms: [item.label, item.url, ...(item.terms || [])].map(normalizeNavSearchText)
    }));

    try {
        const response = await fetch('/api/v1/district-directory');
        const payload = await response.json();
        const rows = Array.isArray(payload?.data) ? payload.data : [];
        const provinces = new Set();

        rows.forEach(item => {
            const district = String(item?.district || '').trim();
            const province = String(item?.province || '').trim();
            if (!district || !province) return;
            provinces.add(province);
            index.push({
                type: 'district',
                label: `${district} District`,
                url: `/interactive-map?district=${encodeURIComponent(district)}`,
                terms: [district, `${district} district`, `${district} ${province}`, province].map(normalizeNavSearchText)
            });
        });

        provinces.forEach(province => {
            index.push({
                type: 'province',
                label: `${province} Province`,
                url: `/interactive-map?province=${encodeURIComponent(province)}`,
                terms: [province, `${province} province`].map(normalizeNavSearchText)
            });
        });
    } catch (error) {
        console.warn('Navigation search district index unavailable:', error);
    }

    return index;
}

function pickGlobalNavSearchResult(index, query) {
    const normalized = normalizeNavSearchText(query);
    if (!normalized) return null;
    return index.find(item => item.terms.includes(normalized))
        || index.find(item => item.terms.some(term => term.startsWith(normalized)))
        || index.find(item => item.terms.some(term => term.includes(normalized)))
        || null;
}

async function initializeGlobalNavSearch() {
    const form = document.getElementById('globalNavSearchForm');
    const input = document.getElementById('globalNavSearchInput');
    const suggestions = document.getElementById('globalNavSearchSuggestions');
    if (!form || !input) return;

    const index = await buildGlobalNavSearchIndex();
    if (suggestions) {
        suggestions.innerHTML = '';
        index.slice(0, 220).forEach(item => {
            const option = document.createElement('option');
            option.value = item.label;
            suggestions.appendChild(option);
        });
    }

    form.addEventListener('submit', event => {
        event.preventDefault();
        const result = pickGlobalNavSearchResult(index, input.value);
        if (result) {
            window.location.href = result.url;
            return;
        }
        const fallback = input.value.trim();
        if (fallback) {
            window.location.href = `/interactive-map?district=${encodeURIComponent(fallback)}`;
        }
    });
}

// Dynamic ticker that fetches real climate alerts
const TICKER_CATEGORY_META = {
    alert: { icon: '⚠️', link: '/interactive-map' },
    weather: { icon: '🌧️', link: '/interactive-map' },
    stat: { icon: '📊', link: '/data-explorer' },
    tip: { icon: '💡', link: '/projections' },
    info: { icon: '📌', link: '/overview' }
};

function createTickerEntry(text, category = 'info', href = null) {
    return {
        text: String(text).trim(),
        category,
        icon: TICKER_CATEGORY_META[category]?.icon || '📌',
        href: href || getTickerTargetUrl(String(text))
    };
}

function getTickerTargetUrl(message) {
    const text = String(message).toLowerCase();
    if (/impact|affected|population|food price|crop yield|hydropower|livestock|lake kariba|electricity/.test(text)) return '/impacts';
    if (/rain|flood|wet|water level/.test(text)) return '/rainfall';
    if (/temperature|hot|cold|heat|°c/.test(text)) return '/temperature';
    if (/drought|dry|crop loss/.test(text)) return '/drought';
    if (/ndvi|vegetation|health/.test(text)) return '/data-explorer';
    if (/district|province|map|feed/.test(text)) return '/interactive-map';
    if (/projection|future|forecast/.test(text)) return '/projections';
    return '/overview';
}

function chooseTickerCategory(message) {
    const text = String(message).toLowerCase();
    if (/impact|affected|population|food price|crop yield|hydropower|livestock|electricity/.test(text)) {
        return /warning|risk|severe|extreme|low|high/.test(text) ? 'alert' : 'stat';
    }
    if (/warning|risk|alert|severe|extreme|low|high|rain|flood|drought|heat/.test(text)) {
        return /rain|flood|water level/.test(text) ? 'weather' : 'alert';
    }
    if (/average|records|trend|data|coverage|province|year|ndvi|temperature|rainfall|drought/.test(text)) {
        return 'stat';
    }
    return 'tip';
}

function buildTickerAlerts(summary) {
    const availableYears = summary && Array.isArray(summary.years) ? summary.years : [];
    const sharedTickerItems = summary && Array.isArray(summary.ticker_items)
        ? summary.ticker_items.filter(item => typeof item === 'string' && item.trim())
        : [];
    const alerts = [];
    const liveWeatherItems = summary && summary.live_weather
        ? getLiveWeatherTickerItems(summary.live_weather)
        : [];
    const impactTickerItems = sharedTickerItems.filter(text => /impact|affected|population|food price|crop yield|hydropower|livestock|electricity/i.test(text));
    const otherTickerItems = sharedTickerItems.filter(text => !/impact|affected|population|food price|crop yield|hydropower|livestock|electricity/i.test(text));

    liveWeatherItems.slice(0, 3).forEach(text => {
        alerts.push(createTickerEntry(text, 'weather', '/interactive-map'));
    });

    impactTickerItems.slice(0, 2).forEach(text => {
        alerts.push(createTickerEntry(text, chooseTickerCategory(text), '/impacts'));
    });

    if (otherTickerItems.length > 0) {
        otherTickerItems.slice(0, 3).forEach(text => {
            alerts.push(createTickerEntry(text, chooseTickerCategory(text)));
        });
    } else if (sharedTickerItems.length === 0) {
        const sortedYears = availableYears.map(Number).filter(Number.isFinite).sort((a, b) => b - a);
        const summaries = summary && Array.isArray(summary.yearly_summaries) ? summary.yearly_summaries : [];

        summaries.slice(0, 2).forEach(item => {
            const topRain = Array.isArray(item.rainfall) ? item.rainfall[0] : null;
            const topDrought = Array.isArray(item.drought) ? item.drought[0] : null;
            const topTemp = Array.isArray(item.temperature) ? item.temperature[0] : null;
            const topNdvi = Array.isArray(item.ndvi) ? item.ndvi[0] : null;

            if (topRain) {
                alerts.push(createTickerEntry(
                    `Rainfall: ${topRain.province} recorded the highest average rainfall at ${topRain.value} mm`,
                    'stat'
                ));
            }
            if (topTemp) {
                alerts.push(createTickerEntry(
                    `Temperature: ${topTemp.province} recorded the highest average maximum temperature at ${topTemp.value} C`,
                    'stat'
                ));
            }
            if (topDrought) {
                const droughtLabel = topDrought.value > 1.3 ? 'severe drought pressure' : 'the highest drought pressure';
                alerts.push(createTickerEntry(
                    `Drought: ${topDrought.province} had ${droughtLabel} with a score of ${topDrought.value}`,
                    'alert'
                ));
            }
            if (topNdvi) {
                alerts.push(createTickerEntry(
                    `NDVI: ${topNdvi.province} showed the strongest vegetation health with NDVI ${topNdvi.value}`,
                    'stat'
                ));
            }
        });

        if (summary && summary.latest_year) {
            alerts.push(createTickerEntry(
                `${formatNumber(summary.total_records)} climate readings are available for ${summary.latest_year}`,
                'stat',
                '/data-explorer'
            ));
        }

        alerts.push(createTickerEntry(buildYearRangeLabel(sortedYears), 'info'));
    }

    const sortedCoverageYears = availableYears.map(Number).filter(Number.isFinite).sort((a, b) => a - b);
    const coverageTickerText = sortedCoverageYears.length > 0
        ? `Climate information currently covers ${sortedCoverageYears[0]} to ${sortedCoverageYears[sortedCoverageYears.length - 1]}`
        : 'Climate coverage is loading';

    const navigationItems = [
        createTickerEntry('Explore projections for your district using the Projections tab', 'tip', '/projections'),
        createTickerEntry(coverageTickerText, 'info', '/overview'),
        createTickerEntry('Compare rainfall and temperature trends in the Data Explorer', 'tip', '/data-explorer')
    ];

    const finalAlerts = alerts.concat(navigationItems).slice(0, 8);
    return {
        alerts: finalAlerts,
        availableYears
    };
}

function createTickerItem(item) {
    const entry = document.createElement('span');
    entry.className = `ticker-item ticker-${item.category}`;
    entry.textContent = `${item.icon} ${item.text}`;

    return entry;
}

function renderTickerAlerts(alerts) {
    const tickerContent = document.getElementById('tickerContent');
    if (!tickerContent) return;

    tickerContent.innerHTML = '';
    const shouldUseStaticTicker = alerts.length <= 1;
    tickerContent.classList.toggle('static', shouldUseStaticTicker);

    const scroll = document.createElement('div');
    scroll.className = 'ticker-scroll';
    alerts.forEach(item => scroll.appendChild(createTickerItem(item)));
    tickerContent.appendChild(scroll);

    if (!shouldUseStaticTicker) {
        tickerContent.appendChild(scroll.cloneNode(true));
    }

    const desktopDuration = Math.max(36, Math.min(60, alerts.length * 7 + 20));
    const mobileDuration = Math.max(44, desktopDuration + 10);
    tickerContent.style.setProperty('--ticker-duration', `${desktopDuration}s`);
    tickerContent.style.setProperty('--ticker-duration-mobile', `${mobileDuration}s`);

    if (alerts.length === 0) {
        tickerContent.innerHTML = '';
        tickerContent.appendChild(createTickerItem({ text: 'No climate updates are available right now.', category: 'info' }));
    }
}

function getLiveWeatherTickerItems(liveWeather) {
    return liveWeather && Array.isArray(liveWeather.ticker_items)
        ? liveWeather.ticker_items.filter(item => typeof item === 'string' && item.trim())
        : [];
}

function getLiveWeatherFallbackTickerItems(liveWeather) {
    if (getLiveWeatherTickerItems(liveWeather).length > 0) {
        return [];
    }

    return [
        'Live weather will appear in Climate Updates after browser location access is allowed.'
    ];
}

function renderTickerFromSummary(summary, liveWeather = null) {
    if (!summary) return false;

    const summaryWithWeather = {
        ...summary,
        live_weather: liveWeather || summary.live_weather
    };
    const { alerts, availableYears } = buildTickerAlerts(summaryWithWeather);

    updateFooterCoverage({
        totalRecords: summary.total_records,
        provinces: summary.provinces,
        years: availableYears
    });

    renderTickerAlerts(alerts);
    return true;
}

function getStoredSiteSummary(coords = null) {
    try {
        const raw = localStorage.getItem(buildSiteSummaryCacheKey(coords));
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        return parsed && parsed.data ? parsed.data : null;
    } catch (error) {
        console.warn('Unable to read stored site summary:', error);
        return null;
    }
}

async function updateTicker() {
    let viewerCoords = null;
    try {
        viewerCoords = await getPreferredViewerCoordinates();
        const summary = await getCachedSiteSummary(viewerCoords);
        renderTickerFromSummary(summary);
        window.dispatchEvent(new CustomEvent('liveWeatherUpdated', { detail: summary?.live_weather || null }));

        return; /*

        const yearsRes = await fetch('/api/v1/years');
        const yearsData = await yearsRes.json();
        const availableYears = yearsData.success ? yearsData.data : [];
        const sortedYears = Array.isArray(availableYears)
            ? availableYears.map(Number).filter(Number.isFinite).sort((a, b) => b - a)
            : [];
        const tickerYears = sortedYears.slice(0, 3);
        const latestYear = sortedYears.length > 0 ? sortedYears[0] : 2024;
        const provincesRes = await fetch('/api/v1/provinces');
        const provincesData = await provincesRes.json();
        const provinces = provincesData.success ? provincesData.data : [];

        const alerts = [];

        const yearlyTickerResponses = await Promise.all(
            tickerYears.map(async (year) => {
                const [rainRes, droughtRes, tempRes, ndviRes] = await Promise.all([
                    fetch(`/api/v1/rankings/rainfall?year=${year}`),
                    fetch(`/api/v1/rankings/drought?year=${year}`),
                    fetch(`/api/v1/rankings/temperature?year=${year}`),
                    fetch(`/api/v1/rankings/ndvi?year=${year}`)
                ]);

                const [rainData, droughtData, tempData, ndviData] = await Promise.all([
                    rainRes.json(),
                    droughtRes.json(),
                    tempRes.json(),
                    ndviRes.json()
                ]);

                const topRain = rainData.success && rainData.data.rankings ? rainData.data.rankings[0] : null;
                const topDrought = droughtData.success && droughtData.data.rankings ? droughtData.data.rankings[0] : null;
                const topTemp = tempData.success && tempData.data.rankings ? tempData.data.rankings[0] : null;
                const topNdvi = ndviData.success && ndviData.data.rankings ? ndviData.data.rankings[0] : null;
                const messages = [];

                messages.push(`${year} climate summary`);

                if (topRain) {
                    messages.push(`Rainfall: ${topRain.province} recorded the highest average rainfall at ${topRain.value} mm`);
                }

                if (topTemp) {
                    messages.push(`Temperature: ${topTemp.province} recorded the highest average maximum temperature at ${topTemp.value}°C`);
                }

                if (topDrought) {
                    const droughtLabel = topDrought.value > 1.3 ? 'severe drought pressure' : 'the highest drought pressure';
                    messages.push(`Drought: ${topDrought.province} had ${droughtLabel} with a score of ${topDrought.value}`);
                }

                if (topNdvi) {
                    messages.push(`NDVI: ${topNdvi.province} showed the strongest vegetation health with NDVI ${topNdvi.value}`);
                }

                if (messages.length === 1) {
                    messages.push(`No ranking data was available for this year`);
                }

                return messages;
            })
        );

        alerts.push(...yearlyTickerResponses.flat());

        const overviewRes = await fetch(`/api/v1/overview?year=${latestYear}`);
        const overviewData = await overviewRes.json();
        if (overviewData.success && overviewData.data) {
            alerts.push(`${formatNumber(overviewData.data.total_records)} climate readings are available for ${latestYear}`);
            updateFooterCoverage({
                totalRecords: overviewData.data.total_records,
                provinces,
                years: availableYears
            });
        }

        alerts.push(buildYearRangeLabel(sortedYears));
        
        // Update ticker
        const tickerContent = document.getElementById('tickerContent');
        if (tickerContent && alerts.length > 0) {
            const desktopDuration = Math.max(120, alerts.length * 14);
            const mobileDuration = Math.max(140, alerts.length * 17);
            let html = '';
            alerts.forEach(alert => {
                html += `<span class="ticker-item">${alert}</span>`;
            });
            tickerContent.innerHTML = html;
            tickerContent.style.setProperty('--ticker-duration', `${desktopDuration}s`);
            tickerContent.style.setProperty('--ticker-duration-mobile', `${mobileDuration}s`);
        } else if (tickerContent) {
            tickerContent.innerHTML = '<span class="ticker-item">No climate updates are available right now.</span>';
            tickerContent.style.setProperty('--ticker-duration', '120s');
            tickerContent.style.setProperty('--ticker-duration-mobile', '140s');
        }
        
        */
    } catch (error) {
        console.warn('Climate update ticker refresh skipped:', error);
        window.dispatchEvent(new CustomEvent('liveWeatherUpdated', { detail: null }));

        const storedSummary = getStoredSiteSummary(viewerCoords) || getStoredSiteSummary(null);
        if (storedSummary && renderTickerFromSummary(storedSummary)) {
            return;
        }

        const tickerContent = document.getElementById('tickerContent');
        if (tickerContent) {
            tickerContent.innerHTML = '<span class="ticker-item">Unable to load climate updates right now.</span>';
            tickerContent.style.setProperty('--ticker-duration', '120s');
            tickerContent.style.setProperty('--ticker-duration-mobile', '140s');
        }
    }
}

async function getCachedSiteSummary(coords = null) {
    const normalizedCoords = normalizeViewerCoordinates(coords);
    const cacheKey = buildSiteSummaryCacheKey(normalizedCoords);

    try {
        const raw = localStorage.getItem(cacheKey);
        if (raw) {
            const parsed = JSON.parse(raw);
            if (parsed.expiresAt > Date.now() && parsed.data) {
                return parsed.data;
            }
        }
    } catch (error) {
        console.warn('Unable to read cached site summary:', error);
    }

    if (siteSummaryRequest[cacheKey]) {
        return siteSummaryRequest[cacheKey];
    }

    siteSummaryRequest[cacheKey] = (async () => {
        const params = normalizedCoords
            ? `?${new URLSearchParams({
                lat: String(normalizedCoords.latitude),
                lon: String(normalizedCoords.longitude)
            }).toString()}`
            : '';
        const response = await fetch(`/api/v1/site-summary${params}`);
        const payload = await response.json();
        if (!payload.success) {
            throw new Error(payload.error || 'Failed to load site summary');
        }

        try {
            localStorage.setItem(cacheKey, JSON.stringify({
                expiresAt: Date.now() + SITE_SUMMARY_CACHE_TTL_MS,
                data: payload.data
            }));
        } catch (error) {
            console.warn('Unable to cache site summary:', error);
        }

        return payload.data;
    })();

    try {
        return await siteSummaryRequest[cacheKey];
    } finally {
        delete siteSummaryRequest[cacheKey];
    }
}

// Initialize layout on page load
document.addEventListener('DOMContentLoaded', function() {
            purgeLegacyPortalCaches();
            initializeGlobalNavSearch();
            updateLiveClock();
            setInterval(updateLiveClock, 1000);
            const appShell = document.getElementById('appShell');
    const appSidebar = document.getElementById('appSidebar');
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebarPinned = document.getElementById('sidebarPinned');

    if (sidebarToggle && appSidebar) {
        sidebarToggle.addEventListener('click', function() {
            appSidebar.classList.toggle('is-open');
            syncSidebarLayout();
        });
    }

    if (sidebarPinned && appShell && appSidebar) {
        const savedPinned = localStorage.getItem(SIDEBAR_PINNED_KEY) === 'true';
        applySidebarPinnedState(savedPinned);
        sidebarPinned.addEventListener('change', function() {
            localStorage.setItem(SIDEBAR_PINNED_KEY, String(sidebarPinned.checked));
            applySidebarPinnedState(sidebarPinned.checked);
        });
    }

    if (appSidebar) {
        appSidebar.addEventListener('mouseenter', syncSidebarLayout);
        appSidebar.addEventListener('mouseleave', syncSidebarLayout);
        appSidebar.addEventListener('transitionend', syncSidebarLayout);
    }

    document.addEventListener('click', function(event) {
        if (window.innerWidth > 991) return;
        if (!appSidebar || !sidebarToggle) return;
        if (appSidebar.contains(event.target) || sidebarToggle.contains(event.target)) return;
        appSidebar.classList.remove('is-open');
        syncSidebarLayout();
    });

    window.addEventListener('resize', syncSidebarLayout);
    syncSidebarLayout();

    const cachedSummary = getStoredSiteSummary(getStoredViewerCoordinates()) || getStoredSiteSummary();
    const hasInstantTicker = renderTickerFromSummary(cachedSummary);

    if (hasInstantTicker) {
        setTimeout(updateTicker, 0);
    } else {
        // Defer ticker fetch to let the page content render first.
        setTimeout(updateTicker, 600);
    }

    // Refresh every 5 minutes
    setInterval(updateTicker, 300000);
});