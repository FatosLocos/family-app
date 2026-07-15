from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView, PasswordResetConfirmView, PasswordResetView
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone

from households.models import Household, HouseholdInvite, Membership
from identity.forms import LoginForm, SignUpForm


class LocalLoginView(LoginView):
    authentication_form = LoginForm
    template_name = "identity/login.html"


class LocalLogoutView(LogoutView):
    pass


class LocalPasswordResetView(PasswordResetView):
    template_name = "identity/password_reset.html"
    email_template_name = "identity/password_reset_email.html"
    subject_template_name = "identity/password_reset_subject.txt"
    success_url = reverse_lazy("identity:password_reset_done")


class LocalPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "identity/password_reset_confirm.html"
    success_url = reverse_lazy("identity:login")


def signup(request):
    if request.user.is_authenticated:
        return redirect("today")

    invite_code = request.session.get("pending_invite_code", "")
    pending_invite = HouseholdInvite.objects.filter(code=invite_code, accepted_by__isnull=True).select_related("household").first()
    if pending_invite and pending_invite.expires_at and pending_invite.expires_at <= timezone.now():
        request.session.pop("pending_invite_code", None)
        pending_invite = None

    if settings.INVITE_ONLY_MODE and not pending_invite:
        return render(request, "identity/signup_closed.html")

    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user = form.save()
            if pending_invite and (not pending_invite.expires_at or pending_invite.expires_at > timezone.now()):
                household = pending_invite.household
                Membership.objects.create(household=household, user=user, role=pending_invite.role)
                pending_invite.accepted_by = user
                pending_invite.save(update_fields=["accepted_by"])
                request.session.pop("pending_invite_code", None)
            else:
                if settings.INVITE_ONLY_MODE:
                    return render(request, "identity/signup_closed.html")
                household_name = request.POST.get("household_name", "").strip() or f"Gezin {user.display_name}"
                household = Household.objects.create(name=household_name)
                Membership.objects.create(household=household, user=user, role=Membership.Role.OWNER)
            login(request, user)
            request.session["active_household_id"] = household.pk
        return redirect("today")
    return render(request, "identity/signup.html", {"form": form, "pending_invite": pending_invite})
