from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


@dataclass(frozen=True)
class SignatureStamp:
    signer_name: str
    signer_email: str
    signer_ip: str = "127.0.0.1"
    page_index: int = 0
    x: float = 72.0
    y: float = 110.0
    signed_at_utc: str = ""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def create_sample_pdf(destination: Path, title: str = "Contrato de Prestação de Serviços (Demo)") -> Path:
    """Creates a synthetic 1-page PDF document for local demonstrations and testing."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, 760, title)
    c.setFont("Helvetica", 11)
    c.drawString(72, 725, "Documento fictício gerado automaticamente para validação do motor de assinatura.")
    c.drawString(72, 705, "Contratante: Empresa Demo Ltda.  |  Contratada: Consultoria Tech Exemplo S.A.")
    c.drawString(72, 675, "Cláusula 1 — Este arquivo não contém dados reais de terceiros.")
    c.drawString(72, 655, "Cláusula 2 — A integridade pós-assinatura é garantida por resumo criptográfico SHA-256.")
    c.line(72, 165, 340, 165)
    c.drawString(72, 150, "Área reservada para assinatura eletrônica")
    c.showPage()
    c.save()
    destination.write_bytes(buf.getvalue())
    return destination


def _build_stamp_overlay(stamp: SignatureStamp, original_hash: str, signed_ts: str, page_size: tuple[float, float]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=page_size)
    c.setStrokeColorRGB(0.12, 0.31, 0.47)
    c.setFillColorRGB(0.95, 0.97, 1.0)
    c.roundRect(stamp.x, stamp.y, 260, 56, 6, stroke=1, fill=1)
    c.setFillColorRGB(0.08, 0.2, 0.35)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(stamp.x + 10, stamp.y + 42, f"Assinado eletronicamente por {stamp.signer_name}")
    c.setFont("Helvetica", 8)
    c.drawString(stamp.x + 10, stamp.y + 29, f"E-mail: {stamp.signer_email} | IP: {stamp.signer_ip}")
    c.drawString(stamp.x + 10, stamp.y + 17, f"Data UTC: {signed_ts}")
    c.drawString(stamp.x + 10, stamp.y + 6, f"Hash Orig.: {original_hash[:24]}...")
    c.showPage()
    c.save()
    return buf.getvalue()


def _build_audit_certificate_page(stamp: SignatureStamp, original_hash: str, signed_ts: str, doc_id: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(72, 760, "Certificado de Assinatura Eletrônica e Auditoria")
    c.setFont("Helvetica", 10)
    lines = [
        f"Documento ID: {doc_id}",
        f"Signatário: {stamp.signer_name} <{stamp.signer_email}>",
        f"IP de Origem: {stamp.signer_ip}",
        f"Carimbo de Tempo (UTC): {signed_ts}",
        f"SHA-256 do Documento Original: {original_hash}",
        "Status: Assinatura concluída e registrada na trilha de auditoria.",
    ]
    y = 720
    for line in lines:
        c.drawString(72, y, line)
        y -= 22
    c.showPage()
    c.save()
    return buf.getvalue()


def apply_visual_signature(
    source_pdf: Path,
    output_pdf: Path,
    stamp: SignatureStamp,
    doc_id: str,
) -> tuple[str, str, str]:
    """Stamps a visual signature block onto the PDF, appends an audit page, and returns (orig_hash, signed_hash, ts)."""
    original_hash = sha256_file(source_pdf)
    signed_ts = stamp.signed_at_utc or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    reader = PdfReader(str(source_pdf))
    writer = PdfWriter()
    target_idx = min(max(stamp.page_index, 0), len(reader.pages) - 1)

    for idx, page in enumerate(reader.pages):
        if idx == target_idx:
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)
            overlay_bytes = _build_stamp_overlay(stamp, original_hash, signed_ts, (width, height))
            overlay_page = PdfReader(io.BytesIO(overlay_bytes)).pages[0]
            page.merge_page(overlay_page)
        writer.add_page(page)

    cert_bytes = _build_audit_certificate_page(stamp, original_hash, signed_ts, doc_id)
    writer.add_page(PdfReader(io.BytesIO(cert_bytes)).pages[0])

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    with output_pdf.open("wb") as f:
        writer.write(f)

    signed_hash = sha256_file(output_pdf)
    return original_hash, signed_hash, signed_ts
