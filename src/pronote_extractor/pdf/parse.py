"""Texte d'une case PDF -> champs du cours."""
import re

TIME = re.compile(r"^(\d{1,2})h(\d{2})$")
TEACHER = re.compile(r"^[A-ZÀ-Ü][A-ZÀ-Ü' -]*\s[A-Z]\.$")
QUINZ = re.compile(r"\s*\bQ([12])$")
ROOM_SEP = re.compile(r"[/,]")        # salles : « C 7/C 8 » (lycée), « B05 P,B11 » (collège)
PUA = re.compile(r"[-]")  # pictogrammes PRONOTE (police d'icônes) -> retirés du texte


def hhmm(t):
    h, m = TIME.match(t).groups()
    return f"{int(h):02d}:{m}"


def to_min(t):
    h, m = map(int, t.split(":")); return h * 60 + m


def parse_cell(raw, week=None):
    """Texte brut d'une case -> dict (matiere, profs, groupe, salles, quinzaine, pictogramme).
    Dernière ligne finissant par Q1/Q2 = quinzaine ; à défaut, `week` = lettre de semaine A/B
    encadrée (déjà retirée du texte) ; [..] = groupe ; NOM X. = profs ;
    1re ligne restante = matière ; suivantes = salles, découpées sur « / » ou « , »."""
    picto = bool(PUA.search(raw))
    lines = [PUA.sub("", l).strip() for l in raw.splitlines() if PUA.sub("", l).strip()]

    quinzaine = week
    if lines and QUINZ.search(lines[-1]):
        quinzaine = "Q" + QUINZ.search(lines[-1]).group(1)
        lines[-1] = QUINZ.sub("", lines[-1]).strip()
        if not lines[-1]: lines.pop()

    groupe = next((l.strip("[]") for l in lines if l.startswith("[")), None)
    lines = [l for l in lines if not l.startswith("[")]
    profs = [l for l in lines if TEACHER.match(l)]
    rest = [l for l in lines if not TEACHER.match(l)]
    matiere = rest[0] if rest else ""
    salles = [s.strip() for l in rest[1:] for s in ROOM_SEP.split(l) if s.strip()]
    return {"matiere": matiere, "profs": profs, "groupe": groupe, "salles": salles,
            "quinzaine": quinzaine, "pictogramme": picto}
