# Deployment

Production runs on the TransIP VPS in `/opt/family-app`.

## Environment

The Docker Compose stack runs a local PostgreSQL database on the VPS. App data is stored in the Docker volume
`family-app_postgres-data`; it remains on the VPS.

Required for local VPS database mode:

```bash
DATABASE_URL=postgresql://family_app:<password>@db:5432/family_app
HOSTNAME=0.0.0.0
```

The Compose file provides the `db` service and passes `DATABASE_URL` to the `web` service.

On a fresh local VPS database, visit `/login` and create the first account. That account becomes the household owner.
Registration is closed after the first account. Add household members from Instellingen with a new invite code; the member accepts it at `/invite/CODE`.

After editing runtime values on the VPS:

```bash
cd /opt/family-app
sudo docker compose up -d --no-build --force-recreate web
curl -fsS https://app.example.com/api/health
```

## DNS and TLS

`app.example.com` moet naar je VPS wijzen and is served by the existing Caddy edge container.
Caddy obtains and renews the public Let's Encrypt certificate.
