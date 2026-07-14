from __future__ import annotations

import signal
import threading
import time

from django.core.management.base import BaseCommand

from home.ha_gateway import listen_forever, sync_once
from home.models import HomeAssistantConfig


class Command(BaseCommand):
    help = "Luister naar Home Assistant WebSocket events voor gekoppelde huishoudens."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Voer alleen de initiele WebSocket-sync uit en stop.")
        parser.add_argument("--scan-interval", type=float, default=60.0, help="Aantal seconden tussen scans naar nieuwe HA-configs.")

    def handle(self, *args, **options):
        if options["once"]:
            total = 0
            for config in HomeAssistantConfig.objects.select_related("household"):
                try:
                    total += sync_once(config)
                except Exception as error:
                    config.last_error = str(error)[:300]
                    config.save(update_fields=["last_error", "updated_at"])
            self.stdout.write(self.style.SUCCESS(f"{total} Home Assistant-entiteiten bijgewerkt."))
            return

        stop_event = threading.Event()

        def stop(*_args):
            stop_event.set()

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        threads: dict[int, threading.Thread] = {}
        while not stop_event.is_set():
            for config in HomeAssistantConfig.objects.select_related("household"):
                if config.id in threads and threads[config.id].is_alive():
                    continue
                thread = threading.Thread(target=listen_forever, args=(config, stop_event), daemon=True)
                thread.start()
                threads[config.id] = thread
                self.stdout.write(f"Home Assistant listener gestart voor huishouden {config.household_id}.")
            time.sleep(options["scan_interval"])
