from django.urls import path

from home import views

app_name = "home"
urlpatterns = [
    path("", views.index, name="index"),
    path("home-assistant/opslaan/", views.save_home_assistant, name="save_home_assistant"),
    path("home-assistant/synchroniseren/", views.sync_home_assistant, name="sync_home_assistant"),
    path("entiteiten/<int:entity_id>/<str:action>/", views.control, name="control"),
    path("entiteiten/<int:entity_id>/live/start/", views.start_google_live_stream, name="start_google_live_stream"),
    path("entiteiten/<int:entity_id>/live/stop/", views.stop_google_live_stream, name="stop_google_live_stream"),
    path("entiteiten/<int:entity_id>/live/mp4/", views.google_live_mp4, name="google_live_mp4"),
    path("onderhoud/toevoegen/", views.add_maintenance, name="add_maintenance"),
    path("onderhoud/<int:item_id>/afronden/", views.complete_maintenance, name="complete_maintenance"),
    path("noodkaart/toevoegen/", views.add_emergency_contact, name="add_emergency_contact"),
    path("inrichting/ruimtes/toevoegen/", views.add_room, name="add_room"),
    path("inrichting/toevoegen/", views.add_furnishing, name="add_furnishing"),
    path("documenten/toevoegen/", views.add_document, name="add_document"),
    path("documenten/<int:document_id>/download/", views.download_document, name="download_document"),
    path("documenten/<int:document_id>/verwijderen/", views.delete_document, name="delete_document"),
    # Home Assistant custom integration API
    path("api/ha/webhook/<str:webhook_token>/", views.ha_webhook_receiver, name="ha_webhook_receiver"),
    path("api/ha/entiteiten/", views.ha_entities_list, name="ha_entities_list"),
    path("api/ha/entiteiten/<str:entity_id>/control/", views.ha_control_entity, name="ha_control_entity"),
]
