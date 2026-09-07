# Brugervejledning

Tal en idé ind på telefonen. Sorter den ved computeren. Godkendte kort åbner en Outlook-kladde til Wrike med **høj prioritet**.

## Sådan kommer en idé ind

1. Optag med **ASR Voice Recorder** på Android eller iPhone.
2. Slå upload til **Dropbox** til. Filen lander i `Dropbox\Apps\ASRRecordings` på din PC - samme mappe, du bekræftede under installationen.
3. Computeren skal køre Indtagelse (den starter ved login). Du behøver ikke have telefonen på nettet, mens PC'en behandler filen.
4. Hold mappen **lokal** i Dropbox. En fil, der kun ligger online, er en tom pladsholder og bliver sprunget over.

Programmet venter, til filen er færdig med at synke, og flytter den derefter ud af Dropbox, så skyen ikke fyldes.

## Indbakken

Åbn [http://127.0.0.1:8000](http://127.0.0.1:8000) hvis browseren ikke kommer af sig selv. Log ind med den adgangskode, setup viste.

Til venstre ligger usorterede optagelser. Til højre ser du teksten og ét forslag:

| Handling | Betydning |
|---|---|
| **Åbn i Outlook** | Opretter en kladde til `wrike@wrike.com` med din mail på kopi og **høj prioritet**. Du trykker selv Send. |
| **Genskab overskrift** | Bed Ollama skrive titlen om. |
| **Smid væk** | Fjern forslaget eller hele optagelsen. Lyden slettes ikke, før du selv siger til. |
| **Prøv igen** | Hvis behandlingen fejlede. |

Hvis Outlook-vinduet ikke kommer, brug **Hent .eml**. Den fil har også høj prioritet, når du åbner den i Outlook.

## Telefon og computer

Du kan tale, mens computeren er slukket. Når PC'en tændes, henter Dropbox filen, og Indtagelse behandler den. Første overskrift efter opstart kan tage længere, især uden GPU.

Der er ingen grænse for, hvor længe du må tale. En lang indtaling giver ét kort. Noten bliver et referat.

## Opdatér programmet

Når en godkendt version ligger på NAS, vises en blå bjælke øverst i indbakken.

1. Vent, til en igangværende optagelse er færdig.
2. Klik **Opdatér og genstart**.
3. Vent. Browseren finder programmet igen.

Du skal ikke hente fra GitHub eller køre `SETUP.bat`, medmindre programmet beder om det. Hvis NAS ikke kan nås, vises ingen opdatering, og den installerede version kan bruges videre.

## Ved fejl

Dobbeltklik `SYSTEMTJEK.bat`. Send kun `fejlrapport.zip` til IT. Den indeholder ikke adgangskode, `.env`, runtime eller lyd.

| Problem | Løsning |
|---|---|
| Ingen nye idéer | Kontrollér at Dropbox-mappen er den, du valgte under setup, og at filen er færdig med at synke. |
| Outlook åbner ikke | Brug Hent .eml, eller åbn Outlook og prøv igen. |
| Whisper eller Ollama advarer | Vent, eller kør SYSTEMTJEK.bat. CPU virker, men er langsommere. |
| Programmet starter ikke | Kør SYSTEMTJEK.bat. Bed IT om SETUP.bat, hvis startfilen siger det. |
