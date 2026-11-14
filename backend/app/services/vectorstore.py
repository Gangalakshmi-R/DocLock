"""ChromaDB access over its v2 REST API. Every function degrades gracefully if Chroma is unreachable."""
from __future__ import annotations

from typing import Optional

import requests

from app import config

_BASE = "/api/v2/tenants/default_tenant/databases/default_database/collections"
_collection_id: Optional[str] = None


def _find_collection(base: str) -> Optional[str]:
    r = requests.get(base, timeout=10)
    r.raise_for_status()
    for collection in r.json():
        if collection.get("name") == config.CHROMA_COLLECTION:
            return collection["id"]
    return None


def collection_id() -> str:
    global _collection_id
    if _collection_id:
        return _collection_id
    base = f"{config.CHROMA_URL}{_BASE}"
    found = _find_collection(base)
    if not found:
        created = requests.post(base, json={"name": config.CHROMA_COLLECTION, "metadata": {"hnsw:space": "cosine"}}, timeout=15)
        if created.status_code == 409:  # created concurrently by another request
            found = _find_collection(base)
        else:
            created.raise_for_status()
            found = created.json()["id"]
    if not found:
        raise requests.RequestException("Could not resolve the Chroma collection")
    _collection_id = found
    return found


def upsert_batch(items: list[dict]) -> bool:
    """items: dicts with keys id, vector, text, document_id, filename, chunk_index."""
    items = [i for i in items if i.get("vector")]
    if not items:
        return False
    try:
        url = f"{config.CHROMA_URL}{_BASE}/{collection_id()}/upsert"
        body = {
            "ids": [i["id"] for i in items],
            "embeddings": [i["vector"] for i in items],
            "documents": [i["text"] for i in items],
            "metadatas": [{"documentId": i["document_id"], "filename": i["filename"], "chunkIndex": i["chunk_index"]} for i in items],
        }
        requests.post(url, json=body, timeout=60).raise_for_status()
        return True
    except requests.RequestException as exc:
        print(f"Chroma upsert warning: {exc}")
        return False


def query(vector: list[float], document_id: Optional[int], limit: int) -> list[str]:
    """Vector ids of the nearest passages, best first. Empty list if Chroma is unavailable."""
    if not vector:
        return []
    try:
        url = f"{config.CHROMA_URL}{_BASE}/{collection_id()}/query"
        body: dict = {"query_embeddings": [vector], "n_results": limit}
        if document_id is not None:
            body["where"] = {"documentId": {"$eq": document_id}}
        r = requests.post(url, json=body, timeout=30)
        r.raise_for_status()
        ids = r.json().get("ids") or []
        return [str(x) for x in (ids[0] if ids else [])]
    except requests.RequestException as exc:
        print(f"Chroma query warning: {exc}")
        return []


def delete(ids: list[str]) -> None:
    if not ids:
        return
    try:
        url = f"{config.CHROMA_URL}{_BASE}/{collection_id()}/delete"
        requests.post(url, json={"ids": ids}, timeout=30).raise_for_status()
    except requests.RequestException as exc:
        print(f"Chroma delete warning: {exc}")
