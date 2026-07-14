"""Persist current grocery prices while retaining meaningful historic changes."""

from household.models import ShoppingPrice, ShoppingPriceSnapshot


TRACKED_FIELDS = (
    "price",
    "unit_label",
    "is_offer",
    "offer_label",
    "regular_price",
    "offer_valid_until",
    "product_url",
    "source",
    "matched_product_name",
)


def save_price_observation(*, household, item, retailer, values):
    """Update the current price and retain a snapshot only when it changed."""
    current = ShoppingPrice.objects.for_household(household).filter(item=item, retailer=retailer).first()
    changed = current is None or any(getattr(current, field) != values.get(field) for field in TRACKED_FIELDS)

    if current is None:
        current = ShoppingPrice(household=household, item=item, retailer=retailer)
    for field in TRACKED_FIELDS:
        setattr(current, field, values.get(field))
    current.save()

    if changed:
        ShoppingPriceSnapshot.objects.create(
            household=household,
            item=item,
            retailer=retailer,
            price=current.price,
            unit_label=current.unit_label,
            is_offer=current.is_offer,
            offer_label=current.offer_label,
            regular_price=current.regular_price,
            source=current.source,
        )
    return current, changed
