from django.contrib import admin

from planning.models import CalendarEvent, CalendarSource, EventGuest, EventInvite, EventProgramItem, EventQuestion, EventVenue, IcsSubscription

admin.site.register((CalendarSource, CalendarEvent, IcsSubscription, EventVenue, EventInvite, EventProgramItem, EventQuestion, EventGuest))
