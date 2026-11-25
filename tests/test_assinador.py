import io
from pathlib import Path

from PIL import Image, ImageDraw
from pypdf import PdfReader

from app.database import SignerDatabase
from app.pdf_engine import SignatureStamp, apply_visual_signature, create_sample_pdf, sha256_file
from app.webhooks import build_signed_webhook_payload


def _make_demo_signature_png() -> bytes:
    img = Image.new("RGBA", (220, 60), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    draw.line([(12, 42), (75, 16), (140, 44), (205, 20)], fill=(11, 37, 64, 255), width=4)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_pdf_signature_stamping_with_png_and_tamper_detection(tmp_path: Path):
    orig = create_sample_pdf(tmp_path / "contract.pdf")
    signed = tmp_path / "contract_signed.pdf"
    db = SignerDatabase(tmp_path / "signer.db")
    doc_id = "doc-test-01"
    db.create_document(doc_id, "Contrato Teste", str(orig), sha256_file(orig))
    db.update_stamp_position(doc_id, page_index=0, x=64.0, y=120.0)

    stamp = SignatureStamp(
        signer_name="Lucas Pereira",
        signer_email="lucas@demo.example",
        x=64.0,
        y=120.0,
        signature_png_bytes=_make_demo_signature_png(),
    )
    orig_h, signed_h, ts = apply_visual_signature(orig, signed, stamp, doc_id)
    db.mark_signed(doc_id, str(signed), signed_h, stamp.signer_name, stamp.signer_email, ts)

    assert signed.exists()
    assert len(PdfReader(str(signed)).pages) == 2
    assert orig_h != signed_h
    assert sha256_file(signed) == signed_h
    assert db.get_stats() == {"total": 1, "signed": 1, "pending": 0, "completion_rate": 100.0}
    assert len(db.get_audit_events(doc_id)) == 3  # CREATED, POSITION_UPDATED, SIGNED
    assert db.find_by_hash(signed_h)["doc_id"] == doc_id

    signed.write_bytes(signed.read_bytes() + b"\n%tampered")
    assert sha256_file(signed) != signed_h


def test_webhook_hmac_payload():
    body, sig = build_signed_webhook_payload("doc_signed", "doc-1", "abc123", "secret")
    assert b"doc_signed" in body
    assert sig.startswith("sha256=")
    assert len(sig) == len("sha256=") + 64
