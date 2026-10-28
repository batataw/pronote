"""Extraction déterministe d'un emploi du temps PRONOTE exporté en PDF -> JSON."""
from pathlib import Path

from .detect import detect
from .errors import ExtractionError


def extract(src):
    """Chemin ou `bytes` -> modèle commun (dict). Le contenu doit être un PDF."""
    data = bytes(src) if isinstance(src, (bytes, bytearray, memoryview)) else Path(src).read_bytes()
    detect(data)
    from .pdf.extract import extract as extract_pdf
    return extract_pdf(data)


__all__ = ["extract", "detect", "ExtractionError"]
