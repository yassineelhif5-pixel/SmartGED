"""Boundary detection for multi-document PDFs (scan batches).

Two detectors, combined:

* **Heuristic** (always available, no AI): page-numbering resets ("Page 1/3"), document headers with
  an identifier ("FACTURE N° …", "BON DE COMMANDE …"), changes of reference number and blank
  separator pages. It is deliberately conservative: a page that says "page 2/3" is never a start.
* **AI** (when the organisation configured a provider): the ``document_splitting`` prompt receives a
  short excerpt of each page and returns the segments. The answer is structurally validated
  (contiguous, in range, no overlap); an invalid answer falls back to the heuristic.

Nothing is cut here: the result is a *proposal* reviewed by a human (see ``split_service``).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, DocumentType

START_KEYWORDS = [
    "facture", "invoice", "avoir", "credit note", "bon de commande", "purchase order", "bon de livraison",
    "delivery note", "devis", "quotation", "quote", "contrat", "contract", "relevé", "releve", "statement",
    "bulletin de paie", "bulletin de salaire", "fiche de paie", "payslip", "attestation", "certificat",
    "procès-verbal", "proces-verbal", "ordre de mission", "note de frais", "reçu", "recu", "receipt",
    "courrier", "lettre de", "convention", "avenant", "mandat",
]
_KW = "|".join(sorted((re.escape(k) for k in START_KEYWORDS), key=len, reverse=True))
HEADER_RE = re.compile(rf"\b({_KW})\b\s*(?:n[°o]\.?|no\.?|num(?:éro|ero)?\.?|#|:)?\s*((?=[A-Z0-9/._-]*\d)[A-Z0-9][A-Z0-9/._-]{{2,}})?",
                       re.IGNORECASE)
PAGE_OF_RE = re.compile(r"\bpage\s*(\d{1,3})\s*(?:/|sur|of|de)\s*(\d{1,3})\b", re.IGNORECASE)
SHORT_PAGE_OF_RE = re.compile(r"(?:^|\s)(\d{1,2})\s*/\s*(\d{1,2})\s*$", re.MULTILINE)
REF_RE = re.compile(r"\b(?:n[°o]|no\.?|réf(?:érence)?\.?|ref\.?)\s*[:.]?\s*((?=[A-Z0-9/._-]*\d)[A-Z0-9][A-Z0-9/._-]{3,})", re.IGNORECASE)
BLANK_CHARS = 15
BOUNDARY_THRESHOLD = 0.5


@dataclass
class PageSignal:
    page: int
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    blank: bool = False
    header: str | None = None
    reference: str | None = None
    page_of: tuple[int, int] | None = None


@dataclass
class Detection:
    method: str
    segments: list[dict[str, Any]]
    separator_pages: list[int]
    confidence: float | None
    details: dict[str, Any]

    @property
    def is_multi(self) -> bool:
        return len(self.segments) > 1


def _clean(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").strip()


def _page_of(text: str) -> tuple[int, int] | None:
    m = PAGE_OF_RE.search(text)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return (a, b) if 1 <= a <= b else None
    tail = text[-120:]
    m = SHORT_PAGE_OF_RE.search(tail)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return (a, b) if 1 <= a <= b <= 50 else None
    return None


def analyse_pages(pages: list[tuple[int, str]]) -> list[PageSignal]:
    signals: list[PageSignal] = []
    for number, raw in pages:
        text = _clean(raw)
        sig = PageSignal(page=number)
        compact = re.sub(r"\s+", "", text)
        if len(compact) < BLANK_CHARS:
            sig.blank = True
            signals.append(sig)
            continue
        sig.page_of = _page_of(text)
        head = text[:400]
        m = HEADER_RE.search(head)
        if m:
            sig.header = m.group(1).lower()
            if m.group(2):
                sig.reference = m.group(2).upper()
        if sig.reference is None:
            r = REF_RE.search(head)
            if r:
                sig.reference = r.group(1).upper()
        signals.append(sig)

    previous: PageSignal | None = None
    current_ref: str | None = None
    for sig in signals:
        if sig.blank:
            continue
        if previous is None:  # first content page always starts a document
            sig.score = 1.0
            sig.reasons.append("first_page")
            current_ref = sig.reference
            previous = sig
            continue
        if sig.page_of is not None:
            if sig.page_of[0] == 1:
                sig.score += 0.6
                sig.reasons.append(f"page_numbering_reset (1/{sig.page_of[1]})")
            else:
                sig.score -= 0.8
                sig.reasons.append(f"continuation (page {sig.page_of[0]}/{sig.page_of[1]})")
        if previous.page_of is not None and previous.page_of[0] < previous.page_of[1] and sig.page_of is None:
            sig.score -= 0.3
            sig.reasons.append("previous_page_announced_more_pages")
        if sig.header:
            sig.score += 0.5 if sig.reference else 0.3
            sig.reasons.append(f"document_header ({sig.header}{' ' + sig.reference if sig.reference else ''})")
        if sig.reference and current_ref and sig.reference != current_ref:
            sig.score += 0.2
            sig.reasons.append("new_reference")
        if sig.reference and sig.reference == current_ref:
            sig.score -= 0.4
            sig.reasons.append("same_reference")
        if sig.blank is False and previous.page + 1 < sig.page:
            # one or more blank separator pages right before this one
            sig.score += 0.3
            sig.reasons.append("after_blank_separator")
        sig.score = round(max(-1.0, min(1.0, sig.score)), 3)
        if sig.score >= BOUNDARY_THRESHOLD and sig.reference:
            current_ref = sig.reference
        elif current_ref is None and sig.reference:
            current_ref = sig.reference
        previous = sig
    return signals


def heuristic_segments(pages: list[tuple[int, str]]) -> Detection:
    signals = analyse_pages(pages)
    separators = [s.page for s in signals if s.blank]
    segments: list[dict[str, Any]] = []
    for sig in signals:
        if sig.blank:
            continue
        if not segments or sig.score >= BOUNDARY_THRESHOLD:
            segments.append({"start_page": sig.page, "end_page": sig.page, "title": None,
                             "document_type_code": None, "confidence": None if not segments else sig.score,
                             "reasons": sig.reasons, "_header": sig.header, "_reference": sig.reference})
        else:
            segments[-1]["end_page"] = sig.page
    for seg in segments:
        header, ref = seg.pop("_header"), seg.pop("_reference")
        if header:
            seg["title"] = f"{header.capitalize()}{' ' + ref if ref else ''}"
    boundary_scores = [s["confidence"] for s in segments[1:] if s["confidence"] is not None]
    # Blank separators only count as boundaries when they sit between two content pages
    if len(segments) == 1:
        segments[0]["confidence"] = None
    confidence = round(min(boundary_scores), 3) if boundary_scores else None
    for seg in segments:
        if seg["confidence"] is None and len(segments) > 1:
            seg["confidence"] = confidence
    return Detection(method="heuristic", segments=segments, separator_pages=separators, confidence=confidence,
                     details={"signals": [{"page": s.page, "score": s.score, "reasons": s.reasons, "blank": s.blank}
                                          for s in signals]})


def validate_segments(segments: list[dict[str, Any]], page_count: int, *, allow_gaps: bool = True) -> list[dict[str, Any]]:
    """Normalise and validate segments: in range, ordered, non-overlapping. Raises ValueError."""
    out: list[dict[str, Any]] = []
    last_end = 0
    for raw in segments:
        try:
            start, end = int(raw["start_page"]), int(raw["end_page"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Each segment needs integer start_page and end_page") from exc
        if not 1 <= start <= end <= page_count:
            raise ValueError(f"Segment {start}-{end} is outside pages 1-{page_count}")
        if start <= last_end:
            raise ValueError("Segments must be ordered and must not overlap")
        if not allow_gaps and start != last_end + 1:
            raise ValueError("Segments must be contiguous")
        last_end = end
        out.append({**raw, "start_page": start, "end_page": end})
    if not out:
        raise ValueError("At least one segment is required")
    return out


def ai_segments(db: Session, doc: Document, pages: list[tuple[int, str]], *, key: str,
                heuristic: Detection) -> Detection:
    from app.services import ai_service

    types = list(db.scalars(select(DocumentType).where(DocumentType.tenant_id == doc.tenant_id,
                                                       DocumentType.is_active.is_(True))))
    catalogue = "\n".join(f"- {t.code} — {t.name}" for t in types) or "(aucun type configuré)"
    excerpts = []
    for number, text in pages:
        t = _clean(text)
        snippet = t if len(t) <= 900 else f"{t[:700]}\n[…]\n{t[-200:]}"
        excerpts.append(f"[[page {number}]]\n{snippet or '(page vide)'}")
    content = ai_service.neutralise("\n\n".join(excerpts), 60_000)
    result = ai_service.run_prompt(
        db, doc.tenant_id, prompt_code="document_splitting", feature="document_splitting", idempotency_key=key,
        document_id=doc.id, variables={"document_content": content, "page_count": str(len(pages)),
                                       "document_types": catalogue, "file_name": doc.original_file_name})
    meta = {"model": result.completion.model, "credits": result.credits,
            "tokens": result.completion.input_tokens + result.completion.output_tokens}
    data = result.data or {}
    raw = data.get("documents")
    page_count = max((n for n, _ in pages), default=0)
    codes = {t.code: t for t in types}
    try:
        if not isinstance(raw, list):
            raise ValueError("missing 'documents' list")
        segs = validate_segments([{"start_page": d.get("start_page"), "end_page": d.get("end_page")}
                                  for d in raw if isinstance(d, dict)], page_count)
    except ValueError as exc:
        heuristic.details["ai"] = {**meta, "error": f"invalid AI answer: {exc}", "fallback": "heuristic"}
        return heuristic
    segments = []
    heur_starts = {s["start_page"] for s in heuristic.segments}
    for seg, d in zip(segs, [d for d in raw if isinstance(d, dict)], strict=False):
        try:
            conf = max(0.0, min(1.0, float(d.get("confidence") or 0.5)))
        except (TypeError, ValueError):
            conf = 0.5
        reasons = [str(d.get("reason") or "")[:300]] if d.get("reason") else []
        if seg["start_page"] in heur_starts and seg["start_page"] != segs[0]["start_page"]:
            conf = round(min(1.0, conf + 0.1), 3)
            reasons.append("confirmed_by_heuristic")
        code = d.get("document_type") if d.get("document_type") in codes else None
        title = str(d.get("title") or "").strip()[:200] or None
        segments.append({"start_page": seg["start_page"], "end_page": seg["end_page"], "title": title,
                         "document_type_code": code, "document_type_id": str(codes[code].id) if code else None,
                         "confidence": conf, "reasons": reasons})
    covered = {p for s in segments for p in range(s["start_page"], s["end_page"] + 1)}
    separators = sorted(n for n, _ in pages if n not in covered)
    confidence = round(min(s["confidence"] for s in segments[1:]), 3) if len(segments) > 1 else None
    return Detection(method="ai", segments=segments, separator_pages=separators, confidence=confidence,
                     details={"ai": meta, "heuristic": {"segments": [[s["start_page"], s["end_page"]]
                                                                      for s in heuristic.segments]},
                              "signals": heuristic.details.get("signals", [])})
