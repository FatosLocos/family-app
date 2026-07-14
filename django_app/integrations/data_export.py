from __future__ import annotations

from django.utils import timezone

from family.models import BulletinPost, Contact, ContactPerson, WishItem, WishList
from finance.models import BankAccount, Budget, RecurringRule, Transaction
from household.models import MealPlan, Receipt, Routine, ShoppingItem, ShoppingList, ShoppingPrice, Task
from notifications.models import Notification
from planning.models import CalendarEvent, CalendarSource, IcsSubscription


def household_export(household):
    """Build a portable household export without credentials or uploaded files."""
    return {
        "format": "family-app-export",
        "version": 1,
        "exported_at": timezone.now(),
        "household": {"id": household.id, "name": household.name, "created_at": household.created_at},
        "members": [
            {"name": member.user.display_name, "email": member.user.email, "role": member.role}
            for member in household.memberships.select_related("user").order_by("created_at")
        ],
        "family": {
            "contacts": list(Contact.objects.for_household(household).values("name", "contact_type", "email", "phone", "address", "postal_code", "city", "notes")),
            "people": list(ContactPerson.objects.for_household(household).select_related("contact").values("contact__name", "name", "birth_date", "email", "phone")),
            "wishlists": list(WishList.objects.for_household(household).select_related("owner").values("title", "owner__display_name", "is_shared", "created_at")),
            "wishes": list(WishItem.objects.for_household(household).select_related("wishlist").values("wishlist__title", "title", "url", "image_url", "price", "repeatable", "reserved_by")),
            "bulletin_posts": list(BulletinPost.objects.for_household(household).select_related("author").values("author__display_name", "body", "pinned", "created_at")),
        },
        "household_data": {
            "tasks": list(Task.objects.for_household(household).select_related("assigned_to").values("title", "notes", "assigned_to__display_name", "due_at", "priority", "completed_at", "created_at")),
            "shopping_lists": list(ShoppingList.objects.for_household(household).values("name", "is_default", "created_at")),
            "shopping_items": list(ShoppingItem.objects.for_household(household).select_related("list").values("list__name", "name", "quantity", "category", "recurring", "recurrence_days", "completed_at", "created_at")),
            "shopping_prices": list(ShoppingPrice.objects.for_household(household).select_related("item").values("item__name", "retailer", "price", "unit_label", "is_offer", "offer_label", "product_url", "observed_at")),
            "meals": list(MealPlan.objects.for_household(household).values("title", "planned_for", "notes")),
            "routines": list(Routine.objects.for_household(household).select_related("assigned_to").values("title", "cadence", "assigned_to__display_name", "is_active")),
            "receipts": list(Receipt.objects.for_household(household).values("retailer", "purchased_on", "total_amount", "ocr_text", "ocr_status", "ocr_error", "created_at")),
        },
        "planning": {
            "sources": list(CalendarSource.objects.for_household(household).values("provider", "name", "external_id", "is_enabled", "is_read_only", "last_sync_at")),
            "events": list(CalendarEvent.objects.for_household(household).values("title", "starts_at", "ends_at", "is_all_day", "location", "notes", "external_id")),
            "ics_subscriptions": list(IcsSubscription.objects.for_household(household).select_related("source").values("name", "source__name", "last_error")),
        },
        "finance": {
            "accounts": list(BankAccount.objects.for_household(household).select_related("connection").values("connection__provider", "name", "iban", "currency", "balance", "is_active")),
            "transactions": list(Transaction.objects.for_household(household).select_related("account").values("account__name", "booked_at", "description", "counterparty", "amount", "currency", "payment_type", "metadata", "recurring_override")),
            "recurring_rules": list(RecurringRule.objects.for_household(household).values("merchant", "direction", "group", "expected_amount", "cadence_days", "occurrence_count", "last_seen_at", "user_confirmed", "is_excluded")),
            "budgets": list(Budget.objects.for_household(household).values("name", "monthly_limit", "category")),
        },
        "notifications": list(Notification.objects.for_household(household).values("title", "body", "kind", "action_url", "read_at", "created_at")),
    }
