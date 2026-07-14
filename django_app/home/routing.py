from django.urls import path

from home import consumers
from integrations.consumers import LocalProbeConsumer


websocket_urlpatterns = [
    path("ws/huis/<int:household_id>/", consumers.HomeLiveConsumer.as_asgi()),
    path("ws/probe/<uuid:probe_id>/", LocalProbeConsumer.as_asgi()),
]
