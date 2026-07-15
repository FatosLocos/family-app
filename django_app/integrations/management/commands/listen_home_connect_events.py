from __future__ import annotations

import signal
import threading
import time

from django.core.management.base import BaseCommand

from integrations.home_connect_events import listen_home_connect_events_forever
from integrations.models import IntegrationConnection


class Command(BaseCommand):
    help = "Luister naar directe Home Connect-apparaatevents voor geconfigureerde koppelingen."

    def add_arguments(self, parser):
        parser.add_argument("--scan-interval", type=float, default=60.0, help="Seconden tussen controles op nieuwe koppelingen.")

    def handle(self, *args, **options):
        stop_event = threading.Event()

        def stop(*_args):
            stop_event.set()

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        threads: dict[int, threading.Thread] = {}
        while not stop_event.is_set():
            connections = IntegrationConnection.objects.filter(
                provider=IntegrationConnection.Provider.HOME_CONNECT,
                status__in=["configured", "needs_sync"],
            )
            for connection in connections:
                if connection.id in threads and threads[connection.id].is_alive():
                    continue
                thread = threading.Thread(
                    target=listen_home_connect_events_forever,
                    args=(connection, stop_event),
                    daemon=True,
                    name=f"home-connect-{connection.id}",
                )
                thread.start()
                threads[connection.id] = thread
                self.stdout.write(f"Home Connect-listener gestart voor koppeling {connection.id}.")
            time.sleep(options["scan_interval"])
