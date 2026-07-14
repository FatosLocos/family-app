from django.contrib import admin

from family.models import BulletinPost, Contact, ContactPerson, WishItem, WishList, WishReservation

admin.site.register((Contact, ContactPerson, WishList, WishItem, WishReservation, BulletinPost))
