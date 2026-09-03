from __future__ import annotations

import re

FILLERS = (
    r"øh+",
    r"øhm+",
    r"hmm+",
    r"altså",
    r"ligesom",
    r"ikke også",
)
LEAD_STRIP = (
    r"husk(?:\s+lige)?\s+at",
    r"husk",
    r"jeg skal(?:\s+lige)?(?:\s+have)?",
    r"jeg vil(?:\s+gerne)?",
    r"jeg tænkte(?:\s+på)?(?:\s+at)?",
    r"en idé(?:\s+er)?(?:\s+at)?",
    r"idéen er(?:\s+at)?",
    r"opgaven er(?:\s+at)?",
    r"så skal jeg",
    r"så skal vi",
    r"og så",
    r"så",
)

SPLIT_MARKERS = re.compile(
    r"""
    \n+
    | (?<=[\.\!\?]) \s+
    | \s+ (?:og\s+så|dernæst|derefter|en\s+anden\s+ting|for\s+det\s+(?:første|andet|tredje)) \s+
    | \s+ (?:nummer|nr\.?)\s+(?:to|tre|fire|fem|\d+) [\.\:)]? \s+
    | (?<=\d[\.\)]) \s+
    """,
    re.IGNORECASE | re.VERBOSE,
)

SPACE = re.compile(r"\s+")
LEAD_RE = re.compile(r"^(?:" + r"|".join(LEAD_STRIP) + r")\s+", re.IGNORECASE)
FILLER_RE = re.compile(r"\b(?:" + r"|".join(FILLERS) + r")\b[,\s]*", re.IGNORECASE)


def extract_proposals(transcript: str) -> list[dict[str, str]]:
    cleaned = SPACE.sub(" ", (transcript or "").strip())
    if not cleaned:
        return []

    chunks = [chunk.strip(" -–—,;:") for chunk in SPLIT_MARKERS.split(cleaned) if chunk and chunk.strip()]
    chunks = [chunk for chunk in chunks if _is_content(chunk)]
    if not chunks:
        chunks = [cleaned]

    proposals: list[dict[str, str]] = []
    for chunk in chunks:
        title, note = _to_title_note(chunk)
        if title:
            proposals.append({"title": title, "note": note})

    if not proposals:
        title, note = _to_title_note(cleaned)
        proposals.append({"title": title or "Ny idé", "note": note})
    return proposals


def _is_content(chunk: str) -> bool:
    words = FILLER_RE.sub(" ", chunk).strip()
    return len(words) >= 8


def _to_title_note(chunk: str) -> tuple[str, str]:
    text = FILLER_RE.sub(" ", chunk)
    text = SPACE.sub(" ", text).strip(" .")
    rest = text
    stripped = LEAD_RE.sub("", text).strip()
    if stripped:
        text = stripped
    title = _title_case(_clip_title(text))
    note = rest if rest != title else text
    if note and not note.endswith((".", "!", "?")):
        note = note + "."
    return title, note


def _clip_title(text: str) -> str:
    first = re.split(r"[:–—]|\s+[-]\s+", text, maxsplit=1)[0].strip()
    if len(first) <= 72:
        return first.rstrip(".!,;")
    trimmed = first[:72].rsplit(" ", 1)[0]
    return (trimmed or first[:72]).rstrip(".!,;")


def _title_case(text: str) -> str:
    if not text:
        return "Ny idé"
    return text[0].upper() + text[1:]
