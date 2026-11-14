"""Point d'entrée FastAPI du routeur `pi5-ai-router`.

Étape 1 du plan d'architecture maître : squelette applicatif, cycle de vie `lifespan`
(avec un `httpx.AsyncClient` partagé), healthcheck et catalogue de modèles virtuels.
Le classifieur, le moteur de cascade, le streaming SSE et le dashboard sont branchés
aux étapes suivantes.
"""

from __future__ import annotations

import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.schemas import ChatCompletionRequest, RoutingRulesSchema

logger = logging.getLogger("pi5_ai_router.health")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RULES_PATH = PROJECT_ROOT / "config" / "routing_rules.json"

# Modèles virtuels exposés à OpenCode et Zed (aucun nom de modèle fournisseur n'est codé ici).
VIRTUAL_MODELS: dict[str, str] = {
    "smart-router": "Smart Router (Auto-Classification)",
    "smart-router-plan": "Smart Router (#plan - Architecture)",
    "smart-router-debug": "Smart Router (#debug - Deep Reasoning)",
    "smart-router-code": "Smart Router (#code - Refactoring)",
    "smart-router-fast": "Smart Router (#fast - Autocomplete)",
}

# Politique de timeouts vers les fournisseurs : lecture longue pour les réponses en streaming.
UPSTREAM_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)
UPSTREAM_LIMITS = httpx.Limits(max_connections=100, max_keepalive_connections=20)


def rules_path() -> Path:
    """Chemin de `config/routing_rules.json` (surchargeable via `RULES_FILE_PATH`)."""
    configured = os.getenv("RULES_FILE_PATH")
    return Path(configured) if configured else DEFAULT_RULES_PATH


def bedrock_locked() -> bool:
    """Verrou financier AWS Bedrock : verrouillé par défaut si `BEDROCK_LOCKED` est absent."""
    raw = os.getenv("BEDROCK_LOCKED", "true").strip().lower()
    return raw not in {"false", "0", "no", "off"}


def check_rules(config_path: Path | None = None) -> dict[str, Any]:
    """Charge et valide les règles de routage sans lever d'exception.

    Retourne `{"rules_loaded": bool, "rules_updated_at": str | None}`. Une configuration
    invalide est journalisée mais ne doit jamais empêcher le démarrage du routeur.
    """
    path = config_path or rules_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        RoutingRulesSchema.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        logger.warning("routing rules unavailable at %s: %s", path, exc)
        return {"rules_loaded": False, "rules_updated_at": None}
    return {"rules_loaded": True, "rules_updated_at": payload.get("updated_at")}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Ouvre le client HTTP partagé et l'état applicatif, puis les libère à l'arrêt."""
    app.state.http_client = httpx.AsyncClient(
        timeout=UPSTREAM_TIMEOUT,
        limits=UPSTREAM_LIMITS,
        follow_redirects=True,
    )
    app.state.started_at = time.time()
    app.state.classifier_ready = False  # Étape 2 (FastEmbed/ONNX).
    app.state.rules_loaded = False
    app.state.rules_updated_at = None

    status = check_rules()
    app.state.rules_loaded = status["rules_loaded"]
    app.state.rules_updated_at = status["rules_updated_at"]
    logger.info(
        "router started (rules_loaded=%s, bedrock_locked=%s)",
        status["rules_loaded"],
        bedrock_locked(),
    )

    try:
        yield
    finally:
        await app.state.http_client.aclose()
        logger.info("router stopped")


app = FastAPI(
    title="pi5-ai-router",
    version="0.1.0",
    description="Routeur IA auto-hébergé compatible OpenAI (Raspberry Pi 5 / Windows 11).",
    lifespan=lifespan,
)


@app.get("/health", tags=["system"])
async def health(request: Request) -> dict[str, Any]:
    """Healthcheck consommé par Docker et par le dashboard."""
    return {
        "status": "ok" if request.app.state.rules_loaded else "degraded",
        "rules_loaded": request.app.state.rules_loaded,
        "classifier_ready": request.app.state.classifier_ready,
        "bedrock_locked": bedrock_locked(),
    }


@app.get("/v1/models", tags=["openai"])
async def list_models() -> dict[str, Any]:
    """Catalogue OpenAI-compatible des modèles virtuels du routeur."""
    created = int(time.time())
    return {
        "object": "list",
        "data": [
            {
                "id": model_id,
                "object": "model",
                "created": created,
                "owned_by": "pi5-ai-router",
                "description": description,
            }
            for model_id, description in VIRTUAL_MODELS.items()
        ],
    }


@app.post("/v1/chat/completions", tags=["openai"])
async def chat_completions(payload: ChatCompletionRequest) -> JSONResponse:
    """Stub de l'Étape 1 : le moteur de routage est branché aux Étapes 3 et 4."""
    logger.info("chat completion received for model=%s (routing engine pending)", payload.model)
    return JSONResponse(
        status_code=501,
        content={
            "error": {
                "message": "Routing engine not implemented yet (architecture plan steps 3-4).",
                "type": "not_implemented",
                "param": None,
                "code": "routing_engine_pending",
            }
        },
    )
