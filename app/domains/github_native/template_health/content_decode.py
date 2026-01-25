from __future__ import annotations

import base64


def _decode_contents(payload: dict[str, object]) -> str | None:
    content = payload.get("content")
    encoding = payload.get("encoding")
    if not content:
        return None
    if encoding == "base64":
        try:
            normalized = "".join(str(content).split())
            decoded = base64.b64decode(normalized, validate=True).decode(
                "utf-8", errors="replace"
            )
        except (ValueError, UnicodeDecodeError):
            return None
        return decoded or None
    if isinstance(content, str):
        return content
    return None
