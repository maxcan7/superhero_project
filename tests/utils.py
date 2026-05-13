"""Test utilities."""

import json
from base64 import b64encode

import itsdangerous


def make_session_cookie(session_data: dict[str, object], secret: str) -> str:
    """Return a Starlette-compatible signed session cookie value."""
    data = b64encode(json.dumps(session_data).encode("utf-8"))
    signer = itsdangerous.TimestampSigner(secret)
    return signer.sign(data).decode("utf-8")
