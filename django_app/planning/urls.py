from django.urls import path

from planning import views

app_name = "planning"
urlpatterns = [
    path("", views.index, name="index"),
    path("toevoegen/", views.add_event, name="add_event"),
    path("afspraken/<int:event_id>/aanpassen/", views.update_event, name="update_event"),
    path("afspraken/<int:event_id>/verwijderen/", views.delete_event, name="delete_event"),
    path("ics/toevoegen/", views.add_ics_subscription, name="add_ics_subscription"),
    path("ics/importeren/", views.import_ics_file, name="import_ics_file"),
    path("bronnen/<int:source_id>/schakelen/", views.toggle_source, name="toggle_source"),
    path("bronnen/<int:source_id>/verwijderen/", views.remove_source, name="remove_source"),
]
