from django.db import models
from django.conf import settings


class HouseholdOwnedModel(models.Model):
    """Base model for entities owned by a household with automatic RLS scoping."""

    household = models.ForeignKey("households.Household", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["household", "created_at"]),
            models.Index(fields=["household", "updated_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.household_id})"
