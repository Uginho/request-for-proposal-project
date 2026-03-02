from unittest.mock import patch

import pytest

from src.agents.rfp_emailer import (
    _filter_ingredients,
    _get_categories_for_specialty,
    compose_rfp_email,
    generate_rfp_drafts,
    send_selected,
)

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

SAMPLE_DISTRIBUTOR = {
    "id": 1,
    "name": "Sysco Seattle",
    "specialty": "Broadline",
    "email": "test@example.com",
    "address": "22820 54th Ave S",
    "city": "Kent",
    "state": "WA",
    "phone": "206-622-2261",
    "website": "https://www.sysco.com",
    "notes": None,
}

SAMPLE_INGREDIENTS = [
    {"id": 1, "name": "jalapeño",  "category": "vegetables"},
    {"id": 2, "name": "chicken",   "category": "chicken"},
    {"id": 3, "name": "shrimp",    "category": "seafood"},
    {"id": 4, "name": "oaxaca cheese", "category": "none"},
]


# ---------------------------------------------------------------------------
# _get_categories_for_specialty
# ---------------------------------------------------------------------------

class TestGetCategoriesForSpecialty:
    def test_broadline_returns_none(self):
        assert _get_categories_for_specialty("Broadline") is None

    def test_produce_returns_veg_and_fruit(self):
        cats = _get_categories_for_specialty("Produce")
        assert "vegetables" in cats
        assert "fruit" in cats

    def test_seafood_returns_seafood(self):
        assert _get_categories_for_specialty("Seafood") == ["seafood"]

    def test_meat_returns_proteins(self):
        cats = _get_categories_for_specialty("Meat & Proteins")
        assert "beef" in cats
        assert "chicken" in cats

    def test_italian_specialty_returns_none_category(self):
        cats = _get_categories_for_specialty("Italian & Specialty")
        assert cats == ["none"]

    def test_unknown_specialty_defaults_to_all(self):
        assert _get_categories_for_specialty("Mystery Supplier") is None

    def test_none_specialty_returns_all(self):
        assert _get_categories_for_specialty(None) is None


# ---------------------------------------------------------------------------
# _filter_ingredients
# ---------------------------------------------------------------------------

class TestFilterIngredients:
    def test_none_categories_returns_all(self):
        result = _filter_ingredients(SAMPLE_INGREDIENTS, None)
        assert len(result) == len(SAMPLE_INGREDIENTS)

    def test_seafood_filter(self):
        result = _filter_ingredients(SAMPLE_INGREDIENTS, ["seafood"])
        assert len(result) == 1
        assert result[0]["name"] == "shrimp"

    def test_produce_filter(self):
        result = _filter_ingredients(SAMPLE_INGREDIENTS, ["vegetables", "fruit"])
        assert len(result) == 1
        assert result[0]["name"] == "jalapeño"

    def test_none_category_filter(self):
        result = _filter_ingredients(SAMPLE_INGREDIENTS, ["none"])
        assert len(result) == 1
        assert result[0]["name"] == "oaxaca cheese"

    def test_no_match_returns_empty(self):
        result = _filter_ingredients(SAMPLE_INGREDIENTS, ["fruit"])
        assert result == []


# ---------------------------------------------------------------------------
# compose_rfp_email
# ---------------------------------------------------------------------------

class TestComposeRfpEmail:
    def test_returns_subject_and_body(self):
        subject, body = compose_rfp_email(SAMPLE_DISTRIBUTOR, SAMPLE_INGREDIENTS)
        assert subject
        assert body

    def test_subject_contains_pablo(self):
        subject, _ = compose_rfp_email(SAMPLE_DISTRIBUTOR, SAMPLE_INGREDIENTS)
        assert "Pablo" in subject

    def test_body_contains_distributor_name(self):
        _, body = compose_rfp_email(SAMPLE_DISTRIBUTOR, SAMPLE_INGREDIENTS)
        assert "Sysco Seattle" in body

    def test_body_contains_all_ingredients(self):
        _, body = compose_rfp_email(SAMPLE_DISTRIBUTOR, SAMPLE_INGREDIENTS)
        assert "jalapeño" in body.lower()
        assert "chicken" in body.lower()

    def test_empty_ingredient_list_does_not_crash(self):
        subject, body = compose_rfp_email(SAMPLE_DISTRIBUTOR, [])
        assert body


# ---------------------------------------------------------------------------
# generate_rfp_drafts
# ---------------------------------------------------------------------------

class TestGenerateRfpDrafts:
    def test_returns_one_draft_per_matched_distributor(self, tmp_path):
        import src.db.models as m
        m.DB_PATH = str(tmp_path / "test.db")
        m.init_db()
        m.insert_distributor(
            name="Sysco Seattle", specialty="Broadline",
            address="123 Main", city="Kent", state="WA",
            phone="206-000-0000", email="test@example.com",
            website="https://sysco.com", notes=None,
        )
        m.insert_ingredient("jalapeño")

        drafts = generate_rfp_drafts()
        assert len(drafts) == 1
        assert drafts[0]["distributor_name"] == "Sysco Seattle"

    def test_specialty_routing_filters_correctly(self, tmp_path):
        import src.db.models as m
        m.DB_PATH = str(tmp_path / "test.db")
        m.init_db()
        # Seafood distributor
        m.insert_distributor(
            name="Ocean Beauty", specialty="Seafood",
            address="123 Main", city="Seattle", state="WA",
            phone="206-000-0000", email="test@example.com",
            website="https://ob.com", notes=None,
        )
        ing_id = m.insert_ingredient("shrimp")
        veg_id = m.insert_ingredient("jalapeño")
        # Give shrimp a seafood report_title, jalapeño a vegetables one
        m.insert_ingredient_pricing(
            ingredient_id=ing_id, commodity="shrimp",
            price_per_lb=None, original_price=None, original_unit=None,
            market=None, report_title="USDA AMS Report 3646 — Seafood",
            report_date=None, no_data_reason=None,
        )
        m.insert_ingredient_pricing(
            ingredient_id=veg_id, commodity="jalapeno pepper",
            price_per_lb=1.5, original_price=15.0, original_unit="10 lb carton",
            market="Los Angeles", report_title="USDA AMS Report 2307 — Vegetables",
            report_date=None, no_data_reason=None,
        )

        drafts = generate_rfp_drafts()
        assert len(drafts) == 1
        names = [i["name"] for i in drafts[0]["matched_ingredients"]]
        assert "shrimp" in names
        assert "jalapeño" not in names

    def test_distributor_with_no_matching_ingredients_is_skipped(self, tmp_path):
        import src.db.models as m
        m.DB_PATH = str(tmp_path / "test.db")
        m.init_db()
        m.insert_distributor(
            name="Ocean Beauty", specialty="Seafood",
            address="123 Main", city="Seattle", state="WA",
            phone="206-000-0000", email="test@example.com",
            website="https://ob.com", notes=None,
        )
        # Only a vegetable ingredient — no seafood match
        veg_id = m.insert_ingredient("jalapeño")
        m.insert_ingredient_pricing(
            ingredient_id=veg_id, commodity="jalapeno pepper",
            price_per_lb=1.5, original_price=15.0, original_unit="10 lb carton",
            market="Los Angeles", report_title="USDA AMS Report 2307 — Vegetables",
            report_date=None, no_data_reason=None,
        )

        drafts = generate_rfp_drafts()
        assert drafts == []

    def test_drafts_saved_to_db_as_draft_status(self, tmp_path):
        import src.db.models as m
        m.DB_PATH = str(tmp_path / "test.db")
        m.init_db()
        m.insert_distributor(
            name="Sysco Seattle", specialty="Broadline",
            address="123 Main", city="Kent", state="WA",
            phone="206-000-0000", email="test@example.com",
            website="https://sysco.com", notes=None,
        )
        m.insert_ingredient("jalapeño")
        generate_rfp_drafts()

        emails = m.get_all_rfp_emails()
        assert len(emails) == 1
        assert emails[0]["status"] == "draft"


# ---------------------------------------------------------------------------
# send_selected
# ---------------------------------------------------------------------------

class TestSendSelected:
    @patch("src.agents.rfp_emailer.send_email")
    def test_sends_only_selected(self, mock_send, tmp_path):
        import src.db.models as m
        m.DB_PATH = str(tmp_path / "test.db")
        m.init_db()
        m.insert_distributor(
            name="Sysco Seattle", specialty="Broadline",
            address="123 Main", city="Kent", state="WA",
            phone="206-000-0000", email="test@example.com",
            website="https://sysco.com", notes=None,
        )
        m.insert_ingredient("jalapeño")
        drafts = generate_rfp_drafts()

        results = send_selected(drafts)
        assert mock_send.call_count == 1
        assert results[0]["status"] == "sent"

    @patch("src.agents.rfp_emailer.send_email")
    def test_failed_send_updates_db(self, mock_send, tmp_path):
        import src.db.models as m
        m.DB_PATH = str(tmp_path / "test.db")
        m.init_db()
        m.insert_distributor(
            name="Sysco Seattle", specialty="Broadline",
            address="123 Main", city="Kent", state="WA",
            phone="206-000-0000", email="test@example.com",
            website="https://sysco.com", notes=None,
        )
        m.insert_ingredient("jalapeño")
        drafts = generate_rfp_drafts()

        mock_send.side_effect = Exception("SMTP error")
        results = send_selected(drafts)

        assert "failed" in results[0]["status"]
        emails = m.get_all_rfp_emails()
        assert "failed" in emails[0]["status"]

    @patch("src.agents.rfp_emailer.send_email")
    def test_one_failure_does_not_stop_pipeline(self, mock_send, tmp_path):
        import src.db.models as m
        m.DB_PATH = str(tmp_path / "test.db")
        m.init_db()
        for name, email in [("Dist A", "a@test.com"), ("Dist B", "b@test.com")]:
            m.insert_distributor(
                name=name, specialty="Broadline",
                address="123 Main", city="Seattle", state="WA",
                phone="206-000-0000", email=email,
                website="https://example.com", notes=None,
            )
        m.insert_ingredient("jalapeño")
        drafts = generate_rfp_drafts()

        mock_send.side_effect = [Exception("fail"), None]
        results = send_selected(drafts)

        assert len(results) == 2
        assert results[1]["status"] == "sent"

    @patch("src.agents.rfp_emailer.send_email")
    def test_empty_selection_sends_nothing(self, mock_send, tmp_path):
        import src.db.models as m
        m.DB_PATH = str(tmp_path / "test.db")
        m.init_db()

        results = send_selected([])
        assert results == []
        mock_send.assert_not_called()
