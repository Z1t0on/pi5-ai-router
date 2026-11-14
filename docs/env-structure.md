# Infrastructure & Variables d'Environnement — `pi5-ai-router`

## 1. Paramètres Réseau & Matériel (Raspberry Pi 5)
- **Hôte SSH** : `olivier@192.168.1.44` (alias mDNS : `olivier@ai-router.local`)
- **Architecture** : Debian 12 Bookworm 64-bit (`aarch64` / `linux/arm64`)
- **RAM disponible** : 8 Go (budget cible du conteneur : < 500 Mo)
- **Répertoire projet distant** : `~/pi5-ai-router`
- **Port exposé** : `4000`
  - **API OpenAI-compatible** : `http://192.168.1` (ou `http://ai-router.local`)
  - **Dashboard d'administration** : `http://192.168.1`

## 2. Sécurité Financière & Configuration Routeur
- `BEDROCK_LOCKED=true` (Verrou actif par défaut pour protéger le crédit AWS de 200 $)
- `ROUTER_PORT=4000`
- `RULES_FILE_PATH=/app/config/routing_rules.v2.json`
- `SQLITE_DB_PATH=/app/data/router_logs.db`
- `FASTEMBED_MODEL=BAAI/bge-small-en-v1.5`

## 3. Clés API des 16 Fournisseurs (`routing_rules.v2.json`)
*(Ne jamais stocker les vraies valeurs dans NotebookLM ou Git — uniquement dans `.env` sur le Pi 5)*

### Providers Principaux (Free Tier & Crédits)
- `GEMINI_API_KEY=` *(Google AI Studio)*
- `OPENROUTER_API_KEY=` *(OpenRouter Free Tier)*
- `GROQ_API_KEY=` *(Groq Cloud)*
- `DEEPSEEK_API_KEY=` *(DeepSeek Official API)*
- `CLOUDFLARE_API_TOKEN=` *(Cloudflare Workers AI)*
- `CLOUDFLARE_ACCOUNT_ID=` *(Requis pour construire l'URL Cloudflare)*

### Providers Secondaires & Haute Capacité
- `INCEPTION_API_KEY=` *(Inception AI - Mercury 3 / Edit 2)*
- `KILO_API_KEY=` *(Kilo Code)*
- `KILO_BASE_URL=https://kilocode.ai`
- `LLM7_API_KEY=` *(LLM7.io)*
- `OPENAI_API_KEY=` *(OpenAI API)*
- `DASHSCOPE_API_KEY=` *(Qwen / Alibaba Cloud DashScope)*
- `SAMBANOVA_API_KEY=` *(SambaNova Systems)*
- `SILICONFLOW_API_KEY=` *(SiliconFlow)*
- `ZAI_API_KEY=` *(Z.AI Models)*
- `COHERE_API_KEY=` *(Cohere API)*

### AWS Bedrock (Protégé par `BEDROCK_LOCKED=true`)
- `AWS_BEDROCK_API_KEY=` *(Si utilisation d'un proxy/gateway Bedrock)*
- `AWS_ACCESS_KEY_ID=` *(Identifiant IAM AWS standard pour boto3)*
- `AWS_SECRET_ACCESS_KEY=` *(Clé secrète IAM AWS pour boto3)*
- `AWS_REGION=us-east-1`

### Note sur `opencode_v2`
- `NATIVE_OPENCODE_SESSION=` *(Non requis sur le Pi 5 : le routeur redirige automatiquement `opencode_v2` vers le premier provider gratuit actif parmi `groq`, `siliconflow`, `google_ai_studio` ou `cloudflare`)*
