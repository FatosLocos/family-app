from django.urls import path

from integrations import views

app_name = "integrations"
urlpatterns = [
    path("", views.index, name="index"),
    path("profiel/", views.save_profile, name="save_profile"),
    path("huishouden/", views.save_household, name="save_household"),
    path("outlook/configuratie/", views.save_outlook_config, name="save_outlook_config"),
    path("outlook/start/", views.start_outlook, name="start_outlook"),
    path("outlook/callback/", views.outlook_callback, name="outlook_callback"),
    path("bunq/configuratie/", views.save_bunq_config, name="save_bunq_config"),
    path("bunq/start/", views.start_bunq, name="start_bunq"),
    path("bunq/callback/", views.bunq_callback, name="bunq_callback"),
    path("<int:connection_id>/synchroniseren/", views.sync_connection, name="sync_connection"),
    path("<int:connection_id>/ontkoppelen/", views.disconnect_connection, name="disconnect_connection"),
]
