"""Browser-side token management plus the bearer-token API surface for OpenClaw."""
import json
from datetime import datetime, time

from django.contrib import messages
from django.db.models import Count, Max, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.views.decorators.http import require_GET, require_POST

from config.services import build_today_summary
from finance.models import BankAccount, Budget, Transaction
from home.models import HomeEntity
from home.services import HomeAssistantError, control_entity
from household.forms import ShoppingItemForm, TaskForm
from household.models import ShoppingItem, ShoppingList, Task, TaskList
from household.tasks import refresh_household_shopping_prices
from households.decorators import household_required, parent_required
from identity.models import User
from integrations.models import IntegrationConnection, OpenClawNotificationPreference, OpenClawToken
from integrations.openclaw_api import ALL_SCOPES, NOTIFICATION_CATEGORIES, create_token, log_openclaw_action, require_openclaw_token, revoke_token
from integrations.providers import ProviderError, dropbox_list_folder_contents, dropbox_overview, dropbox_read_file_text, dropbox_search
from notifications.models import Notification
from planning.forms import CalendarEventForm
from planning.models import CalendarEvent, CalendarSource


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
    list_name = str(payload.get("lijst") or "").strip()
    form = TaskForm(payload)
    form.fields["assigned_to"].queryset = User.objects.filter(memberships__household=request.household).distinct()
    if not form.is_valid():
        log_openclaw_action(request.household, "taak_toevoegen", "Taak toevoegen mislukt", status="error", detail=str(form.errors), user=request.openclaw_user)
        return JsonResponse({"error": "Ongeldige taakvelden.", "details": form.errors}, status=400)
    task = form.save(commit=False)
    task.household = request.household
    task.created_by_agent = True
    if list_name:
        task_list, _ = TaskList.objects.get_or_create(household=request.household, name=list_name)
        task.list = task_list
    task.save()
    log_openclaw_action(request.household, "taak_toevoegen", f"Taak '{task.title}' toegevoegd" + (f" aan lijstje '{list_name}'" if list_name else ""), user=request.openclaw_user)
    return JsonResponse({"id": task.id, "title": task.title, "lijst": task.list.name if task.list else None}, status=201)


@require_openclaw_token("taken:write")
@require_GET
def api_task_lists(request):
    lists = TaskList.objects.for_household(request.household)
    open_counts = {}
    counts = Task.objects.for_household(request.household).filter(completed_at__isnull=True, list__isnull=False).values("list_id").annotate(count=Count("id"))
    for row in counts:
        open_counts[row["list_id"]] = row["count"]
    log_openclaw_action(request.household, "taak_lijsten", "Lijstjes opgevraagd", user=request.openclaw_user)
    return JsonResponse({
        "lists": [{"id": task_list.id, "name": task_list.name, "open_task_count": open_counts.get(task_list.id, 0)} for task_list in lists],
    })


@require_openclaw_token("taken:write")
@require_POST
def api_add_task_list(request):
    try:
        payload = json.loads(request.body)
    except (TypeError, ValueError):
        return JsonResponse({"error": "Ongeldige aanvraag."}, status=400)
    name = str(payload.get("naam") or "").strip()
    if not name:
        return JsonResponse({"error": "Veld 'naam' is verplicht."}, status=400)
    task_list, created = TaskList.objects.get_or_create(household=request.household, name=name)
    log_openclaw_action(request.household, "taak_lijst_aanmaken", f"Lijstje '{task_list.name}' " + ("aangemaakt" if created else "bestond al"), user=request.openclaw_user)
    return JsonResponse({"id": task_list.id, "name": task_list.name, "created": created}, status=201 if created else 200)


@require_openclaw_token("taken:write")
@require_POST
def api_move_task(request, task_id):
    """Re-file an existing task under a (possibly new) list, without touching completion state."""
    task = get_object_or_404(Task.objects.for_household(request.household), pk=task_id)
    try:
        payload = json.loads(request.body) if request.body else {}
    except (TypeError, ValueError):
        payload = {}
    list_name = str(payload.get("lijst") or "").strip()
    task_list = None
    if list_name:
        task_list, _ = TaskList.objects.get_or_create(household=request.household, name=list_name)
    base_position = Task.objects.for_household(request.household).filter(list=task_list).aggregate(Max("position"))["position__max"]
    task.list = task_list
    task.position = (base_position + 1) if base_position is not None else 0
    task.save(update_fields=["list", "position", "updated_at"])
    log_openclaw_action(request.household, "taak_verplaatsen", f"Taak '{task.title}' verplaatst naar " + (f"lijstje '{task_list.name}'" if task_list else "Zonder lijst"), user=request.openclaw_user)
    return JsonResponse({"id": task.id, "title": task.title, "lijst": task_list.name if task_list else None})


@require_openclaw_token("vandaag:read")
@require_GET
def api_all_tasks(request):
    """Every open task (not capped to a handful like api_today's preview), with list membership."""
    tasks = Task.objects.for_household(request.household).filter(completed_at__isnull=True).select_related("list", "assigned_to").order_by("list_id", "position", "created_at")
    log_openclaw_action(request.household, "taken", "Volledige takenlijst opgevraagd", user=request.openclaw_user)
    return JsonResponse({
        "tasks": [
            {
                "id": task.id,
                "title": task.title,
                "notes": task.notes,
                "due_at": task.due_at.isoformat() if task.due_at else None,
                "priority": task.priority,
                "assigned_to": str(task.assigned_to) if task.assigned_to else None,
                "lijst": task.list.name if task.list else None,
                "created_by_agent": task.created_by_agent,
            }
            for task in tasks
        ],
    })


@require_openclaw_token("taken:write")
@require_POST
def api_complete_task(request, task_id):
    task = get_object_or_404(Task.objects.for_household(request.household), pk=task_id)
    try:
        payload = json.loads(request.body) if request.body else {}
    except (TypeError, ValueError):
        payload = {}
    task.completed_at = timezone.now()
    task.completion_reason = str(payload.get("reason") or "").strip()[:300]
    task.save(update_fields=["completed_at", "completion_reason", "updated_at"])
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


def _parse_agenda_bound(value):
    """Accept either a date ("2026-08-01") or a full ISO datetime for start/end filters."""
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        parsed_date = parse_date(value)
        if parsed_date is None:
            return None
        parsed = datetime.combine(parsed_date, time.min)
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


@require_openclaw_token("agenda:read")
@require_GET
def api_agenda(request):
    """No date filter by default — the whole calendar is returned unless start/end narrow it."""
    events = CalendarEvent.objects.for_household(request.household).order_by("starts_at")
    start = _parse_agenda_bound(request.GET.get("start"))
    end = _parse_agenda_bound(request.GET.get("end"))
    if start:
        events = events.filter(ends_at__gte=start)
    if end:
        events = events.filter(starts_at__lt=end)
    log_openclaw_action(request.household, "agenda", "Agenda opgevraagd", user=request.openclaw_user)
    return JsonResponse({
        "events": [
            {
                "id": event.id,
                "title": event.title,
                "starts_at": event.starts_at.isoformat(),
                "ends_at": event.ends_at.isoformat(),
                "is_all_day": event.is_all_day,
                "location": event.location,
                "notes": event.notes,
            }
            for event in events
        ],
    })


@require_openclaw_token("agenda:write")
@require_POST
def api_add_event(request):
    try:
        payload = json.loads(request.body)
    except (TypeError, ValueError):
        return JsonResponse({"error": "Ongeldige aanvraag."}, status=400)
    form = CalendarEventForm(payload)
    form.fields["participants"].queryset = User.objects.filter(memberships__household=request.household).distinct()
    if not form.is_valid():
        log_openclaw_action(request.household, "afspraak_toevoegen", "Afspraak toevoegen mislukt", status="error", detail=str(form.errors), user=request.openclaw_user)
        return JsonResponse({"error": "Ongeldige afspraakvelden.", "details": form.errors}, status=400)
    event = form.save(commit=False)
    event.household = request.household
    event.source, _ = CalendarSource.objects.get_or_create(household=request.household, provider=CalendarSource.Provider.LOCAL, name="Gezinsagenda", defaults={"is_read_only": False})
    event.save()
    form.save_m2m()
    log_openclaw_action(request.household, "afspraak_toevoegen", f"Afspraak '{event.title}' toegevoegd", user=request.openclaw_user)
    return JsonResponse({"id": event.id, "title": event.title, "starts_at": event.starts_at.isoformat()}, status=201)


@require_openclaw_token("geld:read")
@require_GET
def api_finance(request):
    """Read-only: account balances, recent transactions, budget status. No mutating finance endpoint exists yet."""
    month_start = timezone.localdate().replace(day=1)
    accounts = BankAccount.objects.for_household(request.household).filter(is_active=True).select_related("connection")
    transactions = Transaction.objects.for_household(request.household).select_related("account")[:20]
    monthly_expenses = Transaction.objects.for_household(request.household).filter(booked_at__gte=month_start, amount__lt=0)
    budgets = []
    for budget in Budget.objects.for_household(request.household):
        spent = None
        remaining = None
        if budget.category:
            spent = abs(monthly_expenses.filter(category__iexact=budget.category).aggregate(total=Sum("amount"))["total"] or 0)
            remaining = budget.monthly_limit - spent
        budgets.append({
            "name": budget.name,
            "category": budget.category,
            "monthly_limit": str(budget.monthly_limit),
            "spent_this_month": str(spent) if spent is not None else None,
            "remaining_this_month": str(remaining) if remaining is not None else None,
        })
    log_openclaw_action(request.household, "geld", "Financieel overzicht opgevraagd", user=request.openclaw_user)
    return JsonResponse({
        "accounts": [
            {"name": account.name, "iban": account.iban, "balance": str(account.balance) if account.balance is not None else None, "currency": account.currency}
            for account in accounts
        ],
        "recent_transactions": [
            {
                "id": transaction.id,
                "booked_at": transaction.booked_at.isoformat(),
                "description": transaction.description,
                "counterparty": transaction.counterparty,
                "amount": str(transaction.amount),
                "currency": transaction.currency,
                "category": transaction.category,
            }
            for transaction in transactions
        ],
        "budgets": budgets,
    })


@household_required
@require_POST
def save_openclaw_notification_preferences(request):
    categories = [category for category in request.POST.getlist("categories") if category in NOTIFICATION_CATEGORIES]
    OpenClawNotificationPreference.objects.update_or_create(
        household=request.household, user=request.user, defaults={"categories": categories},
    )
    messages.success(request, "Voorkeuren voor proactieve meldingen opgeslagen.")
    return redirect("integrations:index")


@require_openclaw_token("meldingen:read")
@require_GET
def api_pending_notifications(request):
    preference = OpenClawNotificationPreference.objects.for_household(request.household).filter(user=request.openclaw_user).first()
    categories = set(preference.categories) if preference else set()
    log_openclaw_action(request.household, "meldingen", "Openstaande meldingen opgevraagd", user=request.openclaw_user)
    if not categories:
        return JsonResponse({"notifications": []})
    pending = [
        notification
        for notification in Notification.objects.for_household(request.household).filter(delivered_to_openclaw_at__isnull=True)
        if (notification.dedupe_key or "").split(":")[0] in categories
    ]
    return JsonResponse({
        "notifications": [
            {"id": notification.id, "title": notification.title, "body": notification.body, "kind": notification.kind, "created_at": notification.created_at.isoformat()}
            for notification in pending
        ],
    })


@require_openclaw_token("meldingen:write")
@require_POST
def api_mark_notifications_delivered(request):
    try:
        payload = json.loads(request.body)
    except (TypeError, ValueError):
        return JsonResponse({"error": "Ongeldige aanvraag."}, status=400)
    ids = payload.get("ids")
    if not isinstance(ids, list) or not ids:
        return JsonResponse({"error": "Veld 'ids' is verplicht en moet een niet-lege lijst zijn."}, status=400)
    updated = Notification.objects.for_household(request.household).filter(id__in=ids, delivered_to_openclaw_at__isnull=True).update(delivered_to_openclaw_at=timezone.now())
    log_openclaw_action(request.household, "meldingen_afgehandeld", f"{updated} melding(en) gemarkeerd als afgeleverd", user=request.openclaw_user)
    return JsonResponse({"updated": updated})


def _dropbox_connection(request):
    return IntegrationConnection.objects.for_household(request.household).filter(provider=IntegrationConnection.Provider.DROPBOX).first()


@require_openclaw_token("dropbox:read")
@require_GET
def api_dropbox_overview(request):
    connection = _dropbox_connection(request)
    if not connection:
        return JsonResponse({"error": "Dropbox is niet gekoppeld in Instellingen."}, status=400)
    try:
        entries = dropbox_overview(connection)
    except ProviderError as error:
        log_openclaw_action(request.household, "dropbox", "Dropbox-overzicht ophalen mislukt", status="error", detail=str(error), user=request.openclaw_user)
        return JsonResponse({"error": str(error)}, status=400)
    log_openclaw_action(request.household, "dropbox", "Dropbox-overzicht opgevraagd", user=request.openclaw_user)
    return JsonResponse({"entries": entries})


@require_openclaw_token("dropbox:read")
@require_GET
def api_dropbox_list(request):
    connection = _dropbox_connection(request)
    if not connection:
        return JsonResponse({"error": "Dropbox is niet gekoppeld in Instellingen."}, status=400)
    path = request.GET.get("pad", "")
    try:
        entries = dropbox_list_folder_contents(connection, path)
    except ProviderError as error:
        log_openclaw_action(request.household, "dropbox", f"Map '{path}' bekijken mislukt", status="error", detail=str(error), user=request.openclaw_user)
        return JsonResponse({"error": str(error)}, status=400)
    log_openclaw_action(request.household, "dropbox", f"Map '{path or '/'}' bekeken", user=request.openclaw_user)
    return JsonResponse({"entries": entries})


@require_openclaw_token("dropbox:read")
@require_GET
def api_dropbox_search(request):
    connection = _dropbox_connection(request)
    if not connection:
        return JsonResponse({"error": "Dropbox is niet gekoppeld in Instellingen."}, status=400)
    query = request.GET.get("q", "").strip()
    if not query:
        return JsonResponse({"error": "Parameter 'q' is verplicht."}, status=400)
    path = request.GET.get("pad", "")
    try:
        entries = dropbox_search(connection, query, path=path)
    except ProviderError as error:
        log_openclaw_action(request.household, "dropbox", f"Zoeken naar '{query}' mislukt", status="error", detail=str(error), user=request.openclaw_user)
        return JsonResponse({"error": str(error)}, status=400)
    log_openclaw_action(request.household, "dropbox", f"Gezocht naar '{query}'", user=request.openclaw_user)
    return JsonResponse({"entries": entries})


@require_openclaw_token("dropbox:content")
@require_GET
def api_dropbox_read(request):
    connection = _dropbox_connection(request)
    if not connection:
        return JsonResponse({"error": "Dropbox is niet gekoppeld in Instellingen."}, status=400)
    path = request.GET.get("pad", "")
    if not path:
        return JsonResponse({"error": "Parameter 'pad' is verplicht."}, status=400)
    try:
        result = dropbox_read_file_text(connection, path)
    except ProviderError as error:
        log_openclaw_action(request.household, "dropbox", f"Bestand '{path}' lezen mislukt", status="error", detail=str(error), user=request.openclaw_user)
        return JsonResponse({"error": str(error)}, status=400)
    log_openclaw_action(request.household, "dropbox", f"Bestand '{path}' gelezen", user=request.openclaw_user)
    return JsonResponse(result)
