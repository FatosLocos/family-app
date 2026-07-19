"""Browser-side token management plus the bearer-token API surface for OpenClaw."""
import json

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from config.services import build_today_summary
from household.forms import TaskForm
from household.models import Task
from households.decorators import parent_required
from identity.models import User
from integrations.models import OpenClawToken
from integrations.openclaw_api import create_token, log_openclaw_action, require_openclaw_token, revoke_token
from notifications.models import Notification


@parent_required
@require_POST
def create_openclaw_token(request):
    _, token = create_token(request.household)
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


@require_openclaw_token
@require_GET
def api_today(request):
    summary = build_today_summary(request.household)
    log_openclaw_action(request.household, "vandaag", "Dagoverzicht opgevraagd")
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


@require_openclaw_token
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
        log_openclaw_action(request.household, "taak_toevoegen", "Taak toevoegen mislukt", status="error", detail=str(form.errors))
        return JsonResponse({"error": "Ongeldige taakvelden.", "details": form.errors}, status=400)
    task = form.save(commit=False)
    task.household = request.household
    task.save()
    log_openclaw_action(request.household, "taak_toevoegen", f"Taak '{task.title}' toegevoegd")
    return JsonResponse({"id": task.id, "title": task.title}, status=201)


@require_openclaw_token
@require_POST
def api_complete_task(request, task_id):
    task = get_object_or_404(Task.objects.for_household(request.household), pk=task_id)
    task.completed_at = timezone.now()
    task.save(update_fields=["completed_at", "updated_at"])
    Notification.objects.for_household(request.household).filter(dedupe_key=f"task-overdue:{task.id}", read_at__isnull=True).update(read_at=timezone.now())
    log_openclaw_action(request.household, "taak_afronden", f"Taak '{task.title}' afgerond")
    return JsonResponse({"id": task.id, "completed_at": task.completed_at.isoformat()})
