r"""Prøve: kan sprogmodellen holde en lang indtaling uden at miste slutningen?

Kræver at Ollama kører, så den hører ikke hjemme i tests\.
Kør med:  .\.venv\Scripts\python.exe scripts\probe_long_note.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.rewrite import context_size, rewrite_idea

LONG = """
Jeg har en idé om, at vi skal have styr på hele lageret i Hedehusene, for det er
efterhånden blevet et rod, og vi bruger alt for lang tid på at finde ting. Først og
fremmest skal vi have lavet en optælling af alt hvad der står på reol femten til
tyveogtyve, for jeg tror der står varer derinde fra to tusind og treogtyve som vi
aldrig får solgt. Morten mente at der stod for omkring hundrede og fyrre tusind
kroner, men jeg tror det er mere. Vi skal have en beslutning om hvad der skal
skrottes, og det skal ikke være mig der beslutter det alene, det skal op på et møde
med Lene og Morten og gerne også Kasper fra økonomi. Dernæst er der selve
indretningen. Jeg synes vi skal flytte de hurtige varenumre ned i øjenhøjde, altså
det vi plukker allermest, fordi lige nu står de øverst og folk skal have stigen frem
hver gang, og det er både langsomt og noget rod med arbejdsmiljøet. Der var en
arbejdsmiljørepræsentant der nævnte det sidste år, og vi fik aldrig gjort noget ved
det. Så skal vi have nye labels på alle hylder, for de gamle kan man ikke læse
længere, og scanneren kan slet ikke læse dem. Jeg har snakket med en leverandør der
heder Nordlabel, og de kan lave dem for omkring tolv tusind kroner for hele lageret,
inklusive montering, og det synes jeg faktisk er billigt i forhold til den tid vi
spilder. Der er også hele spørgsmålet om vi skal have et rigtigt lagerstyringssystem
i stedet for de regneark vi bruger nu. Jeg ved godt det er en større ting, og det
koster penge, men vi taber ordrer fordi vi siger at noget er på lager og så er det
ikke, og det er sket tre gange bare i denne måned. Kunden i Aalborg var meget
utilfreds. Jeg tænker vi skal have et par tilbud hjem, og jeg vil gerne se på om
det vi allerede betaler for i økonomisystemet kan noget vi ikke bruger. Til sidst,
og det er faktisk det vigtigste, så skal vi have en fast rutine hvor der bliver
ryddet op hver fredag eftermiddag i en halv time, alle mand, for ellers falder vi
tilbage i det samme rod om tre måneder, uanset hvor fint vi rydder op nu. Og en
allersidste ting som jeg ikke må glemme: hele det her skal være færdigt inden
lagerrevisionen den fjortende november, for ellers får vi samme bemærkning i
revisionsprotokollen som sidste år.
""".strip()


def main() -> int:
    print(f"LAENGDE     {len(LONG)} tegn")
    print(f"NUM_CTX     {context_size(LONG)} (foer aendringen: altid 2048)")

    card = rewrite_idea(LONG)
    if not card:
        print("INTET KORT  sprogmodellen svarede ikke")
        return 1

    print(f"TITEL       {card['title']}")
    print(f"NOTE        {card['note']}")

    # Datoen staar allersidst i indtalingen. I et 2048-vindue ville den vaere klippet
    # vaek, foer modellen naaede at se den.
    note = card["note"].lower()
    hit = next((word for word in ("november", "fjortende", "14") if word in note), None)
    print(f"HALEN MED   {'ja, noten naevner ' + hit if hit else 'nej, slutningen naaede ikke med'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
