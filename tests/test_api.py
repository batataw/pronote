import pytest
from fastapi.testclient import TestClient

from conftest import NOAM_PDF
from pdfgen import make_pdf
from pronote_extractor.api import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def post(client, data, name="fichier", ctype="application/octet-stream"):
    return client.post("/extract", files={"file": (name, data, ctype)})


def test_health(client):
    assert client.get("/health").json() == {"ok": True, "pdfplumber": "0.11.10"}


def test_extract_pdf(client, noam_expected):
    r = post(client, NOAM_PDF.read_bytes(), "edt.png", "image/png")  # type par contenu, pas par nom
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "pdf"
    assert set(body) == {"source", "etablissement", "creneaux", "cours", "warnings"}
    assert [{k: v for k, v in c.items() if k != "page"} for c in body["cours"]] == noam_expected["cours"]


@pytest.mark.parametrize("data", [b"bonjour", b"\x89PNG\r\n\x1a\nimage", b"\xff\xd8\xff\xe0image"])
def test_unsupported_type(client, data):
    r = post(client, data)
    assert r.status_code == 422 and r.json()["error"] == "unsupported_type"


def test_invalid_file(client):
    r = post(client, b"%PDF-1.4\ncorrompu")
    assert r.status_code == 422 and r.json()["error"] == "invalid_file"


def test_no_grid(client):
    r = post(client, make_pdf([[("text", 50, 50, "Document scanne", 10)]]))
    assert r.status_code == 422 and r.json()["error"] == "no_grid"


def test_too_large(client):
    r = post(client, b"%PDF-" + b"0" * (10 * 1024 * 1024))
    assert r.status_code == 413
