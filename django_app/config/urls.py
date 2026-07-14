from django.contrib import admin
from django.urls import include, path

from config import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", views.today, name="today"),
    path("zoeken/", views.search, name="search"),
    path("healthz", views.healthz, name="healthz"),
    path("account/", include("identity.urls")),
    path("", include("households.urls")),
    path("gezin/", include("family.urls")),
    path("huishouden/", include("household.urls")),
    path("planning/", include("planning.urls")),
    path("geld/", include("finance.urls")),
    path("huis/", include("home.urls")),
    path("instellingen/", include("integrations.urls")),
    path("meldingen/", include("notifications.urls")),
]
