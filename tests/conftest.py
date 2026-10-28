import importlib.util
import json
from pathlib import Path

import pytest

TESTS = Path(__file__).parent
FIXTURES = TESTS / "fixtures"
NOAM_PDF = FIXTURES / "noam.pdf"


def load_reference(name):
    """Prototype de la spec (annexe A), verbatim, chargé comme module."""
    spec = importlib.util.spec_from_file_location(f"ref_{name}", TESTS / "reference" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def noam_expected():
    return json.loads((FIXTURES / "noam.expected.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def pdf_prototype_output():
    return load_reference("pronote_pdf_extract").extract(str(NOAM_PDF))


@pytest.fixture(scope="session")
def pdf_output():
    from pronote_extractor.pdf.extract import extract
    return extract(NOAM_PDF)
