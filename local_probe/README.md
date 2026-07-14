# Family App Local Probe

De probe draait op een apparaat in je thuisnetwerk en opent zelf een versleutelde uitgaande WebSocket-verbinding naar de Family App. Er hoeft geen poort van het thuisnetwerk naar internet open te staan.

```bash
cd local_probe
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m family_app_probe.main pair \
  --server https://app.ligtvoet.tech \
  --code FAP-PLAATS-HIER-DE-CODE \
  --name "Woonkamer probe"
```

Daarna activeer je lokaal een Hue Bridge. Druk eerst op de fysieke Bridge-knop.

```bash
.venv/bin/python -m family_app_probe.main hue-link --bridge https://192.168.1.20
.venv/bin/python -m family_app_probe.main run
```

De probe leest lokaal Hue en Sonos uit, voert ondersteunde opdrachten daar uit en meldt de actuele status terug. Voor Sonos gebruikt de probe lokale UPnP-eventabonnementen: volume, dempen, afspelen en groepswijzigingen worden daarom meteen bijgewerkt in plaats van pas bij de volgende pollingronde. De probe opent hiervoor alleen een tijdelijke lokale callbackpoort; er hoeft geen poort vanaf internet naar je thuisnetwerk open te staan. Sta op macOS of Windows inkomende verbindingen voor de probe/Python toe wanneer de firewall daarom vraagt.

Daarnaast worden veilige netwerkvondsten via SSDP en mDNS als alleen-lezen suggesties opgeslagen. Nieuwe vondsten worden nooit automatisch bestuurbare apparaten.

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

Controleer lokaal eerst zonder doorlopende dienst met:

```bash
.venv/bin/python -m family_app_probe.main run --once
```

De configuratie, probe-token en lokale Hue-app-key staan uitsluitend in `~/.config/family-app-probe/config.json` met bestandsrechten `0600`. Trek de probe in via **Instellingen > Koppelingen** om het token onmiddellijk ongeldig te maken.
