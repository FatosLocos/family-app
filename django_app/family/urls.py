from django.urls import path

from family import views

app_name = "family"
urlpatterns = [
    path("", views.index, name="index"),
    path("contacten/toevoegen/", views.add_contact, name="add_contact"),
    path("contacten/<int:contact_id>/aanpassen/", views.update_contact, name="update_contact"),
    path("contacten/<int:contact_id>/verwijderen/", views.delete_contact, name="delete_contact"),
    path("contacten/importeren/", views.import_contacts, name="import_contacts"),
    path("contacten/exporteren/", views.export_contacts, name="export_contacts"),
    path("contacten/<int:contact_id>/personen/toevoegen/", views.add_person, name="add_person"),
    path("personen/<int:person_id>/aanpassen/", views.update_person, name="update_person"),
    path("personen/<int:person_id>/verwijderen/", views.delete_person, name="delete_person"),
    path("wensen/toevoegen/", views.add_wish, name="add_wish"),
    path("wensen/<int:item_id>/aanpassen/", views.update_wish, name="update_wish"),
    path("wensen/<int:item_id>/verwijderen/", views.delete_wish, name="delete_wish"),
    path("wensen/<int:wishlist_id>/delen/", views.toggle_wishlist_share, name="toggle_wishlist_share"),
    path("wensen/publiek/<str:token>/", views.public_wishlist, name="public_wishlist"),
    path("wensen/publiek/<str:token>/items/<int:item_id>/reserveren/", views.reserve_wish, name="reserve_wish"),
    path("prikbord/toevoegen/", views.add_post, name="add_post"),
    path("prikbord/<int:post_id>/verwijderen/", views.delete_post, name="delete_post"),
]
