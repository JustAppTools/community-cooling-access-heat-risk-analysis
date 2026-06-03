# Community Cooling Access & Heat Risk Analysis

## Project Overview

This ArcGIS portfolio project analyzes neighborhood heat-risk exposure and access to cooling resources using public facility, Census, FEMA heat-risk, and social vulnerability data.

The project is intended to demonstrate a practical GIS screening workflow for community planning: identifying places where heat exposure, social vulnerability, and limited access to cooling resources may overlap.

## Research Question

Which neighborhoods have higher heat-risk concern and limited access to cooling resources such as libraries, community centers, parks, transit-accessible public facilities, or official cooling centers?

## Study Area

Study area: Spokane County, Washington.

Spokane County is large enough to show urban/suburban/rural variation, has meaningful summer heat exposure, and is manageable for a portfolio-scale ArcGIS Pro project. The workflow can be adapted to another city or county if a better local cooling-center dataset is selected.

## Data Sources

Public data sources used in the first analysis build:

- U.S. Census Bureau TIGER/Line 2024 county and tract boundaries.
- Census Reporter ACS tables for population, poverty, age sensitivity, and no-vehicle households.
- FEMA National Risk Index Census Tracts FeatureServer for heat-wave risk and social vulnerability scores.
- OpenStreetMap / Overpass for library and community center cooling-resource candidates.

See `data_source_references.txt` for working source links.

## Methods

The project organizes raw source data, processed feature classes, map exports, and documentation in a reproducible ArcGIS Pro project structure.

Current workflow:

1. Define Spokane County as the study boundary.
2. Import 2024 TIGER/Line Census tracts and county boundary.
3. Pull ACS tract indicators from Census Reporter.
4. Pull FEMA National Risk Index heat-wave and social vulnerability fields.
5. Query OpenStreetMap for libraries and community centers, then clip candidates to Spokane County.
6. Calculate each tract centroid's nearest distance to a cooling-resource candidate.
7. Score each tract from 4 to 12 using heat-wave risk, social vulnerability, no-vehicle households, and nearest cooling-resource distance.
8. Export a final screening map, chart, tract summary table, and high-concern tract table.

## Outputs

- ArcGIS Pro project: `Community_Cooling_Access_Heat_Risk.aprx`
- File geodatabase: `data_processed/Community_Cooling_Access_Heat_Risk.gdb`
- Final map export: `outputs/maps/spokane_cooling_access_heat_risk_map.png`
- Final map PDF: `outputs/maps/spokane_cooling_access_heat_risk_map.pdf`
- Concern-class chart: `outputs/figures/concern_class_counts.png`
- Tract summary: `data_processed/cooling_heat_risk_tract_summary.csv`
- Ranked high-concern table: `outputs/high_concern_tracts.csv`
- Reproducible build script: `scripts/build_analysis.py`

## Visual Outputs

![Cooling access and heat risk screening map](outputs/maps/spokane_cooling_access_heat_risk_map.png)

![Concern class counts](outputs/figures/concern_class_counts.png)

## Results Summary

The first analysis build includes 130 Spokane County Census tracts and 46 cooling-resource candidates clipped to the county boundary: 28 libraries and 18 community centers.

Concern class counts:

- Low: 32 tracts
- Medium: 66 tracts
- High: 32 tracts

Top high-concern tracts by final score:

| Tract | Class | Score | Nearest cooling resource (mi) | No-vehicle households (%) | FEMA heat-wave risk score |
|---|---:|---:|---:|---:|---:|
| Census Tract 136 | High | 12 | 2.65 | 8.50 | 73.68 |
| Census Tract 117.02 | High | 12 | 2.20 | 9.11 | 79.28 |
| Census Tract 123 | High | 12 | 2.06 | 15.76 | 81.92 |
| Census Tract 104.03 | High | 11 | 3.08 | 5.82 | 64.37 |
| Census Tract 118 | High | 11 | 1.89 | 17.09 | 69.82 |

## Limitations

This is an independent portfolio GIS screening project. It is not official emergency-management, public-health, or heat-response guidance. Cooling-resource availability can change by day, season, staffing, operating hours, and emergency activation status. The OpenStreetMap facility layer identifies candidate public cooling resources, not officially activated cooling centers. Any operational use would require validation with local agencies.

## Skills Demonstrated

- ArcGIS Pro project organization
- Public GIS data acquisition
- Coordinate systems and projections
- Demographic and vulnerability overlay
- Proximity and access analysis
- Attribute calculations and index scoring
- Cartographic layout design
- Reproducible GIS documentation
