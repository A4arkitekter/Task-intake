# Brugervejledning

Tal en idé ind på telefonen. Programmet opretter opgaven direkte i Wrike med den prioritet, du har valgt i administrationen (standard er **høj prioritet**).

## Sådan kommer en idé ind

1. Optag på telefonen og slå upload til **OneDrive** til. OneDrive er et GDPR-krav — Dropbox og andre skyer må ikke bruges.
   - **Android:** **ASR Voice Recorder** (Play Butik). Filen lander typisk i `OneDrive\Apps\ASR Cloud Uploads\asr`.
   - **iPhone:** **RecUp** (App Store). Filen skal lande i OneDrive, ikke Dropbox.
2. Det skal være **samme mappe**, du ser under Optagelser på [http://127.0.0.1:7000](http://127.0.0.1:7000). Stien kan rettes der — du skal ikke åbne en `.env`-fil.
3. Computeren skal køre Indtagelse (den starter ved login). Du behøver ikke have telefonen på nettet, mens PC'en behandler filen.
4. Hold mappen **lokal**. En fil, der kun ligger online, er en tom pladsholder og bliver sprunget over.

Programmet venter, til filen er færdig med at synke, og flytter den derefter ud af sky-mappen. Originalen ligger i `data\behandlet`. En kopi til afspilning ligger i `data\audio`.

## Administrationen

Åbn [http://127.0.0.1:7000](http://127.0.0.1:7000) hvis browseren ikke kommer af sig selv. Der er intet login. Hvis IT har valgt en anden port fra 7000 og op, bruges den adresse i stedet.

Første gang opretter du din egen Wrike-app og udfylder **Client ID**, **Secret key** og **Permanent access token** efter trinnene i administrationen. **Wrike konto** viser, hvem nøglerne tilhører — den kan ikke skiftes. Står der en kollegas navn, skal du indsætte dine egne nøgler. Derefter vælger du **Wrike-mappe** og **prioritet** (High som standard). **Opret testopgave** viser, at API'et og mappen virker.

| Handling | Betydning |
|---|---|
| **Gem sti** | Skift mappen, optagelser hentes fra. |
| **Søg Wrike-mappe** | Vælg hvor opgaverne lander. |
| **Prioritet** | High er standard. Ændringen gælder næste opgave. |
| **Opret testopgave** | Sender en test ind i den valgte mappe. |
| **Prøv igen** | Hvis Whisper eller Wrike fejlede. Transskriptionen genbruges, hvis den allerede findes. |
| **Hent fejlrapport.zip** | Til IT/Cursor. Indeholder ikke token eller lyd. |

## Telefon og computer

Du kan tale, mens computeren er slukket. Når PC'en tændes, henter OneDrive filen, og Indtagelse behandler den. Første overskrift efter opstart kan tage længere, især uden GPU.

Ligger optagelsen i telefonens app, men ikke i mappen på computeren, har telefonen ofte sat appen i dvale. Administrationen har en **Fejlfinding**-boks med trin til Android og iPhone.

Der er ingen grænse for, hvor længe du må tale. En lang indtaling giver én Wrike-opgave. Noten bliver et referat.

## Opdatér programmet

Når en godkendt version ligger på NAS, vises en blå bjælke øverst.

1. Vent, til en igangværende optagelse er færdig.
2. Klik **Opdatér og genstart**.
3. Vent. Browseren finder programmet igen.

Du skal ikke hente fra GitHub eller køre `SETUP.bat`, medmindre programmet beder om det. Hvis NAS ikke kan nås, vises ingen opdatering, og den installerede version kan bruges videre.

## Ved fejl

Dobbeltklik `SYSTEMTJEK.bat`, eller hent `fejlrapport.zip` fra administrationen. Send kun den zip til IT. Den indeholder ikke adgangskode, `.env`, runtime eller lyd.

| Problem | Løsning |
|---|---|
| Ingen nye idéer | Kontrollér stien til optagelser i browseren, og at filen er færdig med at synke. |
| Wrike-lampen er rød | Udfyld Client ID, Client secret og Get token i administrationen, logget ind i Wrike som dig selv. |
| Mapperne i Wrike mangler | Nøglerne tilhører en anden. Siden skriver navnet. Opret din egen app (+ App) og indsæt Client ID, Secret key og Permanent access token. |
| Whisper eller Ollama advarer | Vent, eller kør SYSTEMTJEK.bat. CPU virker, men er langsommere. |
| Programmet starter ikke | Kør SYSTEMTJEK.bat. Bed IT om SETUP.bat, hvis startfilen siger det. |
