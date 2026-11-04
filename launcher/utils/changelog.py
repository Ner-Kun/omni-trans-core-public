import re

_NOTE_RE = re.compile(r"^\*\*Note:\*\*\s*(.+?)\s*$", re.IGNORECASE)
_GENERIC_HEADING_RE = re.compile(
    r"^#\s+(changelog|release notes?|what'?s new)\s*$",
    re.IGNORECASE,
)


def clean_changelog(text: str) -> tuple[str, str | None]:
    """Split release notes into a body and an optional GitHub fallback note."""
    note = None
    lines = (text or "").strip().splitlines()

    while lines and not lines[0].strip():
        lines.pop(0)

    if lines:
        match = _NOTE_RE.match(lines[0].strip())
        if match:
            note = match.group(1).strip()
            lines.pop(0)

    while lines and not lines[0].strip():
        lines.pop(0)

    if lines and _GENERIC_HEADING_RE.match(lines[0].strip()):
        lines.pop(0)

    while lines and not lines[0].strip():
        lines.pop(0)

    return "\n".join(lines).strip(), note
