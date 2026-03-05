"""Voyage AI embedding client for canon indexing."""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Max batch size for Voyage API
DEFAULT_BATCH_SIZE = 64


class VoyageEmbedder:
    """Embeds text using Voyage AI API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ):
        if api_key is None:
            from src.config import settings
            api_key = settings.VOYAGE_API_KEY
        if model is None:
            from src.config import settings
            model = settings.EMBEDDING_MODEL

        import voyageai
        self._client = voyageai.Client(api_key=api_key)
        self._model = model
        self._batch_size = batch_size

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts, returning 1024-dim vectors."""
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            result = self._client.embed(batch, model=self._model)
            all_embeddings.extend(result.embeddings)
            logger.debug("Embedded batch %d-%d", i, i + len(batch))

        return all_embeddings

    def embed_single(self, text: str) -> list[float]:
        """Embed a single text."""
        result = self._client.embed([text], model=self._model)
        return result.embeddings[0]
