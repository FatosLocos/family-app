from django.contrib import admin

from household.models import MealPlan, Routine, ShoppingItem, ShoppingList, Task, TaskList, WeatherPreference, WeatherData

admin.site.register((Task, TaskList, ShoppingList, ShoppingItem, MealPlan, Routine, WeatherPreference, WeatherData))
