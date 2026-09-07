# Installation og opdatering

Brug denne vejledning ved en ny computer, en gammel installation eller en almindelig opdatering.

## Start her: Hvad passer på computeren?

| Situationen | Gør dette |
|---|---|
| Programmet er **ikke installeret** i en lokal mappe | Følg **A - Førstegangsinstallation**. |
| En ældre version virker, men de to updaterfiler mangler | Følg **B - Gør en gammel installation klar til opdatering** én gang. |
| `OPDATER.bat` og `Update-Intake.ps1` ligger allerede i den lokale programmappe | Start programmet normalt. Følg **C - Fremtidige opdateringer**, når indbakken viser en opdatering. |

**Vigtigt:** Kør aldrig `OPDATER.bat` direkte fra NAS'en. Updateren skal altid køres fra computerens lokale programmappe, for eksempel `C:\apps\task-intake`.

En **førstegangsinstallation** betyder, at computeren ikke har en fungerende lokal installation. Har en kollega allerede en ældre fungerende version, skal den normalt ikke installeres forfra.

Kollegaen har **ikke** GitHub-adgang. IT henter ZIP'en.

## A - Førstegangsinstallation

Du skal bruge internet og læseadgang til firmaets NAS. GitHub-adgang er kun nødvendig for den, der henter ZIP'en første gang.

### 1. Hent programmet (IT)

1. Åbn repositoryet i browseren og vælg **Code → Download ZIP**.
2. Pak ZIP-filen ud til en lokal mappe, for eksempel:

```text
C:\apps\task-intake
```

Kontrollér, at `SETUP.bat` ligger direkte i denne mappe - ikke i en ekstra undermappe som `Task-intake-main`. Windows kan blokere scripts fra en ZIP; `SETUP.bat` fjerner den blokering selv.

### 2. Kopiér hele runtime-mappen fra NAS

1. Åbn denne mappe i Stifinder:

```text
\\a4diskstation4\A4software\task-intake
```

2. Kopiér **hele mappen `runtime`**.
3. Indsæt den i den lokale programmappe.
4. Kontrollér, at denne fil findes:

```text
C:\apps\task-intake\runtime\runtime-manifest.json
```

Hvis stien indeholder `runtime\runtime`, er mappen lagt ét niveau for dybt.

GitHub indeholder ikke runtime, modeller, EXE-filer eller DLL-filer. Derfor skal runtime altid kopieres fra NAS ved en førstegangsinstallation.

Forventet indhold i `runtime/`:

- `runtime-manifest.json` med størrelser og sha256
- Whisper `large-v3` som `whisper-large-v3` eller `models--Systran--faster-whisper-large-v3`
- `OllamaSetup.exe` (og evt. `ollama-models` med `qwen2.5:14b`)
- valgfrit `gpu/*.whl` (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`) — installeres kun hvis NVIDIA findes

### 3. Installér og kontrollér

1. Dobbeltklik den lokale `SETUP.bat`.
2. Godkend eventuelle Windows-vinduer, der dukker op bag kommandovinduet.
3. Setup viser optagelsesstien (typisk `C:\Users\<login>\Dropbox\Apps\ASRRecordings`) og lader dig rette den. Derefter skal kollegaens arbejdmail udfyldes (`MAIL_CC` / `REMIND_TO`). Adgangskoden vises én gang.
4. Vent, til der står at opsætningen er færdig.
5. Dobbeltklik `SYSTEMTJEK.bat`.

Setup opretter lokale filer som `.env`, `.venv`, `install-state.json` og logfiler. De skal ikke kopieres mellem computere.

`.env` peger `INBOX_DIR` på `C:\Users\<login>\Dropbox\Apps\ASRRecordings`. Telefonen bruger ASR Voice Recorder med upload til Dropbox (Android eller iPhone). Mangler mappen, er det en advarsel — telefon eller Dropbox er ikke færdig — ikke et stop.

GPU er en bonus. Setup bruger CUDA når NVIDIA findes, ellers CPU. Whisper er `large-v3`. Ollama `qwen2.5:14b` kører også på CPU; første overskrift tager længere.

Hvis setup melder `Forkert checksum`, skal hele runtime-mappen kopieres igen fra NAS. Installationen må ikke fortsætte med en forkert runtime.

Programmet skal køre, når Dropbox lander en fil. Autostart bruger `Start-Indtagelse.ps1` skjult — ikke et sort konsolvindue, kollegaen skal huske at åbne.

## B - Gør en gammel installation klar til opdatering

Brug kun disse trin, hvis computeren allerede har en fungerende version, men mangler updateren.

1. Luk programmet og browserfanen.
2. Åbn denne mappe på NAS:

```text
\\a4diskstation4\A4software\task-intake\updates
```

3. Kopiér **begge** disse filer:
   - `OPDATER.bat`
   - `Update-Intake.ps1`
4. Indsæt begge filer i computerens eksisterende, lokale programmappe - samme sted som `SETUP.bat`.
5. Dobbeltklik den **lokale** `OPDATER.bat`.
6. Vent på beskeden om, at opdateringen er gennemført.
7. Kør kun `SETUP.bat`, hvis updateren udtrykkeligt beder om det.
8. Fremover vises nye opdateringer direkte i indbakken.

Det er ikke nok kun at kopiere `OPDATER.bat`; de to filer hører sammen.

Updateren bevarer computerens `runtime`, `.env`, `.venv`, `data/`, installationstilstand og lokale logfiler.

## C - Fremtidige opdateringer

Når begge updaterfiler findes lokalt, skal brugeren ikke holde øje med versioner eller have GitHub-adgang:

1. Programmet kører ved login (eller startes med `START.bat`).
2. Programmet kontrollerer automatisk den godkendte version på NAS.
3. Hvis der er en ny version, vises en blå besked øverst i indbakken.
4. Afslut først en eventuel igangværende optagelse.
5. Klik **Opdatér og genstart**.
6. Vent. Programmet lukker kortvarigt, installerer opdateringen og kommer automatisk tilbage i browseren.

Hvis NAS'en midlertidigt ikke kan kontaktes (ingen svar på port 445 inden 3 sekunder), vises ingen opdatering. Den installerede version kan fortsat bruges.

Ved en almindelig opdatering skal brugeren ikke hente fra GitHub, kopiere filer, køre en batchfil, kopiere runtime eller køre setup.

`OPDATER.bat` er herefter kun en reservefunktion til IT. Den skal fortsat kun køres fra den lokale programmappe.

Et `.git`-katalog slår opdateringsknappen fra, så udviklermaskinen ikke overskriver sig selv.

### Kan updateren bruges uden en installation?

**Nej.** Updateren erstatter programfiler i en eksisterende lokal installation. Den installerer ikke runtime, Python-miljø eller `.env`. På en computer uden en fungerende installation skal du følge **A - Førstegangsinstallation**.

## Udvikler: udgiv en opdatering

1. Commit og push.
2. Dobbeltklik `UDGIV OPDATERING.bat` (kræver rent git-træ).
3. Pakken og `latest.json` lander i `\\a4diskstation4\A4software\task-intake\updates`.
