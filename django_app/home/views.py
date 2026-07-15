from ast import literal_eval
from datetime import timedelta
import json
from os.path import basename
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib import messages
from django.http import FileResponse, HttpResponse, JsonResponse, StreamingHttpResponse
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from asgiref.sync import sync_to_async

from django.utils import timezone

from home.forms import EmergencyContactForm, FurnishingItemForm, HomeAssistantConfigForm, HouseholdDocumentForm, MaintenanceItemForm, RoomForm
from home.models import EmergencyContact, FurnishingItem, HomeActionAudit, HomeAssistantConfig, HomeEntity, HouseholdDocument, MaintenanceItem, Room
from home.services import HomeAssistantError, control_entity, save_config, sync_entities
from households.decorators import household_required, parent_required
from integrations.models import IntegrationConnection, SyncRun
from integrations.local_probe import expire_stale_probes


def _tab_redirect(tab):
    return redirect(f"{reverse('home:index')}?tab={tab}")


def _return_to_home(request):
    referer = request.META.get("HTTP_REFERER", "")
    if referer and url_has_allowed_host_and_scheme(
        referer,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        parsed = urlsplit(referer)
        return redirect(f"{parsed.path}?{parsed.query}" if parsed.query else parsed.path)
    return redirect("home:index")


def _hue_sync_summary(sync_run):
    if not sync_run or sync_run.status != "succeeded" or not sync_run.detail:
        return sync_run.detail if sync_run else ""
    try:
        result = literal_eval(sync_run.detail)
    except (SyntaxError, ValueError):
        return sync_run.detail
    if not isinstance(result, dict):
        return sync_run.detail
    labels = (("lights", "lamp", "lampen"), ("groups", "kamer of zone", "kamers of zones"), ("sensors", "sensor", "sensoren"), ("scenes", "scène", "scènes"))
    values = []
    for key, singular, plural in labels:
        try:
            count = int(result.get(key, 0))
        except (TypeError, ValueError):
            continue
        if count:
            values.append(f"{count} {singular if count == 1 else plural}")
    return " · ".join(values) if values else sync_run.detail


def _group_hue_sensors(entities):
    regular_entities, grouped = [], {}
    for entity in entities:
        if entity.source != HomeEntity.Source.HUE or entity.domain != "sensor":
            regular_entities.append(entity)
            continue
        attributes = entity.attributes if isinstance(entity.attributes, dict) else {}
        device_id = str(attributes.get("hue_device_id") or entity.id)
        sensor_group = grouped.setdefault(
            device_id,
            {
                "name": attributes.get("hue_device_name") or entity.name.split(" · ", 1)[0],
                "product_name": attributes.get("hue_product_name") or "",
                "locations": set(),
                "sensors": [],
                "is_available": True,
                "battery_level": attributes.get("hue_battery_level"),
                "connectivity": attributes.get("hue_connectivity") or "",
            },
        )
        sensor_group["locations"].update(str(location) for location in attributes.get("hue_locations", []) if location)
        sensor_group["sensors"].append(entity)
        sensor_group["is_available"] = sensor_group["is_available"] and entity.is_available
        if sensor_group["battery_level"] is None and attributes.get("hue_battery_level") is not None:
            sensor_group["battery_level"] = attributes["hue_battery_level"]
        if not sensor_group["connectivity"] and attributes.get("hue_connectivity"):
            sensor_group["connectivity"] = attributes["hue_connectivity"]
    sensor_groups = []
    for sensor_group in grouped.values():
        sensor_group["locations"] = sorted(sensor_group["locations"])
        sensor_group["sensors"].sort(
            key=lambda item: str(
                (item.attributes if isinstance(item.attributes, dict) else {}).get("hue_sensor_kind") or item.name
            )
        )
        kind_counts = {}
        for sensor in sensor_group["sensors"]:
            attributes = sensor.attributes if isinstance(sensor.attributes, dict) else {}
            kind = str(attributes.get("hue_sensor_kind") or sensor.name)
            kind_counts[kind] = kind_counts.get(kind, 0) + 1
        kind_indexes = {}
        for sensor in sensor_group["sensors"]:
            attributes = sensor.attributes if isinstance(sensor.attributes, dict) else {}
            kind = str(attributes.get("hue_sensor_kind") or sensor.name)
            kind_indexes[kind] = kind_indexes.get(kind, 0) + 1
            sensor.sensor_label = f"{kind} {kind_indexes[kind]}" if kind_counts[kind] > 1 else kind
        health = []
        if sensor_group["battery_level"] is not None:
            health.append(f"Batterij {sensor_group['battery_level']}%")
        if sensor_group["connectivity"]:
            health.append(_hue_connectivity_label(sensor_group["connectivity"]))
        sensor_group["connectivity_issue"] = _hue_has_connectivity_issue(sensor_group["connectivity"])
        sensor_group["health"] = " · ".join(health)
        sensor_groups.append(sensor_group)
    return regular_entities, sorted(sensor_groups, key=lambda item: str(item["name"]).lower())


def _hue_connectivity_label(value):
    status = str(value or "").strip().lower()
    if status == "connected":
        return "Verbonden"
    if status in {"connectivity_issue", "disconnected", "unreachable", "not_connected"}:
        return "Niet verbonden"
    return "Verbinding onbekend"


def _hue_has_connectivity_issue(value):
    return str(value or "").strip().lower() not in {"", "connected"}


def _hue_locations(entity):
    attributes = entity.attributes if isinstance(entity.attributes, dict) else {}
    locations = attributes.get("hue_locations")
    if isinstance(locations, list):
        return [str(location) for location in locations if location]
    if entity.source == HomeEntity.Source.HUE and entity.domain == "scene" and attributes.get("hue_group_name"):
        return [str(attributes["hue_group_name"])]
    if entity.source == HomeEntity.Source.HUE and entity.domain == "group":
        return [entity.name]
    return []


def _entity_locations(entity):
    attributes = entity.attributes if isinstance(entity.attributes, dict) else {}
    ha_area = str(attributes.get("ha_area") or "")
    if entity.source == HomeEntity.Source.HOME_ASSISTANT and ha_area:
        return [ha_area]
    return _hue_locations(entity)


def _decorate_home_entities(entities):
    def sort_key(entity):
        attributes = entity.attributes if isinstance(entity.attributes, dict) else {}
        is_hue_scene = entity.source == HomeEntity.Source.HUE and entity.domain == "scene"
        return (1 if is_hue_scene else 0, str(attributes.get("hue_group_name") or "").lower(), entity.name.lower())

    decorated = sorted(entities, key=sort_key)
    previous_scene_group = None
    for entity in decorated:
        attributes = entity.attributes if isinstance(entity.attributes, dict) else {}
        entity.google_last_event_time = ""
        event_timestamp = parse_datetime(str(attributes.get("google_last_event_at") or ""))
        if event_timestamp:
            entity.google_last_event_time = timezone.localtime(event_timestamp).strftime("%d %b %H:%M:%S")
        if entity.source == HomeEntity.Source.HUE:
            entity.hue_connectivity_label = _hue_connectivity_label(attributes.get("hue_connectivity"))
            entity.hue_connectivity_issue = _hue_has_connectivity_issue(attributes.get("hue_connectivity"))
        if entity.source == HomeEntity.Source.HUE and entity.domain == "scene":
            group_name = str(attributes.get("hue_group_name") or "Overige scènes")
            entity.scene_group_name = group_name
            entity.starts_scene_group = group_name != previous_scene_group
            previous_scene_group = group_name
        else:
            entity.starts_scene_group = False
    return decorated


def _local_sonos_duplicate_ids(entities):
    """Prefer a live local Sonos group; otherwise fall back to its cloud card."""
    sonos_entities = list(entities.filter(source=HomeEntity.Source.SONOS))
    local_groups = []
    for entity in sonos_entities:
        attributes = entity.attributes if isinstance(entity.attributes, dict) else {}
        if not attributes.get("probe_id") or attributes.get("sonos_entity_type") != "group":
            continue
        members = {str(player_id) for player_id in attributes.get("sonos_player_ids", []) if player_id}
        if members:
            local_groups.append((entity, members))
    if not local_groups:
        return set()

    hidden_ids = set()
    cloud_entities = [
        entity
        for entity in sonos_entities
        if not (entity.attributes if isinstance(entity.attributes, dict) else {}).get("probe_id")
    ]
    for local_group, members in local_groups:
        matching_cloud = []
        for entity in cloud_entities:
            attributes = entity.attributes if isinstance(entity.attributes, dict) else {}
            entity_type = attributes.get("sonos_entity_type")
            if entity_type == "player":
                matches = str(attributes.get("sonos_player_id") or "") in members
            elif entity_type == "group":
                member_ids = {str(player_id) for player_id in attributes.get("sonos_player_ids", []) if player_id}
                coordinator_id = str(attributes.get("sonos_coordinator_id") or "")
                matches = bool(member_ids & members or coordinator_id in members)
            else:
                matches = False
            if matches:
                matching_cloud.append(entity)
        if local_group.is_available:
            hidden_ids.update(entity.pk for entity in matching_cloud)
        elif matching_cloud:
            hidden_ids.add(local_group.pk)
    return hidden_ids


def _norm_entity_key(value):
    return "".join(str(value or "").casefold().split())


def _ha_duplicate_ids(entities):
    """Prefer Home Assistant cards while keeping direct integrations available."""
    all_entities = list(entities)
    ha_entities = [entity for entity in all_entities if entity.source == HomeEntity.Source.HOME_ASSISTANT]
    if not ha_entities:
        return set()
    ha_name_domain_keys = {(_norm_entity_key(entity.domain), _norm_entity_key(entity.name)) for entity in ha_entities if entity.name}
    ha_identifiers = {
        str(identifier)
        for entity in ha_entities
        for identifier in ((entity.attributes or {}).get("ha_device_identifiers", []) if isinstance(entity.attributes, dict) else [])
        if identifier
    }
    hidden_ids = set()
    for entity in all_entities:
        if entity.source == HomeEntity.Source.HOME_ASSISTANT:
            continue
        attributes = entity.attributes if isinstance(entity.attributes, dict) else {}
        direct_values = {
            str(attributes.get(key))
            for key in ("hue_light_id", "hue_grouped_light_id", "hue_scene_id", "sonos_player_id", "sonos_group_id", "google_resource_name", "lg_device_id", "probe_local_key")
            if attributes.get(key)
        }
        if direct_values and any(value and any(value in identifier for identifier in ha_identifiers) for value in direct_values):
            hidden_ids.add(entity.pk)
            continue
        if (_norm_entity_key(entity.domain), _norm_entity_key(entity.name)) in ha_name_domain_keys:
            hidden_ids.add(entity.pk)
    return hidden_ids


@household_required
def index(request):
    tab = request.GET.get("tab", "apparaten")
    expire_stale_probes(request.household)
    config = HomeAssistantConfig.objects.for_household(request.household).first()
    all_entities = HomeEntity.objects.for_household(request.household)
    hidden_ids = _local_sonos_duplicate_ids(all_entities) | _ha_duplicate_ids(all_entities)
    visible_entities = all_entities.exclude(pk__in=hidden_ids)
    source_entities = visible_entities
    source = request.GET.get("source", "alles")
    if source in set(HomeEntity.Source.values):
        source_entities = source_entities.filter(source=source)
    else:
        source = "alles"
    entities = source_entities
    domain = request.GET.get("domain", "apparaten")
    if domain == "apparaten":
        entities = entities.exclude(domain="scene")
    elif domain != "alles":
        entities = entities.filter(domain=domain)
    search_query = request.GET.get("q", "").strip()[:120]
    if search_query:
        entities = entities.filter(Q(name__icontains=search_query) | Q(state__icontains=search_query))
    locations = sorted({location for entity in visible_entities for location in _entity_locations(entity)}, key=str.lower)
    selected_location = request.GET.get("location", "alles")
    if selected_location not in locations:
        selected_location = "alles"
    if selected_location != "alles":
        matching_entity_ids = [entity.id for entity in source_entities if selected_location in _entity_locations(entity)]
        entities = entities.filter(id__in=matching_entity_ids)
    all_sonos_players = list(visible_entities.filter(source=HomeEntity.Source.SONOS, domain="speaker", is_available=True).select_related("connection"))
    display_entities, hue_sensor_groups = _group_hue_sensors(_decorate_home_entities(entities))
    for entity in display_entities:
        attributes = entity.attributes if isinstance(entity.attributes, dict) else {}
        if entity.source != HomeEntity.Source.SONOS or attributes.get("sonos_entity_type") != "group":
            continue
        household_key = str(attributes.get("sonos_household_id") or "")
        member_ids = {str(player_id) for player_id in attributes.get("sonos_player_ids", [])}
        entity.sonos_grouping_candidates = [
            {
                "id": str(player.attributes.get("sonos_player_id")),
                "name": player.name,
                "selected": str(player.attributes.get("sonos_player_id")) in member_ids,
            }
            for player in all_sonos_players
            if player.connection_id == entity.connection_id
            and str((player.attributes or {}).get("sonos_household_id") or "") == household_key
            and (player.attributes or {}).get("sonos_player_id")
        ]
    maintenance = MaintenanceItem.objects.for_household(request.household)
    rooms = Room.objects.for_household(request.household)
    hue_connection = IntegrationConnection.objects.for_household(request.household).filter(provider=IntegrationConnection.Provider.HUE).first()
    home_connections = list(IntegrationConnection.objects.for_household(request.household).filter(
        provider__in=[IntegrationConnection.Provider.HUE, IntegrationConnection.Provider.SONOS, IntegrationConnection.Provider.SPOTIFY, IntegrationConnection.Provider.SMARTCAR, IntegrationConnection.Provider.LG_THINQ, IntegrationConnection.Provider.GOOGLE_HOME, IntegrationConnection.Provider.HOME_CONNECT]
    ).order_by("provider"))
    entity_counts = {
        row["connection_id"]: row["count"]
        for row in HomeEntity.objects.for_household(request.household)
        .filter(connection_id__in=[connection.id for connection in home_connections], is_available=True)
        .values("connection_id")
        .annotate(count=Count("id"))
    }
    for connection in home_connections:
        connection.home_entity_count = entity_counts.get(connection.id, 0)
    hue_sync_run = SyncRun.objects.filter(household=request.household, connection=hue_connection).order_by("-started_at").first() if hue_connection else None
    hue_sync_is_stale = bool(
        hue_connection
        and hue_connection.status == "configured"
        and hue_connection.last_sync_at
        and hue_connection.last_sync_at < timezone.now() - timedelta(minutes=20)
    )
    return render(request, "home/index.html", {"tab": tab, "config": config, "hue_connection": hue_connection, "home_connections": home_connections, "hue_sync_run": hue_sync_run, "hue_sync_summary": _hue_sync_summary(hue_sync_run), "hue_sync_is_stale": hue_sync_is_stale, "entities": entities, "display_entities": display_entities, "hue_sensor_groups": hue_sensor_groups, "search_query": search_query, "selected_source": source, "sources": visible_entities.values_list("source", flat=True).distinct().order_by("source"), "selected_domain": domain, "domains": source_entities.values_list("domain", flat=True).distinct().order_by("domain"), "locations": locations, "selected_location": selected_location, "audits": HomeActionAudit.objects.for_household(request.household).select_related("entity")[:6], "config_form": HomeAssistantConfigForm(initial={"base_url": config.base_url if config else ""}), "maintenance": maintenance, "emergency_contacts": EmergencyContact.objects.for_household(request.household), "rooms": rooms.prefetch_related("items"), "documents": HouseholdDocument.objects.for_household(request.household), "maintenance_form": MaintenanceItemForm(), "emergency_form": EmergencyContactForm(), "room_form": RoomForm(), "furnishing_form": FurnishingItemForm(), "document_form": HouseholdDocumentForm(), "metrics": [{"value": entities.filter(is_available=True).count(), "label": "beschikbaar"}, {"value": maintenance.filter(due_date__lte=timezone.localdate()).count(), "label": "onderhoud"}]})


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
    return _return_to_home(request)


@parent_required
@require_POST
def control(request, entity_id, action):
    entity = get_object_or_404(HomeEntity.objects.for_household(request.household), pk=entity_id)
    try:
        if action == "set_group":
            value = request.POST.getlist("player_ids")
        elif action == "create_alarm":
            value = json.dumps({"time": request.POST.get("alarm_time", ""), "recurrence": request.POST.get("alarm_recurrence", "DAILY")})
        elif action == "update_alarm":
            value = json.dumps(
                {
                    "id": request.POST.get("alarm_id", ""),
                    "time": request.POST.get("alarm_time", ""),
                    "recurrence": request.POST.get("alarm_recurrence", "DAILY"),
                    "volume": request.POST.get("alarm_volume", "20"),
                }
            )
        elif action == "set_home_theater_eq":
            value = json.dumps({"eq_type": request.POST.get("eq_type", ""), "value": request.POST.get("value", "0")})
        elif action == "learn_ir_code":
            value = json.dumps({"code": request.POST.get("ir_code", ""), "timeout": request.POST.get("ir_timeout", "30")})
        elif action in {"remove_group_member", "add_group_member", "add_ht_satellite", "create_stereo_pair", "separate_stereo_pair", "start_room_calibration", "stop_room_calibration"}:
            value = json.dumps(
                {
                    "member_id": request.POST.get("member_id", ""),
                    "role": request.POST.get("role", ""),
                    "channel_map": request.POST.get("channel_map", ""),
                    "confirmed": request.POST.get("confirm_remove") == "yes" or request.POST.get("confirm_add") == "yes" or request.POST.get("confirm_home_theater") == "yes" or request.POST.get("confirm_stereo") == "yes" or request.POST.get("confirm_calibration") == "yes",
                }
            )
        elif action == "set_temperature_range":
            value = {"heat": request.POST.get("heat_temperature", ""), "cool": request.POST.get("cool_temperature", "")}
        elif action == "set_thermostat_mode":
            value = request.POST.get("thermostat_mode", "")
        elif action == "set_eco_mode":
            value = request.POST.get("eco_mode", "")
        elif action == "set_fan_timer":
            value = request.POST.get("fan_seconds", "")
        elif action in {"start_program", "select_program"}:
            if request.POST.get("confirmed") != "yes":
                raise HomeAssistantError("Bevestig eerst dat je deze programmawijziging wilt uitvoeren.")
            value = request.POST.get("home_connect_program", "")
        elif action == "stop_program":
            if request.POST.get("confirmed") != "yes":
                raise HomeAssistantError("Bevestig eerst dat je het programma wilt stoppen.")
            value = ""
        else:
            value = request.POST.get("target_temperature") or request.POST.get("brightness") or request.POST.get("volume") or request.POST.get("color") or request.POST.get("effect") or request.POST.get("favorite_id")
        result = control_entity(request.household, entity, action, value) or {}
        if request.headers.get("HX-Request") == "true":
            response = HttpResponse("")
            response["HX-Trigger"] = json.dumps(
                {
                    "family:toast": {"message": f"{entity.name}: opdracht verzonden." if result.get("queued") else f"{entity.name} bijgewerkt.", "level": "info" if result.get("queued") else "success"},
                    "family:home-control": {
                        "entity_id": entity.id,
                        "action": action,
                        "value": value or "",
                        "state": entity.state,
                        "member_light_ids": entity.attributes.get("member_light_ids", []) if entity.domain == "group" and isinstance(entity.attributes, dict) else [],
                        "sonos_group_id": entity.attributes.get("sonos_group_id", "") if entity.source == HomeEntity.Source.SONOS and isinstance(entity.attributes, dict) else "",
                        "sonos_volume": entity.attributes.get("sonos_volume") if entity.source == HomeEntity.Source.SONOS and isinstance(entity.attributes, dict) else None,
                        "sonos_muted": bool(entity.attributes.get("sonos_muted")) if entity.source == HomeEntity.Source.SONOS and isinstance(entity.attributes, dict) else False,
                        "refresh": action == "set_group",
                        "queued": bool(result.get("queued")),
                        "command_id": result.get("command_id", ""),
                    },
                }
            )
            return response
        messages.success(request, f"{entity.name} bijgewerkt.")
    except HomeAssistantError as error:
        if request.headers.get("HX-Request") == "true":
            response = HttpResponse("")
            response["HX-Trigger"] = json.dumps({"family:toast": {"message": str(error), "level": "error"}})
            return response
        messages.error(request, str(error))
    return _return_to_home(request)


@parent_required
@require_POST
def start_google_live_stream(request, entity_id):
    entity = get_object_or_404(
        HomeEntity.objects.for_household(request.household),
        pk=entity_id,
        source=HomeEntity.Source.GOOGLE_HOME,
    )
    try:
        from integrations.providers import ProviderError, start_google_home_live_stream

        session = start_google_home_live_stream(entity)
        # Store stream names in session for later cleanup
        request.session[f"google_live_stream_{entity.id}"] = {
            "mjpeg_stream_name": session["stream_name"],
            "rtsp_stream_name": session["rtsp_stream_name"],
        }
        request.session.modified = True
        HomeActionAudit.objects.create(household=request.household, entity=entity, action="live_stream", succeeded=True, detail="Tijdelijke Nest-livestream gestart.")
        return JsonResponse({"media_url": reverse("home:google_live_mp4", args=[entity.id]), "expires_at": session["expires_at"]})
    except ProviderError as error:
        HomeActionAudit.objects.create(household=request.household, entity=entity, action="live_stream", succeeded=False, detail=str(error))
        return JsonResponse({"error": str(error)}, status=400)


@parent_required
@require_POST
def stop_google_live_stream(request, entity_id):
    entity = get_object_or_404(HomeEntity.objects.for_household(request.household), pk=entity_id, source=HomeEntity.Source.GOOGLE_HOME)
    from integrations.providers import stop_google_home_live_stream

    stream_info = request.session.get(f"google_live_stream_{entity.id}", {})
    mjpeg_stream_name = stream_info.get("mjpeg_stream_name", "")
    rtsp_stream_name = stream_info.get("rtsp_stream_name", "")
    if mjpeg_stream_name and rtsp_stream_name:
        stop_google_home_live_stream(mjpeg_stream_name, rtsp_stream_name)
        del request.session[f"google_live_stream_{entity.id}"]
        request.session.modified = True
    return HttpResponse(status=204)


@parent_required
def google_live_mp4(request, entity_id):
    entity = get_object_or_404(HomeEntity.objects.for_household(request.household), pk=entity_id, source=HomeEntity.Source.GOOGLE_HOME)
    try:
        from integrations.providers import ProviderError, google_home_mp4_stream

        stream_info = request.session.get(f"google_live_stream_{entity.id}", {})
        stream_name = stream_info.get("mjpeg_stream_name", "")
        if not stream_name:
            raise ProviderError("Geen actieve livestream gevonden.")
        response = google_home_mp4_stream(stream_name)
    except ProviderError as error:
        return HttpResponse(str(error), status=503, content_type="text/plain; charset=utf-8")

    iterator = response.iter_content(chunk_size=64 * 1024)

    async def chunks():
        try:
            while True:
                chunk = await sync_to_async(next, thread_sensitive=False)(iterator, None)
                if chunk is None:
                    break
                if chunk:
                    yield chunk
        finally:
            await sync_to_async(response.close, thread_sensitive=False)()

    stream = StreamingHttpResponse(chunks(), content_type=response.headers.get("Content-Type", "video/mp4"))
    stream["Cache-Control"] = "no-store"
    return stream


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


@csrf_exempt
@require_POST
def ha_webhook_receiver(request, webhook_token: str):
    """Receive state change notifications from Home Assistant webhook."""
    import hmac

    from home.ha_integration import handle_state_change_webhook

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    household_id = payload.get("household_id")
    if not household_id or not hmac.compare_digest(webhook_token, _generate_webhook_token(household_id)):
        return JsonResponse({"error": "Unauthorized"}, status=401)

    success = handle_state_change_webhook(household_id, payload)
    return JsonResponse({"success": success, "entity_id": payload.get("entity_id", "unknown")})


@household_required
def ha_entities_list(request):
    """Get list of Home Assistant entities for the household."""
    from home.ha_integration import get_ha_entities

    entities = get_ha_entities(request.household.id)
    # Filter to supported domains
    supported_domains = {"light", "switch", "climate", "cover", "lock", "scene", "automation", "script"}
    filtered = [e for e in entities if e.get("entity_id", "").split(".")[0] in supported_domains]

    return JsonResponse(
        {
            "entities": [
                {
                    "entity_id": e.get("entity_id", ""),
                    "state": e.get("state", ""),
                    "attributes": e.get("attributes", {}),
                }
                for e in filtered
            ]
        }
    )


@household_required
@require_POST
def ha_control_entity(request, entity_id: str):
    """Control a Home Assistant entity (turn on/off, etc.)."""
    from home.ha_integration import call_ha_service

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    action = data.get("action", "turn_on").lower()
    domain = entity_id.split(".")[0] if "." in entity_id else ""

    if domain not in {"light", "switch", "cover", "lock", "climate"}:
        return JsonResponse({"error": "Unsupported domain"}, status=400)

    service = "turn_on" if action == "on" else "turn_off" if action == "off" else action

    success = call_ha_service(request.household.id, domain, service, entity_id, data.get("data"))
    return JsonResponse({"success": success, "action": action, "entity_id": entity_id})


def _generate_webhook_token(household_id: int) -> str:
    """Generate a deterministic webhook token for a household."""
    import hashlib

    secret = settings.SECRET_KEY
    token_input = f"{household_id}:{secret}:ha-webhook"
    return hashlib.sha256(token_input.encode()).hexdigest()[:32]
