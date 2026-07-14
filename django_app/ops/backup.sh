#!/bin/sh
set -eu

backup_dir="${BACKUP_DIR:-/var/backups/family_app}"
retain_days="${BACKUP_RETAIN_DAYS:-14}"
compose_file="${COMPOSE_FILE:-/opt/family-app/docker-compose.django.yml}"
env_file="${ENV_FILE:-/opt/family-app/django_app/.env}"
mkdir -p "$backup_dir"
timestamp="$(date +%Y-%m-%dT%H-%M-%S)"
backup_file="$backup_dir/family_app-$timestamp.dump"
temporary_file="$backup_file.partial"
media_file="$backup_dir/family_app-$timestamp.media.tar"
temporary_media_file="$media_file.partial"

umask 077
trap 'rm -f "$temporary_file" "$temporary_media_file"' EXIT HUP INT TERM

docker compose --env-file "$env_file" -f "$compose_file" exec -T postgres \
  pg_dump -U postgres -d family_app -Fc > "$temporary_file"
docker compose --env-file "$env_file" -f "$compose_file" exec -T web \
  sh -c 'mkdir -p /app/media && tar -C /app/media -cf - .' > "$temporary_media_file"
mv "$temporary_file" "$backup_file"
mv "$temporary_media_file" "$media_file"
trap - EXIT HUP INT TERM
find "$backup_dir" -type f -name 'family_app-*.dump' -mtime +"$retain_days" -delete
