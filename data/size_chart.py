"""
Shoe size chart: EU size → cm by brand and category.

Usage:
    from data.size_chart import get_size_cm
    cm = get_size_cm("Babolat", "Padel Shoes Man", "42")  # → 26.5
"""

# (brand_lower, category, eu_size) → cm
SIZE_CHART = {
    # babolat
    ("babolat", "junior", "32"): 20.5,
    ("babolat", "junior", "33"): 21.0,
    ("babolat", "junior", "33.5"): 21.3,
    ("babolat", "junior", "34"): 21.5,
    ("babolat", "junior", "35"): 22.0,
    ("babolat", "junior", "35.5"): 22.3,
    ("babolat", "junior", "36"): 22.5,
    ("babolat", "junior", "36.5"): 23.0,
    ("babolat", "junior", "37"): 23.5,
    ("babolat", "junior", "38"): 24.0,
    ("babolat", "junior", "38.5"): 24.5,
    ("babolat", "junior", "39"): 25.0,
    ("babolat", "junior", "40"): 25.3,
    ("babolat", "men", "39"): 25.0,
    ("babolat", "men", "40"): 25.3,
    ("babolat", "men", "40.5"): 25.5,
    ("babolat", "men", "41"): 26.0,
    ("babolat", "men", "42"): 26.5,
    ("babolat", "men", "42.5"): 27.0,
    ("babolat", "men", "43"): 27.5,
    ("babolat", "men", "44"): 28.0,
    ("babolat", "men", "44.5"): 28.3,
    ("babolat", "men", "45"): 28.5,
    ("babolat", "men", "46"): 29.0,
    ("babolat", "men", "46.5"): 29.3,
    ("babolat", "men", "47"): 29.5,
    ("babolat", "men", "48"): 30.0,
    ("babolat", "women", "36"): 22.5,
    ("babolat", "women", "36.5"): 23.0,
    ("babolat", "women", "37"): 23.5,
    ("babolat", "women", "38"): 24.0,
    ("babolat", "women", "38.5"): 24.5,
    ("babolat", "women", "39"): 25.0,
    ("babolat", "women", "40"): 25.3,
    ("babolat", "women", "40.5"): 25.5,
    ("babolat", "women", "41"): 26.0,
    ("babolat", "women", "42"): 26.5,
    # bullpadel (unisex)
    ("bullpadel", "unisex", "31"): 18.5,
    ("bullpadel", "unisex", "32"): 19.2,
    ("bullpadel", "unisex", "33"): 19.9,
    ("bullpadel", "unisex", "34"): 20.5,
    ("bullpadel", "unisex", "35"): 21.2,
    ("bullpadel", "unisex", "36"): 21.8,
    ("bullpadel", "unisex", "37"): 22.5,
    ("bullpadel", "unisex", "37.5"): 23.1,
    ("bullpadel", "unisex", "38"): 23.4,
    ("bullpadel", "unisex", "38.5"): 23.8,
    ("bullpadel", "unisex", "39"): 24.1,
    ("bullpadel", "unisex", "39.5"): 24.5,
    ("bullpadel", "unisex", "40"): 24.8,
    ("bullpadel", "unisex", "41"): 25.2,
    ("bullpadel", "unisex", "42"): 25.9,
    ("bullpadel", "unisex", "42.5"): 26.6,
    ("bullpadel", "unisex", "43"): 27.0,
    ("bullpadel", "unisex", "43.5"): 27.3,
    ("bullpadel", "unisex", "44"): 27.7,
    ("bullpadel", "unisex", "44.5"): 28.0,
    ("bullpadel", "unisex", "45"): 28.3,
    ("bullpadel", "unisex", "46"): 28.6,
    # head
    ("head", "junior", "32"): 20.0,
    ("head", "junior", "33"): 20.5,
    ("head", "junior", "33.5"): 21.0,
    ("head", "junior", "34"): 21.5,
    ("head", "junior", "34.5"): 22.0,
    ("head", "junior", "35"): 22.5,
    ("head", "junior", "36"): 23.0,
    ("head", "junior", "36.5"): 23.5,
    ("head", "junior", "37"): 24.0,
    ("head", "junior", "38"): 24.5,
    ("head", "junior", "38.5"): 25.0,
    ("head", "junior", "39"): 25.5,
    ("head", "junior", "40"): 26.0,
    ("head", "men", "39"): 25.0,
    ("head", "men", "40"): 25.5,
    ("head", "men", "40.5"): 26.0,
    ("head", "men", "41"): 26.5,
    ("head", "men", "42"): 27.0,
    ("head", "men", "42.5"): 27.5,
    ("head", "men", "43"): 28.0,
    ("head", "men", "44"): 28.5,
    ("head", "men", "44.5"): 29.0,
    ("head", "men", "45"): 29.5,
    ("head", "men", "46"): 30.0,
    ("head", "men", "46.5"): 30.5,
    ("head", "men", "47"): 31.5,
    ("head", "women", "36"): 22.5,
    ("head", "women", "36.5"): 23.0,
    ("head", "women", "37"): 23.5,
    ("head", "women", "38"): 24.0,
    ("head", "women", "38.5"): 24.5,
    ("head", "women", "39"): 25.0,
    ("head", "women", "40"): 25.5,
    ("head", "women", "40.5"): 26.0,
    ("head", "women", "41"): 26.5,
    ("head", "women", "42"): 27.0,
    # kswiss
    ("kswiss", "junior", "35.5"): 22.0,
    ("kswiss", "junior", "36"): 22.5,
    ("kswiss", "junior", "37"): 23.0,
    ("kswiss", "junior", "37.5"): 23.5,
    ("kswiss", "junior", "38"): 24.0,
    ("kswiss", "junior", "39"): 24.5,
    ("kswiss", "men", "39.5"): 25.0,
    ("kswiss", "men", "40"): 25.5,
    ("kswiss", "men", "41"): 26.0,
    ("kswiss", "men", "41.5"): 26.5,
    ("kswiss", "men", "42"): 27.0,
    ("kswiss", "men", "42.5"): 27.5,
    ("kswiss", "men", "43"): 28.0,
    ("kswiss", "men", "44"): 28.5,
    ("kswiss", "men", "44.5"): 29.0,
    ("kswiss", "men", "45"): 29.5,
    ("kswiss", "men", "46"): 30.0,
    ("kswiss", "men", "46.5"): 30.5,
    ("kswiss", "men", "47"): 31.0,
    ("kswiss", "women", "35.5"): 22.0,
    ("kswiss", "women", "36"): 22.5,
    ("kswiss", "women", "37"): 23.0,
    ("kswiss", "women", "37.5"): 23.5,
    ("kswiss", "women", "38"): 24.0,
    ("kswiss", "women", "39"): 24.5,
    ("kswiss", "women", "39.5"): 25.0,
    ("kswiss", "women", "40"): 25.5,
    ("kswiss", "women", "41"): 26.0,
    ("kswiss", "women", "41.5"): 26.5,
    ("kswiss", "women", "42"): 27.0,
    # wilson
    ("wilson", "junior", "32.5"): 21.0,
    ("wilson", "junior", "33.5"): 21.5,
    ("wilson", "junior", "34"): 22.0,
    ("wilson", "junior", "34.5"): 22.3,
    ("wilson", "junior", "35.5"): 22.5,
    ("wilson", "junior", "36"): 23.0,
    ("wilson", "junior", "36.5"): 23.5,
    ("wilson", "junior", "37"): 24.0,
    ("wilson", "junior", "37.5"): 24.3,
    ("wilson", "junior", "38.5"): 24.5,
    ("wilson", "junior", "39"): 25.0,
    ("wilson", "junior", "39.5"): 25.5,
    ("wilson", "men", "39"): 24.0,
    ("wilson", "men", "39.5"): 24.5,
    ("wilson", "men", "40.5"): 25.0,
    ("wilson", "men", "41"): 25.5,
    ("wilson", "men", "41.5"): 26.0,
    ("wilson", "men", "42"): 26.5,
    ("wilson", "men", "42.5"): 27.0,
    ("wilson", "men", "43.5"): 27.5,
    ("wilson", "men", "44"): 28.0,
    ("wilson", "men", "44.5"): 28.5,
    ("wilson", "men", "45.5"): 29.0,
    ("wilson", "men", "46"): 29.5,
    ("wilson", "men", "46.5"): 30.0,
    ("wilson", "men", "47.5"): 30.5,
    ("wilson", "men", "48"): 31.0,
    ("wilson", "women", "35"): 21.5,
    ("wilson", "women", "35.5"): 22.0,
    ("wilson", "women", "36.5"): 22.5,
    ("wilson", "women", "37"): 23.0,
    ("wilson", "women", "37.5"): 23.5,
    ("wilson", "women", "38.5"): 24.0,
    ("wilson", "women", "39"): 24.5,
    ("wilson", "women", "39.5"): 25.0,
    ("wilson", "women", "40.5"): 25.5,
    ("wilson", "women", "41"): 26.0,
    ("wilson", "women", "41.5"): 26.5,
    ("wilson", "women", "42"): 27.0,
}


def _detect_shoe_type(category_name: str | None) -> str | None:
    """Detect shoe type from category name."""
    if not category_name:
        return None
    name = category_name.lower()
    if "junior" in name or "kid" in name or "child" in name:
        return "junior"
    if "woman" in name or "women" in name or "female" in name:
        return "women"
    if "man" in name or "men" in name or "male" in name:
        return "men"
    return None


def get_size_cm(brand: str, category_names: list[str], size_label: str) -> float | None:
    """Look up cm for a shoe size.

    Args:
        brand: Brand name (e.g. "Babolat")
        category_names: List of category names the product belongs to
        size_label: EU size (e.g. "42")

    Returns:
        cm value or None if not found.
    """
    if not brand:
        return None

    brand_key = brand.lower().replace("-", "").replace(" ", "")
    size_key = size_label.strip()

    # Detect shoe type from category names
    shoe_type = None
    for cat in category_names:
        shoe_type = _detect_shoe_type(cat)
        if shoe_type:
            break

    # Try exact match first
    if shoe_type:
        cm = SIZE_CHART.get((brand_key, shoe_type, size_key))
        if cm is not None:
            return cm

    # Fallback to unisex
    cm = SIZE_CHART.get((brand_key, "unisex", size_key))
    if cm is not None:
        return cm

    # If no shoe_type detected, try all categories for this brand+size
    if not shoe_type:
        for cat_type in ("men", "women", "junior"):
            cm = SIZE_CHART.get((brand_key, cat_type, size_key))
            if cm is not None:
                return cm

    return None
