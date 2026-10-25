# TerraScope datasets: what is installed, what is missing, what to download

Audited 2026-10-25 on the development machine (`data-cache\`). Sizes are measured, not estimated, unless marked.

## Installed

| Dataset | Where (`data-cache\`) | Size | Licence | What it enables |
|---|---|---|---|---|
| India boundary (geoBoundaries gbOpen IND ADM1) | `india\` | 49 MB | CC BY 2.5 IN | Coverage check (India only), state attribution |
| Place search (GeoNames gazetteer and postal codes) | `places\places.sqlite`, `downloads\geonames\` | 191 MB + 19 MB | CC BY 4.0 (credit GeoNames) | Search suggestions while typing |
| OpenStreetMap southern-zone extract (Geofabrik), dated 2026-10-04 | `downloads\southern-zone-261004.osm.pbf` | 532 MB | ODbL 1.0 | Source for building regions in Andhra Pradesh, Karnataka, Kerala, Tamil Nadu, Telangana, Puducherry |
| Region `tamil-nadu` (Tamil Nadu and Puducherry) | `regions\tamil-nadu\osm.sqlite` | 279 MB | ODbL 1.0 | Road, school, hospital, bus and rail distances (accessibility); rivers, canals and tanks |
| Previous Tamil Nadu build (backup, unused) | `regions\tamil-nadu\previous-build-2026-10-06\` | 276 MB | ODbL 1.0 | Nothing; can be deleted |
| Copernicus DEM GLO-30, 37 tiles (Tamil Nadu, Puducherry, one Andhra tile) | `rasters\dem\` | 1.2 GB | Copernicus DEM licence (free use) | Elevation; height relative to mapped water. Elsewhere read remotely |
| JRC Global Surface Water v1.4, 8 tiles (70-90°E, 0-20°N) | `rasters\gsw\` | 180 MB | Copernicus, free without restriction ("Source: EC JRC/Google") | Water seen on and around the plot, 1984-2021 |
| JRC river flood hazard maps v2.1.2 (tile index and cached parcel results) | `flood-hazard\` | <1 MB | CC BY 4.0 | River flooding by return period (tiles read remotely) |
| Caches | `satellite\sentinel2-cache.sqlite`, `flood-indicators-cache.json` | 7 MB | derived | Faster repeat analyses (Sentinel-2 measurements; surface-water, DEM and land-cover parcel results, 30 days) |

Read remotely, with no download or account: Sentinel-2 L2A and the Impact Observatory / Esri 10 m annual land cover
2017-2023 (CC BY 4.0), both from Microsoft Planetary Computer; the JRC flood tiles; Copernicus DEM outside the installed tiles.

Configuration (`.env`, values not shown): `GROQ_API_KEY` is empty, so reports show the rule-based summary, not an AI
explanation. `SATELLITE_DEMO_FALLBACK=false`, so no synthetic imagery is ever substituted. `RERA_SEED_PATH` is empty.

## Missing, and why

| Gap | Effect in the report | Fix |
|---|---|---|
| Regional OpenStreetMap for any state except Tamil Nadu and Puducherry | Road and school access "Unknown"; **no BUY / WAIT decision** (an unscored location factor withholds it) | `terrascope.cmd fetch-data <state>` (below) |
| State RERA data (only a MahaRERA seed format is supported; none configured) | RERA "Unknown" | Manual check on the state portal: rera.tn.gov.in, rera.ap.gov.in. No public API was found, and portals are not scraped |
| Land records and encumbrance | Title "Unknown"; always on the "before you pay" list | Manual: Tamil Nadu eservices.tn.gov.in (patta/chitta) and tnreginet.gov.in (EC); Andhra Pradesh meebhoomi.ap.gov.in (Adangal, 1B). Web lookups for individuals; not integrated, never automated, never treated as verification |
| Rainfall waterlogging, coastal flooding, observed flood footprints | Those mechanisms "Unknown" | See candidate sources below |
| Land prices | Not shown (removed in this version, J-58) | — |

## Download plan

1. **Andhra Pradesh** (needed for the Vijayawada plot):

   ```bat
   terrascope.cmd fetch-data andhra-pradesh
   ```

   - Downloads 37 Copernicus DEM tiles, **1.41 GB**, into `data-cache\rasters\dem\`.
   - Reuses the southern-zone OSM extract (covers 100% of the state) and the surface-water tiles already on disk:
     0 MB for those.
   - Builds `data-cache\regions\andhra-pradesh\osm.sqlite` (about 250-300 MB; the Tamil Nadu build took 9 minutes).
   - Needs about 1.7 GB plus 2 GB spare (the command checks). Free on 2026-10-25: 9.0 GB.
   - Enables road and school access (so a BUY / WAIT decision), distances to rivers, canals and tanks, and local DEM and
     surface-water reads.
2. **Karnataka, Kerala or Telangana**: the same command with that state's slug (`terrascope.cmd fetch-data --list`),
   only when you analyse plots there. The OSM extract is reused; DEM tile sizes have not been measured yet.
3. **Optional cleanup**: the unused previous Tamil Nadu build frees 276 MB. Delete it only on purpose.

## Candidate sources for flood, rainfall, terrain and drainage (researched 2026-10-25; none integrated)

| Source | What | Resolution / period | Licence (as found) | Notes |
|---|---|---|---|---|
| NRSC Flood Hazard Atlas, Andhra Pradesh (official) | Flood hazard categories from satellite flood maps | District level; 2000-2020 | Not found | Viewing on Bhuvan; no download found. Contact flood@nrsc.gov.in. Usable as a manual check link |
| Global Flood Database v1 (Cloud to Street / Dartmouth) | Observed flood extents, 913 events | 250 m; 2000-2018 | CC BY-NC 4.0 (Earth Engine catalogue) | Non-commercial only; observed, not modelled |
| WRI Aqueduct Floods v2 | Riverine and coastal inundation by return period | ~1 km; released 2020 | Not stated on WRI's page; secondary sources say CC BY 4.0 | Would fill the coastal gap; confirm the licence first |
| MERIT Hydro (HAND layer) | Height above nearest drainage | ~90 m | CC BY-NC 4.0 / ODbL dual; registration form | Would replace the terrain indicator with a real HAND figure; non-commercial |
| HydroSHEDS / HydroRIVERS | River network and basins | 15 arc-seconds | Free for scientific, educational and commercial use (official page); read the licence document | Drainage context |
| IMD gridded rainfall (official) | Daily rainfall | 0.25°; 1901-present | Terms not verified; long series reportedly sold | Rainfall climate, not waterlogging |
| CHIRPS | Daily rainfall | 0.05°; 1981-present | Public domain (Earth Engine catalogue) | Rainfall climate, not waterlogging |
| India-WRIS (official) | Rainfall, river and reservoir dashboards | Varies | NDSAP / 2013 hydro-met policy | Report downloads; no bulk data path found |

Rainfall alone does not show whether a plot waterlogs, and no free, permitted pluvial (rainfall-flood) model for India
was found. The two most useful next integrations would be Aqueduct coastal flooding (after confirming its licence) and
MERIT HAND (if non-commercial use is acceptable). Until then those mechanisms stay "Unknown".

Sources: [WRI Aqueduct Floods](https://datasets.wri.org/datasets/aqueduct-floods-hazard-maps),
[Aqueduct on Zenodo](https://zenodo.org/records/4646839), [MERIT Hydro](https://hydro.iis.u-tokyo.ac.jp/~yamadai/MERIT_Hydro),
[Global Flood Database](https://developers.google.com/earth-engine/datasets/catalog/GLOBAL_FLOOD_DB_MODIS_EVENTS_V1),
[CHIRPS](https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHG_CHIRPS_DAILY),
[HydroRIVERS](https://hydrosheds.org/page/hydrorivers),
[NRSC flood hazard atlases](https://www.nrsc.gov.in/sites/default/files/pdf/DMSP/StoryofMonth_ReleaseofFloodHazardAtlas_%20AP_%20WB.pdf),
[AP RERA](https://rera.ap.gov.in/RERA/Views/Home.aspx), [India-WRIS background](https://www.indiawaterportal.org/article/creating-repository-indias-water-resources-data).
