from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from finance.importers import parse_abn_rows
from finance.models import BankAccount, BankConnection, Budget, RecurringRule, Transaction
from finance.tasks import refresh_household_recurring_rules
from households.models import Household, Membership
from identity.models import User


class AbnImporterTests(SimpleTestCase):
    def test_parses_the_abn_headers_and_structured_description(self):
        rows = [
            ["Rekeningnummer", "Muntsoort", "Transactiedatum", "Rentedatum", "Beginsaldo", "Eindsaldo", "Transactiebedrag", "Omschrijving"],
            ["473586657", "EUR", "20260103", "20251231", "14720,90", "14774,80", "-53,90", "BEA, Apple Pay ADAM MARKT,PAS474 NR:68BHJ8, 07.07.26/16:42 ZOETERMEER"],
        ]
        account, transactions, skipped = parse_abn_rows(rows, "ABN")
        self.assertEqual(account, "473586657")
        self.assertEqual(skipped, 0)
        self.assertEqual(len(transactions), 1)
        self.assertEqual(str(transactions[0]["amount"]), "-53.90")
        self.assertEqual(transactions[0]["metadata"]["method"], "Apple Pay ADAM MARKT")


class FinanceWorkflowTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="ouder@example.com", email="ouder@example.com", password="safe-password-123")
        self.other_user = User.objects.create_user(username="ander@example.com", email="ander@example.com", password="safe-password-123")
        self.household = Household.objects.create(name="Gezin")
        self.other_household = Household.objects.create(name="Ander gezin")
        Membership.objects.create(household=self.household, user=self.owner, role=Membership.Role.PARENT)
        Membership.objects.create(household=self.other_household, user=self.other_user, role=Membership.Role.OWNER)
        connection = BankConnection.objects.create(household=self.household, provider="abn_amro_manual", display_name="ABN AMRO", external_reference="manual")
        self.account = BankAccount.objects.create(household=self.household, connection=connection, provider_account_id="rekening-1", name="Betaalrekening")
        self.client.force_login(self.owner)

    def transaction(self, identifier, booked_at, amount, counterparty):
        return Transaction.objects.create(household=self.household, account=self.account, provider_transaction_id=identifier, booked_at=booked_at, amount=Decimal(amount), description=counterparty, counterparty=counterparty)

    def test_recurring_detection_respects_manual_exclusion_and_confirmation(self):
        first = self.transaction("odido-1", date(2026, 5, 1), "-45.00", "Odido")
        self.transaction("odido-2", date(2026, 6, 1), "-45.00", "Odido")
        refresh_household_recurring_rules(self.household)
        rule = RecurringRule.objects.get(household=self.household, merchant="Odido")
        self.assertEqual(rule.expected_amount, Decimal("45.00"))
        self.client.post(reverse("finance:set_recurring_override", args=[first.id]), {"value": "no"})
        rule.refresh_from_db()
        self.assertTrue(rule.is_excluded)
        refresh_household_recurring_rules(self.household)
        rule.refresh_from_db()
        self.assertTrue(rule.is_excluded)
        self.client.post(reverse("finance:set_recurring_override", args=[first.id]), {"value": "yes"})
        rule.refresh_from_db()
        self.assertTrue(rule.user_confirmed)
        self.assertFalse(rule.is_excluded)

    def test_income_uses_recent_stable_amount_after_three_higher_payments(self):
        for index, amount in enumerate(("1000.00", "1200.00", "1200.00", "1200.00"), start=1):
            self.transaction(f"salaris-{index}", date(2026, index, 1), amount, "Salaris")
        refresh_household_recurring_rules(self.household)
        rule = RecurringRule.objects.get(household=self.household, merchant="Salaris")
        self.assertEqual(rule.direction, RecurringRule.Direction.INCOME)
        self.assertEqual(rule.expected_amount, Decimal("1200.00"))

    def test_budget_crud_and_finance_page_filter_are_household_scoped(self):
        response = self.client.post(reverse("finance:add_budget"), {"name": "Boodschappen", "monthly_limit": "500.00", "category": "Huishouden"})
        self.assertEqual(response.status_code, 302)
        budget = Budget.objects.get(household=self.household, name="Boodschappen")
        self.client.post(reverse("finance:update_budget", args=[budget.id]), {"name": "Boodschappen", "monthly_limit": "550.00", "category": "Eten"})
        budget.refresh_from_db()
        self.assertEqual(budget.monthly_limit, Decimal("550.00"))
        current = self.transaction("eigen", date.today(), "-12.50", "Eigen supermarkt")
        other_connection = BankConnection.objects.create(household=self.other_household, provider="abn_amro_manual", display_name="ABN", external_reference="other")
        other_account = BankAccount.objects.create(household=self.other_household, connection=other_connection, provider_account_id="other", name="Andere rekening")
        Transaction.objects.create(household=self.other_household, account=other_account, provider_transaction_id="ander", booked_at=date.today(), amount=Decimal("-99.00"), description="Privé supermarkt", counterparty="Privé supermarkt")
        response = self.client.get(reverse("finance:index"), {"tab": "transacties", "q": "supermarkt", "rekening": current.account_id})
        self.assertContains(response, "Eigen supermarkt")
        self.assertNotContains(response, "Privé supermarkt")
        self.client.post(reverse("finance:delete_budget", args=[budget.id]))
        self.assertFalse(Budget.objects.filter(pk=budget.id).exists())

    def test_recurring_and_budget_edit_overlays_render(self):
        rule = RecurringRule.objects.create(household=self.household, fingerprint="test", merchant="Verzekering", direction="expense", expected_amount=Decimal("15.00"))
        budget = Budget.objects.create(household=self.household, name="Buffer", monthly_limit=Decimal("100.00"))
        response = self.client.get(reverse("finance:index"), {"tab": "planning"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"recurring-edit-{rule.id}")
        self.assertContains(response, f"budget-edit-{budget.id}")

    def test_child_cannot_open_financial_data_or_see_finance_navigation(self):
        child = User.objects.create_user(username="kind@example.com", email="kind@example.com", password="safe-password-123")
        Membership.objects.create(household=self.household, user=child, role=Membership.Role.CHILD)
        self.client.force_login(child)

        self.assertEqual(self.client.get(reverse("finance:index")).status_code, 403)
        response = self.client.get(reverse("today"))
        self.assertNotContains(response, reverse("finance:index"))
