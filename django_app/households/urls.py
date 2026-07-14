from django.urls import path

from households import views

app_name = "households"
urlpatterns = [
    path("uitnodiging/<str:code>/", views.accept_invite, name="accept_invite"),
    path("uitnodigingen/maken/", views.create_invite, name="create_invite"),
    path("leden/<int:membership_id>/rol/", views.update_member_role, name="update_member_role"),
    path("leden/<int:membership_id>/verwijderen/", views.remove_member, name="remove_member"),
]
