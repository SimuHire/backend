from __future__ import annotations


def parse_sender(value: str) -> tuple[str, str | None]:
    """Split 'Name <email@x>' into (email, name)."""
    if not value:
        return "", None
    text = value.strip()
    if "<" in text and ">" in text:
        name_part, _, rest = text.partition("<")
        email = rest.split(">", 1)[0].strip()
        name = name_part.strip().strip('"') or None
        return email, name
    return text, None
