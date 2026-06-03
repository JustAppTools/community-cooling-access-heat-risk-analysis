# Methodology

## Purpose

This project screens for neighborhoods where heat exposure and limited access to cooling resources may overlap. The analysis is designed for portfolio communication and early planning exploration, not operational heat-response decision-making.

## Unit of Analysis

The planned unit of analysis is Census tracts or block groups within the selected study area. Block groups provide finer spatial detail, while tracts are easier to communicate and often work better with public vulnerability datasets.

## Core Inputs

Input categories used in the first build:

- Study boundary: Spokane County, Washington.
- Cooling resources: Gonzaga/SRHD regional cooling-resource layers, clipped to Spokane County.
- Vulnerable population indicators: ACS poverty, age-sensitive population, no-vehicle households, and FEMA National Risk Index social vulnerability score.
- Heat context: FEMA National Risk Index heat-wave risk score and heat-wave annualized frequency.
- Access context: distance from each tract's Census internal point to the nearest cooling center or cooling space, plus counts within 3 and 5 miles.

## Processing Steps

1. Create a project file geodatabase in `data_processed/`.
2. Import or reference source datasets from `data_raw/` and public web services.
3. Project analysis layers to an appropriate local projected coordinate system.
4. Clip all relevant layers to the study area plus a surrounding buffer.
5. Standardize cooling-resource categories and remove duplicates.
6. Separate cooling centers/spaces from supplemental resources such as parks, pools, splash pads, and drinking fountains.
7. Calculate nearest-distance values from each Census geography to cooling centers/spaces.
8. Summarize cooling-center/space counts within selected distances.
9. Join demographic and vulnerability attributes to the analysis geography.
10. Normalize selected indicators into low, medium, and high concern classes.
11. Combine indicators into a final `Cooling_Access_Heat_Risk_Score`.

## Candidate Score Design

The first-build score uses a simple additive model:

- FEMA heat-wave risk concern: 1 to 3
- FEMA social vulnerability concern: 1 to 3
- ACS no-vehicle household concern: 1 to 3
- Nearest cooling-center/space distance concern: 1 to 3

Final score range: 4 to 12.

Candidate final classes:

- Low: 4 to 6
- Medium: 7 to 9
- High: 10 to 12

The first build uses tertile breaks within Spokane County. These classes are relative screening classes, not absolute public-health thresholds.

## Outputs

The final map should show:

- Study area boundary.
- Census geography symbolized by final concern class.
- Cooling-resource points.
- Major roads or transit context where useful.
- At-a-glance summary of high-concern areas and resource counts.

Supporting outputs may include:

- Ranked table of highest-concern neighborhoods.
- Bar chart of concern-class counts.
- Small locator map or inset.

Current outputs:

- `outputs/maps/spokane_cooling_access_heat_risk_map.png`
- `outputs/maps/spokane_cooling_access_heat_risk_map.pdf`
- `outputs/maps/spokane_cooling_access_distance_map.png`
- `outputs/maps/spokane_cooling_access_distance_map.pdf`
- `outputs/figures/concern_class_counts.png`
- `outputs/figures/top_high_concern_tracts.png`
- `outputs/figures/largest_access_gaps.png`
- `data_processed/cooling_heat_risk_tract_summary.csv`
- `outputs/high_concern_tracts.csv`

The H/S/V/A shorthand used in the map callout means heat-wave risk, social vulnerability, vehicle-access barrier, and cooling-access distance.

## Limitations

The project does not measure indoor temperature, household air-conditioning access, real-time cooling-center activation, travel time, transit schedules, building capacity, operating hours, or individual health outcomes. Distances are straight-line distances from Census tract internal points and should be interpreted as screening indicators only.
