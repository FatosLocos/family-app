from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from integrations.local_probe import ProbeError, apply_discovery, apply_inventory, authenticate_probe, mark_probe_offline, mark_probe_seen, record_probe_command_result


class LocalProbeConsumer(AsyncJsonWebsocketConsumer):
    """Authenticated outbound tunnel from one household's LAN to the VPS."""

    async def connect(self):
        self.probe_id = self.scope["url_route"]["kwargs"]["probe_id"]
        token = parse_qs(self.scope.get("query_string", b"").decode()).get("token", [""])[0]
        try:
            self.probe = await self._authenticate(self.probe_id, token)
        except ProbeError:
            await self.close(code=4403)
            return
        self.group_name = f"local-probe-{self.probe_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self._seen()
        await self.send_json({"type": "connected", "probe_id": str(self.probe_id)})

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
        if hasattr(self, "probe"):
            await self._offline()

    async def receive_json(self, content, **kwargs):
        event_type = content.get("type") if isinstance(content, dict) else ""
        try:
            if event_type == "heartbeat":
                await self._seen(
                    content.get("version", ""),
                    content.get("adapters"),
                    bool(content.get("replace_adapters")),
                )
                await self.send_json({"type": "ack", "event": "heartbeat"})
            elif event_type == "inventory":
                count = await self._inventory(content.get("entities", []))
                await self.send_json({"type": "ack", "event": "inventory", "count": count})
            elif event_type == "discovery":
                count = await self._discovery(content.get("devices", []))
                await self.send_json({"type": "ack", "event": "discovery", "count": count})
            elif event_type == "command_result":
                await self._command_result(
                    bool(content.get("succeeded")),
                    content.get("error", ""),
                    content.get("command_id", ""),
                    content.get("entity_id", ""),
                    content.get("action", ""),
                )
                await self.send_json({"type": "ack", "event": "command_result"})
            else:
                await self.send_json({"type": "error", "message": "Onbekend probe-event."})
        except ProbeError as error:
            await self.send_json({"type": "error", "message": str(error)})

    async def probe_command(self, event):
        await self.send_json(event["payload"])

    @database_sync_to_async
    def _authenticate(self, probe_id, token):
        return authenticate_probe(probe_id, token)

    @database_sync_to_async
    def _seen(self, version="", adapters=None, replace_adapters=False):
        mark_probe_seen(self.probe, version, adapters, replace_adapters=replace_adapters)

    @database_sync_to_async
    def _offline(self):
        mark_probe_offline(self.probe)

    @database_sync_to_async
    def _command_result(self, succeeded, error, command_id, entity_id, action):
        record_probe_command_result(
            self.probe,
            succeeded,
            error,
            command_id=command_id,
            entity_id=entity_id,
            action=action,
        )

    @database_sync_to_async
    def _inventory(self, entities):
        return apply_inventory(self.probe, entities)

    @database_sync_to_async
    def _discovery(self, devices):
        return apply_discovery(self.probe, devices)
