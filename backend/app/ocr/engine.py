"""Text extraction & OCR engine with interchangeable providers.

Strategy per page:
* PDF with a usable text layer → take the text layer (fast, exact).
* Scanned PDF page / image → rasterise (pdftoppm) and OCR with the configured provider.
* Text formats → read directly.
* Office formats → extract XML text.

Providers implement :class:`OcrProvider`. Tesseract is bundled; Azure AI
Document Intelligence, Google Document AI and AWS Textract plug in through the
same interface (see ``docs/AI_CONFIGURATION.md``).
"""

from __future__ import annotations

import abc
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


class OcrNotConfigured(RuntimeError):
    pass


@dataclass
class PageText:
    page_number: int
    text: str
    method: str
    confidence: float | None = None
    blocks: list[dict] | None = None


@dataclass
class ExtractionResult:
    pages: list[PageText] = field(default_factory=list)
    provider: str = "none"
    ocr_used: bool = False

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.text for p in self.pages if p.text)


class OcrProvider(abc.ABC):
    name: str

    @abc.abstractmethod
    def ocr_image(self, image_path: Path, page_number: int) -> PageText: ...

    def is_available(self) -> bool:
        return True


class TesseractProvider(OcrProvider):
    name = "tesseract"

    def __init__(self, languages: str) -> None:
        self.languages = languages
        self.binary = shutil.which("tesseract")

    def is_available(self) -> bool:
        return self.binary is not None

    def _langs(self) -> str:
        try:
            out = subprocess.run([self.binary, "--list-langs"], capture_output=True, text=True, timeout=10)  # type: ignore[list-item]
            installed = set(out.stdout.split()) | set(out.stderr.split())
            wanted = [lang for lang in self.languages.split("+") if lang in installed]
            return "+".join(wanted) or "eng"
        except Exception:  # noqa: BLE001
            return "eng"

    def ocr_image(self, image_path: Path, page_number: int) -> PageText:
        if not self.binary:
            raise OcrNotConfigured("tesseract binary not found")
        result = subprocess.run(
            [self.binary, str(image_path), "stdout", "-l", self._langs(), "--psm", "3", "tsv"],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(f"tesseract failed: {result.stderr[:500]}")
        words, confs, blocks = [], [], []
        lines: dict[tuple[int, int, int], list[str]] = {}
        for row in result.stdout.splitlines()[1:]:
            cols = row.split("\t")
            if len(cols) != 12 or not cols[11].strip():
                continue
            conf = float(cols[10])
            if conf < 0:
                continue
            word = cols[11]
            key = (int(cols[2]), int(cols[3]), int(cols[4]))  # block, paragraph, line
            lines.setdefault(key, []).append(word)
            words.append(word)
            confs.append(conf)
            blocks.append({"text": word, "conf": conf, "bbox": [int(cols[6]), int(cols[7]), int(cols[8]), int(cols[9])]})
        text = "\n".join(" ".join(ws) for _, ws in sorted(lines.items()))
        confidence = round(sum(confs) / len(confs) / 100, 4) if confs else None
        return PageText(page_number, text, "tesseract", confidence, blocks[:5000])


def get_ocr_provider() -> OcrProvider | None:
    settings = get_settings()
    if settings.ocr_provider == "tesseract":
        provider = TesseractProvider(settings.ocr_languages)
        return provider if provider.is_available() else None
    # Cloud providers are registered here once their credentials are configured.
    return None


def _rasterise_pdf_page(pdf: Path, page_number: int, out_dir: Path) -> Path:
    prefix = out_dir / f"p{page_number}"
    subprocess.run(
        ["pdftoppm", "-r", "300", "-gray", "-png", "-f", str(page_number), "-l", str(page_number), "-singlefile",
         str(pdf), str(prefix)],
        check=True, capture_output=True, timeout=300,
    )
    return prefix.with_suffix(".png")


def _office_text(path: Path) -> list[PageText]:
    with zipfile.ZipFile(path) as zf:
        xml_parts = [n for n in zf.namelist() if re.match(r"(word/document|xl/sharedStrings|ppt/slides/slide\d+)\.xml$", n)]
        texts = []
        for name in sorted(xml_parts):
            raw = zf.read(name).decode("utf-8", errors="ignore")
            raw = re.sub(r"</w:p>|</a:p>|</si>", "\n", raw)
            texts.append(re.sub(r"<[^>]+>", "", raw))
    return [PageText(i + 1, t.strip(), "office_xml") for i, t in enumerate(texts) if t.strip()]


def extract_text(path: Path, mime_type: str) -> ExtractionResult:
    settings = get_settings()
    provider = get_ocr_provider()
    result = ExtractionResult(provider=provider.name if provider else "none")

    if mime_type.startswith("text/") or mime_type == "message/rfc822":
        result.pages = [PageText(1, path.read_text(encoding="utf-8", errors="replace"), "plain_text")]
        return result

    if mime_type.startswith("application/vnd.openxmlformats"):
        result.pages = _office_text(path)
        return result

    if mime_type.startswith("image/"):
        if provider is None:
            raise OcrNotConfigured("No OCR provider available for images")
        result.pages = [provider.ocr_image(path, 1)]
        result.ocr_used = True
        return result

    if mime_type == "application/pdf":
        reader = PdfReader(str(path))
        with tempfile.TemporaryDirectory(prefix="documind-ocr-") as tmp:
            for idx, page in enumerate(reader.pages, start=1):
                try:
                    layer = (page.extract_text() or "").strip()
                except Exception:  # noqa: BLE001 — malformed page content
                    layer = ""
                if len(layer) >= settings.ocr_min_text_chars_per_page:
                    result.pages.append(PageText(idx, layer, "text_layer", 1.0))
                    continue
                if provider is None:
                    result.pages.append(PageText(idx, layer, "text_layer_partial"))
                    continue
                image = _rasterise_pdf_page(path, idx, Path(tmp))
                result.pages.append(provider.ocr_image(image, idx))
                result.ocr_used = True
        return result

    raise OcrNotConfigured(f"No extractor for {mime_type}")


# ---------------------------------------------------------------- language
_STOPWORDS = {
    "fr": {"le", "la", "les", "des", "et", "est", "une", "pour", "dans", "du", "que", "qui", "sur", "avec", "par"},
    "en": {"the", "and", "is", "of", "to", "in", "for", "that", "with", "on", "by", "this", "are", "be", "from"},
    "es": {"el", "los", "las", "y", "es", "una", "para", "con", "por", "que", "del", "en", "se"},
    "de": {"der", "die", "das", "und", "ist", "ein", "eine", "mit", "für", "von", "den", "nicht", "zu"},
}


def detect_language(text: str) -> str | None:
    """Lightweight stop-word scoring. Returns None when the evidence is too weak."""
    tokens = re.findall(r"[a-zàâäéèêëîïôöùûüç]+", text.lower()[:20000])
    if len(tokens) < 20:
        return None
    scores = {lang: sum(1 for t in tokens if t in words) for lang, words in _STOPWORDS.items()}
    lang, score = max(scores.items(), key=lambda kv: kv[1])
    return lang if score >= 5 else None
