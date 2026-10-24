# file: app/rag/index.py
"""Hybrid retrieval index: Chroma (dense) + BM25 (sparse), fused with reciprocal-rank fusion."""
from __future__ import annotations

import hashlib
import math
import os
import re
import threading

import chromadb
from chromadb import Documents, EmbeddingFunction, Embeddings
from rank_bm25 import BM25Okapi

_TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")
STOPWORDS = set("a an the of to in on for and or is are be can i my me we you your it this that with by at from "
                "what which how when where do does did will would should could please".split())


def _stem(tok: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if len(tok) > len(suffix) + 2 and tok.endswith(suffix):
            return tok[: -len(suffix)]
    return tok


def tokenize(text: str) -> list[str]:
    """Lower-case word tokens, stopwords removed, light suffix stemming (returned/returns -> return)."""
    return [_stem(t) for t in _TOKEN.findall(text.lower()) if t not in STOPWORDS]


class HashEmbedding(EmbeddingFunction):
    """Deterministic bag-of-words hashing embedder (offline tests, MOCK runs)."""

    def __init__(self, dim: int = 256):
        self.dim = dim

    def __call__(self, input: Documents) -> Embeddings:
        out = []
        for text in input:
            v = [0.0] * self.dim
            for tok in tokenize(text):
                h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
                v[h % self.dim] += 1.0 if (h >> 8) & 1 else -1.0
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / norm for x in v])
        return out

    @staticmethod
    def name() -> str:
        return "hash"

    def get_config(self) -> dict:
        return {"dim": self.dim}

    @staticmethod
    def build_from_config(config: dict) -> "HashEmbedding":
        return HashEmbedding(config.get("dim", 256))


def default_embedder():
    if os.getenv("EMBEDDINGS", "sentence-transformers") == "hash":
        return HashEmbedding()
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    return SentenceTransformerEmbeddingFunction(model_name=os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2"),
                                                normalize_embeddings=True)


class HybridIndex:
    def __init__(self, path: str | None = None, collection: str = "docs", embedder=None):
        self.embedder = embedder or default_embedder()
        model = "v1" if self.embedder.name() == "hash" else os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2")
        tag = re.sub(r"[^a-zA-Z0-9]+", "-", f"{self.embedder.name()}-{model}")  # new model = new collection
        self.client = chromadb.PersistentClient(path=path or os.getenv("CHROMA_DIR", "data/chroma"))
        self.col = self.client.get_or_create_collection(name=f"{collection}-{tag}"[:60].strip("-"),
                                                        embedding_function=self.embedder)
        self._bm25, self._docs, self._lock = None, [], threading.Lock()

    def upsert_chunks(self, chunks: list[dict]) -> int:
        for i in range(0, len(chunks), 128):
            batch = chunks[i:i + 128]
            self.col.upsert(ids=[c["chunk_id"] for c in batch], documents=[c["text"] for c in batch],
                            metadatas=[{k: v for k, v in c.items() if k not in ("chunk_id", "text") and v is not None}
                                       for c in batch])
        self._bm25 = None
        return len(chunks)

    def delete_doc(self, doc_id: str) -> None:
        self.col.delete(where={"doc_id": doc_id})
        self._bm25 = None

    def count(self) -> int:
        return self.col.count()

    def _ensure_bm25(self) -> None:
        with self._lock:
            if self._bm25 is None:
                got = self.col.get(include=["documents", "metadatas"])
                self._docs = list(zip(got["ids"], got["documents"], got["metadatas"], strict=True))
                self._bm25 = BM25Okapi([tokenize(d) or ["_"] for _, d, _ in self._docs]) if self._docs else None

    def search(self, query: str, k: int = 6, candidates: int = 24) -> list[dict]:
        n = self.count()
        if n == 0:
            return []
        q_tokens = set(tokenize(query))
        dense = self.col.query(query_texts=[query], n_results=min(candidates, n),
                               include=["documents", "metadatas", "distances"])
        fused: dict[str, dict] = {}
        for rank, (cid, doc, meta, dist) in enumerate(zip(dense["ids"][0], dense["documents"][0],
                                                          dense["metadatas"][0], dense["distances"][0], strict=True)):
            fused[cid] = {"chunk_id": cid, "text": doc, **meta, "distance": round(dist, 4), "dense_rank": rank,
                          "score": 1 / (60 + rank)}
        self._ensure_bm25()
        if self._bm25 is not None and q_tokens:
            scores = self._bm25.get_scores(list(q_tokens))
            order = sorted(range(len(scores)), key=lambda i: -scores[i])[:candidates]
            for rank, i in enumerate(order):
                cid, doc, meta = self._docs[i]
                if not q_tokens & set(tokenize(doc)):
                    continue
                hit = fused.setdefault(cid, {"chunk_id": cid, "text": doc, **meta, "score": 0.0})
                hit["bm25_rank"] = rank
                hit["score"] += 1 / (60 + rank)
        for hit in fused.values():
            hit["overlap"] = round(len(q_tokens & set(tokenize(hit["text"]))) / max(1, len(q_tokens)), 3)
            hit["score"] = round(hit["score"], 5)
        return sorted(fused.values(), key=lambda h: -h["score"])[: max(k, candidates)]


_INDEX: HybridIndex | None = None


def get_index() -> HybridIndex:
    global _INDEX
    if _INDEX is None:
        _INDEX = HybridIndex()
    return _INDEX


def reset_index() -> None:
    global _INDEX
    _INDEX = None
