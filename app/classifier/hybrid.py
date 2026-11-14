"""Façade du classifieur hybride : règles déterministes puis embeddings ONNX."""

from __future__ import annotations

import time
from pathlib import Path

from app.classifier.rules import (
    DEFAULT_CATEGORY,
    apply_deterministic_rules,
    extract_prompt_text,
)
from app.classifier.semantic import (
    DEFAULT_MODEL_NAME,
    SemanticBackend,
    SemanticClassifier,
)
from app.schemas import ChatCompletionRequest, ClassificationResult


class TaskClassifier:
    """Orchestre l'Étape A (< 1 ms) puis l'Étape B (< 20 ms).

    `warmup()` doit être appelé au démarrage (lifespan FastAPI) : il charge le modèle
    ONNX et fige les ancres. Si le modèle est indisponible, la classification se rabat
    sur `DEFAULT_CATEGORY` via la méthode `fallback_default` sans jamais lever d'exception.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        cache_dir: str | Path | None = None,
        semantic: SemanticBackend | None = None,
    ) -> None:
        self._semantic: SemanticBackend = (
            semantic
            if semantic is not None
            else SemanticClassifier(model_name=model_name, cache_dir=cache_dir)
        )

    @property
    def ready(self) -> bool:
        """Indique si le backend sémantique est chargé (exposé par `GET /health`)."""
        return self._semantic.ready

    def warmup(self) -> None:
        """Prépare les ressources ONNX (idempotent, ne propage aucune exception)."""
        try:
            self._semantic.warmup()
        except Exception:  # noqa: BLE001 - le routeur doit démarrer même sans ONNX
            return None
        return None

    def classify(self, request: ChatCompletionRequest) -> ClassificationResult:
        """Classe une requête entrante selon l'ordre de priorité du plan d'architecture."""
        started = time.perf_counter()

        match = apply_deterministic_rules(request)
        if match is not None:
            return ClassificationResult(
                category=match.category,
                method=match.method,
                cleaned_messages=match.messages,
                latency_ms=(time.perf_counter() - started) * 1000.0,
                confidence=1.0,
            )

        prompt = extract_prompt_text(request.messages)
        prediction = self._semantic.classify(prompt) if prompt else None

        category = prediction.category if prediction is not None else DEFAULT_CATEGORY
        confidence = prediction.confidence if prediction is not None else 0.0
        method = "semantic" if prediction is not None else "fallback_default"

        return ClassificationResult(
            category=category,
            method=method,
            cleaned_messages=list(request.messages),
            latency_ms=(time.perf_counter() - started) * 1000.0,
            confidence=confidence,
        )
