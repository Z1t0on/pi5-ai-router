# Mise à jour : .opencode/skills/routing-rules-schema/SKILL.md

---name: routing-rules-schema
description: Schéma exact de config/routing_rules.json, résolution des 14 providers actifs, gestion des tags (#plan, #debug) et des cooldowns 429.---
# Schéma de `config/routing_rules.json`
- **`global_policy`**:
  - `auto_fallback_on_status_codes`: `[429, 500, 502, 503, 504]`
  - `max_retries_per_route`: `1`
  - `retry_delay_ms`: `200`
  - `cooldown_429_seconds`: `60`
- **`task_routing_matrix`**: 7 catégories actives (`planning_architecture`, `general_coding_refactoring`, `realtime_autocomplete`, `long_context_analysis`, `reasoning_deep_debug`, `vision_ui_ux`, `high_throughput_batch`). Chaque catégorie définit `primary`, `fallback_1` et `fallback_2` avec `{"provider": "...", "model": "..."}`.
- **`providers`**: Chaque entrée expose `auth_env_var`, `base_url` et `top_3_models`. Le moteur doit toujours utiliser `base_url` extrait dynamiquement du JSON si présent pour éviter les endpoints codés en dur.

# Endpoints Officiels Compatibles OpenAI (`app/provider_adapters.py`)
- `opencode_v2` / `opencode`: `https://opencode.ai` (`OPENCODE_API_KEY`) -> Permet d'appeler directement depuis le Pi 5 tous les modèles gratuits configurés de votre console (`deepseek-v4.1-flash-free`, `glm-5.3-flash-free`, `nemotron-3-ultra-free`, `nemotron-3.5-super-vl-free`, `longcat-2.5-preview-free`).
- `z_ai` / `zai`: `https://z.ai` (`ZAI_API_KEY`)
- `nvidia`: `https://nvidia.com` (`NVIDIA_API_KEY`)
- `cerebras`: `https://cerebras.ai` (`CEREBRAS_API_KEY`)
- `groq`: `https://groq.com` (`GROQ_API_KEY`)
- `openrouter`: `https://openrouter.ai` (`OPENROUTER_API_KEY`)
- `google_ai_studio`: `https://generativelanguage.googleapis.com/v1beta/openai/chat/completions` (`GEMINI_API_KEY`)
- `mistral`: `https://mistral.ai` (`MISTRAL_API_KEY`)
- `deepseek_api`: `https://deepseek.com` (`DEEPSEEK_API_KEY`)
- `cloudflare`: `https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/v1/chat/completions` (`CLOUDFLARE_API_TOKEN`)
- `sambanova`: `https://sambanova.ai` (`SAMBANOVA_API_KEY`)
- `cohere`: `https://cohere.ai` (`COHERE_API_KEY`)
- `kilo_code`: Lira la variable dynamique `KILO_BASE_URL` (configurée sur `https://api.kilo.ai/api/gateway`) du fichier `.env` (`KILO_API_KEY`)
- `aws_bedrock`: `https://bedrock-mantle.{AWS_REGION}.api.aws/v1/chat/completions` avec en-tête `Authorization: Bearer {AWS_BEDROCK_API_KEY}`. Reste strictement bloqué et ignoré par le routeur tant que `BEDROCK_LOCKED=true`.
# Règles Métier Critiques1. **Tags explicites de forçage** : Le routeur doit intercepter le dernier message utilisateur. S'il commence par un tag, forcer instantanément la catégorie associée et nettoyer le tag du texte avant l'envoi :
   - `#plan` ou `#pro` -> Force `planning_architecture`
   - `#debug` -> Force `reasoning_deep_debug`
   - `#code` -> Force `general_coding_refactoring`
   - `#fast` -> Force `realtime_autocomplete`
2. **Incompatibilité Tool Calling** : Si le payload de la requête contient une clé `tools` ou `tool_calls`, sauter automatiquement les modèles légers incompatibles avec les appels de fonctions (comme `@cf/meta/llama-3.2-3b-instruct`) et passer directement au fallback.
3. **Mise en quarantaine (Cooldown 429)** : Dès qu'une route `(provider, model)` retourne un statut HTTP `429`, elle doit être placée dans un dictionnaire de cooldown en mémoire pendant 60 secondes. Pendant cette minute, le routeur l'ignore et bascule instantanément sur le fallback sans perdre de temps.


