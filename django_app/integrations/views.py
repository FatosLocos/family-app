import json

from django.contrib import messages
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from households.decorators import household_required, owner_required, parent_required
from households.forms import HouseholdSettingsForm
from identity.forms import ProfileForm
from integrations.forms import BunqConfigForm, HueConfigForm, OutlookConfigForm
from integrations.audit import log_integration_event
from integrations.data_export import household_export
from integrations.models import IntegrationAppConfig, IntegrationAudit, IntegrationConnection
from planning.models import CalendarSource
from integrations.providers import ProviderError, arm_hue_bridge_link, finish_hue_bridge_link
from integrations.services import finish_bunq_connection, finish_hue_connection, finish_outlook_connection, get_app_config, save_app_config, start_bunq_connection, start_hue_connection, start_outlook_connection
from integrations.tasks import sync_connection_task


@household_required
def index(request):
    outlook_client_id, _, outlook_settings = get_app_config(request.household, "outlook")
    bunq_client_id, _, bunq_settings = get_app_config(request.household, "bunq")
    hue_client_id, _, hue_settings = get_app_config(request.household, "hue")
    return render(request, "integrations/index.html", {
        "connections": IntegrationConnection.objects.for_household(request.household).order_by("provider"),
        "recent_audits": IntegrationAudit.objects.for_household(request.household).select_related("user")[:8],
        "outlook_form": OutlookConfigForm(initial={"client_id": outlook_client_id, "tenant_id": outlook_settings.get("tenant_id", "consumers")}),
        "bunq_form": BunqConfigForm(initial={"client_id": bunq_client_id, "environment": bunq_settings.get("environment", "production")}),
        "hue_form": HueConfigForm(initial={"client_id": hue_client_id}),
        "profile_form": ProfileForm(instance=request.user),
        "household_form": HouseholdSettingsForm(instance=request.household),
    })


@household_required
@require_POST
def save_profile(request):
    form = ProfileForm(request.POST, instance=request.user)
    if form.is_valid():
        form.save()
        messages.success(request, "Profiel bijgewerkt.")
    return redirect("integrations:index")


@owner_required
@require_POST
def save_household(request):
    form = HouseholdSettingsForm(request.POST, instance=request.household)
    if form.is_valid():
        form.save()
        messages.success(request, "Huishouden bijgewerkt.")
    return redirect("integrations:index")


@owner_required
def export_household_data(request):
    payload = json.dumps(household_export(request.household), cls=DjangoJSONEncoder, ensure_ascii=False, indent=2)
    response = HttpResponse(payload, content_type="application/json; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="family-app-gegevens.json"'
    return response


@parent_required
@require_POST
def save_outlook_config(request):
    form = OutlookConfigForm(request.POST)
    if form.is_valid():
        save_app_config(request.household, "outlook", form.cleaned_data["client_id"], form.cleaned_data["client_secret"], {"tenant_id": form.cleaned_data["tenant_id"]})
        messages.success(request, "Outlook-configuratie veilig opgeslagen.")
    return redirect("integrations:index")


@parent_required
@require_POST
def save_bunq_config(request):
    form = BunqConfigForm(request.POST)
    if form.is_valid():
        save_app_config(request.household, "bunq", form.cleaned_data["client_id"], form.cleaned_data["client_secret"], {"environment": form.cleaned_data["environment"]})
        messages.success(request, "bunq-configuratie veilig opgeslagen.")
    return redirect("integrations:index")


@parent_required
@require_POST
def save_hue_config(request):
    form = HueConfigForm(request.POST)
    if form.is_valid():
        save_app_config(
            request.household,
            "hue",
            form.cleaned_data["client_id"],
            form.cleaned_data["client_secret"],
            {},
        )
        messages.success(request, "Philips Hue-configuratie veilig opgeslagen.")
    return redirect("integrations:index")


@parent_required
@require_GET
def start_outlook(request):
    try:
        return redirect(start_outlook_connection(request))
    except ValueError as error:
        messages.error(request, str(error))
        return redirect("integrations:index")


@parent_required
@require_GET
def outlook_callback(request):
    try:
        connection = finish_outlook_connection(request, request.GET.get("code", ""), request.GET.get("state", ""))
        log_integration_event(connection=connection, action=IntegrationAudit.Action.CONNECTED, detail="Outlook-account geautoriseerd.")
        sync_connection_task.delay(connection.id, request.household.id)
        messages.success(request, "Outlook is gekoppeld. De agenda wordt nu gesynchroniseerd.")
    except ValueError as error:
        messages.error(request, str(error))
    return redirect("integrations:index")


@parent_required
@require_GET
def start_bunq(request):
    try:
        return redirect(start_bunq_connection(request))
    except ValueError as error:
        messages.error(request, str(error))
        return redirect("integrations:index")


@parent_required
@require_GET
def bunq_callback(request):
    try:
        connection = finish_bunq_connection(request, request.GET.get("code", ""), request.GET.get("state", ""))
        log_integration_event(connection=connection, action=IntegrationAudit.Action.CONNECTED, detail="bunq-account geautoriseerd.")
        sync_connection_task.delay(connection.id, request.household.id)
        messages.success(request, "bunq OAuth is gekoppeld. Start een synchronisatie om de rekeningen op te halen.")
    except ValueError as error:
        messages.error(request, str(error))
    return redirect("integrations:index")


@parent_required
@require_GET
def start_hue(request):
    try:
        return redirect(start_hue_connection(request))
    except ValueError as error:
        messages.error(request, str(error))
        return redirect("integrations:index")


@parent_required
@require_GET
def hue_callback(request):
    try:
        connection = finish_hue_connection(request, request.GET.get("code", ""), request.GET.get("state", ""))
        log_integration_event(connection=connection, action=IntegrationAudit.Action.CONNECTED, detail="Philips Hue-account geautoriseerd; bridge-koppeling wacht op bevestiging.")
        messages.success(request, "Philips Hue is geautoriseerd. Bevestig nu de fysieke Hue Bridge.")
    except ValueError as error:
        messages.error(request, str(error))
    return redirect("integrations:index")


@parent_required
@require_POST
def arm_hue_bridge(request, connection_id):
    connection = IntegrationConnection.objects.for_household(request.household).get(pk=connection_id, provider=IntegrationConnection.Provider.HUE)
    try:
        arm_hue_bridge_link(connection)
        messages.success(request, "De bridge staat klaar. Druk binnen 30 seconden op de fysieke knop en kies daarna Voltooien.")
    except ProviderError as error:
        messages.error(request, str(error))
    return redirect("integrations:index")


@parent_required
@require_POST
def finish_hue_bridge(request, connection_id):
    connection = IntegrationConnection.objects.for_household(request.household).get(pk=connection_id, provider=IntegrationConnection.Provider.HUE)
    try:
        finish_hue_bridge_link(connection)
        sync_connection_task.delay(connection.id, request.household.id)
        messages.success(request, "Philips Hue Bridge is gekoppeld. Lampen worden nu opgehaald.")
    except ProviderError as error:
        messages.error(request, str(error))
    return redirect("integrations:index")


@parent_required
@require_POST
def sync_connection(request, connection_id):
    connection = IntegrationConnection.objects.for_household(request.household).get(pk=connection_id)
    sync_connection_task.delay(connection.id, request.household.id)
    messages.success(request, f"Synchronisatie voor {connection.display_name} staat in de wachtrij.")
    return redirect("integrations:index")


@parent_required
@require_POST
def disconnect_connection(request, connection_id):
    connection = IntegrationConnection.objects.for_household(request.household).select_related("user").get(pk=connection_id)
    provider, display_name, user = connection.provider, connection.display_name, connection.user
    if provider == IntegrationConnection.Provider.OUTLOOK and user:
        CalendarSource.objects.for_household(request.household).filter(provider=CalendarSource.Provider.OUTLOOK, owner=user).delete()
    log_integration_event(
        connection=connection,
        action=IntegrationAudit.Action.DISCONNECTED,
        detail=f"{display_name} ontkoppeld; toegangsgegevens verwijderd.",
    )
    connection.delete()
    messages.success(request, f"{display_name} is ontkoppeld.")
    return redirect("integrations:index")
