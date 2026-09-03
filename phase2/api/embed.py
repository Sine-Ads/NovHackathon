"""Local embeddings via fastembed (ONNX Runtime).

This is deliberately not sentence-transformers. They are different libraries on
different runtimes and their vectors are not interchangeable — switching means a
full re-embed. What fastembed buys is a ~120 MB install instead of ~1.2 GB, and
a much faster cold start, while keeping embeddings local: no embedding API, no
network at query time.

BGE models are trained asymmetrically, so queries and passages go through
different entry points (``query_embed`` prefixes the query internally). Using
``embed`` for both measurably degrades retrieval.

At 1,399 chunks x 384 dimensions the whole index is 2.1 MB, so the query path is
a single numpy matrix multiply. No FAISS, no vector database.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from typing import Iterable, Optional

import numpy as np

from api.config import EMBED_CACHE_DIR, EMBED_DIM, EMBED_MODEL

# bge-small truncates at 512 tokens (~2,000 characters). Feeding it the full
# 8,000-character chunk changes no output and only inflates tokenizer memory.
# The untruncated text still goes to FTS5 and to the LLM; only the embedding
# input is capped here.
EMBED_MAX_CHARS = 2_000

# fastembed defaults to unbounded ONNX threads and forked worker processes, each
# holding its own copy of the model. On this machine (14 GB, no swap) that OOM
# killed the indexer at 4.1 GB RSS. Both limits below are deliberate.
ONNX_THREADS = int(os.getenv("PHASE2_EMBED_THREADS", "4"))
EMBED_BATCH_SIZE = int(os.getenv("PHASE2_EMBED_BATCH", "16"))

_model = None
_model_lock = threading.Lock()


def get_model():
    """Load the ONNX model once, on first use.

    First call downloads weights (~65 MB) into ``EMBED_CACHE_DIR``. Warm this
    before a demo rather than paying for it on stage.

    Note the name is what fastembed calls the model; the artefact it actually
    fetches is Qdrant's quantised ONNX repackaging, ``qdrant/bge-small-en-v1.5-onnx-q``.
    """
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from fastembed import TextEmbedding

                EMBED_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                _model = TextEmbedding(
                    model_name=EMBED_MODEL,
                    threads=ONNX_THREADS,
                    cache_dir=str(EMBED_CACHE_DIR),
                )
    return _model


def embed_passages(texts: Iterable[str]) -> np.ndarray:
    """Embed documents. Returns an L2-normalised (n, dim) float32 array.

    ``parallel=1`` keeps this in-process: forked workers would each reload the
    model, which is what exhausted memory before.
    """
    batch = [t[:EMBED_MAX_CHARS] for t in texts]
    if not batch:
        return np.zeros((0, EMBED_DIM), dtype=np.float32)
    vectors = list(
        get_model().passage_embed(batch, batch_size=EMBED_BATCH_SIZE, parallel=1)
    )
    return _normalize(np.asarray(vectors, dtype=np.float32))


def embed_query(text: str) -> np.ndarray:
    """Embed a search query. Returns an L2-normalised (dim,) float32 vector."""
    vectors = list(get_model().query_embed([text[:EMBED_MAX_CHARS]], parallel=1))
    return _normalize(np.asarray(vectors, dtype=np.float32))[0]


def _normalize(matrix: np.ndarray) -> np.ndarray:
    """L2-normalise rows so cosine similarity is a plain dot product."""
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


class VectorIndex:
    """The whole embedding table held in memory as one matrix.

    Loaded once at API startup. ``search`` is a single matrix multiply against
    ~1,400 rows, which is microseconds — the reason no vector store is needed.
    """

    def __init__(self, chunk_ids: list[str], item_ids: list[str], matrix: np.ndarray):
        self.chunk_ids = chunk_ids
        self.item_ids = item_ids
        self.matrix = matrix
        self._row_by_chunk = {cid: i for i, cid in enumerate(chunk_ids)}

    @classmethod
    def load(cls, conn: sqlite3.Connection, model: Optional[str] = None) -> "VectorIndex":
        model = model or EMBED_MODEL
        rows = conn.execute(
            "SELECT chunk_id, item_id, vec FROM embedding WHERE model = ? ORDER BY chunk_id",
            (model,),
        ).fetchall()
        if not rows:
            return cls([], [], np.zeros((0, EMBED_DIM), dtype=np.float32))
        chunk_ids = [r["chunk_id"] for r in rows]
        item_ids = [r["item_id"] for r in rows]
        matrix = np.vstack(
            [np.frombuffer(r["vec"], dtype=np.float32) for r in rows]
        ).astype(np.float32)
        return cls(chunk_ids, item_ids, matrix)

    def __len__(self) -> int:
        return len(self.chunk_ids)

    def search(self, query_vec: np.ndarray, limit: int = 50) -> list[tuple[str, float]]:
        """Top-``limit`` (chunk_id, cosine) pairs, best first."""
        if not len(self):
            return []
        scores = self.matrix @ query_vec
        top = np.argsort(-scores)[:limit]
        return [(self.chunk_ids[i], float(scores[i])) for i in top]

    def similar_to_item(
        self, item_id: str, limit: int = 6
    ) -> list[tuple[str, float]]:
        """Top-``limit`` (chunk_id, cosine) pairs excluding the item's own chunks."""
        rows = [i for i, iid in enumerate(self.item_ids) if iid == item_id]
        if not rows or not len(self):
            return []
        # An item's own chunks are its nearest neighbours by definition, so the
        # centroid is taken over them and they are then masked out.
        centroid = self.matrix[rows].mean(axis=0)
        norm = np.linalg.norm(centroid)
        if norm:
            centroid = centroid / norm
        scores = self.matrix @ centroid
        scores[rows] = -np.inf
        top = np.argsort(-scores)[:limit]
        return [
            (self.chunk_ids[i], float(scores[i]))
            for i in top
            if np.isfinite(scores[i])
        ]
