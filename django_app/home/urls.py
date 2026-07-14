from django.urls import path

from home import views

app_name = "home"
urlpatterns = [
    path("", views.index, name="index"),
    path("home-assistant/opslaan/", views.save_home_assistant, name="save_home_assistant"),
    path("home-assistant/synchroniseren/", views.sync_home_assistant, name="sync_home_assistant"),
    path("entiteiten/<int:entity_id>/<str:action>/", views.control, name="control"),
    path("onderhoud/toevoegen/", views.add_maintenance, name="add_maintenance"),
    path("onderhoud/<int:item_id>/afronden/", views.complete_maintenance, name="complete_maintenance"),
    path("noodkaart/toevoegen/", views.add_emergency_contact, name="add_emergency_contact"),
    path("inrichting/ruimtes/toevoegen/", views.add_room, name="add_room"),
    path("inrichting/toevoegen/", views.add_furnishing, name="add_furnishing"),
    path("documenten/toevoegen/", views.add_document, name="add_document"),
    path("documenten/<int:document_id>/download/", views.download_document, name="download_document"),
    path("documenten/<int:document_id>/verwijderen/", views.delete_document, name="delete_document"),
]
