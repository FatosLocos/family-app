# Family App

Self-hosted gezinsapp voor planning, huishouden, geld en huis. De actieve applicatie is de Django-monoliet in [`django_app/`](django_app/).

## Lokaal starten

```bash
./django_app/ops/run-dev.sh 8000
```

Open daarna <http://localhost:8000/account/signup/>. De healthcheck staat op <http://localhost:8000/healthz>.

## Productiestack

De Compose-stack staat in [`docker-compose.django.yml`](docker-compose.django.yml). Kopieer eerst `django_app/.env.example` naar `django_app/.env` en vul de secrets in. De volledige VPS-, back-up- en herstelprocedure staat in [`django_app/DEPLOYMENT.md`](django_app/DEPLOYMENT.md).

## Projectstructuur

- `django_app/`: actieve Django-, HTMX- en PostgreSQL-applicatie.
- `legacy/next-app/`: gearchiveerde Next.js-versie. Niet meer gebruiken voor nieuwe functionaliteit of deployments.

## Controleren

```bash
./django_app/ops/run-checks.sh
```

`django_app/.env.local` bevat naast `DATABASE_URL` voor de beperkte applicatierol ook een lokale `TEST_DATABASE_URL` met alleen tijdelijk beheertoegang voor Django's wegwerp-testdatabase. De RLS-proef zelf draait altijd als de beperkte applicatierol.
