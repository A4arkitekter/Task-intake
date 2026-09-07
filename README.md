# Stemmeindtagelse

Tal en idé ind på telefonen. Sorter den ved computeren. Godkendte kort åbner en Outlook-mail til Wrike.

Kollegainstallation (IT): se [INSTALLATIONSVEJLEDNING.pdf](INSTALLATIONSVEJLEDNING.pdf) eller [01-START-HER.md](01-START-HER.md). Daglig brug: [BRUGERVEJLEDNING.pdf](BRUGERVEJLEDNING.pdf). Pak GitHub-ZIP ud i `C:\apps\task-intake`, kopiér `runtime` fra NAS, kør `SETUP.bat` og `SYSTEMTJEK.bat`. Opdateringer kommer bagefter via knappen i indbakken — kollegaen har ikke GitHub-adgang.

## Sådan kører du det

1. Kopiér `.env.example` til `.env` og sæt `APP_PASSWORD` og `SECRET_KEY`.
2. Mail (standard er sat):

   - `MAIL_TO=wrike@wrike.com`
   - `MAIL_CC=ep@a4.dk`
   - `MAIL_MARKER=*PODIOWRIKETASKDELETE*`

   Send fra den adresse, der er knyttet til din Wrike-konto.

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

- Computer: [http://127.0.0.1:8000](http://127.0.0.1:8000) — indbakken. **Åbn i Outlook** udfylder emne + brødtekst; du trykker Send. Hvis Outlook ikke åbner, brug **Hent .eml**.

## Telefonen: optag og lad mappen synke

Telefonen optager med sin **egen** optager-app. Der skal ikke installeres nogen model på telefonen, og PC'en behøver ikke være tændt, når du taler.

1. Installer optageren og slå upload til **Dropbox** til. Dropbox beder kun om adgang til sin egen mappe under `Apps\`, hvor OneDrive-integrationen vil have adgang til alle dine filer.
   - **Android:** ASR Voice Recorder. Filen lander i `Dropbox\Apps\ASRRecordings`.
   - **iPhone:** RecUp (App Store). Filen lander i `Dropbox\Apps\RecUp Memos` eller `Dropbox\Apps\RecUp`. ASR Voice Recorder findes ikke til iPhone.
2. Optag et klip, og se at det lander i den mappe på PC'en.
3. Hold mappen lokal på PC'en. Gør Dropbox den "kun online", ligger filen som en 0-byte pladsholder, som overvågningen med vilje springer over.
4. Sæt `INBOX_DIR` i `.env` til den mappe.

Programmet scanner mappen hvert femte sekund. En fil hentes først ind, når størrelsen har ligget stille to runder i træk, så en halvoverført fil aldrig bliver transskriberet.

Behandlede filer flyttes til `INBOX_ARCHIVE_DIR`, som med vilje ligger **uden for** den synkroniserede mappe (`data\behandlet` som standard). Ellers ville hver optagelse blive liggende i skyen for evigt og spise kvote. Lyden gemmes desuden altid i `data\audio`, så kortet kan afspilles bagefter.

Der er ingen grænse for hvor længe du må tale. Sæt `MAX_DURATION_SEC` til et tal, hvis du alligevel vil have en. En lang indtaling giver stadig **ét** kort, men noten bliver et referat i stedet for to sætninger, og sprogmodellens kontekstvindue vokser med teksten, så slutningen ikke falder ud.

Vinduet stopper ved 8192 tokens, fordi Ollamas hukommelsesforbrug vokser med det — og på et 12 GB kort deles pladsen med Whisper. Det svarer til omkring 25 minutters tale. Bliver en optagelse længere end det, forkortes teksten **synligt** på midten, og begyndelsen og slutningen beholdes; det står i loggen, så du ikke bliver snydt i det stille.

## Du skal ikke kunne miste en idé

En notifikation er et øjeblik. Har du indtalt en idé fredag og holder ferie i tre uger, er notifikationen værdiløs. Derfor er der tre signaler, og kun det sidste er til at overse:

**1. Notifikationen.** Når kortet er klar, kommer en Windows-notifikation med selve overskriften. Den er sat op som en *påmindelse*, så den bliver stående på skærmen, indtil du gør noget ved den — ikke de fem sekunder en almindelig notifikation lever.

Programmet lægger ved første kørsel en genvej i Start-menuen. Det er ikke pynt: Windows viser kun notifikationer fra et program, det kender ved navn, og genvejen er det, der bærer navnet. Genvejen peger på indbakken, så et klik ikke starter en ekstra kopi af serveren. Vil du hellere hedde noget andet, sæt `APP_NAME` og `TOAST_AUMID`.

**2. Den daglige oversigt.** Hver morgen omkring `REMIND_AT` sendes en mail med alt, der ligger usorteret, og hvor gammelt det er. Den gentages **hver dag**, indtil indbakken er tom, så en glemt idé bliver mere og mere påtrængende i stedet for at forsvinde. Fejlede optagelser er med på listen — det er præcis dem, man ellers taber.

Mailen sendes gennem din kørende Outlook, så der ikke skal gemmes en adgangskode nogen steder. Var maskinen slukket klokken 08:30, sendes den, når du tænder — dagen springes ikke over. Slå den fra med `REMIND_ENABLED=0`.

**3. Indbakken åbner af sig selv.** Ved login åbnes indbakken, hvis der venter noget. Sidder du allerede med indbakken fremme, holder den sig i ro i stedet for at stjæle fokus. En *skjult* fane tæller ikke som at du kigger — det gjorde den før, og derfor åbnede vinduet sig aldrig. Slå det fra med `AUTO_OPEN=0`.

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
