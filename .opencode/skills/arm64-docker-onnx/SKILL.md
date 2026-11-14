---
name: arm64-docker-onnx
description: Optimisation Docker multi-architecture (Windows x86_64 + Raspberry Pi 5 ARM64) et pré-chargement FastEmbed ONNX.
---

# Contraintes Matérielles Raspberry Pi 5 (ARM64)
- **Zéro PyTorch**: Ne jamais installer `torch` ou `sentence-transformers`. Utiliser exclusivement `fastembed` qui repose sur `onnxruntime`.
- **Modèle sémantique**: Utiliser `BAAI/bge-small-en-v1.5` (~80 Mo RAM, latence < 15 ms sur Cortex-A76).
- **Pré-téléchargement dans le `Dockerfile`**:
  Ajouter l'étape suivante pour intégrer les poids ONNX dans l'image Docker et éviter tout téléchargement au démarrage :
  ```dockerfile
  ENV FASTEMBED_CACHE_PATH=/app/.cache/fastembed
  RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5')"
  ```
- **Volumes `docker-compose.yml`**: Monter uniquement `./config:/app/config` et `./data:/app/data` afin de préserver `/app/.cache/fastembed` intact dans le conteneur.
