from django.apps import AppConfig


class HouseholdsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "households"

    def ready(self):
        import households.signals
