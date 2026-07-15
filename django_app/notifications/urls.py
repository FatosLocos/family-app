from django.urls import path

from notifications import views

app_name = "notifications"
urlpatterns = [
    path("", views.index, name="index"),
    path("alles-gelezen/", views.mark_all_read, name="mark_all_read"),
    path("<int:notification_id>/gelezen/", views.mark_read, name="mark_read"),
    path("push/abonneer/", views.subscribe_push, name="subscribe_push"),
    path("push/afmelden/", views.unsubscribe_push, name="unsubscribe_push"),
]
