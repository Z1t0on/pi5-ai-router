# Configuration des Clients (OpenCode & Zed) vers `pi5-ai-router`

## 1. Configuration OpenCode (`~/.config/opencode/opencode.json`)
Permet à OpenCode d'utiliser votre Raspberry Pi 5 comme fournisseur compatible OpenAI avec le modèle virtuel `smart-router` (ainsi que des alias explicites par tag si souhaité).

```json
{
  "\$schema": "https://opencode.ai",
  "provider": {
    "pi5-router": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Raspberry Pi 5 AI Router",
      "options": {
        "baseURL": "http://192.168.1",
        "apiKey": "local-pi5-router"
      },
      "models": {
        "smart-router": {
          "name": "Smart Router (Auto-Classification)"
        }
      }
    }
  },
  "model": "pi5-router/smart-router"
}
```

### Utilisation des tags de forçage dans les prompts OpenCode
Si vous souhaitez contourner le classifieur sémantique ONNX pour une requête précise, commencez votre message par l'un des tags suivants :
- `#plan` → Force `planning_architecture`
- `#debug` → Force `reasoning_deep_debug`
- `#code` → Force `general_coding_refactoring`
- `#fast` → Force `realtime_autocomplete`
- `#pro` → Force `planning_architecture`

---

## 2. Configuration de l'éditeur Zed (`%APPDATA%\Zed\settings.json`)
Permet à l'assistant IA de Zed d'envoyer ses requêtes de chat et d'édition vers le Raspberry Pi 5 sur le réseau local.

```json
{
  "language_models": {
    "openai": {
      "api_url": "http://192.168.1",
      "available_models": [
        {
          "name": "smart-router",
          "display_name": "Pi 5 Smart Router",
          "max_tokens": 128000,
          "max_output_tokens": 8192
        }
      ]
    }
  },
  "assistant": {
    "version": "2",
    "default_model": {
      "provider": "openai",
      "model": "smart-router"
    }
  }
}
```
*(Note : Dans Zed, lors de la première connexion, entrez n'importe quelle valeur factice comme `local-pi5` lorsque l'éditeur demande une clé API OpenAI).*
