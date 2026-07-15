from django.urls import path

from finance import views

app_name = "finance"
urlpatterns = [
    path("", views.index, name="index"),
    path("abn/importeren/", views.import_abn, name="import_abn"),
    path("budgetten/toevoegen/", views.add_budget, name="add_budget"),
    path("budgetten/<int:budget_id>/aanpassen/", views.update_budget, name="update_budget"),
    path("budgetten/<int:budget_id>/verwijderen/", views.delete_budget, name="delete_budget"),
    path("terugkerend/<int:rule_id>/aanpassen/", views.update_recurring_rule, name="update_recurring_rule"),
    path("transacties/<int:transaction_id>/terugkerend/", views.set_recurring_override, name="set_recurring_override"),
    path("transacties/<int:transaction_id>/categorie/", views.update_transaction_category, name="update_transaction_category"),
]
