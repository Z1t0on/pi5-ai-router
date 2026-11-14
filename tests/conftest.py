"""Fixtures partagées de la suite `pytest`."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Client de test avec `lifespan` actif et environnement réseau neutre.

    Les variables d'environnement influentes sont retirées pour que le test ne dépende
    ni d'un `.env` local ni de la machine d'exécution.
    """
    monkeypatch.delenv("BEDROCK_LOCKED", raising=False)
    monkeypatch.delenv("RULES_FILE_PATH", raising=False)
    with TestClient(app) as test_client:
        yield test_client
