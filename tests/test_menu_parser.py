import json
import os
from unittest.mock import MagicMock, patch

import pytest

from src.agents.menu_parser import (
    _parse_json_response,
    extract_ingredients_for_dish,
    parse_menu_into_dishes,
    run_menu_parser,
)

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

SAMPLE_DISH = {
    "name": "classic nachos",
    "category": "starters",
    "description": "oaxaca & jack cheese, pickled jalapeños, crema, pico de gallo, guacamole, cilantro",
}

SAMPLE_INGREDIENTS = [
    {"name": "oaxaca cheese", "quantity": 2.0, "unit": "oz", "notes": None},
    {"name": "jack cheese", "quantity": 1.0, "unit": "oz", "notes": None},
    {"name": "jalapeño", "quantity": 3.0, "unit": "whole", "notes": "pickled"},
]


def make_mock_response(payload):
    """Build a mock Anthropic response wrapping a JSON-serialised payload."""
    mock = MagicMock()
    mock.content = [MagicMock(text=json.dumps(payload))]
    return mock


# ---------------------------------------------------------------------------
# _parse_json_response
# ---------------------------------------------------------------------------

class TestParseJsonResponse:
    def test_plain_json_array(self):
        raw = json.dumps([{"a": 1}])
        assert _parse_json_response(raw) == [{"a": 1}]

    def test_strips_json_code_fence(self):
        raw = "```json\n[{\"a\": 1}]\n```"
        assert _parse_json_response(raw) == [{"a": 1}]

    def test_strips_plain_code_fence(self):
        raw = "```\n[{\"a\": 1}]\n```"
        assert _parse_json_response(raw) == [{"a": 1}]

    def test_raises_on_invalid_json(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_json_response("not valid json")


# ---------------------------------------------------------------------------
# parse_menu_into_dishes
# ---------------------------------------------------------------------------

class TestParseMenuIntoDishes:
    @patch("src.agents.menu_parser.client")
    def test_returns_a_list(self, mock_client):
        mock_client.messages.create.return_value = make_mock_response([SAMPLE_DISH])
        result = parse_menu_into_dishes("some menu text")
        assert isinstance(result, list)

    @patch("src.agents.menu_parser.client")
    def test_each_dish_has_required_keys(self, mock_client):
        mock_client.messages.create.return_value = make_mock_response([SAMPLE_DISH])
        result = parse_menu_into_dishes("some menu text")
        for dish in result:
            assert "name" in dish
            assert "category" in dish
            assert "description" in dish

    @patch("src.agents.menu_parser.client")
    def test_makes_exactly_one_llm_call(self, mock_client):
        mock_client.messages.create.return_value = make_mock_response([SAMPLE_DISH])
        parse_menu_into_dishes("some menu text")
        mock_client.messages.create.assert_called_once()


# ---------------------------------------------------------------------------
# extract_ingredients_for_dish
# ---------------------------------------------------------------------------

class TestExtractIngredientsForDish:
    @patch("src.agents.menu_parser.client")
    def test_returns_a_list(self, mock_client):
        mock_client.messages.create.return_value = make_mock_response(SAMPLE_INGREDIENTS)
        result = extract_ingredients_for_dish(SAMPLE_DISH)
        assert isinstance(result, list)

    @patch("src.agents.menu_parser.client")
    def test_each_ingredient_has_required_keys(self, mock_client):
        mock_client.messages.create.return_value = make_mock_response(SAMPLE_INGREDIENTS)
        result = extract_ingredients_for_dish(SAMPLE_DISH)
        for ing in result:
            assert "name" in ing
            assert "quantity" in ing
            assert "unit" in ing
            assert "notes" in ing

    @patch("src.agents.menu_parser.client")
    def test_makes_exactly_one_llm_call_per_dish(self, mock_client):
        mock_client.messages.create.return_value = make_mock_response(SAMPLE_INGREDIENTS)
        extract_ingredients_for_dish(SAMPLE_DISH)
        mock_client.messages.create.assert_called_once()


# ---------------------------------------------------------------------------
# run_menu_parser — integration style with mocked LLM and isolated temp DB
# ---------------------------------------------------------------------------

class TestRunMenuParser:
    @patch("src.agents.menu_parser.extract_text_from_pdf")
    @patch("src.agents.menu_parser.client")
    def test_returns_one_result_per_dish(self, mock_client, mock_extract, tmp_path):
        import src.db.models as m
        m.DB_PATH = str(tmp_path / "test.db")

        mock_extract.return_value = "raw menu text"
        mock_client.messages.create.side_effect = [
            make_mock_response([SAMPLE_DISH]),       # parse_menu_into_dishes
            make_mock_response(SAMPLE_INGREDIENTS),  # extract_ingredients_for_dish
        ]

        results = run_menu_parser("fake/path.pdf")
        assert len(results) == 1
        assert results[0]["dish"] == "classic nachos"
        assert "ingredients" in results[0]

    @patch("src.agents.menu_parser.extract_text_from_pdf")
    @patch("src.agents.menu_parser.client")
    def test_failed_dish_does_not_stop_pipeline(self, mock_client, mock_extract, tmp_path):
        import src.db.models as m
        m.DB_PATH = str(tmp_path / "test.db")

        mock_extract.return_value = "raw menu text"
        second_dish = {**SAMPLE_DISH, "name": "street corn"}

        mock_client.messages.create.side_effect = [
            make_mock_response([SAMPLE_DISH, second_dish]),  # two dishes returned
            Exception("LLM timeout"),                         # first dish fails
            make_mock_response(SAMPLE_INGREDIENTS),           # second dish succeeds
        ]

        results = run_menu_parser("fake/path.pdf")
        assert len(results) == 2
        assert any("error" in r for r in results)
        assert any("ingredients" in r for r in results)

    @patch("src.agents.menu_parser.extract_text_from_pdf")
    @patch("src.agents.menu_parser.client")
    def test_progress_callback_called_for_each_dish(self, mock_client, mock_extract, tmp_path):
        import src.db.models as m
        m.DB_PATH = str(tmp_path / "test.db")

        mock_extract.return_value = "raw menu text"
        mock_client.messages.create.side_effect = [
            make_mock_response([SAMPLE_DISH]),
            make_mock_response(SAMPLE_INGREDIENTS),
        ]

        calls = []
        run_menu_parser("fake/path.pdf", progress_callback=lambda i, t, n: calls.append(n))
        assert "classic nachos" in calls
