from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from households.models import Membership


class HomeLiveConsumer(AsyncJsonWebsocketConsumer):
    """Push home-entity changes only to authenticated household members."""

    async def connect(self):
        self.household_id = int(self.scope["url_route"]["kwargs"]["household_id"])
        user = self.scope.get("user")
        if not user or not user.is_authenticated or not await self._is_member(user.id, self.household_id):
            await self.close(code=4403)
            return
        self.group_name = f"household-home-{self.household_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def home_entity_update(self, event):
        await self.send_json(event["payload"])

    async def home_control_result(self, event):
        await self.send_json(event["payload"])

    @database_sync_to_async
    def _is_member(self, user_id, household_id):
        return Membership.objects.filter(user_id=user_id, household_id=household_id).exists()
