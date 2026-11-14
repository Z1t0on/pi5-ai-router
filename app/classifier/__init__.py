"""Classifieur hybride (règles déterministes + embeddings FastEmbed/ONNX)."""

from app.classifier.hybrid import TaskClassifier
from app.classifier.semantic import SemanticClassifier

__all__ = ["TaskClassifier", "SemanticClassifier"]
