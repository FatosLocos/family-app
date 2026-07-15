from django.contrib.auth.views import PasswordResetDoneView, PasswordResetCompleteView
from django.urls import path

from identity import views

app_name = "identity"
urlpatterns = [
    path("login/", views.LocalLoginView.as_view(), name="login"),
    path("logout/", views.LocalLogoutView.as_view(), name="logout"),
    path("signup/", views.signup, name="signup"),
    path("password-reset/", views.LocalPasswordResetView.as_view(), name="password_reset"),
    path("password-reset/done/", PasswordResetDoneView.as_view(template_name="identity/password_reset_done.html"), name="password_reset_done"),
    path("reset/<uidb64>/<token>/", views.LocalPasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("reset/done/", PasswordResetCompleteView.as_view(template_name="identity/password_reset_complete.html"), name="password_reset_complete"),
]
