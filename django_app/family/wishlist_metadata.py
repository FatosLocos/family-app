"""Safe, best-effort product metadata extraction for wishlist URLs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
import ipaddress
import json
import re
import socket
from urllib.parse import urlparse

import requests


MAX_DOCUMENT_BYTES = 700_000
REQUEST_TIMEOUT = (3.05, 8)
USER_AGENT = "FamilyAppWishlist/1.0 (+https://github.com/FatosLocos/family-app)"


class WishlistMetadataError(ValueError):
    """A product page could not be read safely or did not expose metadata."""


@dataclass(frozen=True)
class WishlistMetadata:
    title: str = ""
    image_url: str = ""
    price: Decimal | None = None
    category: str = "Overig"

    def as_json(self) -> dict[str, str | None]:
        payload = asdict(self)
        payload["price"] = f"{self.price:.2f}" if self.price is not None else None
        return payload


class _MetadataParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title = ""
        self._in_title = False
        self._title_parts: list[str] = []
        self._json_ld_parts: list[str] = []
        self._in_json_ld = False

    def handle_starttag(self, tag, attrs):
        attributes = {key.lower(): value or "" for key, value in attrs}
        if tag == "meta":
            key = (attributes.get("property") or attributes.get("name") or attributes.get("itemprop") or "").lower()
            content = attributes.get("content", "").strip()
            if key and content and key not in self.meta:
                self.meta[key] = content
        elif tag == "title":
            self._in_title = True
        elif tag == "script" and attributes.get("type", "").lower() == "application/ld+json":
            self._in_json_ld = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "script":
            self._in_json_ld = False

    def handle_data(self, data):
        if self._in_title:
            self._title_parts.append(data)
        if self._in_json_ld:
            self._json_ld_parts.append(data)

    def close(self):
        super().close()
        self.title = " ".join(self._title_parts).strip()

    def products(self):
        for source in self._json_ld_parts:
            try:
                document = json.loads(source)
            except json.JSONDecodeError:
                continue
            yield from _product_nodes(document)


def _product_nodes(value):
    if isinstance(value, list):
        for item in value:
            yield from _product_nodes(item)
        return
    if not isinstance(value, dict):
        return
    item_type = value.get("@type", "")
    types = item_type if isinstance(item_type, list) else [item_type]
    if any(str(entry).lower() == "product" for entry in types):
        yield value
    graph = value.get("@graph")
    if graph:
        yield from _product_nodes(graph)


def _validate_public_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise WishlistMetadataError("Gebruik een geldige publieke productlink.")
    if parsed.hostname.lower() == "localhost":
        raise WishlistMetadataError("Lokale adressen kunnen niet worden opgehaald.")
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(parsed.hostname, None, type=socket.SOCK_STREAM)}
    except socket.gaierror as error:
        raise WishlistMetadataError("Deze productlink kon niet worden gevonden.") from error
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            raise WishlistMetadataError("Lokale adressen kunnen niet worden opgehaald.")
    return parsed.geturl()


def _read_page(url: str) -> tuple[str, str]:
    current_url = _validate_public_url(url)
    for _ in range(4):
        try:
            response = requests.get(
                current_url,
                headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
                timeout=REQUEST_TIMEOUT,
                allow_redirects=False,
                stream=True,
            )
        except requests.RequestException as error:
            raise WishlistMetadataError("De productpagina is tijdelijk niet bereikbaar.") from error
        location = response.headers.get("Location")
        if response.is_redirect and location:
            current_url = _validate_public_url(requests.compat.urljoin(current_url, location))
            continue
        if response.status_code >= 400:
            raise WishlistMetadataError("De productpagina gaf geen bruikbare reactie.")
        content_type = response.headers.get("Content-Type", "").lower()
        if content_type and "html" not in content_type:
            raise WishlistMetadataError("Deze link verwijst niet naar een productpagina.")
        content = bytearray()
        for chunk in response.iter_content(16_384):
            content.extend(chunk)
            if len(content) > MAX_DOCUMENT_BYTES:
                break
        encoding = response.encoding or "utf-8"
        return current_url, content.decode(encoding, errors="replace")
    raise WishlistMetadataError("De productlink heeft te veel doorverwijzingen.")


def _as_text(value) -> str:
    return " ".join(str(value or "").split())[:240]


def _extract_image(value) -> str:
    if isinstance(value, list):
        value = value[0] if value else ""
    if isinstance(value, dict):
        value = value.get("url") or value.get("contentUrl") or ""
    return str(value or "").strip()[:500]


def _parse_price(value) -> Decimal | None:
    if value is None:
        return None
    match = re.search(r"(?:EUR|€)?\s*([0-9]{1,5}(?:[.\s][0-9]{3})*(?:[,\.][0-9]{1,2})?)", str(value), re.I)
    if not match:
        return None
    number = match.group(1).replace(" ", "")
    if number.count(",") == 1:
        number = number.replace(".", "").replace(",", ".")
    try:
        amount = Decimal(number).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None
    return amount if Decimal("0") <= amount <= Decimal("99999.99") else None


def _infer_category(title: str, explicit_category: str = "") -> str:
    if explicit_category:
        return _as_text(explicit_category)[:80]
    text = title.casefold()
    keywords = {
        "Boeken": ("boek", "roman", "isbn"),
        "Speelgoed": ("lego", "spel", "puzzel", "pop", "knuffel"),
        "Elektronica": ("koptelefoon", "telefoon", "ipad", "speaker", "camera"),
        "Kleding": ("shirt", "trui", "broek", "schoenen", "jas"),
        "Sport": ("fiets", "sport", "voetbal", "fitness"),
    }
    for category, terms in keywords.items():
        if any(term in text for term in terms):
            return category
    return "Overig"


def fetch_wishlist_metadata(url: str) -> WishlistMetadata:
    """Fetch Open Graph and JSON-LD product details from a public product URL."""

    _, document = _read_page(url)
    parser = _MetadataParser()
    parser.feed(document)
    parser.close()
    meta = parser.meta
    product = next(iter(parser.products()), {})
    offers = product.get("offers", {}) if isinstance(product, dict) else {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    title = _as_text(meta.get("og:title") or product.get("name") or meta.get("twitter:title") or parser.title)
    image_url = _extract_image(meta.get("og:image") or product.get("image") or meta.get("twitter:image"))
    price = _parse_price(
        meta.get("product:price:amount")
        or meta.get("price")
        or (offers.get("price") if isinstance(offers, dict) else None)
    )
    category = _infer_category(title, meta.get("product:category") or meta.get("category") or product.get("category", ""))
    if not title:
        raise WishlistMetadataError("Er zijn geen productgegevens gevonden op deze link.")
    return WishlistMetadata(title=title, image_url=image_url, price=price, category=category)
