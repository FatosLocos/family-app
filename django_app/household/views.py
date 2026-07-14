from django.contrib import messages
from django.db.models import Count, Max
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from datetime import timedelta
from decimal import Decimal
import re

from django.utils import timezone
from django.views.decorators.http import require_POST

from households.decorators import household_required
from household.forms import MealPlanForm, ReceiptForm, RoutineForm, ShoppingItemForm, ShoppingPriceForm, TaskForm
from household.models import MealPlan, Receipt, Routine, ShoppingItem, ShoppingList, ShoppingPrice, ShoppingPriceSnapshot, Task
from household.price_history import save_price_observation
from household.receipt_matching import match_receipt_to_transaction
from notifications.models import Notification
from household.tasks import process_receipt_ocr, refresh_household_shopping_prices


def _shopping_item_multiplier(item):
    """Use an explicit count such as '2 pakken'; weights stay one product."""
    match = re.match(r"^\s*(\d+)\s*(?:x\b|stuks?\b|pakken?\b|flessen?\b|zakken?\b|dozen?\b)", item.quantity.casefold())
    return Decimal(match.group(1)) if match else Decimal("1")


@household_required
def index(request):
    tab = request.GET.get("tab", "taken")
    task_filter = request.GET.get("filter", "open")
    household = request.household
    default_list, _ = ShoppingList.objects.get_or_create(household=household, name="Boodschappen", defaults={"is_default": True})
    tasks = Task.objects.for_household(household).select_related("assigned_to")
    if task_filter == "vandaag":
        tasks = tasks.filter(completed_at__isnull=True, due_at__date=timezone.localdate())
    elif task_filter == "afgerond":
        tasks = tasks.filter(completed_at__isnull=False)
    elif task_filter != "alles":
        tasks = tasks.filter(completed_at__isnull=True)
    members = request.user.__class__.objects.filter(memberships__household=household).distinct()
    task_form = TaskForm()
    task_form.fields["assigned_to"].queryset = members
    routine_form = RoutineForm()
    routine_form.fields["assigned_to"].queryset = members
    receipts = list(Receipt.objects.for_household(household).select_related("transaction", "transaction__account")[:30])
    for receipt in receipts:
        receipt.bank_amount = abs(receipt.transaction.amount) if receipt.transaction_id else None
        receipt.amount_difference = abs(receipt.bank_amount - receipt.total_amount) if receipt.transaction_id and receipt.total_amount else None
    frequent_products = list(
        ShoppingItem.objects.for_household(household)
        .filter(completed_at__gte=timezone.now() - timedelta(days=90))
        .values("name")
        .annotate(times_bought=Count("id"), last_bought=Max("completed_at"))
        .order_by("-times_bought", "-last_bought")[:8]
    )
    price_items = list(ShoppingItem.objects.for_household(household).filter(list=default_list, completed_at__isnull=True).prefetch_related("prices")[:50])
    snapshots_by_item = {}
    for snapshot in ShoppingPriceSnapshot.objects.for_household(household).filter(item__in=price_items).order_by("item_id", "-observed_at"):
        if len(snapshots_by_item.setdefault(snapshot.item_id, [])) < 8:
            snapshots_by_item[snapshot.item_id].append(snapshot)
    price_trend_map = {}
    for snapshot in ShoppingPriceSnapshot.objects.for_household(household).select_related("item").order_by("item_id", "retailer", "observed_at"):
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
    price_trends.sort(key=lambda trend: abs(trend["delta"]), reverse=True)
    retailer_choices = ShoppingPrice.Retailer.choices
    price_rows = []
    latest_price_at = None
    retailer_totals = {retailer: {"retailer": retailer, "label": label, "total": Decimal("0"), "priced_items": 0} for retailer, label in retailer_choices}
    for item in price_items:
        prices_by_retailer = {price.retailer: price for price in item.prices.all()}
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
                {"retailer": retailer, "label": label, "price": prices_by_retailer.get(retailer)}
                for retailer, label in retailer_choices
            ],
        })
    context = {
        "tab": tab, "task_filter": task_filter, "today": timezone.localdate(),
        "task_form": task_form, "shopping_form": ShoppingItemForm(), "meal_form": MealPlanForm(), "routine_form": routine_form,
        "tasks": tasks[:50],
        "shopping_items": ShoppingItem.objects.for_household(household).filter(list=default_list)[:50],
        "price_items": price_items,
        "price_rows": price_rows,
        "retailer_choices": retailer_choices,
        "price_totals": [
            {**total, "missing_items": len(price_items) - total["priced_items"]}
            for total in retailer_totals.values()
        ],
        "latest_price_at": latest_price_at,
        "price_form": ShoppingPriceForm(),
        "receipts": receipts,
        "frequent_products": frequent_products,
        "price_trends": price_trends[:8],
        "receipt_form": ReceiptForm(),
        "meals": MealPlan.objects.for_household(household).order_by("planned_for")[:14],
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
        messages.success(request, "Taak toegevoegd.")
    else:
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
    if request.headers.get("HX-Request"):
        return render(request, "household/partials/task_row.html", {"task": task})
    return redirect("household:index")


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
        messages.success(request, "Boodschap toegevoegd. Prijzen worden bijgewerkt.")
    else:
        messages.error(request, "Vul een productnaam in.")
    return redirect("household:index")


@household_required
@require_POST
def toggle_shopping_item(request, item_id):
    item = get_object_or_404(ShoppingItem.objects.for_household(request.household), pk=item_id)
    item.completed_at = None if item.completed_at else timezone.now()
    item.save(update_fields=["completed_at", "updated_at"])
    if request.headers.get("HX-Request"):
        return render(request, "household/partials/shopping_row.html", {"item": item})
    return redirect("household:index")


@household_required
@require_POST
def add_meal(request):
    form = MealPlanForm(request.POST)
    if form.is_valid():
        meal = form.save(commit=False)
        meal.household = request.household
        meal.save()
        messages.success(request, "Maaltijd ingepland.")
    return redirect("household:index")


@household_required
@require_POST
def add_routine(request):
    form = RoutineForm(request.POST)
    form.fields["assigned_to"].queryset = request.user.__class__.objects.filter(memberships__household=request.household).distinct()
    if form.is_valid():
        routine = form.save(commit=False)
        routine.household = request.household
        routine.save()
        messages.success(request, "Routine toegevoegd.")
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
