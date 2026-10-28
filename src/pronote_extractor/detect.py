"""Type d'entrée déterminé par le contenu (signature d'octets), jamais par l'extension.
Seul le PDF exporté par PRONOTE est accepté."""
from .errors import ExtractionError


def detect(data):
    """`bytes` -> "pdf" ; ExtractionError("unsupported_type") sinon.
    La signature est cherchée dans le 1er Kio (la norme tolère des octets avant `%PDF-`)."""
    if b"%PDF-" in bytes(data[:1024]): return "pdf"
    raise ExtractionError("unsupported_type", "PDF exporté depuis PRONOTE attendu")
