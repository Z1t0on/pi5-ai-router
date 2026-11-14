"""Étape 1 — squelette FastAPI, healthcheck, catalogue de modèles et contrats Pydantic."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import VIRTUAL_MODELS, app, check_rules, rules_path
from app.schemas import ChatCompletionRequest, RoutingRulesSchema

EXPECTED_HEALTH_KEYS = {"status", "rules_loaded", "classifier_ready", "bedrock_locked"}


def test_health_endpoint_returns_200_and_expected_keys(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert EXPECTED_HEALTH_KEYS <= payload.keys()
    assert payload["status"] == "ok"
    assert payload["rules_loaded"] is True
    assert payload["classifier_ready"] is False


def test_health_locks_bedrock_by_default(client: TestClient) -> None:
    assert client.get("/health").json()["bedrock_locked"] is True


def test_health_reports_unlocked_bedrock_when_env_disables_lock(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BEDROCK_LOCKED", "false")

    assert client.get("/health").json()["bedrock_locked"] is False


def test_v1_models_lists_smart_router_and_tag_aliases(client: TestClient) -> None:
    response = client.get("/v1/models")

    assert response.status_code == 200
    payload = response.json()
    assert payload["object"] == "list"
    model_ids = {entry["id"] for entry in payload["data"]}
    assert {
        "smart-router",
        "smart-router-plan",
        "smart-router-debug",
        "smart-router-code",
        "smart-router-fast",
    } <= model_ids
    for entry in payload["data"]:
        assert entry["object"] == "model"
        assert entry["owned_by"] == "pi5-ai-router"


def test_lifespan_exposes_shared_async_http_client(client: TestClient) -> None:
    http_client = client.app.state.http_client

    assert isinstance(http_client, httpx.AsyncClient)
    assert http_client.is_closed is False


def test_lifespan_closes_shared_http_client_on_shutdown() -> None:
    with TestClient(app) as test_client:
        http_client = test_client.app.state.http_client
        assert http_client.is_closed is False

    assert http_client.is_closed is True


def test_chat_completion_request_schema_rejects_empty_messages() -> None:
    with pytest.raises(ValidationError):
        ChatCompletionRequest(messages=[])


def test_chat_completion_request_schema_keeps_unknown_openai_fields() -> None:
    request = ChatCompletionRequest(
        messages=[
            {"role": "system", "content": "You are a router."},
            {
                "role": "user",
                "content": [{"type": "image_url", "image_url": {"url": "http://pi5/image.png"}}],
            },
        ],
        stream=True,
        stream_options={"include_usage": True},
        tools=[{"type": "function", "function": {"name": "read_file"}}],
    )

    assert request.model == "smart-router"
    assert request.stream is True
    assert request.messages[1].content[0]["type"] == "image_url"
    dumped = request.model_dump()
    assert dumped["stream_options"] == {"include_usage": True}
    assert dumped["tools"][0]["function"]["name"] == "read_file"


def test_chat_completions_stub_returns_501_until_routing_engine(client: TestClient) -> None:
    response = client.post(
        "/v1/chat/completions",
        json={"model": "smart-router", "messages": [{"role": "user", "content": "Hello"}]},
    )

    assert response.status_code == 501
    assert response.json()["error"]["code"] == "routing_engine_pending"


def test_routing_rules_schema_validates_repository_config() -> None:
    rules_file = Path(rules_path())

    assert rules_file.is_file(), f"missing routing rules at {rules_file}"
    raw = json.loads(rules_file.read_text(encoding="utf-8"))
    rules = RoutingRulesSchema.model_validate(raw)

    assert rules.task_routing_matrix, "task_routing_matrix must not be empty"
    assert rules.providers, "providers must not be empty"
    for category, cascade in rules.task_routing_matrix.items():
        for slot in ("primary", "fallback_1", "fallback_2"):
            target = getattr(cascade, slot)
            if target is not None:
                assert target.provider in rules.providers, f"{category}.{slot} -> unknown provider"


def test_check_rules_reports_loaded_with_valid_config() -> None:
    status = check_rules()

    assert status["rules_loaded"] is True
    assert status["rules_updated_at"]


def test_virtual_models_alias_map_covers_opencode_catalog() -> None:
    assert set(VIRTUAL_MODELS) == {
        "smart-router",
        "smart-router-plan",
        "smart-router-debug",
        "smart-router-code",
        "smart-router-fast",
    }
