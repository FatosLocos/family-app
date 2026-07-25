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
    path("bronnen/<int:source_id>/terugsturen/", views.toggle_source_write_back, name="toggle_source_write_back"),
    path("bronnen/<int:source_id>/verwijderen/", views.remove_source, name="remove_source"),
    path("locaties/toevoegen/", views.add_event_venue, name="add_event_venue"),
    path("locaties/<int:venue_id>/aanpassen/", views.update_event_venue, name="update_event_venue"),
    path("locaties/<int:venue_id>/verwijderen/", views.delete_event_venue, name="delete_event_venue"),
    path("afspraken/<int:event_id>/uitnodiging/", views.update_event_invite, name="update_event_invite"),
    path("afspraken/<int:event_id>/uitnodiging/delen/", views.toggle_event_share, name="toggle_event_share"),
    path("afspraken/<int:event_id>/uitnodiging/programma/toevoegen/", views.add_event_program_item, name="add_event_program_item"),
    path("afspraken/<int:event_id>/uitnodiging/vragen/toevoegen/", views.add_event_question, name="add_event_question"),
    path("uitnodiging/programma/<int:item_id>/verwijderen/", views.delete_event_program_item, name="delete_event_program_item"),
    path("uitnodiging/vragen/<int:question_id>/verwijderen/", views.delete_event_question, name="delete_event_question"),
    path("uitnodiging/publiek/<str:token>/", views.public_event_invite, name="public_event_invite"),
    path("uitnodiging/publiek/<str:token>/aanmelden/", views.rsvp_event, name="rsvp_event"),
]
