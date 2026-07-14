from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def home_entity_payload(entity):
    attributes = entity.attributes if isinstance(entity.attributes, dict) else {}
    return {
        "type": "home.entity.updated",
        "entity": {
            "id": entity.id,
            "source": entity.source,
            "domain": entity.domain,
            "state": entity.state,
            "is_available": entity.is_available,
            "attributes": {
                "sonos_playback_state": attributes.get("sonos_playback_state", ""),
                "sonos_volume": attributes.get("sonos_volume"),
                "sonos_muted": bool(attributes.get("sonos_muted")),
                "sonos_group_id": attributes.get("sonos_group_id", ""),
                "sonos_now_playing_title": attributes.get("sonos_now_playing_title", ""),
                "sonos_now_playing_artist": attributes.get("sonos_now_playing_artist", ""),
                "sonos_now_playing_album": attributes.get("sonos_now_playing_album", ""),
                "sonos_now_playing_artwork": attributes.get("sonos_now_playing_artwork", ""),
                "sonos_source_name": attributes.get("sonos_source_name", ""),
                "sonos_position": attributes.get("sonos_position", ""),
                "sonos_duration": attributes.get("sonos_duration", ""),
                "sonos_can_next": bool(attributes.get("sonos_can_next")),
                "sonos_can_previous": bool(attributes.get("sonos_can_previous")),
                "sonos_can_shuffle": bool(attributes.get("sonos_can_shuffle")),
                "sonos_can_repeat": bool(attributes.get("sonos_can_repeat")),
                "sonos_shuffle": bool(attributes.get("sonos_shuffle")),
                "sonos_repeat": bool(attributes.get("sonos_repeat")),
            },
        },
    }


def broadcast_home_entity(entity):
    """Send a confirmed entity state to all open home dashboards in its household."""
    layer = get_channel_layer()
    if not layer:
        return
    async_to_sync(layer.group_send)(
        f"household-home-{entity.household_id}",
        {"type": "home.entity_update", "payload": home_entity_payload(entity)},
    )
