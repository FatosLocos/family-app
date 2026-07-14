# Home Assistant Gateway

Family App gebruikt Home Assistant als externe smart-home gateway. Home Assistant zelf wordt niet gebundeld in de Family App stack; alleen de Family App listener draait mee in Docker.

## Runtime

- Home Assistant draait bij voorkeur thuis op Home Assistant OS, Home Assistant Green/Yellow, Raspberry Pi, mini-pc, NAS of VM.
- Family App draait op de Django/VPS-stack.
- De Compose-service `ha-listener` draait `python manage.py listen_home_assistant` en gebruikt dezelfde database en Redis channel layer als `web`.
- De Family App bereikt Home Assistant via de ingestelde base URL en long-lived access token. Gebruik bij externe toegang bij voorkeur Nabu Casa, Tailscale of WireGuard.

## Inbound gedrag

- Handmatige synchronisatie blijft beschikbaar via de REST API.
- De listener gebruikt de Home Assistant WebSocket API voor:
  - authenticatie op `/api/websocket`;
  - initiele `get_states`;
  - registry reads voor entities, devices en areas;
  - `state_changed` events.
- Home Assistant entiteiten worden opgeslagen als `HomeEntity` met `source="home_assistant"`.
- Registry metadata blijft in `HomeEntity.attributes` onder `ha_*` keys:
  - `ha_area`, `ha_area_id`;
  - `ha_entity_registry`;
  - `ha_device`, `ha_device_identifiers`;
  - `ha_device_class`, `ha_icon`, `ha_platform`;
  - `ha_last_changed`, `ha_last_updated`.

## Deduplicatie en fallback

- De Huis UI toont Home Assistant als voorkeursbron wanneer hetzelfde fysieke apparaat ook via Hue, Sonos, Google Home, LG ThinQ of de lokale probe bestaat.
- Directe integraties worden niet verwijderd; ze blijven beschikbaar als fallback.
- Fallback mag alleen bij een betrouwbare match op bekende identifiers of exact genormaliseerde naam + domain.
- Audits vermelden of bediening via Home Assistant of via fallback liep.

## Custom Home Assistant integration contract

De toekomstige Home Assistant custom integration gebruikt de namespace `family_app`. V1 publiceert nog geen Family App-data naar Home Assistant, maar het contract ligt vast in `home.ha_contract`.

Geplande entiteiten:

| Platform | Object id | Betekenis |
| --- | --- | --- |
| `sensor` | `family_open_tasks` | Aantal open gezinstaken |
| `calendar` | `family` | Gezinsagenda |
| `todo` | `family_shopping` | Boodschappenlijst |
| `binary_sensor` | `family_maintenance_due` | Er is verlopen onderhoud |

Geplande events:

| Event type | Verplichte velden |
| --- | --- |
| `family_app.task_created` | `task_id`, `title`, `household_id` |
| `family_app.task_completed` | `task_id`, `title`, `household_id`, `completed_by` |
| `family_app.maintenance_due` | `maintenance_id`, `title`, `household_id`, `due_date` |

De custom integration moet later authenticeren tegen een expliciet Family App-token per huishouden. Hergebruik nooit het Home Assistant long-lived access token voor verkeer terug naar Family App.
