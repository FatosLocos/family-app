from datetime import timedelta

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from households.decorators import owner_required, parent_required
from households.forms import InviteForm, ChildProfileForm
from households.models import HouseholdInvite, Membership, ChildProfile
from households.code_utils import hash_invite_code, verify_invite_code


def _open_invite(code):
    code_hash = hash_invite_code(code)
    invite = get_object_or_404(HouseholdInvite, code_hash=code_hash, accepted_by__isnull=True)
    if invite.expires_at and invite.expires_at <= timezone.now():
        return None
    return invite


def accept_invite(request, code):
    invite = _open_invite(code)
    if not invite:
        messages.error(request, "Deze uitnodiging is verlopen of al gebruikt.")
        return redirect("identity:login")
    if not request.user.is_authenticated:
        request.session["pending_invite_code"] = code
        return redirect("identity:signup")
    with transaction.atomic():
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
        with transaction.atomic():
            invite, code = HouseholdInvite.create_with_code(
                household=request.household,
                created_by=request.user,
                role=form.cleaned_data["role"],
                label=form.cleaned_data["label"],
                expires_at=timezone.now() + timedelta(days=14),
            )
            request.session[f"invite_code_{invite.id}"] = code
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
        with transaction.atomic():
            membership.delete()
            messages.success(request, f"{name} is uit het huishouden verwijderd.")
    return redirect(f"{reverse('family:index')}?tab=leden")


@parent_required
@require_POST
def setup_child_profile(request, membership_id):
    membership = get_object_or_404(
        Membership.objects.select_related("user"),
        pk=membership_id,
        household=request.household,
        role=Membership.Role.CHILD
    )
    if ChildProfile.objects.filter(household=request.household, user=membership.user).exists():
        messages.info(request, "Dit kind heeft al een profiel.")
        return redirect(f"{reverse('family:index')}?tab=leden")

    form = ChildProfileForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            profile = form.save(commit=False)
            profile.household = request.household
            profile.user = membership.user
            profile.save()
            messages.success(request, f"Profiel gemaakt voor {membership.user.display_name or membership.user.get_full_name()}.")
        return redirect(f"{reverse('family:index')}?tab=leden")

    return redirect(f"{reverse('family:index')}?tab=leden")
