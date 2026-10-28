"""Modèle de sortie (spec §5)."""
from dataclasses import asdict, dataclass, field


@dataclass
class Course:
    jour: str
    debut: str
    fin: str
    matiere: str
    profs: list = field(default_factory=list)
    groupe: str | None = None
    salles: list = field(default_factory=list)
    quinzaine: str | None = None      # "Q1", "Q2" ou None
    demi_case: bool = False           # case partagée avec un autre groupe
    pictogramme: bool = False         # glyphe d'icône PRONOTE dans la case (sens inconnu)
    horaire_estime: bool = False      # horaire interpolé, case non alignée sur l'axe
    page: int | None = None           # page du PDF (1 = première)


@dataclass
class Result:
    source: str                       # toujours "pdf"
    etablissement: str | None
    creneaux: list
    cours: list
    warnings: list

    def to_dict(self):
        return asdict(self)
