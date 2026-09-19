from __future__ import annotations

import io
import os
import tempfile
from dataclasses import dataclass

from PIL import Image

from .article_numbers import extract_article_numbers, normalize_article_number
from .config import AppConfig

try:
    import pytesseract
except ImportError:  # pragma: no cover
    pytesseract = None

try:
    import pdf2image
except ImportError:  # pragma: no cover
    pdf2image = None

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None

try:
    from pyzbar.pyzbar import decode as decode_barcode
except ImportError:  # pragma: no cover
    decode_barcode = None


@dataclass(frozen=True, slots=True)
class OptionalFeatures:
    tesseract: bool
    pdf_images: bool
    pdf_text: bool
    barcode: bool


def optional_features() -> OptionalFeatures:
    return OptionalFeatures(
        tesseract=pytesseract is not None,
        pdf_images=pdf2image is not None,
        pdf_text=PdfReader is not None,
        barcode=decode_barcode is not None,
    )


class OcrService:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def _configure_tesseract(self) -> bool:
        if pytesseract is None:
            return False

        if self.config.tesseract_path and os.path.exists(self.config.tesseract_path):
            pytesseract.pytesseract.tesseract_cmd = self.config.tesseract_path

        if self.config.tessdata_path and os.path.isdir(self.config.tessdata_path):
            os.environ["TESSDATA_PREFIX"] = self.config.tessdata_path

        try:
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    def extract_from_image(self, image: Image.Image) -> str | None:
        if decode_barcode is not None:
            try:
                for code in decode_barcode(image):
                    candidate = normalize_article_number(
                        code.data.decode("utf-8", errors="ignore")
                    )
                    if candidate:
                        return candidate
            except Exception:
                pass

        if not self._configure_tesseract():
            return None

        try:
            gray = image.convert("L")
            text = pytesseract.image_to_string(
                gray,
                lang=self.config.ocr_language,
                config="--oem 3 --psm 6",
            )
            numbers = extract_article_numbers(text)
            return numbers[0] if numbers else None
        except Exception:
            return None

    def extract_pdf_text(self, pdf_bytes: bytes) -> str:
        native_text = self._extract_native_pdf_text(pdf_bytes)
        if native_text.strip():
            return native_text

        if pdf2image is None or not self._configure_tesseract():
            return ""

        temp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp:
                temp.write(pdf_bytes)
                temp_path = temp.name

            poppler = (
                self.config.poppler_path
                if self.config.poppler_path and os.path.isdir(self.config.poppler_path)
                else None
            )
            pages = pdf2image.convert_from_path(
                temp_path,
                dpi=self.config.ocr_dpi,
                poppler_path=poppler,
            )
            return "\n".join(
                pytesseract.image_to_string(page.convert("L"), lang=self.config.ocr_language)
                for page in pages
            )
        except Exception:
            return ""
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    @staticmethod
    def _extract_native_pdf_text(pdf_bytes: bytes) -> str:
        if PdfReader is None:
            return ""

        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception:
            return ""
