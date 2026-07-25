from django.urls import path

from travel import views

app_name = "travel"
urlpatterns = [
    path("", views.index, name="index"),
    path("toevoegen/", views.add_trip, name="add_trip"),
    path("<int:trip_id>/aanpassen/", views.update_trip, name="update_trip"),
    path("<int:trip_id>/verwijderen/", views.delete_trip, name="delete_trip"),
    path("<int:trip_id>/takenlijst/koppelen/", views.link_task_list, name="link_task_list"),
    path("<int:trip_id>/tussenstops/toevoegen/", views.add_stop, name="add_stop"),
    path("tussenstops/<int:stop_id>/verwijderen/", views.delete_stop, name="delete_stop"),
    path("<int:trip_id>/documenten/toevoegen/", views.add_document, name="add_document"),
    path("documenten/<int:document_id>/downloaden/", views.download_document, name="download_document"),
    path("documenten/<int:document_id>/verwijderen/", views.delete_document, name="delete_document"),
    path("<int:trip_id>/ideeen/toevoegen/", views.add_idea, name="add_idea"),
    path("ideeen/<int:idea_id>/verwijderen/", views.delete_idea, name="delete_idea"),
]
