import json
import os
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from datetime import timedelta

from django.contrib import messages
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from households.decorators import household_required, owner_required, parent_required
from households.forms import HouseholdSettingsForm
from identity.forms import ProfileForm
from integrations.forms import BunqConfigForm, GoogleHomeConfigForm, HueConfigForm, LgThinQConfigForm, OutlookConfigForm, SonosConfigForm
from integrations.audit import log_integration_event
from integrations.data_export import household_export
from integrations.models import IntegrationAppConfig, IntegrationAudit, IntegrationConnection, LocalDiscovery, LocalProbe, SyncRun
from integrations.local_probe import ProbeError, create_pairing, pair_probe, revoke_probe
from planning.models import CalendarSource
from integrations.providers import ProviderError, arm_hue_bridge_link, finish_hue_bridge_link
from integrations.services import finish_bunq_connection, finish_google_home_connection, finish_hue_connection, finish_lg_thinq_connection, finish_outlook_connection, finish_sonos_connection, get_app_config, get_sonos_event_callback_token, public_origin, save_app_config, save_sonos_config as save_sonos_integration_config, start_bunq_connection, start_google_home_connection, start_hue_connection, start_lg_thinq_connection, start_outlook_connection, start_sonos_connection
from integrations.sonos_events import SonosEventError, process_sonos_event
from integrations.tasks import sync_connection_task


@household_required
def index(request):
    outlook_client_id, _, outlook_settings = get_app_config(request.household, "outlook")
    bunq_client_id, _, bunq_settings = get_app_config(request.household, "bunq")
    hue_client_id, _, hue_settings = get_app_config(request.household, "hue")
    sonos_client_id, _, sonos_settings = get_app_config(request.household, "sonos")
    sonos_event_callback_token = get_sonos_event_callback_token(request.household)
    google_home_client_id, _, google_home_settings = get_app_config(request.household, "google_home")
    lg_thinq_client_id, _, lg_thinq_settings = get_app_config(request.household, "lg_thinq")
    return render(request, "integrations/index.html", {
        "connections": IntegrationConnection.objects.for_household(request.household).order_by("provider"),
        "recent_audits": IntegrationAudit.objects.for_household(request.household).select_related("user")[:8],
        "outlook_form": OutlookConfigForm(initial={"client_id": outlook_client_id, "tenant_id": outlook_settings.get("tenant_id", "consumers")}),
        "bunq_form": BunqConfigForm(initial={"client_id": bunq_client_id, "environment": bunq_settings.get("environment", "production")}),
        "hue_form": HueConfigForm(initial={"client_id": hue_client_id, "app_id": hue_settings.get("app_id", ""), "device_name": hue_settings.get("device_name", "Family App")}),
        "hue_redirect_url": f"{public_origin(request)}/instellingen/hue/callback/",
        "sonos_form": SonosConfigForm(initial={"client_id": sonos_client_id, "events_enabled": sonos_settings.get("events_enabled", False)}),
        "sonos_redirect_url": f"{public_origin(request)}/instellingen/sonos/callback/",
        "sonos_event_callback_url": f"{public_origin(request)}/instellingen/sonos/events/{request.household.id}/{sonos_event_callback_token}/" if sonos_event_callback_token else "Sla eerst de Sonos-configuratie op.",
        "google_home_form": GoogleHomeConfigForm(initial={"client_id": google_home_client_id, "project_id": google_home_settings.get("project_id", "")}),
        "google_home_redirect_url": f"{public_origin(request)}/instellingen/google-home/callback/",
        "lg_thinq_form": LgThinQConfigForm(initial={"client_id": lg_thinq_client_id, "authorize_url": lg_thinq_settings.get("authorize_url", ""), "token_url": lg_thinq_settings.get("token_url", ""), "api_base_url": lg_thinq_settings.get("api_base_url", ""), "devices_path": lg_thinq_settings.get("devices_path", "/devices")}),
        "lg_thinq_redirect_url": f"{public_origin(request)}/instellingen/lg-thinq/callback/",
        "profile_form": ProfileForm(instance=request.user),
        "household_form": HouseholdSettingsForm(instance=request.household),
        "local_probes": LocalProbe.objects.for_household(request.household).all(),
        "local_discoveries": LocalDiscovery.objects.for_household(request.household).select_related("probe")[:20],
        "probe_pairing_code": request.session.pop("probe_pairing_code", ""),
        "probe_server_url": public_origin(request),
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


@parent_required
@require_POST
def create_local_probe_pairing(request):
    _, code = create_pairing(request.household)
    request.session["probe_pairing_code"] = code
    messages.success(request, "Nieuwe pairing-code gemaakt. Deze is 10 minuten geldig.")
    return redirect("integrations:index")


@parent_required
@require_GET
def download_local_probe(request):
    """Serve only the installable agent source, never a local configuration."""
    source_dir = Path(os.environ.get("LOCAL_PROBE_SOURCE_DIR", settings.BASE_DIR.parent / "local_probe"))
    allowed_files = (
        "README.md",
        "requirements.txt",
        "family-app-probe.service",
        "nl.familyapp.probe.plist",
        "family_app_probe/__init__.py",
        "family_app_probe/config.py",
        "family_app_probe/discovery.py",
        "family_app_probe/hue.py",
        "family_app_probe/main.py",
        "family_app_probe/sonos.py",
    )
    archive = BytesIO()
    with ZipFile(archive, "w", ZIP_DEFLATED) as zip_file:
        for relative_path in allowed_files:
            file_path = source_dir / relative_path
            if file_path.is_file():
                zip_file.write(file_path, f"family-app-probe/{relative_path}")
    archive.seek(0)
    return FileResponse(archive, as_attachment=True, filename="family-app-local-probe.zip", content_type="application/zip")


@parent_required
@require_POST
def revoke_local_probe(request, probe_id):
    probe = LocalProbe.objects.for_household(request.household).get(pk=probe_id)
    revoke_probe(probe)
    messages.success(request, f"{probe.name} is ingetrokken.")
    return redirect("integrations:index")


@csrf_exempt
@require_POST
def local_probe_pair(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
        probe, token = pair_probe(str(payload.get("code") or ""), str(payload.get("name") or ""), str(payload.get("version") or ""))
        origin = public_origin(request).replace("http://", "ws://").replace("https://", "wss://")
        return JsonResponse({"probe_id": str(probe.id), "token": token, "websocket_url": f"{origin}/ws/probe/{probe.id}/"})
    except (ValueError, UnicodeDecodeError, ProbeError) as error:
        return JsonResponse({"error": str(error) or "Pairing mislukt."}, status=400)


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
            {"app_id": form.cleaned_data["app_id"], "device_name": form.cleaned_data["device_name"] or "Family App"},
        )
        messages.success(request, "Philips Hue-configuratie veilig opgeslagen.")
    return redirect("integrations:index")


@parent_required
@require_POST
def save_sonos_config(request):
    form = SonosConfigForm(request.POST)
    if form.is_valid():
        save_sonos_integration_config(request.household, form.cleaned_data["client_id"], form.cleaned_data["client_secret"], form.cleaned_data["events_enabled"])
        messages.success(request, "Sonos-configuratie veilig opgeslagen.")
    return redirect("integrations:index")


@parent_required
@require_POST
def save_google_home_config(request):
    form = GoogleHomeConfigForm(request.POST)
    if form.is_valid():
        save_app_config(request.household, "google_home", form.cleaned_data["client_id"], form.cleaned_data["client_secret"], {"project_id": form.cleaned_data["project_id"]})
        messages.success(request, "Google Home-configuratie veilig opgeslagen.")
    return redirect("integrations:index")


@parent_required
@require_POST
def save_lg_thinq_config(request):
    form = LgThinQConfigForm(request.POST)
    if form.is_valid():
        devices_path = form.cleaned_data["devices_path"].strip()
        if not devices_path.startswith("/"):
            devices_path = f"/{devices_path}"
        save_app_config(request.household, "lg_thinq", form.cleaned_data["client_id"], form.cleaned_data["client_secret"], {"authorize_url": form.cleaned_data["authorize_url"], "token_url": form.cleaned_data["token_url"], "api_base_url": form.cleaned_data["api_base_url"], "devices_path": devices_path})
        messages.success(request, "LG ThinQ-configuratie veilig opgeslagen.")
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
@require_GET
def start_sonos(request):
    try:
        return redirect(start_sonos_connection(request))
    except ValueError as error:
        messages.error(request, str(error))
        return redirect("integrations:index")


@parent_required
@require_GET
def sonos_callback(request):
    try:
        connection = finish_sonos_connection(request, request.GET.get("code", ""), request.GET.get("state", ""))
        log_integration_event(connection=connection, action=IntegrationAudit.Action.CONNECTED, detail="Sonos-account geautoriseerd.")
        sync_connection_task.delay(connection.id, request.household.id)
        messages.success(request, "Sonos is gekoppeld. Speakers worden nu opgehaald.")
    except ValueError as error:
        messages.error(request, str(error))
    return redirect("integrations:index")


@csrf_exempt
@require_POST
def sonos_event_callback(request, household_id, callback_token, event_path=""):
    try:
        result = process_sonos_event(household_id, callback_token, request.headers, request.body)
    except SonosEventError:
        return HttpResponse(status=403)
    if result.get("sync_needed") and result.get("connection_id"):
        sync_connection_task.delay(result["connection_id"], household_id)
    return HttpResponse(status=200)


@parent_required
@require_GET
def start_google_home(request):
    try:
        return redirect(start_google_home_connection(request))
    except ValueError as error:
        messages.error(request, str(error))
        return redirect("integrations:index")


@parent_required
@require_GET
def google_home_callback(request):
    try:
        connection = finish_google_home_connection(request, request.GET.get("code", ""), request.GET.get("state", ""))
        log_integration_event(connection=connection, action=IntegrationAudit.Action.CONNECTED, detail="Google Home Device Access geautoriseerd.")
        sync_connection_task.delay(connection.id, request.household.id)
        messages.success(request, "Google Home is gekoppeld. Ondersteunde Google Nest-apparaten worden nu opgehaald.")
    except ValueError as error:
        messages.error(request, str(error))
    return redirect("integrations:index")


@parent_required
@require_GET
def start_lg_thinq(request):
    try:
        return redirect(start_lg_thinq_connection(request))
    except ValueError as error:
        messages.error(request, str(error))
        return redirect("integrations:index")


@parent_required
@require_GET
def lg_thinq_callback(request):
    try:
        connection = finish_lg_thinq_connection(request, request.GET.get("code", ""), request.GET.get("state", ""))
        log_integration_event(connection=connection, action=IntegrationAudit.Action.CONNECTED, detail="LG ThinQ-account geautoriseerd.")
        sync_connection_task.delay(connection.id, request.household.id)
        messages.success(request, "LG ThinQ is gekoppeld. Apparaten worden nu opgehaald.")
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
        sync_run = SyncRun.objects.create(household=request.household, connection=connection, status="queued")
        sync_connection_task.delay(connection.id, request.household.id, sync_run.id)
        messages.success(request, "Philips Hue Bridge is gekoppeld. Lampen worden nu opgehaald.")
    except ProviderError as error:
        messages.error(request, str(error))
    return redirect("integrations:index")


@parent_required
@require_POST
def sync_connection(request, connection_id):
    connection = IntegrationConnection.objects.for_household(request.household).get(pk=connection_id)
    stale_before = timezone.now() - timedelta(minutes=10)
    SyncRun.objects.filter(
        household=request.household,
        connection=connection,
        status="queued",
        started_at__lt=stale_before,
    ).update(
        status="failed",
        detail="De synchronisatiewachtrij reageerde niet. Probeer opnieuw.",
        finished_at=timezone.now(),
    )
    active_run = SyncRun.objects.filter(
        household=request.household,
        connection=connection,
        status__in=["queued", "running"],
    ).order_by("-started_at").first()
    if active_run:
        messages.info(request, f"Synchronisatie voor {connection.display_name} loopt al.")
    else:
        sync_run = SyncRun.objects.create(household=request.household, connection=connection, status="queued")
        sync_connection_task.delay(connection.id, request.household.id, sync_run.id)
        messages.success(request, f"Synchronisatie voor {connection.display_name} staat in de wachtrij.")
    next_url = request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(next_url)
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
