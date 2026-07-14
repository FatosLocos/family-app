# Family App

Nederlandse gezinsapp voor taken, boodschappen, geld, agenda en Home Assistant.

## Start

De app kan draaien met lokale PostgreSQL via `DATABASE_URL`. Dit is ook het primaire pad voor de TransIP VPS, zodat gezinsdata lokaal op de VPS blijft staan.

1. Start een PostgreSQL database.
2. Kopieer `.env.example` naar `.env.local` en vul `DATABASE_URL`.
3. Start lokaal:

```bash
npm run dev
```

Bij de eerste request maakt de app de lokale tabellen aan en seedt hij één huishouden: `Ons gezin`.
Open daarna `/login` en maak het eerste lokale account aan. Dat account wordt eigenaar van het huishouden; publieke registratie sluit daarna.
Gezinsleden voeg je toe via Instellingen -> Nieuwe invite-code. De invite-link `/invite/CODE` laat een gezinslid een lokaal account aanmaken en koppelt dat account aan hetzelfde huishouden.
De eigenaar kan in Instellingen open invite-codes intrekken, gezinsleden verwijderen en leden promoveren naar beheerder of terugzetten naar lid.
Iedereen kan in Instellingen het eigen profiel bijwerken, inclusief naam, e-mail, telefoon, kleur, dagoverzicht en lokaal wachtwoord.
Het dashboard toont slimme signalen voor achterstallige taken, taken vandaag, open boodschappen, terugkerende producten, betaalmomenten, agenda en nog ontbrekende koppelingen.

PostgreSQL via `DATABASE_URL` is de enige database- en authenticatielaag. Het schema wordt bij het starten van de app gecontroleerd en waar nodig aangevuld.

Home Assistant tokens, bunq API keys en OAuth secrets worden server-side opgeslagen en niet in browser-local storage bewaard.

## Bankkoppeling

De financiële module heeft een provider-neutrale basis voor bankconnecties, rekeningen en transacties. `bunq` is de eerste provider:

- OAuth is de voorkeursroute: registreer in bunq Developer de redirect URI `https://jouw-domein/api/bunq/oauth/callback`.
- Lokaal op poort 3001 is dat `http://localhost:3001/api/bunq/oauth/callback`.
- OAuth client ID/secret en access tokens worden server-side opgeslagen.
- API key opslag blijft beschikbaar als developer fallback.
- Bankrekeningen en transacties hebben eigen tabellen.
- Betalingen starten is bewust niet geïmplementeerd.
- `/api/bunq/oauth/start` start de bunq autorisatie.
- `/api/bunq/oauth/callback` wisselt de code om voor een access token en bewaart die server-side.
- `/api/bunq/sync` is voorbereid, maar vereist nog bunq session setup en request signing voordat live sync werkt.

## Takenkoppelingen

De takenmodule heeft een integratiebasis voor externe takenbronnen:

- Microsoft To Do gebruikt Microsoft Graph en vereist OAuth met delegated task permissions.
- Apple Herinneringen heeft geen eenvoudige server-side web-API; officiële toegang loopt via EventKit in een native macOS/iOS helper.
- `/api/tasks/sync` is voorbereid en geeft per provider de ontbrekende live-sync stap terug.

Referenties:

- Microsoft Graph To Do API: https://learn.microsoft.com/en-us/graph/todo-concept-overview
- Apple EventKit Reminders: https://developer.apple.com/documentation/eventkit

## Slimme Boodschappen

De boodschappenmodule heeft nu een basis voor:

- terugkerende producten
- koopfrequentie per product
- prijshistorie per product/winkel/bron
- OCR-scanrecords voor bonnen of productfoto's

`/api/shopping/ocr` accepteert JPG, PNG, WebP en PDF uploads en maakt een scanrecord aan. De OCR-provider zelf moet nog worden gekoppeld; daarna kunnen herkende producten als `price_observations` en reviewbare boodschappen worden opgeslagen.

## Smart Home

De eerste directe smart-home integratie is Philips Hue:

- Hue Bridge URL en app key worden server-side opgeslagen.
- Voor lokale live-tests kun je `HUE_BRIDGE_URL` en `HUE_APP_KEY` in `.env.local` zetten.
- In development kan `/api/hue/pair` een app key aanvragen nadat je de fysieke Hue Bridge-knop indrukt.
- `/api/hue/lights` haalt Hue CLIP v2 lampen op.
- `/api/hue/lights/[rid]` kan lampen aan/uit zetten of dimmen.
- Home Assistant blijft beschikbaar als bredere integratie.
- Google Home is breder, maar zwaarder qua platform/OAuth en daarom later logischer dan Hue direct.

Google Home / Nest:

- `smart_home_integrations` bewaart Google Home/Nest metadata en OAuth secretvelden server-side.
- `Google Home APIs` is bedoeld voor structuren, apparaten en automations via ondersteunde Android/iOS Home APIs flow.
- `Nest SDM` synchroniseert ondersteunde Nest-apparaten via server-side OAuth en de Smart Device Management REST API.
- Configureer in Google Cloud OAuth de redirect URI `https://jouw-domein/api/google-home/oauth/callback`.
- Lokaal op poort 3001 is dat `http://localhost:3001/api/google-home/oauth/callback`.
- `/api/google-home/oauth/start?mode=nest_sdm` start de Nest-autorisatie.
- `/api/google-home/oauth/callback` wisselt de code om voor tokens en bewaart die server-side.
- `/api/google-home/sync` haalt Nest-apparaten op en slaat ze op in `smart_home_devices`.

Referenties:

- Google Home APIs: https://developers.home.google.com/apis
- Google OAuth 2.0: https://developers.google.com/identity/protocols/oauth2
- Nest SDM API: https://developers.google.com/nest/device-access/api

## Agenda-integratie

Outlook.com agenda's worden per gezinslid gekoppeld via Microsoft OAuth en Microsoft Graph:

- Een beheerder kan de Application (client) ID en client secret value eenmalig opslaan via Instellingen. De omgevingsvariabelen `OUTLOOK_CALENDAR_CLIENT_ID` en `OUTLOOK_CALENDAR_CLIENT_SECRET` blijven een optionele serverfallback. Daarna kiest ieder gezinslid alleen **Aanmelden met Outlook** en geeft toestemming.
- `calendar_integrations` bewaart per gezinslid de refresh tokens server-side.
- `calendar_events` bevat lokale gezinsafspraken en gesynchroniseerde Outlook-afspraken in één geïntegreerde lijst.
- De sync haalt eerst `/me/calendars` op en leest daarna per Outlook-agenda `calendarView`.
- De redirect URI moet exact overeenkomen met het adres waarop de app draait, lokaal bijvoorbeeld `http://localhost:3000/api/outlook-calendar/oauth/callback`.
- Op je VPS is dat `https://app.example.com/api/outlook-calendar/oauth/callback`.
- Gebruik voor persoonlijke Outlook.com accounts meestal tenant `consumers`.
- Scopes: `offline_access`, `User.Read`, `Calendars.Read`.
- `/api/outlook-calendar/oauth/start` start de Microsoft autorisatie.
- `/api/outlook-calendar/sync` haalt via Microsoft Graph `calendarView` afspraken op voor de komende periode.

Referenties:

- Microsoft Graph calendarView: https://learn.microsoft.com/en-us/graph/api/user-list-calendarview?view=graph-rest-1.0
- Microsoft OAuth authorization code flow: https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow
- Microsoft OAuth scopes: https://learn.microsoft.com/en-us/entra/identity-platform/scopes-oidc

## Controle

```bash
npm run lint
npm run typecheck
npm run test
npm run build
```
