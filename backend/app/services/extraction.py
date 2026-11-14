"""Document text extraction with automatic OCR fallback for scanned PDFs and images.

Text-based PDFs use their embedded text. Pages with too little embedded text are rendered
and passed to Tesseract. Raster images are OCRed directly. Office and other formats continue
to use Apache Tika. Page markers are retained in extracted text for RAG citations.
"""
from __future__ import annotations

import io
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

from app import config


@dataclass(frozen=True)
class ExtractionResult:
    text: str
    page_count: Optional[int] = None
    ocr_used: bool = False
    ocr_pages: tuple[int, ...] = ()


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif"}


def _tika_extract(path: Path) -> str:
    data = path.read_bytes()
    last_error: Exception | None = None
    for attempt in range(4):  # Tika can still be starting immediately after docker compose up
        try:
            response = requests.put(
                f"{config.TIKA_URL}/tika",
                data=data,
                headers={"Accept": "text/plain", "Content-Type": "application/octet-stream"},
                timeout=180,
            )
            response.raise_for_status()
            return response.text or ""
        except requests.RequestException as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"Apache Tika extraction failed: {last_error}") from last_error


def _ocr_image(image) -> str:
    """OCR a PIL image after conservative grayscale/contrast preprocessing."""
    if not config.OCR_ENABLED:
        return ""
    try:
        import pytesseract
        from PIL import ImageOps
    except ImportError as exc:  # fail clearly if a local non-Docker install omitted OCR extras
        raise RuntimeError("OCR dependencies are missing. Install backend/requirements.txt and Tesseract OCR.") from exc

    processed = ImageOps.grayscale(image)
    processed = ImageOps.autocontrast(processed)
    # Small phone screenshots/scans benefit from modest upscaling before OCR.
    if processed.width < 1400:
        scale = min(2.0, 1400 / max(processed.width, 1))
        processed = processed.resize((int(processed.width * scale), int(processed.height * scale)))
    try:
        return pytesseract.image_to_string(
            processed,
            lang=config.OCR_LANG,
            config="--oem 1 --psm 3",
            timeout=config.OCR_TIMEOUT_SECONDS,
        ).strip()
    except RuntimeError as exc:
        raise RuntimeError(f"Tesseract OCR failed: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"Tesseract OCR failed. Check installed language packs ({config.OCR_LANG}): {exc}") from exc


def _extract_pdf(path: Path) -> ExtractionResult:
    """Extract embedded page text and OCR only pages that appear to be scanned."""
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is missing. Rebuild the backend image to enable PDF OCR.") from exc

    page_texts: list[str] = []
    ocr_pages: list[int] = []
    try:
        pdf = fitz.open(path)
        try:
            page_count = len(pdf)
            for page_index in range(page_count):
                page = pdf.load_page(page_index)
                native_text = (page.get_text("text") or "").strip()
                # A few stray characters (e.g. page numbers) are not useful text extraction.
                useful_chars = sum(ch.isalnum() for ch in native_text)
                chosen_text = native_text
                if config.OCR_ENABLED and useful_chars < config.OCR_MIN_PAGE_CHARS:
                    pix = page.get_pixmap(dpi=config.OCR_DPI, alpha=False)
                    from PIL import Image
                    image = Image.open(io.BytesIO(pix.tobytes("png")))
                    recognized = _ocr_image(image)
                    if len(recognized.strip()) > len(native_text):
                        chosen_text = recognized.strip()
                        if chosen_text:
                            ocr_pages.append(page_index + 1)
                page_texts.append(f"[Page {page_index + 1}]\n{chosen_text}".rstrip())
        finally:
            pdf.close()
    except Exception as exc:
        # Preserve the existing Tika fallback for unusual, encrypted or malformed PDFs.
        try:
            fallback = _tika_extract(path)
            if fallback.strip():
                return ExtractionResult(fallback, None, False, ())
        except Exception:
            pass
        raise RuntimeError(f"PDF extraction failed: {exc}") from exc

    return ExtractionResult(
        text="\n\n".join(page_texts).strip(),
        page_count=page_count,
        ocr_used=bool(ocr_pages),
        ocr_pages=tuple(ocr_pages),
    )


def extract_document(path: Path) -> ExtractionResult:
    """Return extracted text plus OCR/page metadata for ingestion."""
    suffix = path.suffix.lower()
    if suffix in config.PLAIN_TEXT_EXTENSIONS:
        return ExtractionResult(path.read_bytes().decode("utf-8", errors="replace"))
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix in IMAGE_EXTENSIONS:
        if not config.OCR_ENABLED:
            return ExtractionResult("")
        try:
            from PIL import Image
            with Image.open(path) as image:
                text = _ocr_image(image)
            return ExtractionResult(text=text, page_count=1, ocr_used=bool(text.strip()),
                                    ocr_pages=(1,) if text.strip() else ())
        except Exception as exc:
            raise RuntimeError(f"Image OCR failed: {exc}") from exc
    return ExtractionResult(_tika_extract(path))


def extract_text(path: Path) -> str:
    """Backward-compatible text-only extraction API used by existing callers/tests."""
    return extract_document(path).text
