from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect, render
from django.utils import timezone

from households.models import Household, HouseholdInvite, Membership
from identity.forms import LoginForm, SignUpForm


class LocalLoginView(LoginView):
    authentication_form = LoginForm
    template_name = "identity/login.html"


class LocalLogoutView(LogoutView):
    pass


def signup(request):
    if request.user.is_authenticated:
        return redirect("today")
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        invite_code = request.session.pop("pending_invite_code", "")
        invite = HouseholdInvite.objects.filter(code=invite_code, accepted_by__isnull=True).select_related("household").first()
        if invite and (not invite.expires_at or invite.expires_at > timezone.now()):
            household = invite.household
            Membership.objects.create(household=household, user=user, role=invite.role)
            invite.accepted_by = user
            invite.save(update_fields=["accepted_by"])
        else:
            household_name = request.POST.get("household_name", "").strip() or f"Gezin {user.display_name}"
            household = Household.objects.create(name=household_name)
            Membership.objects.create(household=household, user=user, role=Membership.Role.OWNER)
        login(request, user)
        request.session["active_household_id"] = household.pk
        return redirect("today")
    invite_code = request.session.get("pending_invite_code", "")
    pending_invite = HouseholdInvite.objects.filter(code=invite_code, accepted_by__isnull=True).select_related("household").first()
    if pending_invite and pending_invite.expires_at and pending_invite.expires_at <= timezone.now():
        request.session.pop("pending_invite_code", None)
        pending_invite = None
    return render(request, "identity/signup.html", {"form": form, "pending_invite": pending_invite})
