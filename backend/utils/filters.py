# utils/filters.py - Updated version
import pandas as pd
import logging

logger = logging.getLogger(__name__)


def apply_filters(df, province=None, district=None, year=None, month=None):
    """
    Apply filters to the dataframe
    Returns filtered dataframe (could be empty)
    """
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()

    filtered = df.copy()
    original_count = len(filtered)

    # Apply province filter
    if province and str(province).lower() != "all" and province != "":
        mask = filtered["Province"].str.lower() == str(province).lower()
        filtered = filtered[mask]
        logger.debug(
            f"Filtered by province: {province}, from {original_count} to {len(filtered)}")

    # Apply district filter
    if district and str(district).lower() != "all" and district != "":
        if "District" in filtered.columns:
            mask = filtered["District"].str.lower() == str(district).lower()
            filtered = filtered[mask]
            logger.debug(
                f"Filtered by district: {district}, remaining: {len(filtered)}")

    # Apply year filter
    if year and str(year).lower() != "all" and year != "":
        try:
            year_int = int(year)
            if "Year" in filtered.columns:
                filtered = filtered[filtered["Year"] == year_int]
            elif "Date" in filtered.columns:
                filtered = filtered[filtered["Date"].dt.year == year_int]
            logger.debug(
                f"Filtered by year: {year}, remaining: {len(filtered)}")
        except (ValueError, TypeError):
            logger.warning(f"Invalid year value: {year}")

    # Apply month filter
    if month and str(month).lower() != "all" and month != "":
        try:
            month_int = int(month)
            if "Month" in filtered.columns:
                filtered = filtered[filtered["Month"] == month_int]
            elif "Date" in filtered.columns:
                filtered = filtered[filtered["Date"].dt.month == month_int]
            logger.debug(
                f"Filtered by month: {month}, remaining: {len(filtered)}")
        except (ValueError, TypeError):
            logger.warning(f"Invalid month value: {month}")

    return filtered


def get_filter_options(df):
    """Get available filter options from the dataset"""
    if df is None or df.empty:
        return {"provinces": [], "districts": [], "years": [], "months": []}

    options = {
        "provinces": sorted(df["Province"].dropna().unique().tolist()) if "Province" in df.columns else [],
        "districts": sorted(df["District"].dropna().unique().tolist()) if "District" in df.columns else [],
        "years": sorted(df["Year"].dropna().unique().tolist()) if "Year" in df.columns else [],
        "months": sorted(df["Month"].dropna().unique().tolist()) if "Month" in df.columns else []
    }

    return options


def has_data(df):
    """Check if dataframe has data"""
    return df is not None and not df.empty
