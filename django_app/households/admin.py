from django.contrib import admin

from households.models import Household, HouseholdInvite, Membership

admin.site.register((Household, Membership, HouseholdInvite))
