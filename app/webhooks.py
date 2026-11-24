from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any


def build_signed_webhook_payload(event_type: str, doc_id: str, signed_sha256: str, secret: str) -> tuple[bytes, str]:
    """Builds a JSON webhook body and its HMAC-SHA256 hex digest."""
    body_obj: dict[str, Any] = {
        "event_type": event_type,
        "document_id": doc_id,
        "signed_sha256": signed_sha256,
    }
    raw = json.dumps(body_obj, sort_keys=True).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return raw, f"sha256={sig}"
