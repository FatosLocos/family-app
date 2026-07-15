from django.urls import path

from identity import views

app_name = "identity"
urlpatterns = [
    path("login/", views.LocalLoginView.as_view(), name="login"),
    path("logout/", views.LocalLogoutView.as_view(), name="logout"),
    path("signup/", views.signup, name="signup"),
    path("reset/<uidb64>/<token>/", views.LocalPasswordResetConfirmView.as_view(), name="password_reset_confirm"),
]
