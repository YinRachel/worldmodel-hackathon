"""Local concept search for the demo; no retailer or live-search claims."""
import json
import re
from pathlib import Path


CATALOG_PATH = Path(__file__).with_name("furniture_catalog.json")


def _catalog():
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def catalog_info():
    """Return user-facing provenance and limitations for the catalog."""
    data = _catalog()
    return {"label": data["label"], "notice": data["notice"],
            "source": "local_demo", "live_search": False,
            "supports_price_filter": False, "count": len(data["products"])}


def _public_product(product):
    return {**product, "is_demo": True, "price": None,
            "product_url": None, "image_url": None,
            "dimensions_note": "Illustrative concept dimensions; not verified product measurements."}


def get_product(product_id):
    """Return a concept by its stable ID, or None if unknown."""
    for product in _catalog()["products"]:
        if product["id"] == product_id:
            return _public_product(product)
    return None


def search_catalog(query=""):
    """Match local sofa concepts using descriptive words and seat counts.

    No price filtering or web retrieval is performed. Unknown descriptive
    queries return no results rather than inventing an available product.
    """
    if not isinstance(query, str):
        raise ValueError("Search query must be text.")
    query = query.strip().lower()[:500]
    tokens = set(re.findall(r"[a-z]+", query.replace("mid-century", "midcentury")))
    products = _catalog()["products"]
    vocabulary = set()
    token_sets = {}
    for product in products:
        words = " ".join([product["name"], product["style"], product["color"], *product["tags"]])
        product_tokens = set(re.findall(r"[a-z]+", words.lower().replace("mid-century", "midcentury")))
        token_sets[product["id"]] = product_tokens
        vocabulary.update(product_tokens)

    neutral = {"a", "an", "the", "i", "want", "would", "like", "please", "find", "search", "for", "me",
               "show", "some", "sofa", "sofas", "couch", "couches", "with", "and", "in", "seat", "seats", "seater",
               "two", "three", "under", "below", "less", "than", "pounds", "gbp", "budget"}
    constraints = (tokens & vocabulary) - neutral
    seat_match = re.search(r"\b(2|3|two|three)[ -]?(?:seat(?:s|er)?|person)\b", query)
    seat_count = None
    if seat_match:
        seat_count = {"2": 2, "two": 2, "3": 3, "three": 3}[seat_match.group(1)]
    if not constraints and (tokens - neutral) and seat_count is None:
        return []
    return [_public_product(p) for p in products
            if constraints <= token_sets[p["id"]]
            and (seat_count is None or p["seats"] == seat_count)]
