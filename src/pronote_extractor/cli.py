"""Usage : python -m pronote_extractor edt.pdf > edt.json"""
import json
import sys

from . import extract
from .errors import ExtractionError


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        out = extract(argv[0])
    except ExtractionError as e:
        print(json.dumps({"error": e.code, "detail": e.detail}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0
