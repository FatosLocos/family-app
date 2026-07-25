# Architectuurfundamentals

Dit document legt de **bindende** architectuurprincipes van Family App vast. Het is geen
wensenlijst en geen stijlgids: het beschrijft afspraken waaraan elke nieuwe module, elk nieuw
model en elke nieuwe feature getoetst wordt.

Elk principe verwijst naar het codepatroon dat het vandaag al afdwingt, met bestandspaden. Zo
is dit document toetsbaar: wijkt de code af van de tekst, dan is er een bug in één van beide en
moet dat opgelost worden — niet genegeerd.

Een PR of issue kan hiernaar verwijzen ("voldoet aan fundamentals 1, 2, 3") in plaats van per
keer opnieuw te beargumenteren waarom bijvoorbeeld RLS of MCP-pariteit nodig is. Onderaan staat
een [checklist voor elke nieuwe module](#checklist-voor-elke-nieuwe-module).

Alle paden zijn relatief aan de repo-root.

---

## 1. Security by design

Family App bevat de meest persoonlijke gegevens van een gezin: bankrekeningen en transacties,
gezondheids- en kindgegevens, thuisadres en apparaten, e-mail en agenda's. Beveiliging is
daarom geen laag die achteraf over een module heen gelegd wordt, maar een eigenschap van het
ontwerp. Concreet: **een module is pas af als een gecompromitteerde of foutieve queryset nog
steeds geen data van een ander huishouden kan teruggeven.**

Dat is niet retorisch — het is in de database afgedwongen.

### 1.1 Het huishouden is de isolatiegrens, en de database bewaakt hem

Elke tabel met een `household`-kolom draagt dezelfde, generieke Postgres-policy:

```sql
CREATE POLICY household_isolation ON "<tabel>"
  USING      (household_id::text = current_setting('app.household_id', true))
  WITH CHECK (household_id::text = current_setting('app.household_id', true));
```

De tenantvariabele `app.household_id` wordt gezet door
`django_app/common/db_scope.py` (`household_db_scope`, nestbaar: hij herstelt de vorige waarde
in plaats van hem te wissen) en voor gewone webrequests aangeroepen door
`django_app/households/middleware.py` (`ActiveHouseholdMiddleware`).

Applicatiecode filtert daarbovenop altijd expliciet via
`django_app/common/scoping.py` (`HouseholdQuerySet.for_household`) — twee lagen, niet één.
Views halen objecten op met
`get_object_or_404(Model.objects.for_household(request.household), pk=...)`, zodat een id uit
een ander huishouden een **404** geeft en niet een 403 (een 403 zou bevestigen dát het object
bestaat).

De rolscheiding die maakt dat de applicatierol RLS niet kan uitzetten, staat beschreven in
`django_app/SECURITY.md`.

### 1.2 De RLS-migratie is een apart bestand, geen bijzaak

De policy komt **nooit** mee in de `CreateModel`-migratie. Elk nieuw household-model krijgt een
eigen migratie `<n>_<modelnaam>_rls.py` die van de create-migratie afhangt. Kopieer
`django_app/household/migrations/0021_tasklist_rls.py` letterlijk en verander alleen `TABLES`
en `dependencies`. Voor meerdere tabellen tegelijk (met defensieve `DROP POLICY IF EXISTS`):
`django_app/integrations/migrations/0002_enable_household_rls.py`.

Harde eisen aan zo'n migratie:

- policynaam exact `household_isolation`;
- zowel `ENABLE ROW LEVEL SECURITY` **als** `FORCE ROW LEVEL SECURITY`;
- zowel `USING (...)` **als** `WITH CHECK (...)`;
- vendor-guard `if schema_editor.connection.vendor != "postgresql": return`;
- een reverse-functie die de policy dropt en RLS uitzet.

Bestaande migraties worden nooit aangepast; een correctie is altijd een nieuwe migratie.

### 1.3 De dekking wordt getest, niet vertrouwd

Twee mechanismen falen zodra iemand een household-model toevoegt zonder policy:

- `django_app/ops/verify_rls.sh` — draait als de beperkte applicatierol op de VPS en in CI.
  Het eerste `DO $$`-blok bevat een `VALUES`-lijst met élke verwachte tabel en gooit een
  exception zodra er één ontbreekt of RLS niet geforceerd is. Daarna bewijst een tweede blok de
  isolatie echt: het schrijft een taak in huishouden A, leest hem niet in huishouden B, en
  verwacht dat een write voor A vanuit B met `insufficient_privilege` faalt.
- `django_app/config/tests.py`, klasse `HouseholdRlsPolicyTests`:
  - `test_all_household_scoped_models_have_forced_postgres_rls` inspecteert `pg_class` en
    `pg_policies` voor elk model met een veld dat letterlijk `household` heet, en eist
    `(relrowsecurity, relforcerowsecurity, policy_exists) == (True, True, True)`.
  - `test_vps_rls_verification_covers_every_household_scoped_table` leest `verify_rls.sh` als
    tekst en eist dat `('<app>_<model>')` erin voorkomt — vandaar dat de vorm in de
    `VALUES`-lijst exact zo geschreven moet worden, zonder spaties binnen de haakjes.

De enige uitzondering is `BOOTSTRAP_SCOPE_TABLES` in diezelfde testklasse:
`households_membership` en `households_householdinvite` bepalen zélf welk huishouden actief
wordt, of lossen een eenmalige uitnodiging op vóórdat die scope bestaat. Daar wordt niets aan
toegevoegd zonder een expliciet gedocumenteerde reden.

### 1.4 De publieke deellink: één uitzondering, in de database geregeld

De publieke wenslijst is de enige anonieme toegang tot huishouddata, en laat zien hoe zo'n
uitzondering hoort te worden gebouwd: `django_app/family/migrations/0004_wishreservation_household_and_public_share_policy.py`
en `django_app/family/migrations/0005_limit_public_wishlist_writes.py`.

Het mechanisme: anoniem betekent dat `app.household_id` nooit gezet is, dus het normale
predicaat is NULL en niet true, dus is er niets zichtbaar. De uitzondering is een `OR`-clausule
die "tenant matcht" vervangt door "deze rij hangt onder een gedeeld object" — op de roottabel
`OR is_shared`, op een kindtabel `OR EXISTS (SELECT 1 FROM <parent> ...)`.

**`USING` versus `WITH CHECK` is hier de security-grens, en dat is precies wat migratie 0005
repareerde.** `USING` bepaalt wat gelezen mag worden, `WITH CHECK` wat geschreven mag worden.
Voor `family_wishlist` en `family_wishitem` staat de gedeeld-clausule daarom **alleen** in
`USING`; `WITH CHECK` blijft de kale huishoudencheck. Anoniem lezen mag, anoniem schrijven
niet. Alleen `family_wishreservation` — de énige tabel waar het publiek mag INSERTen — heeft de
`OR EXISTS(...)` óók in `WITH CHECK`, en dan met per voorouder een extra
`AND <parent>.household_id = family_wishreservation.household_id`, zodat een anonieme bezoeker
geen willekeurig `household_id` kan meesmokkelen.

Autorisatie zelf zit niet in de policy: de ongokbare `share_token`
(`secrets.token_urlsafe(24)`, `django_app/family/views.py` `toggle_wishlist_share`) wordt in
Python gecontroleerd, RLS doet alleen containment. De publieke views
(`public_wishlist`, `reserve_wish` in `django_app/family/views.py`) draaien zonder
`household_required` en gebruiken bewust `.filter(is_shared=True)` in plaats van
`.for_household()`, omdat er op een anonieme request geen huishouden is.

Wil je iets vergelijkbaars bouwen, kopieer dan deze twee migraties en die drie views — en
motiveer in de PR expliciet waarom de nieuwe `WITH CHECK` veilig is.

---

## 2. MCP-pariteit: elke module is ook via OpenClaw bruikbaar

Family App is geen webapp met een chatbot ernaast. De webUI en de OpenClaw-agent zijn twee
gelijkwaardige voorkanten op hetzelfde datamodel. **Een module die alleen via de browser werkt,
is niet af.** Nieuwe functionaliteit krijgt in principe altijd bijbehorende MCP-tools; laat je
ze weg, dan is dat een bewuste, in de PR gemotiveerde uitzondering — niet de default.

Dit is al de facto de praktijk: taken, taaklijsten, gezinsleden, boodschappen, huis, agenda,
geld, meldingen, Dropbox, e-mail (Outlook én IMAP) en Microsoft To Do zijn allemaal zowel UI
als MCP-tool.

De keten die je volgt, in deze volgorde:

1. **`mcp_bridge/server.py`** — een `@mcp.tool()` op een gewone sync-functie met `ctx: Context`
   als eerste parameter. Dit proces bevat geen Django; het is een pure HTTP-forwarder.
   Toolnamen zijn Nederlands (`taken`, `taak_bijwerken`), parameternamen en docstrings zijn
   Engels. `_checked(response)` vertaalt FamilyApps eigen Nederlandse `{"error": ...}` naar een
   `RuntimeError`, zodat de agent de echte reden ziet in plaats van een generieke HTTP-fout.
2. **`django_app/integrations/openclaw_views.py`** — een `api_*`-view achter een bearer-token.
   Alle writes zijn POST; er is nergens PATCH/PUT/DELETE. Querysets altijd via
   `for_household(request.household)`, objecten altijd via `get_object_or_404`.
   Route toevoegen in `django_app/integrations/urls.py`, onder het prefix
   `/instellingen/api/openclaw/...` (gemount in `django_app/config/urls.py`).
3. **`require_openclaw_token(scope)`** in `django_app/integrations/openclaw_api.py` — doet
   `csrf_exempt`, authenticeert het composite token `f"{household_id}.{raw}"` (zodat de
   RLS-scope bekend is vóór de eerste query), opent `household_db_scope` om de héle view, zet
   `request.household` / `request.openclaw_user` / `request.openclaw_token_scopes`, bumpt
   `last_used_at`, en weigert met 403 als de scope ontbreekt. **Views roepen zelf nooit
   `household_db_scope` aan** — de decorator deed dat al. Voor endpoints die meerdere providers
   bedienen bestaat `require_openclaw_token_any([...])`; die view moet dan zélf de precieze
   scope checken tegen `request.openclaw_token_scopes` (zie `_resolve_mail_account`).
4. **`OpenClawActionLog`** (`django_app/integrations/models.py`) — elke actie, gelukt of
   mislukt, wordt gelogd via `log_openclaw_action(...)`. Ook een geweigerde actie
   (`toegang_geweigerd`), zodat een dichtgezet token net zo zichtbaar is als een werkend token.
   Het gezin ziet dit terug in Instellingen. Een MCP-endpoint zonder auditregel is niet af.

Hergebruik van businesslogica is hierbij de norm, niet duplicatie: `api_today`
(`django_app/integrations/openclaw_views.py`) roept dezelfde `build_today_summary()` aan als de
HTML-view `today` (`django_app/config/views.py`, logica in `django_app/config/services.py`).
De agent en de gebruiker krijgen daardoor per definitie hetzelfde antwoord op "wat staat er
vandaag".

Vergeet tot slot de documentatie in `django_app/templates/integrations/index.html` niet: het
proza dat beschrijft wat OpenClaw mag, en de uitputtende opsomming van toolnamen in de
probe-stap van de handleiding.

---

## 3. Scopes: de gebruiker bepaalt per token wat OpenClaw mag

De agent krijgt nooit "toegang tot de app". Hij krijgt precies de rechten die een gezinslid bij
het aanmaken van zijn eigen token heeft aangevinkt.

- `ALL_SCOPES` en `SCOPE_LABELS` in `django_app/integrations/openclaw_api.py` zijn de enige
  bron van waarheid. Elke scope in `ALL_SCOPES` **moet** een label in `SCOPE_LABELS` hebben:
  `django_app/integrations/views.py` bouwt `openclaw_scope_choices` met een ongeguarde
  `SCOPE_LABELS[scope]`, dus een ontbrekend label is een KeyError op de Instellingen-pagina.
- De scope-picker staat in `django_app/templates/integrations/index.html`, in het formulier
  naar `integrations:create_openclaw_token`. Elk gezinslid maakt zijn eigen token met zijn
  eigen vinkjes; de gekozen scopes staan op `OpenClawToken.scopes`
  (`django_app/integrations/models.py`).
- Labels zijn Nederlands en beschrijven wat er feitelijk gebeurt, in de taal van de gebruiker
  ("E-mail versturen en beantwoorden namens jou"), niet in de taal van de code.
- Scopes zijn gesplitst op `:read` en `:write`, en per bron waar bronnen echt verschillen
  (`outlook_mail:*` naast `imap_mail:*`, `dropbox:read` naast `dropbox:content`).

**Nooit meeliften op een bestaande, bredere scope.** Een nieuwe capability voegt een eigen,
aanvinkbare scope toe. De verleiding om "dit valt wel onder `huis:write`" is precies wat het
systeem waardeloos maakt: wie `huis:write` aanvinkte om de lampen te bedienen, heeft daarmee
niet ingestemd met iets wat er later stil bij is gekomen. Bestaande tokens dragen bovendien de
oude scopelijst; nieuwe functionaliteit onder een oude scope wordt daardoor met terugwerkende
kracht toegekend aan tokens die er nooit voor gekozen hebben.

Hergebruik van een bestaande scope mag alleen als de nieuwe actie aantoonbaar binnen dezelfde
capability en hetzelfde risiconiveau valt (bijvoorbeeld een extra veld op een bestaande
mailwrite). Dat is een expliciete afweging in de PR, geen stilzwijgende default.

---

## 4. Verwijderen via MCP is een uitzonderingsgeval

**Er is op dit moment bewust geen enkele delete-actie aan OpenClaw blootgesteld.** De 35 tools
in `mcp_bridge/server.py` lezen, maken aan, werken bij, ronden af en vinken af — geen enkele
verwijdert huishouddata. In `django_app/integrations/openclaw_views.py` bestaat geen
DELETE-route en geen `.delete()` op een domeinobject. Dat is geen omissie maar een keuze:
een agent die een instructie verkeerd interpreteert moet hooguit iets verkeerds toevoegen of
een verkeerd veld overschrijven — beide zichtbaar in `OpenClawActionLog` en met de hand te
herstellen. Onherstelbaar dataverlies op basis van een chatbericht is een andere categorie.

Bouw dus geen delete-tools. Waar "weghalen" nodig is, kies een omkeerbare vorm: afronden,
afvinken, archiveren, intrekken.

Mocht delete-via-MCP ooit alsnog toegevoegd worden, dan geldt onverkort:

- een **eigen, zwaardere scope**, los aanvinkbaar en nooit standaard aangevinkt — nooit
  hetzelfde lichte `:write`-vinkje als voor lezen en bijwerken;
- een **expliciete extra bevestigingsstap** in de flow, waarbij de agent eerst precies moet
  benoemen wat verwijderd wordt en de gebruiker apart bevestigt;
- bij voorkeur **soft delete** (markeren en herstelbaar houden) in plaats van een harde
  `DELETE`;
- een auditregel in `OpenClawActionLog` die het verwijderde object identificeerbaar beschrijft.

Wie zo'n tool voorstelt, motiveert in de issue waarom afronden/archiveren niet volstaat.

---

## 5. Eén samenhangend overzicht, geen verzameling losse tools

Taken, agenda, boodschappen, financiën, huis, e-mail en To Do zijn geen aparte apps die
toevallig hetzelfde inlogscherm delen. Ze horen samen te komen in één overzicht voor het gezin.
Dat is tegelijk de reden dat OpenClaw hier nuttig kan zijn: één plek, één samenhangend
datamodel, in plaats van een agent die losse en onderling incompatibele bronnen moet
combineren.

Wat dat concreet betekent voor een nieuwe module:

- **Zichtbaar op Start.** `build_today_summary()` in `django_app/config/services.py` aggregeert
  taken, boodschappen, afspraken, meldingen, routines, maaltijden en verjaardagen tot één
  antwoord op "wat is er vandaag", en wordt gedeeld door de HTML-view
  (`django_app/config/views.py` `today` → `django_app/templates/today/index.html`) en de
  MCP-tool `vandaag`. Heeft je module iets dat vandaag speelt, dan hoort het daar.
- **Vindbaar.** `search()` in `django_app/config/views.py` doorzoekt alle modules tegelijk;
  een nieuw zoekbaar model komt in **beide** dicts (de lege en de gevulde) plus in
  `django_app/templates/search/index.html` en
  `django_app/templates/search/partials/results.html`.
- **Hergebruik in plaats van een silo.** Bestaande bouwstenen zijn er om gebruikt te worden:
  `TaskList`/`Task` (`django_app/household/models.py`) voor alles wat een afvinkbare
  actie is, `CalendarEvent`/`CalendarSource` (`django_app/planning/models.py`) voor alles met
  een tijdstip, het scope-systeem uit principe 3 voor rechten. Een Reizen- of
  Evenementen-module bouwt dus geen eigen takenlijst en geen eigen agenda-implementatie: hij
  koppelt aan de bestaande.
- **Dezelfde vorm.** Per app één abstracte `*Record`-basisklasse (zie hieronder), Nederlandse
  URL-segmenten met Engelse view- en URL-namen, tabs en filters als query params op één pagina
  in plaats van losse URL's, en de gedeelde componenten en CSS-klassen uit
  `django_app/templates/base.html` en `django_app/templates/components/`.
- **Bereikbaar.** Een nieuwe module krijgt standaard een link in het "Meer"-paneel van
  `django_app/templates/base.html` (zowel in de desktop-dock als in het mobiele
  overflowmenu); de onderste mobiele dock is gecapt op vier items plus één centrale knop.

### Let op: `HouseholdOwnedModel` is dode code — niet gebruiken

`django_app/households/base_models.py` definieert een `HouseholdOwnedModel`. **Geen enkel model
erft ervan** (te controleren met `grep -rn "HouseholdOwnedModel" --include=*.py .` — één hit,
de definitie zelf). Het mist bovendien `objects = HouseholdManager()`, dus subklassen zouden
géén `.for_household()` hebben en principe 1 stilzwijgend ondermijnen.

De conventie die écht gevolgd wordt, is **een abstracte `*Record`-basisklasse per app**:

- `HouseholdRecord` — `django_app/household/models.py`
- `FamilyRecord` — `django_app/family/models.py`
- `PlanningRecord` — `django_app/planning/models.py`
- `FinanceRecord` — `django_app/finance/models.py`

Alle vier hebben dezelfde vorm: `household`-FK, `created_at`, `updated_at`,
`objects = HouseholdManager()`, `class Meta: abstract = True`. Kopieer die van
`django_app/household/models.py` voor je nieuwe app. De apps `home`, `integrations` en
`notifications` herhalen de velden inline; dat is bestaand, geen nieuw voorbeeld om te volgen.

---

## Checklist voor elke nieuwe module

Af te vinken in de PR. Niet van toepassing mag, maar dan met één regel uitleg.

**Model en isolatie (principe 1)**

- [ ] Abstracte `<App>Record`-basisklasse met `household`, `created_at`, `updated_at` en
      `objects = HouseholdManager()` — niet `HouseholdOwnedModel`.
- [ ] Elke `UniqueConstraint` is household-gescoped (`fields=("household", ...)`), tenzij een
      parent-FK het huishouden al impliceert.
- [ ] Eigen RLS-migratie `<n>_<model>_rls.py`, gekopieerd van
      `django_app/household/migrations/0021_tasklist_rls.py`: policynaam `household_isolation`,
      ENABLE + FORCE, USING + WITH CHECK, vendor-guard, reverse-functie.
- [ ] `('<app>_<model>')` toegevoegd aan de `VALUES`-lijst in `django_app/ops/verify_rls.sh`.
- [ ] Geen bestaande migratie gewijzigd.
- [ ] Views scopen met `for_household()` + `get_object_or_404` (cross-household ⇒ 404).
- [ ] Rechten via `@household_required` / `@parent_required` / `@owner_required`
      (`django_app/households/decorators.py`), boven `@require_POST`.

**MCP-pariteit (principe 2)**

- [ ] `@mcp.tool()` in `mcp_bridge/server.py` — Nederlandse toolnaam, Engelse docstring en
      parameternamen.
- [ ] `api_*`-view in `django_app/integrations/openclaw_views.py` (POST voor writes) + route in
      `django_app/integrations/urls.py`.
- [ ] `log_openclaw_action(...)` op elk pad, ook op de foutpaden.
- [ ] Businesslogica gedeeld met de HTML-view in plaats van gedupliceerd.
- [ ] `django_app/templates/integrations/index.html` bijgewerkt: het OpenClaw-proza én de
      opsomming van toolnamen in de probe-stap.

**Scopes (principe 3)**

- [ ] Nieuwe scope in `ALL_SCOPES` **en** een Nederlands label in `SCOPE_LABELS`
      (`django_app/integrations/openclaw_api.py`).
- [ ] Gesplitst in `:read` en `:write` waar dat betekenis heeft.
- [ ] Niet meegelift op een bestaande bredere scope (of: expliciet gemotiveerd waarom het
      dezelfde capability en hetzelfde risiconiveau is).

**Delete (principe 4)**

- [ ] Geen delete-tool via MCP. Weghalen gebeurt omkeerbaar: afronden, afvinken, archiveren.

**Overzicht (principe 5)**

- [ ] Relevante data zichtbaar in `build_today_summary()` en op Start.
- [ ] Zoekbaar model toegevoegd aan `search()` en de twee zoektemplates.
- [ ] Bestaande bouwstenen hergebruikt (`Task`/`TaskList`, `CalendarEvent`, het scope-systeem)
      in plaats van een eigen variant.
- [ ] Nav-link in het "Meer"-paneel van `django_app/templates/base.html` (beide plekken).

**Tests en verificatie**

- [ ] Minstens één happy-path-test per nieuw endpoint.
- [ ] Per muterend endpoint een cross-household test die **404** verwacht, plus een
      `refresh_from_db()`-assertie dat er niets veranderd is.
- [ ] Testdata en foutmeldingen in het Nederlands; code en MCP-docstrings in het Engels.
- [ ] `./django_app/ops/run-checks.sh` groen (de volledige testsuite) en
      `django_app/ops/verify_rls.sh` groen tegen de beperkte applicatierol — dezelfde stappen
      die `.github/workflows/django-tests.yml` draait, naast `ruff check .` en
      `manage.py check`. Draai lokaal ook `manage.py makemigrations --check --dry-run`, zodat
      een modelwijziging zonder migratie niet blijft liggen.
- [ ] Geen nieuwe dependencies zonder harde noodzaak.
