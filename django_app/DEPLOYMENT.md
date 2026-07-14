# Django VPS-omschakeling

Deze procedure zet alleen de nieuwe Django-stack op poort `127.0.0.1:8088` klaar. De bestaande app en andere VPS-services blijven ongemoeid totdat de Caddy-edge bewust wordt omgezet.

## Voorbereiden

1. Maak een archief van de huidige app en bestaande database volgens de huidige VPS-procedure. Verwijder niets.
2. Plaats deze repository onder `/opt/family-app`.
3. Kopieer `django_app/.env.example` naar `django_app/.env` en vul minimaal in:

```dotenv
DJANGO_SECRET_KEY=<minimaal-50-tekens-random>
FIELD_ENCRYPTION_KEY=<aparte-random-secret>
POSTGRES_PASSWORD=<lange-unieke-wachtwoord-voor-app-rol>
POSTGRES_SUPERUSER_PASSWORD=<aparte-lange-admin-wachtwoord>
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=app.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://app.example.com
DJANGO_FORCE_HTTPS=1
DJANGO_HSTS_SECONDS=31536000
```

Genereer secrets bijvoorbeeld met `openssl rand -base64 48`. Laat `DATABASE_URL` weg: Compose bouwt die veilig uit `POSTGRES_PASSWORD` op. PostgreSQL start met een aparte `family_app`-rol zonder superuserrechten; alleen die rol wordt door Django gebruikt zodat RLS ook bij directe databaseverbindingen wordt afgedwongen.

De bestaande edge op deze VPS draait op het Docker-netwerk `family-app-edge`. Controleer voordat je start dat het netwerk bestaat; alleen de Django-webcontainer wordt eraan gekoppeld. Daardoor kan de bestaande Caddy-edge later veilig proxyen naar de vaste alias `family-app-web:8000`, zonder poorten van andere services te wijzigen.

```bash
sudo docker network inspect family-app-edge >/dev/null
```

### Capaciteit

De volledige stack draait PostgreSQL, Redis, Gunicorn, Celery worker, Celery beat en Caddy. Reserveer minimaal **2 GB vrije RAM** voor deze stack tijdens build en start. Op een VPS waar de bestaande Arena- en legacy-apps blijven draaien is daarom **minimaal 4 GB totaal RAM** nodig. Start niet wanneer `free -h` minder dan ongeveer 2 GB beschikbaar geheugen toont; een build in swap kan bestaande services vertragen of laten uitvallen.

```bash
free -h
sudo docker stats --no-stream
```

## Starten en valideren

```bash
cd /opt/family-app
sudo docker compose --env-file django_app/.env -f docker-compose.django.yml up -d --build
sudo docker compose --env-file django_app/.env -f docker-compose.django.yml ps
curl -fsS http://127.0.0.1:8088/healthz
sudo docker compose --env-file django_app/.env -f docker-compose.django.yml exec web python manage.py check --deploy
COMPOSE_FILE=/opt/family-app/docker-compose.django.yml ENV_FILE=/opt/family-app/django_app/.env \
  sudo /opt/family-app/django_app/ops/verify_rls.sh
```

De stack start met eigen volumes `family-app_family_app-postgres` en `family-app_family_app-redis`. Alleen bij een nog niet geaccepteerde, lege Django-installatie mag je deze opnieuw initialiseren; dit raakt de legacy-volumes niet:

```bash
sudo docker compose --env-file django_app/.env -f docker-compose.django.yml down -v
```

De RLS-controle opent een transactie, maakt tijdelijk twee huishoudens aan en bevestigt dat het tweede huishouden de taak van het eerste niet kan lezen of schrijven. De transactie wordt teruggedraaid; er blijven geen testgegevens achter. De lokale poort is uitsluitend bedoeld voor deze health- en RLS-checks. Omdat productie sessiecookies HTTPS vereisen, voer browseracceptatie uit via een tijdelijke HTTPS-hostname op de edge of na de gecontroleerde routewissel.

Maak na de tijdelijke HTTPS-route of routewissel een testhuishouden aan, voeg een gezinslid uit en controleer Taken, Boodschappen, Planning en Geld.

## Back-up en hersteltest

Maak een back-up nadat de stack actief is. De dump en het gekoppelde media-archief krijgen dezelfde tijdstempel:

```bash
sudo env BACKUP_DIR=/var/backups/family_app \
  COMPOSE_FILE=/opt/family-app/docker-compose.django.yml \
  ENV_FILE=/opt/family-app/django_app/.env \
  /opt/family-app/django_app/ops/backup.sh
```

Installeer vervolgens `ops/systemd/family-app-backup.service` en
`ops/systemd/family-app-backup.timer` onder `/etc/systemd/system/`, voer
`sudo systemctl daemon-reload` uit en activeer de timer met
`sudo systemctl enable --now family-app-backup.timer`.

Valideer eerst iedere nieuwe back-up zonder productiedata te raken. Dit herstelt de dump in een tijdelijke controle-database, controleert het media-archief en verwijdert die tijdelijke database direct weer:

```bash
COMPOSE_FILE=/opt/family-app/docker-compose.django.yml ENV_FILE=/opt/family-app/django_app/.env \
  /opt/family-app/django_app/ops/verify-backup.sh /var/backups/family_app/family_app-YYYY-MM-DDTHH-MM-SS.dump
```

Voer daarna op een onderhoudsmoment de volledige hersteltest uit op de nieuwe stack. Het script vraagt expliciet om `HERSTEL` en overschrijft alleen de PostgreSQL-database van deze Compose-stack:

```bash
COMPOSE_FILE=/opt/family-app/docker-compose.django.yml ENV_FILE=/opt/family-app/django_app/.env \
  /opt/family-app/django_app/ops/restore.sh /var/backups/family_app/family_app-YYYY-MM-DDTHH-MM-SS.dump
```

Controleer na herstel opnieuw `http://127.0.0.1:8088/healthz` en het aantal testgegevens.

## Definitieve routewissel

Pas pas na acceptatie de bestaande Caddy-edge aan zodat `app.example.com` naar `family-app-web:8000` proxy't. De bestaande edge en de Django-webcontainer delen dan alleen het `family-app-edge`-netwerk. Herlaad alleen de edge-configuratie en verifieer vervolgens:

```caddy
app.example.com {
    encode zstd gzip
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
        -Server
    }
    reverse_proxy family-app-web:8000 {
        health_uri /healthz
        health_interval 15s
    }
}
```

De op poort `127.0.0.1:8088` gebonden Django-Caddy-container blijft beschikbaar voor lokale VPS-validatie; hij is niet de productie-upstream van de bestaande edge.

```bash
curl -fsS https://app.example.com/healthz
```

Voor rollback zet je uitsluitend die Caddy-route terug naar de gearchiveerde legacy-app. Stop of verwijder de legacy-app pas nadat de nieuwe app en back-up/hersteltest zijn geaccepteerd.
