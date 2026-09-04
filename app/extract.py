from __future__ import annotations

import re

from app.rewrite import rewrite_idea

FILLERS = re.compile(
    r"\b(?:øh+|øhm+|hmm+|altså|ligesom|ikke også|bare lige|ikke)\b[,\s]*",
    re.IGNORECASE,
)
SPACE = re.compile(r"\s+")

# Spoken lead-ins, applied repeatedly from the start.
PREAMBLE = re.compile(
    r"""^(?:
        ja|jo|nej|okay|ok|nå|så|øh+|altså|
        husk(?:\s+lige)?(?:\s+at)?|
        jeg\s+(?:skal|vil|burde|må|kan)(?:\s+lige)?(?:\s+have)?(?:\s+at)?|
        vi\s+(?:skal|vil|burde|må|kan|bør)(?:\s+lige)?(?:\s+have)?(?:\s+at)?|
        jeg\s+tænkte(?:\s+på)?(?:\s+at)?|
        jeg\s+tænker(?:\s+på)?(?:\s+at)?|
        det\s+var(?:\s+bare)?(?:\s+lige)?(?:\s+en\s+ting)?(?:\s+at)?|
        en\s+(?:idé|ting)(?:\s+mere)?(?:\s+er)?(?:\s+at)?|
        idéen\s+er(?:\s+at)?|
        opgaven\s+er(?:\s+at)?|
        der\s+skal(?:\s+lige)?|
        kan\s+du(?:\s+ikke)?|
        jeg\s+har\s+en(?:\s+ny)?\s+idé|
        den\s+(?:ve|ne)drører|
        der\s+handler\s+om(?:\s+at)?|
        vi\s+(?:skal|vil)\s+have(?:\s+(?:nogle|noget))?|
        nogle|noget|
        og\s+så|
        at
    )\s+""",
    re.IGNORECASE | re.VERBOSE,
)

# Infinitive → short Danish imperative for typical task verbs.
IMPERATIVE = {
    "sortere": "Sortér",
    "ringe": "Ring",
    "kalde": "Kald",
    "booke": "Book",
    "bestille": "Bestil",
    "sende": "Send",
    "skrive": "Skriv",
    "købe": "Køb",
    "hente": "Hent",
    "tjekke": "Tjek",
    "chekke": "Tjek",
    "kontrollere": "Kontrollér",
    "opdatere": "Opdater",
    "rette": "Ret",
    "lave": "Lav",
    "gøre": "Gør",
    "finde": "Find",
    "følge": "Følg",
    "følge op": "Følg op",
    "melde": "Meld",
    "aftale": "Aftal",
    "møde": "Mød",
    "huske": "Husk",
    "spørge": "Spørg",
    "svare": "Svar",
    "læse": "Læs",
    "se": "Se",
    "kigge": "Kig",
    "gennemgå": "Gennemgå",
    "forberede": "Forbered",
    "planlægge": "Planlæg",
    "flytte": "Flyt",
    "slette": "Slet",
    "tilføje": "Tilføj",
    "ændre": "Ændr",
    "betale": "Betal",
    "fakturere": "Fakturér",
    "godkende": "Godkend",
    "underskrive": "Underskriv",
    "printe": "Print",
    "udskrive": "Udskriv",
    "uploade": "Upload",
    "downloade": "Download",
    "dele": "Del",
    "invitere": "Invitér",
    "bekræfte": "Bekræft",
    "aflyse": "Aflys",
    "udsætte": "Udsæt",
    "rykke": "Ryk",
    "kontakte": "Kontakt",
    "maile": "Mail",
    "maile til": "Mail",
}


def extract_proposals(transcript: str) -> list[dict[str, str]]:
    cleaned = SPACE.sub(" ", (transcript or "").strip())
    if not cleaned:
        return []
    rewritten = rewrite_idea(cleaned)
    if rewritten:
        return [rewritten]
    note = cleaned if cleaned.endswith((".", "!", "?")) else cleaned + "."
    return [{"title": headline(cleaned), "note": note}]


_OPENER_SENTENCE = re.compile(
    r"^(?:jeg har en(?: ny)? idé|det (?:var|er) bare|den (?:ve|ne)drører)\b",
    re.IGNORECASE,
)


def headline(transcript: str) -> str:
    text = FILLERS.sub(" ", transcript)
    text = SPACE.sub(" ", text).strip(" .,-")
    text = _prefer_task_sentence(text)
    text = _strip_preamble(text)
    text = _take_after_modal(text)
    text = _to_imperative(text)
    text = _clip(text)
    return _title_case(text) or "Ny idé"


def _prefer_task_sentence(text: str) -> str:
    parts = [part.strip() for part in re.split(r"(?<=[\.!?])\s+", text) if part.strip()]
    if not parts:
        return text
    useful = [part for part in parts if not _OPENER_SENTENCE.match(part)]
    return useful[0] if useful else parts[-1]


def _take_after_modal(text: str) -> str:
    match = re.search(
        r"\b(?:skal|vil|bør|burde)\s+(?:lige\s+)?(?:have\s+(?:nogle|noget)\s+)?(.+)$",
        text,
        re.IGNORECASE,
    )
    if not match:
        return text
    rest = match.group(1).strip(" .,-")
    return rest if len(rest) >= 4 else text


def _strip_preamble(text: str) -> str:
    previous = None
    while text and text != previous:
        previous = text
        text = PREAMBLE.sub("", text, count=1).strip(" .,-")
    return text


def _to_imperative(text: str) -> str:
    lower = text.lower()
    for infinitive, imperative in sorted(IMPERATIVE.items(), key=lambda item: -len(item[0])):
        pattern = re.compile(r"^" + re.escape(infinitive) + r"\b", re.IGNORECASE)
        if pattern.match(lower):
            return pattern.sub(imperative, text, count=1)
    return text


def _clip(text: str) -> str:
    first = re.split(r"[\.!?]", text, maxsplit=1)[0].strip()
    if len(first) <= 60:
        return first.rstrip(" .,;:")
    trimmed = first[:60].rsplit(" ", 1)[0]
    return (trimmed or first[:60]).rstrip(" .,;:")


def _title_case(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    return text[0].upper() + text[1:]
