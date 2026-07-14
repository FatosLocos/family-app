from datetime import timedelta
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from household.models import MealPlan, Receipt, Routine, ShoppingItem, ShoppingList, ShoppingPrice, Task
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

    def test_owner_can_update_and_delete_household_records(self):
        self.client.force_login(self.owner)
        shopping_list = ShoppingList.objects.create(household=self.first_household, name="Boodschappen")
        item = ShoppingItem.objects.create(household=self.first_household, list=shopping_list, name="Melk")
        meal = MealPlan.objects.create(household=self.first_household, title="Pasta", planned_for=timezone.localdate())
        routine = Routine.objects.create(household=self.first_household, title="Afval")

        self.client.post(reverse("household:update_task", args=[self.task.pk]), {"title": "Privé taak aangepast", "priority": 3, "notes": "Voor vrijdag"})
        self.client.post(reverse("household:update_shopping_item", args=[item.pk]), {"name": "Havermelk", "quantity": "2 pakken", "recurrence_days": 7})
        self.client.post(reverse("household:update_meal", args=[meal.pk]), {"title": "Risotto", "planned_for": timezone.localdate(), "notes": "Met salade"})
        self.client.post(reverse("household:update_routine", args=[routine.pk]), {"title": "Papier wegbrengen", "cadence": "wekelijks"})

        self.task.refresh_from_db()
        item.refresh_from_db()
        meal.refresh_from_db()
        routine.refresh_from_db()
        self.assertEqual(self.task.title, "Privé taak aangepast")
        self.assertEqual(item.name, "Havermelk")
        self.assertEqual(meal.title, "Risotto")
        self.assertEqual(routine.title, "Papier wegbrengen")

        self.client.post(reverse("household:delete_task", args=[self.task.pk]))
        self.client.post(reverse("household:delete_shopping_item", args=[item.pk]))
        self.client.post(reverse("household:delete_meal", args=[meal.pk]))
        self.client.post(reverse("household:delete_routine", args=[routine.pk]))
        self.assertFalse(Task.objects.filter(pk=self.task.pk).exists())
        self.assertFalse(ShoppingItem.objects.filter(pk=item.pk).exists())
        self.assertFalse(MealPlan.objects.filter(pk=meal.pk).exists())
        self.assertFalse(Routine.objects.filter(pk=routine.pk).exists())

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

    def test_receipt_ocr_stores_text_and_detected_total(self):
        receipt = Receipt.objects.create(household=self.first_household, retailer="Jumbo", image=SimpleUploadedFile("bon.jpg", b"image", content_type="image/jpeg"))
        with patch("household.ocr.Image.open") as image_open, patch("household.ocr.pytesseract.image_to_string", return_value="JUMBO\nTOTAAL 12,34"):
            image_open.return_value.__enter__.return_value = object()
            from household.ocr import process_receipt
            process_receipt(receipt.id)
        receipt.refresh_from_db()
        self.assertEqual(receipt.ocr_status, Receipt.OcrStatus.COMPLETE)
        self.assertEqual(str(receipt.total_amount), "12.34")

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
