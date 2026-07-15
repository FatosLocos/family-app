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


def _hex_from_xy(value):
    """Return a presentational sRGB color from a Hue xy point when available."""
    if not isinstance(value, dict):
        return ""
    try:
        x_value, y_value = float(value.get("x")), float(value.get("y"))
    except (TypeError, ValueError):
        return ""
    if not 0 < y_value <= 1 or not 0 <= x_value <= 1:
        return ""
    z_value = max(0.0, 1 - x_value - y_value)
    x_xyz = x_value / y_value
    z_xyz = z_value / y_value
    red = 3.2406 * x_xyz - 1.5372 - 0.4986 * z_xyz
    green = -0.9689 * x_xyz + 1.8758 + 0.0415 * z_xyz
    blue = 0.0557 * x_xyz - 0.204 + 1.057 * z_xyz
    maximum = max(red, green, blue, 1.0)
    channels = [max(0.0, min(1.0, channel / maximum)) for channel in (red, green, blue)]
    channels = [12.92 * channel if channel <= 0.0031308 else 1.055 * channel ** (1 / 2.4) - 0.055 for channel in channels]
    return "#" + "".join(f"{round(channel * 255):02x}" for channel in channels)


def _light_capabilities(resource):
    dimming = resource.get("dimming") if isinstance(resource.get("dimming"), dict) else {}
    color = resource.get("color") if isinstance(resource.get("color"), dict) else {}
    color_temperature = resource.get("color_temperature") if isinstance(resource.get("color_temperature"), dict) else {}
    mirek_schema = color_temperature.get("mirek_schema") if isinstance(color_temperature.get("mirek_schema"), dict) else {}
    effects = resource.get("effects_v2") if isinstance(resource.get("effects_v2"), dict) else resource.get("effects") if isinstance(resource.get("effects"), dict) else {}
    effect_values = [str(item) for item in effects.get("effect_values", []) if isinstance(item, str)]
    effects_resource = "effects_v2" if isinstance(resource.get("effects_v2"), dict) else "effects" if isinstance(resource.get("effects"), dict) else ""
    return {
        "brightness": dimming.get("brightness"),
        "supports_dimming": bool(dimming),
        "color_xy": color.get("xy") if isinstance(color.get("xy"), dict) else {},
        "color_hex": _hex_from_xy(color.get("xy")),
        "supports_color": bool(color),
        "color_temperature": color_temperature.get("mirek"),
        "color_temperature_min": mirek_schema.get("mirek_minimum") or 153,
        "color_temperature_max": mirek_schema.get("mirek_maximum") or 500,
        "supports_color_temperature": bool(color_temperature),
        "supports_effects": bool(effect_values),
        "effect_values": effect_values,
        "effect_current": str(effects.get("status") or "no_effect") if effect_values else "",
        "effects_resource": effects_resource,
        "effects_action_key": "action" if effects_resource == "effects_v2" else "effect" if effects_resource else "",
    }


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

    def link_bridge(self, bridge: str) -> None:
        """Register this probe as a local Hue application for one bridge."""
        normalized_bridge = str(bridge or "").strip().rstrip("/")
        if not normalized_bridge.startswith(("http://", "https://")):
            raise RuntimeError("Het lokale Hue Bridge-adres is ongeldig.")
        self.config["bridge"] = normalized_bridge
        self.config.pop("app_key", None)
        self.bridge = normalized_bridge
        self.app_key = ""
        self.link()

    def inventory(self):
        if not self.enabled:
            return []
        response = requests.get(f"{self.bridge}/clip/v2/resource", headers={"hue-application-key": self.app_key}, verify=False, timeout=10)
        response.raise_for_status()
        result = response.json().get("data", [])
        grouped_light_context = {}
        owner_context = {}
        device_locations = {}
        device_light_ids = {}
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
                "device_ids": [],
            }
            owner_context[str(item.get("id") or "")] = context
            for child in item.get("children") or []:
                if isinstance(child, dict) and child.get("rtype") == "device" and child.get("rid"):
                    device_id = str(child["rid"])
                    device_locations.setdefault(device_id, set()).add(name)
                    context["device_ids"].append(device_id)
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
            device_light_ids[str(item["id"])] = [
                str(service["rid"])
                for service in item.get("services") or []
                if isinstance(service, dict) and service.get("rtype") == "light" and service.get("rid")
            ]
        for context in owner_context.values():
            member_device_ids = context.get("device_ids", [])
            context["member_light_ids"] = [
                light_id
                for device_id in member_device_ids
                for light_id in device_light_ids.get(device_id, [])
            ]
            context["member_names"] = [
                str(device_context.get(device_id, {}).get("name") or "")
                for device_id in member_device_ids
                if device_context.get(device_id, {}).get("name")
            ]
        light_capabilities = {
            str(item.get("id") or ""): _light_capabilities(item)
            for item in result
            if item.get("type") == "light" and item.get("id")
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
                output.append({"source": "hue", "local_key": f"light:{resource_id}", "external_id": resource_id, "domain": "light", "name": metadata.get("name") or "Hue lamp", "state": "on" if on else "off", "is_available": True, "is_supported": True, "attributes": {"hue_light_id": resource_id, "hue_resource_type": "light", **_light_capabilities(item)}})
            elif resource_type == "grouped_light":
                on = bool((item.get("on") or {}).get("on"))
                owner = item.get("owner") if isinstance(item.get("owner"), dict) else {}
                context = grouped_light_context.get(str(resource_id), {}) or owner_context.get(str(owner.get("rid") or ""), {})
                # Bridge-home and private groups have no useful room/zone label.
                # The app presents rooms and zones, not these implementation groups.
                if not context:
                    continue
                member_light_ids = context.get("member_light_ids", [])
                member_color_hexes = [
                    capabilities["color_hex"]
                    for light_id in member_light_ids
                    if (capabilities := light_capabilities.get(str(light_id))) and capabilities.get("color_hex")
                ]
                group_capabilities = _light_capabilities(item)
                unique_colors = list(dict.fromkeys(member_color_hexes))
                if not group_capabilities.get("color_hex") and len(unique_colors) == 1:
                    group_capabilities["color_hex"] = unique_colors[0]
                group_capabilities["member_color_hexes"] = unique_colors
                group_capabilities["color_mixed"] = len(unique_colors) > 1
                output.append({"source": "hue", "local_key": f"grouped_light:{resource_id}", "external_id": resource_id, "domain": "group", "name": context.get("name") or metadata.get("name") or "Hue kamer", "state": "on" if on else "off", "is_available": True, "is_supported": True, "attributes": {"hue_grouped_light_id": resource_id, "hue_resource_type": "grouped_light", "hue_group_name": context.get("name", ""), "hue_group_type": context.get("group_type", ""), "hue_locations": context.get("locations", []), "member_light_ids": member_light_ids, "member_names": context.get("member_names", []), "member_count": len(member_light_ids), **group_capabilities}})
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
