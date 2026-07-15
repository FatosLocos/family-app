from __future__ import annotations

import signal
import threading
import time

from django.core.management.base import BaseCommand

from common.db_scope import household_db_scope
from home.ha_gateway import listen_forever, sync_once
from home.models import HomeAssistantConfig
from households.models import Household


class Command(BaseCommand):
    help = "Luister naar Home Assistant WebSocket events voor gekoppelde huishoudens."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Voer alleen de initiele WebSocket-sync uit en stop.")
        parser.add_argument("--scan-interval", type=float, default=60.0, help="Aantal seconden tussen scans naar nieuwe HA-configs.")

    def handle(self, *args, **options):
        if options["once"]:
            total = 0
            for household in Household.objects.all():
                with household_db_scope(household.pk):
                    for config in HomeAssistantConfig.objects.filter(household=household):
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
            for household in Household.objects.all():
                with household_db_scope(household.pk):
                    for config in HomeAssistantConfig.objects.filter(household=household):
                        if config.id in threads and threads[config.id].is_alive():
                            continue
                        thread = threading.Thread(target=listen_forever, args=(config, stop_event), daemon=True)
                        thread.start()
                        threads[config.id] = thread
                        self.stdout.write(f"Home Assistant listener gestart voor huishouden {config.household_id}.")
            time.sleep(options["scan_interval"])
