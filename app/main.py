from __future__ import annotations

import base64
import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .database import SignerDatabase
from .pdf_engine import SignatureStamp, apply_visual_signature, create_sample_pdf, sha256_bytes, sha256_file

APP_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"

STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "storage"))
DB_PATH = Path(os.getenv("DB_PATH", "data/assinador.db"))

app = FastAPI(title="Assinador Pro — Electronic Signature Studio", version="2.0.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
db = SignerDatabase(DB_PATH)


def seed_demo_documents() -> None:
    """Seeds 3 synthetic demo contracts on first boot so the UI is immediately interactive."""
    if db.list_documents():
        return
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    samples = [
        ("doc-demo-001", "Contrato de Serviços SaaS — Acme Logística", "Acme Logística Ltda.", "Marina Alves", "marina@acme-demo.example", True),
        ("doc-demo-002", "Acordo de Confidencialidade (NDA) — Vortex Cloud", "Vortex Cloud S.A.", "Lucas Pereira", "lucas@vortex-demo.example", False),
        ("doc-demo-003", "Proposta Comercial Anual — Horizonte Varejo", "Horizonte Varejo Ltda.", "Carla Souza", "carla@horizonte-demo.example", False),
    ]
    for doc_id, title, party, signer_name, signer_email, should_sign in samples:
        orig_path = STORAGE_DIR / f"{doc_id}_original.pdf"
        create_sample_pdf(orig_path, title=title, party_a=party)
        orig_hash = sha256_file(orig_path)
        db.create_document(doc_id, title, str(orig_path), orig_hash, signer_name=signer_name, signer_email=signer_email)
        if should_sign:
            signed_path = STORAGE_DIR / f"{doc_id}_signed.pdf"
            stamp = SignatureStamp(signer_name=signer_name, signer_email=signer_email, signer_ip="198.51.100.14")
            _, signed_hash, signed_ts = apply_visual_signature(orig_path, signed_path, stamp, doc_id)
            db.mark_signed(doc_id, str(signed_path), signed_hash, signer_name, signer_email, signed_ts, signer_ip="198.51.100.14")


seed_demo_documents()


def _render(template_name: str, replacements: dict[str, str] | None = None) -> str:
    html = (TEMPLATES_DIR / template_name).read_text(encoding="utf-8")
    for k, v in (replacements or {}).items():
        html = html.replace(k, v)
    return html


class PositionUpdate(BaseModel):
    page_index: int = 0
    x: float = 58.0
    y: float = 104.0


# ---- HTML Views ----
@app.get("/", response_class=HTMLResponse)
def dashboard_page() -> str:
    return _render("dashboard.html")


@app.get("/upload", response_class=HTMLResponse)
def upload_editor_page() -> str:
    return _render("editor.html", {"{{DOC_ID}}": ""})


@app.get("/editor/{doc_id}", response_class=HTMLResponse)
def document_editor_page(doc_id: str) -> str:
    if not db.get_document(doc_id):
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    return _render("editor.html", {"{{DOC_ID}}": doc_id})


@app.get("/sign/{doc_id}", response_class=HTMLResponse)
def sign_portal_page(doc_id: str) -> str:
    if not db.get_document(doc_id):
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    return _render("sign.html", {"{{DOC_ID}}": doc_id})


@app.get("/validate", response_class=HTMLResponse)
def validate_page() -> str:
    return _render("validate.html")


# ---- REST API ----
@app.get("/api/stats")
def api_stats() -> dict[str, Any]:
    return db.get_stats()


@app.get("/api/documents")
def api_list_documents() -> list[dict[str, Any]]:
    return db.list_documents()


@app.get("/api/documents/{doc_id}")
def api_get_document(doc_id: str) -> dict[str, Any]:
    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    return {**doc, "events": db.get_audit_events(doc_id)}


@app.get("/api/documents/{doc_id}/pdf")
def api_get_pdf(doc_id: str):
    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    target = Path(doc["signed_path"] or doc["original_path"])
    if not target.exists():
        raise HTTPException(status_code=404, detail="Arquivo PDF não encontrado.")
    return FileResponse(target, media_type="application/pdf")


@app.post("/api/documents")
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form("Documento Sem Título"),
    signer_name: str = Form(""),
    signer_email: str = Form(""),
) -> dict[str, Any]:
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF são aceitos.")
    doc_id = f"doc-{uuid.uuid4().hex[:10]}"
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    orig_path = STORAGE_DIR / f"{doc_id}_original.pdf"
    orig_path.write_bytes(await file.read())
    orig_hash = sha256_file(orig_path)
    db.create_document(doc_id, title, str(orig_path), orig_hash, signer_name=signer_name, signer_email=signer_email)
    return {"doc_id": doc_id, "title": title, "original_sha256": orig_hash, "status": "PENDING"}


@app.patch("/api/documents/{doc_id}/position")
def update_position(doc_id: str, body: PositionUpdate) -> dict[str, Any]:
    if not db.get_document(doc_id):
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    db.update_stamp_position(doc_id, body.page_index, body.x, body.y)
    return {"doc_id": doc_id, "page_index": body.page_index, "x": body.x, "y": body.y}


@app.post("/api/documents/{doc_id}/sign")
def sign_document(
    doc_id: str,
    request: Request,
    signer_name: str = Form(...),
    signer_email: str = Form(...),
    page_index: int = Form(0),
    x: float = Form(58.0),
    y: float = Form(104.0),
    signature_data_url: str = Form(""),
) -> dict[str, Any]:
    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")

    sig_png: bytes | None = None
    if signature_data_url and "," in signature_data_url:
        try:
            sig_png = base64.b64decode(signature_data_url.split(",", 1)[1])
        except Exception:
            sig_png = None

    signed_path = STORAGE_DIR / f"{doc_id}_signed.pdf"
    client_ip = request.client.host if request.client else "127.0.0.1"
    stamp = SignatureStamp(
        signer_name=signer_name,
        signer_email=signer_email,
        signer_ip=client_ip,
        page_index=page_index,
        x=x,
        y=y,
        signature_png_bytes=sig_png,
    )
    _, signed_hash, signed_ts = apply_visual_signature(Path(doc["original_path"]), signed_path, stamp, doc_id)
    db.mark_signed(doc_id, str(signed_path), signed_hash, signer_name, signer_email, signed_ts, signer_ip=client_ip)
    return {"doc_id": doc_id, "status": "SIGNED", "signed_sha256": signed_hash, "signed_at": signed_ts}


@app.get("/api/verify")
def api_verify_query(q: str = Query(...)) -> dict[str, Any]:
    doc = db.find_by_hash(q)
    if not doc:
        return {"found": False, "intact": False}
    target = Path(doc["signed_path"] or doc["original_path"])
    recorded = doc["signed_sha256"] or doc["original_sha256"]
    computed = sha256_file(target) if target.exists() else ""
    return {
        "found": True,
        "intact": bool(computed and computed == recorded),
        "doc_id": doc["doc_id"],
        "title": doc["title"],
        "status": doc["status"],
        "signer_name": doc["signer_name"],
        "signer_email": doc["signer_email"],
        "signed_at": doc["signed_at"],
        "recorded_sha256": recorded,
        "computed_sha256": computed,
        "events": db.get_audit_events(doc["doc_id"]),
    }


@app.post("/api/validate-upload")
async def api_validate_upload(file: UploadFile = File(...)) -> dict[str, Any]:
    computed = sha256_bytes(await file.read())
    doc = db.find_by_hash(computed)
    if not doc:
        return {"found": False, "intact": False, "computed_sha256": computed}
    return {
        "found": True,
        "intact": True,
        "doc_id": doc["doc_id"],
        "title": doc["title"],
        "status": doc["status"],
        "signer_name": doc["signer_name"],
        "signer_email": doc["signer_email"],
        "signed_at": doc["signed_at"],
        "recorded_sha256": doc["signed_sha256"] or doc["original_sha256"],
        "computed_sha256": computed,
        "events": db.get_audit_events(doc["doc_id"]),
    }


@app.get("/api/documents/{doc_id}/verify")
def verify_document(doc_id: str) -> dict[str, Any]:
    doc = db.get_document(doc_id)
    if not doc or not doc.get("signed_path"):
        raise HTTPException(status_code=404, detail="Documento assinado não encontrado.")
    signed_file = Path(doc["signed_path"])
    if not signed_file.exists():
        raise HTTPException(status_code=404, detail="Arquivo físico ausente no storage.")
    current_hash = sha256_file(signed_file)
    return {
        "doc_id": doc_id,
        "intact": current_hash == doc["signed_sha256"],
        "recorded_sha256": doc["signed_sha256"],
        "computed_sha256": current_hash,
    }


@app.get("/api/documents/{doc_id}/download")
def download_signed(doc_id: str):
    doc = db.get_document(doc_id)
    if not doc or not doc.get("signed_path"):
        raise HTTPException(status_code=404, detail="Documento assinado não encontrado.")
    return FileResponse(doc["signed_path"], media_type="application/pdf", filename=f"{doc_id}_assinado.pdf")
