import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  Layers3,
  MapPinned,
  Pencil,
  Plus,
  RotateCcw,
  SlidersHorizontal,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import {
  MapContainer,
  TileLayer,
  Polygon,
  CircleMarker,
  GeoJSON,
  Tooltip as LTooltip,
  useMap,
  useMapEvents,
} from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "leaflet-draw";
import "leaflet-draw/dist/leaflet.draw.css";
import {
  buildAnalysis,
  CoverageResult,
  DOC_TYPE_LABEL,
  DocType,
  evaluateParcel,
  EvaluationSettings,
  GeoJSONPolygon,
  ParcelRecord,
  uploadEvidence,
} from "../lib/api";
import { AnalysisOverlay, rememberCollection } from "./AnalysisOverlay";
import {
  AREA_UNIT_LABEL,
  AREA_UNITS,
  AreaUnit,
  formatArea,
  useAreaUnit,
} from "../lib/area";

export type Point = [number, number];
type Basemap = "street" | "satellite";
/** Base maps are for looking only; none of them feeds the analysis. */
const BASEMAPS: Record<
  Basemap,
  {
    label: string;
    note: string;
    props: {
      url: string;
      attribution: string;
      maxNativeZoom: number;
      maxZoom: number;
    };
  }
> = {
  street: {
    label: "Map",
    note: "",
    props: {
      url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxNativeZoom: 19,
      maxZoom: 19,
    },
  },
  // EOxCloudless 2023: a cloud-free composite of 2023 Sentinel-2 images, 10 m pixels, CC BY-NC-SA 4.0 (non-commercial).
  // Real detail ends at zoom 14 (9.4 m per pixel at 11°N); EOX's zoom 15-18 tiles are enlarged copies (measured 2026-10-26),
  // so Leaflet stretches zoom 14 itself instead of downloading them.
  satellite: {
    label: "Satellite (2023)",
    note: "Satellite view: a cloud-free composite of Sentinel-2 images from 2023 (10 m pixels, blurred when zoomed in). It is not today's image, and it is a picture for orientation only, not the satellite data TerraScope analyses. It cannot show ownership, legal access, title, zoning or safety.",
    props: {
      url: "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2023_3857/default/g/{z}/{y}/{x}.jpg",
      attribution:
        '<a href="https://cloudless.eox.at">EOxCloudless</a> 2023 by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2023), CC BY-NC-SA 4.0',
      maxNativeZoom: 14,
      maxZoom: 19,
    },
  },
};
const defaults: EvaluationSettings = {
  profile: "homebuyer",
  property_type: "residential",
  investment_horizon: "1_to_3y",
  weights: {
    growth_pct: 20,
    legal_safety_pct: 35,
    accessibility_pct: 25,
    flood_safety_pct: 20,
  },
  preferences: {
    road_importance: "medium",
    school_importance: "high",
    max_road_distance_m: 3000,
    max_school_distance_m: 5000,
    rera_requirement: "important",
  },
};
const presets: Record<
  string,
  {
    weights?: Partial<EvaluationSettings["weights"]>;
    preferences?: Partial<EvaluationSettings["preferences"]>;
  }
> = {
  homebuyer: {
    weights: {
      growth_pct: 20,
      legal_safety_pct: 35,
      accessibility_pct: 25,
      flood_safety_pct: 20,
    },
  },
  developer: {
    weights: {
      growth_pct: 40,
      legal_safety_pct: 20,
      accessibility_pct: 30,
      flood_safety_pct: 10,
    },
  },
  investor: {
    weights: {
      growth_pct: 45,
      legal_safety_pct: 20,
      accessibility_pct: 20,
      flood_safety_pct: 15,
    },
  },
  conservative: {
    weights: {
      growth_pct: 10,
      legal_safety_pct: 40,
      accessibility_pct: 20,
      flood_safety_pct: 30,
    },
    preferences: { rera_requirement: "strict" },
  },
  custom: {},
};
const geo = (p: Point[]): GeoJSONPolygon => ({
  type: "Polygon",
  coordinates: [p.map(([lat, lon]) => [lon, lat])],
});
function metrics(p: Point[]) {
  if (p.length < 4) return { area: 0, perimeter: 0 };
  const m = 111320;
  const lat = (p[0][0] * Math.PI) / 180;
  let area = 0;
  let perimeter = 0;
  p.forEach((a, i) => {
    const b = p[(i + 1) % p.length];
    const x = (a[1] - p[0][1]) * m * Math.cos(lat),
      y = (a[0] - p[0][0]) * m,
      nx = (b[1] - p[0][1]) * m * Math.cos(lat),
      ny = (b[0] - p[0][0]) * m;
    area += x * ny - nx * y;
    perimeter += Math.hypot(nx - x, ny - y);
  });
  return { area: Math.abs(area) / 2, perimeter };
}
function cross(a: Point, b: Point, c: Point) {
  return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
}
function onSegment(a: Point, b: Point, c: Point) {
  return (
    Math.min(a[0], b[0]) - 1e-12 <= c[0] &&
    c[0] <= Math.max(a[0], b[0]) + 1e-12 &&
    Math.min(a[1], b[1]) - 1e-12 <= c[1] &&
    c[1] <= Math.max(a[1], b[1]) + 1e-12
  );
}
function segmentsIntersect(a: Point, b: Point, c: Point, d: Point) {
  const abC = cross(a, b, c), abD = cross(a, b, d);
  const cdA = cross(c, d, a), cdB = cross(c, d, b);
  const eps = 1e-12;
  if (Math.abs(abC) < eps && onSegment(a, b, c)) return true;
  if (Math.abs(abD) < eps && onSegment(a, b, d)) return true;
  if (Math.abs(cdA) < eps && onSegment(c, d, a)) return true;
  if (Math.abs(cdB) < eps && onSegment(c, d, b)) return true;
  return (abC > 0) !== (abD > 0) && (cdA > 0) !== (cdB > 0);
}
/** Reject crossings introduced by dragging vertices after the initial draw. */
function isSimplePolygon(points: Point[]) {
  if (points.length < 4) return false;
  const same = (a: Point, b: Point) =>
    Math.abs(a[0] - b[0]) < 1e-12 && Math.abs(a[1] - b[1]) < 1e-12;
  const vertices = same(points[0], points[points.length - 1])
    ? points.slice(0, -1)
    : points;
  if (vertices.length < 3) return false;
  for (let i = 0; i < vertices.length; i++) {
    const a = vertices[i], b = vertices[(i + 1) % vertices.length];
    for (let j = i + 1; j < vertices.length; j++) {
      if (j === i + 1 || (i === 0 && j === vertices.length - 1)) continue;
      const c = vertices[j], d = vertices[(j + 1) % vertices.length];
      if (segmentsIntersect(a, b, c, d)) return false;
    }
  }
  return true;
}
function DrawLayer({
  points,
  onChange,
}: {
  points: Point[];
  onChange: (p: Point[]) => void;
}) {
  const map = useMap();
  const group = useRef<L.FeatureGroup | null>(null);
  useEffect(() => {
    group.current = new L.FeatureGroup();
    map.addLayer(group.current);
    const draw = new (L as any).Control.Draw({
      draw: {
        polygon: {
          allowIntersection: false,
          shapeOptions: { color: "#b8f36a", fillOpacity: 0.14 },
        },
        polyline: false,
        rectangle: false,
        circle: false,
        marker: false,
        circlemarker: false,
      },
      edit: { featureGroup: group.current },
    });
    map.addControl(draw);
    const created = (e: any) => {
      group.current?.clearLayers();
      group.current?.addLayer(e.layer);
      const c = e.layer
        .getLatLngs()[0]
        .map((x: L.LatLng) => [x.lat, x.lng] as Point);
      onChange([...c, c[0]]);
    };
    const edited = (e: any) =>
      e.layers.eachLayer((l: any) => {
        const c = l
          .getLatLngs()[0]
          .map((x: L.LatLng) => [x.lat, x.lng] as Point);
        onChange([...c, c[0]]);
      });
    map.on((L as any).Draw.Event.CREATED, created);
    map.on((L as any).Draw.Event.EDITED, edited);
    return () => {
      map.off((L as any).Draw.Event.CREATED, created);
      map.off((L as any).Draw.Event.EDITED, edited);
      map.removeControl(draw);
      map.removeLayer(group.current!);
    };
  }, [map, onChange]);
  useEffect(() => {
    if (group.current) {
      group.current.clearLayers();
      if (points.length > 3)
        group.current.addLayer(
          L.polygon(points, { color: "#b8f36a", fillOpacity: 0.14 }),
        );
    }
  }, [points]);
  return null;
}
// Depends on the coordinates, not on an array rebuilt every render: that re-flew the
// map back to zoom 14 after each vertex, edit or keystroke.
function ZoomWatch({ onZoom }: { onZoom: (z: number) => void }) {
  const map = useMapEvents({ zoomend: () => onZoom(map.getZoom()) });
  return null;
}
function Focus({ lat, lon }: { lat: number; lon: number }) {
  const map = useMap();
  useEffect(() => {
    map.flyTo([lat, lon], 14, { duration: 0.6 });
  }, [lat, lon, map]);
  return null;
}

// The boundary lives in App, so returning from a report keeps the parcel the user drew.
// It starts empty: an invented default box must never be analysed as "user-defined".
export function ParcelWorkspace({
  search,
  points,
  onPointsChange: setPoints,
  onBack,
  onReport,
}: {
  search: { lat: number; lon: number; label: string };
  points: Point[];
  onPointsChange: (points: Point[]) => void;
  onBack: () => void;
  onReport: (snapshot: ParcelRecord, settings: EvaluationSettings) => void;
}) {
  const center: Point = [search.lat, search.lon];
  const hasBoundary = points.length >= 4;
  const boundaryValid = hasBoundary && isSimplePolygon(points);
  const [settings, setSettings] = useState(defaults);
  const [drawer, setDrawer] = useState(false);
  const [layers, setLayers] = useState(false);
  const [basemap, setBasemap] = useState<Basemap>("street");
  const [tileErrors, setTileErrors] = useState(0);
  const [areaUnit, setAreaUnit] = useAreaUnit();
  const [startedAt, setStartedAt] = useState(0);
  const [collected, setCollected] = useState<ParcelRecord | null>(null);
  const [zoom, setZoom] = useState(14);
  const [stage, setStage] = useState(-1);
  const [snapshot, setSnapshot] = useState<ParcelRecord | null>(null);
  const [notice, setNotice] = useState("");
  const [outside, setOutside] = useState<CoverageResult | null>(null);
  const [docs, setDocs] = useState<
    { file: File; status: string; docType: DocType }[]
  >([]);
  const [pendingReport, setPendingReport] = useState<{
    snapshot: ParcelRecord;
    settings: EvaluationSettings;
  } | null>(null);
  const stat = metrics(points);
  const amenityMarkers = useMemo(() => {
    const infrastructure = snapshot?.infrastructure;
    if (!infrastructure)
      return [] as {
        key: string;
        position: Point;
        color: string;
        label: string;
      }[];
    return [
      {
        key: "road",
        color: "#f8c15c",
        label: `Nearest road${infrastructure.nearest_road_type ? ` (${infrastructure.nearest_road_type})` : ""} · ${infrastructure.nearest_road_distance_m == null ? "distance unavailable" : `${Math.round(infrastructure.nearest_road_distance_m)} m`}`,
        lat: infrastructure.nearest_road_lat,
        lon: infrastructure.nearest_road_lon,
      },
      {
        key: "school",
        color: "#77d8ff",
        label: `Nearest school · ${infrastructure.nearest_school_distance_m == null ? "distance unavailable" : `${Math.round(infrastructure.nearest_school_distance_m)} m`}`,
        lat: infrastructure.nearest_school_lat,
        lon: infrastructure.nearest_school_lon,
      },
    ].flatMap((item) =>
      typeof item.lat === "number" && typeof item.lon === "number"
        ? [
            {
              key: item.key,
              position: [item.lat, item.lon] as Point,
              color: item.color,
              label: item.label,
            },
          ]
        : [],
    );
  }, [snapshot]);
  const stages = [
    "Collecting evidence (satellite, infrastructure, elevation, RERA)",
    ...(docs.length ? ["Uploading your documents"] : []),
    "Scoring against your evaluation lens",
    "Analysis ready",
  ];
  const choose = (profile: EvaluationSettings["profile"]) =>
    setSettings((s) => ({
      ...s,
      profile,
      weights: { ...s.weights, ...(presets[profile].weights || {}) },
      preferences: {
        ...s.preferences,
        ...(presets[profile].preferences || {}),
      },
    }));
  const normalize = (
    key: keyof EvaluationSettings["weights"],
    value: number,
  ) => {
    const others = Object.keys(settings.weights).filter(
      (x) => x !== key,
    ) as (keyof EvaluationSettings["weights"])[];
    const remaining = 100 - value;
    const sum = others.reduce((n, x) => n + settings.weights[x], 0) || 1;
    setSettings((s) => ({
      ...s,
      profile: "custom",
      weights: {
        ...s.weights,
        [key]: value,
        ...Object.fromEntries(
          others.map((x) => [x, Math.round((s.weights[x] / sum) * remaining)]),
        ),
      },
    }));
  };
  async function analyze() {
    if (stage >= 0) return;
    if (points.length < 4) {
      setNotice("Draw a closed polygon before analyzing.");
      return;
    }
    if (!boundaryValid) {
      setNotice("Boundary edges cross. Move the crossing vertex, or press Clear and redraw a simple parcel.");
      return;
    }
    setPendingReport(null);
    setNotice("");
    setOutside(null);
    setCollected(null);
    setStartedAt(Date.now());
    setStage(0);
    const began = Date.now();
    try {
      const from = new Date();
      from.setFullYear(from.getFullYear() - 2);
      // Each setStage marks a request that is genuinely in flight -- no timer.
      const result = await buildAnalysis({
        polygon: geo(points),
        address: search.label,
        analysis_date_from: from.toISOString().slice(0, 10),
        analysis_date_to: new Date().toISOString().slice(0, 10),
      });
      // Outside India nothing was collected: say so instead of producing a report.
      if ("status" in result) {
        setOutside(result.coverage);
        setStage(-1);
        return;
      }
      const parcelId = result.evidence_snapshot.parcel_id || "";
      setSnapshot(result.evidence_snapshot);
      setCollected(result.evidence_snapshot);
      rememberCollection((Date.now() - began) / 1000);
      if (docs.length) {
        setStage(1);
        await uploadDocs(parcelId);
      }
      setStage(docs.length ? 2 : 1);
      const evaluated = await evaluateParcel(
        parcelId,
        settings,
        result.analysis_snapshot_id,
      );
      setSnapshot(evaluated);
      setPendingReport({ snapshot: evaluated, settings });
      setStage(docs.length ? 3 : 2);
    } catch (error) {
      setStage(-1);
      setNotice(
        error instanceof Error
          ? error.message
          : "Analysis failed. Check the service logs.",
      );
    }
  }
  const setStatus = (file: File, status: string) =>
    setDocs((d) => d.map((x) => (x.file === file ? { ...x, status } : x)));
  async function uploadDocs(parcelId: string) {
    for (const doc of docs) {
      setStatus(doc.file, "uploading…");
      try {
        const result = await uploadEvidence(parcelId, doc.file, doc.docType);
        setStatus(
          doc.file,
          result.text_indexed
            ? `text extracted${result.pages ? ` · ${result.pages} pages` : ""}`
            : "stored · no text extracted",
        );
      } catch {
        setStatus(doc.file, "upload failed");
      }
    }
  }
  return (
    <main className="workspace-shell">
      <header className="topbar">
        <div className="wordmark">
          <span className="mark">
            <Sparkles size={14} />
          </span>{" "}
          TERRASCOPE
        </div>
        <button className="quiet-button" onClick={onBack}>
          <ArrowLeft size={15} /> New search
        </button>
        <div className="crumb">
          <MapPinned size={14} />{" "}
          {search.label.split(",").slice(0, 2).join(",")}
        </div>
        <div className="top-actions">
          <button
            className="quiet-button"
            onClick={() => setLayers((x) => !x)}
            title={
              amenityMarkers.length
                ? "Show the nearest road and school found by the analysis"
                : "Nearby amenities appear here once the parcel has been analyzed"
            }
          >
            <Layers3 size={15} /> Layers
            {layers && !amenityMarkers.length ? " · none yet" : ""}
          </button>
          <span className="avatar">RS</span>
        </div>
      </header>
      <section className="map-stage">
        <MapContainer center={center} zoom={14} zoomControl className="map">
          <TileLayer
            key={basemap}
            {...BASEMAPS[basemap].props}
            eventHandlers={{
              tileerror: () => setTileErrors((n) => n + 1),
              tileload: () => setTileErrors(0),
            }}
          />
          <Focus lat={search.lat} lon={search.lon} />
          <ZoomWatch onZoom={setZoom} />
          <DrawLayer points={points} onChange={setPoints} />
          {layers &&
            (snapshot?.public_land?.overlaps || [])
              .filter((f) => f.geometry && f.geometry.type !== "Point")
              .map((f, i) => (
                <GeoJSON
                  key={`pl-${f.osm_id}-${i}`}
                  data={f.geometry!}
                  style={{ color: "#ff9b8e", weight: 2, fillOpacity: 0.15 }}
                >
                  <LTooltip>{`${f.category_label}${f.name ? ` · ${f.name}` : ""} · mapped, not ownership`}</LTooltip>
                </GeoJSON>
              ))}
          {layers &&
            [
              ...(snapshot?.public_land?.overlaps || []),
              ...(snapshot?.public_land?.nearby || []),
            ]
              .filter(
                (f) => typeof f.lat === "number" && typeof f.lon === "number",
              )
              .map((f, i) => (
                <CircleMarker
                  key={`plm-${f.osm_id}-${i}`}
                  center={[f.lat!, f.lon!]}
                  radius={6}
                  pathOptions={{
                    color: f.contact === "nearby" ? "#c9a7ff" : "#ff9b8e",
                  }}
                >
                  <LTooltip>{`${f.category_label}${f.name ? ` · ${f.name}` : ""} · ${f.contact === "nearby" ? `${Math.round(f.distance_m)} m away` : "touches the boundary"} · mapped, not ownership`}</LTooltip>
                </CircleMarker>
              ))}
          {layers &&
            amenityMarkers.map((marker) => (
              <CircleMarker
                key={marker.key}
                center={marker.position}
                radius={7}
                pathOptions={{ color: marker.color }}
              >
                <LTooltip>{marker.label}</LTooltip>
              </CircleMarker>
            ))}
          <Polygon
            positions={points}
            pathOptions={{ color: boundaryValid ? "#b8f36a" : "#ff9b8e", weight: 2, fillOpacity: 0.12 }}
          />
        </MapContainer>
        <div className="basemap-toggle" role="group" aria-label="Base map">
          {(Object.keys(BASEMAPS) as Basemap[]).map((key) => (
            <button
              key={key}
              className={`map-control${basemap === key ? " active" : ""}`}
              aria-pressed={basemap === key}
              onClick={() => {
                setBasemap(key);
                setTileErrors(0);
              }}
            >
              {BASEMAPS[key].label}
            </button>
          ))}
        </div>
        {basemap === "satellite" && (
          <div className="basemap-note" role="note">
            {tileErrors > 3
              ? "Satellite tiles are not loading (network or provider). Switch back to Map, or try again later; no substitute imagery is shown."
              : zoom > BASEMAPS.satellite.props.maxNativeZoom
                ? `Zoomed in past the imagery's real detail: each 10 m pixel is stretched, so small features (houses, paths, walls) cannot be seen. Zoom out to ${BASEMAPS.satellite.props.maxNativeZoom} for the sharpest view. ${BASEMAPS.satellite.note}`
                : BASEMAPS.satellite.note}
          </div>
        )}
        <div className="map-controls">
          <button
            className="map-control active"
            onClick={() =>
              document
                .querySelector(".leaflet-draw-draw-polygon")
                ?.dispatchEvent(new MouseEvent("click", { bubbles: true }))
            }
          >
            <Plus size={15} /> Draw
          </button>
          <button
            className="map-control"
            onClick={() =>
              document
                .querySelector(".leaflet-draw-edit-edit")
                ?.dispatchEvent(new MouseEvent("click", { bubbles: true }))
            }
          >
            <Pencil size={15} /> Edit
          </button>
          <button
            className="map-control"
            disabled={!hasBoundary}
            onClick={() => setPoints([])}
          >
            <RotateCcw size={15} /> Clear
          </button>
        </div>
        <div className="map-location">
          <MapPinned size={14} /> {search.label}
        </div>
        <div className="map-readout">
          <div>
            <span>
              AREA{" "}
              <select
                className="area-unit"
                aria-label="Area unit"
                value={areaUnit}
                onChange={(e) => setAreaUnit(e.target.value as AreaUnit)}
              >
                {AREA_UNITS.map((u) => (
                  <option key={u} value={u}>
                    {AREA_UNIT_LABEL[u]}
                  </option>
                ))}
              </select>
            </span>
            <strong>
              {boundaryValid ? formatArea(stat.area, areaUnit) : hasBoundary ? "INVALID" : "—"}
            </strong>
          </div>
          <div>
            <span>PERIMETER</span>
            <strong>
              {boundaryValid
                ? `${Math.round(stat.perimeter).toLocaleString()} m`
                : hasBoundary ? "INVALID" : "—"}
            </strong>
          </div>
          <div>
            <span>BOUNDARY</span>
            <strong>{boundaryValid ? "USER-DEFINED" : hasBoundary ? "INVALID" : "NOT DRAWN"}</strong>
          </div>
        </div>
        <div className="boundary-note">
          Boundary is user-defined and is not a legal cadastral boundary.
        </div>
      </section>
      <aside className="workspace-panel">
        <div className="panel-kicker">
          PARCEL WORKSPACE <span>01 / 01</span>
        </div>
        <h1>
          Draw the parcel
          <br />
          <em>you want to understand.</em>
        </h1>
        <p className="panel-copy">
          Use the map to define the analysis boundary. This geometry stays
          intact through every evidence layer.
        </p>
        <div className="panel-actions">
          <button className="primary-button" onClick={() => setDrawer(true)}>
            <SlidersHorizontal size={16} /> Configure evaluation
          </button>
          <button
            className="secondary-button"
            disabled={stage >= 0 || !boundaryValid}
            onClick={analyze}
          >
            <Sparkles size={16} />{" "}
            {stage >= 0 ? "Analysis in progress…" : "Analyze This Parcel"}
          </button>
          {!hasBoundary ? (
            <p className="field-hint">
              Click <strong>Draw</strong> on the map and outline the parcel,
              closing it on the first corner.
            </p>
          ) : !boundaryValid ? (
            <p className="field-hint">Boundary edges cross. Move the crossing vertex or press <strong>Clear</strong> and redraw before analyzing.</p>
          ) : null}
        </div>
        <div className="workspace-footer">
          <label className="upload-row">
            <input
              type="file"
              accept=".pdf,.txt,application/pdf,text/plain"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file)
                  setDocs((d) => [
                    ...d,
                    {
                      file,
                      status: "attached · uploads with analysis",
                      docType: "other",
                    },
                  ]);
                e.target.value = "";
              }}
            />
            <Upload size={15} />
            <span>
              <strong>+ Add evidence</strong>
              <small>PDF or TXT · optional</small>
            </span>
          </label>
          {docs.map((doc, index) => (
            <div className="file-row" key={`${doc.file.name}-${index}`}>
              {doc.file.name} ·{" "}
              <select
                aria-label={`Document type for ${doc.file.name}`}
                value={doc.docType}
                onChange={(e) =>
                  setDocs((d) =>
                    d.map((x, i) =>
                      i === index
                        ? { ...x, docType: e.target.value as DocType }
                        : x,
                    ),
                  )
                }
              >
                {(Object.keys(DOC_TYPE_LABEL) as DocType[]).map((type) => (
                  <option key={type} value={type}>
                    {DOC_TYPE_LABEL[type]}
                  </option>
                ))}
              </select>{" "}
              · {doc.status}
              <button
                type="button"
                className="file-remove"
                aria-label={`Remove ${doc.file.name}`}
                onClick={() =>
                  setDocs((d) => d.filter((_, position) => position !== index))
                }
              >
                <X size={13} />
              </button>
            </div>
          ))}
          <div className="source-legend">
            <span title="Fetched from a provider during this analysis">
              <i className="dot live" /> LIVE
            </span>
            <span title="Reused from an earlier provider response">
              <i className="dot cached" /> CACHED
            </span>
            <span title="A document you uploaded">
              <i className="dot user_upload" /> UPLOAD
            </span>
            <span title="Computed by TerraScope from other evidence">
              <i className="dot derived" /> DERIVED
            </span>
            <span title="From a static seed dataset shipped with the app">
              <i className="dot seed" /> SEED
            </span>
          </div>
        </div>
      </aside>
      {outside && (
        <div className="coverage-card" role="alert">
          <div className="panel-kicker">OUTSIDE COVERAGE</div>
          <h2>This parcel is not analysed.</h2>
          <p>{outside.reason}</p>
          <p>
            No evidence was collected and no report was created. TerraScope
            covers India: every state and union territory.
          </p>
          <small>
            Boundary: {outside.boundary_source || "unknown"} ·{" "}
            {outside.boundary_licence || ""} · data as of{" "}
            {(outside.boundary_as_of || "").slice(0, 10) || "unknown"}
          </small>
          <button className="quiet-button" onClick={() => setOutside(null)}>
            Redraw the boundary
          </button>
        </div>
      )}
      {stage >= 0 && (
        <AnalysisOverlay
          stage={stage}
          stages={stages}
          startedAt={startedAt}
          collected={collected}
          onOpen={() =>
            pendingReport &&
            onReport(pendingReport.snapshot, pendingReport.settings)
          }
        />
      )}
      {drawer && (
        <div className="drawer-backdrop" onClick={() => setDrawer(false)}>
          <aside
            className="settings-drawer"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="drawer-header">
              <div>
                <div className="panel-kicker">EVALUATION LENS</div>
                <h2>How should we evaluate this land?</h2>
              </div>
              <button className="icon-button" onClick={() => setDrawer(false)}>
                <X size={18} />
              </button>
            </div>
            <div className="drawer-scroll">
              <label className="field-label">PROFILE</label>
              <div className="preset-grid">
                {(
                  [
                    "homebuyer",
                    "developer",
                    "investor",
                    "conservative",
                    "custom",
                  ] as const
                ).map((p) => (
                  <button
                    className={
                      settings.profile === p ? "preset selected" : "preset"
                    }
                    key={p}
                    onClick={() => choose(p)}
                  >
                    {p}
                  </button>
                ))}
              </div>
              <label className="field-label">PROPERTY TYPE</label>
              <div className="segmented">
                {(
                  [
                    "residential",
                    "commercial",
                    "industrial",
                    "mixed_use",
                  ] as const
                ).map((p) => (
                  <button
                    className={settings.property_type === p ? "selected" : ""}
                    key={p}
                    onClick={() =>
                      setSettings((s) => ({ ...s, property_type: p }))
                    }
                  >
                    {p.replace("_", " ")}
                  </button>
                ))}
              </div>
              <label className="field-label">INVESTMENT HORIZON</label>
              <select
                value={settings.investment_horizon}
                onChange={(e) =>
                  setSettings((s) => ({
                    ...s,
                    investment_horizon: e.target
                      .value as EvaluationSettings["investment_horizon"],
                  }))
                }
              >
                <option value="under_1y">&lt;1 year</option>
                <option value="1_to_3y">1–3 years</option>
                <option value="3_to_5y">3–5 years</option>
                <option value="5_to_10y">5–10 years</option>
                <option value="10_plus_y">10+ years</option>
              </select>
              <label className="field-label">
                PRIORITIES <span>must total 100%</span>
              </label>
              {(
                [
                  ["growth_pct", "Area growth"],
                  ["legal_safety_pct", "Legal Safety"],
                  ["accessibility_pct", "Accessibility"],
                  ["flood_safety_pct", "Flood Safety"],
                ] as const
              ).map(([key, label]) => (
                <div className="slider-row" key={key}>
                  <span>{label}</span>
                  <strong>{settings.weights[key]}%</strong>
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={settings.weights[key]}
                    onChange={(e) => normalize(key, Number(e.target.value))}
                  />
                </div>
              ))}
              <div className="weight-total">
                100% <span>normalized allocation</span>
              </div>
              <label className="field-label">INFRASTRUCTURE</label>
              <div className="two-col">
                <label>
                  Road importance
                  <select
                    value={settings.preferences.road_importance}
                    onChange={(e) =>
                      setSettings((s) => ({
                        ...s,
                        preferences: {
                          ...s.preferences,
                          road_importance: e.target.value as any,
                        },
                      }))
                    }
                  >
                    <option>low</option>
                    <option>medium</option>
                    <option>high</option>
                  </select>
                </label>
                <label>
                  School importance
                  <select
                    value={settings.preferences.school_importance}
                    onChange={(e) =>
                      setSettings((s) => ({
                        ...s,
                        preferences: {
                          ...s.preferences,
                          school_importance: e.target.value as any,
                        },
                      }))
                    }
                  >
                    <option>low</option>
                    <option>medium</option>
                    <option>high</option>
                  </select>
                </label>
              </div>
              <label className="field-label">
                ACCESSIBILITY LIMITS <span>score reaches 0 at the limit</span>
              </label>
              <div className="slider-row">
                <span>Road within</span>
                <strong>
                  {settings.preferences.max_road_distance_m.toLocaleString()} m
                </strong>
                <input
                  type="range"
                  min="100"
                  max="5000"
                  step="100"
                  value={settings.preferences.max_road_distance_m}
                  aria-label="Maximum road distance in metres"
                  onChange={(e) =>
                    setSettings((s) => ({
                      ...s,
                      preferences: {
                        ...s.preferences,
                        max_road_distance_m: Number(e.target.value),
                      },
                    }))
                  }
                />
              </div>
              <div className="slider-row">
                <span>School within</span>
                <strong>
                  {settings.preferences.max_school_distance_m.toLocaleString()}{" "}
                  m
                </strong>
                <input
                  type="range"
                  min="100"
                  max="5000"
                  step="100"
                  value={settings.preferences.max_school_distance_m}
                  aria-label="Maximum school distance in metres"
                  onChange={(e) =>
                    setSettings((s) => ({
                      ...s,
                      preferences: {
                        ...s.preferences,
                        max_school_distance_m: Number(e.target.value),
                      },
                    }))
                  }
                />
              </div>
              <p className="field-hint">
                Straight-line distance from your boundary to the nearest mapped
                road or school. Proximity, not legal access.
              </p>
              <label className="field-label">RERA REQUIREMENT</label>
              <div className="segmented three">
                {(["strict", "important", "informational"] as const).map(
                  (x) => (
                    <button
                      className={
                        settings.preferences.rera_requirement === x
                          ? "selected"
                          : ""
                      }
                      key={x}
                      onClick={() =>
                        setSettings((s) => ({
                          ...s,
                          preferences: {
                            ...s.preferences,
                            rera_requirement: x,
                          },
                        }))
                      }
                    >
                      {x}
                    </button>
                  ),
                )}
              </div>
            </div>
            <div className="drawer-footer">
              <button
                className="primary-button"
                onClick={() => setDrawer(false)}
              >
                Use this evaluation lens
              </button>
            </div>
          </aside>
        </div>
      )}
      {notice && <div className="toast">{notice}</div>}
    </main>
  );
}
