from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from household.models import MealIngredient, MealPlan, PantryItem, Receipt, ReceiptLineItem, Routine, ShoppingItem, ShoppingList, ShoppingOffer, ShoppingPrice, ShoppingPriceProviderStatus, ShoppingPriceSnapshot, Task
from household.ocr import parse_receipt_line_items
from household.price_providers import PriceProviderError, PriceResult, fetch_checkjebon_prices, refresh_household_prices
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

    def test_meal_ingredients_and_pantry_items_have_forced_household_rls(self):
        if connection.vendor != "postgresql":
            self.skipTest("RLS is alleen van toepassing op PostgreSQL.")

        for table in ("household_mealingredient", "household_pantryitem", "household_shoppingoffer", "household_shoppingpriceproviderstatus"):
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT c.relrowsecurity, c.relforcerowsecurity,
                           EXISTS(
                               SELECT 1 FROM pg_policies p
                               WHERE p.schemaname = current_schema()
                                 AND p.tablename = %s
                                 AND p.policyname = 'household_isolation'
                           )
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = current_schema() AND c.relname = %s
                    """,
                    [table, table],
                )
                row = cursor.fetchone()
            self.assertEqual(row, (True, True, True), table)

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

    def test_recurring_shopping_tab_groups_history_and_shows_next_replenishment(self):
        shopping_list = ShoppingList.objects.create(household=self.first_household, name="Boodschappen")
        ShoppingItem.objects.create(
            household=self.first_household,
            list=shopping_list,
            name="Koffie",
            recurring=True,
            recurrence_days=7,
            completed_at=timezone.now() - timedelta(days=2),
        )
        ShoppingItem.objects.create(
            household=self.first_household,
            list=shopping_list,
            name="Koffie",
            recurring=True,
            recurrence_days=7,
        )
        ShoppingItem.objects.create(household=self.first_household, list=shopping_list, name="Eenmalig")
        self.client.force_login(self.owner)

        response = self.client.get(reverse("household:index"), {"tab": "terugkerend"})

        self.assertContains(response, "Terugkerende boodschappen")
        self.assertContains(response, "Koffie")
        self.assertContains(response, "Elke 7 dagen")
        self.assertContains(response, "Staat op de lijst")
        self.assertNotContains(response, "Eenmalig")

    def test_shopping_list_defaults_to_open_items_and_can_show_completed_history(self):
        shopping_list = ShoppingList.objects.create(household=self.first_household, name="Boodschappen")
        ShoppingItem.objects.create(household=self.first_household, list=shopping_list, name="Open product")
        completed = ShoppingItem.objects.create(
            household=self.first_household,
            list=shopping_list,
            name="Afgerond product",
            completed_at=timezone.now(),
        )
        self.client.force_login(self.owner)

        open_response = self.client.get(reverse("household:index"), {"tab": "boodschappen"})
        completed_response = self.client.get(
            reverse("household:index"), {"tab": "boodschappen", "shopping_filter": "afgerond"}
        )
        toggle_response = self.client.post(
            f"{reverse('household:toggle_shopping_item', args=[completed.id])}?shopping_filter=afgerond",
            HTTP_HX_REQUEST="true",
        )

        self.assertContains(open_response, "Open product")
        self.assertNotContains(open_response, "Afgerond product")
        self.assertContains(completed_response, "Afgerond product")
        self.assertEqual(toggle_response.status_code, 200)
        self.assertEqual(toggle_response.content, b"")

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

    @patch("household.views.refresh_household_shopping_prices.delay")
    def test_meal_ingredients_can_be_created_and_transferred_once_to_shopping(self, refresh_prices):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("household:add_meal"),
            {
                "title": "Pasta",
                "planned_for": timezone.localdate(),
                "notes": "Snel doordeweeks",
                "ingredients_text": "Pasta | 500 g | Pasta\nTomaten | 4 stuks | Groente",
            },
        )
        self.assertRedirects(response, f"{reverse('household:index')}?tab=maaltijden")
        meal = MealPlan.objects.get(household=self.first_household, title="Pasta")
        self.assertEqual(list(meal.ingredients.values_list("name", "quantity", "category")), [("Pasta", "500 g", "Pasta"), ("Tomaten", "4 stuks", "Groente")])

        response = self.client.post(reverse("household:add_meal_ingredients_to_shopping_list", args=[meal.id]))
        self.assertRedirects(response, f"{reverse('household:index')}?tab=maaltijden")
        self.assertEqual(ShoppingItem.objects.filter(household=self.first_household, completed_at__isnull=True).count(), 2)
        refresh_prices.assert_called_once_with(self.first_household.id)

        self.client.post(reverse("household:add_meal_ingredients_to_shopping_list", args=[meal.id]))
        self.assertEqual(ShoppingItem.objects.filter(household=self.first_household, completed_at__isnull=True).count(), 2)
        refresh_prices.assert_called_once()

    def test_meal_ingredient_actions_are_household_scoped(self):
        own_meal = MealPlan.objects.create(household=self.first_household, title="Pasta", planned_for=timezone.localdate())
        own_ingredient = MealIngredient.objects.create(household=self.first_household, meal=own_meal, name="Pasta")
        self.client.force_login(self.child)

        response = self.client.post(reverse("household:delete_meal_ingredient", args=[own_ingredient.id]))
        self.assertEqual(response.status_code, 404)
        response = self.client.post(reverse("household:add_meal_ingredients_to_shopping_list", args=[own_meal.id]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(MealIngredient.objects.filter(pk=own_ingredient.id).exists())

    def test_meal_view_shows_ingredient_summary_and_transfer_action(self):
        meal = MealPlan.objects.create(household=self.first_household, title="Pasta", planned_for=timezone.localdate())
        MealIngredient.objects.create(household=self.first_household, meal=meal, name="Pasta", quantity="500 g")
        self.client.force_login(self.owner)

        response = self.client.get(reverse("household:index"), {"tab": "maaltijden"})

        self.assertContains(response, "1 ingrediënt")
        self.assertContains(response, reverse("household:add_meal_ingredients_to_shopping_list", args=[meal.id]))

    @patch("household.views.refresh_household_shopping_prices.delay")
    def test_low_pantry_item_can_be_adjusted_and_added_to_shopping(self, refresh_prices):
        item = PantryItem.objects.create(
            household=self.first_household,
            name="Vaatwastabletten",
            quantity="1",
            unit="stuks",
            minimum_quantity="2",
            category="Schoonmaak",
        )
        self.client.force_login(self.owner)

        response = self.client.get(reverse("household:index"), {"tab": "voorraad"})
        self.assertContains(response, "Vaatwastabletten")
        self.assertContains(response, "Laag")

        self.client.post(reverse("household:adjust_pantry_item", args=[item.id]), {"delta": "2"})
        item.refresh_from_db()
        self.assertEqual(item.quantity, 3)

        self.client.post(reverse("household:adjust_pantry_item", args=[item.id]), {"delta": "-9"})
        item.refresh_from_db()
        self.assertEqual(item.quantity, 0)
        self.client.post(reverse("household:add_pantry_item_to_shopping_list", args=[item.id]))
        shopping_item = ShoppingItem.objects.get(household=self.first_household, name="Vaatwastabletten", completed_at__isnull=True)
        self.assertEqual(shopping_item.quantity, "2 stuks")
        self.assertEqual(shopping_item.category, "Schoonmaak")
        refresh_prices.assert_called_once_with(self.first_household.id)

    def test_pantry_actions_are_household_scoped(self):
        item = PantryItem.objects.create(household=self.first_household, name="Koffie")
        self.client.force_login(self.child)

        response = self.client.post(reverse("household:adjust_pantry_item", args=[item.id]), {"delta": "1"})

        self.assertEqual(response.status_code, 404)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 0)

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
        payload = {"retailer": "ah", "price": "4.99", "unit_label": "500 g", "product_url": "https://example.test/koffie"}
        self.client.post(reverse("household:save_shopping_price", args=[item.id]), payload)
        payload["price"] = "4.49"
        self.client.post(reverse("household:save_shopping_price", args=[item.id]), payload)
        price = ShoppingPrice.objects.get(item=item, retailer="ah")
        self.assertEqual(str(price.price), "4.49")
        self.assertFalse(price.is_offer)
        self.assertEqual(price.source, ShoppingPrice.Source.MANUAL)
        self.assertEqual(ShoppingPriceSnapshot.objects.filter(item=item, retailer="ah").count(), 2)

    def test_price_comparison_keeps_each_retailer_in_its_own_cell(self):
        self.client.force_login(self.owner)
        shopping_list = ShoppingList.objects.create(household=self.first_household, name="Boodschappen")
        item = ShoppingItem.objects.create(household=self.first_household, list=shopping_list, name="Koffie")
        ShoppingPrice.objects.create(household=self.first_household, item=item, retailer=ShoppingPrice.Retailer.ALBERT_HEIJN, price="4.49", unit_label="500 g", product_url="https://example.test/koffie")
        ShoppingPrice.objects.create(household=self.first_household, item=item, retailer=ShoppingPrice.Retailer.KAUFLAND, price="3.99")

        response = self.client.get(reverse("household:index"), {"tab": "prijzen"})

        self.assertContains(response, 'class="price-matrix"')
        self.assertContains(response, 'retailer-ah')
        self.assertContains(response, 'retailer-jumbo is-empty')
        self.assertContains(response, 'retailer-lidl is-empty')
        self.assertContains(response, 'retailer-kaufland')
        self.assertContains(response, "Nog niet geprijsd")
        self.assertContains(response, "Basisprijs niet beschikbaar")
        self.assertContains(response, 'https://example.test/koffie')
        totals = {total["retailer"]: total for total in response.context["price_totals"]}
        headers = {header["retailer"]: header for header in response.context["price_retailer_headers"]}
        self.assertEqual(totals[ShoppingPrice.Retailer.ALBERT_HEIJN]["total"], Decimal("4.49"))
        self.assertEqual(totals[ShoppingPrice.Retailer.KAUFLAND]["missing_items"], 0)
        self.assertEqual(headers[ShoppingPrice.Retailer.JUMBO]["priced_items"], 0)

    def test_insights_show_frequent_products_and_price_movement(self):
        self.client.force_login(self.owner)
        shopping_list = ShoppingList.objects.create(household=self.first_household, name="Boodschappen")
        first = ShoppingItem.objects.create(household=self.first_household, list=shopping_list, name="Komkommer", completed_at=timezone.now() - timedelta(days=15))
        ShoppingItem.objects.create(household=self.first_household, list=shopping_list, name="Komkommer", completed_at=timezone.now() - timedelta(days=3))
        old_snapshot = ShoppingPriceSnapshot.objects.create(household=self.first_household, item=first, retailer=ShoppingPrice.Retailer.JUMBO, price="0.89", source=ShoppingPrice.Source.MANUAL)
        current_snapshot = ShoppingPriceSnapshot.objects.create(household=self.first_household, item=first, retailer=ShoppingPrice.Retailer.JUMBO, price="1.19", source=ShoppingPrice.Source.MANUAL)
        ShoppingPriceSnapshot.objects.filter(pk=old_snapshot.pk).update(observed_at=timezone.now() - timedelta(days=14))
        ShoppingPriceSnapshot.objects.filter(pk=current_snapshot.pk).update(observed_at=timezone.now() - timedelta(days=1))

        response = self.client.get(reverse("household:index"), {"tab": "inzicht"})

        self.assertContains(response, "Boodschappatronen")
        self.assertContains(response, "Komkommer")
        self.assertContains(response, "+€ 0,30")

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

    @patch("household.price_providers.requests.get")
    def test_checkjebon_skips_prepared_variants_for_a_single_fresh_product(self, get):
        from household import price_providers

        price_providers._checkjebon_cache = None
        get.return_value.json.return_value = [
            {"n": "ah", "u": "https://ah.example.test", "d": [
                {"n": "AH Kopsoep tomaat", "p": 0.99, "s": "3 stuks", "l": "/kopsoep"},
                {"n": "AH Hummus tomaat", "p": 1.99, "s": "200 g", "l": "/hummus"},
                {"n": "AH Trostomaten", "p": 2.49, "s": "500 g", "l": "/trostomaten"},
            ]},
        ]
        get.return_value.raise_for_status.return_value = None
        item = ShoppingItem.objects.create(household=self.first_household, list=ShoppingList.objects.create(household=self.first_household, name="Boodschappen"), name="Tomaat", quantity="5")

        results = fetch_checkjebon_prices([item])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].matched_product_name, "AH Trostomaten")

    @patch("household.price_providers.fetch_prijsprofeet_offers", return_value=[])
    @patch("household.price_providers.fetch_checkjebon_prices", return_value=[])
    def test_price_sync_removes_stale_checkjebon_matches(self, _base_prices, _offers):
        shopping_list = ShoppingList.objects.create(household=self.first_household, name="Boodschappen")
        item = ShoppingItem.objects.create(household=self.first_household, list=shopping_list, name="Tomaat")
        ShoppingPrice.objects.create(
            household=self.first_household,
            item=item,
            retailer=ShoppingPrice.Retailer.ALBERT_HEIJN,
            price="0.99",
            source=ShoppingPrice.Source.CHECKJEBON,
            matched_product_name="AH Kopsoep tomaat",
        )

        refresh_household_prices(self.first_household)

        self.assertFalse(ShoppingPrice.objects.filter(item=item).exists())

    @patch("household.price_providers.fetch_prijsprofeet_offers")
    @patch("household.price_providers.fetch_checkjebon_prices")
    def test_price_sync_keeps_offers_separate_from_base_prices_and_preserves_manual_prices(self, base_prices, offers):
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
        self.assertFalse(price.is_offer)
        self.assertEqual(price.source, ShoppingPrice.Source.CHECKJEBON)
        self.assertEqual(str(price.price), "1.29")
        offer = ShoppingOffer.objects.get(item=automatic, retailer=ShoppingPrice.Retailer.JUMBO)
        self.assertEqual(str(offer.price), "0.99")
        self.assertEqual(offer.source, ShoppingPrice.Source.PRIJSPROFEET)
        self.assertEqual(str(ShoppingPrice.objects.get(item=manual, retailer=ShoppingPrice.Retailer.JUMBO).price), "6.50")
        self.assertEqual(ShoppingPriceSnapshot.objects.filter(item=automatic, retailer=ShoppingPrice.Retailer.JUMBO).count(), 1)

        refresh_household_prices(self.first_household)
        self.assertEqual(ShoppingPriceSnapshot.objects.filter(item=automatic, retailer=ShoppingPrice.Retailer.JUMBO).count(), 1)
        self.assertEqual(ShoppingOffer.objects.filter(item=automatic, retailer=ShoppingPrice.Retailer.JUMBO).count(), 1)
        self.assertEqual(
            ShoppingPriceProviderStatus.objects.get(
                household=self.first_household,
                provider=ShoppingPriceProviderStatus.Provider.CHECKJEBON,
            ).status,
            ShoppingPriceProviderStatus.Status.SUCCEEDED,
        )

        self.client.force_login(self.owner)
        response = self.client.get(reverse("household:index"), {"tab": "prijzen"})
        self.assertContains(response, "Basisprijzen via Checkjebon")
        self.assertContains(response, "€ 1,29")
        self.assertContains(response, "Aanbieding € 0,99")
        self.assertContains(response, "prijsvergelijkingen bijgewerkt")

    @patch("household.price_providers.fetch_prijsprofeet_offers", side_effect=PriceProviderError("tijdelijk onbereikbaar"))
    @patch("household.price_providers.fetch_checkjebon_prices", return_value=[])
    def test_price_sync_preserves_previous_offers_when_offer_provider_is_unavailable(self, _base_prices, _offers):
        shopping_list = ShoppingList.objects.create(household=self.first_household, name="Boodschappen")
        item = ShoppingItem.objects.create(household=self.first_household, list=shopping_list, name="Koffie")
        ShoppingOffer.objects.create(
            household=self.first_household,
            item=item,
            retailer=ShoppingPrice.Retailer.JUMBO,
            price="4.99",
            source=ShoppingPrice.Source.PRIJSPROFEET,
            offer_label="Bonus",
        )

        result = refresh_household_prices(self.first_household)

        self.assertEqual(result["errors"], 1)
        self.assertEqual(ShoppingOffer.objects.filter(item=item).count(), 1)
        status = ShoppingPriceProviderStatus.objects.get(
            household=self.first_household,
            provider=ShoppingPriceProviderStatus.Provider.PRIJSPROFEET,
        )
        self.assertEqual(status.status, ShoppingPriceProviderStatus.Status.FAILED)
        self.assertIn("tijdelijk onbereikbaar", status.detail)

    @patch("household.views.refresh_household_shopping_prices.delay")
    def test_parent_can_start_a_price_refresh(self, delay):
        self.client.force_login(self.owner)

        response = self.client.post(reverse("household:refresh_prices"))

        self.assertRedirects(response, f"{reverse('household:index')}?tab=prijzen")
        delay.assert_called_once_with(self.first_household.id)

    def test_receipt_ocr_stores_text_and_detected_total(self):
        shopping_list = ShoppingList.objects.create(household=self.first_household, name="Boodschappen")
        expected_item = ShoppingItem.objects.create(household=self.first_household, list=shopping_list, name="Komkommer")
        receipt = Receipt.objects.create(household=self.first_household, retailer="Jumbo", image=SimpleUploadedFile("bon.jpg", b"image", content_type="image/jpeg"))
        with patch("household.ocr.Image.open") as image_open, patch("household.ocr.pytesseract.image_to_string", return_value="JUMBO\n14-07-2026\nKOMKOMMER    0,79\n2 x HAVERMELK    3,98\nTOTAAL 4,77"):
            image_open.return_value.__enter__.return_value = object()
            from household.ocr import process_receipt
            process_receipt(receipt.id)
        receipt.refresh_from_db()
        self.assertEqual(receipt.ocr_status, Receipt.OcrStatus.COMPLETE)
        self.assertEqual(str(receipt.total_amount), "4.77")
        self.assertEqual(receipt.purchased_on, date(2026, 7, 14))
        lines = list(ReceiptLineItem.objects.filter(receipt=receipt).order_by("id"))
        self.assertEqual([(line.name, str(line.total_price)) for line in lines], [("KOMKOMMER", "0.79"), ("HAVERMELK", "3.98")])
        self.assertEqual(str(lines[1].quantity), "2.00")
        self.assertEqual(str(lines[1].unit_price), "1.99")
        self.assertEqual(lines[0].shopping_item, expected_item)

    def test_receipt_line_parser_excludes_totals_and_payment_rows(self):
        rows = parse_receipt_line_items("KOMKOMMER    0,79\n2 x HAVERMELK    3,98\nSUBTOTAAL    4,77\nPIN    4,77\nTOTAAL    4,77")

        self.assertEqual([row["name"] for row in rows], ["KOMKOMMER", "HAVERMELK"])

    def test_receipt_ocr_detects_a_retailer_when_the_upload_form_left_it_empty(self):
        receipt = Receipt.objects.create(household=self.first_household, image=SimpleUploadedFile("bon.jpg", b"image", content_type="image/jpeg"))
        with patch("household.ocr.Image.open") as image_open, patch("household.ocr.pytesseract.image_to_string", return_value="Albert Heijn\n2026-07-14\nTOTAAL 12,34"):
            image_open.return_value.__enter__.return_value = object()
            from household.ocr import process_receipt
            process_receipt(receipt.id)

        receipt.refresh_from_db()
        self.assertEqual(receipt.retailer, "Albert Heijn")
        self.assertEqual(receipt.purchased_on, date(2026, 7, 14))

    def test_receipt_insight_compares_an_exactly_matched_line_with_current_store_price(self):
        shopping_list = ShoppingList.objects.create(household=self.first_household, name="Boodschappen")
        item = ShoppingItem.objects.create(household=self.first_household, list=shopping_list, name="Komkommer")
        ShoppingPrice.objects.create(
            household=self.first_household,
            item=item,
            retailer=ShoppingPrice.Retailer.JUMBO,
            price="0.85",
        )
        receipt = Receipt.objects.create(
            household=self.first_household,
            retailer="Jumbo",
            purchased_on=timezone.localdate(),
            ocr_status=Receipt.OcrStatus.COMPLETE,
            image=SimpleUploadedFile("bon.jpg", b"image", content_type="image/jpeg"),
        )
        ReceiptLineItem.objects.create(
            household=self.first_household,
            receipt=receipt,
            shopping_item=item,
            name="KOMKOMMER",
            total_price="0.79",
        )
        self.client.force_login(self.owner)

        response = self.client.get(f"{reverse('household:index')}?tab=inzicht")

        self.assertContains(response, "gekoppeld aan Komkommer")
        self.assertContains(response, "Vergelijkprijs € 0,85")
        self.assertContains(response, "Gekocht via bonnen")

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
