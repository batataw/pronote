def test_pdf_prototype_golden(pdf_prototype_output, noam_expected):
    assert pdf_prototype_output["cours"] == noam_expected["cours"]
    assert pdf_prototype_output["creneaux"] == noam_expected["creneaux"]


def without_page(cours):
    """`page` (tâche 4) n'existe pas dans la vérité terrain."""
    return [{k: v for k, v in c.items() if k != "page"} for c in cours]


def test_pdf_golden(pdf_output, noam_expected):
    assert pdf_output["source"] == "pdf"
    assert pdf_output["etablissement"] == noam_expected["etablissement"]
    # `page` (tâche 4) n'existe pas dans la vérité terrain : comparé à part
    assert without_page(pdf_output["cours"]) == noam_expected["cours"]
    assert all(c["page"] == 1 for c in pdf_output["cours"])
    assert pdf_output["creneaux"] == noam_expected["creneaux"]


def test_pdf_matches_prototype(pdf_output, pdf_prototype_output):
    assert pdf_output["warnings"] == pdf_prototype_output["warnings"]
    assert without_page(pdf_output["cours"]) == pdf_prototype_output["cours"]


def test_pdf_from_bytes(pdf_output):
    from conftest import NOAM_PDF
    from pronote_extractor.pdf.extract import extract
    assert extract(NOAM_PDF.read_bytes()) == pdf_output


def test_pdf_golden_gounod():
    """Collège : semaines A/B (lettre encadrée), salles séparées par des virgules.
    Vérité terrain transcrite à la main depuis le rendu du PDF."""
    import json
    from conftest import FIXTURES
    from pronote_extractor.pdf.extract import extract
    expected = json.loads((FIXTURES / "gounod.expected.json").read_text(encoding="utf-8"))
    out = extract(FIXTURES / "gounod.pdf")
    assert out["etablissement"] == expected["etablissement"]
    assert out["creneaux"] == expected["creneaux"]
    assert without_page(out["cours"]) == expected["cours"]
    assert out["warnings"] == []
