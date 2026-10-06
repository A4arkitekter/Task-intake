# Stemmeindtagelse

Tal en idé ind på telefonen. Programmet opretter opgaven direkte i Wrike. Mappe og prioritet vælges i browseren.

Kollegainstallation (IT): se [INSTALLATIONSVEJLEDNING.pdf](INSTALLATIONSVEJLEDNING.pdf) eller [01-START-HER.md](01-START-HER.md). Daglig brug: [BRUGERVEJLEDNING.pdf](BRUGERVEJLEDNING.pdf). Pak GitHub-ZIP ud i `C:\apps\task-intake`, kopiér `runtime` fra NAS, kør `SETUP.bat` og `SYSTEMTJEK.bat`. Opdateringer kommer bagefter via knappen i administrationen — kollegaen har ikke GitHub-adgang.

## Sådan kører du det

1. Kopiér `.env.example` til `.env` og sæt `SECRET_KEY` plus `WRIKE_TOKEN` én gang.
2. Mappe og prioritet sættes **ikke** i `.env`. Åbn [http://127.0.0.1:7000](http://127.0.0.1:7000) og vælg Wrike-mappe + High/Normal/Low.

3. Start:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python -m app
```

Første start downloader Whisper `small` (~500 MB) til `data/models`.

### Bedre genkendelse med NVIDIA-kort

`small` på CPU hører stednavne og egennavne forkert. Har du et NVIDIA-kort, giver `large-v3` mærkbart bedre tekst og er samtidig hurtigere:

```powershell
pip install -r requirements-gpu.txt
```

Sæt så i `.env`:

```
WHISPER_MODEL=large-v3
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=int8_float16
```

`int8_float16` giver samme tekst som `float16`, men bruger det halve VRAM — det er værd at vide, hvis Ollama deler kortet med Whisper. Har du allerede hentet modellen til et andet projekt, så peg `MODEL_DIR` på den fælles cache (typisk `%USERPROFILE%\.cache\huggingface\hub`) i stedet for at hente 2,9 GB igen.

CTranslate2 slår `cublas64_12.dll` og cuDNN op ad navn, så `app/transcribe.py` lægger pakkernes DLL-mapper i `PATH` ved opstart. Kan GPU'en ikke bruges, falder programmet tilbage til CPU og skriver hvorfor i loggen — `/api/health` viser hvilken enhed der faktisk kører.

### Programmet skal ikke sidde på GPU'en hele dagen

Det her kører altid, og du bruger sandsynligvis selv GPU'en til andet — for eksempel til at transkribere store filer manuelt. Derfor **låner** programmet kun kortet:

- Whisper frigives efter `WHISPER_IDLE_UNLOAD_SEC` sekunders tomgang (5 minutter som standard). Det koster omkring 7 sekunder at hente modellen frem igen, og her er ventetid billigere end at stå i vejen.
- Sprogmodellen slipper kortet efter `LLM_KEEP_ALIVE` (5 minutter) i stedet for at holde næsten 9 GB i en time.
- Er GPU'en optaget, når en idé lander, prøver programmet igen og ender på CPU frem for at tabe idéen. Fejler det alligevel, bliver optagelsen liggende i indbakken med en **Prøv igen**-knap — lyden slettes aldrig, før du selv siger til.

I tomgang holder programmet kun et par hundrede megabyte CUDA-kontekst, ikke modellerne.

Overskrifter skrives af lokal Ollama (`qwen2.5:14b` som standard — ikke ChatGPT). Modellen skal køre: `ollama serve` og `ollama pull qwen2.5:14b`. Uden Ollama falder overskriften tilbage til rå Whisper-tekst. I indbakken kan du trykke **Genskab overskrift** på eksisterende kort.

- Computer: [http://127.0.0.1:7000](http://127.0.0.1:7000) — administrationen. Her vælger du Wrike-mappe og prioritet, ser lamper og henter fejlrapport. Er port 7000 optaget, kan `APP_PORT` i `.env` sættes til en anden port fra 7000 og op.

## Telefonen: optag og lad mappen synke

Telefonen optager med sin **egen** optager-app. Der skal ikke installeres nogen model på telefonen, og PC'en behøver ikke være tændt, når du taler.

1. Installer optageren og slå upload til **OneDrive** til.
   - **Android:** ASR Voice Recorder. Filen lander typisk i `OneDrive\Apps\ASR Cloud Uploads\asr`.
   - **iPhone:** RecUp (App Store). Filen kan lande i OneDrive eller `Dropbox\Apps\RecUp Memos` / `Dropbox\Apps\RecUp`. ASR Voice Recorder findes ikke til iPhone.
2. Optag et klip, og se at det lander i den mappe på PC'en.
3. Hold mappen lokal på PC'en. Gør OneDrive den "kun online", ligger filen som en 0-byte pladsholder, som overvågningen med vilje springer over.
4. Ret stien i browseren, hvis den ikke passer. `.env` er kun første gæt.

Programmet scanner mappen hvert femte sekund. En fil hentes først ind, når størrelsen har ligget stille to runder i træk, så en halvoverført fil aldrig bliver transskriberet.

Behandlede filer flyttes til `INBOX_ARCHIVE_DIR`, som med vilje ligger **uden for** den synkroniserede mappe (`data\behandlet` som standard). Ellers ville hver optagelse blive liggende i skyen for evigt og spise kvote. Lyden gemmes desuden altid i `data\audio`, så kortet kan afspilles bagefter.

Der er ingen grænse for hvor længe du må tale. Sæt `MAX_DURATION_SEC` til et tal, hvis du alligevel vil have en. En lang indtaling giver stadig **ét** kort, men noten bliver et referat i stedet for to sætninger, og sprogmodellens kontekstvindue vokser med teksten, så slutningen ikke falder ud.

Vinduet stopper ved 8192 tokens, fordi Ollamas hukommelsesforbrug vokser med det — og på et 12 GB kort deles pladsen med Whisper. Det svarer til omkring 25 minutters tale. Bliver en optagelse længere end det, forkortes teksten **synligt** på midten, og begyndelsen og slutningen beholdes; det står i loggen, så du ikke bliver snydt i det stille.

## Du skal ikke kunne miste en idé

En notifikation er et øjeblik. Har du indtalt en idé fredag og holder ferie i tre uger, er notifikationen værdiløs. Derfor er der tre signaler, og kun det sidste er til at overse:

**1. Notifikationen.** Når kortet er klar, kommer en Windows-notifikation med selve overskriften. Den er sat op som en *påmindelse*, så den bliver stående på skærmen, indtil du gør noget ved den — ikke de fem sekunder en almindelig notifikation lever.

Programmet lægger ved første kørsel en genvej i Start-menuen. Det er ikke pynt: Windows viser kun notifikationer fra et program, det kender ved navn, og genvejen er det, der bærer navnet. Genvejen peger på indbakken, så et klik ikke starter en ekstra kopi af serveren. Vil du hellere hedde noget andet, sæt `APP_NAME` og `TOAST_AUMID`.

**2. Den daglige oversigt.** Hver morgen omkring `REMIND_AT` sendes en mail med job, der ikke kom i Wrike. Den gentages **hver dag**, indtil listen er tom. Fejlede Whisper-kørsler er med på listen.

Mailen sendes gennem din kørende Outlook, så der ikke skal gemmes en adgangskode nogen steder. Var maskinen slukket klokken 08:30, sendes den, når du tænder — dagen springes ikke over. Slå den fra med `REMIND_ENABLED=0`.

**3. Administrationen åbner kun af sig selv ved fejl**, og kun hvis `AUTO_OPEN=1`. Standard er slået fra, så udvikleren ikke får et vindue i vejen.

Alle tre skriver en linje i loggen, når de faktisk har sendt noget. Det lyder overflødigt, men "der kom ingen fejl" er ikke det samme som "beskeden kom frem", og forskellen kostede en dags fejlsøgning.

Vil du se oversigten uden at vente til i morgen:

```powershell
.\.venv\Scripts\python.exe scripts\send_reminder.py --draft   # kladde i Outlook
.\.venv\Scripts\python.exe scripts\send_reminder.py           # send den
.\.venv\Scripts\python.exe scripts\probe_toast.py             # prøv notifikationen
```

## Start automatisk med Windows

```powershell
.\scripts\install-autostart.ps1
```

Den registrerer en planlagt opgave, der starter programmet ved login uden vindue. Stop det igen med `.\scripts\stop.ps1`.

Under udvikling: sæt `DEV_RELOAD=1` for at få uvicorn til at genindlæse ved kodeændringer.
