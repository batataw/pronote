#!/usr/bin/env python3
"""
Extraction d'un emploi du temps PRONOTE exporté en PDF (vectoriel) -> JSON.
Aucun OCR : texte et rectangles sont lus directement dans le PDF.

Usage : python3 pronote_pdf_extract.py edt.pdf > edt.json
Dépendance : pdfplumber
"""
import sys, re, json
import pdfplumber

DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"]
TIME = re.compile(r"^(\d{1,2})h(\d{2})$")
TEACHER = re.compile(r"^[A-ZÀ-Ü][A-ZÀ-Ü' -]*\s[A-Z]\.$")
QUINZ = re.compile(r"\s*\bQ([12])$")
PUA = re.compile(r"[\ue000-\uf8ff]")  # pictogrammes PRONOTE (police d'icônes) -> retirés du texte


def hhmm(t):
    h, m = TIME.match(t).groups()
    return f"{int(h):02d}:{m}"


def to_min(t):
    h, m = map(int, t.split(":")); return h * 60 + m


def extract(path):
    with pdfplumber.open(path) as pdf:
        page = pdf.pages[0].dedupe_chars()
        words = page.extract_words()
        for w in words: w["text"] = PUA.sub("", w["text"])

        # Cadre de la grille = plus grand rectangle ; cours = rectangles intérieurs
        rects = [r for r in page.rects if r["width"] > 20 and r["height"] > 10]
        frame = max(rects, key=lambda r: r["width"] * r["height"])
        cells = [r for r in rects if r is not frame]

        # Colonnes jours : en-têtes "lundi", "mardi"… -> bornes x issues des cases
        heads = sorted([w for w in words if w["text"].lower() in DAYS], key=lambda w: w["x0"])
        xs = sorted({round(r["x0"], 1) for r in cells} | {round(r["x1"], 1) for r in cells})
        def day_of(x):
            centers = [((h["x0"] + h["x1"]) / 2, h["text"].lower()) for h in heads]
            return min(centers, key=lambda c: abs(c[0] - x))[1]

        # Axe horaire : libellés "8h05"… à gauche de la grille ; à chaque frontière de ligne,
        # le libellé le plus haut = fin de la ligne précédente, le plus bas = début de la suivante.
        grid_x0 = min(r["x0"] for r in cells)
        labels = sorted([(w["top"], hhmm(w["text"])) for w in words
                         if w["x0"] < grid_x0 - 5 and TIME.match(w["text"])])
        bounds = sorted({round(r["top"], 1) for r in cells} | {round(r["bottom"], 1) for r in cells})
        def near(y):
            return sorted([t for top, t in labels if -12 <= top - y <= 6], key=to_min)
        def start_at(y):
            n = near(y); return n[-1] if n else None
        def end_at(y):
            n = near(y); return n[0] if n else None
        labeled = [b for b in bounds if near(b)]
        def interp(y):
            """Frontière sans libellé (case de 1,5 ligne) : interpolation linéaire dans la ligne,
            arrondie à 5 min. Renvoie (heure, estimé?)."""
            up = max(b for b in labeled if b < y); down = min(b for b in labeled if b > y)
            a, b = to_min(start_at(up)), to_min(end_at(down))
            v = round((a + (b - a) * (y - up) / (down - up)) / 5) * 5
            return f"{v // 60:02d}:{v % 60:02d}"

        cours, warnings = [], []
        for r in sorted(cells, key=lambda r: (r["x0"], r["top"])):
            crop = page.within_bbox((r["x0"], r["top"], r["x1"], r["bottom"]))
            raw = crop.extract_text() or ""
            picto = bool(PUA.search(raw))
            lines = [PUA.sub("", l).strip() for l in raw.splitlines() if PUA.sub("", l).strip()]
            yt, yb = round(r["top"], 1), round(r["bottom"], 1)
            debut, fin = start_at(yt), end_at(yb)
            estime = not debut or not fin
            debut, fin = debut or interp(yt), fin or interp(yb)

            quinzaine = None
            if lines and QUINZ.search(lines[-1]):
                quinzaine = "Q" + QUINZ.search(lines[-1]).group(1)
                lines[-1] = QUINZ.sub("", lines[-1]).strip()
                if not lines[-1]: lines.pop()

            groupe = next((l.strip("[]") for l in lines if l.startswith("[")), None)
            lines = [l for l in lines if not l.startswith("[")]
            profs = [l for l in lines if TEACHER.match(l)]
            rest = [l for l in lines if not TEACHER.match(l)]
            matiere = rest[0] if rest else ""
            salles = [s.strip() for l in rest[1:] for s in l.split("/") if s.strip()]

            c = {"jour": day_of((r["x0"] + r["x1"]) / 2), "debut": debut, "fin": fin,
                 "matiere": matiere, "profs": profs, "groupe": groupe, "salles": salles,
                 "quinzaine": quinzaine, "pictogramme": picto, "horaire_estime": estime,
                 "demi_case": r["width"] < (frame["width"] / len(heads)) * 0.75}
            if estime: warnings.append(f"{c['jour']} {debut}–{fin} {matiere} : case à cheval sur un créneau, horaire interpolé")
            if not profs: warnings.append(f"{c['jour']} {debut} : aucun prof lu")
            cours.append(c)

        # Fusion : même cours sur deux lignes contiguës SANS pause entre elles
        cours.sort(key=lambda c: (DAYS.index(c["jour"]), to_min(c["debut"]), c["quinzaine"] or ""))
        merged = []
        for c in cours:
            key = lambda x: (x["jour"], x["matiere"], tuple(x["profs"]), x["groupe"], tuple(x["salles"]), x["quinzaine"])
            m = next((p for p in merged if key(p) == key(c) and p["fin"] == c["debut"]), None)
            if m: m["fin"] = c["fin"]
            else: merged.append(c)

        header = page.within_bbox((0, 0, page.width, frame["top"] + 15)).extract_text().splitlines()
        etab = next((l for l in header if l.strip().upper().startswith(("LYCEE", "COLLEGE", "LYCÉE", "COLLÈGE"))), None)

    return {"etablissement": etab,
            "creneaux": sorted({t for _, t in labels}, key=to_min),
            "cours": merged, "warnings": warnings}


if __name__ == "__main__":
    print(json.dumps(extract(sys.argv[1]), ensure_ascii=False, indent=1))
