# Family App

De volledige herbouw van de gezinsapp. De bestaande Next.js-app in de projectroot is legacy en wordt niet door deze stack gebruikt.

## Lokaal

```bash
/opt/homebrew/bin/python3.12 -m venv ../.venv-django
../.venv-django/bin/pip install -r requirements.txt
cat > .env.local <<'EOF'
DATABASE_URL=postgresql://family_app@127.0.0.1:5432/family_app
TEST_DATABASE_URL=postgresql://<lokale-admin>@127.0.0.1:5432/family_app
DJANGO_DEBUG=1
DJANGO_FORCE_HTTPS=0
EOF
./ops/run-dev.sh 8000
```

De app accepteert uitsluitend PostgreSQL. Open `http://localhost:8000/account/signup/` om een nieuw huishouden te starten.

Gebruik daarna `./ops/run-checks.sh` voor de testdatabase. Productie gebruikt `TEST_DATABASE_URL` nooit.

Voor de lokale RLS-proef moet je met een beperkte database-rol werken. Wanneer
je lokale beheeraccount superuser is, gebruik dan bijvoorbeeld:

```bash
RLS_ROLE=family_app DATABASE_URL=postgresql://<lokale-admin>@127.0.0.1:5432/family_app \
  ./ops/verify_rls.sh
```

De productiecontainer gebruikt de beperkte applicatierol al rechtstreeks; daar
is `RLS_ROLE` niet nodig.

## VPS

1. Kopieer `django_app/.env.example` naar `django_app/.env` en vul alle secrets in.
2. Voeg `POSTGRES_PASSWORD` en `POSTGRES_SUPERUSER_PASSWORD` toe aan hetzelfde `.env` bestand. Django gebruikt alleen de niet-superuser app-rol; de adminrol is uitsluitend voor initialisatie en back-up/herstel.
3. Start de stack vanaf de repository-root:

```bash
docker compose --env-file django_app/.env -f docker-compose.django.yml up -d --build
```

De bestaande Caddy-edge op de VPS kan vervolgens `app.example.com` naar `family-app-web:8000` op het gedeelde edge-netwerk doorsturen. Laat de oude Next-app op zijn bestaande poort draaien totdat deze herbouw is geaccepteerd.

De volledige gecontroleerde start-, back-up-, herstel- en rollbackprocedure staat in [DEPLOYMENT.md](DEPLOYMENT.md).

De Home Assistant gateway draait als aparte listener-service naast de web- en Celery-processen. Het runtime- en contractontwerp staat in [docs/home-assistant-gateway.md](docs/home-assistant-gateway.md).

## Back-up

Installeer de meegeleverde systemd-timer voor een dagelijkse back-up om 03:15:

```bash
sudo install -m 644 ops/systemd/family-app-backup.service /etc/systemd/system/family-app-backup.service
sudo install -m 644 ops/systemd/family-app-backup.timer /etc/systemd/system/family-app-backup.timer
sudo systemctl daemon-reload
sudo systemctl enable --now family-app-backup.timer
systemctl list-timers family-app-backup.timer
```

De back-ups blijven lokaal op de VPS; externe versleutelde opslag is bewust nog niet geconfigureerd. Controleer een nieuwe dump altijd eerst zonder productiedata te wijzigen:

```bash
COMPOSE_FILE=/opt/family-app/docker-compose.django.yml ENV_FILE=/opt/family-app/django_app/.env \
  /opt/family-app/django_app/ops/verify-backup.sh /var/backups/family_app/family_app-YYYY-MM-DDTHH-MM-SS.dump
```
