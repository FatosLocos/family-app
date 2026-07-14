from django.contrib import admin

from household.models import MealPlan, Routine, ShoppingItem, ShoppingList, Task

admin.site.register((Task, ShoppingList, ShoppingItem, MealPlan, Routine))
