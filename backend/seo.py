"""Per-page SEO copy shared by the app, sitemap and llms.txt."""

SITE_NAME = "Zambia Climate Portal"

# Per-page SEO copy. Keyed by URL path; used by base.html for meta description,
# Open Graph tags, breadcrumbs and the sitemap. Keep descriptions under ~160 chars.
PAGE_META = {
    "/": ("Home", "Explore Zambia's rainfall, temperature, drought and flood data by district and province, with 2015-2025 records, maps and projections."),
    "/overview": ("Climate Overview", "National overview of Zambia's climate: key rainfall, temperature and drought indicators with filters by province and year."),
    "/interactive-map": ("Interactive Map", "Interactive district map of Zambia showing rainfall, temperature and climate risk, with filters by year and indicator."),
    "/flood-events": ("Flood Events", "Flood events in Zambia by district and year: frequency, severity and the areas most often affected."),
    "/temperature": ("Temperature", "Temperature trends across Zambia's provinces and districts, including averages, extremes and long-term change."),
    "/rainfall": ("Rainfall", "Rainfall patterns in Zambia by month, season, district and province, with year-on-year comparison charts."),
    "/drought": ("Drought Indicators", "Drought indicators for Zambia: dry spells, rainfall deficits and the districts most exposed to drought risk."),
    "/projections": ("Projections", "Projected climate trends for Zambia's rainfall and temperature, built from the portal's historical record."),
    "/impacts": ("Impact Analysis", "How climate conditions affect agriculture, food prices and communities across Zambia's districts."),
    "/comparison": ("District Comparison", "Rank and compare Zambia's districts on rainfall, temperature and climate risk side by side."),
    "/data-explorer": ("Data Explorer", "Filter, browse and download Zambia climate records by province, district, year and month."),
    "/about": ("About", "About the Zambia Climate Data Visualization Portal: purpose, data sources, methods and the people behind the project."),
    "/privacy": ("Privacy Policy", "How the Zambia Climate Portal handles visitor information, cookies and third-party services."),
}
