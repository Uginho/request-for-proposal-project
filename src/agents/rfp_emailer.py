import os
import smtplib
from datetime import date, datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv

from src.db import models

load_dotenv()

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

QUOTE_DEADLINE_DAYS = 7

# Maps keywords found in distributor specialty to allowed USDA ingredient categories.
# None means the distributor gets all ingredients (broadline).
SPECIALTY_CATEGORY_MAP = {
    "broadline":     None,
    "cash & carry":  None,
    "produce":       ["vegetables", "fruit"],
    "dairy":         ["vegetables", "fruit"],
    "seafood":       ["seafood"],
    "meat":          ["beef", "pork", "chicken"],
    "proteins":      ["beef", "pork", "chicken"],
    "dry goods":     ["beef", "pork", "chicken"],
    "italian":       ["none"],   # specialty importers get non-USDA items
    "mediterranean": ["none"],
    "specialty":     ["none"],
}


def _get_categories_for_specialty(specialty):
    """
    Returns allowed USDA categories for a distributor specialty string.
    None means all categories (broadline). Matches on keyword substrings.
    """
    if not specialty:
        return None
    specialty_lower = specialty.lower()
    for keyword, categories in SPECIALTY_CATEGORY_MAP.items():
        if keyword in specialty_lower:
            return categories
    return None  # default: broadline behavior


def _filter_ingredients(ingredients, allowed_categories):
    """Filter ingredients to only those matching allowed USDA categories."""
    if allowed_categories is None:
        return ingredients
    return [i for i in ingredients if i["category"] in allowed_categories]


def compose_rfp_email(distributor, ingredients):
    """
    Build a professional RFP email for a single distributor.
    Returns (subject, plain_text_body).
    """
    deadline = (date.today() + timedelta(days=QUOTE_DEADLINE_DAYS)).strftime("%B %d, %Y")
    ingredient_count = len(ingredients)
    ingredient_lines = "\n".join(f"  - {ing['name'].title()}" for ing in ingredients)

    subject = "RFP — Ingredient Quote Request from Pablo y Pablo"

    body = f"""Hi {distributor['name']} Team,

We are reaching out on behalf of Pablo y Pablo, a Latin restaurant located in Wallingford, Seattle, WA. We are conducting a Request for Proposal process and would like to request pricing on the {ingredient_count} ingredients listed below:

{ingredient_lines}

Please reply with your best pricing and availability by {deadline}. Quantities will be confirmed upon distributor selection.

We look forward to hearing from you.

Best regards,
Pablo y Pablo Operations Team
1605 N 34th St, Wallingford, Seattle, WA 98103
okols211@alumni.wfu.edu
"""
    return subject, body


def generate_rfp_drafts():
    """
    Phase 1 — Generate:
    1. Load all distributors and ingredients with USDA categories
    2. Filter ingredients per distributor by specialty
    3. Compose email for each distributor with matched ingredients
    4. Persist as 'draft' status in rfp_emails table
    5. Return list of draft dicts for UI rendering

    Distributors with zero matching ingredients are skipped.
    Clears previous drafts/sent emails on each run.
    """
    models.clear_rfp_emails()
    distributors = models.get_all_distributors()
    ingredients = models.get_ingredients_with_categories()

    drafts = []
    for distributor in distributors:
        allowed_categories = _get_categories_for_specialty(distributor.get("specialty"))
        matched = _filter_ingredients(ingredients, allowed_categories)

        if not matched:
            continue

        subject, body = compose_rfp_email(distributor, matched)
        email_id = models.insert_rfp_email(
            distributor_id=distributor["id"],
            to_email=distributor["email"],
            subject=subject,
            body=body,
            status="draft",
            sent_at=None,
        )

        drafts.append({
            "rfp_email_id": email_id,
            "distributor_id": distributor["id"],
            "distributor_name": distributor["name"],
            "specialty": distributor.get("specialty", ""),
            "to_email": distributor["email"],
            "subject": subject,
            "body": body,
            "matched_ingredients": matched,
        })

    return drafts


def send_selected(selected_drafts):
    """
    Phase 2 — Send:
    Sends emails only for the distributor drafts passed in.
    Updates status in DB to 'sent' or 'failed: <reason>'.
    One failure never stops the rest.
    Returns list of result dicts per distributor.
    """
    results = []
    for draft in selected_drafts:
        try:
            send_email(draft["to_email"], draft["subject"], draft["body"])
            status = "sent"
            sent_at = datetime.now(timezone.utc).isoformat()
        except Exception as e:
            status = f"failed: {e}"
            sent_at = None

        models.update_rfp_email_status(draft["rfp_email_id"], status, sent_at)
        results.append({
            "distributor": draft["distributor_name"],
            "distributor_id": draft["distributor_id"],
            "status": status,
        })

    return results


def send_email(to_email, subject, body):
    """Send a plain-text email via Gmail SMTP. Raises on failure."""
    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, to_email, msg.as_string())
