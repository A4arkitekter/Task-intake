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
2. Du skal **ikke skrive noget** i SETUP. Godkend en Windows-UAC, hvis den ligger bagved. **Skriv ikke ollama**, og brug ikke Ollamas vindue — luk det, hvis det kommer. Setup kører færdig af sig selv.
3. Setup finder selv mappen, optagelser hentes fra: ASR i OneDrive (`Apps\ASR Cloud Uploads\asr`) eller RecUp, med `Dropbox\Apps\ASRRecordings` som reserve. Stien rettes i browseren bagefter. Android bruger ASR Voice Recorder; iPhone bruger RecUp. ASR findes ikke i App Store.

```text
C:\Users\<windows-login>\OneDrive\Apps\ASR Cloud Uploads\asr
```
4. Vent, til opsætningen er færdig. Åbn [http://127.0.0.1:7000](http://127.0.0.1:7000).
5. I administrationen står der trin for trin, hvad du skal kopiere fra Wrike. Du skal indsætte **tre nøgler**, som du selv laver — ikke en kollegas:

   1. Tryk **Åbn Wrike API-siden**.
   2. Log ind med **din** arbejdmail.
   3. Tryk **+ App**. App-navn: **Indtagelse**. Gem. En almindelig Wrike-bruger kan gøre det — det er tjekket.
   4. Kopiér **Client ID**, **Secret key** (øje-ikonet viser teksten) og **Permanent access token** (Get token / Obtain token). Indsæt i de tre felter. Tryk **Gem nøgler**.
   5. Siden skriver **Wrike ser dig som: [dit navn]**. Er det en kollegas navn, er token forkert.

   Token arver den brugers mapper. Derfor kan I ikke dele de tre nøgler.
6. Udfyld **mail til IT-support** (besked kun ved fejl) og ret optagelsesmappen, hvis stien er forkert. Wrike-mappe og prioritet (High som standard) vælges samme sted.
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
