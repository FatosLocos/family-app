from django.contrib import admin

from travel.models import Trip, TripDocument, TripIdea, TripStop

admin.site.register((Trip, TripStop, TripDocument, TripIdea))
