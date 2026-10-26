# TerraScope datasets: what is installed, what is missing, what to download

Audited 2026-10-25 on the development machine (`data-cache\`). Sizes are measured, not estimated, unless marked.

## Installed

| Dataset | Where (`data-cache\`) | Size | Licence | What it enables |
|---|---|---|---|---|
| India boundary (geoBoundaries gbOpen IND ADM1) | `india\` | 49 MB | CC BY 2.5 IN | Coverage check (India only), state attribution |
| Place search (GeoNames gazetteer and postal codes) | `places\places.sqlite`, `downloads\geonames\` | 191 MB + 19 MB | CC BY 4.0 (credit GeoNames) | Search suggestions while typing |
| OpenStreetMap southern-zone extract (Geofabrik), dated 2026-10-04 | `downloads\southern-zone-261004.osm.pbf` | 532 MB | ODbL 1.0 | Source for building regions in Andhra Pradesh, Karnataka, Kerala, Tamil Nadu, Telangana, Puducherry |
| Region `tamil-nadu` (Tamil Nadu and Puducherry) | `regions\tamil-nadu\osm.sqlite` | 279 MB | ODbL 1.0 | Road, school, hospital, bus and rail distances (accessibility); rivers, canals and tanks |
| Region `andhra-pradesh` (built 2026-10-25 from the same extract) | `regions\andhra-pradesh\osm.sqlite` | 204 MB | ODbL 1.0 | 572,665 road segments, 1,803 schools, 4,532 hospitals, 3,528 bus stops/stations, 565 railway stations, 32,399 water bodies, 11,473 waterways |
| Public-facility stores (built 2026-10-26 from the same extract) | `regions\tamil-nadu\public_land.sqlite`, `regions\andhra-pradesh\public_land.sqlite` | 5.0 MB + 3.1 MB | ODbL 1.0 | Courts (TN 91, AP 35), government offices, government schools and hospitals (by name or operator tag), stadiums and sports grounds, parks, railway land / stations / lines, defence areas (TN 71, AP 29), protected areas, burial grounds. Mapping only, never ownership |
| Previous Tamil Nadu build (backup, unused) | `regions\tamil-nadu\previous-build-2026-10-06\` | 276 MB | ODbL 1.0 | Nothing; can be deleted |
| Copernicus DEM GLO-30, 75 tiles (Tamil Nadu, Puducherry, Andhra Pradesh) | `rasters\dem\` | 2.5 GB | Copernicus DEM licence (free use) | Elevation; height relative to mapped water. Elsewhere read remotely |
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
| Regional OpenStreetMap for any state except Tamil Nadu, Puducherry and Andhra Pradesh | Road and school access "Unknown"; **no BUY / WAIT decision** (an unscored location factor withholds it) | `terrascope.cmd fetch-data <state>` (below) |
| State RERA data (only a MahaRERA seed format is supported; none configured) | RERA "Unknown" | Manual check on the state portal: rera.tn.gov.in, rera.ap.gov.in. No public API was found, and portals are not scraped |
| Land records and encumbrance | Title "Unknown"; always on the "before you pay" list | Manual: Tamil Nadu eservices.tn.gov.in (patta/chitta) and tnreginet.gov.in (EC); Andhra Pradesh meebhoomi.ap.gov.in (Adangal, 1B). Web lookups for individuals; not integrated, never automated, never treated as verification |
| Rainfall waterlogging, coastal flooding, observed flood footprints | Those mechanisms "Unknown" | See candidate sources below |
| Land prices | Not shown (removed in this version, J-58) | — |

## Download plan

1. **Andhra Pradesh**: done 2026-10-25 (see the verification below).

2. **Karnataka, Kerala or Telangana**: the same command with that state's slug (`terrascope.cmd fetch-data --list`),
   only when you analyse plots there. The OSM extract is reused; DEM tile sizes have not been measured yet.
3. **Optional cleanup**: the unused previous Tamil Nadu build frees 276 MB. Delete it only on purpose.

## Verified in the pipeline (2026-10-25, Vijayawada plot, re-analysed on an audit copy)

| Layer | Loaded and used | Result for the plot |
|---|---|---|
| Regional OSM (andhra-pradesh) | yes | road 1 m from the boundary (residential), school 326 m, hospital 309 m, bus stop 408 m, railway halt 2.1 km |
| OSM water features | yes | canal 1.4 km; nearest mapped "water" 2.2 km (a fountain tagged as water: an OSM quirk) |
| Copernicus DEM | yes | 22.6 m; +7.1 m above the nearest mapped water |
| JRC Global Surface Water | yes | no water seen on the plot or within 500 m, 1984-2021 |
| JRC river flood maps | yes | 7 scenarios; no modelled river flooding up to 1-in-500 years |
| Annual land cover 2017-2023 | yes | 88.2% (2017) to 88.6% (2023) built within 1 km; all 7 years used |
| Sentinel-2 | yes | 8 observations, no material change |

## Online services used for viewing and discovery (not analysis)

| Service | Used for | Licence / terms | Notes |
|---|---|---|---|
| EOxCloudless 2023 (EOX, Sentinel-2 composite) | "Satellite (2023)" basemap in the workspace | CC BY-NC-SA 4.0, free for non-commercial use with attribution; commercial use needs an EOX licence | 10 m, one cloud-free composite for 2023; not today's image; not the analysis data. Real detail ends at zoom 14 (measured below) |
| OpenStreetMap tiles | "Map" basemap | ODbL; OSM tile usage policy (light use) | Heavy or commercial use needs another tile host |
| GDELT DOC 2.0 | Local news timeline | Free, no key; no licence page found; asks for at most one request per 5 s | Headline-level metadata from 2017-01-01 (a 2018 query returned 2018 articles, 2026-10-26); at most 250 records per query; frequently rate-limited (HTTP 429) from this network, so TerraScope pauses 2 minutes after a 429 |

## Satellite sharpness, measured (2026-10-26, Senjeri, 10.85°N)

Detail added by each zoom level, as the mean grey-level difference between a tile and the tile one level below
enlarged 2x (more difference = more real detail):

| Zoom (m per screen pixel) | 14 (9.4) | 15 (4.7) | 16 (2.3) | 17 (1.2) | 18 (0.6) |
|---|---|---|---|---|---|
| EOxCloudless 2023 | 8.1 | 2.7 | 1.6 | 1.3 | — |
| Esri World Imagery (6 tiles fetched for this comparison only; not used by the app) | — | 10.3 | 10.9 | 10.7 | 11.4 |

EOX tiles above zoom 14 are enlarged copies of the 10 m Sentinel-2 composite, so the blur is the source, not a bug.
The workspace now stops downloading EOX tiles above zoom 14 (Leaflet enlarges zoom 14 itself) and says so when the user
zooms further. Sharp (sub-metre) imagery needs a commercial imagery provider; none has been switched.

## Licensing: academic demo vs commercial deployment

Verified 2026-10-26 on the providers' own pages:

- **EOxCloudless:** 2018-2025 layers are CC BY-NC-SA 4.0 (non-commercial, attribution); the 2016 layer is CC BY 4.0
  (commercial use allowed, attribution, but ten-year-old imagery). Commercial licences are sold per product; no prices
  are published (quote via cloudless@eox.at).
- **OSM tiles (OSMF tile usage policy):** visible attribution; a valid Referer (browsers send it); honour caching; no
  bulk or offline download; heavy use is not allowed, and access can be blocked without notice. Commercial services are
  warned that access may be withdrawn at any time.
- **Costs found for licensed alternatives:** ArcGIS Location Platform lists 2M free basemap tiles, then $0.15 per
  1,000 (the page does not name World Imagery or state commercial terms: confirm with Esri). MapTiler: Free plan for
  non-commercial use (5k map sessions, 100k requests a month); Flex $30 a month (25k sessions, 500k requests); its
  satellite resolution per plan is not stated.

- **Academic / non-commercial demo:** the current setup is permitted.
  - EOxCloudless 2023 is CC BY-NC-SA 4.0. Attribution is shown on the map.
  - OpenStreetMap tiles are used at light, interactive volume.
- **Commercial deployment is blocked until the basemaps are licensed.**
  - EOxCloudless needs an EOX commercial licence (EOX Commercial Attribution-RestrictedUse licence; contact EOX).
  - `tile.openstreetmap.org` must not carry production traffic (OSMF tile usage policy); use a commercial OSM tile host
    instead.
  - Licensed satellite alternatives to evaluate: an EOX commercial licence for the same layer; Esri World Imagery under
    an ArcGIS Location Platform account; or a paid satellite basemap plan from a map-tile vendor. Each has its own
    attribution and caching terms, to be read before switching. No provider has been switched.
- **GDELT:** no licence or terms page was found. Treat it as a discovery aid for the demo, and confirm terms with the
  GDELT Project before any commercial use.

## Candidate sources for flood, rainfall, terrain and drainage (researched 2026-10-25; none integrated)

| Source | What | Resolution / period | Licence (as found) | Notes |
|---|---|---|---|---|
| NRSC Flood Hazard Atlas, Andhra Pradesh (official) | Flood hazard categories from satellite flood maps | District level; 2000-2020 | Not found | Viewing on Bhuvan; no download found. Contact flood@nrsc.gov.in. Usable as a manual check link |
| Global Flood Database v1 (Cloud to Street / Dartmouth) | Observed flood extents, 913 events | 250 m; 2000-2018 | CC BY-NC 4.0 (Earth Engine catalogue) | Non-commercial only; observed, not modelled |
| WRI Aqueduct Floods v2 | Riverine and coastal inundation by return period | ~1 km; released 2020 | Not stated on WRI's page; secondary sources say CC BY 4.0 | Would fill the coastal gap; confirm the licence first |
| MERIT Hydro (HAND layer) | Height above nearest drainage | ~90 m | CC BY-NC 4.0 / ODbL dual; registration form | Would replace the terrain indicator with a real HAND figure; non-commercial |
| HydroSHEDS / HydroRIVERS | River network and basins | 15 arc-seconds | Free for scientific, educational and commercial use (official page); read the licence document | Drainage context |
| SACHET, NDMA (official) | CAP 1.2 disaster alerts from IMD, INCOIS, state authorities | Country / state RSS feeds | Not stated | Current warnings, not historical parcel risk; feed URL not confirmed |
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
