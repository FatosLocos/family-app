from __future__ import annotations

import requests


def _xy_from_hex(value):
    raw = str(value or "").strip().lstrip("#")
    if len(raw) != 6 or any(character not in "0123456789abcdefABCDEF" for character in raw):
        raise RuntimeError("Kies een geldige kleur.")
    channels = [int(raw[index:index + 2], 16) / 255 for index in range(0, 6, 2)]
    red, green, blue = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
    x_value = red * 0.4124 + green * 0.3576 + blue * 0.1805
    y_value = red * 0.2126 + green * 0.7152 + blue * 0.0722
    z_value = red * 0.0193 + green * 0.1192 + blue * 0.9505
    total = x_value + y_value + z_value
    if total <= 0:
        raise RuntimeError("Zwart kan niet als Hue-kleur worden ingesteld. Schakel de lamp uit om zwart te gebruiken.")
    return {"x": round(x_value / total, 4), "y": round(y_value / total, 4)}


SENSOR_FIELDS = {
    "motion": ("motion", "motion", "Beweging"),
    "temperature": ("temperature", "temperature", "Temperatuur"),
    "light_level": ("light", "light_level", "Lichtniveau"),
    "button": ("button", "last_event", "Knop"),
    "relative_rotary": ("relative_rotary", "last_event", "Draaiknop"),
}


def _sensor_state(resource_type, value):
    if resource_type == "motion":
        return "Beweging" if value else "Geen beweging"
    if resource_type == "temperature":
        return f"{float(value):.1f} °C" if value is not None else "Onbekend"
    if resource_type == "light_level":
        return f"{int(value)} lux" if value is not None else "Onbekend"
    if resource_type == "button":
        return str(value or "Geen recente actie").replace("_", " ")
    if resource_type == "relative_rotary":
        rotation = value.get("rotation") if isinstance(value, dict) else {}
        if rotation:
            direction = "rechts" if rotation.get("direction") == "clock_wise" else "links"
            return f"{rotation.get('steps', 0)} stappen {direction}"
        return str(value.get("action") or "Geen recente actie") if isinstance(value, dict) else "Geen recente actie"
    return str(value or "Onbekend")


class HueAdapter:
    name = "hue"

    def __init__(self, config):
        self.config = config
        self.bridge = str(config.get("bridge", "")).rstrip("/")
        self.app_key = str(config.get("app_key", ""))

    @property
    def enabled(self):
        return bool(self.bridge and self.app_key)

    def link(self):
        response = requests.post(f"{self.bridge}/api", json={"devicetype": "family-app-probe"}, verify=False, timeout=8)
        response.raise_for_status()
        result = response.json()
        success = result[0].get("success", {}) if isinstance(result, list) and result else {}
        username = success.get("username")
        if not username:
            raise RuntimeError("Hue Bridge is nog niet bevestigd. Druk op de fysieke Bridge-knop en probeer opnieuw.")
        self.config["app_key"] = username
        self.app_key = username

    def inventory(self):
        if not self.enabled:
            return []
        response = requests.get(f"{self.bridge}/clip/v2/resource", headers={"hue-application-key": self.app_key}, verify=False, timeout=10)
        response.raise_for_status()
        result = response.json().get("data", [])
        grouped_light_context = {}
        owner_context = {}
        device_locations = {}
        for item in result:
            resource_type = item.get("type")
            if resource_type not in {"room", "zone"}:
                continue
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            name = str(metadata.get("name") or ("Hue kamer" if resource_type == "room" else "Hue zone"))
            context = {
                "name": name,
                "group_type": resource_type,
                "locations": [name],
            }
            owner_context[str(item.get("id") or "")] = context
            for child in item.get("children") or []:
                if isinstance(child, dict) and child.get("rtype") == "device" and child.get("rid"):
                    device_locations.setdefault(str(child["rid"]), set()).add(name)
            for service in item.get("services") or []:
                if not isinstance(service, dict) or service.get("rtype") != "grouped_light" or not service.get("rid"):
                    continue
                grouped_light_context[str(service["rid"])] = context
        device_context = {}
        for item in result:
            if item.get("type") != "device" or not item.get("id"):
                continue
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            product_data = item.get("product_data") if isinstance(item.get("product_data"), dict) else {}
            device_context[str(item["id"])] = {
                "name": str(metadata.get("name") or product_data.get("product_name") or "Hue apparaat"),
                "product_name": str(product_data.get("product_name") or ""),
                "locations": sorted(device_locations.get(str(item["id"]), set())),
                "battery_level": None,
                "connectivity": "",
            }
        for item in result:
            owner = item.get("owner") if isinstance(item.get("owner"), dict) else {}
            context = device_context.get(str(owner.get("rid") or ""))
            if not context:
                continue
            if item.get("type") == "device_power":
                power_state = item.get("power_state") if isinstance(item.get("power_state"), dict) else {}
                context["battery_level"] = power_state.get("battery_level")
            elif item.get("type") == "zigbee_connectivity":
                context["connectivity"] = str(item.get("status") or "")
        output = []
        for item in result:
            resource_type, resource_id = item.get("type"), item.get("id")
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            if resource_type == "light":
                on = bool((item.get("on") or {}).get("on"))
                dimming = item.get("dimming") or {}
                output.append({"source": "hue", "local_key": f"light:{resource_id}", "external_id": resource_id, "domain": "light", "name": metadata.get("name") or "Hue lamp", "state": "on" if on else "off", "is_available": True, "is_supported": True, "attributes": {"hue_light_id": resource_id, "hue_resource_type": "light", "brightness": dimming.get("brightness"), "supports_dimming": bool(dimming), "supports_color": bool(item.get("color")), "supports_color_temperature": bool(item.get("color_temperature"))}})
            elif resource_type == "grouped_light":
                on = bool((item.get("on") or {}).get("on"))
                owner = item.get("owner") if isinstance(item.get("owner"), dict) else {}
                context = grouped_light_context.get(str(resource_id), {}) or owner_context.get(str(owner.get("rid") or ""), {})
                # Bridge-home and private groups have no useful room/zone label.
                # The app presents rooms and zones, not these implementation groups.
                if not context:
                    continue
                output.append({"source": "hue", "local_key": f"grouped_light:{resource_id}", "external_id": resource_id, "domain": "group", "name": context.get("name") or metadata.get("name") or "Hue kamer", "state": "on" if on else "off", "is_available": True, "is_supported": True, "attributes": {"hue_grouped_light_id": resource_id, "hue_resource_type": "grouped_light", "hue_group_name": context.get("name", ""), "hue_group_type": context.get("group_type", ""), "hue_locations": context.get("locations", []), "supports_dimming": bool(item.get("dimming"))}})
            elif resource_type == "scene":
                group = item.get("group") if isinstance(item.get("group"), dict) else {}
                context = owner_context.get(str(group.get("rid") or ""), {})
                output.append({"source": "hue", "local_key": f"scene:{resource_id}", "external_id": resource_id, "domain": "scene", "name": metadata.get("name") or "Hue scène", "state": str((item.get("status") or {}).get("active") or "inactive"), "is_available": True, "is_supported": True, "attributes": {"hue_scene_id": resource_id, "hue_resource_type": "scene", "hue_group_name": context.get("name", ""), "hue_group_type": context.get("group_type", ""), "hue_locations": context.get("locations", [])}})
            elif resource_type in SENSOR_FIELDS:
                owner = item.get("owner") if isinstance(item.get("owner"), dict) else {}
                device = device_context.get(str(owner.get("rid") or ""), {})
                container_key, value_key, label = SENSOR_FIELDS[resource_type]
                container = item.get(container_key) if isinstance(item.get(container_key), dict) else {}
                value = container.get(value_key)
                state = _sensor_state(resource_type, value)
                connectivity = device.get("connectivity", "")
                output.append({"source": "hue", "local_key": f"sensor:{resource_id}", "external_id": resource_id, "domain": "sensor", "name": f"{device.get('name', 'Hue sensor')} · {label}", "state": state, "is_available": connectivity != "disconnected", "is_supported": False, "attributes": {"hue_sensor_kind": label, "hue_device_id": str(owner.get("rid") or resource_id), "hue_device_name": device.get("name", "Hue sensor"), "hue_product_name": device.get("product_name", ""), "hue_locations": device.get("locations", []), "hue_battery_level": device.get("battery_level"), "hue_connectivity": connectivity, "sensor_active": bool(value) if resource_type == "motion" else False}})
        return output

    def control(self, local_key, action, value):
        local_type, resource_id = local_key.split(":", 1)
        resource_type = "grouped_light" if local_type == "grouped_light" else "scene" if local_type == "scene" else "light"
        if resource_type == "scene":
            if action != "activate":
                raise RuntimeError("Deze Hue-scène ondersteunt alleen starten.")
            response = requests.put(f"{self.bridge}/clip/v2/resource/scene/{resource_id}", headers={"hue-application-key": self.app_key}, json={"recall": {"action": "active"}}, verify=False, timeout=8)
            response.raise_for_status()
            return
        body = {"on": {"on": action == "on"}} if action in {"on", "off"} else {}
        if action == "brightness":
            brightness = float(value)
            if not 0 <= brightness <= 100:
                raise RuntimeError("Helderheid moet tussen 0 en 100 liggen.")
            body = {"on": {"on": True}, "dimming": {"brightness": brightness}}
        if action == "color_temperature":
            body = {"on": {"on": True}, "color_temperature": {"mirek": int(float(value))}}
        if action == "color":
            body = {"on": {"on": True}, "color": {"xy": _xy_from_hex(value)}}
        if action == "effect":
            body = {"effects_v2": {"action": str(value)}}
        if not body:
            raise RuntimeError("Deze Hue-actie wordt lokaal nog niet ondersteund.")
        response = requests.put(f"{self.bridge}/clip/v2/resource/{resource_type}/{resource_id}", headers={"hue-application-key": self.app_key}, json=body, verify=False, timeout=8)
        response.raise_for_status()
