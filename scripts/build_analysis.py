"""Build analysis outputs for the cooling access heat-risk project.

Run with the ArcGIS Pro Python interpreter:
    "C:\\Program Files\\ArcGIS\\Pro\\bin\\Python\\envs\\arcgispro-py3\\python.exe" scripts\\build_analysis.py
"""

from __future__ import annotations

import csv
import json
import math
import textwrap
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path

import arcpy
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import pandas as pd
import requests


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data_raw"
PROCESSED = ROOT / "data_processed"
OUTPUTS = ROOT / "outputs"
MAPS = OUTPUTS / "maps"
FIGURES = OUTPUTS / "figures"
GDB = PROCESSED / "Community_Cooling_Access_Heat_Risk.gdb"

STATE_FIPS = "53"
COUNTY_FIPS = "063"
COUNTY_GEOID = f"{STATE_FIPS}{COUNTY_FIPS}"
STUDY_NAME = "Spokane County, Washington"
ANALYSIS_SR = arcpy.SpatialReference(26911)  # NAD 1983 UTM Zone 11N
WGS84 = arcpy.SpatialReference(4326)

TIGER_TRACTS_URL = "https://www2.census.gov/geo/tiger/TIGER2024/TRACT/tl_2024_53_tract.zip"
TIGER_COUNTIES_URL = "https://www2.census.gov/geo/tiger/TIGER2024/COUNTY/tl_2024_us_county.zip"
TIGER_ROADS_URL = "https://www2.census.gov/geo/tiger/TIGER2024/ROADS/tl_2024_53063_roads.zip"
CENSUS_REPORTER_URL = (
    "https://api.censusreporter.org/1.0/data/show/latest"
    "?table_ids=B01001,B17001,B08201&geo_ids=140|05000US53063"
)
NRI_QUERY_URL = (
    "https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/"
    "National_Risk_Index_Census_Tracts/FeatureServer/0/query"
)
GONZAGA_COOLING_APP_ITEM = "f1e9424b84954502ba1163b9765480dd"
GONZAGA_PORTAL = "https://gonz.maps.arcgis.com"

PLACE_LABELS = [
    ("Spokane", -117.4235, 47.6588),
    ("Spokane Valley", -117.2394, 47.6732),
    ("Cheney", -117.5758, 47.4874),
    ("Airway Heights", -117.5933, 47.6446),
    ("Medical Lake", -117.6826, 47.5729),
    ("Deer Park", -117.4769, 47.9543),
    ("Liberty Lake", -117.1182, 47.6759),
]

URBAN_LABELS = [
    ("Downtown Spokane", -117.4235, 47.6588, 0, -950),
    ("North Spokane", -117.421, 47.705, 0, 0),
    ("Spokane Valley", -117.2394, 47.6732, 0, 0),
    ("South Hill", -117.395, 47.628, 0, 0),
]


def ensure_dirs() -> None:
    for path in [
        RAW,
        PROCESSED,
        MAPS,
        FIGURES,
        RAW / "tiger",
        RAW / "acs",
        RAW / "nri",
        RAW / "gonzaga_cooling_resources",
    ]:
        path.mkdir(parents=True, exist_ok=True)


def download(url: str, destination: Path) -> None:
    if destination.exists() and destination.stat().st_size > 0:
        return
    print(f"Downloading {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "JustAppTools GIS portfolio project"})
    with urllib.request.urlopen(req, timeout=120) as response:
        destination.write_bytes(response.read())


def unzip(zip_path: Path, destination: Path) -> None:
    marker = destination / ".unzipped"
    if marker.exists():
        return
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(destination)
    marker.write_text("unzipped\n", encoding="utf-8")


def delete_if_exists(dataset: str | Path) -> None:
    if arcpy.Exists(str(dataset)):
        arcpy.management.Delete(str(dataset))


def cleanup_obsolete_outputs() -> None:
    for name in [
        "Cooling_Resource_Candidates",
        "Cooling_Resource_Candidates_UTM11N",
        "Cooling_Resource_Candidates_WGS84",
    ]:
        delete_if_exists(GDB / name)


def prepare_boundaries() -> tuple[Path, Path]:
    tiger_dir = RAW / "tiger"
    tracts_zip = tiger_dir / "tl_2024_53_tract.zip"
    counties_zip = tiger_dir / "tl_2024_us_county.zip"
    tracts_dir = tiger_dir / "tl_2024_53_tract"
    counties_dir = tiger_dir / "tl_2024_us_county"

    download(TIGER_TRACTS_URL, tracts_zip)
    download(TIGER_COUNTIES_URL, counties_zip)
    unzip(tracts_zip, tracts_dir)
    unzip(counties_zip, counties_dir)

    tract_shp = next(tracts_dir.glob("tl_2024_53_tract.shp"))
    county_shp = next(counties_dir.glob("tl_2024_us_county.shp"))

    county_fc = GDB / "Study_Area_Spokane_County"
    tracts_fc = GDB / "Spokane_County_Tracts"
    county_projected = GDB / "Study_Area_Spokane_County_UTM11N"
    tracts_projected = GDB / "Spokane_County_Tracts_UTM11N"

    delete_if_exists(county_fc)
    arcpy.management.MakeFeatureLayer(str(county_shp), "county_lyr", f"STATEFP = '{STATE_FIPS}' AND COUNTYFP = '{COUNTY_FIPS}'")
    arcpy.management.CopyFeatures("county_lyr", str(county_fc))

    delete_if_exists(tracts_fc)
    arcpy.management.MakeFeatureLayer(str(tract_shp), "tracts_lyr", f"COUNTYFP = '{COUNTY_FIPS}'")
    arcpy.management.CopyFeatures("tracts_lyr", str(tracts_fc))

    for src, dest in [(county_fc, county_projected), (tracts_fc, tracts_projected)]:
        delete_if_exists(dest)
        arcpy.management.Project(str(src), str(dest), ANALYSIS_SR)

    return tracts_projected, county_projected


def prepare_roads() -> Path:
    tiger_dir = RAW / "tiger"
    roads_zip = tiger_dir / "tl_2024_53063_roads.zip"
    roads_dir = tiger_dir / "tl_2024_53063_roads"
    download(TIGER_ROADS_URL, roads_zip)
    unzip(roads_zip, roads_dir)
    roads_shp = next(roads_dir.glob("tl_2024_53063_roads.shp"))

    roads_fc = GDB / "Spokane_County_Major_Roads"
    roads_projected = GDB / "Spokane_County_Major_Roads_UTM11N"
    delete_if_exists(roads_fc)
    arcpy.management.MakeFeatureLayer(str(roads_shp), "roads_lyr", "MTFCC IN ('S1100', 'S1200')")
    arcpy.management.CopyFeatures("roads_lyr", str(roads_fc))
    delete_if_exists(roads_projected)
    arcpy.management.Project(str(roads_fc), str(roads_projected), ANALYSIS_SR)
    return roads_projected


def value(row: dict, table: str, field: str) -> float:
    return float(row.get(table, {}).get("estimate", {}).get(field) or 0)


def fetch_acs() -> pd.DataFrame:
    out_json = RAW / "acs" / "census_reporter_acs_spokane_tracts_latest.json"
    out_csv = RAW / "acs" / "acs_spokane_tract_indicators.csv"
    if not out_json.exists():
        response = requests.get(CENSUS_REPORTER_URL, timeout=60, headers={"User-Agent": "JustAppTools GIS portfolio project"})
        response.raise_for_status()
        out_json.write_text(response.text, encoding="utf-8")

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    rows = []
    for geo_id, tables in payload["data"].items():
        geoid = geo_id.replace("14000US", "")
        total_pop = value(tables, "B01001", "B01001001")
        under_5 = value(tables, "B01001", "B01001003") + value(tables, "B01001", "B01001027")
        over_65 = sum(value(tables, "B01001", f"B010010{i:02d}") for i in range(20, 26))
        over_65 += sum(value(tables, "B01001", f"B010010{i:02d}") for i in range(44, 50))
        poverty_universe = value(tables, "B17001", "B17001001")
        poverty = value(tables, "B17001", "B17001002")
        household_universe = value(tables, "B08201", "B08201001")
        no_vehicle = value(tables, "B08201", "B08201002")
        rows.append(
            {
                "GEOID": geoid,
                "NAME": payload["geography"].get(geo_id, {}).get("name", ""),
                "ACS_TOTAL_POP": total_pop,
                "ACS_UNDER5": under_5,
                "ACS_OVER65": over_65,
                "ACS_SENSITIVE_PCT": safe_pct(under_5 + over_65, total_pop),
                "ACS_POVERTY_PCT": safe_pct(poverty, poverty_universe),
                "ACS_NO_VEHICLE_PCT": safe_pct(no_vehicle, household_universe),
            }
        )
    df = pd.DataFrame(rows).sort_values("GEOID")
    df.to_csv(out_csv, index=False)
    return df


def fetch_nri() -> pd.DataFrame:
    out_json = RAW / "nri" / "fema_nri_spokane_tracts_heat_wave.json"
    out_csv = RAW / "nri" / "fema_nri_spokane_tracts_heat_wave.csv"
    if not out_json.exists():
        params = {
            "f": "json",
            "where": f"STCOFIPS='{COUNTY_GEOID}'",
            "outFields": (
                "NRI_ID,TRACTFIPS,HWAV_RISKS,HWAV_RISKR,HWAV_AFREQ,"
                "SOVI_SCORE,SOVI_RATNG,RISK_SCORE,RISK_RATNG"
            ),
            "returnGeometry": "false",
        }
        response = requests.get(NRI_QUERY_URL, params=params, timeout=60)
        response.raise_for_status()
        out_json.write_text(response.text, encoding="utf-8")

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    rows = [feature["attributes"] for feature in payload.get("features", [])]
    df = pd.DataFrame(rows).rename(
        columns={
            "TRACTFIPS": "GEOID",
            "HWAV_RISKS": "NRI_HEATWAVE_RISK_SCORE",
            "HWAV_RISKR": "NRI_HEATWAVE_RISK_RATING",
            "HWAV_AFREQ": "NRI_HEATWAVE_ANNUALIZED_FREQ",
            "SOVI_SCORE": "NRI_SOVI_SCORE",
            "SOVI_RATNG": "NRI_SOVI_RATING",
            "RISK_SCORE": "NRI_COMPOSITE_RISK_SCORE",
            "RISK_RATNG": "NRI_COMPOSITE_RISK_RATING",
        }
    )
    df.to_csv(out_csv, index=False)
    return df


def safe_pct(numerator: float, denominator: float) -> float:
    if not denominator:
        return 0.0
    return round((numerator / denominator) * 100, 2)


def query_feature_layer(url: str) -> list[dict]:
    params = {
        "f": "json",
        "where": "1=1",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
    }
    response = requests.get(f"{url}/query", params=params, timeout=60)
    response.raise_for_status()
    return response.json().get("features", [])


def service_community_name(url: str) -> str:
    service_name = url.split("/FeatureServer/")[0].rstrip("/").split("/")[-1]
    service_name = service_name.replace("_Cooling_Resources_Map", "")
    service_name = service_name.replace("_Cooling_Resources", "")
    service_name = service_name.replace("Town_of_", "")
    service_name = service_name.replace("City_of_", "")
    return service_name.replace("_", " ")


def fetch_gonzaga_cooling_resources(county_fc: Path) -> tuple[Path, Path]:
    raw_dir = RAW / "gonzaga_cooling_resources"
    app_data_url = f"{GONZAGA_PORTAL}/sharing/rest/content/items/{GONZAGA_COOLING_APP_ITEM}/data?f=json"
    app_data = requests.get(app_data_url, timeout=60).json()
    map_item = app_data["map"]["itemId"]
    webmap_url = f"{GONZAGA_PORTAL}/sharing/rest/content/items/{map_item}/data?f=json"
    webmap = requests.get(webmap_url, timeout=60).json()
    (raw_dir / "gonzaga_cooling_resources_webmap.json").write_text(json.dumps(webmap, indent=2), encoding="utf-8")

    rows = []
    seen = set()
    for layer in webmap.get("operationalLayers", []):
        title = layer.get("title", "")
        url = layer.get("url")
        if not url:
            continue
        features = query_feature_layer(url)
        layer_payload = {"title": title, "url": url, "features": features}
        safe_title = f"{service_community_name(url)}_{title}".replace(" ", "_").replace("/", "_")
        (raw_dir / f"{safe_title}.json").write_text(json.dumps(layer_payload, indent=2), encoding="utf-8")
        for feature in features:
            geom = feature.get("geometry") or {}
            attrs = feature.get("attributes") or {}
            if "x" not in geom or "y" not in geom:
                continue
            name = attrs.get("Name") or attrs.get("NAME") or "Unnamed resource"
            address = attrs.get("Address") or ""
            key = (title, name.strip().lower(), address.strip().lower(), round(geom["x"], 5), round(geom["y"], 5))
            if key in seen:
                continue
            seen.add(key)
            is_primary = title == "Cooling Centers and Spaces"
            rows.append(
                {
                    "name": name,
                    "category": title,
                    "access_use": 1 if is_primary else 0,
                    "resource_type": attrs.get("Type_of_Center") or attrs.get("Type_of_Location") or title,
                    "community": service_community_name(url),
                    "address": address,
                    "lat": float(geom["y"]),
                    "lon": float(geom["x"]),
                    "source_url": url,
                }
            )

    resources_csv = raw_dir / "gonzaga_cooling_resources.csv"
    with resources_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["name", "category", "access_use", "resource_type", "community", "address", "lat", "lon", "source_url"],
        )
        writer.writeheader()
        writer.writerows(rows)

    points_wgs = GDB / "Regional_Cooling_Resources_WGS84"
    points_utm = GDB / "Regional_Cooling_Resources_UTM11N"
    all_resources = GDB / "Regional_Cooling_Resources"
    primary_resources = GDB / "Cooling_Centers_and_Spaces"
    delete_if_exists(points_wgs)
    arcpy.management.CreateFeatureclass(str(GDB), points_wgs.name, "POINT", spatial_reference=WGS84)
    for field, length in [
        ("Name", 180),
        ("Category", 60),
        ("ResourceType", 120),
        ("Community", 80),
        ("Address", 180),
        ("SourceURL", 255),
    ]:
        arcpy.management.AddField(str(points_wgs), field, "TEXT", field_length=length)
    arcpy.management.AddField(str(points_wgs), "AccessUse", "SHORT")
    with arcpy.da.InsertCursor(
        str(points_wgs),
        ["SHAPE@XY", "Name", "Category", "AccessUse", "ResourceType", "Community", "Address", "SourceURL"],
    ) as cursor:
        for item in rows:
            cursor.insertRow(
                (
                    (item["lon"], item["lat"]),
                    item["name"][:180],
                    item["category"][:60],
                    item["access_use"],
                    item["resource_type"][:120],
                    item["community"][:80],
                    item["address"][:180],
                    item["source_url"][:255],
                )
            )

    delete_if_exists(points_utm)
    arcpy.management.Project(str(points_wgs), str(points_utm), ANALYSIS_SR)
    delete_if_exists(all_resources)
    arcpy.management.MakeFeatureLayer(str(points_utm), "regional_resources_lyr")
    arcpy.management.SelectLayerByLocation("regional_resources_lyr", "WITHIN", str(county_fc))
    arcpy.management.CopyFeatures("regional_resources_lyr", str(all_resources))

    delete_if_exists(primary_resources)
    arcpy.management.MakeFeatureLayer(str(all_resources), "primary_resources_lyr", "AccessUse = 1")
    arcpy.management.CopyFeatures("primary_resources_lyr", str(primary_resources))
    return primary_resources, all_resources


def facility_group(resource_type: str | None) -> str:
    text = (resource_type or "").lower()
    if "library" in text:
        return "Library"
    if "senior" in text:
        return "Senior/community"
    if "community" in text or "recreation" in text:
        return "Community/recreation"
    return "Other cooling space"


def percentile_scores(values: pd.Series) -> pd.Series:
    cleaned = pd.to_numeric(values, errors="coerce").fillna(0)
    q1 = cleaned.quantile(1 / 3)
    q2 = cleaned.quantile(2 / 3)
    return cleaned.apply(lambda value: 1 if value <= q1 else 2 if value <= q2 else 3)


def add_analysis_fields(tracts_fc: Path) -> None:
    existing = {field.name for field in arcpy.ListFields(str(tracts_fc))}
    fields = [
        ("ACS_TOTAL_POP", "DOUBLE"),
        ("ACS_POVERTY_PCT", "DOUBLE"),
        ("ACS_NO_VEHICLE_PCT", "DOUBLE"),
        ("ACS_SENSITIVE_PCT", "DOUBLE"),
        ("NRI_HEATWAVE_RISK_SCORE", "DOUBLE"),
        ("NRI_HEATWAVE_RISK_RATING", "TEXT"),
        ("NRI_HEATWAVE_ANNUALIZED_FREQ", "DOUBLE"),
        ("NRI_SOVI_SCORE", "DOUBLE"),
        ("NRI_SOVI_RATING", "TEXT"),
        ("NEAREST_COOLING_MI", "DOUBLE"),
        ("COOLING_WITHIN_3MI", "LONG"),
        ("COOLING_WITHIN_5MI", "LONG"),
        ("ACCESS_POINT_METHOD", "TEXT"),
        ("HEAT_CONCERN_SCORE", "SHORT"),
        ("SOVI_CONCERN_SCORE", "SHORT"),
        ("TRANSPORT_BARRIER_SCORE", "SHORT"),
        ("COOLING_ACCESS_SCORE", "SHORT"),
        ("FINAL_CONCERN_SCORE", "SHORT"),
        ("CONCERN_CLASS", "TEXT"),
    ]
    for name, field_type in fields:
        if name not in existing:
            kwargs = {"field_length": 40} if field_type == "TEXT" else {}
            arcpy.management.AddField(str(tracts_fc), name, field_type, **kwargs)


def tract_representative_point(row: tuple) -> arcpy.PointGeometry:
    _, intptlat, intptlon, geom = row
    try:
        point_wgs = arcpy.PointGeometry(arcpy.Point(float(intptlon), float(intptlat)), WGS84)
        return point_wgs.projectAs(ANALYSIS_SR)
    except Exception:
        return arcpy.PointGeometry(geom.trueCentroid, ANALYSIS_SR)


def compute_access_metrics(tracts_fc: Path, resources_fc: Path) -> dict[str, dict]:
    resources = [row[0] for row in arcpy.da.SearchCursor(str(resources_fc), ["SHAPE@"])]
    metrics = {}
    for row in arcpy.da.SearchCursor(str(tracts_fc), ["GEOID", "INTPTLAT", "INTPTLON", "SHAPE@"]):
        geoid = row[0]
        point = tract_representative_point(row)
        distances_m = [point.distanceTo(resource) for resource in resources]
        if not distances_m:
            nearest = math.nan
            within_3 = 0
            within_5 = 0
        else:
            nearest = min(distances_m) / 1609.344
            within_3 = sum(distance <= 3 * 1609.344 for distance in distances_m)
            within_5 = sum(distance <= 5 * 1609.344 for distance in distances_m)
        metrics[geoid] = {
            "NEAREST_COOLING_MI": round(nearest, 2) if not math.isnan(nearest) else None,
            "COOLING_WITHIN_3MI": within_3,
            "COOLING_WITHIN_5MI": within_5,
            "ACCESS_POINT_METHOD": "Census tract internal point",
        }
    return metrics


def classify(score: int) -> str:
    if score >= 10:
        return "High"
    if score >= 7:
        return "Medium"
    return "Low"


def build_summary(tracts_fc: Path, resources_fc: Path, acs: pd.DataFrame, nri: pd.DataFrame) -> pd.DataFrame:
    access = pd.DataFrame.from_dict(compute_access_metrics(tracts_fc, resources_fc), orient="index").reset_index()
    access = access.rename(columns={"index": "GEOID"})
    summary = acs.merge(nri, on="GEOID", how="left").merge(access, on="GEOID", how="left")
    summary["HEAT_CONCERN_SCORE"] = percentile_scores(summary["NRI_HEATWAVE_RISK_SCORE"])
    summary["SOVI_CONCERN_SCORE"] = percentile_scores(summary["NRI_SOVI_SCORE"])
    summary["TRANSPORT_BARRIER_SCORE"] = percentile_scores(summary["ACS_NO_VEHICLE_PCT"])
    summary["COOLING_ACCESS_SCORE"] = percentile_scores(summary["NEAREST_COOLING_MI"])
    summary["FINAL_CONCERN_SCORE"] = (
        summary["HEAT_CONCERN_SCORE"]
        + summary["SOVI_CONCERN_SCORE"]
        + summary["TRANSPORT_BARRIER_SCORE"]
        + summary["COOLING_ACCESS_SCORE"]
    )
    summary["CONCERN_CLASS"] = summary["FINAL_CONCERN_SCORE"].apply(classify)
    summary = summary.sort_values(["FINAL_CONCERN_SCORE", "NEAREST_COOLING_MI"], ascending=[False, False])
    summary.to_csv(PROCESSED / "cooling_heat_risk_tract_summary.csv", index=False)
    summary.head(15).to_csv(OUTPUTS / "high_concern_tracts.csv", index=False)

    add_analysis_fields(tracts_fc)
    lookup = summary.set_index("GEOID").to_dict(orient="index")
    update_fields = [
        "GEOID",
        "ACS_TOTAL_POP",
        "ACS_POVERTY_PCT",
        "ACS_NO_VEHICLE_PCT",
        "ACS_SENSITIVE_PCT",
        "NRI_HEATWAVE_RISK_SCORE",
        "NRI_HEATWAVE_RISK_RATING",
        "NRI_HEATWAVE_ANNUALIZED_FREQ",
        "NRI_SOVI_SCORE",
        "NRI_SOVI_RATING",
        "NEAREST_COOLING_MI",
        "COOLING_WITHIN_3MI",
        "COOLING_WITHIN_5MI",
        "ACCESS_POINT_METHOD",
        "HEAT_CONCERN_SCORE",
        "SOVI_CONCERN_SCORE",
        "TRANSPORT_BARRIER_SCORE",
        "COOLING_ACCESS_SCORE",
        "FINAL_CONCERN_SCORE",
        "CONCERN_CLASS",
    ]
    with arcpy.da.UpdateCursor(str(tracts_fc), update_fields) as cursor:
        for row in cursor:
            data = lookup.get(row[0])
            if not data:
                continue
            for index, field in enumerate(update_fields[1:], start=1):
                row[index] = data.get(field)
            cursor.updateRow(row)
    return summary


def polygon_parts(geometry: arcpy.Geometry) -> list[list[tuple[float, float]]]:
    parts = []
    for part in geometry:
        coords = []
        for point in part:
            if point:
                coords.append((point.X, point.Y))
        if coords:
            parts.append(coords)
    return parts


def line_parts(geometry: arcpy.Geometry) -> list[list[tuple[float, float]]]:
    parts = []
    for part in geometry:
        coords = []
        for point in part:
            if point:
                coords.append((point.X, point.Y))
        if len(coords) > 1:
            parts.append(coords)
    return parts


def project_xy(lon: float, lat: float) -> tuple[float, float]:
    geom = arcpy.PointGeometry(arcpy.Point(lon, lat), WGS84).projectAs(ANALYSIS_SR)
    return geom.centroid.X, geom.centroid.Y


def draw_scale_bar(ax, miles: int = 5, *, location: tuple[float, float] = (0.06, 0.06)) -> None:
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    length = miles * 1609.344
    start_x = x0 + (x1 - x0) * location[0]
    start_y = y0 + (y1 - y0) * location[1]
    tick = (y1 - y0) * 0.012
    ax.plot([start_x, start_x + length], [start_y, start_y], color="white", linewidth=3.1, solid_capstyle="butt", zorder=19)
    ax.plot([start_x, start_x + length], [start_y, start_y], color="#3f4447", linewidth=1.35, solid_capstyle="butt", zorder=20)
    ax.plot([start_x, start_x], [start_y - tick, start_y + tick], color="#3f4447", linewidth=0.8, zorder=20)
    ax.plot([start_x + length, start_x + length], [start_y - tick, start_y + tick], color="#3f4447", linewidth=0.8, zorder=20)
    ax.text(
        start_x + length / 2,
        start_y + tick * 1.45,
        f"{miles} mi",
        ha="center",
        va="bottom",
        fontsize=7.2,
        color="#303437",
        bbox={"boxstyle": "round,pad=0.08", "facecolor": "white", "edgecolor": "none", "alpha": 0.72},
        zorder=20,
    )


def draw_north_arrow(ax) -> None:
    ax.annotate(
        "N",
        xy=(0.94, 0.91),
        xytext=(0.94, 0.82),
        xycoords="axes fraction",
        ha="center",
        va="center",
        fontsize=10,
        weight="bold",
        arrowprops={"arrowstyle": "-|>", "lw": 1.4, "color": "#2f3437"},
        color="#2f3437",
    )


def set_extent_from_wgs(ax, xmin: float, ymin: float, xmax: float, ymax: float) -> None:
    ll = project_xy(xmin, ymin)
    ur = project_xy(xmax, ymax)
    ax.set_xlim(ll[0], ur[0])
    ax.set_ylim(ll[1], ur[1])


def extent_patch_from_wgs(xmin: float, ymin: float, xmax: float, ymax: float) -> patches.Rectangle:
    ll = project_xy(xmin, ymin)
    ur = project_xy(xmax, ymax)
    return patches.Rectangle(
        ll,
        ur[0] - ll[0],
        ur[1] - ll[1],
        fill=False,
        edgecolor="#1f4e5f",
        linewidth=1.4,
        linestyle="--",
        zorder=25,
    )


def draw_layers(
    ax,
    tracts_fc: Path,
    county_fc: Path,
    roads_fc: Path,
    all_resources_fc: Path,
    *,
    detail: bool = False,
    labels: bool = False,
    resources: bool = True,
) -> None:
    colors = {"Low": "#dceff4", "Medium": "#f5cf7a", "High": "#b85852"}
    ax.set_facecolor("#f8f7f2")
    tract_edge = "#ffffff" if detail else "#f2efe7"
    for geom, concern in arcpy.da.SearchCursor(str(tracts_fc), ["SHAPE@", "CONCERN_CLASS"]):
        for part in polygon_parts(geom):
            ax.add_patch(
                patches.Polygon(
                    part,
                    closed=True,
                    facecolor=colors.get(concern, "#dddddd"),
                    edgecolor=tract_edge,
                    linewidth=0.45 if detail else 0.35,
                    zorder=1,
                )
            )

    for geom, mtfcc in arcpy.da.SearchCursor(str(roads_fc), ["SHAPE@", "MTFCC"]):
        color = "#8e8b85" if mtfcc == "S1100" else "#c2bdb5"
        width = 0.9 if mtfcc == "S1100" else 0.45
        for part in line_parts(geom):
            xs, ys = zip(*part)
            ax.plot(xs, ys, color=color, linewidth=width if detail else width * 0.65, alpha=0.58, zorder=3)

    if resources:
        supplemental_x, supplemental_y = [], []
        primary_by_group = {
            "Library": ([], []),
            "Community/recreation": ([], []),
            "Senior/community": ([], []),
            "Other cooling space": ([], []),
        }
        for geom, access_use, resource_type in arcpy.da.SearchCursor(str(all_resources_fc), ["SHAPE@", "AccessUse", "ResourceType"]):
            if access_use == 1:
                xs, ys = primary_by_group[facility_group(resource_type)]
                xs.append(geom.centroid.X)
                ys.append(geom.centroid.Y)
            else:
                supplemental_x.append(geom.centroid.X)
                supplemental_y.append(geom.centroid.Y)
        ax.scatter(
            supplemental_x,
            supplemental_y,
            s=6 if detail else 4,
            c="#4fa7a0",
            edgecolors="white",
            linewidths=0.12,
            alpha=0.18 if detail else 0.12,
            zorder=5,
        )
        symbol_specs = {
            "Library": {"marker": "P", "color": "#155e8a", "size": 54},
            "Community/recreation": {"marker": "s", "color": "#206f5b", "size": 42},
            "Senior/community": {"marker": "^", "color": "#6f4e9b", "size": 48},
            "Other cooling space": {"marker": "D", "color": "#9a5a20", "size": 38},
        }
        for group, (xs, ys) in primary_by_group.items():
            spec = symbol_specs[group]
            ax.scatter(
                xs,
                ys,
                s=(spec["size"] if detail else spec["size"] * 0.55) * 1.62,
                marker=spec["marker"],
                c="white",
                edgecolors="white",
                linewidths=0,
                zorder=5.8,
            )
            ax.scatter(
                xs,
                ys,
                s=spec["size"] if detail else spec["size"] * 0.55,
                marker=spec["marker"],
                c=spec["color"],
                edgecolors="white",
                linewidths=0.95,
                zorder=6,
            )

    for geom in arcpy.da.SearchCursor(str(county_fc), ["SHAPE@"]):
        for part in polygon_parts(geom[0]):
            ax.add_patch(patches.Polygon(part, closed=True, fill=False, edgecolor="#2f3437", linewidth=1.0, zorder=7))

    if labels:
        for name, lon, lat in PLACE_LABELS:
            x, y = project_xy(lon, lat)
            ax.text(
                x,
                y,
                name,
                fontsize=7.2 if not detail else 8,
                color="#303437",
                ha="center",
                va="center",
                zorder=8,
                bbox={"boxstyle": "round,pad=0.12", "facecolor": "white", "edgecolor": "none", "alpha": 0.65},
            )
    ax.set_aspect("equal")
    ax.axis("off")


def draw_urban_labels(ax) -> None:
    for name, lon, lat, dx, dy in URBAN_LABELS:
        x, y = project_xy(lon, lat)
        ax.text(
            x + dx,
            y + dy,
            name,
            fontsize=7.5,
            color="#303437",
            ha="center",
            va="center",
            zorder=4,
            bbox={"boxstyle": "round,pad=0.16", "facecolor": "white", "edgecolor": "none", "alpha": 0.72},
        )


def draw_top_tract_outlines(
    ax,
    tracts_fc: Path,
    summary: pd.DataFrame,
    *,
    outline_width: float = 1.9,
    halo_width: float = 3.2,
    badge_font: float = 7.4,
    badge_pad: float = 0.22,
    show_badges: bool = True,
) -> None:
    top_order = {str(row.GEOID): idx for idx, row in enumerate(summary.head(4).itertuples(), start=1)}
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    for geoid, geom in arcpy.da.SearchCursor(str(tracts_fc), ["GEOID", "SHAPE@"]):
        rank = top_order.get(str(geoid))
        if rank is None:
            continue
        visible_points = []
        for part in polygon_parts(geom):
            visible_points.extend([(x, y) for x, y in part if x0 <= x <= x1 and y0 <= y <= y1])
            ax.add_patch(
                patches.Polygon(
                    part,
                    closed=True,
                    fill=False,
                    edgecolor="white",
                    linewidth=halo_width,
                    alpha=0.9,
                    zorder=21,
                )
            )
            ax.add_patch(
                patches.Polygon(
                    part,
                    closed=True,
                    fill=False,
                    edgecolor="#1f4e5f",
                    linewidth=outline_width,
                    alpha=0.98,
                    zorder=22,
                )
            )
        anchor = geom.centroid
        label_x, label_y = anchor.X, anchor.Y
        if visible_points:
            label_x = sum(x for x, _ in visible_points) / len(visible_points)
            label_y = sum(y for _, y in visible_points) / len(visible_points)
        if show_badges and x0 <= label_x <= x1 and y0 <= label_y <= y1:
            ax.text(
                label_x,
                label_y,
                str(rank),
                fontsize=badge_font,
                weight="bold",
                color="white",
                ha="center",
                va="center",
                bbox={
                    "boxstyle": f"round,pad={badge_pad}",
                    "facecolor": "#1f4e5f",
                    "edgecolor": "white",
                    "linewidth": 0.7,
                    "alpha": 0.96,
                },
                zorder=25,
            )


def draw_callout_box(ax, title: str, body: str, y: float) -> None:
    ax.text(0, y, title, fontsize=9.2, weight="bold", color="#222222", ha="left", va="top")
    ax.text(0, y - 0.052, textwrap.fill(body, 44), fontsize=7.8, color="#3f4447", ha="left", va="top", linespacing=1.2)


def draw_grouped_legend(fig, colors: dict[str, str], class_counts: pd.Series) -> None:
    legend_ax = fig.add_axes([0.055, 0.073, 0.62, 0.072])
    legend_ax.axis("off")

    def heading(x: float, label: str) -> None:
        legend_ax.text(x, 0.92, label, transform=legend_ax.transAxes, fontsize=7.4, weight="bold", color="#222222", ha="left", va="top")

    def patch_item(x: float, y: float, color: str, label: str) -> None:
        legend_ax.add_patch(
            patches.Rectangle((x, y - 0.07), 0.025, 0.12, transform=legend_ax.transAxes, facecolor=color, edgecolor="white", linewidth=0.5)
        )
        legend_ax.text(x + 0.034, y, label, transform=legend_ax.transAxes, fontsize=7.2, color="#303437", ha="left", va="center")

    def marker_item(x: float, y: float, marker: str, color: str, label: str, size: float = 36) -> None:
        legend_ax.scatter([x + 0.012], [y], transform=legend_ax.transAxes, s=size, marker=marker, c=color, edgecolors="white", linewidths=0.6)
        legend_ax.text(x + 0.034, y, label, transform=legend_ax.transAxes, fontsize=7.2, color="#303437", ha="left", va="center")

    heading(0.00, "Concern class")
    patch_item(0.00, 0.58, colors["Low"], f"Low ({class_counts['Low']})")
    patch_item(0.00, 0.30, colors["Medium"], f"Medium ({class_counts['Medium']})")
    patch_item(0.00, 0.02, colors["High"], f"High ({class_counts['High']})")

    legend_ax.plot([0.245, 0.245], [0.04, 0.86], transform=legend_ax.transAxes, color="#ddd8cf", linewidth=0.8)
    heading(0.28, "Scored cooling resources")
    marker_item(0.28, 0.58, "P", "#155e8a", "Libraries", 42)
    marker_item(0.28, 0.30, "s", "#206f5b", "Community/rec", 34)
    marker_item(0.50, 0.58, "^", "#6f4e9b", "Senior/community", 42)
    marker_item(0.50, 0.30, "D", "#9a5a20", "Other spaces", 34)

    legend_ax.plot([0.70, 0.70], [0.04, 0.86], transform=legend_ax.transAxes, color="#ddd8cf", linewidth=0.8)
    heading(0.74, "Context")
    legend_ax.scatter([0.756], [0.58], transform=legend_ax.transAxes, s=26, marker="o", c="#4fa7a0", edgecolors="white", linewidths=0.6)
    legend_ax.text(0.79, 0.58, "Supplemental resources", transform=legend_ax.transAxes, fontsize=7.2, color="#303437", ha="left", va="center")
    legend_ax.plot([0.744, 0.775], [0.30, 0.30], transform=legend_ax.transAxes, color="#9b9690", linewidth=1.2)
    legend_ax.text(0.79, 0.30, "Major roads", transform=legend_ax.transAxes, fontsize=7.2, color="#303437", ha="left", va="center")
    legend_ax.plot([0.744, 0.775], [0.02, 0.02], transform=legend_ax.transAxes, color="#1f4e5f", linewidth=2.0)
    legend_ax.text(0.79, 0.02, "Top priority tract", transform=legend_ax.transAxes, fontsize=7.2, color="#303437", ha="left", va="center")


def draw_component_chart(ax, top: pd.DataFrame, y0: float) -> None:
    factor_fields = [
        ("H", "HEAT_CONCERN_SCORE", "#b85852"),
        ("S", "SOVI_CONCERN_SCORE", "#6f4e9b"),
        ("V", "TRANSPORT_BARRIER_SCORE", "#d99a31"),
        ("A", "COOLING_ACCESS_SCORE", "#1f4e5f"),
    ]
    ax.text(0, y0, "Why They Rank High", fontsize=9.4, weight="bold", color="#222222", ha="left", va="top")
    ax.text(0, y0 - 0.036, "All four reach maximum factor scores; mileage shows access severity.", fontsize=7.3, color="#4a4f52", ha="left", va="top")
    legend_x = 0.0
    for label, _, color in factor_fields:
        ax.add_patch(patches.Rectangle((legend_x, y0 - 0.098), 0.018, 0.016, transform=ax.transAxes, facecolor=color, edgecolor="none"))
        ax.text(legend_x + 0.024, y0 - 0.089, label, transform=ax.transAxes, fontsize=6.8, color="#4a4f52", ha="left", va="center")
        legend_x += 0.090

    bar_x = 0.18
    bar_w = 0.63
    bar_h = 0.018
    row_y = y0 - 0.138
    for rank, (_, row) in enumerate(top.iterrows(), start=1):
        ax.text(0.0, row_y + bar_h / 2, str(rank), fontsize=7.0, weight="bold", color="#1f4e5f", ha="left", va="center")
        left = bar_x
        for _, field, color in factor_fields:
            width = bar_w * (float(row[field]) / 12.0)
            ax.add_patch(
                patches.Rectangle((left, row_y), width, bar_h, transform=ax.transAxes, facecolor=color, edgecolor="white", linewidth=0.35)
            )
            left += width
        ax.text(
            bar_x + bar_w + 0.035,
            row_y + bar_h / 2,
            f'{int(row["FINAL_CONCERN_SCORE"])}',
            fontsize=7.0,
            color="#4a4f52",
            ha="left",
            va="center",
        )
        row_y -= 0.036


def draw_map(
    tracts_fc: Path,
    county_fc: Path,
    roads_fc: Path,
    primary_resources_fc: Path,
    all_resources_fc: Path,
    summary: pd.DataFrame,
) -> None:
    colors = {"Low": "#dceff4", "Medium": "#f5cf7a", "High": "#b85852"}
    urban_extent = (-117.50, 47.585, -117.22, 47.755)
    fig = plt.figure(figsize=(14, 9.5), facecolor="white")
    main_ax = fig.add_axes([0.045, 0.16, 0.61, 0.69])
    county_ax = fig.add_axes([0.735, 0.685, 0.18, 0.18])
    info_ax = fig.add_axes([0.70, 0.073, 0.285, 0.575])
    info_ax.axis("off")

    draw_layers(main_ax, tracts_fc, county_fc, roads_fc, all_resources_fc, detail=True, labels=False)
    set_extent_from_wgs(main_ax, *urban_extent)
    draw_top_tract_outlines(main_ax, tracts_fc, summary, outline_width=1.7, halo_width=2.8, badge_font=6.8, badge_pad=0.16)
    draw_urban_labels(main_ax)
    main_ax.set_title("Spokane Urban Core Detail", fontsize=12, weight="bold", loc="left", pad=5)

    draw_layers(county_ax, tracts_fc, county_fc, roads_fc, all_resources_fc, detail=False, labels=False, resources=False)
    county_ax.add_patch(extent_patch_from_wgs(*urban_extent))
    county_ax.set_title("County Context", fontsize=10, weight="bold", loc="left", pad=4)
    county_ax.text(
        0.5,
        -0.06,
        "Dashed box shows detail extent",
        transform=county_ax.transAxes,
        ha="center",
        va="center",
        fontsize=7,
        color="#303437",
        clip_on=False,
    )

    extent = arcpy.Describe(str(county_fc)).extent
    pad_x = (extent.XMax - extent.XMin) * 0.04
    pad_y = (extent.YMax - extent.YMin) * 0.04
    county_ax.set_xlim(extent.XMin - pad_x, extent.XMax + pad_x)
    county_ax.set_ylim(extent.YMin - pad_y, extent.YMax + pad_y)
    draw_top_tract_outlines(county_ax, tracts_fc, summary, outline_width=1.1, halo_width=2.0, show_badges=False)
    draw_scale_bar(main_ax, 5, location=(0.62, 0.07))
    draw_north_arrow(main_ax)

    class_counts = summary["CONCERN_CLASS"].value_counts().reindex(["Low", "Medium", "High"]).fillna(0).astype(int)
    primary_count = int(arcpy.management.GetCount(str(primary_resources_fc))[0])
    all_count = int(arcpy.management.GetCount(str(all_resources_fc))[0])
    fig.text(0.045, 0.955, "Spokane Cooling Access & Heat Risk Screening", fontsize=19, weight="bold", ha="left")
    fig.text(
        0.045,
        0.925,
        f"Relative score for heat risk, social vulnerability, vehicle access, and cooling-resource distance | "
        f"not an official designation | {primary_count} scored cooling resources | {all_count} mapped resources",
        fontsize=8.9,
        color="#4a4f52",
        ha="left",
    )

    draw_grouped_legend(fig, colors, class_counts)

    top = summary.head(4).copy()
    info_ax.text(0, 1.0, "Key Finding", fontsize=11.2, weight="bold", color="#222222", ha="left", va="top")
    info_ax.text(
        0,
        0.935,
        textwrap.fill(
            "Use the ranked tracts to target cooling outreach, pop-up cooling options, and site verification where heat exposure and access gaps stack together.",
            46,
        ),
        fontsize=8.0,
        color="#3f4447",
        ha="left",
        va="top",
        linespacing=1.18,
    )
    info_ax.text(0, 0.775, "Top Priority Tracts", fontsize=11.2, weight="bold", color="#222222", ha="left", va="top")
    info_ax.text(0, 0.741, "Countywide rank; detail map labels visible top tracts.", fontsize=7.4, color="#4a4f52", ha="left", va="top")
    info_ax.text(0.50, 0.700, "H", fontsize=7.4, weight="bold", color="#4a4f52", ha="center", va="top")
    info_ax.text(0.57, 0.700, "S", fontsize=7.4, weight="bold", color="#4a4f52", ha="center", va="top")
    info_ax.text(0.64, 0.700, "V", fontsize=7.4, weight="bold", color="#4a4f52", ha="center", va="top")
    info_ax.text(0.71, 0.700, "A", fontsize=7.4, weight="bold", color="#4a4f52", ha="center", va="top")
    info_ax.text(0.80, 0.700, "Total | mi", fontsize=7.4, weight="bold", color="#4a4f52", ha="left", va="top")
    y = 0.665
    for rank, (_, row) in enumerate(top.iterrows(), start=1):
        tract = row["NAME"].replace("Census Tract ", "").replace(", Spokane, WA", "")
        info_ax.text(
            0.015,
            y - 0.002,
            str(rank),
            fontsize=7.2,
            weight="bold",
            ha="center",
            va="center",
            color="white",
            bbox={"boxstyle": "round,pad=0.18", "facecolor": "#1f4e5f", "edgecolor": "none", "alpha": 0.96},
        )
        info_ax.text(0.06, y, f"Tract {tract}", fontsize=8.5, weight="bold", ha="left", va="top", color="#222222")
        info_ax.text(0.50, y, f'{int(row["HEAT_CONCERN_SCORE"])}', fontsize=8.0, ha="center", va="top", color="#4a4f52")
        info_ax.text(0.57, y, f'{int(row["SOVI_CONCERN_SCORE"])}', fontsize=8.0, ha="center", va="top", color="#4a4f52")
        info_ax.text(0.64, y, f'{int(row["TRANSPORT_BARRIER_SCORE"])}', fontsize=8.0, ha="center", va="top", color="#4a4f52")
        info_ax.text(0.71, y, f'{int(row["COOLING_ACCESS_SCORE"])}', fontsize=8.0, ha="center", va="top", color="#4a4f52")
        info_ax.text(
            0.80,
            y,
            f'{int(row["FINAL_CONCERN_SCORE"])} | {row["NEAREST_COOLING_MI"]:.1f}',
            fontsize=8.0,
            ha="left",
            va="top",
            color="#4a4f52",
        )
        y -= 0.056

    info_ax.plot([0, 1], [y + 0.023, y + 0.023], color="#d5d1c8", linewidth=0.8)
    draw_component_chart(info_ax, top, y - 0.018)
    info_ax.text(
        0,
        0.128,
        "H: heat | S: social vulnerability | V: vehicle-access barrier | A: cooling access. Each factor is scored 0-3.",
        fontsize=7.2,
        color="#4a4f52",
        ha="left",
        va="top",
        wrap=True,
    )
    info_ax.text(0, 0.070, "Caution", fontsize=8.4, weight="bold", color="#222222", ha="left", va="top")
    info_ax.text(
        0,
        0.044,
        textwrap.fill("Distances use tract internal points. Facility status, hours, capacity, and transit travel time are not modeled.", 50),
        fontsize=7.1,
        color="#4a4f52",
        ha="left",
        va="top",
        linespacing=1.15,
    )
    info_ax.set_xlim(0, 1)
    info_ax.set_ylim(0, 1)

    fig.text(
        0.045,
        0.006,
        "Sources: SRHD/Gonzaga Spokane Regional Cooling Resources; Census TIGER/Line 2024; Census Reporter ACS; FEMA National Risk Index.",
        ha="left",
        va="bottom",
        fontsize=6.8,
        color="#6b7175",
    )
    fig.text(
        0.985,
        0.006,
        "By: Victor Suarez | (c) 2026 Victor Suarez",
        ha="right",
        va="bottom",
        fontsize=6.8,
        color="#6b7175",
    )

    fig.savefig(MAPS / "spokane_cooling_access_heat_risk_map.png", dpi=220)
    fig.savefig(MAPS / "spokane_cooling_access_heat_risk_map.pdf")
    plt.close(fig)


def draw_chart(summary: pd.DataFrame) -> None:
    order = ["Low", "Medium", "High"]
    colors = ["#83bfd8", "#f2c45f", "#c84f4a"]
    counts = summary["CONCERN_CLASS"].value_counts().reindex(order).fillna(0)
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    bars = ax.bar(order, counts.values, color=colors, edgecolor="#2f3437", linewidth=0.6)
    ax.set_title("Census Tracts by Cooling Access & Heat Risk Concern", fontsize=13, weight="bold", loc="left")
    ax.set_ylabel("Tract count")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.25)
    for bar in bars:
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5, f"{int(bar.get_height())}", ha="center")
    fig.tight_layout()
    fig.savefig(FIGURES / "concern_class_counts.png", dpi=220)
    plt.close(fig)


def draw_top_tracts_chart(summary: pd.DataFrame) -> None:
    top = summary.head(10).sort_values("FINAL_CONCERN_SCORE")
    labels = top["NAME"].str.replace(", Spokane, WA", "", regex=False)
    fig, ax = plt.subplots(figsize=(8.4, 5.2))
    ax.barh(labels, top["FINAL_CONCERN_SCORE"], color="#c84f4a", edgecolor="#2f3437", linewidth=0.5)
    ax.set_xlim(0, 12.5)
    ax.set_xlabel("Final concern score")
    ax.set_title("Top 10 High-Concern Census Tracts", fontsize=13, weight="bold", loc="left")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", alpha=0.25)
    for y, (_, row) in enumerate(top.iterrows()):
        ax.text(
            row["FINAL_CONCERN_SCORE"] + 0.15,
            y,
            f'{row["NEAREST_COOLING_MI"]:.1f} mi to nearest center',
            va="center",
            fontsize=8,
            color="#4a4f52",
        )
    fig.tight_layout()
    fig.savefig(FIGURES / "top_high_concern_tracts.png", dpi=220)
    plt.close(fig)


def access_distance_class(distance: float | None) -> str:
    if distance is None or pd.isna(distance):
        return "No value"
    if distance <= 1.5:
        return "0-1.5 mi"
    if distance <= 3:
        return "1.5-3 mi"
    if distance <= 5:
        return "3-5 mi"
    return ">5 mi"


def draw_access_distance_map(
    tracts_fc: Path,
    county_fc: Path,
    roads_fc: Path,
    all_resources_fc: Path,
    summary: pd.DataFrame,
) -> None:
    colors = {
        "0-1.5 mi": "#d9f0d3",
        "1.5-3 mi": "#f6e3a1",
        "3-5 mi": "#e8a16f",
        ">5 mi": "#b85852",
        "No value": "#dddddd",
    }
    fig = plt.figure(figsize=(11, 8), facecolor="white")
    ax = fig.add_axes([0.055, 0.13, 0.72, 0.74])
    info_ax = fig.add_axes([0.80, 0.18, 0.16, 0.62])
    info_ax.axis("off")

    ax.set_facecolor("#f8f7f2")
    for geom, distance in arcpy.da.SearchCursor(str(tracts_fc), ["SHAPE@", "NEAREST_COOLING_MI"]):
        cls = access_distance_class(distance)
        for part in polygon_parts(geom):
            ax.add_patch(
                patches.Polygon(
                    part,
                    closed=True,
                    facecolor=colors[cls],
                    edgecolor="#ffffff",
                    linewidth=0.45,
                    zorder=1,
                )
            )

    for geom, mtfcc in arcpy.da.SearchCursor(str(roads_fc), ["SHAPE@", "MTFCC"]):
        color = "#8e8b85" if mtfcc == "S1100" else "#c2bdb5"
        width = 0.9 if mtfcc == "S1100" else 0.45
        for part in line_parts(geom):
            xs, ys = zip(*part)
            ax.plot(xs, ys, color=color, linewidth=width, alpha=0.58, zorder=3)

    primary_by_group = {
        "Library": ([], []),
        "Community/recreation": ([], []),
        "Senior/community": ([], []),
        "Other cooling space": ([], []),
    }
    for geom, access_use, resource_type in arcpy.da.SearchCursor(str(all_resources_fc), ["SHAPE@", "AccessUse", "ResourceType"]):
        if access_use == 1:
            xs, ys = primary_by_group[facility_group(resource_type)]
            xs.append(geom.centroid.X)
            ys.append(geom.centroid.Y)
    symbol_specs = {
        "Library": {"marker": "P", "color": "#155e8a", "size": 54},
        "Community/recreation": {"marker": "s", "color": "#206f5b", "size": 42},
        "Senior/community": {"marker": "^", "color": "#6f4e9b", "size": 48},
        "Other cooling space": {"marker": "D", "color": "#9a5a20", "size": 38},
    }
    for group, (xs, ys) in primary_by_group.items():
        spec = symbol_specs[group]
        ax.scatter(xs, ys, s=spec["size"], marker=spec["marker"], c=spec["color"], edgecolors="white", linewidths=0.75, zorder=6)

    for geom in arcpy.da.SearchCursor(str(county_fc), ["SHAPE@"]):
        for part in polygon_parts(geom[0]):
            ax.add_patch(patches.Polygon(part, closed=True, fill=False, edgecolor="#2f3437", linewidth=1.0, zorder=7))

    set_extent_from_wgs(ax, -117.52, 47.58, -117.18, 47.76)
    ax.set_aspect("equal")
    ax.axis("off")
    draw_scale_bar(ax, 5, location=(0.055, 0.055))

    fig.text(0.055, 0.94, "Cooling Center/Space Access Distance", fontsize=18, weight="bold", ha="left")
    fig.text(
        0.055,
        0.91,
        "Straight-line distance from Census tract internal point to nearest Gonzaga/SRHD cooling center or cooling space",
        fontsize=9,
        color="#4a4f52",
        ha="left",
    )

    counts = summary["NEAREST_COOLING_MI"].apply(access_distance_class).value_counts().reindex(
        ["0-1.5 mi", "1.5-3 mi", "3-5 mi", ">5 mi"]
    ).fillna(0).astype(int)
    info_ax.text(0, 1, "Distance Classes", fontsize=11, weight="bold", ha="left", va="top")
    y = 0.90
    for label in ["0-1.5 mi", "1.5-3 mi", "3-5 mi", ">5 mi"]:
        info_ax.add_patch(patches.Rectangle((0, y - 0.035), 0.14, 0.035, facecolor=colors[label], edgecolor="none"))
        info_ax.text(0.18, y - 0.017, f"{label} ({counts[label]})", fontsize=8.6, ha="left", va="center")
        y -= 0.08
    info_ax.text(
        0,
        y - 0.02,
        textwrap.fill("This map isolates physical proximity only. It does not include heat, vulnerability, transit, operating hours, or facility capacity.", 33),
        fontsize=8.2,
        color="#3f4447",
        ha="left",
        va="top",
        linespacing=1.25,
    )
    fig.text(
        0.055,
        0.025,
        "Sources: SRHD/Gonzaga Spokane Regional Cooling Resources; Census TIGER/Line 2024.",
        ha="left",
        fontsize=7.5,
        color="#4a4f52",
    )
    fig.savefig(MAPS / "spokane_cooling_access_distance_map.png", dpi=220)
    fig.savefig(MAPS / "spokane_cooling_access_distance_map.pdf")
    plt.close(fig)


def draw_access_gap_chart(summary: pd.DataFrame) -> None:
    top = summary.sort_values("NEAREST_COOLING_MI", ascending=False).head(10).sort_values("NEAREST_COOLING_MI")
    labels = top["NAME"].str.replace(", Spokane, WA", "", regex=False)
    fig, ax = plt.subplots(figsize=(8.4, 5.2))
    ax.barh(labels, top["NEAREST_COOLING_MI"], color="#e8a16f", edgecolor="#2f3437", linewidth=0.5)
    ax.set_xlabel("Miles to nearest cooling center/space")
    ax.set_title("Largest Cooling Center/Space Access Gaps", fontsize=13, weight="bold", loc="left")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", alpha=0.25)
    for y, (_, row) in enumerate(top.iterrows()):
        ax.text(row["NEAREST_COOLING_MI"] + 0.12, y, f'{row["NEAREST_COOLING_MI"]:.1f} mi', va="center", fontsize=8.5, color="#4a4f52")
    fig.tight_layout()
    fig.savefig(FIGURES / "largest_access_gaps.png", dpi=220)
    plt.close(fig)


def main() -> None:
    ensure_dirs()
    arcpy.env.workspace = str(GDB)
    arcpy.env.overwriteOutput = True
    cleanup_obsolete_outputs()

    tracts_fc, county_fc = prepare_boundaries()
    roads_fc = prepare_roads()
    acs = fetch_acs()
    nri = fetch_nri()
    primary_resources_fc, all_resources_fc = fetch_gonzaga_cooling_resources(county_fc)
    summary = build_summary(tracts_fc, primary_resources_fc, acs, nri)
    draw_map(tracts_fc, county_fc, roads_fc, primary_resources_fc, all_resources_fc, summary)
    draw_access_distance_map(tracts_fc, county_fc, roads_fc, all_resources_fc, summary)
    draw_chart(summary)
    draw_top_tracts_chart(summary)
    draw_access_gap_chart(summary)

    print(f"Created {PROCESSED / 'cooling_heat_risk_tract_summary.csv'}")
    print(f"Created {OUTPUTS / 'high_concern_tracts.csv'}")
    print(f"Created {MAPS / 'spokane_cooling_access_heat_risk_map.png'}")
    print(f"Created {MAPS / 'spokane_cooling_access_distance_map.png'}")
    print(f"Created {FIGURES / 'concern_class_counts.png'}")
    print(f"Created {FIGURES / 'top_high_concern_tracts.png'}")
    print(f"Created {FIGURES / 'largest_access_gaps.png'}")


if __name__ == "__main__":
    main()
