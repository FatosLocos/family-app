from django.urls import path

from integrations import views

app_name = "integrations"
urlpatterns = [
    path("", views.index, name="index"),
    path("profiel/", views.save_profile, name="save_profile"),
    path("huishouden/", views.save_household, name="save_household"),
    path("gegevens/exporteren/", views.export_household_data, name="export_household_data"),
    path("outlook/configuratie/", views.save_outlook_config, name="save_outlook_config"),
    path("outlook/start/", views.start_outlook, name="start_outlook"),
    path("outlook/callback/", views.outlook_callback, name="outlook_callback"),
    path("bunq/configuratie/", views.save_bunq_config, name="save_bunq_config"),
    path("bunq/start/", views.start_bunq, name="start_bunq"),
    path("bunq/callback/", views.bunq_callback, name="bunq_callback"),
    path("hue/configuratie/", views.save_hue_config, name="save_hue_config"),
    path("hue/start/", views.start_hue, name="start_hue"),
    path("hue/callback/", views.hue_callback, name="hue_callback"),
    path("hue/<int:connection_id>/bridge/start/", views.arm_hue_bridge, name="arm_hue_bridge"),
    path("hue/<int:connection_id>/bridge/voltooien/", views.finish_hue_bridge, name="finish_hue_bridge"),
    path("<int:connection_id>/synchroniseren/", views.sync_connection, name="sync_connection"),
    path("<int:connection_id>/ontkoppelen/", views.disconnect_connection, name="disconnect_connection"),
]
