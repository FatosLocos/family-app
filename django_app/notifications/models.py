from django.conf import settings
from django.db import models

from common.scoping import HouseholdManager
from households.models import Household


class Notification(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE)
    title = models.CharField(max_length=180)
    body = models.CharField(max_length=500, blank=True)
    kind = models.CharField(max_length=40, default="info")
    dedupe_key = models.CharField(max_length=180, null=True, blank=True)
    action_url = models.CharField(max_length=300, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = HouseholdManager()

    class Meta:
        ordering = ("-created_at",)
        constraints = [models.UniqueConstraint(fields=("household", "dedupe_key"), name="unique_household_notification_key")]
