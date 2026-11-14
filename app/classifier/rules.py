"""Étape A du classifieur : règles déterministes (cible < 1 ms).

Ordre de priorité strict, appliqué par `apply_deterministic_rules` :
1. alias de modèle explicite (`smart-router-plan`, ...) ;
2. tag en tête du dernier message utilisateur (`#plan`, `#pro`, `#debug`, `#code`, `#fast`),
   supprimé du prompt avant transmission ;
3. contenu multimodal (`image_url`) -> `vision_ui_ux` ;
4. contexte estimé > 32 000 tokens -> `long_context_analysis`.

Aucune règle ne dépend d'un fournisseur ou d'un nom de modèle distant : seuls les alias
virtuels exposés par le routeur sont reconnus ici.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from app.schemas import ChatCompletionRequest, ChatMessage, ClassificationMethod

# Alias de modèles exposés par `GET /v1/models` -> catégorie forcée.
MODEL_ALIAS_CATEGORIES: dict[str, str] = {
    "smart-router-plan": "planning_architecture",
    "smart-router-debug": "reasoning_deep_debug",
    "smart-router-code": "general_coding_refactoring",
    "smart-router-fast": "realtime_autocomplete",
}

# Tags de forçage acceptés en tête du dernier message utilisateur.
TAG_CATEGORIES: dict[str, str] = {
    "#plan": "planning_architecture",
    "#pro": "planning_architecture",
    "#debug": "reasoning_deep_debug",
    "#code": "general_coding_refactoring",
    "#fast": "realtime_autocomplete",
}

MAX_CONTEXT_TOKENS = 32_000
CHARS_PER_TOKEN = 4  # Estimation volontairement grossière (pas de tokenizer au runtime).
MAX_CONTEXT_CHARS = MAX_CONTEXT_TOKENS * CHARS_PER_TOKEN

# Catégorie retenue lorsque aucune règle ni embedding ne permet de décider.
DEFAULT_CATEGORY = "general_coding_refactoring"

TAG_PATTERN = re.compile(r"^\s*(#(?:plan|pro|debug|code|fast))(?:\s+|$)", re.IGNORECASE)
IMAGE_BLOCK_TYPES = frozenset({"image_url", "image", "input_image"})


@dataclass(frozen=True, slots=True)
class DeterministicMatch:
    """Résultat d'une règle déterministe (aucun appel réseau ni ONNX)."""

    category: str
    method: ClassificationMethod
    messages: list[ChatMessage]


def normalized_model_name(model: str) -> str:
    """Normalise `pi5-router/smart-router-plan` -> `smart-router-plan`."""
    return model.rsplit("/", 1)[-1].strip().lower()


def iter_text_blocks(content: str | list[dict[str, Any]] | None) -> Iterator[str]:
    """Énumère les segments textuels d'un contenu OpenAI (str ou blocs multimodaux)."""
    if isinstance(content, str):
        yield content
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    yield text


def message_text(message: ChatMessage) -> str:
    """Concatène les segments textuels d'un message."""
    return "\n".join(iter_text_blocks(message.content))


def estimate_tokens(messages: list[ChatMessage]) -> int:
    """Estime la taille du contexte en tokens (`len(text) // 4` par message)."""
    return sum(len(text) // CHARS_PER_TOKEN for text in (message_text(m) for m in messages))


def has_image_block(messages: list[ChatMessage]) -> bool:
    """Détecte la présence d'un bloc image (payload multimodal)."""
    for message in messages:
        if isinstance(message.content, list):
            for block in message.content:
                if isinstance(block, dict) and block.get("type") in IMAGE_BLOCK_TYPES:
                    return True
    return False


def _last_user_index(messages: list[ChatMessage]) -> int | None:
    for index in range(len(messages) - 1, -1, -1):
        if messages[index].role == "user":
            return index
    return None


def extract_prompt_text(messages: list[ChatMessage]) -> str:
    """Texte du dernier message utilisateur, sinon du dernier message textuel."""
    index = _last_user_index(messages)
    candidates = [messages[index]] if index is not None else []
    candidates.extend(reversed(messages))
    for message in candidates:
        text = message_text(message).strip()
        if text:
            return text
    return ""


def strip_leading_tag(text: str) -> tuple[str, str | None]:
    """Retire un tag de forçage en tête de prompt.

    Retourne `(texte nettoyé, tag détecté)` ; le tag est absent si le message ne commence pas par lui.
    """
    match = TAG_PATTERN.match(text)
    if match is None:
        return text, None
    tag = match.group(1).lower()
    return text[match.end():].lstrip(), tag


def _force_alias(request: ChatCompletionRequest) -> DeterministicMatch | None:
    model = normalized_model_name(request.model)
    category = MODEL_ALIAS_CATEGORIES.get(model)
    if category is None:
        return None
    return DeterministicMatch(category=category, method="alias", messages=list(request.messages))


def _force_tag(messages: list[ChatMessage]) -> DeterministicMatch | None:
    index = _last_user_index(messages)
    if index is None:
        return None

    message = messages[index]
    if not isinstance(message.content, str):
        return None

    cleaned, tag = strip_leading_tag(message.content)
    if tag is None:
        return None

    rewritten = list(messages)
    rewritten[index] = message.model_copy(update={"content": cleaned})
    return DeterministicMatch(
        category=TAG_CATEGORIES[tag], method="tag", messages=rewritten
    )


def apply_deterministic_rules(request: ChatCompletionRequest) -> DeterministicMatch | None:
    """Applique les règles de l'Étape A dans l'ordre de priorité documenté."""
    messages = list(request.messages)

    if (alias_match := _force_alias(request)) is not None:
        return alias_match
    if (tag_match := _force_tag(messages)) is not None:
        return tag_match
    if has_image_block(messages):
        return DeterministicMatch(
            category="vision_ui_ux", method="multimodal", messages=messages
        )
    if estimate_tokens(messages) > MAX_CONTEXT_TOKENS:
        return DeterministicMatch(
            category="long_context_analysis", method="long_context", messages=messages
        )
    return None
