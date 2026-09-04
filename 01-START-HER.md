# Start her (IT)

Kollegaen har ikke GitHub-adgang. Du henter programmet én gang, kopierer runtime fra NAS og kører setup. Bagefter opdaterer kollegaen med knappen **Opdatér og genstart** i indbakken.

Kollegaens mappe er **ikke** et Git-repository.

## Første computer

1. Download ZIP fra GitHub (`Code → Download ZIP`) og pak den ud til:

   ```text
   C:\apps\task-intake
   ```

   `SETUP.bat` skal ligge direkte i den mappe — ikke i en ekstra undermappe.

2. Kopiér **hele** `runtime` fra NAS:

   ```text
   \\a4diskstation4\A4software\task-intake\runtime
   ```

   til `C:\apps\task-intake\runtime`. Denne fil skal findes:

   ```text
   C:\apps\task-intake\runtime\runtime-manifest.json
   ```

   Hvis stien indeholder `runtime\runtime`, er mappen lagt ét niveau for dybt.

3. Dobbeltklik `SETUP.bat`. Godkend Windows-vinduer, der dukker op bagved.
4. Dobbeltklik `SYSTEMTJEK.bat`. Send kun `fejlrapport.zip` til IT ved fejl — ikke `.env` og ikke lyd.
5. Programmet starter af sig selv ved login. Manuelt: `START.bat`.

GPU er en bonus. Uden NVIDIA kører Whisper og Ollama på CPU; første overskrift tager længere.

Dropbox-mappen er `C:\Users\<login>\Dropbox\Apps\ASRRecordings` (ASR Voice Recorder, Android eller iPhone). Mangler den, er det en advarsel, ikke et stop.

## Senere opdateringer

Efter commit og push: dobbeltklik `UDGIV OPDATERING.bat`. Den skriver til:

```text
\\a4diskstation4\A4software\task-intake\updates
```

Kollegaen trykker **Opdatér og genstart** i indbakken. Kør ikke `OPDATER.bat` fra NAS.

Udførlig vejledning: [docs/source/KOLLEGA-START.md](docs/source/KOLLEGA-START.md).
