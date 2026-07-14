from django.urls import path

from notifications import views

app_name = "notifications"
urlpatterns = [path("<int:notification_id>/gelezen/", views.mark_read, name="mark_read")]
