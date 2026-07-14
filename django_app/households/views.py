from datetime import timedelta

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from households.decorators import owner_required, parent_required
from households.forms import InviteForm
from households.models import HouseholdInvite, Membership


def _open_invite(code):
    invite = get_object_or_404(HouseholdInvite, code=code, accepted_by__isnull=True)
    if invite.expires_at and invite.expires_at <= timezone.now():
        return None
    return invite


def accept_invite(request, code):
    invite = _open_invite(code)
    if not invite:
        messages.error(request, "Deze uitnodiging is verlopen of al gebruikt.")
        return redirect("identity:login")
    if not request.user.is_authenticated:
        request.session["pending_invite_code"] = invite.code
        return redirect("identity:signup")
    membership, created = Membership.objects.get_or_create(household=invite.household, user=request.user, defaults={"role": invite.role})
    if created:
        invite.accepted_by = request.user
        invite.save(update_fields=["accepted_by"])
        request.session["active_household_id"] = invite.household_id
        messages.success(request, f"Je bent toegevoegd aan {invite.household.name}.")
    else:
        messages.info(request, "Je bent al lid van dit huishouden.")
    return redirect("today")


@parent_required
@require_POST
def create_invite(request):
    form = InviteForm(request.POST)
    if form.is_valid():
        HouseholdInvite.objects.create(
            household=request.household,
            created_by=request.user,
            role=form.cleaned_data["role"],
            label=form.cleaned_data["label"],
            expires_at=timezone.now() + timedelta(days=14),
        )
        messages.success(request, "Uitnodiging gemaakt. Deel de link vanuit het overzicht.")
    return redirect(f"{reverse('family:index')}?tab=leden")


@owner_required
@require_POST
def update_member_role(request, membership_id):
    membership = get_object_or_404(Membership.objects.select_related("user"), pk=membership_id, household=request.household)
    role = request.POST.get("role")
    if membership.role == Membership.Role.OWNER:
        messages.error(request, "De eigenaarrol kan niet vanuit dit scherm worden gewijzigd.")
    elif role in {Membership.Role.PARENT, Membership.Role.CHILD}:
        membership.role = role
        membership.save(update_fields=["role"])
        messages.success(request, f"Rol van {membership.user} bijgewerkt.")
    return redirect(f"{reverse('family:index')}?tab=leden")


@owner_required
@require_POST
def remove_member(request, membership_id):
    membership = get_object_or_404(Membership.objects.select_related("user"), pk=membership_id, household=request.household)
    if membership.role == Membership.Role.OWNER:
        messages.error(request, "De eigenaar kan niet worden verwijderd.")
    else:
        name = str(membership.user)
        membership.delete()
        messages.success(request, f"{name} is uit het huishouden verwijderd.")
    return redirect(f"{reverse('family:index')}?tab=leden")
