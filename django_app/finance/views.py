from django.contrib import messages
from django.db.models import Q, Sum
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from finance.forms import BudgetForm, RecurringRuleSettingsForm, StatementUploadForm
from finance.importers import parse_abn_rows, rows_for_upload
from finance.models import BankAccount, BankConnection, Budget, RecurringRule, Transaction
from finance.tasks import fingerprint, refresh_household_recurring_rules
from households.decorators import household_required, parent_required


@household_required
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
    accounts = BankAccount.objects.for_household(request.household).select_related("connection")
    month_start = timezone.localdate().replace(day=1)
    monthly_total = transactions.filter(booked_at__gte=month_start, amount__lt=0).aggregate(total=Sum("amount"))["total"] or 0
    recurring_groups = []
    for group_code, group_label in RecurringRule.Group.choices:
        rules = [rule for rule in recurring if rule.group == group_code]
        if rules:
            total = sum((rule.expected_amount if rule.direction == RecurringRule.Direction.INCOME else -rule.expected_amount) for rule in rules)
            recurring_groups.append({"code": group_code, "label": group_label, "rules": rules, "total": total})
    return render(request, "finance/index.html", {
        "tab": tab, "query": query, "account_id": account_id, "provider": provider, "transactions": transactions[:100], "accounts": accounts,
        "recurring": recurring, "recurring_groups": recurring_groups, "budgets": Budget.objects.for_household(request.household), "monthly_total": monthly_total,
        "providers": BankConnection.Provider.choices, "group_choices": RecurringRule.Group.choices,
        "upload_form": StatementUploadForm(), "budget_form": BudgetForm(), "recurring_form": RecurringRuleSettingsForm(),
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
