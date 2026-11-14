# Contexte & Architecture — `pi5-ai-router`

Ce dépôt contient le code d'un routeur d'IA autonome, compatible OpenAI (`POST /v1/chat/completions`), développé en Python 3.11+ / FastAPI et conteneurisé sous Docker multi-architecture (`linux/amd64` + `linux/arm64`) pour tourner 24h/24 sur un **Raspberry Pi 5 (Debian 12 ARM64, 8 Go RAM, IP `192.168.1.44`, port `4000`)**.

## Règles Architecturales Non-Négociables
1. **Source de vérité unique** : `config/routing_rules.json` pilote dynamiquement (avec rechargement à chaud via `os.path.getmtime`) les fournisseurs, les modèles autorisés et les cascades de secours. Ne code jamais de noms de modèles ou de routes en dur dans le code Python.
2. **Budget matériel Pi 5 (< 500 Mo RAM)** : L'utilisation de `torch` ou `sentence-transformers` est strictement interdite. Le classifieur sémantique (`app/classifier.py`) utilise exclusivement `fastembed` (`BAAI/bge-small-en-v1.5` en ONNX Runtime) pré-téléchargé lors du `docker build`.
3. **Verrou financier AWS Bedrock (`BEDROCK_LOCKED=true`)** : Tant que `BEDROCK_LOCKED` est actif (dans `.env` ou via le dashboard), 100 % des appels vers `aws_bedrock` doivent être bloqués et redirigés vers le fallback gratuit suivant afin de protéger le crédit de 200 $.
4. **Streaming SSE sans coupure (`stream: true`)** : Avant de renvoyer un statut HTTP `200 OK` au client (OpenCode ou Zed), le moteur (`app/router_engine.py`) doit vérifier le statut HTTP et le premier chunk du fournisseur distant. En cas d'erreur `429` ou `5xx`, le basculement sur `fallback_1` puis `fallback_2` s'opère silencieusement avant l'envoi des en-têtes.
5. **Asynchrone intégral** : Tous les appels HTTP sortants utilisent `httpx.AsyncClient` (jamais `requests`).

## Sécurité & Périmètre des Fichiers
- **Ne jamais lire, afficher ou logger les secrets de `.env`** dans les logs SQLite (`./data/router_logs.db`) ou les réponses HTTP.
- **Sanctuarisation des tests** : Ne jamais contourner ou supprimer un test dans `tests/` pour masquer un bug dans `app/`.
- **Déploiement distant** : Le déploiement sur le Raspberry Pi 5 s'effectue exclusivement via SSH/SCP non-interactif (`-o BatchMode=yes`) sur `olivier@192.168.1.44` dans `~/pi5-ai-router`.

## Skills du Projet Disponibles
Avant de coder ou concevoir une brique, charge le skill correspondant dans `.opencode/skills/` :
- `routing-rules-schema` : Schéma de `config/routing_rules.json`, endpoints des 15 providers, gestion des tags (`#plan`, `#debug`, `#code`, `#fast`, `#pro`) et cooldowns 429.
- `fastapi-sse-streaming` : Gestion du streaming SSE OpenAI avec bascule avant le premier token.
- `arm64-docker-onnx` : Optimisation Docker multi-arch et pré-chargement ONNX FastEmbed.
- `dashboard-ui-sqlite` : Schéma SQLite WAL et interface web sombre (`app/static/index.html`).
- `pi5-ssh-deploy` : Procédure de déploiement autonome via SSH/SCP sur `olivier@192.168.1.44`.
