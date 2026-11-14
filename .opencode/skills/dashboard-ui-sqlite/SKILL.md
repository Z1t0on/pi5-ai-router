---
name: dashboard-ui-sqlite
description: Architecture de la base SQLite des logs et de l'interface web sombre (app/static/index.html) sans build frontend.
---

# Persistance SQLite (`./data/router_logs.db`)
- Utiliser `aiosqlite` ou `sqlite3` avec mode WAL (`PRAGMA journal_mode=WAL;`) pour éviter tout verrouillage lors des écritures concurrentes.
- Tables requises :
  - `request_logs` (`id`, `timestamp`, `category`, `provider`, `model`, `latency_ms`, `status_code`, `is_fallback`, `error_detail`)
  - `system_state` (`key TEXT PRIMARY KEY`, `value TEXT`) pour persister l'état de `bedrock_locked` et des providers désactivés manuellement.

# Dashboard Web (`app/static/index.html`)
- Fichier HTML unique autonome utilisant **Tailwind CSS via CDN** et **Vanilla JS (Fetch API)** — aucun processus Node.js/Vite requis sur le Raspberry Pi 5.
- Endpoints d'administration exposés par `app/main.py` :
  - `GET /api/status` : Retourne l'état du verrou Bedrock, la liste des 16 providers avec présence de clé `.env` (`has_key: bool`, jamais la valeur) et activation manuelle.
  - `POST /api/toggle-bedrock` : Active/désactive `bedrock_locked`.
  - `POST /api/toggle-provider/{provider_id}` : Active/désactive un fournisseur.
  - `POST /api/upload-rules` : Valide la structure JSON (`task_routing_matrix` et `providers` requis) et remplace `config/routing_rules.json`.
  - `GET /api/logs` : Retourne les 50 dernières requêtes.
