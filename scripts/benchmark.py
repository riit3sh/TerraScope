"""Time the real analysis flow for fixed test parcels, through the running backend.

    python scripts/benchmark.py --runs 2 --allow-saving-reports [--out result.json]

Every run SAVES a report in the backend's store, so point it at an isolated store
(start the services with BACKEND_STORE_PATH set to a scratch file), never at the
store holding your own reports. The polygons are test geometry, not surveyed
boundaries. Run 1 for a parcel is "cold" for its per-parcel caches (river flood
results, region tiles already on disk stay warm); later runs are "warm".
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from datetime import date, timedelta

import httpx

API = "http://127.0.0.1:8000"


def box(west: float, south: float, east: float, north: float) -> dict:
    return {"type": "Polygon", "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]]}


# The acceptance parcel: the exact polygon of the VIT report (snapshot 568d1f42, 2.75 acres).
VIT_ACCEPTANCE = {"type": "Polygon", "coordinates": [[
    [79.15536230217474, 12.969645765583497], [79.15654219912079, 12.969619636743653],
    [79.15649929377727, 12.968846221841105], [79.15534084950296, 12.968835770271891],
    [79.15536230217474, 12.969645765583497]]]}

PARCELS = {
    # name: polygon
    "VIT acceptance parcel (568d1f42 polygon)": VIT_ACCEPTANCE,
    "VIT Vellore campus (part)": box(79.1540, 12.9680, 79.1610, 12.9735),
    "Katpadi residential plot": box(79.14270, 12.95370, 79.14284, 12.95384),
    "Kadapa": box(78.8441, 14.4507, 78.8450, 14.4516),
    "Chennai Velachery, beside the lake": box(80.2120, 12.9856, 80.2128, 12.9864),
    "Patna, Bihar (outside southern India)": box(85.1440, 25.6210, 85.1449, 25.6219),
    "Puducherry (union territory)": box(79.8330, 11.9340, 79.8339, 11.9349),
    "Colombo (outside India)": box(79.8612, 6.9271, 79.8621, 6.9280),
}
SETTINGS = {
    "profile": "homebuyer", "property_type": "residential", "investment_horizon": "1_to_3y",
    "weights": {"growth_pct": 20, "legal_safety_pct": 35, "accessibility_pct": 25, "flood_safety_pct": 20},
    "preferences": {"road_importance": "medium", "school_importance": "high", "max_road_distance_m": 3000,
                    "max_school_distance_m": 5000, "rera_requirement": "important"},
}


def run_once(client: httpx.Client, name: str, polygon: dict) -> dict:
    today = date.today()
    out: dict = {"parcel": name}
    began = time.perf_counter()
    response = client.post(f"{API}/api/v1/parcels/analyze", json={
        "polygon": polygon, "address": name, "analysis_date_from": (today - timedelta(days=730)).isoformat(),
        "analysis_date_to": today.isoformat()}, timeout=240)
    out["analyze_s"] = round(time.perf_counter() - began, 2)
    out["analyze_status"] = response.status_code
    body = response.json()
    if response.status_code != 200 or body.get("status") == "outside_coverage":
        out["result"] = body.get("status") or body.get("detail")
        return out
    snapshot = body["evidence_snapshot"]
    out["collectors_ms"] = snapshot["metadata"].get("collection_timings_ms")
    # Fingerprints of the evidence, to check that a faster run returned the same answer.
    satellite = snapshot.get("satellite") or {}
    out["satellite_sha"] = hashlib.sha1(json.dumps([satellite.get("ndvi_trend"), satellite.get("ndbi_trend")],
                                                   sort_keys=True).encode()).hexdigest()[:10]
    flood = {k: v for k, v in (snapshot.get("flood_indicators") or {}).items() if k != "river_flood"}
    flood["scenarios"] = ((snapshot.get("flood_indicators") or {}).get("river_flood") or {}).get("scenarios")
    out["flood_sha"] = hashlib.sha1(json.dumps(flood, sort_keys=True).encode()).hexdigest()[:10]
    out["satellite_freshness"] = next((e.get("freshness") for e in snapshot.get("evidence") or []
                                       if e.get("source_type") == "satellite"), None)
    began = time.perf_counter()
    evaluated = client.post(f"{API}/api/v1/parcels/{snapshot['parcel_id']}/evaluate",
                            json={"analysis_snapshot_id": body["analysis_snapshot_id"], **SETTINGS}, timeout=120)
    out["evaluate_s"] = round(time.perf_counter() - began, 3)
    result = evaluated.json()
    out["verdict"] = result.get("verdict", {}).get("recommendation")
    out["explanation_source"] = result.get("verdict", {}).get("explanation_source")
    out["accessibility"] = (result.get("score_breakdown") or {}).get("accessibility_score")
    out["change_type"] = (result.get("satellite") or {}).get("change_type")
    out["observations"] = len((result.get("satellite") or {}).get("imagery_dates") or [])
    began = time.perf_counter()
    client.get(f"{API}/api/v1/parcels/{snapshot['parcel_id']}", timeout=30).raise_for_status()
    out["reopen_s"] = round(time.perf_counter() - began, 3)
    out["area_ha"] = round(snapshot["geometry_metadata"]["area_m2"] / 10_000, 3)
    return out


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--allow-saving-reports", action="store_true", required=True)
    parser.add_argument("--out")
    parser.add_argument("--offset-deg", type=float, default=0.0,
                        help="shift every polygon east by this many degrees, so run 1 is truly cold (new cache keys)")
    args = parser.parse_args()
    shift = lambda polygon: {"type": "Polygon", "coordinates": [[[x + args.offset_deg, y] for x, y in polygon["coordinates"][0]]]}  # noqa: E731
    results = []
    with httpx.Client() as client:
        for run in range(1, args.runs + 1):
            for name, polygon in PARCELS.items():
                result = {"run": run, **run_once(client, name, shift(polygon))}
                print(json.dumps(result), flush=True)
                results.append(result)
    summary = {}
    for key in ("analyze_s", "evaluate_s", "reopen_s"):
        values = [r[key] for r in results if key in r and r.get("analyze_status") == 200 and "collectors_ms" in r]
        if values:
            summary[key] = {"n": len(values), "p50": percentile(values, 0.5), "p95": percentile(values, 0.95),
                            "max": max(values)}
    for run in range(1, args.runs + 1):
        values = [r["analyze_s"] for r in results if r["run"] == run and "collectors_ms" in r]
        if values:
            summary[f"analyze_s_run{run}_median"] = statistics.median(values)
    print(json.dumps(summary, indent=2))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump({"results": results, "summary": summary}, handle, indent=2)


if __name__ == "__main__":
    main()
