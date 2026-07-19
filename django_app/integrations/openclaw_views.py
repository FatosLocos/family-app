"""Browser-side token management plus the bearer-token API surface for OpenClaw."""
import json

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from config.services import build_today_summary
from home.models import HomeEntity
from home.services import HomeAssistantError, control_entity
from household.forms import ShoppingItemForm, TaskForm
from household.models import ShoppingItem, ShoppingList, Task
from household.tasks import refresh_household_shopping_prices
from households.decorators import parent_required
from identity.models import User
from integrations.models import OpenClawToken
from integrations.openclaw_api import ALL_SCOPES, create_token, log_openclaw_action, require_openclaw_token, revoke_token
from notifications.models import Notification


@parent_required
@require_POST
def create_openclaw_token(request):
    scopes = [scope for scope in request.POST.getlist("scopes") if scope in ALL_SCOPES]
    _, token = create_token(request.household, request.user, scopes=scopes)
    request.session["openclaw_token"] = token
    messages.success(request, "Nieuw OpenClaw-token gemaakt. Bewaar het meteen — het wordt niet nogmaals getoond.")
    return redirect("integrations:index")


@parent_required
@require_POST
def revoke_openclaw_token(request, token_id):
    token = get_object_or_404(OpenClawToken.objects.for_household(request.household), pk=token_id)
    revoke_token(token)
    messages.success(request, "OpenClaw-token ingetrokken.")
    return redirect("integrations:index")


@require_openclaw_token("vandaag:read")
@require_GET
def api_today(request):
    summary = build_today_summary(request.household)
    log_openclaw_action(request.household, "vandaag", "Dagoverzicht opgevraagd", user=request.openclaw_user)
    return JsonResponse({
        "today": summary["today"].isoformat(),
        "tasks_open": [
            {"id": task.id, "title": task.title, "due_at": task.due_at.isoformat() if task.due_at else None, "priority": task.priority}
            for task in summary["tasks"]
        ],
        "tasks_due_today": {"total": summary["tasks_due_today_total"], "done": summary["tasks_due_today_done"]},
        "shopping_open_count": summary["shopping_open_count"],
        "shopping_items": [{"id": item.id, "name": item.name, "quantity": item.quantity} for item in summary["shopping_items"]],
        "events_today": [
            {
                "id": event.id,
                "title": event.title,
                "starts_at": event.starts_at.isoformat(),
                "ends_at": event.ends_at.isoformat(),
                "is_all_day": event.is_all_day,
                "location": event.location,
            }
            for event in summary["events_today"]
        ],
    })


@require_openclaw_token("taken:write")
@require_POST
def api_add_task(request):
    try:
        payload = json.loads(request.body)
    except (TypeError, ValueError):
        return JsonResponse({"error": "Ongeldige aanvraag."}, status=400)
    payload.setdefault("priority", Task.Priority.NORMAL)
    form = TaskForm(payload)
    form.fields["assigned_to"].queryset = User.objects.filter(memberships__household=request.household).distinct()
    if not form.is_valid():
        log_openclaw_action(request.household, "taak_toevoegen", "Taak toevoegen mislukt", status="error", detail=str(form.errors), user=request.openclaw_user)
        return JsonResponse({"error": "Ongeldige taakvelden.", "details": form.errors}, status=400)
    task = form.save(commit=False)
    task.household = request.household
    task.save()
    log_openclaw_action(request.household, "taak_toevoegen", f"Taak '{task.title}' toegevoegd", user=request.openclaw_user)
    return JsonResponse({"id": task.id, "title": task.title}, status=201)


@require_openclaw_token("taken:write")
@require_POST
def api_complete_task(request, task_id):
    task = get_object_or_404(Task.objects.for_household(request.household), pk=task_id)
    task.completed_at = timezone.now()
    task.save(update_fields=["completed_at", "updated_at"])
    Notification.objects.for_household(request.household).filter(dedupe_key=f"task-overdue:{task.id}", read_at__isnull=True).update(read_at=timezone.now())
    log_openclaw_action(request.household, "taak_afronden", f"Taak '{task.title}' afgerond", user=request.openclaw_user)
    return JsonResponse({"id": task.id, "completed_at": task.completed_at.isoformat()})


@require_openclaw_token("boodschappen:read")
@require_GET
def api_shopping_list(request):
    items = ShoppingItem.objects.for_household(request.household).filter(completed_at__isnull=True).order_by("created_at")
    log_openclaw_action(request.household, "boodschappen", "Boodschappenlijst opgevraagd", user=request.openclaw_user)
    return JsonResponse({
        "items": [{"id": item.id, "name": item.name, "quantity": item.quantity, "category": item.category} for item in items],
    })


@require_openclaw_token("boodschappen:write")
@require_POST
def api_add_shopping_item(request):
    try:
        payload = json.loads(request.body)
    except (TypeError, ValueError):
        return JsonResponse({"error": "Ongeldige aanvraag."}, status=400)
    payload.setdefault("recurrence_days", 7)
    form = ShoppingItemForm(payload)
    if not form.is_valid():
        log_openclaw_action(request.household, "boodschap_toevoegen", "Boodschap toevoegen mislukt", status="error", detail=str(form.errors), user=request.openclaw_user)
        return JsonResponse({"error": "Ongeldige velden.", "details": form.errors}, status=400)
    shopping_list, _ = ShoppingList.objects.get_or_create(household=request.household, name="Boodschappen", defaults={"is_default": True})
    item = form.save(commit=False)
    item.household = request.household
    item.list = shopping_list
    item.save()
    refresh_household_shopping_prices.delay(request.household.id)
    log_openclaw_action(request.household, "boodschap_toevoegen", f"Boodschap '{item.name}' toegevoegd", user=request.openclaw_user)
    return JsonResponse({"id": item.id, "name": item.name}, status=201)


@require_openclaw_token("huis:read")
@require_GET
def api_home_entities(request):
    entities = HomeEntity.objects.for_household(request.household).filter(is_available=True).order_by("domain", "name")
    log_openclaw_action(request.household, "huis_lezen", "Apparaten opgevraagd", user=request.openclaw_user)
    return JsonResponse({
        "entities": [
            {
                "id": entity.id,
                "name": entity.name,
                "domain": entity.domain,
                "state": entity.state,
                "source": entity.source,
                "is_supported": entity.is_supported,
                "attributes": entity.attributes if isinstance(entity.attributes, dict) else {},
            }
            for entity in entities
        ],
    })


@require_openclaw_token("huis:write")
@require_POST
def api_home_control(request, entity_id):
    entity = get_object_or_404(HomeEntity.objects.for_household(request.household), pk=entity_id)
    try:
        payload = json.loads(request.body)
    except (TypeError, ValueError):
        return JsonResponse({"error": "Ongeldige aanvraag."}, status=400)
    action = str(payload.get("action") or "").strip()
    if not action:
        return JsonResponse({"error": "Veld 'action' is verplicht."}, status=400)
    try:
        result = control_entity(request.household, entity, action, payload.get("value")) or {}
    except HomeAssistantError as error:
        log_openclaw_action(request.household, "huis_bedienen", f"Bediening '{action}' op '{entity.name}' mislukt", status="error", detail=str(error), user=request.openclaw_user)
        return JsonResponse({"error": str(error)}, status=400)
    entity.refresh_from_db()
    log_openclaw_action(request.household, "huis_bedienen", f"'{entity.name}': {action}", user=request.openclaw_user)
    return JsonResponse({"id": entity.id, "name": entity.name, "state": entity.state, **result})
