from hmac import compare_digest
from pathlib import Path

from fastapi import HTTPException


def load_operations_token(token: str, token_file: str) -> str:
    if token:
        return token
    if not token_file:
        return ""
    try:
        return Path(token_file).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def require_operations_access(
    *,
    configured_token: str,
    authorization: str | None,
    environment: str,
) -> None:
    if not configured_token:
        if environment == "online":
            raise HTTPException(status_code=503, detail="Operations token is not configured")
        return
    scheme, _, provided_token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not compare_digest(
        provided_token, configured_token
    ):
        raise HTTPException(status_code=401, detail="Invalid operations token")
