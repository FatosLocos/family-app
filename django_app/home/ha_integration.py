"""Home Assistant custom integration via webhooks and REST API.

The webhook side of this integration is receive-only (see
home.views.ha_webhook_receiver): Home Assistant must be configured manually
with a REST command + automation pointing at that URL, since HA has no
stable public API for a third party to register automations remotely."""
import logging
from typing import Any

import requests
from django.utils import timezone

from home.models import HomeEntity

logger = logging.getLogger(__name__)


def handle_state_change_webhook(household_id: int, payload: dict[str, Any]) -> bool:
    """Handle incoming state change from Home Assistant webhook."""
    from common.db_scope import household_db_scope

    try:
        with household_db_scope(household_id):
            entity_id = payload.get("entity_id", "")
            old_state = payload.get("old_state", "")
            new_state = payload.get("new_state", "")
            timestamp = payload.get("timestamp", timezone.now().isoformat())

            # Parse entity_id (format: "domain.entity_name")
            if not entity_id or "." not in entity_id:
                return False

            domain, name = entity_id.split(".", 1)

            # Update or create HomeEntity
            entity, created = HomeEntity.objects.update_or_create(
                household_id=household_id,
                entity_id=entity_id,
                defaults={
                    "domain": domain,
                    "name": name.replace("_", " ").title(),
                    "state": new_state,
                    "source": HomeEntity.Source.HOME_ASSISTANT,
                    "is_available": new_state != "unavailable",
                    "attributes": {
                        "old_state": old_state,
                        "updated_at": timestamp,
                    },
                },
            )

            logger.info(f"Synced HA entity {entity_id}: {old_state} → {new_state}")
            return True

    except Exception as e:
        logger.error(f"Failed to handle HA webhook for household {household_id}: {e}")
        return False


def get_ha_config_url(household_id: int) -> str | None:
    """Get the configuration URL for Home Assistant integration."""
    from home.models import HomeAssistantConfig

    try:
        config = HomeAssistantConfig.objects.get(household_id=household_id)
        return config.base_url
    except HomeAssistantConfig.DoesNotExist:
        return None


def call_ha_service(
    household_id: int, domain: str, service: str, entity_id: str, data: dict[str, Any] | None = None
) -> bool:
    """Call a Home Assistant service (e.g., turn on/off lights)."""
    from common.db_scope import household_db_scope
    from home.models import HomeAssistantConfig
    from integrations.crypto import decrypt

    try:
        with household_db_scope(household_id):
            config = HomeAssistantConfig.objects.get(household_id=household_id)
            token = decrypt(config.token_encrypted)

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            service_data = {"entity_id": entity_id, **(data or {})}

            response = requests.post(
                f"{config.base_url}/api/services/{domain}/{service}",
                json=service_data,
                headers=headers,
                timeout=10,
            )
            response.raise_for_status()

            logger.info(f"Called HA service {domain}.{service} for {entity_id}")
            return True

    except Exception as e:
        logger.error(f"Failed to call HA service for household {household_id}: {e}")
        return False


def get_ha_entities(household_id: int) -> list[dict[str, Any]]:
    """Fetch current entity states from Home Assistant."""
    from common.db_scope import household_db_scope
    from home.models import HomeAssistantConfig
    from integrations.crypto import decrypt

    try:
        with household_db_scope(household_id):
            config = HomeAssistantConfig.objects.get(household_id=household_id)
            token = decrypt(config.token_encrypted)

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            response = requests.get(
                f"{config.base_url}/api/states",
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()

            entities = response.json()
            if isinstance(entities, list):
                return entities
            return []

    except Exception as e:
        logger.error(f"Failed to fetch HA entities for household {household_id}: {e}")
        return []
