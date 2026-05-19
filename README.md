# Climate Data Visualization Portal

## Problem Statement

Researchers, policymakers, and the public lack accessible platforms to analyze and interpret climate data. This limits evidence-based decision-making, public awareness, and planning for climate risks.

## Objectives

- Create an online portal that aggregates climate data relevant to Zambia, including temperature, rainfall, drought indicators, and extreme weather events.
- Develop visualization tools to display trends, projections, and potential impacts in an understandable format.
- Provide user-friendly interfaces for non-experts to explore and use climate information.

## What The Portal Provides

- Overview page with key indicators, charts, rankings, and dataset coverage.
- Interactive district map for exploring climate conditions by location and year.
- Rainfall, temperature, drought, flood, extreme events, impacts, and comparison pages.
- Climate projection page with historical trends, RCP-style scenario bands, and 2030/2050/2100 planning outlooks.
- Data explorer with filters, summary statistics, charts, tables, CSV export, and PNG chart downloads.
- JSON API endpoints for reusable climate summaries and visualizations.

## Main Pages

- `/` - Home page
- `/overview` - Climate overview snapshot
- `/dashboard` - Legacy alias for the overview page
- `/interactive-map` - District map exploration
- `/rainfall` - Rainfall analysis
- `/temperature` - Temperature analysis
- `/drought` - Drought indicators
- `/projections` - RCP-style planning projections
- `/flood-events` - Flood event signals
- `/extreme-events` - Extreme weather event signals
- `/impacts` - Climate-linked impacts
- `/comparison` - District comparison
- `/data-explorer` - Filtered data exploration
- `/about` - Methodology and project information
- `/api/v1/docs` - API route catalog

## Data Coverage

The project uses Zambia climate records covering 2015-2025. The dataset includes geography, year/month, rainfall, temperature, drought severity, vegetation, soil moisture, and climate-linked impact indicators.

See `DATASET_SPECIFICATION.md` for the expected schema and data quality notes.

## Projection Method

The projections page combines historical annual trends with RCP-style planning assumptions for moderate and high emissions pathways. It is meant for awareness and planning demonstrations, not official meteorological forecasting or IPCC model output.

Projection indicators include:

- Average rainfall
- Average maximum temperature
- Average drought severity score
- Population affected

## Local Setup

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
python scripts\init_db.py
python scripts\migrate_data_fixed.py
python app.py
```

The app runs at:

```text
http://localhost:5000
```

## Build Data From Free Sources

The portal can generate a schema-compatible CSV from free public sources using Zambia district boundaries and the Open-Meteo historical archive:

```powershell
python scripts\build_free_source_dataset.py --start-year 2015 --end-year 2025 --output data\processed\free_sources_zambia_climate_data.csv
python scripts\migrate_data_fixed.py data\processed\free_sources_zambia_climate_data.csv
```

Open-Meteo may rate-limit full-country runs. The builder caches successful district downloads in `data/raw/free_source_cache`, so rerunning resumes from cache. For gentler batches:

```powershell
python scripts\build_free_source_dataset.py --start-year 2015 --end-year 2025 --max-new-requests 10 --sleep-seconds 5 --output data\processed\free_sources_zambia_climate_data.csv
```

To fetch additional free context datasets:

```powershell
python scripts\fetch_free_context_sources.py
```

This attempts WFP/HDX food prices and ReliefWeb climate-event reports, and writes a `data/raw/free_source_manifest.json` file listing automated and manual enrichment sources. MODIS NDVI, FAOSTAT, and World Bank CCKP remain source targets that usually require separate API workflows or account-backed tools such as Google Earth Engine.

For a quick test, limit the run to a few districts:

```powershell
python scripts\build_free_source_dataset.py --start-year 2024 --end-year 2024 --limit-districts 2 --output data\processed\free_sources_sample_2024.csv
```

This fills rainfall, temperature, humidity, evapotranspiration, wind, solar radiation, soil moisture, and computed drought indicators. NDVI, food prices, crop yield, hydropower, and event impacts should be enriched from MODIS, WFP/HDX, FAOSTAT, World Bank, and ReliefWeb sources.

## Daily District Weather Updates

Daily updates can be fetched into the same `climate_records` table used by the portal. Put the weather key in `.env` as `DAILY_WEATHER_API_KEY` or reuse `LIVE_WEATHER_API_KEY`; do not place keys in source files.

```powershell
python scripts\update_daily_weather.py --limit-districts 2
python scripts\update_daily_weather.py
```

Each run writes CSV snapshots to `data\processed\daily_weather_updates\` and upserts rows by `date + province + district`, so rerunning updates the same day instead of creating duplicates. The default endpoint is OpenWeather current weather; set `DAILY_WEATHER_API_URL` if you use another compatible current-weather endpoint.

## Testing

```powershell
python -m unittest discover -s tests
```

## Key Technologies

- Flask
- PostgreSQL
- Pandas
- Bootstrap
- Chart.js
- Leaflet

## Project Value

This portal turns climate records into accessible visual information. It helps users compare districts, inspect trends, understand drought and flood signals, and connect climate conditions to practical impacts such as population affected, crop yield, and hydropower.
