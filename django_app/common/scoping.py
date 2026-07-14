from django.db import models


class HouseholdQuerySet(models.QuerySet):
    def for_household(self, household):
        return self.filter(household=household)


HouseholdManager = models.Manager.from_queryset(HouseholdQuerySet)
