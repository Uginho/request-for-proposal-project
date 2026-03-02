import json
import os

import anthropic
import pdfplumber
from dotenv import load_dotenv

from src.db import models

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-haiku-4-5-20251001"


def extract_text_from_pdf(pdf_path):
    """Extract raw text from a PDF. pdfplumber handles multi-column layouts better than most parsers."""
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text


def _parse_json_response(raw):
    """Strip markdown code fences if present, then parse JSON."""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        # drop first line (```json or ```) and last line (```)
        raw = "\n".join(lines[1:-1])
    return json.loads(raw)


def parse_menu_into_dishes(menu_text):
    """
    Single Claude call: convert raw menu text into a structured list of dishes.
    Returns a list of dicts: {name, category, description, price}
    """
    prompt = f"""You are given text extracted from a restaurant menu PDF. The layout may be garbled due to multi-column formatting — use context to reconstruct the correct dish groupings.

Parse every dish into a JSON array. Each object must have exactly these keys:
- "name": dish name (string)
- "category": one of ["starters", "salads_soups", "chips_and", "tacos", "sides", "entrees"]
- "description": full ingredient description as it appears on the menu (string)

Include every dish — starters, soups, salads, salsas, tacos, sides, and entrees.
Return ONLY a valid JSON array. No explanation, no markdown.

Menu text:
{menu_text}"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_json_response(response.content[0].text)


def extract_ingredients_for_dish(dish):
    """
    One Claude call per dish: extract ingredients with estimated quantities.
    Returns a list of dicts: {name, quantity, unit, notes}
    """
    prompt = f"""You are a professional chef. Given the dish below, list every ingredient with an estimated quantity for one serving.

Dish: {dish["name"]}
Description: {dish["description"]}

Return ONLY a valid JSON array. Each object must have exactly these keys:
- "name": ingredient name (lowercase, singular form, e.g. "jalapeño" not "jalapeños")
- "quantity": numeric quantity (float or null if unknown)
- "unit": unit of measurement (e.g. "oz", "cup", "tbsp", "whole", "g") or null
- "notes": short prep note if relevant (e.g. "pickled", "fire-roasted") or null

No explanation, no markdown."""

    response = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_json_response(response.content[0].text)


def run_menu_parser(pdf_path, progress_callback=None):
    """
    Full Step 1 pipeline:
    1. Extract text from PDF
    2. Parse into dish list (one LLM call)
    3. For each dish, extract ingredients (one LLM call per dish)
    4. Persist everything to the DB

    progress_callback(current, total, dish_name) is called before each dish
    so the UI can show live progress.

    Returns a list of result dicts. Failed dishes include an "error" key instead
    of "ingredients" — one failure never stops the rest.
    """
    models.init_db()

    menu_text = extract_text_from_pdf(pdf_path)
    dishes = parse_menu_into_dishes(menu_text)

    results = []
    total = len(dishes)

    for i, dish in enumerate(dishes):
        if progress_callback:
            progress_callback(i, total, dish["name"])

        try:
            dish_id = models.insert_dish(
                name=dish["name"],
                category=dish["category"],
                description=dish["description"],
            )

            ingredients = extract_ingredients_for_dish(dish)

            for ing in ingredients:
                ingredient_id = models.insert_ingredient(ing["name"])
                models.insert_dish_ingredient(
                    dish_id=dish_id,
                    ingredient_id=ingredient_id,
                    quantity=ing.get("quantity"),
                    unit=ing.get("unit"),
                    notes=ing.get("notes"),
                )

            results.append(
                {
                    "dish": dish["name"],
                    "category": dish["category"],
                    "ingredients": ingredients,
                }
            )

        except Exception as e:
            results.append({"dish": dish["name"], "category": dish.get("category", ""), "error": str(e)})

    return results
