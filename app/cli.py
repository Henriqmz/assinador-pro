from __future__ import annotations

import argparse
from pathlib import Path

from .database import SignerDatabase
from .pdf_engine import SignatureStamp, apply_visual_signature, create_sample_pdf, sha256_file
from .webhooks import build_signed_webhook_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Assinador Pro — Demo CLI")
    parser.add_argument("--demo", action="store_true", help="Gera PDF demo, aplica assinatura visual e valida SHA-256")
    args = parser.parse_args()
    if not args.demo:
        print("Use --demo para executar a demonstração completa ou 'uvicorn app.main:app --reload'.")
        return

    storage = Path("storage")
    db = SignerDatabase(Path("data/assinador_demo.db"))
    doc_id = "doc-demo-001"
    orig = create_sample_pdf(storage / f"{doc_id}_original.pdf")
    signed = storage / f"{doc_id}_signed.pdf"
    db.create_document(doc_id, "Contrato Demo SaaS", str(orig), sha256_file(orig))

    stamp = SignatureStamp(signer_name="Marina Alves", signer_email="marina@acme-demo.example", signer_ip="198.51.100.10")
    orig_h, signed_h, ts = apply_visual_signature(orig, signed, stamp, doc_id)
    db.mark_signed(doc_id, str(signed), signed_h, stamp.signer_name, stamp.signer_email, ts)
    _, webhook_sig = build_signed_webhook_payload("doc_signed", doc_id, signed_h, "demo-hmac-secret")

    print(f"PDF original:  {orig} (SHA-256: {orig_h[:16]}...)")
    print(f"PDF assinado:  {signed} (SHA-256: {signed_h[:16]}...)")
    print(f"Integridade OK: {sha256_file(signed) == signed_h}")
    print(f"Assinatura Webhook HMAC: {webhook_sig[:24]}...")


if __name__ == "__main__":
    main()
