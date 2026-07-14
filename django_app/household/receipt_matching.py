from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from finance.models import Transaction


def match_receipt_to_transaction(receipt) -> bool:
    """Attach an unambiguous outgoing transaction to a receipt.

    A receipt is never relinked automatically once a user or a prior match has
    selected a transaction. Matching is intentionally conservative: amount and
    purchase date must both be available, and a tied best candidate is ignored.
    """
    if receipt.transaction_id or not receipt.total_amount or not receipt.purchased_on:
        return False

    total = abs(Decimal(receipt.total_amount))
    candidates = list(
        Transaction.objects.for_household(receipt.household)
        .filter(
            amount__lt=0,
            booked_at__range=(receipt.purchased_on - timedelta(days=4), receipt.purchased_on + timedelta(days=4)),
        )
        .select_related("account")
    )

    scored = []
    retailer = receipt.retailer.casefold().strip()
    for transaction in candidates:
        amount_difference = abs(abs(transaction.amount) - total)
        if amount_difference > Decimal("0.05"):
            continue
        date_distance = abs((transaction.booked_at - receipt.purchased_on).days)
        haystack = f"{transaction.counterparty} {transaction.description}".casefold()
        retailer_bonus = 0 if retailer and retailer in haystack else 1
        scored.append((amount_difference, retailer_bonus, date_distance, transaction.id, transaction))

    if not scored:
        return False
    scored.sort(key=lambda item: item[:4])
    best = scored[0]
    if len(scored) > 1 and scored[1][:3] == best[:3]:
        return False

    receipt.transaction = best[-1]
    receipt.save(update_fields=["transaction", "updated_at"])
    return True
