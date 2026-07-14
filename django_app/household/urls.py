from django.urls import path

from household import views

app_name = "household"
urlpatterns = [
    path("", views.index, name="index"),
    path("taken/toevoegen/", views.add_task, name="add_task"),
    path("taken/<int:task_id>/toggle/", views.toggle_task, name="toggle_task"),
    path("taken/<int:task_id>/aanpassen/", views.update_task, name="update_task"),
    path("taken/<int:task_id>/verwijderen/", views.delete_task, name="delete_task"),
    path("boodschappen/toevoegen/", views.add_shopping_item, name="add_shopping_item"),
    path("boodschappen/<int:item_id>/toggle/", views.toggle_shopping_item, name="toggle_shopping_item"),
    path("boodschappen/<int:item_id>/aanpassen/", views.update_shopping_item, name="update_shopping_item"),
    path("boodschappen/<int:item_id>/verwijderen/", views.delete_shopping_item, name="delete_shopping_item"),
    path("boodschappen/<int:item_id>/prijs/", views.save_shopping_price, name="save_shopping_price"),
    path("boodschappen/bonnen/toevoegen/", views.add_receipt, name="add_receipt"),
    path("maaltijden/toevoegen/", views.add_meal, name="add_meal"),
    path("maaltijden/<int:meal_id>/aanpassen/", views.update_meal, name="update_meal"),
    path("maaltijden/<int:meal_id>/verwijderen/", views.delete_meal, name="delete_meal"),
    path("routines/toevoegen/", views.add_routine, name="add_routine"),
    path("routines/<int:routine_id>/aanpassen/", views.update_routine, name="update_routine"),
    path("routines/<int:routine_id>/verwijderen/", views.delete_routine, name="delete_routine"),
]
