"""Contrats Pydantic partagés par le classifieur, le moteur de routage et le dashboard.

Deux familles de modèles cohabitent ici :
- les contrats OpenAI (`ChatMessage`, `ChatCompletionRequest`) reçus par `POST /v1/chat/completions` ;
- le schéma de validation de `config/routing_rules.json` (`RoutingRulesSchema` et ses sous-modèles),
  qui garantit qu'aucun nom de modèle ou de fournisseur n'est codé en dur dans le code Python.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Rôles OpenAI acceptés dans un message entrant.
MessageRole = Literal["system", "user", "assistant", "tool"]

DEFAULT_FALLBACK_STATUS_CODES: tuple[int, ...] = (429, 500, 502, 503, 504)


# --------------------------------------------------------------------------- #
# Contrats OpenAI entrants
# --------------------------------------------------------------------------- #
class ChatMessage(BaseModel):
    """Un message du tableau `messages` d'une requête OpenAI."""

    model_config = ConfigDict(extra="allow")

    role: MessageRole
    content: str | list[dict[str, Any]] | None = Field(
        default=None,
        description="Texte brut ou blocs multimodaux (`text`, `image_url`, ...).",
    )
    name: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None


class ChatCompletionRequest(BaseModel):
    """Payload de `POST /v1/chat/completions`.

    `extra="allow"` conserve les paramètres OpenAI additionnels (`n`, `stop`, `stream_options`,
    `response_format`, ...) afin de les retransmettre tels quels au fournisseur distant.
    """

    model_config = ConfigDict(extra="allow")

    model: str = Field(
        default="smart-router",
        description="Modèle virtuel (`smart-router` ou un alias de tag).",
    )
    messages: list[ChatMessage] = Field(..., min_length=1)
    stream: bool = False
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, gt=0)
    tools: list[dict[str, Any]] | None = None
    tool_choice: Any | None = None


# --------------------------------------------------------------------------- #
# Schéma de `config/routing_rules.json`
# --------------------------------------------------------------------------- #
class RouteConfig(BaseModel):
    """Une cible de la cascade : `{"provider": "...", "model": "..."}`."""

    model_config = ConfigDict(extra="allow")

    provider: str
    model: str


class TaskCascadeSchema(BaseModel):
    """Cascade ordonnée d'une catégorie de `task_routing_matrix`."""

    model_config = ConfigDict(extra="allow")

    primary: RouteConfig
    fallback_1: RouteConfig
    fallback_2: RouteConfig | None = None


class GlobalPolicySchema(BaseModel):
    """Politique globale anti-429 appliquée par le moteur de routage."""

    model_config = ConfigDict(extra="allow")

    strategy: str | None = None
    free_tier_priority: bool | None = None
    auto_fallback_on_status_codes: list[int] = Field(
        default_factory=lambda: list(DEFAULT_FALLBACK_STATUS_CODES)
    )
    max_retries_per_route: int = Field(default=1, ge=0)
    retry_delay_ms: int = Field(default=200, ge=0)
    cooldown_429_seconds: int = Field(default=60, ge=0)
    logging: dict[str, Any] | None = None


class ProviderModelSchema(BaseModel):
    """Un modèle déclaré dans `providers.<id>.top_3_models`."""

    model_config = ConfigDict(extra="allow")

    priority: int | None = None
    model_name: str | None = None
    model_id: str
    recommended_usage: str | None = None
    fallback_route: RouteConfig | None = None


class ProviderConfigSchema(BaseModel):
    """Un fournisseur déclaré dans `providers`."""

    model_config = ConfigDict(extra="allow")

    display_name: str | None = None
    access_type: str | None = None
    auth_env_var: str | None = None
    base_url: str | None = None
    quotas: dict[str, Any] | None = None
    top_3_models: list[ProviderModelSchema] = Field(default_factory=list)


class RoutingRulesSchema(BaseModel):
    """Validation stricte de `config/routing_rules.json` (source de vérité unique)."""

    model_config = ConfigDict(extra="allow")

    updated_at: str | None = None
    description: str | None = None
    global_policy: GlobalPolicySchema = Field(default_factory=GlobalPolicySchema)
    task_routing_matrix: dict[str, TaskCascadeSchema] = Field(..., min_length=1)
    providers: dict[str, ProviderConfigSchema] = Field(..., min_length=1)
