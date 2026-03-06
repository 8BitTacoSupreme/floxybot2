"""ChromaDB local vector store for Co-Pilot offline canon search."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

# Suppress ChromaDB posthog telemetry errors before importing chromadb
try:
    import posthog
    posthog.capture = lambda *args, **kwargs: None
except ImportError:
    pass

import chromadb
import chromadb.config

logger = logging.getLogger(__name__)


class ChromaStore:
    """Local ChromaDB wrapper for canon vector search."""

    def __init__(self, persist_dir: str | Path | None = None):
        chroma_settings = chromadb.config.Settings(anonymized_telemetry=False)
        if persist_dir is None:
            # Ephemeral (in-memory) for testing
            self._client = chromadb.Client(chroma_settings)
        else:
            self._client = chromadb.PersistentClient(
                path=str(persist_dir), settings=chroma_settings
            )
        self._collection = self._client.get_or_create_collection(
            name="canon",
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        """Add or update canon chunks in the collection."""
        self._collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

    def query(self, text: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Query the canon collection by text similarity.

        Returns list of {id, document, metadata, distance}.
        """
        results = self._collection.query(
            query_texts=[text],
            n_results=min(top_k, self.count() or 1),
        )

        items = []
        if results and results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                item = {
                    "id": doc_id,
                    "document": results["documents"][0][i] if results["documents"] else "",
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                }
                if results.get("distances"):
                    item["distance"] = results["distances"][0][i]
                items.append(item)
        return items

    def count(self) -> int:
        """Return the number of documents in the collection."""
        return self._collection.count()

    def clear(self) -> None:
        """Delete all documents from the collection."""
        self._client.delete_collection("canon")
        self._collection = self._client.get_or_create_collection(
            name="canon",
            metadata={"hnsw:space": "cosine"},
        )
