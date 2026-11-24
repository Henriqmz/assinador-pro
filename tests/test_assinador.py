from pathlib import Path

from pypdf import PdfReader

from app.database import SignerDatabase
from app.pdf_engine import SignatureStamp, apply_visual_signature, create_sample_pdf, sha256_file
from app.webhooks import build_signed_webhook_payload


def test_pdf_signature_stamping_and_tamper_detection(tmp_path: Path):
    orig = create_sample_pdf(tmp_path / "contract.pdf")
    signed = tmp_path / "contract_signed.pdf"
    db = SignerDatabase(tmp_path / "signer.db")
    doc_id = "doc-test-01"
    db.create_document(doc_id, "Contrato Teste", str(orig), sha256_file(orig))

    stamp = SignatureStamp(signer_name="Lucas Pereira", signer_email="lucas@demo.example")
    orig_h, signed_h, ts = apply_visual_signature(orig, signed, stamp, doc_id)
    db.mark_signed(doc_id, str(signed), signed_h, stamp.signer_name, stamp.signer_email, ts)

    assert signed.exists()
    # Original 1 page + 1 appended audit certificate page = 2 pages
    assert len(PdfReader(str(signed)).pages) == 2
    assert orig_h != signed_h
    assert sha256_file(signed) == signed_h

    # Tampering must invalidate SHA-256 verification
    signed.write_bytes(signed.read_bytes() + b"\n%tampered")
    assert sha256_file(signed) != signed_h


def test_webhook_hmac_payload():
    body, sig = build_signed_webhook_payload("doc_signed", "doc-1", "abc123", "secret")
    assert b"doc_signed" in body
    assert sig.startswith("sha256=")
    assert len(sig) == len("sha256=") + 64
