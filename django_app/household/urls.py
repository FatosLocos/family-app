from django.urls import path

from household import views

app_name = "household"
urlpatterns = [
    path("", views.index, name="index"),
    path("taken/toevoegen/", views.add_task, name="add_task"),
    path("taken/<int:task_id>/toggle/", views.toggle_task, name="toggle_task"),
    path("taken/<int:task_id>/aanpassen/", views.update_task, name="update_task"),
    path("taken/<int:task_id>/verwijderen/", views.delete_task, name="delete_task"),
    path("taken/lijstjes/toevoegen/", views.add_task_list, name="add_task_list"),
    path("taken/lijstjes/<int:list_id>/verwijderen/", views.delete_task_list, name="delete_task_list"),
    path("taken/herschikken/", views.reorder_tasks, name="reorder_tasks"),
    path("boodschappen/toevoegen/", views.add_shopping_item, name="add_shopping_item"),
    path("boodschappen/<int:item_id>/toggle/", views.toggle_shopping_item, name="toggle_shopping_item"),
    path("boodschappen/<int:item_id>/aanpassen/", views.update_shopping_item, name="update_shopping_item"),
    path("boodschappen/<int:item_id>/verwijderen/", views.delete_shopping_item, name="delete_shopping_item"),
    path("boodschappen/<int:item_id>/prijs/", views.save_shopping_price, name="save_shopping_price"),
    path("boodschappen/prijzen/verversen/", views.refresh_prices, name="refresh_prices"),
    path("boodschappen/bonnen/toevoegen/", views.add_receipt, name="add_receipt"),
    path("maaltijden/toevoegen/", views.add_meal, name="add_meal"),
    path("maaltijden/<int:meal_id>/aanpassen/", views.update_meal, name="update_meal"),
    path("maaltijden/<int:meal_id>/verwijderen/", views.delete_meal, name="delete_meal"),
    path("maaltijden/<int:meal_id>/ingredienten/toevoegen/", views.add_meal_ingredient, name="add_meal_ingredient"),
    path("maaltijden/<int:meal_id>/naar-boodschappen/", views.add_meal_ingredients_to_shopping_list, name="add_meal_ingredients_to_shopping_list"),
    path("maaltijden/ingredienten/<int:ingredient_id>/verwijderen/", views.delete_meal_ingredient, name="delete_meal_ingredient"),
    path("voorraad/toevoegen/", views.add_pantry_item, name="add_pantry_item"),
    path("voorraad/<int:item_id>/aanpassen/", views.update_pantry_item, name="update_pantry_item"),
    path("voorraad/<int:item_id>/bijwerken/", views.adjust_pantry_item, name="adjust_pantry_item"),
    path("voorraad/<int:item_id>/naar-boodschappen/", views.add_pantry_item_to_shopping_list, name="add_pantry_item_to_shopping_list"),
    path("voorraad/<int:item_id>/verwijderen/", views.delete_pantry_item, name="delete_pantry_item"),
    path("routines/toevoegen/", views.add_routine, name="add_routine"),
    path("routines/<int:routine_id>/afronden/", views.complete_routine, name="complete_routine"),
    path("routines/<int:routine_id>/aanpassen/", views.update_routine, name="update_routine"),
    path("routines/<int:routine_id>/verwijderen/", views.delete_routine, name="delete_routine"),
]
