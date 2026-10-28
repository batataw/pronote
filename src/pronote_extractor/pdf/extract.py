"""Extracteur PDF : texte et rectangles lus directement dans le PDF vectoriel, aucun OCR."""
import io

import pdfplumber
from pdfminer.pdfparser import PDFSyntaxError
from pdfplumber.utils.exceptions import PdfminerException

from ..errors import ExtractionError
from ..schema import Course, Result
from .parse import PUA, TIME, hhmm, parse_cell, to_min

DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"]
NO_GRID = "PDF sans grille ni libellés horaires (PDF scanné ?) : exporter le PDF directement depuis PRONOTE"


PDF_ERRORS = (PdfminerException, PDFSyntaxError, ValueError, TypeError, KeyError)


class NoGrid(Exception):
    pass


def open_pdf(src):
    """Chemin ou contenu brut (bytes)."""
    try:
        if isinstance(src, (bytes, bytearray, memoryview)):
            return pdfplumber.open(io.BytesIO(bytes(src)))
        return pdfplumber.open(str(src))
    except PDF_ERRORS as e:
        raise ExtractionError("invalid_file", f"PDF illisible ({type(e).__name__})") from e


def interpolate(y, up, down, start_up, end_down):
    """Heure d'une frontière sans libellé en `y`, entre les frontières étiquetées `up` (début de
    ligne `start_up`) et `down` (fin de ligne `end_down`) : interpolation linéaire arrondie à 5 min."""
    a, b = to_min(start_up), to_min(end_down)
    v = round((a + (b - a) * (y - up) / (down - up)) / 5) * 5
    return f"{v // 60:02d}:{v % 60:02d}"


def week_markers(page, words):
    """Lettres de semaine du collège : une lettre seule (A, B…) dans un petit cadre (≤ 20 × 12 pt)
    en coin de case. Renvoie [(cadre, lettre)]."""
    boxes = [r for r in page.rects if r["width"] <= 20 and r["height"] <= 12]
    out = []
    for w in words:
        if len(w["text"]) != 1 or not w["text"].isupper(): continue
        box = next((b for b in boxes if b["x0"] - 1 <= w["x0"] and w["x1"] <= b["x1"] + 1
                    and b["top"] - 1 <= w["top"] and w["bottom"] <= b["bottom"] + 1), None)
        if box: out.append((box, w["text"]))
    return out


def inside(obj, r):
    cx, cy = (obj["x0"] + obj["x1"]) / 2, (obj["top"] + obj["bottom"]) / 2
    return r["x0"] <= cx <= r["x1"] and r["top"] <= cy <= r["bottom"]


def extract_page(page, page_no):
    """Une page = une semaine ou une quinzaine -> (cours, warnings, libellés, établissement)."""
    page = page.dedupe_chars()
    words = page.extract_words()
    for w in words: w["text"] = PUA.sub("", w["text"])

    # Cadre de la grille = plus grand rectangle ; cours = rectangles intérieurs
    rects = [r for r in page.rects if r["width"] > 20 and r["height"] > 10]
    heads = sorted([w for w in words if w["text"].lower() in DAYS], key=lambda w: w["x0"])
    if len(rects) < 2 or not heads: raise NoGrid
    frame = max(rects, key=lambda r: r["width"] * r["height"])
    cells = [r for r in rects if r is not frame]

    # Colonnes jours : en-têtes "lundi", "mardi"… ; le jour d'une case = en-tête le plus proche en x
    def day_of(x):
        centers = [((h["x0"] + h["x1"]) / 2, h["text"].lower()) for h in heads]
        return min(centers, key=lambda c: abs(c[0] - x))[1]

    # Axe horaire : libellés "8h05"… à gauche de la grille ; à chaque frontière de ligne,
    # le libellé le plus haut = fin de la ligne précédente, le plus bas = début de la suivante.
    grid_x0 = min(r["x0"] for r in cells)
    labels = sorted([(w["top"], hhmm(w["text"])) for w in words
                     if w["x0"] < grid_x0 - 5 and TIME.match(w["text"])])
    if not labels: raise NoGrid
    bounds = sorted({round(r["top"], 1) for r in cells} | {round(r["bottom"], 1) for r in cells})
    def near(y):
        return sorted([t for top, t in labels if -12 <= top - y <= 6], key=to_min)
    def start_at(y):
        n = near(y); return n[-1] if n else None
    def end_at(y):
        n = near(y); return n[0] if n else None
    labeled = [b for b in bounds if near(b)]
    def interp(y):
        """Frontière sans libellé (case de 1,5 ligne)."""
        up = max(b for b in labeled if b < y); down = min(b for b in labeled if b > y)
        return interpolate(y, up, down, start_at(up), end_at(down))

    markers = week_markers(page, words)
    cours, warnings = [], []
    for r in sorted(cells, key=lambda r: (r["x0"], r["top"])):
        crop = page.within_bbox((r["x0"], r["top"], r["x1"], r["bottom"]))
        mine = [(b, t) for b, t in markers if inside(b, r)]
        if mine:  # la lettre encadrée n'appartient ni aux salles ni aux profs : retirée du texte
            crop = crop.filter(lambda o: o.get("object_type") != "char" or not any(inside(o, b) for b, _ in mine))
        fields = parse_cell(crop.extract_text() or "", week=mine[0][1] if len(mine) == 1 else None)
        yt, yb = round(r["top"], 1), round(r["bottom"], 1)
        debut, fin = start_at(yt), end_at(yb)
        estime = not debut or not fin
        debut, fin = debut or interp(yt), fin or interp(yb)

        c = Course(jour=day_of((r["x0"] + r["x1"]) / 2), debut=debut, fin=fin, **fields,
                   horaire_estime=estime, demi_case=r["width"] < (frame["width"] / len(heads)) * 0.75,
                   page=page_no)
        if estime: warnings.append(f"{c.jour} {debut}–{fin} {c.matiere} : case à cheval sur un créneau, horaire interpolé")
        if not c.profs: warnings.append(f"{c.jour} {debut} : aucun prof lu")
        cours.append(c)

    # Fusion : même cours sur deux lignes contiguës SANS pause entre elles
    cours.sort(key=lambda c: (DAYS.index(c.jour), to_min(c.debut), c.quinzaine or ""))
    key = lambda x: (x.jour, x.matiere, tuple(x.profs), x.groupe, tuple(x.salles), x.quinzaine)
    merged = []
    for c in cours:
        m = next((p for p in merged if key(p) == key(c) and p.fin == c.debut), None)
        if m: m.fin = c.fin
        else: merged.append(c)

    header = (page.within_bbox((0, 0, page.width, frame["top"] + 15)).extract_text() or "").splitlines()
    etab = next((l for l in header if l.strip().upper().startswith(("LYCEE", "COLLEGE", "LYCÉE", "COLLÈGE"))), None)
    return merged, warnings, labels, etab


def extract(src):
    with open_pdf(src) as pdf:
        try:
            pages = pdf.pages
        except PDF_ERRORS as e:
            raise ExtractionError("invalid_file", f"PDF illisible ({type(e).__name__})") from e
        multi = len(pages) > 1
        cours, warnings, labels, etab = [], [], set(), None
        for n, page in enumerate(pages, start=1):
            try:
                c, w, lab, e = extract_page(page, n)
            except NoGrid:
                if multi: warnings.append(f"page {n} : pas de grille d'emploi du temps, ignorée")
                continue
            cours += c
            warnings += [f"page {n} : {x}" for x in w] if multi else w
            labels |= {t for _, t in lab}
            etab = etab or e
    if not cours and not labels: raise ExtractionError("no_grid", NO_GRID)
    return Result(source="pdf", etablissement=etab, creneaux=sorted(labels, key=to_min),
                  cours=cours, warnings=warnings).to_dict()
