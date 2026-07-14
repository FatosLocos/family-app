"""Token-free price and offer sources used for daily shopping comparisons."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import re
import time
import unicodedata
from urllib.parse import urljoin

import requests

from household.models import ShoppingItem, ShoppingPrice
from household.price_history import save_price_observation


CHECKJEBON_URL = "https://www.checkjebon.nl/data/supermarkets.json"
PRIJSPROFEET_URL = "https://www.prijsprofeet.nl/api/v1/search"
REQUEST_TIMEOUT = 15
_checkjebon_cache: tuple[float, list[dict]] | None = None


class PriceProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class PriceResult:
    item_id: int
    retailer: str
    price: Decimal
    matched_product_name: str
    unit_label: str = ""
    product_url: str = ""
    source: str = ShoppingPrice.Source.CHECKJEBON
    is_offer: bool = False
    offer_label: str = ""
    regular_price: Decimal | None = None
    offer_valid_until: date | None = None


def _normalized(value: str) -> str:
    value = unicodedata.normalize("NFD", value.casefold())
    value = "".join(character for character in value if unicodedata.category(character) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _tokens(value: str) -> list[str]:
    ignored = {"x", "stuk", "stuks", "per", "gram", "gr", "g", "kg", "kilo", "ml", "liter", "l"}
    return [token for token in _normalized(value).split() if token not in ignored and not re.fullmatch(r"\d+(?:\.\d+)?", token)]


def _quantity_grams(value: str) -> int | None:
    normalized = _normalized(value).replace(" gr ", " g ")
    multi = re.search(r"(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)\s*(kg|kilo|g|gram)\b", normalized)
    single = re.search(r"(\d+(?:\.\d+)?)\s*(kg|kilo|g|gram)\b", normalized)
    match = multi or single
    if not match:
        return None
    amount = float(match.group(1)) * (float(match.group(2)) if multi else 1)
    unit = match.group(3 if multi else 2)
    return round(amount * (1000 if unit in {"kg", "kilo"} else 1))


def _decimal(value) -> Decimal | None:
    try:
        result = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if Decimal("0") <= result <= Decimal("9999.99") else None


def _package_label(product: dict) -> str:
    return str(product.get("s") or "").strip()


def _matches(item: ShoppingItem, product: dict) -> bool:
    query_tokens = _tokens(f"{item.quantity} {item.name}")
    name = _normalized(str(product.get("n") or ""))
    if not query_tokens or not all(token in name for token in query_tokens):
        return False
    # A plain spread query should not resolve to snack bars or biscuit variants.
    if any(token in {"pasta", "chocopasta", "hazelnootpasta"} for token in query_tokens):
        if any(token in name for token in {"b ready", "bready", "biscuit", "snack", "sticks", "dip"}):
            return False
    return True


def _candidate_score(item: ShoppingItem, product: dict) -> tuple[float, Decimal]:
    product_name = _normalized(str(product.get("n") or ""))
    item_name = _normalized(item.name)
    text_score = 0 if product_name == item_name else len(product_name) / 100
    target_quantity = _quantity_grams(f"{item.quantity} {item.name}")
    candidate_quantity = _quantity_grams(f"{_package_label(product)} {product_name}")
    quantity_score = abs(candidate_quantity - target_quantity) if target_quantity and candidate_quantity else 0
    return (quantity_score + text_score, _decimal(product.get("p")) or Decimal("9999"))


def _checkjebon_data() -> list[dict]:
    global _checkjebon_cache
    if _checkjebon_cache and time.monotonic() - _checkjebon_cache[0] < 3600:
        return _checkjebon_cache[1]
    try:
        response = requests.get(CHECKJEBON_URL, headers={"User-Agent": "FamilyApp/1.0"}, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as error:
        raise PriceProviderError("Checkjebon is tijdelijk niet bereikbaar.") from error
    if not isinstance(payload, list):
        raise PriceProviderError("Checkjebon leverde geen bruikbare prijsdata.")
    _checkjebon_cache = (time.monotonic(), payload)
    return payload


def fetch_checkjebon_prices(items) -> list[PriceResult]:
    stores = {"ah": ShoppingPrice.Retailer.ALBERT_HEIJN, "jumbo": ShoppingPrice.Retailer.JUMBO, "lidl": ShoppingPrice.Retailer.LIDL}
    results: list[PriceResult] = []
    for item in items:
        for store in _checkjebon_data():
            retailer = stores.get(store.get("n"))
            products = store.get("d") if isinstance(store.get("d"), list) else []
            candidates = [product for product in products if isinstance(product, dict) and _matches(item, product) and _decimal(product.get("p")) is not None]
            if not retailer or not candidates:
                continue
            candidate = min(candidates, key=lambda product: _candidate_score(item, product))
            product_path = str(candidate.get("l") or "")
            store_url = str(store.get("u") or "")
            results.append(PriceResult(
                item_id=item.id,
                retailer=retailer,
                price=_decimal(candidate.get("p")),
                matched_product_name=str(candidate.get("n") or item.name),
                unit_label=_package_label(candidate) or item.quantity,
                product_url=urljoin(store_url, product_path) if store_url and product_path else "",
            ))
    return results


def _same_product_word(product_word: str, query_word: str) -> bool:
    return product_word == query_word or product_word.rstrip("sn") == query_word.rstrip("sn")


def _offer_matches(item: ShoppingItem, offer: dict) -> bool:
    if not offer.get("is_promotional") or _decimal(offer.get("price")) is None:
        return False
    if str(offer.get("unified_category") or "") in {"drogisterij", "baby-drogisterij", "huishouden"}:
        return False
    query = [token for token in _tokens(item.name) if len(token) > 2]
    product = [token for token in _tokens(str(offer.get("name") or "")) if len(token) > 2 and token not in {"ah", "jumbo", "lidl", "aldi", "plus", "dirk"}]
    return bool(query and product and len(query) == len(product) and all(_same_product_word(left, right) for left, right in zip(product, query)))


def _offer_score(item: ShoppingItem, offer: dict) -> tuple[float, Decimal]:
    name = _normalized(str(offer.get("name") or ""))
    score = max(0, len(name) - len(_normalized(item.name))) / 10
    regular = _decimal(offer.get("original_price"))
    current = _decimal(offer.get("price")) or Decimal("9999")
    if regular:
        score -= float(regular - current)
    return (score, current)


def _offer_label(offer: dict) -> str:
    keywords = offer.get("promotional_keywords")
    if isinstance(keywords, list) and keywords and keywords[0]:
        return str(keywords[0])[:160]
    return str(offer.get("promotion_type") or "Aanbieding").replace("_", " ")[:160]


def fetch_prijsprofeet_offers(items) -> list[PriceResult]:
    retailers = {"albert_heijn": ShoppingPrice.Retailer.ALBERT_HEIJN, "jumbo": ShoppingPrice.Retailer.JUMBO, "lidl": ShoppingPrice.Retailer.LIDL}
    results: list[PriceResult] = []
    for item in items:
        try:
            response = requests.get(PRIJSPROFEET_URL, params={"q": item.name, "page_size": 20}, headers={"User-Agent": "FamilyApp/1.0"}, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError):
            continue
        offers = payload.get("results") if isinstance(payload, dict) and isinstance(payload.get("results"), list) else []
        for retailer_key, retailer in retailers.items():
            candidates = [offer for offer in offers if isinstance(offer, dict) and offer.get("retailer") == retailer_key and _offer_matches(item, offer)]
            if not candidates:
                continue
            offer = min(candidates, key=lambda value: _offer_score(item, value))
            valid_until = None
            try:
                valid_until = date.fromisoformat(str(offer.get("valid_until") or "")[:10])
            except ValueError:
                pass
            results.append(PriceResult(
                item_id=item.id,
                retailer=retailer,
                price=_decimal(offer.get("price")),
                matched_product_name=str(offer.get("name") or item.name),
                source=ShoppingPrice.Source.PRIJSPROFEET,
                is_offer=True,
                offer_label=_offer_label(offer),
                regular_price=_decimal(offer.get("original_price")),
                offer_valid_until=valid_until,
                product_url=str(offer.get("product_url") or "")[:500],
            ))
    return results


def refresh_household_prices(household) -> dict[str, int]:
    items = list(ShoppingItem.objects.for_household(household).filter(completed_at__isnull=True).order_by("created_at")[:50])
    if not items:
        return {"updated": 0, "offers": 0, "errors": 0}
    items_by_id = {item.id: item for item in items}
    errors = 0
    try:
        base_prices = fetch_checkjebon_prices(items)
    except PriceProviderError:
        base_prices = []
        errors += 1
    offers = fetch_prijsprofeet_offers(items)
    # Offers intentionally overwrite an indicative base price for the same item/store.
    results = {(result.item_id, result.retailer): result for result in base_prices}
    results.update({(result.item_id, result.retailer): result for result in offers})
    updated = offers_count = 0
    for result in results.values():
        existing = ShoppingPrice.objects.for_household(household).filter(item_id=result.item_id, retailer=result.retailer).first()
        if existing and existing.source == ShoppingPrice.Source.MANUAL:
            continue
        values = {
            "price": result.price,
            "unit_label": result.unit_label,
            "is_offer": result.is_offer,
            "offer_label": result.offer_label,
            "regular_price": result.regular_price,
            "offer_valid_until": result.offer_valid_until,
            "product_url": result.product_url,
            "source": result.source,
            "matched_product_name": result.matched_product_name,
        }
        save_price_observation(
            household=household,
            item=items_by_id[result.item_id],
            retailer=result.retailer,
            values=values,
        )
        updated += 1
        offers_count += int(result.is_offer)
    return {"updated": updated, "offers": offers_count, "errors": errors}
