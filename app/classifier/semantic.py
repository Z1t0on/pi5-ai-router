"""Étape B du classifieur : embeddings FastEmbed/ONNX (cible < 20 ms).

Le modèle `BAAI/bge-small-en-v1.5` (~80 Mo, ONNX Runtime quantifié) est pré-téléchargé
dans l'image Docker ; aucun `torch` ni `sentence-transformers` n'est utilisé.

Les ancres de chaque catégorie sont encodées une seule fois au `warmup()`, puis réduites
en un centroïde normalisé. La classification d'un prompt se résume donc à un embedding
(384 dimensions) suivi d'un produit scalaire avec 5 centroïdes.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np

DEFAULT_MODEL_NAME = "BAAI/bge-small-en-v1.5"
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Catégories discriminées sémantiquement (les deux autres sont purement déterministes).
SEMANTIC_CATEGORIES: tuple[str, ...] = (
    "planning_architecture",
    "general_coding_refactoring",
    "realtime_autocomplete",
    "reasoning_deep_debug",
    "high_throughput_batch",
)

# Ancres rédigées en anglais : `bge-small-en-v1.5` est un modèle anglophone.
CATEGORY_ANCHORS: dict[str, tuple[str, ...]] = {
    "planning_architecture": (
        "Design the architecture of a new service and choose the module boundaries.",
        "Write an implementation plan with milestones, risks and technical trade-offs.",
        "Compare design alternatives and recommend a scalable system architecture.",
    ),
    "general_coding_refactoring": (
        "Write a Python function that implements this business logic.",
        "Refactor this module to remove duplication and improve readability.",
        "Fix the bug in the following code and add unit tests.",
    ),
    "realtime_autocomplete": (
        "Complete the next line of this function while I am typing.",
        "Give a one line inline code completion suggestion right now.",
        "Quick autocomplete for the current editor cursor with minimal latency.",
    ),
    "reasoning_deep_debug": (
        "Debug this stack trace and explain the root cause step by step.",
        "Analyse this failing test and reason about the underlying race condition.",
        "Investigate a complex bug with careful chain of thought reasoning.",
    ),
    "high_throughput_batch": (
        "Process a large batch of documents and summarise each one.",
        "Run this classification task over thousands of records in bulk.",
        "High volume bulk text transformation for a whole dataset.",
    ),
}

# Cache process-global : un seul modèle ONNX et une seule matrice d'ancres par configuration.
_MODEL_CACHE: dict[tuple[str, str], Any] = {}
_ANCHOR_CACHE: dict[tuple[str, str], np.ndarray] = {}
_CACHE_LOCK = threading.Lock()


@dataclass(frozen=True, slots=True)
class SemanticPrediction:
    """Catégorie prédite et similarité cosinus associée (0..1)."""

    category: str
    confidence: float


class SemanticBackend(Protocol):
    """Interface minimale consommée par `TaskClassifier` (permet un stub en test)."""

    @property
    def ready(self) -> bool: ...

    def warmup(self) -> None: ...

    def classify(self, text: str) -> SemanticPrediction | None: ...


def resolve_cache_dir(cache_dir: str | Path | None = None) -> str:
    """Répertoire de cache FastEmbed (`FASTEMBED_CACHE_PATH` prioritaire)."""
    if cache_dir is not None:
        return str(cache_dir)
    return os.getenv("FASTEMBED_CACHE_PATH") or str(PROJECT_ROOT / ".cache" / "fastembed")


def _normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=-1, keepdims=True)
    return matrix / np.clip(norms, 1e-12, None)


def _load_model(model_name: str, cache_dir: str) -> Any:
    """Charge (ou réutilise) le `TextEmbedding` FastEmbed partagé."""
    key = (model_name, cache_dir)
    with _CACHE_LOCK:
        cached = _MODEL_CACHE.get(key)
        if cached is not None:
            return cached
        from fastembed import TextEmbedding  # import paresseux : démarrage possible sans ONNX

        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        model = TextEmbedding(model_name=model_name, cache_dir=cache_dir)
        _MODEL_CACHE[key] = model
        return model


def _anchor_centroids(model: Any, model_name: str, cache_dir: str) -> np.ndarray:
    """Encode les ancres une seule fois et retourne les centroïdes normalisés."""
    key = (model_name, cache_dir)
    with _CACHE_LOCK:
        cached = _ANCHOR_CACHE.get(key)
        if cached is not None:
            return cached

        texts = [anchor for category in SEMANTIC_CATEGORIES for anchor in CATEGORY_ANCHORS[category]]
        embeddings = _normalize(np.asarray(list(model.embed(texts)), dtype=np.float32))

        centroids: list[np.ndarray] = []
        offset = 0
        for category in SEMANTIC_CATEGORIES:
            size = len(CATEGORY_ANCHORS[category])
            centroids.append(embeddings[offset:offset + size].mean(axis=0))
            offset += size

        matrix = np.ascontiguousarray(_normalize(np.vstack(centroids)))
        _ANCHOR_CACHE[key] = matrix
        return matrix


class SemanticClassifier:
    """Classifieur sémantique FastEmbed, paresseux et tolérant aux pannes."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        cache_dir: str | Path | None = None,
    ) -> None:
        self.model_name = model_name
        self.cache_dir = resolve_cache_dir(cache_dir)
        self._model: Any | None = None
        self._centroids: np.ndarray | None = None
        self._categories: tuple[str, ...] = SEMANTIC_CATEGORIES
        self._error: str | None = None

    @property
    def ready(self) -> bool:
        return self._centroids is not None and self._model is not None

    @property
    def error(self) -> str | None:
        return self._error

    def warmup(self) -> None:
        """Charge le modèle ONNX et pré-calcule les ancres (idempotent, sans exception)."""
        if self.ready:
            return
        try:
            model = _load_model(self.model_name, self.cache_dir)
            self._centroids = _anchor_centroids(model, self.model_name, self.cache_dir)
            self._model = model
            self._error = None
        except Exception as exc:  # noqa: BLE001 - dégradation contrôlée, jamais de crash au démarrage
            self._model = None
            self._centroids = None
            self._error = f"{type(exc).__name__}: {exc}"

    def classify(self, text: str) -> SemanticPrediction | None:
        """Retourne la catégorie la plus proche, ou `None` si le backend est indisponible."""
        prompt = text.strip()
        if not prompt or not self.ready:
            return None
        assert self._model is not None and self._centroids is not None

        embedding = _normalize(
            np.asarray(list(self._model.embed([prompt])), dtype=np.float32)
        )[0]
        scores = self._centroids @ embedding
        best = int(np.argmax(scores))
        confidence = float(np.clip(scores[best], 0.0, 1.0))
        return SemanticPrediction(category=self._categories[best], confidence=confidence)
