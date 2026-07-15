"""Google Home event cache to reduce polling frequency."""
from datetime import timedelta
from django.core.cache import cache
from django.utils import timezone


def get_cached_google_events(connection_id: int) -> dict | None:
    """Get cached Google Home events for a connection."""
    key = f"google_events:{connection_id}"
    return cache.get(key)


def cache_google_events(connection_id: int, events: dict, ttl: int = 300) -> None:
    """Cache Google Home events with TTL (default 5 minutes)."""
    key = f"google_events:{connection_id}"
    cache.set(key, events, ttl)


def is_google_events_cache_fresh(connection_id: int, max_age: int = 60) -> bool:
    """Check if cached events are fresh enough (default 1 minute)."""
    key = f"google_events:{connection_id}:timestamp"
    last_update = cache.get(key)
    if last_update is None:
        return False
    return (timezone.now() - last_update).total_seconds() < max_age


def mark_google_events_updated(connection_id: int) -> None:
    """Mark when Google events were last updated."""
    key = f"google_events:{connection_id}:timestamp"
    cache.set(key, timezone.now(), 3600)
