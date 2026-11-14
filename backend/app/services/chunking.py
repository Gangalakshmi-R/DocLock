"""Text chunking with overlap. Pure Python (no I/O) so it is trivial to unit-test and benchmark."""
from __future__ import annotations

# Preferred split points, strongest first. (separator, how many characters of it stay in the chunk)
_BOUNDARIES = (("\n\n", 0), ("\n", 0), (". ", 1), ("? ", 1), ("! ", 1), (" ", 0))


def _best_boundary(text: str, lo: int, hi: int) -> int | None:
    """Latest natural break in text[lo:hi], preferring paragraph > line > sentence > word."""
    for sep, keep in _BOUNDARIES:
        idx = text.rfind(sep, lo, hi)
        if idx != -1:
            return idx + keep
    return None


def split_chunks(text: str, chunk_size: int = 1000, overlap: int = 150) -> list[tuple[str, int, int]]:
    """Split *text* into overlapping chunks.

    Returns (chunk_text, start_offset, end_offset) tuples where offsets index into the original text.
    Chunks end on a paragraph, line, sentence or word boundary when one exists in the back half of the
    window, so passages rarely stop mid-sentence.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if not 0 <= overlap < chunk_size:
        raise ValueError("overlap must be >= 0 and smaller than chunk_size")
    output: list[tuple[str, int, int]] = []
    if not text or not text.strip():
        return output

    n = len(text)
    start = 0
    while start < n:
        end = min(n, start + chunk_size)
        if end < n:
            boundary = _best_boundary(text, start + chunk_size // 2, end)
            if boundary is not None and boundary > start:
                end = boundary
        chunk = text[start:end].strip()
        if chunk:
            output.append((chunk, start, end))
        if end >= n:
            break
        start = max(start + 1, end - overlap)  # always make forward progress
    return output
