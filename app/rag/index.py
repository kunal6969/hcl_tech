"""
index.py — ChromaDB vector store interface for hospital policy documents (R1).

All policy and procedure documents are chunked and stored here.
The retrieve node calls search_documents() to find relevant chunks.

Metadata per chunk (for R2 citations and R4 conflict resolution):
  doc           — document filename or title
  section       — section name within the document
  version       — document version string
  effective_date — ISO date when document takes effect
  authority     — "government_regulation" | "clinical_guideline" | "hospital_policy"
  status        — "active" | "superseded"
  ingested_at   — ISO datetime when ingested (tie-breaker for conflict resolution)
"""
from __future__ import annotations

import hashlib
import os
from datetime import date
from pathlib import Path
from typing import Any

# ChromaDB persistent path
_CHROMA_DIR = Path(__file__).parents[2] / "data" / "chroma"
_COLLECTION_NAME = "hospital_policies"

# Embedding model (MiniLM is fast and fits on any laptop; hash mode for offline tests)
_EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
_USE_HASH_EMBEDDINGS = os.getenv("EMBEDDINGS", "").lower() == "hash"


def _hash_embed(text: str) -> list[float]:
    """
    Deterministic hash-based embedding for offline tests (EMBEDDINGS=hash).
    Returns a 384-dim float vector derived from the MD5 of the text.
    NOT for production — only for tests that must run without a model.
    """
    h = hashlib.md5(text.encode()).hexdigest()
    # Repeat 24-char hex to get 384 floats
    floats = []
    for i in range(0, len(h) * 16, len(h)):
        chunk = h[(i % len(h)):(i % len(h)) + 2]
        floats.append(int(chunk, 16) / 255.0)
        if len(floats) >= 384:
            break
    while len(floats) < 384:
        floats.append(0.0)
    return floats[:384]


def _get_hash_ef():
    """
    Build a ChromaDB EmbeddingFunction that uses hash embeddings.
    Must subclass chromadb.EmbeddingFunction[Documents] to get embed_query
    and other protocol methods required by chromadb 1.5.x.
    """
    import chromadb
    from chromadb import Documents, Embeddings

    class _HashEmbeddingFunction(chromadb.EmbeddingFunction[Documents]):
        """Hash-based embedding for offline tests (EMBEDDINGS=hash)."""

        def __init__(self) -> None:  # suppress deprecation warning about missing __init__
            pass

        @staticmethod
        def name() -> str:
            return "hash_embedding"

        def __call__(self, input: Documents) -> Embeddings:  # type: ignore[override]
            return [_hash_embed(text) for text in input]

    return _HashEmbeddingFunction()


def _get_client():
    """Return a persistent ChromaDB client."""
    import chromadb
    _CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(_CHROMA_DIR))


def _get_collection():
    """Return (or create) the hospital_policies ChromaDB collection."""
    client = _get_client()

    if _USE_HASH_EMBEDDINGS:
        ef = _get_hash_ef()
        return client.get_or_create_collection(
            _COLLECTION_NAME,
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
    else:
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        ef = SentenceTransformerEmbeddingFunction(model_name=_EMBEDDING_MODEL)
        return client.get_or_create_collection(
            _COLLECTION_NAME,
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )


def add_chunks(
    chunks: list[str],
    metadatas: list[dict[str, str]],
    doc_id_prefix: str,
) -> list[str]:
    """
    Add text chunks to the ChromaDB collection.

    Args:
        chunks: List of text strings (one per chunk).
        metadatas: List of metadata dicts (one per chunk).
                   Required keys: doc, section, version, effective_date, authority, status, ingested_at
        doc_id_prefix: Prefix for chunk IDs, e.g. "icu-visiting-policy".

    Returns:
        List of assigned chunk IDs.
    """
    collection = _get_collection()
    ids = [f"{doc_id_prefix}-chunk-{i}" for i in range(len(chunks))]

    # Upsert so re-ingesting the same doc updates rather than duplicates
    collection.upsert(
        ids=ids,
        documents=chunks,
        metadatas=metadatas,
    )
    return ids


def search_documents(
    query: str,
    n_results: int = 5,
    filters: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """
    Semantic search over hospital policy documents (R1).

    Automatically filters to:
      - status = "active" (unless overridden in filters)
      - effective_date <= today (only currently effective documents)

    Args:
        query: The user's question text.
        n_results: Number of chunks to return.
        filters: Additional ChromaDB where-filters.

    Returns:
        List of chunk dicts with keys:
          content, doc, section, version, effective_date, authority, status, ingested_at, distance
    """
    collection = _get_collection()

    # Build where-clause: always filter active docs
    where: dict[str, Any] = {"status": "active"}
    if filters:
        where.update(filters)

    today = date.today().isoformat()

    try:
        results = collection.query(
            query_texts=[query],
            n_results=min(n_results, max(collection.count(), 1)),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
    except Exception:
        return []

    chunks = []
    docs_list = results.get("documents", [[]])[0]
    metas_list = results.get("metadatas", [[]])[0]
    dists_list = results.get("distances", [[]])[0]

    for doc_text, meta, dist in zip(docs_list, metas_list, dists_list):
        # Filter by effective_date (only docs that are currently in effect)
        eff_date = meta.get("effective_date", "1900-01-01")
        if eff_date > today:
            continue  # not yet effective
        chunks.append({
            "content": doc_text,
            "doc": meta.get("doc", ""),
            "section": meta.get("section", ""),
            "version": meta.get("version", ""),
            "effective_date": eff_date,
            "authority": meta.get("authority", "hospital_policy"),
            "status": meta.get("status", "active"),
            "ingested_at": meta.get("ingested_at", ""),
            "distance": dist,
        })

    return chunks
