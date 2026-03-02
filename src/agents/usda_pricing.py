import base64
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import anthropic
import requests
from dotenv import load_dotenv

from src.db import models

load_dotenv()

ANTHROPIC_CLIENT = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-haiku-4-5-20251001"
BASE_URL = "https://marsapi.ams.usda.gov/services/v1.2"

# Pre-identified active report IDs closest to Seattle's Pacific supply chain.
# LA Terminal Market -- closest active West Coast produce market —
CATEGORY_REPORTS = {
    "vegetables": 2307,  # Los Angeles Terminal Market Vegetables Prices
    "fruit": 2306,       # Los Angeles Terminal Market Fruit Prices
    "beef": 2833,        # USDA Beef & Pork Variety Meats Report
    "pork": 2838,        # Weekly Pork & Beef Variety Meat Report
    "chicken": 3646,     # Weekly National Chicken Report
}

MARKET_LABEL = "Los Angeles Terminal Market"


def _get_auth_headers():
    key = os.getenv("USDA_API_KEY")
    auth = "Basic " + base64.b64encode(f"{key}:".encode()).decode()
    return {"Accept": "application/json", "Authorization": auth}


def fetch_report_with_retry(slug_id, timeout=30, max_retries=2):
    """
    Fetch a USDA report's data rows with retry + exponential backoff.
    Returns a list of row dicts, or None if all attempts fail.
    """
    headers = _get_auth_headers()
    from datetime import date, timedelta
    # Limit to last 14 days — avoids pulling 100k rows of historical data
    since = (date.today() - timedelta(days=14)).strftime("%m/%d/%Y")

    for attempt in range(max_retries + 1):
        try:
            r = requests.get(
                f"{BASE_URL}/reports/{slug_id}",
                params={"allSections": "true", "report_begin_date": since},
                headers=headers,
                timeout=timeout,
            )
            if r.status_code == 200:
                data = r.json()
                # Response is a list of sections; pricing data lives in "Report Details"
                if isinstance(data, list):
                    for section in data:
                        if isinstance(section, dict) and "Report Details" in section.get("reportSection", ""):
                            return section.get("results", [])
                    # Fallback: return results from any section that has pricing fields
                    for section in data:
                        results = section.get("results", []) if isinstance(section, dict) else []
                        if results and "low_price" in results[0]:
                            return results
                    return []
                return data.get("results", []) if isinstance(data, dict) else []
        except Exception:
            if attempt < max_retries:
                time.sleep(2 ** attempt)
    return None


def map_ingredients_to_usda(ingredient_names):
    """
    Single Claude call to map all ingredients to USDA categories and commodity terms.
    Batching into one call avoids N round-trips and is faster.
    Returns dict: {ingredient_name: {category, commodity, reason}}
    """
    prompt = f"""Map these restaurant ingredients to USDA commodity categories for wholesale price lookup.

Ingredients: {json.dumps(ingredient_names)}

For each ingredient return:
- "category": one of ["vegetables", "fruit", "beef", "pork", "chicken", "seafood", "none"]
  - vegetables: fresh vegetables (peppers, tomatoes, onions, garlic, cabbage, carrots, fennel, tomatillo, serrano, etc.)
  - fruit: botanically fruits — avocado, lime, lemon, pineapple, pomegranate, plantain, cucumber, squash, corn, etc.
            NOTE: avocado, cucumber, squash, and corn are botanically fruits — classify them as "fruit"
  - beef: any beef cut (chuck, ribeye, steak, ground beef, etc.)
  - pork: pork cuts (belly, shoulder, carnitas, etc.)
  - chicken: chicken or poultry
  - seafood: fish, shrimp, shellfish, prawns
  - none: specialty or processed items with no USDA equivalent
         (e.g. oaxaca cheese, cotija, crema, prepared sauces, masa, spice blends, cashew cheese)
- "commodity": lowercase USDA search term (e.g. "jalapeno pepper", "avocado") or null if none
- "reason": one sentence — required when category is "none"

Return ONLY a valid JSON object. Keys are ingredient names exactly as given. No markdown."""

    response = ANTHROPIC_CLIENT.messages.create(
        model=MODEL,
        max_tokens=8096,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    # Extract the JSON object by finding its true boundaries —
    # guards against Claude adding explanation text before or after the JSON
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON object found in Claude response: {raw[:200]}")
    return json.loads(raw[start:end])


def find_price_in_report(rows, commodity_term):
    """
    Search USDA report rows for a commodity match and extract a price.
    USDA reports use inconsistent field names across categories —
    this function tries common patterns rather than assuming structure.
    Returns (price, unit, market) — all None if not found.
    """
    if not rows:
        return None, None, None

    term_lower = commodity_term.lower()
    # Extract clean words (strips punctuation/plurals issue e.g. "peppers," → "peppers")
    term_words = set(re.findall(r"\b\w+\b", term_lower))

    matching = []
    for row in rows:
        for field in ["commodity", "commodityName", "class", "item", "description", "label"]:
            val = str(row.get(field, "")).lower()
            val_words = set(re.findall(r"\b\w+\b", val))
            # Match if: exact substring OR any significant search word found in commodity
            if term_lower in val or any(w in val_words for w in term_words if len(w) > 3):
                matching.append(row)
                break

    if not matching:
        return None, None, None

    row = matching[0]

    # Extract price — USDA AMS uses low_price/high_price; average when both present
    price = None
    try:
        low = row.get("low_price") or row.get("mostly_low_price")
        high = row.get("high_price") or row.get("mostly_high_price")
        if low is not None and high is not None:
            price = (float(low) + float(high)) / 2
        elif low is not None:
            price = float(low)
        elif high is not None:
            price = float(high)
    except (ValueError, TypeError):
        pass

    # Extract unit — USDA AMS uses "package" field
    unit = row.get("package") or row.get("unit_of_sale") or row.get("unit")
    if unit:
        unit = str(unit)

    # Extract market location
    market = (
        row.get("market_location_city")
        or row.get("market_location_name")
        or row.get("office_city")
        or MARKET_LABEL
    )

    return price, unit, market


def normalize_to_per_lb(price, unit):
    """
    Normalize price to per-lb by extracting any weight from the unit string.
    Uses regex to handle any 'X lb' pattern dynamically — no hardcoded values.
    Returns normalized price or None if no lb weight found.
    """
    if price is None or unit is None:
        return None

    unit_lower = unit.lower()

    # Already a per-lb price
    if any(x in unit_lower for x in ["per lb", "/lb", "per pound"]) or unit_lower == "lb":
        return round(price, 4)

    # Extract any number before "lb" — handles 10, 20, 25, 40, 45, 50, 100, etc.
    match = re.search(r"(\d+(?:\.\d+)?)\s*lb", unit_lower)
    if match:
        weight = float(match.group(1))
        if weight > 0:
            return round(price / weight, 4)

    return None


def run_usda_pricing(progress_callback=None):
    """
    Full Step 2 pipeline:
    1. Load all ingredients from DB
    2. Map every ingredient to a USDA category + commodity (one Claude call)
    3. Fetch each unique USDA report once and cache it
    4. Search cached report data for each ingredient's commodity
    5. Normalize price to per-lb where possible
    6. Persist results to ingredient_pricing table

    Ingredients with no USDA equivalent get a null price with a documented reason.
    One ingredient failure never stops the rest.

    Returns a list of result dicts per ingredient.
    """
    ingredients = models.get_all_ingredients()
    if not ingredients:
        return []

    # Clear previous pricing so re-runs don't duplicate rows
    models.clear_ingredient_pricing()

    ingredient_names = [i["name"] for i in ingredients]
    total = len(ingredient_names)

    # ── Step 1: Map all ingredients in one Claude call ─────────────────────
    if progress_callback:
        progress_callback(0, total, "Mapping ingredients to USDA commodities via Claude...")

    mappings = map_ingredients_to_usda(ingredient_names)

    # ── Step 2: Fetch only the unique reports we actually need ──────────────
    needed_categories = {
        m.get("category")
        for m in mappings.values()
        if m.get("category") in CATEGORY_REPORTS
    }

    if progress_callback:
        progress_callback(0, total, f"Fetching {len(needed_categories)} USDA report(s) in parallel...")

    # Fetch all needed reports concurrently — cuts wait time from N×10s to ~10s total
    report_cache = {}
    with ThreadPoolExecutor(max_workers=len(needed_categories) or 1) as executor:
        futures = {
            executor.submit(fetch_report_with_retry, CATEGORY_REPORTS[cat]): cat
            for cat in needed_categories
        }
        for future in as_completed(futures):
            category = futures[future]
            report_cache[category] = future.result()

    # ── Step 3: Price lookup per ingredient ────────────────────────────────
    results = []

    for i, ingredient in enumerate(ingredients):
        name = ingredient["name"]
        if progress_callback:
            progress_callback(i, total, name)

        mapping = mappings.get(name, {})
        category = mapping.get("category", "none")
        commodity = mapping.get("commodity")
        reason = mapping.get("reason", "No USDA commodity equivalent")

        try:
            if category == "none" or not commodity:
                models.insert_ingredient_pricing(
                    ingredient_id=ingredient["id"],
                    commodity=None,
                    price_per_lb=None,
                    original_price=None,
                    original_unit=None,
                    market=None,
                    report_title=None,
                    report_date=None,
                    no_data_reason=reason,
                )
                results.append({"ingredient": name, "status": "no_data", "reason": reason})
                continue

            rows = report_cache.get(category)
            price, unit, market = find_price_in_report(rows, commodity)
            price_per_lb = normalize_to_per_lb(price, unit)

            report_slug = CATEGORY_REPORTS.get(category)
            report_title = f"USDA AMS Report {report_slug} — {category.title()}"

            models.insert_ingredient_pricing(
                ingredient_id=ingredient["id"],
                commodity=commodity,
                price_per_lb=price_per_lb,
                original_price=price,
                original_unit=unit,
                market=market or MARKET_LABEL,
                report_title=report_title,
                report_date=None,
                no_data_reason=None if price else "Commodity not found in report data",
            )

            results.append({
                "ingredient": name,
                "commodity": commodity,
                "price": price,
                "price_per_lb": price_per_lb,
                "unit": unit,
                "market": market,
                "status": "found" if price else "not_found",
            })

        except Exception as e:
            results.append({"ingredient": name, "status": "error", "reason": str(e)})

    return results
