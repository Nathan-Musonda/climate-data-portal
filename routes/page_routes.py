from flask import Blueprint, current_app, render_template

from utils.data_loader import get_filter_options_from_db
from utils.database import db_manager

page_routes = Blueprint('pages', __name__)


def get_year_coverage_context(years):
    numeric_years = sorted({int(year) for year in years if year is not None})
    latest_data_year = max(numeric_years) if numeric_years else None
    fallback_year = latest_data_year

    context = {
        'dashboard_latest_data_year': latest_data_year,
        'dashboard_complete_years': numeric_years,
        'dashboard_partial_years': [],
        'dashboard_year_month_counts': {},
        'dashboard_default_year': fallback_year,
    }

    try:
        rows = db_manager.execute_query(
            "SELECT year, COUNT(DISTINCT month) AS month_count "
            "FROM climate_records "
            "WHERE year IS NOT NULL "
            "GROUP BY year "
            "ORDER BY year"
        ) or []
    except Exception as error:
        current_app.logger.warning(f"Unable to load year month coverage: {error}")
        rows = []

    if not rows:
        return context

    month_counts = {}
    for row in rows:
        year = row.get('year')
        if year is None:
            continue
        month_counts[int(year)] = int(row.get('month_count') or 0)

    complete_years = sorted(year for year, count in month_counts.items() if count >= 12)
    partial_years = sorted(year for year, count in month_counts.items() if 0 < count < 12)
    context.update({
        'dashboard_complete_years': complete_years or numeric_years,
        'dashboard_partial_years': partial_years,
        'dashboard_year_month_counts': month_counts,
        'dashboard_default_year': max(complete_years) if complete_years else fallback_year,
    })
    return context


def build_filter_context(include_provinces=True, include_districts=True, include_months=False):
    options = get_filter_options_from_db()
    years = sorted(options.get('years', []))
    year_context = get_year_coverage_context(years)
    context = {
        'dashboard_years': years,
        'dashboard_latest_year': year_context.get('dashboard_default_year'),
        **year_context,
    }

    if include_provinces:
        provinces = sorted(options.get('provinces', []))
        context['dashboard_provinces'] = provinces
        context['explorer_provinces'] = provinces

    if include_districts:
        districts = sorted(options.get('districts', []))
        context['dashboard_districts'] = districts
        context['explorer_districts'] = districts

    if include_months:
        context['about_months'] = sorted(options.get('months', []))

    context['explorer_years'] = years
    context['district_geojson_url'] = current_app.config.get('DISTRICT_GEOJSON_URL')
    return context


def render_error_page(status_code, message):
    return (
        render_template('error.html', error_code=status_code, error_message=message),
        status_code,
    )


@page_routes.route('/')
def home():
    return render_template('index.html')


@page_routes.route('/overview')
@page_routes.route('/dashboard')
def dashboard():
    return render_template('dashboard.html', **build_filter_context())


@page_routes.route('/rainfall')
def rainfall():
    return render_template('rainfall.html', **build_filter_context())


@page_routes.route('/temperature')
def temperature():
    return render_template('temperature.html', **build_filter_context())


@page_routes.route('/drought')
def drought():
    return render_template('drought.html', **build_filter_context())


@page_routes.route('/projections')
def projections():
    return render_template('projections.html', **build_filter_context())


@page_routes.route('/impacts')
def impacts():
    return render_template('impacts.html')


@page_routes.route('/extreme-events')
def extreme_events():
    return render_template('extreme_events.html', **build_filter_context(include_districts=False))


@page_routes.route('/flood-events')
def flood_events():
    return render_template('flood_events.html', **build_filter_context(include_districts=False))


@page_routes.route('/rankings')
def rankings():
    return render_template('rankings.html', **build_filter_context())


@page_routes.route('/comparison')
def comparison():
    return rankings()


@page_routes.route('/interactive-map')
def interactive_map():
    return render_template(
        'interactive_map.html',
        **build_filter_context(include_provinces=False)
    )


@page_routes.route('/data-explorer')
def data_explorer():
    return render_template(
        'data_explorer.html',
        **build_filter_context()
    )


@page_routes.route('/about')
def about():
    context = build_filter_context(include_months=True)
    months = context.pop('about_months', [])
    provinces = context.get('dashboard_provinces', [])
    districts = context.get('dashboard_districts', [])
    years = context.get('dashboard_years', [])

    total_records = 0
    try:
        result = db_manager.execute_query(
            "SELECT COUNT(*) AS total_records FROM climate_records"
        ) or []
        if result:
            total_records = int(result[0].get('total_records', 0) or 0)
    except Exception as error:
        current_app.logger.warning(f"Unable to load about page record count: {error}")

    return render_template(
        'about.html',
        about_total_records=total_records,
        about_province_count=len(provinces),
        about_district_count=len(districts),
        about_month_count=len(months),
        about_start_year=years[0] if years else None,
        about_end_year=years[-1] if years else None
    )
