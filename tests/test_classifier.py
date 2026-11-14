"""Étape 2 — classifieur hybride : règles déterministes, fastembed/ONNX et latences cibles."""

from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

import pytest

from app.classifier.hybrid import TaskClassifier
from app.classifier.rules import DEFAULT_CATEGORY
from app.classifier.semantic import SemanticPrediction
from app.schemas import ChatCompletionRequest
from app.classifier.semantic import DEFAULT_MODEL_NAME, resolve_cache_dir

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class StubSemantic:
    """Backend sémantique factice : compte les appels et retourne une prédiction fixe."""

    def __init__(
        self,
        prediction: SemanticPrediction | None = None,
        ready: bool = True,
    ) -> None:
        self.prediction = prediction
        self._ready = ready
        self.calls = 0
        self.seen_texts: list[str] = []

    @property
    def ready(self) -> bool:
        return self._ready

    def warmup(self) -> None:
        return None

    def classify(self, text: str) -> SemanticPrediction | None:
        self.calls += 1
        self.seen_texts.append(text)
        return self.prediction


def make_request(
    content: str | list[dict],
    *,
    model: str = "smart-router",
    role: str = "user",
) -> ChatCompletionRequest:
    return ChatCompletionRequest(model=model, messages=[{"role": role, "content": content}])


@pytest.fixture(scope="module")
def real_classifier() -> TaskClassifier:
    classifier = TaskClassifier(model_name=DEFAULT_MODEL_NAME)
    classifier.warmup()
    assert classifier.ready, "fastembed model must be provisioned (docker build / warmup)"
    return classifier


# --------------------------------------------------------------------------- #
# Règles déterministes (Étape A)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("smart-router-plan", "planning_architecture"),
        ("smart-router-debug", "reasoning_deep_debug"),
        ("smart-router-code", "general_coding_refactoring"),
        ("smart-router-fast", "realtime_autocomplete"),
        ("pi5-router/smart-router-plan", "planning_architecture"),
    ],
)
def test_model_alias_forces_category_without_semantic_call(model: str, expected: str) -> None:
    semantic = StubSemantic(SemanticPrediction("high_throughput_batch", 0.9))
    classifier = TaskClassifier(semantic=semantic)

    result = classifier.classify(make_request("summarise this repository", model=model))

    assert result.category == expected
    assert result.method == "alias"
    assert semantic.calls == 0


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("#plan", "planning_architecture"),
        ("#pro", "planning_architecture"),
        ("#debug", "reasoning_deep_debug"),
        ("#code", "general_coding_refactoring"),
        ("#fast", "realtime_autocomplete"),
    ],
)
def test_explicit_tags_force_category_and_strip_tag(tag: str, expected: str) -> None:
    semantic = StubSemantic(SemanticPrediction("high_throughput_batch", 0.9))
    classifier = TaskClassifier(semantic=semantic)

    result = classifier.classify(make_request(f"{tag} refactor the auth module"))

    assert result.category == expected
    assert result.method == "tag"
    assert result.cleaned_messages[-1].content == "refactor the auth module"
    assert tag not in result.cleaned_messages[-1].content
    assert semantic.calls == 0


@pytest.mark.parametrize("tag", ["#PLAN", "#Debug", "#CODE"])
def test_tag_detection_is_case_insensitive(tag: str) -> None:
    classifier = TaskClassifier(semantic=StubSemantic())

    result = classifier.classify(make_request(f"{tag}  do the thing"))

    assert result.method == "tag"
    assert result.cleaned_messages[-1].content == "do the thing"


def test_tag_only_prompt_is_stripped_to_empty_string() -> None:
    classifier = TaskClassifier(semantic=StubSemantic())

    result = classifier.classify(make_request("#fast"))

    assert result.method == "tag"
    assert result.category == "realtime_autocomplete"
    assert result.cleaned_messages[-1].content == ""


def test_tag_must_be_at_prompt_start_to_force_category() -> None:
    semantic = StubSemantic(SemanticPrediction("planning_architecture", 0.8))
    classifier = TaskClassifier(semantic=semantic)
    prompt = "Please #plan this later"

    result = classifier.classify(make_request(prompt))

    assert result.method == "semantic"
    assert result.cleaned_messages[-1].content == prompt
    assert semantic.calls == 1


def test_tag_cleanup_only_touches_last_user_message() -> None:
    request = ChatCompletionRequest(
        messages=[
            {"role": "system", "content": "#code is a tag, keep me"},
            {"role": "assistant", "content": "#plan stay intact"},
            {"role": "user", "content": "#debug inspect the crash"},
        ]
    )
    classifier = TaskClassifier(semantic=StubSemantic())

    result = classifier.classify(request)

    assert result.cleaned_messages[0].content == "#code is a tag, keep me"
    assert result.cleaned_messages[1].content == "#plan stay intact"
    assert result.cleaned_messages[2].content == "inspect the crash"
    # La requête d'origine n'est jamais mutée.
    assert request.messages[2].content == "#debug inspect the crash"


def test_multimodal_image_url_routes_to_vision_ui_ux() -> None:
    semantic = StubSemantic(SemanticPrediction("planning_architecture", 0.9))
    classifier = TaskClassifier(semantic=semantic)
    content = [
        {"type": "text", "text": "compare these two screens"},
        {"type": "image_url", "image_url": {"url": "http://pi5.local/mock.png"}},
    ]

    result = classifier.classify(make_request(content))

    assert result.category == "vision_ui_ux"
    assert result.method == "multimodal"
    assert semantic.calls == 0


def test_long_context_over_32k_tokens_routes_to_long_context_analysis() -> None:
    semantic = StubSemantic(SemanticPrediction("planning_architecture", 0.9))
    classifier = TaskClassifier(semantic=semantic)

    result = classifier.classify(make_request("a" * 128_004))

    assert result.category == "long_context_analysis"
    assert result.method == "long_context"
    assert semantic.calls == 0


def test_context_at_threshold_still_uses_semantic_classification() -> None:
    semantic = StubSemantic(SemanticPrediction("general_coding_refactoring", 0.7))
    classifier = TaskClassifier(semantic=semantic)

    result = classifier.classify(make_request("a" * 128_000))

    assert result.method == "semantic"
    assert result.category == "general_coding_refactoring"


def test_deterministic_rules_execute_under_1ms() -> None:
    classifier = TaskClassifier(semantic=StubSemantic())
    request = make_request("#plan design the storage layer")
    classifier.classify(request)  # échauffement Python (imports, copies)

    durations = []
    for _ in range(50):
        start = time.perf_counter()
        classifier.classify(request)
        durations.append((time.perf_counter() - start) * 1000.0)

    assert statistics.median(durations) < 1.0, f"median {statistics.median(durations):.3f} ms"


# --------------------------------------------------------------------------- #
# Classifieur sémantique (Étape B, modèle réel)
# --------------------------------------------------------------------------- #
def test_semantic_classifier_routes_coding_request(real_classifier: TaskClassifier) -> None:
    result = real_classifier.classify(
        make_request("Write a Python function that parses a CSV file and returns a list of rows.")
    )

    assert result.method == "semantic"
    assert result.category == "general_coding_refactoring"
    assert 0.0 < result.confidence <= 1.0


def test_semantic_classifier_routes_architecture_request(real_classifier: TaskClassifier) -> None:
    result = real_classifier.classify(
        make_request(
            "Design the architecture and module boundaries of a new distributed service, "
            "with milestones, risks and technical trade-offs."
        )
    )

    assert result.method == "semantic"
    assert result.category == "planning_architecture"


def test_semantic_classifier_routes_debug_request(real_classifier: TaskClassifier) -> None:
    result = real_classifier.classify(
        make_request("Debug this stack trace and explain the root cause step by step.")
    )

    assert result.method == "semantic"
    assert result.category == "reasoning_deep_debug"


def test_hybrid_classification_latency_under_25ms(real_classifier: TaskClassifier) -> None:
    request = make_request("Explain how the routing cache invalidation works in this module.")
    real_classifier.classify(request)  # échauffement du tokenizer/ONNX

    durations = []
    for _ in range(5):
        start = time.perf_counter()
        result = real_classifier.classify(request)
        durations.append((time.perf_counter() - start) * 1000.0)
        assert result.method == "semantic"

    median = statistics.median(durations)
    assert median < 25.0, f"median {median:.3f} ms > 25 ms (runs={durations})"


def test_semantic_classifier_returns_none_when_not_warm() -> None:
    from app.classifier.semantic import SemanticClassifier

    classifier = SemanticClassifier()
    assert classifier.ready is False
    assert classifier.classify("anything") is None


# --------------------------------------------------------------------------- #
# Dégradation et contraintes matérielles
# --------------------------------------------------------------------------- #
def test_classifier_reports_fallback_when_semantic_unavailable() -> None:
    classifier = TaskClassifier(semantic=StubSemantic(ready=False))
    classifier.warmup()

    result = classifier.classify(make_request("Write a function to sort users by name"))

    assert result.method == "fallback_default"
    assert result.category == DEFAULT_CATEGORY
    assert result.confidence == 0.0
    assert classifier.ready is False


def test_classifier_exposes_ready_after_warmup(real_classifier: TaskClassifier) -> None:
    assert real_classifier.ready is True


def test_no_pytorch_dependency_is_installed_or_required() -> None:
    import app.classifier.hybrid  # noqa: F401  (force l'import du module)
    import app.main  # noqa: F401

    assert "torch" not in sys.modules
    requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    dependencies = " ".join(
        line.split("#", 1)[0].strip() for line in requirements.splitlines()
    )
    assert "torch" not in dependencies
    assert "sentence-transformers" not in dependencies


def test_fastembed_cache_dir_honours_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FASTEMBED_CACHE_PATH", r"C:\cache\fastembed")

    assert resolve_cache_dir() == r"C:\cache\fastembed"
