from datetime import timedelta
from os.path import basename

from django.contrib import messages
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from django.utils import timezone

from home.forms import EmergencyContactForm, FurnishingItemForm, HomeAssistantConfigForm, HouseholdDocumentForm, MaintenanceItemForm, RoomForm
from home.models import EmergencyContact, FurnishingItem, HomeActionAudit, HomeAssistantConfig, HomeEntity, HouseholdDocument, MaintenanceItem, Room
from home.services import HomeAssistantError, control_entity, save_config, sync_entities
from households.decorators import household_required, parent_required
from integrations.models import IntegrationConnection


def _tab_redirect(tab):
    return redirect(f"{reverse('home:index')}?tab={tab}")


@household_required
def index(request):
    tab = request.GET.get("tab", "apparaten")
    config = HomeAssistantConfig.objects.for_household(request.household).first()
    entities = HomeEntity.objects.for_household(request.household)
    domain = request.GET.get("domain", "alles")
    if domain != "alles":
        entities = entities.filter(domain=domain)
    maintenance = MaintenanceItem.objects.for_household(request.household)
    rooms = Room.objects.for_household(request.household)
    hue_connection = IntegrationConnection.objects.for_household(request.household).filter(provider=IntegrationConnection.Provider.HUE).first()
    return render(request, "home/index.html", {"tab": tab, "config": config, "hue_connection": hue_connection, "entities": entities, "selected_domain": domain, "domains": HomeEntity.objects.for_household(request.household).values_list("domain", flat=True).distinct().order_by("domain"), "audits": HomeActionAudit.objects.for_household(request.household).select_related("entity")[:6], "config_form": HomeAssistantConfigForm(initial={"base_url": config.base_url if config else ""}), "maintenance": maintenance, "emergency_contacts": EmergencyContact.objects.for_household(request.household), "rooms": rooms.prefetch_related("items"), "documents": HouseholdDocument.objects.for_household(request.household), "maintenance_form": MaintenanceItemForm(), "emergency_form": EmergencyContactForm(), "room_form": RoomForm(), "furnishing_form": FurnishingItemForm(), "document_form": HouseholdDocumentForm(), "metrics": [{"value": entities.filter(is_available=True).count(), "label": "beschikbaar"}, {"value": maintenance.filter(due_date__lte=timezone.localdate()).count(), "label": "onderhoud"}]})


@parent_required
@require_POST
def save_home_assistant(request):
    form = HomeAssistantConfigForm(request.POST)
    if form.is_valid():
        try:
            save_config(request.household, form.cleaned_data["base_url"], form.cleaned_data["token"])
            messages.success(request, "Home Assistant is veilig opgeslagen.")
        except HomeAssistantError as error:
            messages.error(request, str(error))
    else:
        messages.error(request, "Controleer het Home Assistant-adres.")
    return redirect("home:index")


@parent_required
@require_POST
def sync_home_assistant(request):
    try:
        messages.success(request, f"{sync_entities(request.household)} entiteiten bijgewerkt.")
    except HomeAssistantError as error:
        messages.error(request, str(error))
    return redirect("home:index")


@parent_required
@require_POST
def control(request, entity_id, action):
    entity = get_object_or_404(HomeEntity.objects.for_household(request.household), pk=entity_id)
    try:
        control_entity(request.household, entity, action, request.POST.get("target_temperature") or request.POST.get("brightness"))
        messages.success(request, f"{entity.name} bijgewerkt.")
    except HomeAssistantError as error:
        messages.error(request, str(error))
    return redirect("home:index")


@parent_required
@require_POST
def add_maintenance(request):
    form = MaintenanceItemForm(request.POST)
    if form.is_valid():
        MaintenanceItem.objects.create(household=request.household, **form.cleaned_data)
        messages.success(request, "Onderhoud toegevoegd.")
    return _tab_redirect("onderhoud")


@parent_required
@require_POST
def complete_maintenance(request, item_id):
    item = get_object_or_404(MaintenanceItem.objects.for_household(request.household), pk=item_id)
    item.last_completed_at = timezone.localdate()
    item.due_date = timezone.localdate() + timedelta(days=item.cadence_days)
    item.save(update_fields=["last_completed_at", "due_date"])
    messages.success(request, "Onderhoud afgevinkt.")
    return _tab_redirect("onderhoud")


@parent_required
@require_POST
def add_emergency_contact(request):
    form = EmergencyContactForm(request.POST)
    if form.is_valid():
        EmergencyContact.objects.create(household=request.household, **form.cleaned_data)
        messages.success(request, "Noodkaart bijgewerkt.")
    return _tab_redirect("noodkaart")


@parent_required
@require_POST
def add_room(request):
    form = RoomForm(request.POST)
    if form.is_valid():
        Room.objects.get_or_create(household=request.household, name=form.cleaned_data["name"], defaults={"icon": form.cleaned_data["icon"]})
        messages.success(request, "Ruimte toegevoegd.")
    return _tab_redirect("inrichting")


@parent_required
@require_POST
def add_furnishing(request):
    form = FurnishingItemForm(request.POST)
    if form.is_valid():
        room = Room.objects.for_household(request.household).filter(pk=request.POST.get("room")).first()
        FurnishingItem.objects.create(household=request.household, room=room, **form.cleaned_data)
        messages.success(request, "Item toegevoegd.")
    return _tab_redirect("inrichting")


@parent_required
@require_POST
def add_document(request):
    form = HouseholdDocumentForm(request.POST, request.FILES)
    if form.is_valid():
        HouseholdDocument.objects.create(household=request.household, uploaded_by=request.user, **form.cleaned_data)
        messages.success(request, "Document veilig opgeslagen.")
    else:
        messages.error(request, "Controleer het document.")
    return _tab_redirect("documenten")


@household_required
def download_document(request, document_id):
    document = get_object_or_404(HouseholdDocument.objects.for_household(request.household), pk=document_id)
    return FileResponse(document.file.open("rb"), as_attachment=True, filename=basename(document.file.name))


@parent_required
@require_POST
def delete_document(request, document_id):
    document = get_object_or_404(HouseholdDocument.objects.for_household(request.household), pk=document_id)
    document.file.delete(save=False)
    document.delete()
    messages.success(request, "Document verwijderd.")
    return _tab_redirect("documenten")
