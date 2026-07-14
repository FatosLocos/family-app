from datetime import timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from finance.models import BankAccount, BankConnection, Transaction
from household.models import Receipt
from household.receipt_matching import match_receipt_to_transaction
from households.models import Household


class ReceiptTransactionMatchingTests(TestCase):
    def setUp(self):
        self.household = Household.objects.create(name="Gezin")
        connection = BankConnection.objects.create(household=self.household, provider="abn_amro_manual", display_name="ABN")
        self.account = BankAccount.objects.create(household=self.household, connection=connection, provider_account_id="rekening", name="Rekening")

    def receipt(self, **values):
        return Receipt.objects.create(
            household=self.household,
            retailer="Jumbo",
            purchased_on=timezone.localdate(),
            total_amount=Decimal("12.34"),
            image=SimpleUploadedFile("bon.jpg", b"image", content_type="image/jpeg"),
            **values,
        )

    def transaction(self, **values):
        return Transaction.objects.create(
            household=self.household,
            account=self.account,
            provider_transaction_id=values.pop("provider_transaction_id", "transaction-1"),
            booked_at=values.pop("booked_at", timezone.localdate()),
            amount=values.pop("amount", Decimal("-12.34")),
            description=values.pop("description", "Jumbo boodschappen"),
            **values,
        )

    def test_matches_an_unambiguous_transaction_within_amount_and_date_tolerance(self):
        transaction = self.transaction()
        receipt = self.receipt()

        self.assertTrue(match_receipt_to_transaction(receipt))
        receipt.refresh_from_db()
        self.assertEqual(receipt.transaction, transaction)

    def test_does_not_attach_when_two_candidates_are_equally_likely(self):
        self.transaction(provider_transaction_id="transaction-1")
        self.transaction(provider_transaction_id="transaction-2")
        receipt = self.receipt()

        self.assertFalse(match_receipt_to_transaction(receipt))
        receipt.refresh_from_db()
        self.assertIsNone(receipt.transaction)

    def test_does_not_replace_an_existing_manual_link(self):
        first = self.transaction(provider_transaction_id="transaction-1", booked_at=timezone.localdate() - timedelta(days=1))
        second = self.transaction(provider_transaction_id="transaction-2", booked_at=timezone.localdate())
        receipt = self.receipt(transaction=first)

        self.assertFalse(match_receipt_to_transaction(receipt))
        receipt.refresh_from_db()
        self.assertEqual(receipt.transaction, first)
        self.assertNotEqual(receipt.transaction, second)
