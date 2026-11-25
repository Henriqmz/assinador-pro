from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
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
    signature_png_bytes: bytes | None = None


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def create_sample_pdf(
    destination: Path,
    title: str = "Contrato de Prestação de Serviços (Demo)",
    party_a: str = "Acme Logística Ltda.",
    party_b: str = "Consultoria Tech Exemplo S.A.",
) -> Path:
    """Creates a clean synthetic 1-page business PDF for demos and automated tests."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    # Subtle header bar
    c.setFillColorRGB(0.06, 0.11, 0.18)
    c.rect(0, 790, A4[0], 52, stroke=0, fill=1)
    c.setFillColorRGB(0.85, 0.95, 1.0)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(54, 811, title)

    c.setFillColorRGB(0.12, 0.16, 0.22)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(54, 752, "1. IDENTIFICAÇÃO DAS PARTES")
    c.setFont("Helvetica", 10)
    c.drawString(54, 732, f"CONTRATANTE: {party_a} (Dados sintéticos para demonstração)")
    c.drawString(54, 715, f"CONTRATADA:  {party_b}")

    c.setFont("Helvetica-Bold", 11)
    c.drawString(54, 680, "2. OBJETO E ESCOPO")
    c.setFont("Helvetica", 10)
    clauses = [
        "2.1. O presente instrumento estabelece a entrega de integrações de APIs, automações",
        "operacionais e painéis de acompanhamento conforme cronograma aprovado pelas partes.",
        "2.2. Este documento é integralmente fictício, gerado automaticamente para validação",
        "do motor de assinatura eletrônica e verificação criptográfica SHA-256.",
        "2.3. Após a assinatura eletrônica, qualquer alteração binária no arquivo invalida",
        "automaticamente o resumo criptográfico registrado na folha de auditoria.",
    ]
    y = 660
    for line in clauses:
        c.drawString(54, y, line)
        y -= 18

    c.setStrokeColorRGB(0.75, 0.80, 0.86)
    c.setDash(4, 3)
    c.roundRect(54, 100, 270, 82, 6, stroke=1, fill=0)
    c.setDash()
    c.setFillColorRGB(0.45, 0.52, 0.60)
    c.setFont("Helvetica", 9)
    c.drawString(66, 166, "Área reservada para assinatura eletrônica")

    c.showPage()
    c.save()
    destination.write_bytes(buf.getvalue())
    return destination


def _build_stamp_overlay(
    stamp: SignatureStamp,
    original_hash: str,
    signed_ts: str,
    page_size: tuple[float, float],
) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=page_size)
    box_w, box_h = 264, 76 if stamp.signature_png_bytes else 58

    c.setStrokeColorRGB(0.14, 0.40, 0.62)
    c.setFillColorRGB(0.95, 0.98, 1.0)
    c.roundRect(stamp.x, stamp.y, box_w, box_h, 6, stroke=1, fill=1)

    text_top = stamp.y + box_h - 14
    if stamp.signature_png_bytes:
        try:
            img = ImageReader(io.BytesIO(stamp.signature_png_bytes))
            c.drawImage(
                img,
                stamp.x + 10,
                stamp.y + box_h - 32,
                width=120,
                height=26,
                preserveAspectRatio=True,
                mask="auto",
            )
            text_top = stamp.y + box_h - 42
        except Exception:
            pass

    c.setFillColorRGB(0.06, 0.16, 0.28)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(stamp.x + 10, text_top, f"Assinado eletronicamente por {stamp.signer_name}")
    c.setFont("Helvetica", 7.5)
    c.drawString(stamp.x + 10, text_top - 11, f"E-mail: {stamp.signer_email} | IP: {stamp.signer_ip}")
    c.drawString(stamp.x + 10, text_top - 21, f"UTC: {signed_ts} | SHA-256: {original_hash[:18]}...")
    c.showPage()
    c.save()
    return buf.getvalue()


def _build_audit_certificate_page(
    stamp: SignatureStamp,
    original_hash: str,
    signed_ts: str,
    doc_id: str,
) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    c.setFillColorRGB(0.06, 0.11, 0.18)
    c.rect(0, 785, A4[0], 57, stroke=0, fill=1)
    c.setFillColorRGB(0.85, 0.95, 1.0)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(54, 808, "Certificado de Assinatura Eletrônica e Auditoria")

    c.setFillColorRGB(0.10, 0.14, 0.20)
    c.setFont("Helvetica", 10.5)
    lines = [
        f"ID do Documento: {doc_id}",
        f"Signatário: {stamp.signer_name} <{stamp.signer_email}>",
        f"Endereço IP de Origem: {stamp.signer_ip}",
        f"Carimbo de Tempo (UTC): {signed_ts}",
        f"Posição do Carimbo: Página {stamp.page_index + 1} (X={stamp.x:.0f}, Y={stamp.y:.0f})",
        f"SHA-256 (Original): {original_hash}",
        "Status: Assinatura concluída e selada com trilha de auditoria.",
    ]
    y = 740
    for line in lines:
        c.drawString(54, y, line)
        y -= 24

    if stamp.signature_png_bytes:
        try:
            c.setFont("Helvetica-Bold", 10)
            c.drawString(54, y - 16, "Representação Gráfica da Assinatura:")
            img = ImageReader(io.BytesIO(stamp.signature_png_bytes))
            c.drawImage(img, 54, y - 82, width=200, height=56, preserveAspectRatio=True, mask="auto")
        except Exception:
            pass

    c.showPage()
    c.save()
    return buf.getvalue()


def apply_visual_signature(
    source_pdf: Path,
    output_pdf: Path,
    stamp: SignatureStamp,
    doc_id: str,
) -> tuple[str, str, str]:
    """Stamps a visual signature block (optional PNG drawing) onto the PDF and appends an audit page."""
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
