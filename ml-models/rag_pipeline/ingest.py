"""Chunk, embed, and persist TerraScope sample documents in ChromaDB."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import chromadb
from sentence_transformers import SentenceTransformer


STORE_PATH = Path(__file__).with_name("chroma_store")
COLLECTION_NAME = "terrascope_documents"
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def chunk_text(text: str, chunk_size: int = 300, overlap: int = 50) -> list[str]:
    """Split text into approximate token windows using whitespace tokens."""
    if chunk_size <= overlap:
        raise ValueError("chunk_size must be greater than overlap.")
    tokens = text.split()
    step = chunk_size - overlap
    return [" ".join(tokens[start:start + chunk_size]) for start in range(0, len(tokens), step) if tokens[start:start + chunk_size]]


def _collection():
    client = chromadb.PersistentClient(path=str(STORE_PATH))
    return client.get_or_create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})


def _model() -> SentenceTransformer:
    return SentenceTransformer(EMBEDDING_MODEL_NAME)


def build_vector_index(documents: list[dict[str, Any]]) -> dict[str, Any]:
    """Build or upsert the persisted parcel-document vector index."""
    chunks: list[tuple[str, str, dict[str, str]]] = []
    for document_index, document in enumerate(documents):
        required = {"text", "source_type", "source_reference", "parcel_id"}
        missing = required - document.keys()
        if missing:
            raise ValueError(f"Document {document_index} is missing fields: {sorted(missing)}")
        for chunk_index, text in enumerate(chunk_text(str(document["text"]))):
            chunk_id_source = f"{document['parcel_id']}|{document['source_reference']}|{chunk_index}|{text}"
            chunk_id = hashlib.sha256(chunk_id_source.encode("utf-8")).hexdigest()
            metadata = {
                "source_type": str(document["source_type"]),
                "source_reference": str(document["source_reference"]),
                "parcel_id": str(document["parcel_id"]),
            }
            chunks.append((chunk_id, text, metadata))

    if not chunks:
        raise ValueError("At least one document chunk is required to build the index.")
    model = _model()
    embeddings = model.encode([chunk[1] for chunk in chunks], normalize_embeddings=True).tolist()
    collection = _collection()
    collection.upsert(
        ids=[chunk[0] for chunk in chunks],
        documents=[chunk[1] for chunk in chunks],
        metadatas=[chunk[2] for chunk in chunks],
        embeddings=embeddings,
    )
    return {"collection": COLLECTION_NAME, "chunk_count": len(chunks), "store_path": str(STORE_PATH)}

