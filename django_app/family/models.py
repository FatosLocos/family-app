import secrets

from django.conf import settings
from django.db import models

from common.scoping import HouseholdManager
from households.models import Household


class FamilyRecord(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = HouseholdManager()

    class Meta:
        abstract = True


class Contact(FamilyRecord):
    class Type(models.TextChoices):
        PERSON = "person", "Persoon"
        FAMILY = "family", "Familie"
        ORGANISATION = "organisation", "Organisatie"

    name = models.CharField(max_length=200)
    contact_type = models.CharField(max_length=20, choices=Type.choices, default=Type.PERSON)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    address = models.CharField(max_length=240, blank=True)
    postal_code = models.CharField(max_length=24, blank=True)
    city = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("name",)


class ContactPerson(FamilyRecord):
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="people")
    name = models.CharField(max_length=160)
    birth_date = models.DateField(null=True, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ("name",)


class WishList(FamilyRecord):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="wishlists")
    title = models.CharField(max_length=160)
    is_shared = models.BooleanField(default=False)
    share_token = models.CharField(max_length=48, null=True, blank=True, unique=True)


class WishItem(FamilyRecord):
    wishlist = models.ForeignKey(WishList, on_delete=models.CASCADE, related_name="items")
    title = models.CharField(max_length=240)
    url = models.URLField(blank=True)
    image_url = models.URLField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    category = models.CharField(max_length=80, blank=True)
    repeatable = models.BooleanField(default=False)
    reserved_by = models.CharField(max_length=160, blank=True)


class WishReservation(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE)
    item = models.ForeignKey(WishItem, on_delete=models.CASCADE, related_name="reservations")
    name = models.CharField(max_length=160)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = HouseholdManager()


class BulletinPost(FamilyRecord):
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    body = models.TextField(max_length=1000)
    pinned = models.BooleanField(default=False)

    class Meta:
        ordering = ("-pinned", "-created_at")
