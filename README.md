# Stemmeindtagelse

Tal en idé ind på telefonen. Sorter den ved computeren. Godkendte kort åbner en Outlook-mail til Wrike.

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

Overskrifter skrives af lokal Ollama (`qwen2.5:14b` som standard — ikke ChatGPT). Modellen skal køre: `ollama serve` og `ollama pull qwen2.5:14b`. Uden Ollama falder overskriften tilbage til rå Whisper-tekst. I indbakken kan du trykke **Genskab overskrift** på eksisterende kort.

- Computer: [http://127.0.0.1:8000](http://127.0.0.1:8000) — indbakken. **Åbn i Outlook** udfylder emne + brødtekst; du trykker Send. Hvis Outlook ikke åbner, brug **Hent .eml**.
- Telefon: mikrofon kræver **HTTPS**. Kør `.\scripts\start-tunnel.ps1` (Cloudflare Tunnel) og åbn den `https://…` URL + `/ny-ide`. Log ind, tilføj til startskærm. Ikonet **Ny ide** starter optageren.

Optagelser stoppes efter 60 sekunder.
