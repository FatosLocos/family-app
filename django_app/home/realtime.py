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
                "sonos_position_seconds": attributes.get("sonos_position_seconds", 0),
                "sonos_duration_seconds": attributes.get("sonos_duration_seconds", 0),
                "sonos_progress_percent": attributes.get("sonos_progress_percent", 0),
                "sonos_can_next": bool(attributes.get("sonos_can_next")),
                "sonos_can_previous": bool(attributes.get("sonos_can_previous")),
                "sonos_can_shuffle": bool(attributes.get("sonos_can_shuffle")),
                "sonos_can_repeat": bool(attributes.get("sonos_can_repeat")),
                "sonos_shuffle": bool(attributes.get("sonos_shuffle")),
                "sonos_repeat": bool(attributes.get("sonos_repeat")),
                "sonos_repeat_one": bool(attributes.get("sonos_repeat_one")),
                "sonos_crossfade": bool(attributes.get("sonos_crossfade")),
                "sonos_can_crossfade": bool(attributes.get("sonos_can_crossfade")),
                "cast_player_state": attributes.get("cast_player_state", ""),
                "cast_volume": attributes.get("cast_volume"),
                "cast_muted": bool(attributes.get("cast_muted")),
                "cast_title": attributes.get("cast_title", ""),
                "cast_artist": attributes.get("cast_artist", ""),
                "cast_position": attributes.get("cast_position", 0),
                "cast_duration": attributes.get("cast_duration", 0),
                "current_temperature": attributes.get("current_temperature"),
                "humidity": attributes.get("humidity"),
                "hvac_status": attributes.get("hvac_status", ""),
                "google_connectivity": attributes.get("google_connectivity", ""),
                "thermostat_mode": attributes.get("thermostat_mode", ""),
                "eco_mode": attributes.get("eco_mode", ""),
                "temperature_heat": attributes.get("temperature_heat"),
                "temperature_cool": attributes.get("temperature_cool"),
                "fan_timer_mode": attributes.get("fan_timer_mode", ""),
                "google_last_event": attributes.get("google_last_event", ""),
                "google_last_event_at": attributes.get("google_last_event_at", ""),
                "home_connect_operation": attributes.get("home_connect_operation", ""),
                "home_connect_program": attributes.get("home_connect_program", ""),
                "home_connect_selected_program": attributes.get("home_connect_selected_program", ""),
                "home_connect_remaining_label": attributes.get("home_connect_remaining_label", ""),
                "home_connect_program_progress": attributes.get("home_connect_program_progress"),
                "home_connect_door_label": attributes.get("home_connect_door_label", ""),
                "home_connect_can_start": bool(attributes.get("home_connect_can_start")),
                "home_connect_start_status": attributes.get("home_connect_start_status", ""),
                "home_connect_last_event": attributes.get("home_connect_last_event", ""),
                "home_connect_last_event_at": attributes.get("home_connect_last_event_at", ""),
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


def broadcast_home_control_result(entity, *, command_id: str, succeeded: bool, error: str = ""):
    """Confirm the result of an asynchronously executed local-probe command."""
    layer = get_channel_layer()
    if not layer:
        return
    async_to_sync(layer.group_send)(
        f"household-home-{entity.household_id}",
        {
            "type": "home.control_result",
            "payload": {
                "type": "home.control.result",
                "entity_id": entity.id,
                "command_id": command_id,
                "succeeded": succeeded,
                "error": error,
            },
        },
    )
