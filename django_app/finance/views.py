from django.contrib import messages
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from finance.forms import BudgetForm, RecurringRuleSettingsForm, StatementUploadForm, TransactionCategoryForm
from finance.importers import parse_abn_rows, rows_for_upload
from finance.models import BankAccount, BankConnection, Budget, RecurringRule, Transaction
from finance.tasks import fingerprint, next_recurring_due_date, refresh_household_recurring_rules
from households.decorators import household_required, parent_required


@parent_required
def index(request):
    tab = request.GET.get("tab", "transacties")
    query = request.GET.get("q", "").strip()
    account_id = request.GET.get("rekening", "")
    provider = request.GET.get("bron", "")
    transactions = Transaction.objects.for_household(request.household).select_related("account", "account__connection")
    if query:
        transactions = transactions.filter(Q(description__icontains=query) | Q(counterparty__icontains=query) | Q(payment_type__icontains=query))
    if account_id:
        transactions = transactions.filter(account_id=account_id)
    if provider:
        transactions = transactions.filter(account__connection__provider=provider)
    recurring = list(RecurringRule.objects.for_household(request.household).filter(is_excluded=False).order_by("group", "merchant"))
    for rule in recurring:
        rule.next_due_on = next_recurring_due_date(rule)
    accounts = BankAccount.objects.for_household(request.household).select_related("connection")
    month_start = timezone.localdate().replace(day=1)
    monthly_total = transactions.filter(booked_at__gte=month_start, amount__lt=0).aggregate(total=Sum("amount"))["total"] or 0
    recurring_groups = []
    for group_code, group_label in RecurringRule.Group.choices:
        rules = [rule for rule in recurring if rule.group == group_code]
        if rules:
            total = sum((rule.expected_amount if rule.direction == RecurringRule.Direction.INCOME else -rule.expected_amount) for rule in rules)
            recurring_groups.append({"code": group_code, "label": group_label, "rules": rules, "total": total})
    upcoming_recurring = sorted((rule for rule in recurring if rule.next_due_on), key=lambda rule: rule.next_due_on)[:6]
    budgets = list(Budget.objects.for_household(request.household).order_by("name"))
    monthly_expenses = Transaction.objects.for_household(request.household).filter(booked_at__gte=month_start, amount__lt=0)
    for budget in budgets:
        if not budget.category:
            budget.spent = None
            budget.remaining = None
            budget.progress = 0
            continue
        spent = monthly_expenses.filter(category__iexact=budget.category).aggregate(total=Sum("amount"))["total"] or 0
        budget.spent = abs(spent)
        budget.remaining = budget.monthly_limit - budget.spent
        budget.progress = min(100, int((budget.spent / budget.monthly_limit) * 100)) if budget.monthly_limit else 0
    category_options = sorted({budget.category for budget in budgets if budget.category} | set(Transaction.objects.for_household(request.household).exclude(category="").values_list("category", flat=True)), key=str.lower)
    return render(request, "finance/index.html", {
        "tab": tab, "query": query, "account_id": account_id, "provider": provider, "transactions": transactions[:100], "accounts": accounts,
        "recurring": recurring, "recurring_groups": recurring_groups, "upcoming_recurring": upcoming_recurring, "budgets": budgets, "monthly_total": monthly_total,
        "providers": BankConnection.Provider.choices, "group_choices": RecurringRule.Group.choices,
        "upload_form": StatementUploadForm(), "budget_form": BudgetForm(), "recurring_form": RecurringRuleSettingsForm(), "category_options": category_options,
    })


@parent_required
@require_POST
def import_abn(request):
    form = StatementUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Kies een ABN AMRO-exportbestand.")
        return redirect("finance:index")
    try:
        account_identifier, parsed, skipped = parse_abn_rows(rows_for_upload(form.cleaned_data["statement"]), form.cleaned_data["account_name"] or "ABN AMRO")
        connection, _ = BankConnection.objects.get_or_create(household=request.household, provider=BankConnection.Provider.ABN_MANUAL, external_reference="manual", defaults={"display_name": "ABN AMRO import"})
        account, _ = BankAccount.objects.get_or_create(household=request.household, connection=connection, provider_account_id=account_identifier, defaults={"name": form.cleaned_data["account_name"] or f"ABN AMRO {account_identifier[-4:]}", "iban": account_identifier if account_identifier.startswith("NL") else ""})
        created = 0
        for row in parsed:
            _, was_created = Transaction.objects.get_or_create(household=request.household, account=account, provider_transaction_id=row["provider_transaction_id"], defaults=row)
            created += int(was_created)
        refresh_household_recurring_rules(request.household)
        messages.success(request, f"{created} transacties geïmporteerd; {skipped} regels overgeslagen.")
    except Exception as error:
        messages.error(request, f"Import mislukt: {error}")
    return redirect("finance:index")


@parent_required
@require_POST
def add_budget(request):
    form = BudgetForm(request.POST)
    if form.is_valid():
        budget = form.save(commit=False)
        budget.household = request.household
        budget.save()
        messages.success(request, "Budget toegevoegd.")
    return redirect(f"{reverse('finance:index')}?tab=planning")


@parent_required
@require_POST
def update_budget(request, budget_id):
    budget = Budget.objects.for_household(request.household).get(pk=budget_id)
    form = BudgetForm(request.POST, instance=budget)
    if form.is_valid():
        form.save()
        messages.success(request, "Budget aangepast.")
    else:
        messages.error(request, "Controleer de budgetvelden.")
    return redirect(f"{reverse('finance:index')}?tab=planning")


@parent_required
@require_POST
def delete_budget(request, budget_id):
    budget = Budget.objects.for_household(request.household).get(pk=budget_id)
    budget.delete()
    messages.success(request, "Budget verwijderd.")
    return redirect(f"{reverse('finance:index')}?tab=planning")


@parent_required
@require_POST
def update_recurring_rule(request, rule_id):
    rule = RecurringRule.objects.for_household(request.household).get(pk=rule_id)
    form = RecurringRuleSettingsForm(request.POST, instance=rule)
    if form.is_valid():
        form.save()
        messages.success(request, "Terugkerende post aangepast.")
    else:
        messages.error(request, "Controleer de instellingen van deze post.")
    return redirect(f"{reverse('finance:index')}?tab=planning")


@parent_required
@require_POST
def set_recurring_override(request, transaction_id):
    transaction = Transaction.objects.for_household(request.household).get(pk=transaction_id)
    value = request.POST.get("value")
    transaction.recurring_override = value == "yes" if value in {"yes", "no"} else None
    transaction.save(update_fields=["recurring_override", "updated_at"])
    if value == "no":
        RecurringRule.objects.update_or_create(household=request.household, fingerprint=fingerprint(transaction), defaults={
            "merchant": transaction.counterparty or transaction.description[:240],
            "direction": RecurringRule.Direction.INCOME if transaction.amount >= 0 else RecurringRule.Direction.EXPENSE,
            "expected_amount": abs(transaction.amount), "is_excluded": True,
        })
    else:
        refresh_household_recurring_rules(request.household)
    return redirect(f"{reverse('finance:index')}?tab=transacties")


@parent_required
@require_POST
def update_transaction_category(request, transaction_id):
    transaction = get_object_or_404(Transaction.objects.for_household(request.household), pk=transaction_id)
    form = TransactionCategoryForm(request.POST, instance=transaction)
    if form.is_valid():
        category = form.cleaned_data["category"].strip()
        transaction.category = category
        transaction.save(update_fields=["category", "updated_at"])

        updated_count = 1
        if form.cleaned_data["apply_to_history"]:
            counterparty = transaction.counterparty.strip()
            description = transaction.description.strip()
            if counterparty:
                matches = Transaction.objects.for_household(request.household).filter(counterparty__iexact=counterparty)
            elif description:
                matches = Transaction.objects.for_household(request.household).filter(description__iexact=description)
            else:
                matches = Transaction.objects.none()
            if matches.exists():
                updated_count = matches.update(category=category, updated_at=timezone.now())

        if updated_count == 1:
            messages.success(request, "Transactiecategorie bijgewerkt.")
        else:
            messages.success(request, f"Categorie bijgewerkt voor {updated_count} transacties van dezelfde tegenpartij.")
    else:
        messages.error(request, "Controleer de categorie.")
    return redirect(f"{reverse('finance:index')}?tab=transacties")
