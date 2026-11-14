from __future__ import annotations

import fitz
from PIL import Image

from app import config
from app.services import extraction


def test_scanned_pdf_ocr_runs_only_for_sparse_pages(tmp_path, monkeypatch):
    pdf_path = tmp_path / "scanned.pdf"
    pdf = fitz.open()
    page1 = pdf.new_page()
    page1.insert_text((72, 72), "This is a normal text page with enough searchable content.")
    pdf.new_page()  # image-only page
    pdf.save(pdf_path)
    pdf.close()

    monkeypatch.setattr(config, "OCR_ENABLED", True)
    monkeypatch.setattr(config, "OCR_MIN_PAGE_CHARS", 30)
    monkeypatch.setattr(extraction, "_ocr_image", lambda image: "Recognized scanned document text.")

    result = extraction.extract_document(pdf_path)

    assert result.page_count == 2
    assert result.ocr_used is True
    assert result.ocr_pages == (2,)
    assert "[Page 1]" in result.text
    assert "normal text page" in result.text
    assert "[Page 2]" in result.text
    assert "Recognized scanned document text." in result.text


def test_image_document_uses_ocr(tmp_path, monkeypatch):
    image_path = tmp_path / "receipt.png"
    Image.new("RGB", (300, 120), "white").save(image_path)

    monkeypatch.setattr(config, "OCR_ENABLED", True)
    monkeypatch.setattr(extraction, "_ocr_image", lambda image: "Receipt total: 1250 rupees")

    result = extraction.extract_document(image_path)

    assert result.text == "Receipt total: 1250 rupees"
    assert result.page_count == 1
    assert result.ocr_used is True
    assert result.ocr_pages == (1,)


def test_text_pdf_does_not_call_ocr(tmp_path, monkeypatch):
    pdf_path = tmp_path / "text.pdf"
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "A searchable PDF page containing more than thirty useful characters.")
    pdf.save(pdf_path)
    pdf.close()

    monkeypatch.setattr(config, "OCR_ENABLED", True)
    monkeypatch.setattr(config, "OCR_MIN_PAGE_CHARS", 30)

    def should_not_run(_image):
        raise AssertionError("OCR should not run for a text-based PDF page.")

    monkeypatch.setattr(extraction, "_ocr_image", should_not_run)
    result = extraction.extract_document(pdf_path)

    assert result.page_count == 1
    assert result.ocr_used is False
    assert result.ocr_pages == ()
    assert "searchable PDF page" in result.text


def test_ocr_can_be_disabled_for_images(tmp_path, monkeypatch):
    image_path = tmp_path / "receipt.png"
    Image.new("RGB", (100, 100), "white").save(image_path)
    monkeypatch.setattr(config, "OCR_ENABLED", False)

    result = extraction.extract_document(image_path)

    assert result.text == ""
    assert result.ocr_used is False
