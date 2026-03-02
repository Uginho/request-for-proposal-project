import json
from unittest.mock import MagicMock, patch

import pytest

from src.agents.usda_pricing import (
    find_price_in_report,
    map_ingredients_to_usda,
    normalize_to_per_lb,
    run_usda_pricing,
)

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

SAMPLE_MAPPINGS = {
    "jalapeño": {"category": "vegetables", "commodity": "jalapeno pepper", "reason": ""},
    "oaxaca cheese": {"category": "none", "commodity": None, "reason": "Specialty Mexican cheese, no USDA equivalent"},
    "chicken": {"category": "chicken", "commodity": "chicken", "reason": ""},
}

SAMPLE_REPORT_ROWS = [
    {
        "commodity": "PEPPERS, JALAPENO",
        "low_price": 18.0,
        "high_price": 22.0,
        "package": "10 lb carton",
        "market_location_city": "Los Angeles",
    },
    {
        "commodity": "TOMATOES, ROMA",
        "low_price": 10.0,
        "high_price": 14.0,
        "package": "25 lb carton",
        "market_location_city": "Los Angeles",
    },
]

SAMPLE_INGREDIENTS = [
    {"id": 1, "name": "jalapeño"},
    {"id": 2, "name": "oaxaca cheese"},
]


def make_mock_claude_response(payload):
    mock = MagicMock()
    mock.content = [MagicMock(text=json.dumps(payload))]
    return mock


# ---------------------------------------------------------------------------
# normalize_to_per_lb  (pure function — no mocking needed)
# ---------------------------------------------------------------------------

class TestNormalizeToPerLb:
    def test_per_lb_unit(self):
        assert normalize_to_per_lb(2.5, "per lb") == 2.5

    def test_slash_lb_unit(self):
        assert normalize_to_per_lb(2.5, "/lb") == 2.5

    def test_25lb_carton(self):
        assert normalize_to_per_lb(20.0, "25 lb carton") == 0.8

    def test_50lb_bag(self):
        assert normalize_to_per_lb(30.0, "50 lb bag") == 0.6

    def test_10lb_carton(self):
        assert normalize_to_per_lb(15.0, "10 lb carton") == 1.5

    def test_45lb_carton(self):
        # previously missed by hardcoded approach
        assert normalize_to_per_lb(36.5, "45 lb cartons") == round(36.5 / 45, 4)

    def test_100lb_sack(self):
        assert normalize_to_per_lb(50.0, "100 lb sack") == 0.5

    def test_unrecognized_unit_returns_none(self):
        assert normalize_to_per_lb(5.0, "per bunch") is None

    def test_cartons_2_layer_returns_none(self):
        assert normalize_to_per_lb(26.0, "cartons 2 layer") is None

    def test_none_price_returns_none(self):
        assert normalize_to_per_lb(None, "per lb") is None

    def test_none_unit_returns_none(self):
        assert normalize_to_per_lb(5.0, None) is None


# ---------------------------------------------------------------------------
# find_price_in_report  (pure function — no mocking needed)
# ---------------------------------------------------------------------------

class TestFindPriceInReport:
    def test_finds_matching_commodity(self):
        price, unit, market = find_price_in_report(SAMPLE_REPORT_ROWS, "jalapeno pepper")
        assert price == 20.0  # average of 18 and 22
        assert unit == "10 lb carton"
        assert market == "Los Angeles"

    def test_returns_none_for_no_match(self):
        price, unit, market = find_price_in_report(SAMPLE_REPORT_ROWS, "avocado")
        assert price is None
        assert unit is None
        assert market is None

    def test_returns_none_for_empty_rows(self):
        price, unit, market = find_price_in_report([], "tomato")
        assert price is None

    def test_returns_none_for_none_rows(self):
        price, unit, market = find_price_in_report(None, "tomato")
        assert price is None


# ---------------------------------------------------------------------------
# map_ingredients_to_usda
# ---------------------------------------------------------------------------

class TestMapIngredientsToUsda:
    @patch("src.agents.usda_pricing.ANTHROPIC_CLIENT")
    def test_returns_mapping_for_each_ingredient(self, mock_client):
        mock_client.messages.create.return_value = make_mock_claude_response(SAMPLE_MAPPINGS)
        result = map_ingredients_to_usda(["jalapeño", "oaxaca cheese", "chicken"])
        assert "jalapeño" in result
        assert "oaxaca cheese" in result

    @patch("src.agents.usda_pricing.ANTHROPIC_CLIENT")
    def test_each_mapping_has_required_keys(self, mock_client):
        mock_client.messages.create.return_value = make_mock_claude_response(SAMPLE_MAPPINGS)
        result = map_ingredients_to_usda(["jalapeño"])
        for val in result.values():
            assert "category" in val
            assert "commodity" in val

    @patch("src.agents.usda_pricing.ANTHROPIC_CLIENT")
    def test_makes_exactly_one_llm_call(self, mock_client):
        mock_client.messages.create.return_value = make_mock_claude_response(SAMPLE_MAPPINGS)
        map_ingredients_to_usda(["jalapeño", "oaxaca cheese"])
        mock_client.messages.create.assert_called_once()


# ---------------------------------------------------------------------------
# run_usda_pricing — integration style with mocked LLM + USDA + temp DB
# ---------------------------------------------------------------------------

class TestRunUsdaPricing:
    @patch("src.agents.usda_pricing.fetch_report_with_retry")
    @patch("src.agents.usda_pricing.ANTHROPIC_CLIENT")
    def test_returns_result_per_ingredient(self, mock_client, mock_fetch, tmp_path):
        import src.db.models as m
        m.DB_PATH = str(tmp_path / "test.db")
        m.init_db()
        m.insert_ingredient("jalapeño")
        m.insert_ingredient("oaxaca cheese")

        mock_client.messages.create.return_value = make_mock_claude_response(SAMPLE_MAPPINGS)
        mock_fetch.return_value = SAMPLE_REPORT_ROWS

        results = run_usda_pricing()
        assert len(results) == 2

    @patch("src.agents.usda_pricing.fetch_report_with_retry")
    @patch("src.agents.usda_pricing.ANTHROPIC_CLIENT")
    def test_no_data_items_still_persisted(self, mock_client, mock_fetch, tmp_path):
        import src.db.models as m
        m.DB_PATH = str(tmp_path / "test.db")
        m.init_db()
        m.insert_ingredient("oaxaca cheese")

        mock_client.messages.create.return_value = make_mock_claude_response(
            {"oaxaca cheese": {"category": "none", "commodity": None, "reason": "Specialty cheese"}}
        )
        mock_fetch.return_value = []

        results = run_usda_pricing()
        assert results[0]["status"] == "no_data"
        pricing = m.get_all_ingredient_pricing()
        assert len(pricing) == 1
        assert pricing[0]["price_per_lb"] is None

    @patch("src.agents.usda_pricing.fetch_report_with_retry")
    @patch("src.agents.usda_pricing.ANTHROPIC_CLIENT")
    def test_failed_ingredient_does_not_stop_pipeline(self, mock_client, mock_fetch, tmp_path):
        import src.db.models as m
        m.DB_PATH = str(tmp_path / "test.db")
        m.init_db()
        m.insert_ingredient("jalapeño")
        m.insert_ingredient("chicken")

        mappings = {
            "jalapeño": {"category": "vegetables", "commodity": "jalapeno pepper", "reason": ""},
            "chicken": {"category": "chicken", "commodity": "chicken", "reason": ""},
        }
        mock_client.messages.create.return_value = make_mock_claude_response(mappings)
        # Simulate report fetch failure for one category
        mock_fetch.side_effect = [None, SAMPLE_REPORT_ROWS]

        results = run_usda_pricing()
        assert len(results) == 2

    @patch("src.agents.usda_pricing.fetch_report_with_retry")
    @patch("src.agents.usda_pricing.ANTHROPIC_CLIENT")
    def test_progress_callback_fires(self, mock_client, mock_fetch, tmp_path):
        import src.db.models as m
        m.DB_PATH = str(tmp_path / "test.db")
        m.init_db()
        m.insert_ingredient("jalapeño")

        mock_client.messages.create.return_value = make_mock_claude_response(
            {"jalapeño": {"category": "vegetables", "commodity": "jalapeno pepper", "reason": ""}}
        )
        mock_fetch.return_value = SAMPLE_REPORT_ROWS

        calls = []
        run_usda_pricing(progress_callback=lambda i, t, n: calls.append(n))
        assert len(calls) > 0
