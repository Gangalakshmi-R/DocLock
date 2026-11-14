"""Text extraction: plain text is read directly, everything else goes through Apache Tika."""
from __future__ import annotations

import time
from pathlib import Path

import requests

from app import config


def extract_text(path: Path) -> str:
    if path.suffix.lower() in config.PLAIN_TEXT_EXTENSIONS:
        return path.read_bytes().decode("utf-8", errors="replace")

    data = path.read_bytes()
    last_error: Exception | None = None
    for attempt in range(4):  # Tika can still be starting up right after `docker compose up`
        try:
            response = requests.put(
                f"{config.TIKA_URL}/tika", data=data,
                headers={"Accept": "text/plain", "Content-Type": "application/octet-stream"}, timeout=180,
            )
            response.raise_for_status()
            return response.text or ""
        except requests.RequestException as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"Apache Tika extraction failed: {last_error}") from last_error
