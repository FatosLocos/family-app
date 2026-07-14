from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from household.models import MealPlan, Receipt, Routine, ShoppingItem, ShoppingList, ShoppingPrice, ShoppingPriceSnapshot, Task
from household.price_providers import PriceResult, fetch_checkjebon_prices, refresh_household_prices
from household.tasks import replenish_recurring_shopping_items
from households.models import Household, Membership
from identity.models import User


class HouseholdIsolationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner@example.com", email="owner@example.com", password="safe-password-123", display_name="Ouder")
        self.child = User.objects.create_user(username="child@example.com", email="child@example.com", password="safe-password-123", display_name="Kind")
        self.first_household = Household.objects.create(name="Eerste gezin")
        self.second_household = Household.objects.create(name="Tweede gezin")
        Membership.objects.create(user=self.owner, household=self.first_household, role=Membership.Role.OWNER)
        Membership.objects.create(user=self.child, household=self.second_household, role=Membership.Role.CHILD)
        self.task = Task.objects.create(household=self.first_household, title="Privé taak")

    def test_member_cannot_toggle_task_from_another_household(self):
        self.client.force_login(self.child)
        response = self.client.post(reverse("household:toggle_task", args=[self.task.pk]))
        self.assertEqual(response.status_code, 404)
        self.task.refresh_from_db()
        self.assertIsNone(self.task.completed_at)

    def test_owner_can_add_task_to_active_household(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("household:add_task"), {"title": "Afval buiten", "priority": 2}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Task.objects.filter(household=self.first_household, title="Afval buiten").exists())

    def test_recurring_shopping_item_is_replenished_after_interval(self):
        shopping_list = ShoppingList.objects.create(household=self.first_household, name="Boodschappen")
        ShoppingItem.objects.create(household=self.first_household, list=shopping_list, name="Koffie", recurring=True, recurrence_days=7, completed_at=timezone.now() - timedelta(days=8))
        replenish_recurring_shopping_items()
        self.assertTrue(ShoppingItem.objects.filter(household=self.first_household, name="Koffie", completed_at__isnull=True).exists())

    @patch("household.views.refresh_household_shopping_prices.delay")
    def test_owner_can_update_and_delete_household_records(self, refresh_prices):
        self.client.force_login(self.owner)
        shopping_list = ShoppingList.objects.create(household=self.first_household, name="Boodschappen")
        item = ShoppingItem.objects.create(household=self.first_household, list=shopping_list, name="Melk")
        meal = MealPlan.objects.create(household=self.first_household, title="Pasta", planned_for=timezone.localdate())
        routine = Routine.objects.create(household=self.first_household, title="Afval")

        self.client.post(reverse("household:update_task", args=[self.task.pk]), {"title": "Privé taak aangepast", "priority": 3, "notes": "Voor vrijdag"})
        self.client.post(reverse("household:update_shopping_item", args=[item.pk]), {"name": "Havermelk", "quantity": "2 pakken", "recurrence_days": 7})
        self.client.post(reverse("household:update_meal", args=[meal.pk]), {"title": "Risotto", "planned_for": timezone.localdate(), "notes": "Met salade"})
        self.client.post(reverse("household:update_routine", args=[routine.pk]), {"title": "Papier wegbrengen", "cadence": "wekelijks", "interval_days": 7, "next_due_on": timezone.localdate()})

        self.task.refresh_from_db()
        item.refresh_from_db()
        meal.refresh_from_db()
        routine.refresh_from_db()
        self.assertEqual(self.task.title, "Privé taak aangepast")
        self.assertEqual(item.name, "Havermelk")
        self.assertEqual(meal.title, "Risotto")
        self.assertEqual(routine.title, "Papier wegbrengen")
        refresh_prices.assert_called_once_with(self.first_household.id)

        self.client.post(reverse("household:delete_task", args=[self.task.pk]))
        self.client.post(reverse("household:delete_shopping_item", args=[item.pk]))
        self.client.post(reverse("household:delete_meal", args=[meal.pk]))
        self.client.post(reverse("household:delete_routine", args=[routine.pk]))
        self.assertFalse(Task.objects.filter(pk=self.task.pk).exists())
        self.assertFalse(ShoppingItem.objects.filter(pk=item.pk).exists())
        self.assertFalse(MealPlan.objects.filter(pk=meal.pk).exists())
        self.assertFalse(Routine.objects.filter(pk=routine.pk).exists())

    def test_routine_completion_schedules_the_next_occurrence(self):
        self.client.force_login(self.owner)
        routine = Routine.objects.create(
            household=self.first_household,
            title="Afval buiten",
            interval_days=7,
            next_due_on=timezone.localdate() - timedelta(days=2),
        )

        response = self.client.post(reverse("household:complete_routine", args=[routine.id]))

        self.assertRedirects(response, f"{reverse('household:index')}?tab=routines")
        routine.refresh_from_db()
        self.assertIsNotNone(routine.last_completed_at)
        self.assertEqual(routine.next_due_on, timezone.localdate() + timedelta(days=7))

    def test_member_cannot_update_or_delete_records_from_another_household(self):
        self.client.force_login(self.child)
        response = self.client.post(reverse("household:update_task", args=[self.task.pk]), {"title": "Niet toegestaan", "priority": 1})
        self.assertEqual(response.status_code, 404)
        response = self.client.post(reverse("household:delete_task", args=[self.task.pk]))
        self.assertEqual(response.status_code, 404)
        self.task.refresh_from_db()
        self.assertEqual(self.task.title, "Privé taak")

    def test_task_edit_overlay_renders_for_household_task(self):
        self.task.due_at = timezone.now()
        self.task.save(update_fields=["due_at", "updated_at"])
        self.client.force_login(self.owner)
        response = self.client.get(reverse("household:index"), {"tab": "taken", "filter": "alles"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'task-edit-{self.task.pk}')
        self.assertContains(response, 'type="datetime-local"')

    def test_household_can_store_one_price_per_retailer_and_replace_it(self):
        self.client.force_login(self.owner)
        shopping_list = ShoppingList.objects.create(household=self.first_household, name="Boodschappen")
        item = ShoppingItem.objects.create(household=self.first_household, list=shopping_list, name="Koffie")
        payload = {"retailer": "ah", "price": "4.99", "unit_label": "500 g", "is_offer": "on", "offer_label": "Bonus", "product_url": "https://example.test/koffie"}
        self.client.post(reverse("household:save_shopping_price", args=[item.id]), payload)
        payload["price"] = "4.49"
        self.client.post(reverse("household:save_shopping_price", args=[item.id]), payload)
        price = ShoppingPrice.objects.get(item=item, retailer="ah")
        self.assertEqual(str(price.price), "4.49")
        self.assertTrue(price.is_offer)
        self.assertEqual(price.source, ShoppingPrice.Source.MANUAL)
        self.assertEqual(ShoppingPriceSnapshot.objects.filter(item=item, retailer="ah").count(), 2)

    def test_price_comparison_keeps_each_retailer_in_its_own_cell(self):
        self.client.force_login(self.owner)
        shopping_list = ShoppingList.objects.create(household=self.first_household, name="Boodschappen")
        item = ShoppingItem.objects.create(household=self.first_household, list=shopping_list, name="Koffie")
        ShoppingPrice.objects.create(household=self.first_household, item=item, retailer=ShoppingPrice.Retailer.ALBERT_HEIJN, price="4.49", unit_label="500 g", product_url="https://example.test/koffie")
        ShoppingPrice.objects.create(household=self.first_household, item=item, retailer=ShoppingPrice.Retailer.KAUFLAND, price="3.99")

        response = self.client.get(reverse("household:index"), {"tab": "prijzen"})

        self.assertContains(response, 'class="price-comparison-cells"')
        self.assertContains(response, 'retailer-ah')
        self.assertContains(response, 'retailer-jumbo is-empty')
        self.assertContains(response, 'retailer-lidl is-empty')
        self.assertContains(response, 'retailer-kaufland')
        self.assertContains(response, 'https://example.test/koffie')
        totals = {total["retailer"]: total for total in response.context["price_totals"]}
        self.assertEqual(totals[ShoppingPrice.Retailer.ALBERT_HEIJN]["total"], Decimal("4.49"))
        self.assertEqual(totals[ShoppingPrice.Retailer.KAUFLAND]["missing_items"], 0)

    @patch("household.price_providers.requests.get")
    def test_checkjebon_provider_prefers_the_matching_package_size(self, get):
        from household import price_providers

        price_providers._checkjebon_cache = None
        get.return_value.json.return_value = [
            {"n": "ah", "u": "https://ah.example.test", "d": [
                {"n": "Nutella hazelnootpasta", "p": 2.49, "s": "200 g", "l": "/nutella-200"},
                {"n": "Nutella hazelnootpasta", "p": 4.29, "s": "400 g", "l": "/nutella-400"},
            ]},
        ]
        get.return_value.raise_for_status.return_value = None
        item = ShoppingItem.objects.create(household=self.first_household, list=ShoppingList.objects.create(household=self.first_household, name="Boodschappen"), name="Nutella hazelnootpasta", quantity="400 g")

        results = fetch_checkjebon_prices([item])

        self.assertEqual(len(results), 1)
        self.assertEqual(str(results[0].price), "4.29")
        self.assertEqual(results[0].product_url, "https://ah.example.test/nutella-400")

    @patch("household.price_providers.fetch_prijsprofeet_offers")
    @patch("household.price_providers.fetch_checkjebon_prices")
    def test_price_sync_uses_offers_but_preserves_manual_prices(self, base_prices, offers):
        shopping_list = ShoppingList.objects.create(household=self.first_household, name="Boodschappen")
        automatic = ShoppingItem.objects.create(household=self.first_household, list=shopping_list, name="Komkommer")
        manual = ShoppingItem.objects.create(household=self.first_household, list=shopping_list, name="Koffie")
        ShoppingPrice.objects.create(household=self.first_household, item=manual, retailer=ShoppingPrice.Retailer.JUMBO, price="6.50")
        base_prices.return_value = [
            PriceResult(item_id=automatic.id, retailer=ShoppingPrice.Retailer.JUMBO, price=Decimal("1.29"), matched_product_name="Komkommer", unit_label="stuk"),
            PriceResult(item_id=manual.id, retailer=ShoppingPrice.Retailer.JUMBO, price=Decimal("5.99"), matched_product_name="Koffie"),
        ]
        offers.return_value = [
            PriceResult(item_id=automatic.id, retailer=ShoppingPrice.Retailer.JUMBO, price=Decimal("0.99"), matched_product_name="Komkommer", source=ShoppingPrice.Source.PRIJSPROFEET, is_offer=True, offer_label="Bonus", regular_price=Decimal("1.29")),
        ]

        result = refresh_household_prices(self.first_household)

        price = ShoppingPrice.objects.get(item=automatic, retailer=ShoppingPrice.Retailer.JUMBO)
        self.assertEqual(result["updated"], 1)
        self.assertTrue(price.is_offer)
        self.assertEqual(price.source, ShoppingPrice.Source.PRIJSPROFEET)
        self.assertEqual(str(price.price), "0.99")
        self.assertEqual(str(ShoppingPrice.objects.get(item=manual, retailer=ShoppingPrice.Retailer.JUMBO).price), "6.50")
        self.assertEqual(ShoppingPriceSnapshot.objects.filter(item=automatic, retailer=ShoppingPrice.Retailer.JUMBO).count(), 1)

        refresh_household_prices(self.first_household)
        self.assertEqual(ShoppingPriceSnapshot.objects.filter(item=automatic, retailer=ShoppingPrice.Retailer.JUMBO).count(), 1)

    @patch("household.views.refresh_household_shopping_prices.delay")
    def test_parent_can_start_a_price_refresh(self, delay):
        self.client.force_login(self.owner)

        response = self.client.post(reverse("household:refresh_prices"))

        self.assertRedirects(response, f"{reverse('household:index')}?tab=prijzen")
        delay.assert_called_once_with(self.first_household.id)

    def test_receipt_ocr_stores_text_and_detected_total(self):
        receipt = Receipt.objects.create(household=self.first_household, retailer="Jumbo", image=SimpleUploadedFile("bon.jpg", b"image", content_type="image/jpeg"))
        with patch("household.ocr.Image.open") as image_open, patch("household.ocr.pytesseract.image_to_string", return_value="JUMBO\nTOTAAL 12,34"):
            image_open.return_value.__enter__.return_value = object()
            from household.ocr import process_receipt
            process_receipt(receipt.id)
        receipt.refresh_from_db()
        self.assertEqual(receipt.ocr_status, Receipt.OcrStatus.COMPLETE)
        self.assertEqual(str(receipt.total_amount), "12.34")

    def test_pdf_receipt_ocr_reads_the_first_page(self):
        receipt = Receipt.objects.create(household=self.first_household, retailer="Jumbo", image=SimpleUploadedFile("bon.pdf", b"%PDF-1.4", content_type="application/pdf"))

        def render_first_page(command, **_kwargs):
            Path(f"{command[-1]}-1.png").touch()

        with patch("household.ocr.subprocess.run", side_effect=render_first_page) as render, patch("household.ocr.Image.open") as image_open, patch("household.ocr.pytesseract.image_to_string", return_value="JUMBO\nTOTAAL 18,75"):
            image_open.return_value.__enter__.return_value = object()
            from household.ocr import process_receipt
            process_receipt(receipt.id)

        receipt.refresh_from_db()
        render.assert_called_once()
        self.assertEqual(receipt.ocr_status, Receipt.OcrStatus.COMPLETE)
        self.assertEqual(str(receipt.total_amount), "18.75")

    @patch("household.views.process_receipt_ocr.delay")
    def test_owner_can_upload_a_receipt_without_a_message_error(self, process_ocr):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("household:add_receipt"),
            {
                "retailer": "Jumbo",
                "purchased_on": timezone.localdate(),
                "total_amount": "12.34",
                "image": SimpleUploadedFile("bon.jpg", b"image", content_type="image/jpeg"),
            },
        )

        self.assertRedirects(response, f"{reverse('household:index')}?tab=inzicht")
        receipt = Receipt.objects.get(household=self.first_household)
        process_ocr.assert_called_once_with(receipt.id, self.first_household.id)
