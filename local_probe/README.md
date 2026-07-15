# Family App Local Probe

De probe draait op een apparaat in je thuisnetwerk en opent zelf een versleutelde uitgaande WebSocket-verbinding naar de Family App. Er hoeft geen poort van het thuisnetwerk naar internet open te staan.

```bash
cd local_probe
# Gebruik Python 3.12 of 3.13. Bluetooth LE-scans gebruiken voorlopig een
# bibliotheek die nog niet compatibel is met Python 3.14.
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m family_app_probe.main pair \
  --server https://app.example.com \
  --code FAP-PLAATS-HIER-DE-CODE \
  --name "Woonkamer probe"
```

Daarna activeer je lokaal een Hue Bridge. Druk eerst op de fysieke Bridge-knop.

```bash
.venv/bin/python -m family_app_probe.main hue-link --bridge https://192.168.1.20
.venv/bin/python -m family_app_probe.main run
```

De probe leest lokaal Hue, Sonos, Google Cast en Philips Android TV uit, voert ondersteunde opdrachten daar uit en meldt de actuele status terug. Voor Sonos gebruikt de probe lokale UPnP-eventabonnementen: volume, dempen, afspelen en groepswijzigingen worden daarom meteen bijgewerkt in plaats van pas bij de volgende pollingronde. Google Cast-apparaten krijgen lokale status, afspelen/pauzeren, dempen en volume. Philips-tv's worden alleen via SSDP ontdekt en gebruiken de lokale JointSpace API voor status en de vertrouwde afstandsbedieningsknoppen. Sommige recente tv's vereisen hiervoor eerst een lokale JointSpace-pairing; de app meldt dat expliciet en probeert nooit wachtwoorden of codes op het netwerk te raden. De probe opent hiervoor alleen een tijdelijke lokale callbackpoort; er hoeft geen poort vanaf internet naar je thuisnetwerk open te staan. Sta op macOS of Windows inkomende verbindingen voor de probe/Python toe wanneer de firewall daarom vraagt.

## Nest Protect (experimenteel, alleen lezen)

De officiële Google Device Access API ondersteunt geen Nest Protect. De probe kan daarom optioneel de ongedocumenteerde Google/Nest-websessie gebruiken om rook-, koolmonoxide-, hitte-, batterij- en voedingsstatus te lezen. Dit is geen vervanging voor het fysieke alarm of de officiële Nest-meldingen en biedt geen bediening of automatisering.

Haal de volledige Google `iframerpc` Request URL (het `issue token`) en de bijbehorende cookies op volgens de Nest Protect-handleiding van de Family App of het open-source referentieproject `imicknl/ha-nest-protect`. Behandel beide als een wachtwoord. Voer ze alleen op de lokale probe in:

```bash
.venv/bin/python -m family_app_probe.main nest-protect-link --issue-token "PLAK-HIER-HET-ISSUE-TOKEN"
```

De probe vraagt vervolgens verborgen om de cookies, controleert de toegang direct en bewaart ze alleen in het lokale configuratiebestand met rechten `0600`. Na uitloggen bij Google of een wachtwoordwijziging is opnieuw koppelen nodig.

Daarnaast worden veilige netwerkvondsten via SSDP/UPnP, mDNS/Bonjour, WS-Discovery en Bluetooth LE als alleen-lezen suggesties opgeslagen. Daarbij worden HomeKit, Matter, AirPlay/RAOP, Spotify Connect, Google Cast, Android TV en ONVIF-camera's herkend waar ze zich adverteren. Bluetooth LE leest alleen advertenties uit: de probe pairt niet en maakt geen generieke Bluetooth-verbinding. Wanneer Bluetooth is uitgeschakeld of de host geen rechten heeft, slaat de probe deze optionele scan over. Nieuwe vondsten worden nooit automatisch bestuurbare apparaten. Apple HomeKit, Matter en AirPlay vereisen eigen pairing/commissioning en worden daarom niet met onveilige generieke credentials aangestuurd.

## Raspberry Pi of Linux

Kopieer deze map bijvoorbeeld naar `/opt/family-app/local_probe`, maak de virtualenv aan en installeer de service:

```bash
sudo useradd --system --create-home familyprobe
sudo cp family-app-probe.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now family-app-probe
sudo journalctl -u family-app-probe -f
```

Pas in `family-app-probe.service` eerst het pad aan als de map elders staat. Draai `pair` eenmalig als dezelfde gebruiker die de service uitvoert, zodat de configuratie in diens thuismap wordt opgeslagen.

## macOS-laptop

Kopieer de map bijvoorbeeld naar `/opt/family-app/local_probe` en pas de twee paden in `nl.familyapp.probe.plist` aan. Installeer de LaunchAgent daarna voor de ingelogde gebruiker:

```bash
mkdir -p ~/Library/LaunchAgents
cp nl.familyapp.probe.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/nl.familyapp.probe.plist
launchctl kickstart -k gui/$(id -u)/nl.familyapp.probe
```

Controleer lokaal eerst zonder doorlopende dienst met (dit verstuurt alleen de
inventaris; een volledige discovery gebeurt daarna automatisch in de service):

```bash
.venv/bin/python -m family_app_probe.main run --once
```

De configuratie, probe-token, lokale Hue-app-key en eventuele Nest Protect-sessiegegevens staan uitsluitend in `~/.config/family-app-probe/config.json` met bestandsrechten `0600`. Trek de probe in via **Instellingen > Koppelingen** om het token onmiddellijk ongeldig te maken.
