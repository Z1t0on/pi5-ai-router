Voici le plan d'architecture complet et prêt à exécuter pour ton agent, conçu spécifiquement pour déployer un routeur intelligent autonome sur ton Raspberry Pi 5 (8 Go) piloté directement par ton fichier routing_rules.v2.json.

1. 🎯 Modèle Recommandé pour cette étape

Utilise DeepSeek V4.1 Flash ou Kimi K3.1 Pro (en direct dans OpenCode) pour générer tout le projet dans un dossier dédié sur ton PC Windows (par exemple C:\Users\TonNom\Projets\pi5-ai-router\). Une fois créé et testé localement, il n'y aura plus qu'à copier ce dossier sur le Raspberry Pi 5 et lancer une seule commande docker compose up -d.

2. 💡 Explication Simplifiée (pour Olivier)

• Un seul cerveau sur ton Pi 5 : Ton Raspberry Pi va héberger une petite application autonome (en Docker, donc zéro conflit Python) qui lit directement ton fichier routing_rules.v2.json issu de ton Notebook Gemini.
• Classification intelligente en < 20 ms : Avant de transmettre ta requête, le Pi analyse en une fraction de seconde :
	1. La structure (présence d'une image → vision_ui_ux ; gros volume de code > 30 000 tokens → long_context_analysis).
	2. L'intention via un micro-modèle sémantique local (all-MiniLM-L6-v2 en ONNX, seulement 80 Mo de RAM, zéro latence) pour orienter vers planning_architecture, reasoning_deep_debug ou general_coding_refactoring.
• Bascule automatique & protection Bedrock : Il suit exactement la cascade primary → fallback_1 → fallback_2 de ton JSON dès qu'un fournisseur renvoie une erreur 429 ou 5xx, et dispose d'un interrupteur physique/web « Verrou Bedrock » pour bloquer à 100 % toute dépense sur tes 200 $ tant que tu le décides.
• Interface graphique intégrée (http://raspberrypi.local:4000) : Une page web sombre accessible depuis Thorium sur ton PC pour voir en direct quel modèle a répondu, mettre à jour ton routing_rules.v2.json en un clic (glisser-déposer) et couper/activer n'importe quel fournisseur.

3. 📋 Prompt d'Exécution (à copier-coller à ton agent dans un nouveau dossier projet pi5-ai-router)

Agis en tant qu'Architecte Logiciel Senior et Ingénieur DevOps spécialisé Linux/ARM64 (Raspberry Pi 5), Windows Docker Desktop et Python FastAPI.
Construis un routeur d'IA intelligent, autonome et conteneurisé (Docker multi-arch x86_64/ARM64) conçu pour tourner 24h/24 sur un Raspberry Pi 5 (8 Go RAM) et piloté dynamiquement par notre fichier de règles `routing_rules.v2.json`.

### OBJECTIF DU PROJET
Exposer une API 100 % compatible OpenAI (`POST /v1/chat/completions`, `GET /v1/models`, `GET /health`) sur le port `4000` du réseau local afin qu'OpenCode et Zed puissent utiliser un modèle virtuel unique (`smart-router`) qui classe automatiquement chaque requête en moins de 25 ms et applique les cascades de secours définies dans `routing_rules.v2.json`.

### ARBORESCENCE À CRÉER
Crée la structure suivante à la racine du projet :
pi5-ai-router/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
├── config/
│   └── routing_rules.v2.json        # Copie de notre fichier de règles maître
├── app/
│   ├── main.py                      # Serveur FastAPI + routes compatibles OpenAI + API Dashboard
│   ├── router_engine.py             # Moteur d'exécution, retries, fallbacks sur codes 429/500/502/503/504
│   ├── classifier.py                # Classifieur hybride ultra-rapide (<25ms) : règles structurelles + embeddings ONNX
│   ├── provider_adapters.py         # Traduction unifiée vers les 16 providers (OpenAI-compat, Gemini, AWS Bedrock)
│   └── static/
│       └── index.html               # Dashboard web sombre (monitoring live, verrou Bedrock, upload JSON)
├── tests/
│   └── test_router.py               # Suite de tests unitaires (classification, verrou Bedrock, fallback)
└── README.md                        # Guide de test sur Windows 11 et déploiement sur Raspberry Pi 5

### SPÉCIFICATIONS TECHNIQUES DÉTAILLÉES

1. **Classifieur Intelligent (`app/classifier.py`) — Latence cible < 25 ms** :
   - **Étape A (Règles déterministes prioritaires — < 1 ms)** :
     * Si le payload contient une image (`image_url` ou contenu multimodal) -> route vers `vision_ui_ux`.
     * Si la taille estimée du contexte dépasse `32 000` tokens (environ `len(text) // 4`) -> route vers `long_context_analysis`.
     * Si le prompt utilisateur commence par un tag explicite (`#plan`, `#debug`, `#code`, `#fast`, `#pro`) -> force la catégorie correspondante (`planning_architecture`, `reasoning_deep_debug`, `general_coding_refactoring`, `realtime_autocomplete`, `planning_architecture`) et nettoie le tag du message avant l'envoi au modèle.
   - **Étape B (Classifieur sémantique léger ONNX/FastEmbed — < 20 ms)** :
     * Utilise `fastembed` (`BAAI/bge-small-en-v1.5` ou `sentence-transformers/all-MiniLM-L6-v2` quantifié ONNX, compatible x86_64 et ARM64 sans PyTorch) pour comparer l'intention du dernier message utilisateur aux descriptions/exemples des catégories de `task_routing_matrix` (`planning_architecture`, `general_coding_refactoring`, `realtime_autocomplete`, `reasoning_deep_debug`, `high_throughput_batch`).
     * Pré-télécharge le modèle ONNX pendant le `docker build` pour un démarrage instantané hors-ligne.

2. **Moteur de Routage & Adaptateurs (`app/router_engine.py` & `app/provider_adapters.py`)** :
   - Charge `config/routing_rules.v2.json` à chaud (détection automatique via `os.path.getmtime` ou rechargement via l'API du dashboard).
   - Mappe proprement chaque fournisseur de `providers` vers son endpoint officiel :
     * `google_ai_studio` : `https://googleapis.com` (avec header `Authorization: Bearer {GEMINI_API_KEY}`).
     * `cloudflare` : `https://cloudflare.com{CLOUDFLARE_ACCOUNT_ID}/ai/v1/chat/completions` (avec `{CLOUDFLARE_API_TOKEN}`).
     * `openrouter` : `https://openrouter.ai`
     * `groq` : `https://groq.com`
     * `deepseek_api` : `https://deepseek.com`
     * `inception_ai` : `https://inceptionlabs.ai`
     * `kilo_code` : `https://kilocode.ai` (ou variable `KILO_BASE_URL` configurable dans `.env`)
     * `llm7_io` : `https://llm7.io`
     * `openai_api` : `https://openai.com`
     * `qwen_dashscope` : `https://aliyuncs.com`
     * `sambanova` : `https://sambanova.ai`
     * `siliconflow` : `https://siliconflow.com`
     * `z_ai` : `https://z.ai`
     * `cohere` : `https://cohere.ai`
     * `aws_bedrock` : via `boto3` (`bedrock-runtime` `converse` / `converse_stream`) avec support du Prompt Caching et traduction vers le format SSE OpenAI.
     * `opencode_v2` : comme il s'agit d'un alias interne sans clé API externe directe, remplace-le automatiquement par l'équivalent gratuit disponible (`groq` / `siliconflow` / `google_ai_studio` / `cloudflare`) dont la clé est configurée dans `.env`.
   - **Gestion critique du Streaming SSE (`stream: true`)** :
     * Avant de renvoyer un statut HTTP 200 au client (OpenCode/Zed), ouvre le flux `httpx` vers le provider et attend la réception du premier chunk valide. Si le provider renvoie une erreur HTTP (`429`, `500`, `502`, `503`, `504`) ou timeout avant le premier octet, ferme proprement la connexion et bascule silencieusement sur `fallback_1` puis `fallback_2`.
   - **Sécurité anti-dépense (`BEDROCK_LOCKED=true` par défaut)** :
     * Tant que `BEDROCK_LOCKED` est actif (dans `.env` ou via le bouton du dashboard), toute route pointant vers `aws_bedrock` est ignorée et remplacée par le fallback gratuit suivant afin de protéger à 100 % le crédit de 200 $.
   - **Gestion des erreurs, Quotas et Tool Calling** :
     * Applique `global_policy.auto_fallback_on_status_codes` (`429, 500, 502, 503, 504`), `max_retries_per_route` et `retry_delay_ms`.
     * Si la requête contient `tools` / `tool_calls`, saute automatiquement les micro-modèles incompatibles (`llama-3.2-3b`, `llama-prompt-guard`, `mercury-edit`).
     * Gère un cooldown temporaire en mémoire (60s) sur un couple `(provider, model)` ayant renvoyé une erreur `429`.

3. **Dashboard Web Local (`app/static/index.html`)** :
   - Interface web moderne en mode sombre (Tailwind CSS via CDN) accessible sur `http://localhost:4000/` ou `http://<IP_DU_PI>:4000/` permettant sans ligne de commande de :
     * Basculer l'interrupteur **« Verrou de sécurité AWS Bedrock (200 $) »** (ON/OFF en temps réel).
     * Activer/désactiver individuellement chacun des 16 fournisseurs et voir si sa clé `.env` est détectée (badge vert `Clé OK` / gris `Absente`, sans jamais exposer la clé).
     * Mettre à jour `routing_rules.v2.json` par simple glisser-déposer (avec validation de schéma JSON avant écrasement).
     * Visualiser le journal des 50 dernières requêtes depuis SQLite (heure, catégorie détectée, fournisseur/modèle utilisé, latence ms, statut HTTP ou bascule effectuée).

4. **Conteneurisation Multi-Arch (`Dockerfile` & `docker-compose.yml`)** :
   - Base `python:3.11-slim` compatible nativement `linux/amd64` (Windows Docker Desktop) et `linux/arm64` (Raspberry Pi 5).
   - Configuration `restart: unless-stopped`, montage des volumes `./config:/app/config` et `./data:/app/data` (base SQLite légère pour l'historique des logs).
   - Fichier `.env.example` listant proprement toutes les variables `auth_env_var` extraites de `routing_rules.v2.json` + `CLOUDFLARE_ACCOUNT_ID` + `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_REGION` + `BEDROCK_LOCKED=true`.

### CONSIGNES D'EXÉCUTION
- Génère l'intégralité des fichiers propres, commentés et fonctionnels.
- Exécute `pytest` pour valider le chargement de `routing_rules.v2.json`, la classification d'une requête texte/image/gros contexte/tag, la simulation d'un fallback sur erreur 429 et le verrouillage de Bedrock.
- Termine par un résumé clair en 3 étapes pour tester sur Windows 11 puis déployer sur le Raspberry Pi 5.

