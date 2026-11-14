"""Embeddings through Ollama (Nomic Embed Text by default), with batching."""
from __future__ import annotations

import requests

from app import config


def _embed_batch_request(texts: list[str]) -> list[list[float]] | None:
    """One round-trip for many texts using Ollama's /api/embed. Returns None if it failed."""
    try:
        r = requests.post(f"{config.OLLAMA_URL}/api/embed", json={"model": config.EMBED_MODEL, "input": texts}, timeout=300)
        r.raise_for_status()
        vectors = r.json().get("embeddings") or []
        if len(vectors) == len(texts):
            return [[float(v) for v in vec] for vec in vectors]
    except (requests.RequestException, ValueError):
        pass
    return None


def _embed_single_legacy(text: str) -> list[float]:
    """Older Ollama versions only expose /api/embeddings (singular)."""
    try:
        r = requests.post(f"{config.OLLAMA_URL}/api/embeddings", json={"model": config.EMBED_MODEL, "prompt": text}, timeout=180)
        r.raise_for_status()
        return [float(v) for v in r.json().get("embedding", [])]
    except (requests.RequestException, ValueError):
        return []


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed *texts*, returning one vector per input (an empty list marks a text that failed to embed)."""
    results: list[list[float]] = []
    size = max(1, config.EMBED_BATCH_SIZE)
    for i in range(0, len(texts), size):
        batch = texts[i:i + size]
        vectors = _embed_batch_request(batch)
        if vectors is None:
            vectors = [_embed_single_legacy(t) if t.strip() else [] for t in batch]
        results.extend(vectors)
    return results


def embed(text: str) -> list[float]:
    if not text.strip():
        return []
    return embed_batch([text])[0]
