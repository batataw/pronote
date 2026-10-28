"""Microservice HTTP : POST /extract, GET /health. Écoute locale uniquement (appelé par NestJS)."""
from importlib.metadata import version

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse

from . import extract
from .errors import ExtractionError

MAX_UPLOAD = 10 * 1024 * 1024

app = FastAPI(title="pronote-extractor")


def error(status, code, detail=""):
    return JSONResponse(status_code=status, content={"error": code, "detail": detail})


@app.get("/health")
def health():
    return {"ok": True, "pdfplumber": version("pdfplumber")}


@app.post("/extract")
def extract_endpoint(file: UploadFile = File(...)):
    data = file.file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        return error(413, "too_large", "fichier > 10 Mo")
    try:
        return extract(data)
    except ExtractionError as e:
        return error(422, e.code, e.detail)
