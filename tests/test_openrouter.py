import pytest
import json
from unittest.mock import MagicMock
from pydantic import BaseModel, Field
from app.openrouter_service import OpenRouterEngine, FREE_TIER_WATERFALL
from app.schemas import BatchRepoStatusResponse, RepoStatusExtraction, CanonicalStage


class DummySchema(BaseModel):
    message: str
    code: int


def test_waterfall_ordering():
    """Verify engine initializes with the strict free-tier waterfall in order."""
    engine = OpenRouterEngine(api_key="test-key")
    expected_order = [
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        "nvidia/nemotron-3.5-super-vl:free",
        "thinkingmachines/inkling:free",
        "nvidia/nemotron-3-super-120b-a12b:free",
        "openrouter/free",
    ]
    assert engine.models == expected_order


def test_clean_markdown_fence_extraction(monkeypatch):
    """Verify JSON surrounded by markdown code fences is cleaned and parsed."""
    engine = OpenRouterEngine(api_key="test-key")

    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "```json\n{\n  \"message\": \"success\",\n  \"code\": 200\n}\n```"
    mock_choice.message.reasoning = None
    mock_response.choices = [mock_choice]
    mock_response.usage.prompt_tokens = 50
    mock_response.usage.completion_tokens = 20

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    monkeypatch.setattr(OpenRouterEngine, "client", property(lambda self: mock_client))

    result = engine.generate_structured(
        prompt="Test prompt",
        response_schema=DummySchema,
        operation_type="test_op"
    )

    assert result.message == "success"
    assert result.code == 200


def test_reasoning_token_fallback(monkeypatch):
    """Verify that when message.content is None/blank, JSON in reasoning is parsed."""
    engine = OpenRouterEngine(api_key="test-key")

    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = ""
    mock_choice.message.reasoning = (
        "Let me think about how to formulate this response.\n"
        "Here is the final JSON output:\n"
        "{\n  \"message\": \"extracted_from_thoughts\",\n  \"code\": 100\n}\n"
        "Hope this helps."
    )
    mock_response.choices = [mock_choice]
    mock_response.usage.prompt_tokens = 100
    mock_response.usage.completion_tokens = 50

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    monkeypatch.setattr(OpenRouterEngine, "client", property(lambda self: mock_client))

    result = engine.generate_structured(
        prompt="Test prompt",
        response_schema=DummySchema,
        operation_type="test_op"
    )

    assert result.message == "extracted_from_thoughts"
    assert result.code == 100


def test_waterfall_failover_on_error(monkeypatch):
    """Verify that a 403/404 exception in Tier 1 triggers failover to Tier 2."""
    engine = OpenRouterEngine(api_key="test-key")

    # Tier 1 raises error, Tier 2 succeeds
    mock_response_t2 = MagicMock()
    mock_choice_t2 = MagicMock()
    mock_choice_t2.message.content = '{"message": "tier_2_success", "code": 200}'
    mock_choice_t2.message.reasoning = None
    mock_response_t2.choices = [mock_choice_t2]
    mock_response_t2.usage.prompt_tokens = 40
    mock_response_t2.usage.completion_tokens = 15

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        Exception("403 Forbidden: Endpoint gated"),
        mock_response_t2,
    ]
    monkeypatch.setattr(OpenRouterEngine, "client", property(lambda self: mock_client))

    result = engine.generate_structured(
        prompt="Test prompt",
        response_schema=DummySchema,
        operation_type="test_failover"
    )

    assert result.message == "tier_2_success"
    assert mock_client.chat.completions.create.call_count == 2
