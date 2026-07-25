from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from common.scoping import HouseholdManager
from households.models import Household


class TravelRecord(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = HouseholdManager()

    class Meta:
        abstract = True


def trip_document_path(instance, filename):
    return f"trips/{instance.household_id}/{uuid4().hex}{Path(filename).suffix.lower()}"


class Trip(TravelRecord):
    destination = models.CharField(max_length=160)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    # The trip's own list in the normal Taken tab (packing list, preparation tasks), so
    # trip tasks ride along with the existing TaskList/Task infrastructure instead of a
    # second task system. SET_NULL: deleting the list must not delete the trip.
    task_list = models.OneToOneField("household.TaskList", null=True, blank=True, on_delete=models.SET_NULL, related_name="trip")

    class Meta:
        ordering = ("start_date", "id")

    def __str__(self):
        return self.destination


class TripStop(TravelRecord):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="stops")
    name = models.CharField(max_length=160)
    arrives_on = models.DateField(null=True, blank=True)
    departs_on = models.DateField(null=True, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "arrives_on", "id")

    def __str__(self):
        return self.name


class TripDocument(TravelRecord):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="documents")
    title = models.CharField(max_length=180)
    file = models.FileField(upload_to=trip_document_path, blank=True)
    dropbox_path = models.CharField(max_length=500, blank=True)
    url = models.URLField(max_length=500, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="trip_documents")

    class Meta:
        ordering = ("-created_at", "id")

    def __str__(self):
        return self.title

    def clean(self):
        """A document lives in exactly one place: uploaded here, in Dropbox, or behind a link."""
        filled = [bool(self.file), bool((self.dropbox_path or "").strip()), bool((self.url or "").strip())]
        if sum(filled) != 1:
            raise ValidationError("Kies precies één bron: een bestand, een Dropbox-pad of een link.")


class TripIdea(TravelRecord):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="ideas")
    text = models.TextField()
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="trip_ideas")
    created_by_agent = models.BooleanField(default=False)

    class Meta:
        ordering = ("created_at", "id")

    def __str__(self):
        return self.text[:60]
