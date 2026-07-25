from django.apps import AppConfig


class HouseholdsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "households"

    def ready(self):
        # Import puur om het neveneffect: households.signals registreert de
        # signal-handlers. Weghalen laat de registratie stil wegvallen.
        import households.signals  # noqa: F401
