import json
import shutil

import pytest

from conftest import NOAM_PDF
from pronote_extractor import ExtractionError, detect, extract
from pronote_extractor.cli import main

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\0" * 32


def test_detect_by_signature():
    assert detect(NOAM_PDF.read_bytes()) == "pdf"
    assert detect(b"\n\n%PDF-1.4 octets parasites avant l'en-tete") == "pdf"


@pytest.mark.parametrize("data", [b"ceci n'est pas un PDF", PNG, JPEG])
def test_non_pdf_is_unsupported(data):
    """Texte, et désormais images : seul le PDF est accepté."""
    with pytest.raises(ExtractionError) as e:
        detect(data)
    assert e.value.code == "unsupported_type"


def test_text_named_pdf_is_unsupported(tmp_path):
    f = tmp_path / "edt.pdf"
    f.write_text("ceci n'est pas un PDF")
    with pytest.raises(ExtractionError) as e:
        extract(f)
    assert e.value.code == "unsupported_type"


def test_pdf_renamed_png_is_processed_as_pdf(tmp_path, pdf_output):
    f = tmp_path / "edt.png"
    shutil.copy(NOAM_PDF, f)
    assert extract(f) == pdf_output


def test_cli_routes_pdf(tmp_path, capsys, pdf_output):
    f = tmp_path / "capture.png"
    shutil.copy(NOAM_PDF, f)
    assert main([str(f)]) == 0
    assert json.loads(capsys.readouterr().out) == pdf_output


def test_cli_unsupported(tmp_path, capsys):
    f = tmp_path / "notes.txt"
    f.write_text("bonjour")
    assert main([str(f)]) == 1
    assert json.loads(capsys.readouterr().err)["error"] == "unsupported_type"


def test_cli_contract_errors(tmp_path, capsys):
    """Contrat lu par le backend : code 1 et {"error", "detail"} sur stderr, rien sur stdout."""
    from pdfgen import make_pdf
    cases = {"no_grid": make_pdf([[("text", 50, 50, "Document scanne", 10)]]),
             "invalid_file": b"%PDF-1.4\ncorrompu",
             "unsupported_type": b"\x89PNG\r\n\x1a\nimage"}
    for code, data in cases.items():
        f = tmp_path / f"{code}.pdf"
        f.write_bytes(data)
        assert main([str(f)]) == 1
        out = capsys.readouterr()
        assert out.out == ""
        err = json.loads(out.err)
        assert err["error"] == code and err["detail"]


def test_cli_usage(capsys):
    assert main([]) == 2
