"""
rag.py — Retrieval-Augmented Generation module for Querly.

Pipeline:
  1. Upload PDF  -> extract text (PyMuPDF)  -> chunk (~500 words)
  2. Embed chunks (sentence-transformers all-MiniLM-L6-v2)
  3. Store chunks + embeddings in MongoDB (knowledge_base collection)
  4. At reply-time: embed the incoming email body, cosine-search top-3 chunks
"""

import fitz  # PyMuPDF
import asyncio
import numpy as np
from typing import List
from sentence_transformers import SentenceTransformer

from db import db  # reuse the shared motor client

# ── model (loaded once at module import, ~80 MB) ─────────────────────────────
_model = SentenceTransformer("all-MiniLM-L6-v2")

knowledge_collection = db.knowledge_base


# ── helpers ──────────────────────────────────────────────────────────────────

def _extract_text_from_pdf(file_bytes: bytes) -> str:
    """Return all text from a PDF given its raw bytes."""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages = [page.get_text() for page in doc]
    return "\n".join(pages)


def _chunk_text(text: str, chunk_words: int = 500) -> List[str]:
    """Split text into chunks of ~chunk_words words with no overlap."""
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_words):
        chunk = " ".join(words[i : i + chunk_words])
        if chunk.strip():
            chunks.append(chunk.strip())
    return chunks


def _embed(texts: List[str]) -> List[List[float]]:
    """Return L2-normalised float embeddings for a list of strings."""
    embeddings = _model.encode(texts, normalize_embeddings=True)
    return embeddings.tolist()


def _cosine_sim(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two already-normalised vectors."""
    a_arr = np.array(a, dtype=np.float32)
    b_arr = np.array(b, dtype=np.float32)
    return float(np.dot(a_arr, b_arr))


# ── public API ────────────────────────────────────────────────────────────────

async def ingest_pdf(uid: str, filename: str, file_bytes: bytes) -> int:
    """
    Extract, chunk, embed and store a PDF for a given user.
    Returns the number of chunks stored.
    """
    # Run CPU-bound work off the event-loop thread
    text = await asyncio.to_thread(_extract_text_from_pdf, file_bytes)
    chunks = await asyncio.to_thread(_chunk_text, text)

    if not chunks:
        return 0

    embeddings = await asyncio.to_thread(_embed, chunks)

    docs = [
        {
            "uid": uid,
            "source_filename": filename,
            "chunk_text": chunk,
            "embedding": emb,
        }
        for chunk, emb in zip(chunks, embeddings)
    ]

    await knowledge_collection.insert_many(docs)
    return len(docs)


async def search_knowledge_base(uid: str, query: str, top_k: int = 3) -> List[str]:
    """
    Embed *query*, retrieve all chunks for *uid*, rank by cosine similarity,
    and return the top-k chunk texts.

    Falls back to Python-side ranking (works with any MongoDB tier).
    """
    query_emb = await asyncio.to_thread(_embed, [query])
    query_vec = query_emb[0]

    # Fetch all chunks for this user
    cursor = knowledge_collection.find(
        {"uid": uid},
        {"chunk_text": 1, "embedding": 1, "_id": 0}
    )
    docs = await cursor.to_list(length=2000)

    if not docs:
        return []

    # Rank by cosine similarity
    scored = [
        (doc["chunk_text"], _cosine_sim(query_vec, doc["embedding"]))
        for doc in docs
        if doc.get("embedding")
    ]
    scored.sort(key=lambda x: x[1], reverse=True)

    return [text for text, _ in scored[:top_k]]
