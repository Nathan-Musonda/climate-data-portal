Place the Zambia district boundary GeoJSON file here as:

zambia_districts.geojson

Alternative:
- set environment variable ZAMBIA_DISTRICT_GEOJSON_URL to an online GeoJSON URL
- the portal will try the local file first, then the online URL

Expected behavior:
- the dashboard map will shade whole districts by the selected variable
- the interactive map page will shade whole districts by the selected variable
- clicking a shaded district will load that district's details

Recommended GeoJSON properties:
- district
- DISTRICT
- District
- NAME2
- NAME_2
- ADM2_EN

If no boundary file is present, the portal falls back to district markers.
