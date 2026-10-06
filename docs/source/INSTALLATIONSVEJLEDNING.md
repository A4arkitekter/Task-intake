# Installationsvejledning

Sådan kommer Indtagelse på en ny computer, og sådan opdateres den bagefter. Kollegaen har ikke GitHub-adgang. Kollegaens mappe er **ikke** et Git-repository.

## Hvad passer på computeren?

| Situationen | Gør dette |
|---|---|
| Programmet er **ikke installeret** | Følg **A - Førstegangsinstallation**. |
| En ældre version virker, men updaterfilerne mangler | Følg **B** én gang. |
| `OPDATER.bat` og `Update-Intake.ps1` ligger allerede lokalt | Start som sædvanligt. Følg **C**, når indbakken viser en opdatering. |

**Vigtigt:** Kør aldrig `OPDATER.bat` direkte fra NAS'en. Den skal køres fra computerens lokale programmappe, for eksempel `C:\apps\task-intake`.

## A - Førstegangsinstallation

IT henter programmet. Kollegaen skal ikke have GitHub-adgang. Du skal bruge internet og læseadgang til firmaets NAS.

### 1. Hent programmet (IT)

1. Åbn repositoryet og vælg **Code → Download ZIP**.
2. Pak ZIP-filen ud til:

```text
C:\apps\task-intake
```

`SETUP.bat` skal ligge direkte i denne mappe - ikke i en ekstra undermappe som `Task-intake-main`. Windows kan blokere scripts fra en ZIP; `SETUP.bat` fjerner den blokering selv.

### 2. Kopiér runtime fra NAS

1. Åbn `\\a4diskstation4\A4software\task-intake` i Stifinder.
2. Kopiér **hele mappen `runtime`** ind i `C:\apps\task-intake`.
3. Kontrollér, at denne fil findes:

```text
C:\apps\task-intake\runtime\runtime-manifest.json
```

Hvis stien indeholder `runtime\runtime`, er mappen lagt ét niveau for dybt. GitHub indeholder ikke modeller, EXE-filer eller DLL-filer.

### 3. Kør SETUP.bat

1. Dobbeltklik den lokale `SETUP.bat`.
2. Du skal **kun** svare på optagelsesmappe, Wrike-token og arbejdmail. Godkend en Windows-UAC, hvis den ligger bagved. **Skriv ikke ollama**, og brug ikke Ollamas vindue — luk det, hvis det kommer. Setup kører videre af sig selv.
3. Setup viser den mappe, optagelser hentes fra. Den finder selv ASR i OneDrive (`Apps\ASR Cloud Uploads\asr`) eller RecUp, hvis mappen allerede findes. Som reserve vises stadig `Dropbox\Apps\ASRRecordings`. Stien kan rettes senere i browseren.

```text
C:\Users\<windows-login>\OneDrive\Apps\ASR Cloud Uploads\asr
```

   Tryk Enter, hvis stien er rigtig. Ellers skriv RecUps mappe, fx `Dropbox\Apps\RecUp Memos`. Android bruger ASR Voice Recorder; iPhone bruger RecUp. ASR findes ikke i App Store.
4. Sæt **Wrike API-token** én gang. Wrike-mappe og prioritet (High som standard) vælges bagefter i browseren.
5. Skriv din **arbejdmail**. Den bruges til den daglige rykker, når et job ikke kom i Wrike.
6. Vent, til opsætningen er færdig.
7. Dobbeltklik `SYSTEMTJEK.bat`. Ved fejl sendes kun `fejlrapport.zip` til IT - ikke `.env` og ikke lyd.

GPU er en bonus. Uden NVIDIA kører Whisper og Ollama på CPU. Programmet starter ved login, så OneDrive-filer bliver behandlet uden at du åbner et sort vindue.

<!-- PAGEBREAK -->

## B - Gør en gammel installation klar til opdatering

Brug kun disse trin, hvis programmet allerede virker, men mangler updateren.

1. Luk programmet og browserfanen.
2. Åbn `\\a4diskstation4\A4software\task-intake\updates`.
3. Kopiér **begge** filer `OPDATER.bat` og `Update-Intake.ps1` ind i den lokale programmappe (samme sted som `SETUP.bat`).
4. Dobbeltklik den **lokale** `OPDATER.bat`.
5. Kør kun `SETUP.bat`, hvis updateren beder om det.

Updateren bevarer `.env`, `.venv`, `runtime`, `data/` og din mail og optagelsessti.

## C - Fremtidige opdateringer

1. Programmet kører ved login (eller startes med `START.bat`).
2. Er der en ny godkendt version, vises en blå bjælke i indbakken.
3. Afslut en eventuel igangværende optagelse.
4. Klik **Opdatér og genstart**.
5. Vent. Programmet lukker kort, opdaterer og kommer tilbage i browseren.

Hvis NAS ikke svarer inden 3 sekunder, vises ingen opdatering. Den installerede version virker stadig.

Ved en almindelig opdatering skal du ikke hente fra GitHub, kopiere runtime eller køre setup. `OPDATER.bat` er kun en reservefunktion til IT og må ikke køres fra NAS.

## Udvikler: udgiv en opdatering

1. Commit og push.
2. Dobbeltklik `UDGIV OPDATERING.bat` (kræver rent git-træ).
3. Pakken lander i `\\a4diskstation4\A4software\task-intake\updates`.
