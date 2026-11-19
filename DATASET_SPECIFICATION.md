# Dataset Specification

This document defines the dataset required by the Climate Data Visualization Portal so the system can load data, populate filters, render charts, and generate climate and impact insights successfully.

## Purpose

The portal expects climate records at `date + province + district` level. Each row represents one reporting record for a district in a given month or date. The system reads these records from the `climate_records` table and uses them across the dashboard, rainfall, temperature, drought, flood, rankings, explorer, interactive map, and impact pages.

## Minimum Required Fields

These fields are required for the application to function reliably:

| Field | Type | Required | Purpose |
|---|---|---:|---|
| `date` | `DATE` | Yes | Primary time reference for all records |
| `year` | `INTEGER` | Yes | Used for filtering and yearly trend analysis |
| `month` | `INTEGER` | Yes | Used for monthly trend analysis |
| `province` | `VARCHAR(100)` | Yes | Province filter and province rankings |
| `district` | `VARCHAR(100)` | Yes | District filter, district comparison, map analysis |

If any of these are missing, major parts of the system will fail or return empty views.

## Full Recommended Schema

For the full portal experience, the dataset should include all of the following columns.

| Database Column | App Column | Type | Required for Full Portal | Description |
|---|---|---|---:|---|
| `date` | `date` | `DATE` | Yes | Observation/report date |
| `year` | `year` | `INTEGER` | Yes | Reporting year |
| `month` | `month` | `INTEGER` | Yes | Reporting month as `1-12` |
| `month_name` | `month_name` | `VARCHAR(20)` | No | Optional month label |
| `province` | `province` | `VARCHAR(100)` | Yes | Province name |
| `district` | `district` | `VARCHAR(100)` | Yes | District name |
| `rainfall_mm` | `Rainfall_mm` | `DECIMAL(8,2)` | Yes | Rainfall amount in millimetres |
| `temp_max_c` | `Temp_Max_C` | `DECIMAL(5,2)` | Yes | Maximum temperature in Celsius |
| `temp_min_c` | `Temp_Min_C` | `DECIMAL(5,2)` | Yes | Minimum temperature in Celsius |
| `humidity_pct` | `Humidity_pct` | `DECIMAL(5,2)` | No | Relative humidity percentage |
| `evapotranspiration_mm` | `Evapotranspiration_mm` | `DECIMAL(8,2)` | No | Evapotranspiration in millimetres |
| `wind_speed_mps` | `WindSpeed_mps` | `DECIMAL(5,2)` | No | Wind speed in metres per second |
| `solar_radiation_wm2` | `SolarRadiation_Wm2` | `DECIMAL(8,2)` | No | Solar radiation in watts per square metre |
| `soil_moisture_pct` | `SoilMoisture_pct` | `DECIMAL(5,2)` | Yes | Soil moisture percentage |
| `ndvi` | `NDVI` | `DECIMAL(5,3)` | Yes | Vegetation health index |
| `spi` | `SPI` | `DECIMAL(5,2)` | Yes | Standardized Precipitation Index |
| `spei` | `SPEI` | `DECIMAL(5,2)` | Yes | Standardized Precipitation Evapotranspiration Index |
| `pdsi` | `PDSI` | `DECIMAL(5,2)` | Yes | Palmer Drought Severity Index |
| `drought_severity` | `DroughtSeverity` | `VARCHAR(50)` | Yes | Drought classification label |
| `crop_yield_kg_ha` | `CropYield_kg_ha` | `DECIMAL(10,2)` | Yes | Crop yield in kilograms per hectare |
| `livestock_mortality_pct` | `LivestockMortality_pct` | `DECIMAL(5,2)` | No | Livestock mortality percentage |
| `food_price_zmw` | `FoodPrice_ZMW` | `DECIMAL(10,2)` | Yes | Food price indicator in Zambian Kwacha |
| `lake_kariba_level_m` | `LakeKariba_Level_m` | `DECIMAL(6,2)` | Yes | Lake Kariba water level in metres |
| `hydropower_mw` | `Hydropower_MW` | `DECIMAL(10,2)` | Yes | Hydropower generation in megawatts |
| `population_affected` | `PopulationAffected` | `INTEGER` | Yes | Number of affected people |
| `relief_interventions` | `ReliefInterventions` | `INTEGER` | No | Count of relief interventions |

## Naming Rules

The database uses `snake_case` column names. The application internally renames some columns to mixed-case analytical names.

Examples:

- `rainfall_mm` becomes `Rainfall_mm`
- `temp_max_c` becomes `Temp_Max_C`
- `population_affected` becomes `PopulationAffected`

When loading data into PostgreSQL, use the database column names listed under `Database Column`.

## Uniqueness Rule

The current database design expects each record to be unique for:

`date + province + district`

This is enforced by the unique constraint in the database. Duplicate records for the same date, province, and district will cause load conflicts unless cleaned first.

## Data Quality Rules

To avoid errors and misleading outputs, the dataset should follow these rules:

- `date` must use format `YYYY-MM-DD`
- `date` should not be in the future
- `year` should match the year part of `date`
- `month` should match the month part of `date`
- `month` must be between `1` and `12`
- `province` and `district` should use consistent spelling across all rows
- `NDVI` should stay between `-1` and `1`
- `population_affected`, `relief_interventions` should be integers
- numeric climate and impact fields should contain numeric values or `NULL`

Recommended drought labels:

- `No Drought`
- `Mild`
- `Moderate`
- `Severe`

Using consistent drought labels is important because the portal maps these values into drought scores and summary charts.

## What Each Page Depends On

### Dashboard

Needs:

- `date`, `year`, `month`, `province`, `district`
- `rainfall_mm`
- `temp_max_c`, `temp_min_c`
- `ndvi`
- `drought_severity`
- `population_affected`
- `crop_yield_kg_ha`
- `hydropower_mw`

### Rainfall Analysis

Needs:

- `date`, `year`, `month`, `province`
- `rainfall_mm`

### Temperature Analysis

Needs:

- `date`, `year`, `month`, `district`
- `temp_max_c`, `temp_min_c`

### Drought Analysis

Needs:

- `date`, `year`, `month`, `province`, `district`
- `soil_moisture_pct`
- `ndvi`
- `spi`
- `spei`
- `pdsi`
- `drought_severity`

### Impact Analysis

Needs:

- `date`, `year`, `month`, `province`, `district`
- `population_affected`
- `crop_yield_kg_ha`
- `food_price_zmw`
- `lake_kariba_level_m`
- `hydropower_mw`
- `rainfall_mm`, `temp_max_c`, `soil_moisture_pct`, `ndvi`, `drought_severity`

### Flood Risk Analysis

Needs:

- `date`, `year`, `month`, `province`
- `rainfall_mm`
- `spi`
- `soil_moisture_pct`

### District Comparison / Rankings / Explorer / Interactive Map

Needs:

- `date`, `year`, `month`, `province`, `district`
- plus the variable being explored or ranked

## Recommended Coverage

For the strongest analysis value, the dataset should:

- cover multiple years consistently
- include all provinces and districts used in the portal
- use regular monthly reporting
- avoid large blocks of missing values in key fields

The current project validation logic expects years roughly in the `2015-2025` range. If you expand beyond that, validation and some UI text may need updating.

## Example CSV Header

```csv
date,year,month,month_name,province,district,rainfall_mm,temp_max_c,temp_min_c,humidity_pct,evapotranspiration_mm,wind_speed_mps,solar_radiation_wm2,soil_moisture_pct,ndvi,spi,spei,pdsi,drought_severity,crop_yield_kg_ha,livestock_mortality_pct,food_price_zmw,lake_kariba_level_m,hydropower_mw,population_affected,relief_interventions
```

## Example Record

```csv
2024-01-01,2024,1,January,Southern,Siavonga,182.40,31.50,20.40,74.20,4.80,2.90,215.30,36.80,0.540,1.22,0.88,1.10,No Drought,2840.50,2.10,14.70,478.20,920.00,1250,3
```

## Success Checklist

Before loading a new dataset into the system, confirm that:

- all required columns exist
- date values are valid
- year and month columns are populated
- province and district names are clean and consistent
- numeric fields are truly numeric
- duplicate `date + province + district` rows are removed
- drought labels are standardized
- impact columns are included if the impact page should work fully

## Source of Truth in This Project

The current implementation references these files for schema and validation behaviour:

- [backend/scripts/init_db.py](/abs/path/c:/Users/Nathan%20Musonda/OneDrive/Desktop/Climate%20Data%20Visualization%20Portal/backend/scripts/init_db.py:38)
- [utils/data_loader.py](/abs/path/c:/Users/Nathan%20Musonda/OneDrive/Desktop/Climate%20Data%20Visualization%20Portal/utils/data_loader.py:43)
- [utils/validation.py](/abs/path/c:/Users/Nathan%20Musonda/OneDrive/Desktop/Climate%20Data%20Visualization%20Portal/utils/validation.py:41)
