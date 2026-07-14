from django.contrib import admin

from planning.models import CalendarEvent, CalendarSource, IcsSubscription

admin.site.register((CalendarSource, CalendarEvent, IcsSubscription))
