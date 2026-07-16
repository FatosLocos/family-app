from collections import defaultdict

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Max
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from datetime import timedelta
from decimal import Decimal
import json
import re

from django.utils import timezone
from django.views.decorators.http import require_POST

from households.decorators import household_required
from household.forms import MealIngredientForm, MealPlanForm, PantryItemForm, ReceiptForm, RoutineForm, ShoppingItemForm, ShoppingPriceForm, TaskForm
from household.models import MealIngredient, MealPlan, PantryItem, Receipt, ReceiptLineItem, Routine, ShoppingItem, ShoppingList, ShoppingPrice, ShoppingPriceProviderStatus, ShoppingPriceSnapshot, Task, TaskList
from household.price_history import save_price_observation
from household.receipt_matching import match_receipt_to_transaction
from notifications.models import Notification
from household.tasks import process_receipt_ocr, refresh_household_shopping_prices


def _is_htmx_request(request) -> bool:
    """Check if request is an HTMX partial request."""
    return request.headers.get("HX-Request") == "true"


def _form_error_response(request, template: str, context: dict, status: int = 422):
    """Return form with validation errors for HTMX requests."""
    response = render(request, template, context, status=status)
    response["HX-Reswap"] = "innerHTML"
    return response


def _shopping_item_multiplier(item):
    """Use an explicit count such as '2 pakken'; weights stay one product."""
    match = re.match(r"^\s*(\d+)\s*(?:x\b|stuks?\b|pakken?\b|flessen?\b|zakken?\b|dozen?\b)", item.quantity.casefold())
    return Decimal(match.group(1)) if match else Decimal("1")


def _receipt_retailer_code(retailer: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "", str(retailer or "").casefold())
    if normalized in {"ah", "albertheijn"}:
        return ShoppingPrice.Retailer.ALBERT_HEIJN
    if normalized == "jumbo":
        return ShoppingPrice.Retailer.JUMBO
    if normalized == "lidl":
        return ShoppingPrice.Retailer.LIDL
    if normalized == "kaufland":
        return ShoppingPrice.Retailer.KAUFLAND
    return ""


def _receipt_product_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _create_meal_ingredients(meal, ingredient_lines):
    """Turn a compact meal form into structured, reusable grocery ingredients."""
    for raw_line in ingredient_lines.splitlines()[:40]:
        parts = [part.strip() for part in raw_line.split("|", maxsplit=2)]
        name = parts[0] if parts else ""
        if not name:
            continue
        MealIngredient.objects.create(
            household=meal.household,
            meal=meal,
            name=name[:200],
            quantity=(parts[1] if len(parts) > 1 else "")[:60],
            category=(parts[2] if len(parts) > 2 else "")[:80],
        )


@household_required
def index(request):
    tab = request.GET.get("tab", "taken")
    task_filter = request.GET.get("filter", "open")
    shopping_filter = request.GET.get("shopping_filter", "open")
    household = request.household
    default_list, _ = ShoppingList.objects.get_or_create(household=household, name="Boodschappen", defaults={"is_default": True})
    tasks = Task.objects.for_household(household).select_related("assigned_to", "list")
    if task_filter == "vandaag":
        tasks = tasks.filter(completed_at__isnull=True, due_at__date=timezone.localdate())
    elif task_filter == "afgerond":
        tasks = tasks.filter(completed_at__isnull=False)
    elif task_filter != "alles":
        tasks = tasks.filter(completed_at__isnull=True)
    task_lists = list(TaskList.objects.for_household(household))
    tasks = list(tasks[:300])
    tasks_by_list = defaultdict(list)
    for task in tasks:
        tasks_by_list[task.list_id].append(task)
    task_groups = [{"list": task_list, "tasks": tasks_by_list.get(task_list.id, [])} for task_list in task_lists]
    task_groups.append({"list": None, "tasks": tasks_by_list.get(None, [])})
    members = request.user.__class__.objects.filter(memberships__household=household).distinct()
    task_form = TaskForm()
    task_form.fields["assigned_to"].queryset = members
    routine_form = RoutineForm()
    routine_form.fields["assigned_to"].queryset = members
    receipts = list(
        Receipt.objects.for_household(household)
        .select_related("transaction", "transaction__account")
        .prefetch_related("line_items__shopping_item__prices")[:30]
    )
    for receipt in receipts:
        receipt.bank_amount = abs(receipt.transaction.amount) if receipt.transaction_id else None
        receipt.amount_difference = abs(receipt.bank_amount - receipt.total_amount) if receipt.transaction_id and receipt.total_amount else None
        receipt.recognized_line_items = list(receipt.line_items.all())
        retailer_code = _receipt_retailer_code(receipt.retailer)
        for line_item in receipt.recognized_line_items:
            line_item.comparison_price = None
            line_item.comparison_expected = None
            line_item.comparison_delta = None
            if not retailer_code or not line_item.shopping_item_id:
                continue
            current_price = next(
                (price for price in line_item.shopping_item.prices.all() if price.retailer == retailer_code),
                None,
            )
            if current_price is None:
                continue
            line_item.comparison_price = current_price
            quantity = line_item.quantity if line_item.quantity and line_item.quantity > 0 else Decimal("1")
            line_item.comparison_expected = current_price.price * quantity
            line_item.comparison_delta = line_item.total_price - line_item.comparison_expected
    frequent_products = list(
        ShoppingItem.objects.for_household(household)
        .filter(completed_at__gte=timezone.now() - timedelta(days=90))
        .values("name")
        .annotate(times_bought=Count("id"), last_bought=Max("completed_at"))
        .order_by("-times_bought", "-last_bought")[:8]
    )
    receipt_product_map = {}
    receipt_product_rows = (
        ReceiptLineItem.objects.for_household(household)
        .filter(receipt__ocr_status=Receipt.OcrStatus.COMPLETE, receipt__purchased_on__gte=timezone.localdate() - timedelta(days=90))
        .select_related("shopping_item", "receipt")
        .order_by("-receipt__purchased_on", "-id")
    )
    for line_item in receipt_product_rows:
        label = line_item.shopping_item.name if line_item.shopping_item_id else line_item.name
        key = _receipt_product_key(label)
        if not key:
            continue
        row = receipt_product_map.setdefault(
            key,
            {"name": label, "times_bought": 0, "last_bought": line_item.receipt.purchased_on, "total_spend": Decimal("0")},
        )
        row["times_bought"] += 1
        row["total_spend"] += line_item.total_price
        if line_item.receipt.purchased_on and line_item.receipt.purchased_on > row["last_bought"]:
            row["last_bought"] = line_item.receipt.purchased_on
    receipt_products = sorted(receipt_product_map.values(), key=lambda row: (-row["times_bought"], -row["last_bought"].toordinal()))[:8]
    price_items = list(ShoppingItem.objects.for_household(household).filter(list=default_list, completed_at__isnull=True).prefetch_related("prices", "offers")[:20])
    recurring_item_map = {}
    for item in (
        ShoppingItem.objects.for_household(household)
        .filter(list=default_list, recurring=True)
        .order_by("name", "completed_at")
    ):
        key = _receipt_product_key(item.name)
        existing = recurring_item_map.get(key)
        if existing is None or (item.completed_at is None and existing.completed_at is not None) or (
            item.completed_at and existing.completed_at and item.completed_at > existing.completed_at
        ):
            recurring_item_map[key] = item
    recurring_items = list(recurring_item_map.values())
    for item in recurring_items:
        item.is_on_shopping_list = item.completed_at is None
        if item.completed_at is None:
            item.next_replenish_on = None
            item.recurrence_status = "Staat op de lijst"
            continue
        item.next_replenish_on = timezone.localtime(item.completed_at).date() + timedelta(days=item.recurrence_days)
        days_until = (item.next_replenish_on - timezone.localdate()).days
        item.recurrence_status = "Vandaag opnieuw" if days_until <= 0 else f"Over {days_until} dag{'en' if days_until != 1 else ''}"
    recurring_items.sort(key=lambda item: (not item.is_on_shopping_list, item.next_replenish_on or timezone.localdate(), item.name.casefold()))
    shopping_items = ShoppingItem.objects.for_household(household).filter(list=default_list)
    if shopping_filter == "afgerond":
        shopping_items = shopping_items.filter(completed_at__isnull=False)
    elif shopping_filter == "alles":
        pass
    else:
        shopping_filter = "open"
        shopping_items = shopping_items.filter(completed_at__isnull=True)
    snapshots_by_item = {}
    for snapshot in ShoppingPriceSnapshot.objects.for_household(household).filter(item__in=price_items).order_by("item_id", "-observed_at"):
        if len(snapshots_by_item.setdefault(snapshot.item_id, [])) < 8:
            snapshots_by_item[snapshot.item_id].append(snapshot)
    price_trend_map = {}
    for snapshot in ShoppingPriceSnapshot.objects.for_household(household).select_related("item").order_by("item_id", "retailer", "observed_at")[:500]:
        key = (snapshot.item_id, snapshot.retailer)
        trend = price_trend_map.setdefault(key, {"item_name": snapshot.item.name, "retailer": snapshot.retailer, "retailer_label": snapshot.get_retailer_display(), "first": snapshot, "latest": snapshot})
        trend["latest"] = snapshot
    price_trends = []
    for trend in price_trend_map.values():
        delta = trend["latest"].price - trend["first"].price
        if not delta:
            continue
        price_trends.append({
            "item_name": trend["item_name"],
            "retailer_label": trend["retailer_label"],
            "first_price": trend["first"].price,
            "current_price": trend["latest"].price,
            "delta": delta,
            "direction": "up" if delta > 0 else "down",
        })
    price_trends = sorted(price_trends, key=lambda trend: abs(trend["delta"]), reverse=True)[:10]
    pantry_items = list(PantryItem.objects.for_household(household).order_by("category", "name"))
    for pantry_item in pantry_items:
        pantry_item.is_low = pantry_item.quantity <= pantry_item.minimum_quantity
        pantry_item.is_expiring = bool(pantry_item.expires_on and pantry_item.expires_on <= timezone.localdate() + timedelta(days=7))
    retailer_choices = ShoppingPrice.Retailer.choices
    retailer_marks = {
        ShoppingPrice.Retailer.ALBERT_HEIJN: "AH",
        ShoppingPrice.Retailer.JUMBO: "J",
        ShoppingPrice.Retailer.LIDL: "L",
        ShoppingPrice.Retailer.KAUFLAND: "K",
    }
    price_rows = []
    latest_price_at = None
    provider_statuses = list(
        ShoppingPriceProviderStatus.objects.for_household(household).order_by("provider")
    )
    retailer_totals = {retailer: {"retailer": retailer, "label": label, "total": Decimal("0"), "priced_items": 0} for retailer, label in retailer_choices}
    for item in price_items:
        prices_by_retailer = {price.retailer: price for price in item.prices.all()}
        offers_by_retailer = {offer.retailer: offer for offer in item.offers.all()}
        for price in prices_by_retailer.values():
            if latest_price_at is None or price.observed_at > latest_price_at:
                latest_price_at = price.observed_at
            totals = retailer_totals[price.retailer]
            totals["total"] += price.price * _shopping_item_multiplier(item)
            totals["priced_items"] += 1
        price_rows.append({
            "item": item,
            "history": snapshots_by_item.get(item.id, []),
            "cells": [
                {
                    "retailer": retailer,
                    "label": label,
                    "price": prices_by_retailer.get(retailer),
                    "offer": offers_by_retailer.get(retailer),
                }
                for retailer, label in retailer_choices
            ],
        })
    context = {
        "tab": tab, "task_filter": task_filter, "shopping_filter": shopping_filter, "today": timezone.localdate(),
        "task_form": task_form, "shopping_form": ShoppingItemForm(initial={"recurring": tab == "terugkerend"}), "meal_form": MealPlanForm(), "pantry_form": PantryItemForm(), "routine_form": routine_form,
        "tasks": tasks,
        "task_lists": task_lists,
        "task_groups": task_groups,
        "shopping_items": shopping_items[:50],
        "recurring_items": recurring_items,
        "price_items": price_items,
        "price_rows": price_rows,
        "retailer_choices": retailer_choices,
        "price_totals": [
            {**total, "missing_items": len(price_items) - total["priced_items"]}
            for total in retailer_totals.values()
        ],
        "price_retailer_headers": [
            {
                **total,
                "mark": retailer_marks[retailer],
                "missing_items": len(price_items) - total["priced_items"],
            }
            for retailer, total in retailer_totals.items()
        ],
        "latest_price_at": latest_price_at,
        "price_provider_statuses": provider_statuses,
        "price_form": ShoppingPriceForm(),
        "receipts": receipts,
        "frequent_products": frequent_products,
        "receipt_products": receipt_products,
        "price_trends": price_trends[:8],
        "receipt_form": ReceiptForm(),
        "meals": MealPlan.objects.for_household(household).prefetch_related("ingredients").order_by("planned_for")[:14],
        "pantry_items": pantry_items,
        "low_pantry_count": sum(item.is_low for item in pantry_items),
        "routines": Routine.objects.for_household(household).filter(is_active=True).select_related("assigned_to").order_by("next_due_on", "title"),
        "members": members,
    }
    return render(request, "household/index.html", context)


@household_required
@require_POST
def add_task(request):
    form = TaskForm(request.POST)
    form.fields["assigned_to"].queryset = request.user.__class__.objects.filter(memberships__household=request.household).distinct()
    if form.is_valid():
        task = form.save(commit=False)
        task.household = request.household
        task.save()
        if _is_htmx_request(request):
            return render(request, "household/partials/task_form_success.html", {"message": "Taak toegevoegd."})
        messages.success(request, "Taak toegevoegd.")
    else:
        if _is_htmx_request(request):
            return _form_error_response(request, "household/partials/task_form.html", {"form": form})
        messages.error(request, "Controleer de taakvelden.")
    return redirect("household:index")


@household_required
@require_POST
def toggle_task(request, task_id):
    task = get_object_or_404(Task.objects.for_household(request.household), pk=task_id)
    task.completed_at = None if task.completed_at else timezone.now()
    task.save(update_fields=["completed_at", "updated_at"])
    if task.completed_at:
        Notification.objects.for_household(request.household).filter(dedupe_key=f"task-overdue:{task.id}", read_at__isnull=True).update(read_at=timezone.now())
    if request.headers.get("HX-Request") and request.headers.get("HX-Target", "").startswith("today-task-"):
        return render(request, "today/partials/task_row.html", {"task": task})
    if request.headers.get("HX-Request"):
        return render(request, "household/partials/task_row.html", {"task": task})
    if request.GET.get("next") == "today":
        return redirect("today")
    return redirect("household:index")


@household_required
@require_POST
def add_task_list(request):
    name = request.POST.get("name", "").strip()
    if name:
        TaskList.objects.get_or_create(household=request.household, name=name)
        messages.success(request, "Lijstje toegevoegd.")
    else:
        messages.error(request, "Geef het lijstje een naam.")
    return _household_tab_redirect("taken")


@household_required
@require_POST
def delete_task_list(request, list_id):
    task_list = get_object_or_404(TaskList.objects.for_household(request.household), pk=list_id)
    with transaction.atomic():
        base_position = Task.objects.for_household(request.household).filter(list__isnull=True).aggregate(Max("position"))["position__max"]
        next_position = (base_position + 1) if base_position is not None else 0
        for offset, task in enumerate(Task.objects.for_household(request.household).filter(list=task_list).order_by("position", "created_at")):
            task.list = None
            task.position = next_position + offset
            task.save(update_fields=["list", "position", "updated_at"])
        task_list.delete()
    messages.success(request, "Lijstje verwijderd. De taken staan nu onder Zonder lijst.")
    return _household_tab_redirect("taken")


@household_required
@require_POST
def reorder_tasks(request):
    """Persist a drag-and-drop move: task_id into target_list_id, at its new spot in ordered_task_ids.

    ordered_task_ids only contains the tasks currently VISIBLE under the active
    filter pill (open/vandaag/alles/afgerond), so positions are merged into the
    full underlying sequence rather than overwritten wholesale — otherwise a
    hidden task (e.g. already completed while "Open" is active) would collide
    with a visible one sharing the same position slot.
    """
    try:
        payload = json.loads(request.body)
    except (TypeError, ValueError):
        return JsonResponse({"error": "Ongeldige aanvraag."}, status=400)
    task_id = payload.get("task_id")
    target_list_id = payload.get("target_list_id")
    ordered_task_ids = payload.get("ordered_task_ids")
    if not isinstance(task_id, int) or not isinstance(ordered_task_ids, list) or not ordered_task_ids:
        return JsonResponse({"error": "Ongeldige aanvraag."}, status=400)
    if len(set(ordered_task_ids)) != len(ordered_task_ids):
        return JsonResponse({"error": "Dubbele taak in volgorde."}, status=400)

    household = request.household
    task = get_object_or_404(Task.objects.for_household(household), pk=task_id)
    target_list = None
    if target_list_id is not None:
        target_list = get_object_or_404(TaskList.objects.for_household(household), pk=target_list_id)

    valid_ids = set(Task.objects.for_household(household).filter(pk__in=ordered_task_ids).values_list("id", flat=True))
    if task_id not in valid_ids or set(ordered_task_ids) - valid_ids:
        return JsonResponse({"error": "Onbekende taak."}, status=400)

    def _renumber(list_obj, incoming_order):
        current = list(Task.objects.for_household(household).filter(list=list_obj).order_by("position", "created_at"))
        incoming_queue = list(incoming_order)
        merged_ids = []
        for existing_task in current:
            if existing_task.id in incoming_order:
                merged_ids.append(incoming_queue.pop(0))
            else:
                merged_ids.append(existing_task.id)
        by_id = {t.id: t for t in current}
        for index, tid in enumerate(merged_ids):
            existing_task = by_id.get(tid)
            if existing_task is not None and existing_task.position != index:
                existing_task.position = index
                existing_task.save(update_fields=["position", "updated_at"])

    with transaction.atomic():
        source_list_id = task.list_id
        target_list_pk = target_list.id if target_list else None
        task.list = target_list
        task.save(update_fields=["list", "updated_at"])
        _renumber(target_list, ordered_task_ids)
        if source_list_id != target_list_pk:
            source_list = TaskList.objects.filter(household=household, pk=source_list_id).first() if source_list_id else None
            _renumber(source_list, [])
    return JsonResponse({"status": "ok"})


@household_required
@require_POST
def add_shopping_item(request):
    form = ShoppingItemForm(request.POST)
    if form.is_valid():
        shopping_list, _ = ShoppingList.objects.get_or_create(household=request.household, name="Boodschappen", defaults={"is_default": True})
        item = form.save(commit=False)
        item.household = request.household
        item.list = shopping_list
        item.save()
        refresh_household_shopping_prices.delay(request.household.id)
        if _is_htmx_request(request):
            return render(request, "household/partials/item_form_success.html", {"message": "Boodschap toegevoegd."})
        messages.success(request, "Boodschap toegevoegd. Prijzen worden bijgewerkt.")
    else:
        if _is_htmx_request(request):
            return _form_error_response(request, "household/partials/shopping_item_form.html", {"form": form})
        messages.error(request, "Vul een productnaam in.")
    return redirect("household:index")


@household_required
@require_POST
def toggle_shopping_item(request, item_id):
    item = get_object_or_404(ShoppingItem.objects.for_household(request.household), pk=item_id)
    item.completed_at = None if item.completed_at else timezone.now()
    item.save(update_fields=["completed_at", "updated_at"])
    if request.headers.get("HX-Request"):
        if request.headers.get("HX-Target", "").startswith("today-shopping-"):
            return render(request, "today/partials/shopping_row.html", {"item": item})
        shopping_filter = request.GET.get("shopping_filter", "open")
        if (shopping_filter == "open" and item.completed_at) or (shopping_filter == "afgerond" and not item.completed_at):
            return HttpResponse("")
        return render(request, "household/partials/shopping_row.html", {"item": item, "shopping_filter": shopping_filter})
    return redirect("household:index")


@household_required
@require_POST
def add_meal(request):
    form = MealPlanForm(request.POST)
    if form.is_valid():
        meal = form.save(commit=False)
        meal.household = request.household
        meal.save()
        _create_meal_ingredients(meal, form.cleaned_data["ingredients_text"])
        if _is_htmx_request(request):
            return render(request, "household/partials/item_form_success.html", {"message": "Maaltijd ingepland."})
        messages.success(request, "Maaltijd ingepland.")
    else:
        if _is_htmx_request(request):
            return _form_error_response(request, "household/partials/meal_form.html", {"form": form})
    return _household_tab_redirect("maaltijden")


@household_required
@require_POST
def add_routine(request):
    form = RoutineForm(request.POST)
    form.fields["assigned_to"].queryset = request.user.__class__.objects.filter(memberships__household=request.household).distinct()
    if form.is_valid():
        routine = form.save(commit=False)
        routine.household = request.household
        routine.save()
        if _is_htmx_request(request):
            return render(request, "household/partials/item_form_success.html", {"message": "Routine toegevoegd."})
        messages.success(request, "Routine toegevoegd.")
    else:
        if _is_htmx_request(request):
            return _form_error_response(request, "household/partials/routine_form.html", {"form": form, "request": request})
    return redirect("household:index")


@household_required
@require_POST
def complete_routine(request, routine_id):
    routine = get_object_or_404(Routine.objects.for_household(request.household), pk=routine_id, is_active=True)
    routine.last_completed_at = timezone.now()
    routine.next_due_on = timezone.localdate() + timedelta(days=routine.interval_days)
    routine.save(update_fields=["last_completed_at", "next_due_on", "updated_at"])
    messages.success(request, f"{routine.title} is afgerond. Volgende keer: {routine.next_due_on:%d-%m}.")
    return _household_tab_redirect("routines")


def _household_tab_redirect(tab: str):
    return redirect(f"{reverse('household:index')}?tab={tab}")


@household_required
@require_POST
def update_task(request, task_id):
    task = get_object_or_404(Task.objects.for_household(request.household), pk=task_id)
    form = TaskForm(request.POST, instance=task)
    form.fields["assigned_to"].queryset = request.user.__class__.objects.filter(memberships__household=request.household).distinct()
    if form.is_valid():
        form.save()
        messages.success(request, "Taak aangepast.")
    else:
        messages.error(request, "Controleer de taakvelden.")
    return _household_tab_redirect("taken")


@household_required
@require_POST
def delete_task(request, task_id):
    task = get_object_or_404(Task.objects.for_household(request.household), pk=task_id)
    task.delete()
    messages.success(request, "Taak verwijderd.")
    return _household_tab_redirect("taken")


@household_required
@require_POST
def update_shopping_item(request, item_id):
    item = get_object_or_404(ShoppingItem.objects.for_household(request.household), pk=item_id)
    form = ShoppingItemForm(request.POST, instance=item)
    if form.is_valid():
        form.save()
        refresh_household_shopping_prices.delay(request.household.id)
        messages.success(request, "Boodschap aangepast.")
    else:
        messages.error(request, "Controleer de productvelden.")
    return _household_tab_redirect("boodschappen")


@household_required
@require_POST
def delete_shopping_item(request, item_id):
    item = get_object_or_404(ShoppingItem.objects.for_household(request.household), pk=item_id)
    item.delete()
    messages.success(request, "Boodschap verwijderd.")
    return _household_tab_redirect("boodschappen")


@household_required
@require_POST
def save_shopping_price(request, item_id):
    item = get_object_or_404(ShoppingItem.objects.for_household(request.household), pk=item_id)
    form = ShoppingPriceForm(request.POST)
    if form.is_valid():
        save_price_observation(
            household=request.household,
            item=item,
            retailer=form.cleaned_data["retailer"],
            values={
                **{key: value for key, value in form.cleaned_data.items() if key != "retailer"},
                "is_offer": False,
                "offer_label": "",
                "regular_price": None,
                "offer_valid_until": None,
                "source": ShoppingPrice.Source.MANUAL,
                "matched_product_name": item.name,
            },
        )
        messages.success(request, "Prijswaarneming opgeslagen.")
    else:
        messages.error(request, "Controleer de prijsgegevens.")
    return _household_tab_redirect("prijzen")


@household_required
@require_POST
def refresh_prices(request):
    refresh_household_shopping_prices.delay(request.household.id)
    messages.success(request, "Prijscontrole is gestart. De vergelijking wordt zo bijgewerkt.")
    return _household_tab_redirect("prijzen")


@household_required
@require_POST
def add_receipt(request):
    form = ReceiptForm(request.POST, request.FILES)
    if form.is_valid():
        receipt = Receipt.objects.create(household=request.household, **form.cleaned_data)
        matched = match_receipt_to_transaction(receipt)
        process_receipt_ocr.delay(receipt.id, request.household.id)
        messages.success(request, "Bon opgeslagen en gekoppeld aan een banktransactie." if matched else "Bon opgeslagen. Tekstherkenning staat in de wachtrij.")
    else:
        messages.error(request, "Controleer de bon.")
    return _household_tab_redirect("inzicht")


@household_required
@require_POST
def update_meal(request, meal_id):
    meal = get_object_or_404(MealPlan.objects.for_household(request.household), pk=meal_id)
    form = MealPlanForm(request.POST, instance=meal)
    if form.is_valid():
        form.save()
        messages.success(request, "Maaltijd aangepast.")
    else:
        messages.error(request, "Controleer de maaltijdvelden.")
    return _household_tab_redirect("maaltijden")


@household_required
@require_POST
def delete_meal(request, meal_id):
    meal = get_object_or_404(MealPlan.objects.for_household(request.household), pk=meal_id)
    meal.delete()
    messages.success(request, "Maaltijd verwijderd.")
    return _household_tab_redirect("maaltijden")


@household_required
@require_POST
def add_meal_ingredient(request, meal_id):
    meal = get_object_or_404(MealPlan.objects.for_household(request.household), pk=meal_id)
    form = MealIngredientForm(request.POST)
    if form.is_valid():
        ingredient = form.save(commit=False)
        ingredient.household = request.household
        ingredient.meal = meal
        ingredient.save()
        messages.success(request, "Ingrediënt toegevoegd.")
    else:
        messages.error(request, "Vul een ingrediënt in.")
    return _household_tab_redirect("maaltijden")


@household_required
@require_POST
def delete_meal_ingredient(request, ingredient_id):
    ingredient = get_object_or_404(MealIngredient.objects.for_household(request.household), pk=ingredient_id)
    ingredient.delete()
    messages.success(request, "Ingrediënt verwijderd.")
    return _household_tab_redirect("maaltijden")


@household_required
@require_POST
def add_meal_ingredients_to_shopping_list(request, meal_id):
    meal = get_object_or_404(MealPlan.objects.for_household(request.household).prefetch_related("ingredients"), pk=meal_id)
    shopping_list, _ = ShoppingList.objects.get_or_create(
        household=request.household,
        name="Boodschappen",
        defaults={"is_default": True},
    )
    added = 0
    for ingredient in meal.ingredients.all():
        exists = ShoppingItem.objects.for_household(request.household).filter(
            list=shopping_list,
            completed_at__isnull=True,
            name__iexact=ingredient.name,
            quantity__iexact=ingredient.quantity,
            category__iexact=ingredient.category,
        ).exists()
        if not exists:
            ShoppingItem.objects.create(
                household=request.household,
                list=shopping_list,
                name=ingredient.name,
                quantity=ingredient.quantity,
                category=ingredient.category,
            )
            added += 1
    if added:
        refresh_household_shopping_prices.delay(request.household.id)
        messages.success(request, f"{added} ingrediënten aan de boodschappenlijst toegevoegd.")
    else:
        messages.info(request, "Deze ingrediënten staan al op de open boodschappenlijst.")
    return _household_tab_redirect("maaltijden")


@household_required
@require_POST
def add_pantry_item(request):
    form = PantryItemForm(request.POST)
    if form.is_valid():
        item = form.save(commit=False)
        item.household = request.household
        item.save()
        messages.success(request, "Voorraadproduct toegevoegd.")
    else:
        messages.error(request, "Controleer de voorraadvelden.")
    return _household_tab_redirect("voorraad")


@household_required
@require_POST
def update_pantry_item(request, item_id):
    item = get_object_or_404(PantryItem.objects.for_household(request.household), pk=item_id)
    form = PantryItemForm(request.POST, instance=item)
    if form.is_valid():
        form.save()
        messages.success(request, "Voorraadproduct aangepast.")
    else:
        messages.error(request, "Controleer de voorraadvelden.")
    return _household_tab_redirect("voorraad")


@household_required
@require_POST
def adjust_pantry_item(request, item_id):
    item = get_object_or_404(PantryItem.objects.for_household(request.household), pk=item_id)
    try:
        delta = Decimal(str(request.POST.get("delta", "0")))
    except Exception:
        messages.error(request, "Ongeldige voorraadwijziging.")
        return _household_tab_redirect("voorraad")
    item.quantity = max(Decimal("0"), item.quantity + delta)
    item.save(update_fields=["quantity", "updated_at"])
    messages.success(request, f"Voorraad {item.name.lower()} bijgewerkt.")
    return _household_tab_redirect("voorraad")


@household_required
@require_POST
def add_pantry_item_to_shopping_list(request, item_id):
    item = get_object_or_404(PantryItem.objects.for_household(request.household), pk=item_id)
    shopping_list, _ = ShoppingList.objects.get_or_create(
        household=request.household,
        name="Boodschappen",
        defaults={"is_default": True},
    )
    quantity = f"{format(item.minimum_quantity.normalize(), 'f')} {item.unit}" if item.minimum_quantity else ""
    shopping_item, created = ShoppingItem.objects.get_or_create(
        household=request.household,
        list=shopping_list,
        completed_at__isnull=True,
        name__iexact=item.name,
        defaults={"name": item.name, "quantity": quantity, "category": item.category},
    )
    if created:
        refresh_household_shopping_prices.delay(request.household.id)
        messages.success(request, f"{shopping_item.name} staat op de boodschappenlijst.")
    else:
        messages.info(request, f"{item.name} staat al op de open boodschappenlijst.")
    return _household_tab_redirect("voorraad")


@household_required
@require_POST
def delete_pantry_item(request, item_id):
    item = get_object_or_404(PantryItem.objects.for_household(request.household), pk=item_id)
    item.delete()
    messages.success(request, "Voorraadproduct verwijderd.")
    return _household_tab_redirect("voorraad")


@household_required
@require_POST
def update_routine(request, routine_id):
    routine = get_object_or_404(Routine.objects.for_household(request.household), pk=routine_id)
    form = RoutineForm(request.POST, instance=routine)
    form.fields["assigned_to"].queryset = request.user.__class__.objects.filter(memberships__household=request.household).distinct()
    if form.is_valid():
        form.save()
        messages.success(request, "Routine aangepast.")
    else:
        messages.error(request, "Controleer de routinevelden.")
    return _household_tab_redirect("routines")


@household_required
@require_POST
def delete_routine(request, routine_id):
    routine = get_object_or_404(Routine.objects.for_household(request.household), pk=routine_id)
    routine.delete()
    messages.success(request, "Routine verwijderd.")
    return _household_tab_redirect("routines")
