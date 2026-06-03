"""Build the first analysis outputs for the cooling access heat-risk project.

Run with the ArcGIS Pro Python interpreter:
    "C:\\Program Files\\ArcGIS\\Pro\\bin\\Python\\envs\\arcgispro-py3\\python.exe" scripts\\build_analysis.py
"""

from __future__ import annotations

import csv
import json
import math
import time
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
CENSUS_REPORTER_URL = (
    "https://api.censusreporter.org/1.0/data/show/latest"
    "?table_ids=B01001,B17001,B08201&geo_ids=140|05000US53063"
)
NRI_QUERY_URL = (
    "https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/"
    "National_Risk_Index_Census_Tracts/FeatureServer/0/query"
)


def ensure_dirs() -> None:
    for path in [RAW, PROCESSED, MAPS, FIGURES, RAW / "tiger", RAW / "osm", RAW / "acs", RAW / "nri"]:
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


def overpass_query() -> dict | None:
    query = """[out:json][timeout:45];
(
  node["amenity"~"library|community_centre"](47.20,-117.90,48.10,-116.90);
  way["amenity"~"library|community_centre"](47.20,-117.90,48.10,-116.90);
  relation["amenity"~"library|community_centre"](47.20,-117.90,48.10,-116.90);
);
out center tags;"""
    endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass.openstreetmap.ru/api/interpreter",
    ]
    for endpoint in endpoints:
        try:
            response = requests.post(
                endpoint,
                data={"data": query},
                timeout=75,
                headers={"User-Agent": "JustAppTools GIS portfolio project"},
            )
            if response.ok:
                return response.json()
            print(f"Overpass returned {response.status_code} from {endpoint}")
        except Exception as exc:
            print(f"Overpass failed from {endpoint}: {exc}")
        time.sleep(2)
    return None


def fallback_cooling_resources() -> list[dict]:
    return [
        {"name": "Central Library", "category": "library", "lat": 47.6579, "lon": -117.4234},
        {"name": "Shadle Park Library", "category": "library", "lat": 47.7062, "lon": -117.4385},
        {"name": "Hillyard Library", "category": "library", "lat": 47.7135, "lon": -117.3578},
        {"name": "Liberty Park Library", "category": "library", "lat": 47.6572, "lon": -117.3794},
        {"name": "South Hill Library", "category": "library", "lat": 47.6307, "lon": -117.4018},
        {"name": "Indian Trail Library", "category": "library", "lat": 47.7524, "lon": -117.4367},
        {"name": "Spokane Valley Library", "category": "library", "lat": 47.6573, "lon": -117.2395},
        {"name": "Argonne Library", "category": "library", "lat": 47.6799, "lon": -117.2823},
        {"name": "Cheney Library", "category": "library", "lat": 47.4881, "lon": -117.5784},
        {"name": "Deer Park Library", "category": "library", "lat": 47.9546, "lon": -117.4761},
        {"name": "Medical Lake Library", "category": "library", "lat": 47.5724, "lon": -117.6828},
        {"name": "Moran Prairie Library", "category": "library", "lat": 47.5945, "lon": -117.3972},
    ]


def fetch_cooling_resources(county_fc: Path) -> Path:
    raw_json = RAW / "osm" / "osm_cooling_resource_candidates.json"
    resources_csv = RAW / "osm" / "osm_cooling_resource_candidates.csv"
    payload = overpass_query()
    resources = []

    if payload:
        raw_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        for element in payload.get("elements", []):
            tags = element.get("tags", {})
            lat = element.get("lat") or element.get("center", {}).get("lat")
            lon = element.get("lon") or element.get("center", {}).get("lon")
            if lat is None or lon is None:
                continue
            amenity = tags.get("amenity", "unknown")
            resources.append(
                {
                    "name": tags.get("name") or f"OSM {amenity} {element.get('id')}",
                    "category": amenity,
                    "lat": float(lat),
                    "lon": float(lon),
                }
            )
    else:
        resources = fallback_cooling_resources()
        raw_json.write_text(json.dumps({"fallback_resources": resources}, indent=2), encoding="utf-8")

    with resources_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "category", "lat", "lon"])
        writer.writeheader()
        writer.writerows(resources)

    points_wgs = GDB / "Cooling_Resource_Candidates_WGS84"
    points_utm = GDB / "Cooling_Resource_Candidates_UTM11N"
    points_in_county = GDB / "Cooling_Resource_Candidates"
    delete_if_exists(points_wgs)
    arcpy.management.CreateFeatureclass(str(GDB), points_wgs.name, "POINT", spatial_reference=WGS84)
    arcpy.management.AddField(str(points_wgs), "Name", "TEXT", field_length=160)
    arcpy.management.AddField(str(points_wgs), "Category", "TEXT", field_length=80)
    with arcpy.da.InsertCursor(str(points_wgs), ["SHAPE@XY", "Name", "Category"]) as cursor:
        for item in resources:
            cursor.insertRow(((item["lon"], item["lat"]), item["name"][:160], item["category"][:80]))

    delete_if_exists(points_utm)
    arcpy.management.Project(str(points_wgs), str(points_utm), ANALYSIS_SR)
    delete_if_exists(points_in_county)
    arcpy.management.MakeFeatureLayer(str(points_utm), "cooling_candidates_lyr")
    arcpy.management.SelectLayerByLocation("cooling_candidates_lyr", "WITHIN", str(county_fc))
    arcpy.management.CopyFeatures("cooling_candidates_lyr", str(points_in_county))
    return points_in_county


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


def compute_access_metrics(tracts_fc: Path, resources_fc: Path) -> dict[str, dict]:
    resources = [row[0] for row in arcpy.da.SearchCursor(str(resources_fc), ["SHAPE@"])]
    metrics = {}
    for geoid, geom in arcpy.da.SearchCursor(str(tracts_fc), ["GEOID", "SHAPE@"]):
        point = arcpy.PointGeometry(geom.trueCentroid, ANALYSIS_SR)
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


def draw_map(tracts_fc: Path, county_fc: Path, resources_fc: Path, summary: pd.DataFrame) -> None:
    colors = {"Low": "#bfe3c0", "Medium": "#ffe08a", "High": "#df6b57"}
    fig, ax = plt.subplots(figsize=(11, 8.5))
    ax.set_facecolor("#f6f7f5")

    for geom, concern in arcpy.da.SearchCursor(str(tracts_fc), ["SHAPE@", "CONCERN_CLASS"]):
        for part in polygon_parts(geom):
            ax.add_patch(
                patches.Polygon(
                    part,
                    closed=True,
                    facecolor=colors.get(concern, "#dddddd"),
                    edgecolor="#ffffff",
                    linewidth=0.45,
                )
            )

    for geom in arcpy.da.SearchCursor(str(county_fc), ["SHAPE@"]):
        for part in polygon_parts(geom[0]):
            ax.add_patch(patches.Polygon(part, closed=True, fill=False, edgecolor="#2f3437", linewidth=1.1))

    xs, ys, categories = [], [], []
    for geom, category in arcpy.da.SearchCursor(str(resources_fc), ["SHAPE@", "Category"]):
        xs.append(geom.centroid.X)
        ys.append(geom.centroid.Y)
        categories.append(category)
    ax.scatter(xs, ys, s=32, c="#176d9c", edgecolors="white", linewidths=0.8, zorder=5)

    extent = arcpy.Describe(str(county_fc)).extent
    pad_x = (extent.XMax - extent.XMin) * 0.04
    pad_y = (extent.YMax - extent.YMin) * 0.04
    ax.set_xlim(extent.XMin - pad_x, extent.XMax + pad_x)
    ax.set_ylim(extent.YMin - pad_y, extent.YMax + pad_y)
    ax.set_aspect("equal")
    ax.axis("off")

    class_counts = summary["CONCERN_CLASS"].value_counts().reindex(["Low", "Medium", "High"]).fillna(0).astype(int)
    resource_counts = Counter(categories)
    subtitle = (
        f"{STUDY_NAME} | {len(summary)} Census tracts | "
        f"{len(xs)} cooling-resource candidates "
        f"({', '.join(f'{k}: {v}' for k, v in sorted(resource_counts.items()))})"
    )
    ax.set_title("Cooling Access & Heat Risk Screening", fontsize=18, weight="bold", loc="left", pad=14)
    ax.text(0, 1.01, subtitle, transform=ax.transAxes, fontsize=9.5, color="#4a4f52")

    legend_items = [
        patches.Patch(facecolor=colors["Low"], edgecolor="white", label=f"Low concern ({class_counts['Low']})"),
        patches.Patch(facecolor=colors["Medium"], edgecolor="white", label=f"Medium concern ({class_counts['Medium']})"),
        patches.Patch(facecolor=colors["High"], edgecolor="white", label=f"High concern ({class_counts['High']})"),
    ]
    ax.legend(handles=legend_items, loc="lower left", frameon=True, framealpha=0.95, facecolor="white")
    fig.text(
        0.5,
        0.018,
        "Sources: Census TIGER/Line 2024; Census Reporter ACS latest; FEMA National Risk Index; OpenStreetMap.",
        ha="center",
        va="bottom",
        fontsize=7.5,
        color="#4a4f52",
    )

    fig.tight_layout(rect=[0, 0.04, 1, 1])
    fig.savefig(MAPS / "spokane_cooling_access_heat_risk_map.png", dpi=220)
    fig.savefig(MAPS / "spokane_cooling_access_heat_risk_map.pdf")
    plt.close(fig)


def draw_chart(summary: pd.DataFrame) -> None:
    order = ["Low", "Medium", "High"]
    colors = ["#88c58a", "#f0c95a", "#d95847"]
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


def main() -> None:
    ensure_dirs()
    arcpy.env.workspace = str(GDB)
    arcpy.env.overwriteOutput = True

    tracts_fc, county_fc = prepare_boundaries()
    acs = fetch_acs()
    nri = fetch_nri()
    resources_fc = fetch_cooling_resources(county_fc)
    summary = build_summary(tracts_fc, resources_fc, acs, nri)
    draw_map(tracts_fc, county_fc, resources_fc, summary)
    draw_chart(summary)

    print(f"Created {PROCESSED / 'cooling_heat_risk_tract_summary.csv'}")
    print(f"Created {OUTPUTS / 'high_concern_tracts.csv'}")
    print(f"Created {MAPS / 'spokane_cooling_access_heat_risk_map.png'}")
    print(f"Created {FIGURES / 'concern_class_counts.png'}")


if __name__ == "__main__":
    main()
