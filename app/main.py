from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from .database import SignerDatabase
from .pdf_engine import SignatureStamp, apply_visual_signature, sha256_file

STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "storage"))
DB_PATH = Path(os.getenv("DB_PATH", "data/assinador.db"))

app = FastAPI(title="Assinador Pro API", version="1.0.0")
db = SignerDatabase(DB_PATH)

INDEX_HTML = """<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <title>Assinador Pro — Estúdio de Assinatura PDF</title>
  <style>
    body { font-family: system-ui, sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 2rem; }
    .box { max-width: 720px; margin: auto; background: #1e293b; padding: 1.5rem 2rem; border-radius: 12px; }
    h1 { margin-top: 0; color: #38bdf8; }
    a { color: #38bdf8; }
    code { background: #0f172a; padding: .2rem .4rem; border-radius: 4px; }
  </style>
</head>
<body>
  <div class="box">
    <h1>Assinador Pro</h1>
    <p>Estúdio de assinatura eletrônica em PDF com carimbo visual, certificado de auditoria e verificação criptográfica SHA-256.</p>
    <p>Explore a API interativa em <a href="/docs">/docs</a> ou envie um PDF via <code>POST /api/documents</code>.</p>
  </div>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX_HTML


@app.post("/api/documents")
async def upload_document(file: UploadFile = File(...), title: str = Form("Documento Sem Título")):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF são aceitos.")
    doc_id = f"doc-{uuid.uuid4().hex[:10]}"
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    orig_path = STORAGE_DIR / f"{doc_id}_original.pdf"
    orig_path.write_bytes(await file.read())
    orig_hash = sha256_file(orig_path)
    db.create_document(doc_id, title, str(orig_path), orig_hash)
    return {"doc_id": doc_id, "title": title, "original_sha256": orig_hash, "status": "PENDING"}


@app.post("/api/documents/{doc_id}/sign")
def sign_document(
    doc_id: str,
    request: Request,
    signer_name: str = Form(...),
    signer_email: str = Form(...),
    page_index: int = Form(0),
    x: float = Form(72.0),
    y: float = Form(110.0),
):
    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    signed_path = STORAGE_DIR / f"{doc_id}_signed.pdf"
    client_ip = request.client.host if request.client else "127.0.0.1"
    stamp = SignatureStamp(
        signer_name=signer_name,
        signer_email=signer_email,
        signer_ip=client_ip,
        page_index=page_index,
        x=x,
        y=y,
    )
    _, signed_hash, signed_ts = apply_visual_signature(Path(doc["original_path"]), signed_path, stamp, doc_id)
    db.mark_signed(doc_id, str(signed_path), signed_hash, signer_name, signer_email, signed_ts)
    return {"doc_id": doc_id, "status": "SIGNED", "signed_sha256": signed_hash, "signed_at": signed_ts}


@app.get("/api/documents/{doc_id}/verify")
def verify_document(doc_id: str):
    doc = db.get_document(doc_id)
    if not doc or not doc.get("signed_path"):
        raise HTTPException(status_code=404, detail="Documento assinado não encontrado.")
    signed_file = Path(doc["signed_path"])
    if not signed_file.exists():
        raise HTTPException(status_code=404, detail="Arquivo físico ausente no storage.")
    current_hash = sha256_file(signed_file)
    intact = current_hash == doc["signed_sha256"]
    return {
        "doc_id": doc_id,
        "intact": intact,
        "recorded_sha256": doc["signed_sha256"],
        "computed_sha256": current_hash,
    }


@app.get("/api/documents/{doc_id}/download")
def download_signed(doc_id: str):
    doc = db.get_document(doc_id)
    if not doc or not doc.get("signed_path"):
        raise HTTPException(status_code=404, detail="Documento assinado não encontrado.")
    return FileResponse(doc["signed_path"], media_type="application/pdf", filename=f"{doc_id}_assinado.pdf")
