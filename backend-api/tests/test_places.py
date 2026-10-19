"""Place suggestions come from the local GeoNames index and never from a web service.

The index is built by the real builder (data-pipeline/fetch_data.install_places) from
tiny GeoNames-format files, so the builder/reader schema contract is tested too.
"""

import sys
import zipfile
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "backend-api"), str(ROOT / "backend-api" / "src"), str(ROOT / "data-pipeline")]

import fetch_data  # noqa: E402
from routers import parcels, store  # noqa: E402

# geonameid, name, asciiname, alternatenames, lat, lon, class, code, cc, cc2, admin1, admin2, admin3, admin4, population
GAZETTEER = [
    ["1267456", "Kātpādi", "Katpadi", "", "12.96951", "79.14552", "P", "PPL", "IN", "", "25", "605", "", "", "38833"],
    ["10979638", "Katpadi", "Katpadi", "", "13.28298", "74.74743", "P", "PPL", "IN", "", "19", "569", "", "", "0"],
    ["1264527", "Chennai", "Chennai", "Madras,Madraspatnam,de", "13.08784", "80.27847", "P", "PPLA", "IN", "", "25", "603", "", "", "4681087"],
    ["11594570", "Vellore Institute of Technology", "Vellore Institute of Technology", "", "12.97224", "79.15864", "S", "SCHC", "IN", "", "25", "605", "", "", "0"],
    ["1259385", "Port Blair", "Port Blair", "", "11.66613", "92.74635", "P", "PPLA", "IN", "", "01", "640", "", "", "112050"],
    ["999", "Some Stream", "Some Stream", "", "12.9", "79.1", "H", "STM", "IN", "", "25", "605", "", "", "0"],
]
POSTAL = [["IN", "632007", "Katpadi", "Tamil Nadu", "25", "Vellore", "605", "Vellore", "", "12.9695", "79.1455", "4"]]


def _zip(path: Path, rows: list[list[str]]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("IN.txt", "\n".join("\t".join(row + [""] * 4) for row in rows) + "\n")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    downloads = tmp_path / "downloads" / "geonames"
    downloads.mkdir(parents=True)
    _zip(downloads / "IN.zip", GAZETTEER)
    _zip(downloads / "IN-postal.zip", POSTAL)
    (downloads / "admin1CodesASCII.txt").write_text(
        "IN.25\tTamil Nadu\tTamil Nadu\t1\nIN.19\tKarnataka\tKarnataka\t2\nIN.01\tAndaman and Nicobar\tx\t3\n", encoding="utf-8")
    (downloads / "admin2Codes.txt").write_text(
        "IN.25.605\tVellore\tVellore\t1\nIN.25.603\tChennai\tChennai\t2\nIN.19.569\tUdupi\tUdupi\t3\n"
        "IN.01.640\tSouth Andaman\tx\t4\n", encoding="utf-8")
    fetch_data.install_places(tmp_path, session=None)  # every file is on disk, so nothing is downloaded
    monkeypatch.setenv("TERRASCOPE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BACKEND_STORE_PATH", str(tmp_path / "isolated.sqlite3"))
    store.init_store()

    def no_network(*_args, **_kwargs):
        raise AssertionError("autocomplete must not make network requests")

    monkeypatch.setattr(httpx.AsyncClient, "get", no_network)
    from terrascope_backend_api.main import app

    return TestClient(app)


def names(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["display_name"] for item in response.json()]


def test_suggest_is_local_prefix_search(client):
    assert names(client.get("/api/v1/search/suggest", params={"q": "katp"}))[:2] == [
        "Katpadi, Vellore, Tamil Nadu, India",  # ASCII name, and the populated Tamil Nadu town first
        "Katpadi, Udupi, Karnataka, India",
    ]
    assert names(client.get("/api/v1/search/suggest", params={"q": "katpadi vellore"}))[0] == "Katpadi, Vellore, Tamil Nadu, India"
    assert names(client.get("/api/v1/search/suggest", params={"q": "port bl"})) == ["Port Blair, South Andaman, Andaman and Nicobar, India"]


def test_alternate_names_acronyms_and_pin_codes(client):
    assert names(client.get("/api/v1/search/suggest", params={"q": "madras"}))[0] == "Chennai, Chennai, Tamil Nadu, India"
    assert "Vellore Institute of Technology, Vellore, Tamil Nadu, India" in names(
        client.get("/api/v1/search/suggest", params={"q": "vit"}))
    pin = client.get("/api/v1/search/suggest", params={"q": "632007"}).json()
    assert pin[0]["name"] == "Katpadi (PIN 632007)" and pin[0]["precision"].startswith("approximate")
    # Two-letter fragments of foreign-language names are not indexed; streams are not indexed.
    assert names(client.get("/api/v1/search/suggest", params={"q": "de"})) == []
    assert names(client.get("/api/v1/search/suggest", params={"q": "some stream"})) == []


def test_explicit_search_uses_the_local_index_first(client):
    # httpx is patched to fail, so this passes only if Nominatim is not called.
    assert names(client.get("/api/v1/search/geocode", params={"q": "Chennai"}))[0] == "Chennai, Chennai, Tamil Nadu, India"


def test_missing_index_is_reported_not_replaced_by_nominatim(client, tmp_path, monkeypatch):
    monkeypatch.setenv("TERRASCOPE_DATA_DIR", str(tmp_path / "empty"))
    response = client.get("/api/v1/search/suggest", params={"q": "chennai"})
    assert response.status_code == 503
    assert "fetch-data" in response.json()["detail"]
