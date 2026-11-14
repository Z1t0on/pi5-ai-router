# Plan d'Architecture Maître — `pi5-ai-router`

> **Statut** : Plan d'architecture approuvé pour implémentation incrémentale par l'agent `build`.  
> **Cible matérielle** : Windows 11 (`linux/amd64` Docker Desktop pour tests locaux) et Raspberry Pi 5 (`linux/arm64`, Debian 12, 8 Go RAM, IP `192.168.1.44:4000`, budget conteneur < 500 Mo RAM).  
> **Source de vérité** : `config/routing_rules.json` (14 fournisseurs, 7 catégories de tâches, politique anti-429).

---

## 1. Contexte & Objectif

`pi5-ai-router` est un proxy IA autonome compatible avec l'API OpenAI (`POST /v1/chat/completions`, `GET /v1/models`, `GET /health`), conçu pour servir de point d'entrée unique aux clients **OpenCode** et **Zed** sur le réseau local via le modèle virtuel `smart-router` (et ses variantes explicites par tag `smart-router-plan`, `smart-router-debug`, `smart-router-code`, `smart-router-fast`).

### Objectifs Architecturaux Non-Négociables
1. **Latence de classification < 25 ms sur ARM64 CPU** : Classifieur hybride en deux temps — règles déterministes (< 1 ms) suivies d'un classifieur sémantique `fastembed` (`BAAI/bge-small-en-v1.5` en ONNX Runtime quantifié, zéro PyTorch/TensorFlow).
2. **Empreinte mémoire conteneur < 500 Mo** : Poids ONNX pré-téléchargés lors du `docker build`, sans framework ML lourd ni processus Node.js pour le frontend.
3. **Configuration dynamique sans redémarrage** : Lecture et rechargement à chaud de `config/routing_rules.json` via détection de `os.path.getmtime` ou téléversement depuis le dashboard.
4. **Verrou financier AWS Bedrock (`BEDROCK_LOCKED=true`)** : Blocage strict de 100 % des requêtes vers `aws_bedrock` (protégeant le crédit de 200 $), vérifié à la fois dans `.env` et dans l'état persistant SQLite/mémoire avant toute exécution de route.
5. **Streaming SSE sans coupure (`stream: true`)** : Tamponnement et validation du statut HTTP et du premier chunk non vide du fournisseur distant *avant* l'envoi des en-têtes HTTP `200 OK` au client, permettant une bascule silencieuse sur `fallback_1` puis `fallback_2` en cas d'erreur `429` ou `5xx`.
6. **Asynchrone intégral** : Tous les appels HTTP sortants reposent sur `httpx.AsyncClient` (aucun appel bloquant `requests`).

---

## 2. Fichiers Cibles & Arborescence Modulaire

L'architecture adopte un découpage modulaire par domaine métier sous `app/` afin d'isoler la classification, le routage/streaming, la persistance SQLite et le dashboard d'administration :

```text
pi5-ai-router/
├── .env.example                       # Modèle des variables d'environnement (clés des 14 providers + BEDROCK_LOCKED)
├── Dockerfile                         # Build multi-stage ARM64/AMD64 + pré-téléchargement ONNX FastEmbed
├── docker-compose.yml                 # Service port 4000, volumes ./config et ./data, restart: unless-stopped
├── requirements.txt                   # Dépendances Python épurées (FastAPI, uvicorn, httpx, fastembed, aiosqlite, boto3, pytest)
├── config/
│   └── routing_rules.json             # Source de vérité existante (7 catégories, 14 providers)
├── data/                              # Volume persistant (créé au runtime)
│   └── router_logs.db                 # Base SQLite en mode WAL
├── app/
│   ├── __init__.py
│   ├── main.py                        # Point d'entrée FastAPI, lifespan, routes OpenAI (/v1/*, /health) et montage dashboard
│   ├── schemas.py                     # Contrats Pydantic (requêtes/réponses OpenAI, règles JSON, statuts admin)
│   ├── classifier/
│   │   ├── __init__.py                # Façade publique `TaskClassifier`
│   │   ├── rules.py                   # Étape A (< 1 ms) : images multimodales, taille contexte (> 32k tokens), tags (#plan, #debug, #code, #fast, #pro)
│   │   ├── semantic.py                # Étape B (< 20 ms) : embeddings FastEmbed (`BAAI/bge-small-en-v1.5`) + similarité cosinus
│   │   └── hybrid.py                  # Orchestrateur hybride combinant Étape A -> Étape B et nettoyage des tags
│   ├── router/
│   │   ├── __init__.py                # Façade publique `RouterEngine`
│   │   ├── config_loader.py           # Chargement, validation et hot-reload (`os.path.getmtime`) de `config/routing_rules.json`
│   │   ├── cooldown.py                # Gestionnaire de quarantaine 429 en mémoire (60 s par couple provider/model)
│   │   ├── adapters.py                # Résolution d'URL, authentification `.env` et traduction (OpenAI-compat, Cloudflare, Google, AWS Bedrock)
│   │   ├── cascade.py                 # Résolution `[primary, fallback_1, fallback_2]`, verrou Bedrock, filtre tools, alias `opencode_v2`
│   │   └── streaming.py               # Exécution `httpx.AsyncClient` avec buffer du 1er chunk SSE avant HTTP 200 et adaptateur Bedrock Converse Stream
│   ├── db/
│   │   ├── __init__.py
│   │   ├── connection.py              # Initialisation asynchrone `aiosqlite` avec `PRAGMA journal_mode=WAL;` et création des tables
│   │   └── repository.py              # CRUD `request_logs` (50 derniers logs sans secrets/prompts bruts) et `system_state` (`bedrock_locked`, providers désactivés)
│   └── dashboard/
│       ├── __init__.py
│       ├── routes.py                  # APIRouter `/api/*` (status, toggle-bedrock, toggle-provider, upload-rules, logs) et service de `index.html`
│       └── static/
│           └── index.html             # Interface web sombre autonome (Tailwind CSS CDN + Vanilla JS Fetch API)
└── tests/
    ├── conftest.py                    # Fixtures partagées (FastAPI TestClient/AsyncClient, DB temporaire, mock `routing_rules.json`)
    ├── test_health.py                 # Tests Étape 1 (squelette, /health, /v1/models, schémas)
    ├── test_classifier.py             # Tests Étape 2 (règles déterministes, tags, similarité sémantique, latence < 25 ms)
    ├── test_cascade.py                # Tests Étape 3 (hot-reload, verrou Bedrock, cooldown 429, tools, clés manquantes, opencode_v2)
    ├── test_streaming.py              # Tests Étape 4 (buffer 1er chunk SSE, bascule silencieuse sur 429/5xx avant 200, Bedrock SSE)
    └── test_dashboard_db.py           # Tests Étape 5 (SQLite WAL, endpoints /api/*, sécurité non-exposition des secrets)
```

---

## 3. Contrats d'Interface

### 3.1 Schémas Pydantic (`app/schemas.py`)

| Modèle | Rôle | Champs Clés & Contraintes |
| :--- | :--- | :--- |
| `ChatMessage` | Message OpenAI entrant | `role: Literal["system", "user", "assistant", "tool"]`, `content: str \| list[dict[str, Any]] \| None`, `tool_calls: list[dict[str, Any]] \| None = None`, `tool_call_id: str \| None = None` |
| `ChatCompletionRequest` | Payload `POST /v1/chat/completions` | `model: str = "smart-router"`, `messages: list[ChatMessage]`, `stream: bool = False`, `temperature: float \| None = None`, `max_tokens: int \| None = None`, `tools: list[dict[str, Any]] \| None = None`, `tool_choice: Any \| None = None` (`extra="allow"` pour préserver les paramètres OpenAI standards) |
| `ClassificationResult` | Sortie du classifieur | `category: str`, `method: Literal["tag", "alias", "multimodal", "long_context", "semantic", "fallback_default"]`, `cleaned_messages: list[ChatMessage]`, `latency_ms: float`, `confidence: float` |
| `RouteTarget` | Cible d'exécution résolue | `provider: str`, `model: str`, `base_url: str`, `auth_env_var: str`, `is_fallback: bool` |
| `RoutingRulesSchema` | Validation stricte de `config/routing_rules.json` | `updated_at: str`, `global_policy: GlobalPolicySchema`, `task_routing_matrix: dict[str, TaskCascadeSchema]`, `providers: dict[str, ProviderConfigSchema]` |
| `ProviderStatusOut` | État d'un provider pour `/api/status` | `provider_id: str`, `display_name: str`, `access_type: str`, `has_key: bool` (jamais la valeur), `enabled: bool`, `in_cooldown: bool`, `cooldown_remaining_s: int` |
| `SystemStatusOut` | Réponse `GET /api/status` | `bedrock_locked: bool`, `rules_updated_at: str`, `total_providers: int`, `providers: list[ProviderStatusOut]` |
| `RequestLogOut` | Entrée de journal `GET /api/logs` | `id: int`, `timestamp: str`, `category: str`, `provider: str`, `model: str`, `latency_ms: float`, `status_code: int`, `is_fallback: bool`, `error_detail: str \| None` |

### 3.2 Routes FastAPI (`app/main.py` & `app/dashboard/routes.py`)

| Méthode & Chemin | Contrat Entrée / Sortie | Comportement |
| :--- | :--- | :--- |
| `GET /health` | `200 OK` -> `{"status": "ok", "rules_loaded": bool, "classifier_ready": bool, "bedrock_locked": bool}` | Vérifie la disponibilité du routeur, du classifieur ONNX et du verrou Bedrock. |
| `GET /v1/models` | `200 OK` -> Liste OpenAI `{ "object": "list", "data": [...] }` | Expose `smart-router` ainsi que les alias explicites (`smart-router-plan`, `smart-router-debug`, `smart-router-code`, `smart-router-fast`). |
| `POST /v1/chat/completions` | Entrée : `ChatCompletionRequest`<br>Sortie : JSON OpenAI ou `StreamingResponse` (`text/event-stream`) | Classifie la requête, résout la cascade, exécute avec bascule transparente et journalise les métadonnées dans SQLite. |
| `GET /` | HTML (`text/html`) | Sert le dashboard statique `app/dashboard/static/index.html`. |
| `GET /api/status` | `200 OK` -> `SystemStatusOut` | Retourne l'état `bedrock_locked` et le statut des 14 providers (`has_key` sans exposer de secrets). |
| `POST /api/toggle-bedrock` | `200 OK` -> `{"bedrock_locked": bool}` | Inverse et persiste `bedrock_locked` dans SQLite `system_state`. |
| `POST /api/toggle-provider/{provider_id}` | `200 OK` -> `{"provider_id": str, "enabled": bool}` (`404` si inconnu) | Active/désactive manuellement un provider dans SQLite `system_state`. |
| `POST /api/upload-rules` | Corps JSON brut ou fichier multipart | Valide via `RoutingRulesSchema`, écrit atomiquement `config/routing_rules.json` et force le rechargement. |
| `GET /api/logs` | `200 OK` -> `list[RequestLogOut]` | Retourne les 50 dernières entrées de `request_logs` triées par date décroissante. |

### 3.3 Signatures des Fonctions Principales

- **`app/classifier/hybrid.py`** :
  - `class TaskClassifier`:
    - `def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5", cache_dir: str | None = None) -> None`
    - `def warmup(self) -> None` (appelé au `lifespan` FastAPI pour charger les poids ONNX et pré-calculer les centroïdes des catégories)
    - `def classify(self, request: ChatCompletionRequest) -> ClassificationResult`
- **`app/router/config_loader.py`** :
  - `class RulesConfigLoader`:
    - `def __init__(self, rules_path: Path) -> None`
    - `def get_rules(self) -> RoutingRulesSchema` (vérifie `os.path.getmtime` avant retour ; recharge si modifié)
    - `def validate_and_save(self, raw_payload: dict[str, Any]) -> RoutingRulesSchema`
- **`app/router/cascade.py`** :
  - `async def resolve_cascade(category: str, request: ChatCompletionRequest, rules: RoutingRulesSchema, repo: StateRepository, cooldowns: CooldownRegistry) -> list[RouteTarget]`
- **`app/router/streaming.py`** :
  - `async def execute_chat_completion(request: ChatCompletionRequest, category: str, targets: list[RouteTarget], client: httpx.AsyncClient, cooldowns: CooldownRegistry, policy: GlobalPolicySchema) -> dict[str, Any] | StreamingResponse`
- **`app/db/repository.py`** :
  - `class StateRepository`:
    - `async def init_schema(self) -> None`
    - `async def get_bedrock_locked(self, default_from_env: bool) -> bool`
    - `async def set_bedrock_locked(self, locked: bool) -> bool`
    - `async def is_provider_enabled(self, provider_id: str) -> bool`
    - `async def set_provider_enabled(self, provider_id: str, enabled: bool) -> bool`
    - `async def log_request(self, entry: RequestLogCreate) -> None`
    - `async def get_recent_logs(self, limit: int = 50) -> list[RequestLogOut]`

---

## 4. Plan de Développement Incrémental (6 Étapes pour l'Agent `build`)

### Étape 1 : Squelette FastAPI & Healthcheck
- **Périmètre** :
  - Initialiser l'arborescence `app/`, `tests/`, `requirements.txt` et `.env.example` (listant les clés des 14 providers de `config/routing_rules.json`, `CLOUDFLARE_ACCOUNT_ID`, `KILO_BASE_URL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `BEDROCK_LOCKED=true`, `RULES_FILE_PATH`, `SQLITE_DB_PATH`).
  - Créer `app/schemas.py` avec les contrats OpenAI et `RoutingRulesSchema`.
  - Créer `app/main.py` avec cycle de vie `lifespan` (initialisation d'un `httpx.AsyncClient` partagé), routes `GET /health` et `GET /v1/models`, et stub temporaire de `POST /v1/chat/completions`.
- **Critères de validation** :
  - L'application démarre via `uvicorn app.main:app` sans erreur d'import ni avertissement de dépréciation Pydantic v2.
  - `GET /health` répond en < 5 ms avec le statut des composants.
  - `GET /v1/models` retourne `smart-router` et les 4 alias de tags définis dans `opencode.json`.
- **Tests automatisés associés (`tests/test_health.py`)** :
  - `test_health_endpoint_returns_200_and_expected_keys`
  - `test_v1_models_lists_smart_router_and_tag_aliases`
  - `test_chat_completion_request_schema_rejects_empty_messages`

---

### Étape 2 : Classificateur Hybride FastEmbed/ONNX (< 500 Mo RAM)
- **Périmètre** :
  - Implémenter `app/classifier/rules.py` (Étape A, < 1 ms) dans l'ordre strict de priorité :
    1. Alias modèle explicite (`smart-router-plan` -> `planning_architecture`, `smart-router-debug` -> `reasoning_deep_debug`, `smart-router-code` -> `general_coding_refactoring`, `smart-router-fast` -> `realtime_autocomplete`).
    2. Tag explicite en début du dernier message utilisateur (`#plan` / `#pro` -> `planning_architecture`, `#debug` -> `reasoning_deep_debug`, `#code` -> `general_coding_refactoring`, `#fast` -> `realtime_autocomplete`), avec suppression propre du tag avant transmission.
    3. Contenu multimodal (`image_url` ou bloc `type == "image_url"`) -> `vision_ui_ux`.
    4. Contexte long (somme estimée `len(text) // 4 > 32000` tokens sur l'ensemble de `messages`) -> `long_context_analysis`.
  - Implémenter `app/classifier/semantic.py` (Étape B, < 20 ms) avec `fastembed.TextEmbedding(model_name="BAAI/bge-small-en-v1.5")` : pré-calculer les vecteurs normalisés d'ancres descriptives pour les 5 catégories textuelles (`planning_architecture`, `general_coding_refactoring`, `realtime_autocomplete`, `reasoning_deep_debug`, `high_throughput_batch`) au `warmup()`, puis effectuer un produit scalaire numpy sur le dernier message utilisateur.
  - Implémenter `app/classifier/hybrid.py` et intégrer le `warmup()` au `lifespan` de `app/main.py`.
- **Critères de validation** :
  - Aucune dépendance à `torch` ou `sentence-transformers`.
  - Temps d'inférence médian de `classify()` < 25 ms sur requêtes textuelles et < 1 ms sur règles déterministes.
  - Nettoyage garanti des tags `#plan`, `#debug`, `#code`, `#fast`, `#pro` sans altérer le reste du prompt.
- **Tests automatisés associés (`tests/test_classifier.py`)** :
  - `test_model_alias_forces_category_without_onnx`
  - `test_explicit_tags_force_category_and_strip_tag` (paramétré sur `#plan`, `#pro`, `#debug`, `#code`, `#fast`)
  - `test_multimodal_image_url_routes_to_vision_ui_ux`
  - `test_long_context_over_32k_tokens_routes_to_long_context_analysis`
  - `test_semantic_classification_routes_coding_vs_architecture_under_25ms` (avec mesure `time.perf_counter()` post-warmup)

---

### Étape 3 : Moteur de Cascade `routing_rules.json` & Verrou Bedrock
- **Périmètre** :
  - Implémenter `app/router/config_loader.py` : lecture de `config/routing_rules.json`, validation Pydantic et rechargement automatique si `os.path.getmtime` change.
  - Implémenter `app/router/cooldown.py` : registre en mémoire `{ (provider, model): expiry_timestamp }` appliquant `global_policy.cooldown_429_seconds` (`60` s par défaut).
  - Implémenter `app/router/adapters.py` : résolution dynamique des endpoints à partir de `providers[id].base_url`, gestion des cas particuliers (`cloudflare` avec `{CLOUDFLARE_ACCOUNT_ID}`, `kilo_code` via `KILO_BASE_URL`, domaines nus sans schéma `https://` ni suffixe `/v1/chat/completions`, et adaptateur `aws_bedrock` via `boto3` Converse ou endpoint Mantle selon la présence des variables IAM vs Bearer).
  - Implémenter `app/router/cascade.py` : construction de la liste ordonnée `[primary, fallback_1, fallback_2]` (+ extension vers `fallback_route` du modèle si nécessaire), filtrage strict de `aws_bedrock` tant que `BEDROCK_LOCKED=true`, exclusion des providers désactivés ou sans clé `.env`, exclusion des couples en cooldown 429, et filtrage des modèles incompatibles avec `tools`/`tool_calls`.
- **Critères de validation** :
  - Modification de `config/routing_rules.json` prise en compte à la requête suivante sans redémarrage.
  - 0 appel sortant vers `aws_bedrock` lorsque `BEDROCK_LOCKED=true` (même si `aws_bedrock` est `fallback_2` de `planning_architecture`).
  - Bascule immédiate hors d'un couple `(provider, model)` placé en quarantaine 429 pendant 60 s.
- **Tests automatisés associés (`tests/test_cascade.py`)** :
  - `test_config_hot_reload_on_mtime_change`
  - `test_bedrock_locked_skips_aws_bedrock_completely`
  - `test_missing_env_api_key_skips_provider_cleanly`
  - `test_429_cooldown_quarantines_route_for_60_seconds`
  - `test_tools_payload_skips_incompatible_micro_models`
  - `test_opencode_v2_resolution_with_and_without_api_key`
  - `test_base_url_normalization_for_all_14_providers`

---

### Étape 4 : Proxification du Streaming SSE avec Buffer du 1er Chunk
- **Périmètre** :
  - Implémenter `app/router/streaming.py` pour gérer à la fois `stream=False` et `stream=True` avec `httpx.AsyncClient`.
  - Pour `stream=True` :
    1. Itérer sur la cascade résolue et appliquer `max_retries_per_route` + `retry_delay_ms` (200 ms) sur les erreurs transitoires configurées dans `auto_fallback_on_status_codes` (`[429, 500, 502, 503, 504]`).
    2. Ouvrir le flux avec `client.build_request("POST", ...)` + `await client.send(req, stream=True)`.
    3. Vérifier `response.status_code` ; si dans `auto_fallback_on_status_codes`, fermer `await response.aclose()`, enregistrer le cooldown si `429` et passer au fallback suivant.
    4. Lire et valider la première ligne SSE non vide de `response.aiter_lines()` *avant* d'instancier `StreamingResponse`. Si le flux coupe prématurément ou retourne un objet JSON d'erreur avant le premier chunk valide, fermer et passer au fallback.
    5. Retourner `StreamingResponse` avec un générateur asynchrone réémettant ce premier chunk puis le reste du flux, avec fermeture garantie dans `finally: await response.aclose()`.
  - Implémenter la traduction `aws_bedrock` (`converse_stream` / `converse`) vers des chunks SSE OpenAI (`data: {"id": "chatcmpl-bedrock", "object": "chat.completion.chunk", ...}\n\n` + `data: [DONE]\n\n`) lorsque `BEDROCK_LOCKED=false`.
  - Brancher l'ensemble sur `POST /v1/chat/completions` dans `app/main.py`.
- **Critères de validation** :
  - Aucune fuite de connexion `httpx` (toutes les réponses streamées sont fermées sur succès, erreur ou annulation client).
  - Un client OpenCode/Zed ne reçoit **jamais** un `200 OK` suivi d'une erreur `429` ou `502` : le basculement sur `fallback_1` est totalement transparent.
  - Si tous les fallbacks de la cascade échouent, le routeur retourne un statut HTTP `503 Service Unavailable` structuré OpenAI-compatible avant tout envoi SSE.
- **Tests automatisés associés (`tests/test_streaming.py`)** :
  - `test_stream_fallback_on_429_status_before_http_200` (mock `httpx.MockTransport` : primary -> 429, fallback_1 -> 200 SSE ; vérifie que le client reçoit 200 + flux complet de fallback_1)
  - `test_stream_fallback_on_empty_or_error_first_chunk_before_http_200` (primary -> 200 mais flux coupé/erreur JSON avant 1er token -> bascule transparente sur fallback_1)
  - `test_stream_returns_503_when_entire_cascade_fails`
  - `test_non_stream_retries_and_fallbacks_on_503`
  - `test_bedrock_converse_stream_translates_to_openai_sse_when_unlocked`

---

### Étape 5 : Persistance SQLite & API Dashboard
- **Périmètre** :
  - Implémenter `app/db/connection.py` et `app/db/repository.py` avec `aiosqlite` et `PRAGMA journal_mode=WAL;`.
  - Créer les tables `request_logs` (`id`, `timestamp`, `category`, `provider`, `model`, `latency_ms`, `status_code`, `is_fallback`, `error_detail`) et `system_state` (`key TEXT PRIMARY KEY`, `value TEXT`).
  - Synchroniser l'état initial de `bedrock_locked` depuis `.env` (`BEDROCK_LOCKED`) uniquement si la clé est absente de `system_state` (ou prioriser le verrou de sécurité si `BEDROCK_LOCKED=true` selon la politique choisie — voir Section 5).
  - Implémenter `app/dashboard/routes.py` (`GET /`, `GET /api/status`, `POST /api/toggle-bedrock`, `POST /api/toggle-provider/{provider_id}`, `POST /api/upload-rules`, `GET /api/logs`).
  - Créer `app/dashboard/static/index.html` (fichier HTML unique avec Tailwind CSS CDN et Vanilla JS) permettant : le basculement du verrou Bedrock 200 $, la visualisation des 14 providers (`Clé OK` / `Absente` sans jamais exposer la clé) et leur activation/désactivation, le glisser-déposer de `routing_rules.json`, et le tableau temps réel des 50 dernières requêtes.
- **Critères de validation** :
  - Écritures concurrentes SQLite en mode WAL sans `database is locked`.
  - Aucune valeur de clé API `.env` ni aucun corps complet de prompt utilisateur stocké dans `router_logs.db` ou renvoyé par `/api/*`.
  - Téléversement d'un JSON invalide rejeté avec `422 Unprocessable Entity` sans écraser `config/routing_rules.json`.
- **Tests automatisés associés (`tests/test_dashboard_db.py`)** :
  - `test_sqlite_wal_mode_enabled_and_tables_created`
  - `test_api_status_never_exposes_secret_api_keys`
  - `test_toggle_bedrock_persists_across_repository_reinit_and_blocks_calls`
  - `test_toggle_provider_disables_provider_in_cascade`
  - `test_upload_rules_validates_schema_and_rejects_invalid_json`
  - `test_api_logs_returns_last_50_entries_without_prompt_bodies`

---

### Étape 6 : Dockerfile ARM64 Multi-Stage & Conteneurisation
- **Périmètre** :
  - Rédiger `Dockerfile` multi-stage basé sur `python:3.11-slim` compatible `linux/amd64` et `linux/arm64` :
    - Stage `builder` : installation des dépendances de compilation minimales uniquement si nécessaires, installation de `requirements.txt` dans un virtualenv `/opt/venv`.
    - Stage `runtime` : copie `/opt/venv`, définition de `FASTEMBED_CACHE_PATH=/app/.cache/fastembed`, exécution du pré-téléchargement ONNX `BAAI/bge-small-en-v1.5` dans l'image, copie de `app/`, exposition du port `4000`, `HEALTHCHECK` HTTP sur `/health`, lancement `uvicorn app.main:app --host 0.0.0.0 --port 4000`.
  - Rédiger `docker-compose.yml` avec `restart: unless-stopped`, port `4000:4000`, `env_file: .env`, et montage exclusif de `./config:/app/config` et `./data:/app/data` (afin de préserver `/app/.cache/fastembed` dans le conteneur), plus limite mémoire indicative `mem_limit: 512m`.
- **Critères de validation** :
  - Build réussi sur Windows 11 (`linux/amd64`) et support multi-arch (`linux/arm64`) sans `torch`.
  - Démarrage hors-ligne du conteneur sans aucun téléchargement HuggingFace/ONNX au runtime (`FASTEMBED_CACHE_PATH` intact).
  - Empreinte RSS du conteneur en fonctionnement < 500 Mo (`docker stats` sous charge).
- **Tests / Vérifications automatisées associées** :
  - Exécution complète de `pytest` dans le venv/conteneur (`pytest -v`).
  - Vérification statique dans un test (`tests/test_docker_artifacts.py` optionnel ou script CI) que `torch` et `sentence-transformers` sont absents de `requirements.txt` et que `FASTEMBED_CACHE_PATH` est configuré dans `Dockerfile`.

---

## 5. Cas Limites & Fallbacks

| Cas Limite | Comportement Attendu & Résolution |
| :--- | :--- |
| **Cooldown HTTP 429** | Dès qu'un couple `(provider, model)` renvoie HTTP `429` (ou timeout réseau), il est mis en quarantaine en mémoire pendant `global_policy.cooldown_429_seconds` (60 s). Les requêtes suivantes sautent instantanément cette route vers `fallback_1`/`fallback_2` sans attente. Si *toutes* les routes de la cascade sont en cooldown, tenter en dernier ressort la route au cooldown le plus proche de l'expiration ou renvoyer `503`. |
| **Clés `.env` manquantes** | Avant d'appeler un fournisseur, `cascade.py` vérifie que `os.getenv(provider_cfg.auth_env_var)` (et `CLOUDFLARE_ACCOUNT_ID` pour `cloudflare`, ou `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` ou `AWS_BEDROCK_API_KEY` pour `aws_bedrock`) est non vide. Un fournisseur sans clé est ignoré silencieusement dans la cascade (jamais d'erreur 401 gaspillée) et apparaît avec le badge gris `Absente` dans le dashboard. |
| **Résolution de `opencode_v2`** | Dans `config/routing_rules.json`, `opencode_v2` est configuré avec `auth_env_var: "OPENCODE_API_KEY"` et `base_url: "opencode.ai"`. **Double stratégie** : (1) Si `OPENCODE_API_KEY` est présent dans `.env`, router directement vers l'endpoint OpenAI-compatible OpenCode Zen (`https://opencode.ai/zen/v1/chat/completions`) ; (2) Si `OPENCODE_API_KEY` est absent dans `.env`, résoudre dynamiquement `opencode_v2` via le `fallback_route` déclaré sur le modèle correspondant dans `providers.opencode_v2.top_3_models` (ex. `deepseek-v4.1-flash-free` -> `nvidia`, `glm-5.3-flash-free` -> `z_ai`), sinon vers le premier provider gratuit actif ayant une clé configurée (`groq`, `google_ai_studio`, `cloudflare`, `cerebras`). |
| **Payloads `tools` / `tool_calls` incompatibles** | Si `request.tools` ou un message contenant `tool_calls` est présent, `cascade.py` filtre les modèles réputés incompatibles avec le function calling (`llama-3.2-3b`, `llama-prompt-guard`, `mercury-edit`, ou tout modèle listé dans une liste d'exclusion configurable) et bascule directement sur le fallback compatible suivant. Si un provider renvoie `400` mentionnant une non-prise en charge de `tools`, basculer également vers le fallback. |
| **Normalisation des `base_url` hétérogènes** | `config/routing_rules.json` contient des formats variés (`"groq.com"`, `"https://cerebras.ai"`, `"https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"`, `"{CLOUDFLARE_ACCOUNT_ID}"`). `adapters.py` doit : (1) privilégier une éventuelle variable `.env` dédiée (ex. `KILO_BASE_URL` pour `kilo_code`) ; (2) préfixer `https://` si absent ; (3) substituer `{CLOUDFLARE_ACCOUNT_ID}` ; (4) appliquer la table de chemins OpenAI-compatibles officiels lorsque `base_url` ne contient qu'un domaine racine (ex. `nvidia.com` -> `https://integrate.api.nvidia.com/v1/chat/completions`, `groq.com` -> `https://api.groq.com/openai/v1/chat/completions`, `cerebras.ai` -> `https://api.cerebras.ai/v1/chat/completions`, `mistral.ai` -> `https://api.mistral.ai/v1/chat/completions`, `deepseek.com` -> `https://api.deepseek.com/v1/chat/completions`, `openrouter.ai` -> `https://openrouter.ai/api/v1/chat/completions`, `sambanova.ai` -> `https://api.sambanova.ai/v1/chat/completions`, `z.ai` -> `https://api.z.ai/api/paas/v4/chat/completions`, `cohere.ai` -> `https://api.cohere.ai/compatibility/v1/chat/completions`, `opencode.ai` -> `https://opencode.ai/zen/v1/chat/completions`). |
| **Priorité du verrou Bedrock (`BEDROCK_LOCKED`)** | Au premier démarrage (clé absente de SQLite `system_state`), `bedrock_locked` est initialisé depuis `BEDROCK_LOCKED` (défaut strict `true`). Si `BEDROCK_LOCKED=true` est forcé dans l'environnement et que l'utilisateur veut le déverrouiller temporairement via le dashboard, l'état runtime SQLite fait foi jusqu'au prochain redémarrage ou bascule UI, tout en démarrant toujours verrouillé par défaut si la variable d'env est `true` et la DB vierge. |
| **Rechargement JSON concurrent / invalide** | `validate_and_save` valide d'abord le JSON contre `RoutingRulesSchema` avant d'écrire dans un fichier temporaire puis d'effectuer un remplacement atomique (`os.replace`). En cas d'édition manuelle invalide sur disque, `config_loader.py` conserve la dernière configuration valide en cache mémoire et logge l'erreur sans crasher le routeur. |

---

## 6. Plan de Vérification Global (`pytest`)

L'agent `build` devra créer et faire passer l'intégralité des tests suivants via `pytest -v` après chaque étape et avant toute livraison finale :

1. **`tests/test_health.py`** :
   - `test_health_endpoint_returns_200_and_expected_keys`
   - `test_v1_models_lists_smart_router_and_tag_aliases`
   - `test_chat_completion_request_schema_rejects_empty_messages`
2. **`tests/test_classifier.py`** :
   - `test_model_alias_forces_category_without_onnx`
   - `test_explicit_tags_force_category_and_strip_tag`
   - `test_multimodal_image_url_routes_to_vision_ui_ux`
   - `test_long_context_over_32k_tokens_routes_to_long_context_analysis`
   - `test_semantic_classification_routes_coding_vs_architecture_under_25ms`
3. **`tests/test_cascade.py`** :
   - `test_config_hot_reload_on_mtime_change`
   - `test_bedrock_locked_skips_aws_bedrock_completely`
   - `test_missing_env_api_key_skips_provider_cleanly`
   - `test_429_cooldown_quarantines_route_for_60_seconds`
   - `test_tools_payload_skips_incompatible_micro_models`
   - `test_opencode_v2_resolution_with_and_without_api_key`
   - `test_base_url_normalization_for_all_14_providers`
4. **`tests/test_streaming.py`** :
   - `test_stream_fallback_on_429_status_before_http_200`
   - `test_stream_fallback_on_empty_or_error_first_chunk_before_http_200`
   - `test_stream_returns_503_when_entire_cascade_fails`
   - `test_non_stream_retries_and_fallbacks_on_503`
   - `test_bedrock_converse_stream_translates_to_openai_sse_when_unlocked`
5. **`tests/test_dashboard_db.py`** :
   - `test_sqlite_wal_mode_enabled_and_tables_created`
   - `test_api_status_never_exposes_secret_api_keys`
   - `test_toggle_bedrock_persists_across_repository_reinit_and_blocks_calls`
   - `test_toggle_provider_disables_provider_in_cascade`
   - `test_upload_rules_validates_schema_and_rejects_invalid_json`
   - `test_api_logs_returns_last_50_entries_without_prompt_bodies`

> **Note de suivi** : ce document est la version canonique du plan (copie de travail `.opencode/plans/2026-11-14-master-plan.md`). Avancement : **Étapes 1 et 2 terminées** (squelette FastAPI + healthcheck ; classifieur hybride `fastembed`/ONNX avec règles déterministes, warmup au `lifespan`, 41 tests verts, latences mesurées : 0,007 ms déterministe et 5,6 ms sémantique). Les étapes 3 à 6 restent à implémenter.
