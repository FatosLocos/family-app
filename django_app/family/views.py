from datetime import date

from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
import secrets
from urllib.parse import urlencode
from django.views.decorators.http import require_POST

from family.forms import BulletinPostForm, ContactForm, ContactPersonForm, VCardImportForm, WishItemForm
from family.models import BulletinPost, Contact, ContactPerson, WishItem, WishList
from family.vcard import contacts_as_vcard, parse_vcards
from households.decorators import household_required, parent_required
from households.forms import InviteForm
from households.models import HouseholdInvite, Membership


@household_required
def index(request):
    household = request.household
    tab = request.GET.get("tab", "contacten")
    query = request.GET.get("q", "").strip()
    contacts = Contact.objects.for_household(household).prefetch_related("people")
    if query:
        contacts = contacts.filter(Q(name__icontains=query) | Q(people__name__icontains=query)).distinct()
    birthdays = ContactPerson.objects.for_household(household).filter(birth_date__isnull=False).order_by("birth_date")
    memberships = Membership.objects.filter(household=household).select_related("user").order_by("role", "user__display_name", "user__email")
    wishlist_owner = request.user
    requested_owner = request.GET.get("wishlist_for")
    if requested_owner:
        candidate = memberships.filter(user_id=requested_owner).first()
        if candidate and (candidate.user_id == request.user.id or request.membership.can_manage):
            wishlist_owner = candidate.user
    wishlist, _ = WishList.objects.get_or_create(household=household, owner=wishlist_owner, defaults={"title": f"Wensen van {wishlist_owner.display_name or wishlist_owner.first_name or wishlist_owner.email}"})
    invites = HouseholdInvite.objects.filter(household=household, accepted_by__isnull=True).order_by("-created_at")
    for invite in invites:
        invite.share_url = request.build_absolute_uri(reverse("households:accept_invite", args=[invite.code]))
    public_url = request.build_absolute_uri(reverse("family:public_wishlist", args=[wishlist.share_token])) if wishlist.is_shared and wishlist.share_token else ""
    return render(request, "family/index.html", {
        "tab": tab, "query": query, "contacts": contacts, "birthdays": birthdays,
        "wishlist": wishlist, "wishlist_owner": wishlist_owner, "public_url": public_url, "wish_items": wishlist.items.prefetch_related("reservations"), "posts": BulletinPost.objects.for_household(household)[:12],
        "memberships": memberships, "invites": invites,
        "contact_form": ContactForm(), "person_form": ContactPersonForm(), "wish_form": WishItemForm(), "post_form": BulletinPostForm(), "invite_form": InviteForm(),
        "vcard_import_form": VCardImportForm(),
    })


@parent_required
@require_POST
def add_contact(request):
    form = ContactForm(request.POST)
    if form.is_valid():
        contact = form.save(commit=False)
        contact.household = request.household
        contact.save()
        messages.success(request, "Contact toegevoegd.")
    return redirect("family:index")


def _family_tab_redirect(tab: str, **params):
    query = {"tab": tab, **{key: value for key, value in params.items() if value not in (None, "")}}
    return redirect(f"{reverse('family:index')}?{urlencode(query)}")


@parent_required
@require_POST
def update_contact(request, contact_id):
    contact = get_object_or_404(Contact.objects.for_household(request.household), pk=contact_id)
    form = ContactForm(request.POST, instance=contact)
    if form.is_valid():
        form.save()
        messages.success(request, "Contact aangepast.")
    else:
        messages.error(request, "Controleer de contactvelden.")
    return _family_tab_redirect("contacten")


@parent_required
@require_POST
def delete_contact(request, contact_id):
    contact = get_object_or_404(Contact.objects.for_household(request.household), pk=contact_id)
    contact.delete()
    messages.success(request, "Contact verwijderd.")
    return _family_tab_redirect("contacten")


@parent_required
@require_POST
def import_contacts(request):
    contacts_url = f"{reverse('family:index')}?tab=contacten"
    form = VCardImportForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Kies een geldig vCard-bestand.")
        return redirect(contacts_url)
    uploaded = form.cleaned_data["file"]
    if uploaded.size > 2_000_000 or not uploaded.name.lower().endswith(".vcf"):
        messages.error(request, "Gebruik een .vcf-bestand kleiner dan 2 MB.")
        return redirect(contacts_url)
    cards = parse_vcards(uploaded.read())
    imported = 0
    for card in cards:
        contact = Contact.objects.for_household(request.household).filter(name=card["name"], email=card["email"]).first()
        if not contact:
            contact = Contact.objects.create(household=request.household, contact_type=Contact.Type.PERSON, **{key: card[key] for key in ("name", "email", "phone", "address", "postal_code", "city", "notes")})
            imported += 1
        if card["birth_date"]:
            ContactPerson.objects.update_or_create(household=request.household, contact=contact, name=card["name"], defaults={"birth_date": card["birth_date"], "email": card["email"], "phone": card["phone"]})
    messages.success(request, f"{imported} contacten geïmporteerd." if imported else "Geen nieuwe contacten gevonden.")
    return redirect(contacts_url)


@parent_required
def export_contacts(request):
    contacts = Contact.objects.for_household(request.household).prefetch_related("people").order_by("name")
    response = HttpResponse(contacts_as_vcard(contacts), content_type="text/vcard; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="family-app-adresboek.vcf"'
    return response


@parent_required
@require_POST
def add_person(request, contact_id):
    contact = get_object_or_404(Contact.objects.for_household(request.household), pk=contact_id)
    form = ContactPersonForm(request.POST)
    if form.is_valid():
        person = form.save(commit=False)
        person.household = request.household
        person.contact = contact
        person.save()
        messages.success(request, "Persoon toegevoegd aan de familie.")
    return _family_tab_redirect("contacten")


@parent_required
@require_POST
def update_person(request, person_id):
    person = get_object_or_404(ContactPerson.objects.for_household(request.household), pk=person_id)
    form = ContactPersonForm(request.POST, instance=person)
    if form.is_valid():
        form.save()
        messages.success(request, "Persoon aangepast.")
    else:
        messages.error(request, "Controleer de persoonsgegevens.")
    return _family_tab_redirect("contacten")


@parent_required
@require_POST
def delete_person(request, person_id):
    person = get_object_or_404(ContactPerson.objects.for_household(request.household), pk=person_id)
    person.delete()
    messages.success(request, "Persoon verwijderd uit deze familie.")
    return _family_tab_redirect("contacten")


@household_required
@require_POST
def add_wish(request):
    owner = request.user
    owner_id = request.POST.get("owner_id")
    if owner_id and owner_id != str(request.user.id):
        membership = Membership.objects.filter(household=request.household, user_id=owner_id).select_related("user").first()
        if not membership or not request.membership.can_manage:
            messages.error(request, "Alleen ouders kunnen wensen voor iemand anders toevoegen.")
            return redirect(f"{reverse('family:index')}?tab=wensen")
        owner = membership.user
    wishlist, _ = WishList.objects.get_or_create(household=request.household, owner=owner, defaults={"title": f"Wensen van {owner.display_name or owner.email}"})
    form = WishItemForm(request.POST)
    if form.is_valid():
        item = form.save(commit=False)
        item.household = request.household
        item.wishlist = wishlist
        item.save()
        messages.success(request, "Wens toegevoegd.")
    return redirect(f"{reverse('family:index')}?tab=wensen&wishlist_for={owner.id}")


def _can_manage_wishlist(request, wishlist):
    return wishlist.owner_id == request.user.id or request.membership.can_manage


@household_required
@require_POST
def update_wish(request, item_id):
    item = get_object_or_404(WishItem.objects.for_household(request.household).select_related("wishlist"), pk=item_id)
    if not _can_manage_wishlist(request, item.wishlist):
        return HttpResponse(status=403)
    form = WishItemForm(request.POST, instance=item)
    if form.is_valid():
        form.save()
        messages.success(request, "Wens aangepast.")
    else:
        messages.error(request, "Controleer de wensvelden.")
    return _family_tab_redirect("wensen", wishlist_for=item.wishlist.owner_id)


@household_required
@require_POST
def delete_wish(request, item_id):
    item = get_object_or_404(WishItem.objects.for_household(request.household).select_related("wishlist"), pk=item_id)
    if not _can_manage_wishlist(request, item.wishlist):
        return HttpResponse(status=403)
    owner_id = item.wishlist.owner_id
    item.delete()
    messages.success(request, "Wens verwijderd.")
    return _family_tab_redirect("wensen", wishlist_for=owner_id)


@household_required
@require_POST
def add_post(request):
    form = BulletinPostForm(request.POST)
    if form.is_valid():
        post = form.save(commit=False)
        post.household = request.household
        post.author = request.user
        post.save()
    return redirect(f"{reverse('family:index')}?tab=prikbord")


@household_required
@require_POST
def delete_post(request, post_id):
    post = get_object_or_404(BulletinPost.objects.for_household(request.household), pk=post_id)
    if post.author_id != request.user.id and not request.membership.can_manage:
        return HttpResponse(status=403)
    post.delete()
    messages.success(request, "Bericht verwijderd.")
    return _family_tab_redirect("prikbord")


@household_required
@require_POST
def toggle_wishlist_share(request, wishlist_id):
    wishlist = get_object_or_404(WishList.objects.for_household(request.household), pk=wishlist_id)
    if wishlist.owner_id != request.user.id and not request.membership.can_manage:
        messages.error(request, "Je kunt alleen je eigen wishlist delen.")
        return redirect(f"{reverse('family:index')}?tab=wensen")
    wishlist.is_shared = not wishlist.is_shared
    if wishlist.is_shared and not wishlist.share_token:
        wishlist.share_token = secrets.token_urlsafe(24)
    wishlist.save(update_fields=["is_shared", "share_token", "updated_at"])
    messages.success(request, "Externe wishlist-link geactiveerd." if wishlist.is_shared else "Externe wishlist-link uitgeschakeld.")
    return redirect(f"{reverse('family:index')}?tab=wensen&wishlist_for={wishlist.owner_id}")


def public_wishlist(request, token):
    wishlist = get_object_or_404(WishList.objects.filter(is_shared=True), share_token=token)
    return render(request, "family/public_wishlist.html", {"wishlist": wishlist, "items": wishlist.items.prefetch_related("reservations")})


@require_POST
def reserve_wish(request, token, item_id):
    wishlist = get_object_or_404(WishList.objects.filter(is_shared=True), share_token=token)
    item = get_object_or_404(WishItem.objects.filter(wishlist=wishlist), pk=item_id)
    name = request.POST.get("name", "").strip()[:160]
    if not name:
        messages.error(request, "Vul je naam in om deze wens te reserveren.")
    elif not item.repeatable and item.reservations.exists():
        messages.error(request, "Deze wens is al gereserveerd.")
    else:
        item.reservations.create(household=wishlist.household, name=name)
        messages.success(request, "Wens gereserveerd. Bedankt!")
    return redirect("family:public_wishlist", token=token)
