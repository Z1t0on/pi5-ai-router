---
name: fastapi-sse-streaming
description: Pattern FastAPI pour le streaming SSE OpenAI avec bascule silencieuse avant le premier chunk et traduction AWS Bedrock.
---

# Bascule Transparente en Mode Streaming (`stream: true`)
Dans FastAPI, retourner un `StreamingResponse` envoie immédiatement les en-têtes HTTP `200 OK`. Si le fournisseur échoue dans le générateur asynchrone, le client reçoit une erreur coupée et aucun fallback n'est possible.

# Algorithme Obligatoire (`app/router_engine.py`)
1. Itérer sur la cascade résolue `[primary, fallback_1, fallback_2]`.
2. Ouvrir le flux avec `client.build_request("POST", url, ...)` puis `response = await client.send(request, stream=True)`.
3. Vérifier `response.status_code`:
   - Si dans `auto_fallback_on_status_codes`, exécuter `await response.aclose()`, enregistrer le cooldown si `429` et continuer la boucle.
4. Lire la première ligne non vide de `response.aiter_lines()` avant de créer le `StreamingResponse`. Si la connexion coupe ou renvoie un objet d'erreur JSON avant le premier token, fermer et passer au fallback.
5. Passer un générateur asynchrone qui émet cette première ligne puis consomme `response.aiter_lines()`, et ferme `response.aclose()` dans un bloc `finally:`.

# Adaptateur AWS Bedrock (`aws_bedrock`)
- Utiliser `boto3.client("bedrock-runtime", region_name=...)` avec `converse` et `converse_stream`.
- Transformer chaque événement `contentBlockDelta` en ligne SSE OpenAI :
  `data: {"id": "chatcmpl-bedrock", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": null}]}\n\n`
- Émettre `data: [DONE]\n\n` en fin de flux.
