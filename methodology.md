# Methodology

## Purpose

This project screens for neighborhoods where heat exposure and limited access to cooling resources may overlap. The analysis is designed for portfolio communication and early planning exploration, not operational heat-response decision-making.

## Unit of Analysis

The planned unit of analysis is Census tracts or block groups within the selected study area. Block groups provide finer spatial detail, while tracts are easier to communicate and often work better with public vulnerability datasets.

## Core Inputs

Planned input categories:

- Study boundary: county or city boundary.
- Cooling resources: libraries, community centers, parks, official cooling centers, public shelters, or other public facilities.
- Vulnerable population indicators: older adults, young children, poverty, disability, limited English, no vehicle access, or CDC/ATSDR SVI percentile.
- Heat exposure indicators: developed land, impervious surface, low tree canopy proxy, or FEMA heat-wave risk context.
- Access context: distance to nearest cooling resource and count of resources within a defined travel buffer.

## Processing Steps

1. Create a project file geodatabase in `data_processed/`.
2. Import or reference source datasets from `data_raw/` and public web services.
3. Project analysis layers to an appropriate local projected coordinate system.
4. Clip all relevant layers to the study area plus a surrounding buffer.
5. Standardize cooling-resource categories and remove duplicates.
6. Calculate nearest-distance values from each Census geography to cooling resources.
7. Summarize cooling-resource counts within selected distances.
8. Join demographic and vulnerability attributes to the analysis geography.
9. Normalize selected indicators into low, medium, and high concern classes.
10. Combine indicators into a final `Cooling_Access_Heat_Risk_Score`.

## Candidate Score Design

The starter score can use a simple additive model:

- Heat exposure concern: 1 to 3
- Social vulnerability concern: 1 to 3
- No-vehicle or transportation-barrier concern: 1 to 3
- Cooling-resource distance concern: 1 to 3

Final score range: 4 to 12.

Candidate final classes:

- Low: 4 to 6
- Medium: 7 to 9
- High: 10 to 12

Breaks should be reviewed after the actual data distribution is known. Tertiles are acceptable for portfolio screening, but clearly state that they are relative within the study area.

## Planned Outputs

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

## Limitations

The project does not measure indoor temperature, household air-conditioning access, real-time cooling-center activation, travel time, transit schedules, building capacity, operating hours, or individual health outcomes. Distances should be interpreted as screening indicators only.
