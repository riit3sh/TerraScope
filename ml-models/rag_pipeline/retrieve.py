"""Parcel-scoped vector retrieval for the TerraScope RAG pipeline."""

from __future__ import annotations

from typing import Any

try:
    from .ingest import _collection, _model
except ImportError:  # pragma: no cover - supports `python retrieve.py` from this directory.
    from ingest import _collection, _model


def retrieve_context(query: str, parcel_id: str, k: int = 5) -> list[dict[str, Any]]:
    """Return the top-k chunks for a parcel, with source metadata attached."""
    if not query.strip():
        raise ValueError("query must not be empty.")
    if k <= 0:
        return []
    query_embedding = _model().encode([query], normalize_embeddings=True).tolist()
    result = _collection().query(
        query_embeddings=query_embedding,
        n_results=k,
        where={"parcel_id": parcel_id},
        include=["documents", "metadatas", "distances"],
    )
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    return [
        {
            "text": text,
            "metadata": metadata,
            "distance": distance,
        }
        for text, metadata, distance in zip(documents, metadatas, distances)
    ]
