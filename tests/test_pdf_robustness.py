import pytest

from pdfgen import make_pdf, timetable
from pronote_extractor import ExtractionError, extract
from pronote_extractor.pdf.extract import interpolate

LABELS = ["8h00", "9h00", "10h00", "11h00"]


def test_interpolation_real_geometry():
    """Frontière de noam.pdf (lundi) au milieu de la ligne 15:20–16:15 -> 15:45, horaire estimé."""
    assert interpolate(429.4, 405.2, 453.7, "15:20", "16:15") == "15:45"


def test_interpolation_exact_middle_rounds_half_to_even():
    """Milieu géométrique exact : 947,5 min -> round(189,5) = 190 (arrondi au pair de Python) -> 15:50."""
    assert interpolate(50, 0, 100, "15:20", "16:15") == "15:50"


def test_interpolated_course_flagged(pdf_output):
    lundi = [c for c in pdf_output["cours"] if c["jour"] == "lundi" and c["horaire_estime"]]
    assert [(c["debut"], c["fin"]) for c in lundi] == [("14:10", "15:45"), ("15:45", "17:15")]


def test_saturday_supported():
    cells = [(0, 0, 1, ["MATHS", "DUPONT A.", "C 12"]), (5, 1, 3, ["EPS", "MARTIN B."])]
    days = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"]
    out = extract(make_pdf([timetable(days, LABELS, cells)]))
    sat = [c for c in out["cours"] if c["jour"] == "samedi"]
    assert [(c["debut"], c["fin"], c["matiere"]) for c in sat] == [("09:00", "11:00", "EPS")]


def test_multipage_each_page_processed():
    p1 = timetable(["lundi", "mardi"], LABELS, [(0, 0, 1, ["MATHS", "DUPONT A.", "C 12"])])
    p2 = timetable(["lundi", "mardi"], LABELS, [(1, 2, 3, ["ANGLAIS", "SMITH J.", "B 2"])])
    out = extract(make_pdf([p1, p2]))
    assert [(c["page"], c["jour"], c["debut"], c["matiere"]) for c in out["cours"]] == \
           [(1, "lundi", "08:00", "MATHS"), (2, "mardi", "10:00", "ANGLAIS")]


def test_multipage_no_fusion_across_pages():
    cell = (0, 0, 1, ["MATHS", "DUPONT A.", "C 12"])
    nxt = (0, 1, 2, ["MATHS", "DUPONT A.", "C 12"])
    out = extract(make_pdf([timetable(["lundi"], LABELS, [cell]), timetable(["lundi"], LABELS, [nxt])]))
    assert len(out["cours"]) == 2


def test_multipage_page_without_grid_skipped_with_warning():
    p1 = timetable(["lundi"], LABELS, [(0, 0, 1, ["MATHS", "DUPONT A.", "C 12"])])
    out = extract(make_pdf([p1, [("text", 50, 50, "Notes de fin de document", 10)]]))
    assert len(out["cours"]) == 1
    assert "page 2 : pas de grille" in out["warnings"][0]


def test_pdf_without_grid_rejected():
    """PDF scanné (aucun texte ni rectangle exploitables) -> no_grid, avec conseil."""
    with pytest.raises(ExtractionError) as e:
        extract(make_pdf([[("text", 50, 50, "Document scanne", 10)]]))
    assert e.value.code == "no_grid" and "PRONOTE" in e.value.detail


def test_pdf_with_rects_but_no_time_labels_rejected():
    ops = [op for op in timetable(["lundi"], LABELS, [(0, 0, 1, ["MATHS", "DUPONT A."])])
           if not (op[0] == "text" and op[3] in LABELS)]
    with pytest.raises(ExtractionError) as e:
        extract(make_pdf([ops]))
    assert e.value.code == "no_grid"


def test_corrupted_pdf_invalid_file():
    with pytest.raises(ExtractionError) as e:
        extract(b"%PDF-1.4\nceci n'est pas un vrai PDF")
    assert e.value.code == "invalid_file"


def _with_week_marker(ops, letter, boxed=True):
    """Ajoute dans la 1re case la lettre de semaine en bas à droite, encadrée comme au collège."""
    cell = next(op for op in ops[2:] if op[0] == "rect")
    _, x0, top, x1, bottom = cell
    if boxed: ops.append(("rect", x1 - 8, bottom - 11, x1 - 1.6, bottom - 1.4))
    ops.append(("text", x1 - 7, bottom - 10, letter, 7))
    return ops


def test_week_letter_in_box_is_quinzaine_not_room():
    ops = _with_week_marker(timetable(["lundi"], LABELS, [(0, 0, 1, ["MATHS", "DUPONT A.", "C 12"])]), "B")
    (c,) = extract(make_pdf([ops]))["cours"]
    assert (c["quinzaine"], c["salles"]) == ("B", ["C 12"])


def test_week_letter_alone_on_last_line_not_a_room():
    ops = _with_week_marker(timetable(["lundi"], LABELS, [(0, 0, 2, ["EPS", "BERGE E."])]), "A")
    (c,) = extract(make_pdf([ops]))["cours"]
    assert (c["quinzaine"], c["salles"]) == ("A", [])


def test_single_letter_without_box_stays_text():
    """Sans cadre, une lettre isolée n'est pas un marqueur de semaine."""
    ops = _with_week_marker(timetable(["lundi"], LABELS, [(0, 0, 1, ["MATHS", "DUPONT A.", "C 12"])]), "B", boxed=False)
    (c,) = extract(make_pdf([ops]))["cours"]
    assert c["quinzaine"] is None


def test_rooms_split_on_slash_and_comma():
    from pronote_extractor.pdf.parse import parse_cell
    assert parse_cell("MATHS\nDUPONT A.\nC 7/C 8")["salles"] == ["C 7", "C 8"]
    assert parse_cell("FRANCAIS\nCASTANT I.\nB05 P,B11")["salles"] == ["B05 P", "B11"]
    assert parse_cell("FRANCAIS\nCASTANT I.\nB11", week="A")["quinzaine"] == "A"
    assert parse_cell("FRANCAIS\nCASTANT I.\nB11 Q2", week="A")["quinzaine"] == "Q2"  # Q1/Q2 explicite prioritaire
