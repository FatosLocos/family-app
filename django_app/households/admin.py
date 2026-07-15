from django.contrib import admin

from households.models import Household, HouseholdInvite, Membership, ChildProfile

admin.site.register((Household, Membership, HouseholdInvite, ChildProfile))
