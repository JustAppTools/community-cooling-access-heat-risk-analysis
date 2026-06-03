# Community Cooling Access & Heat Risk Analysis

## Project Overview

This ArcGIS portfolio project analyzes neighborhood heat-risk exposure and access to cooling resources using public facility, Census, land cover, and social vulnerability data.

The project is intended to demonstrate a practical GIS screening workflow for community planning: identifying places where heat exposure, social vulnerability, and limited access to cooling resources may overlap.

## Research Question

Which neighborhoods have higher heat-risk concern and limited access to cooling resources such as libraries, community centers, parks, transit-accessible public facilities, or official cooling centers?

## Planned Study Area

Initial study area: Spokane County, Washington.

Spokane County is large enough to show urban/suburban/rural variation, has meaningful summer heat exposure, and is manageable for a portfolio-scale ArcGIS Pro project. The workflow can be adapted to another city or county if a better local cooling-center dataset is selected.

## Data Sources

Planned public data sources include:

- U.S. Census Bureau TIGER/Line boundaries and roads.
- American Community Survey demographic and transportation variables through Census data or ArcGIS Living Atlas.
- CDC/ATSDR Social Vulnerability Index.
- National Land Cover Database or similar land-cover/impervious-surface data.
- Local public facilities such as libraries, community centers, parks, cooling centers, or emergency shelters.
- Optional FEMA National Risk Index heat-wave risk data for contextual hazard screening.

See `data_source_references.txt` for working source links.

## Planned Methods

The project will organize raw source data, processed feature classes, map exports, and documentation in a reproducible ArcGIS Pro project structure.

Planned workflow:

1. Define the county or city study boundary.
2. Collect public cooling-resource candidates.
3. Prepare Census tract or block group demographics.
4. Add heat-exposure indicators such as impervious surface, tree canopy proxy, or land-cover class.
5. Calculate distance or service-area access to cooling resources.
6. Build a simple heat-risk and cooling-access concern score.
7. Map high-concern neighborhoods and summarize ranked results.

## Expected Outputs

- ArcGIS Pro project: `Community_Cooling_Access_Heat_Risk.aprx`
- File geodatabase: `data_processed/Community_Cooling_Access_Heat_Risk.gdb`
- Final map export in `outputs/maps/`
- Supporting charts or figures in `outputs/figures/`
- Portfolio-ready methodology notes in `methodology.md`

## Limitations

This is an independent portfolio GIS screening project. It is not official emergency-management, public-health, or heat-response guidance. Cooling-resource availability can change by day, season, staffing, operating hours, and emergency activation status. Any operational use would require validation with local agencies.

## Skills Demonstrated

- ArcGIS Pro project organization
- Public GIS data acquisition
- Coordinate systems and projections
- Demographic and vulnerability overlay
- Proximity and access analysis
- Raster/vector interpretation
- Attribute calculations and index scoring
- Cartographic layout design
- Reproducible GIS documentation
