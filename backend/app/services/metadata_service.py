"""Dynamic metadata: value coercion & validation driven by admin-defined field definitions."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.errors import ValidationFailed
from app.models import MetadataDataType, MetadataDefinition

TECH_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,79}$")


def _fail(defn: MetadataDefinition, msg: str) -> ValidationFailed:
    return ValidationFailed(f"{defn.display_name}: {msg}", details={"field": defn.technical_name})


def coerce_value(defn: MetadataDefinition, raw: Any) -> Any:  # noqa: C901 — one branch per data type
    """Return a JSON-serialisable, normalised value or raise ValidationFailed. ``None`` clears the field."""
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        if defn.required:
            raise _fail(defn, "value is required")
        return None

    dt = defn.data_type
    rules = defn.validation_rules or {}
    value: Any

    if dt in (MetadataDataType.text, MetadataDataType.long_text, MetadataDataType.reference):
        value = str(raw).strip()
        max_len = rules.get("max_length", 255 if dt == MetadataDataType.text else 20000)
        if len(value) > max_len:
            raise _fail(defn, f"maximum length is {max_len}")
        if (pattern := rules.get("pattern")) and not re.fullmatch(pattern, value):
            raise _fail(defn, "value does not match the expected format")
    elif dt == MetadataDataType.integer:
        try:
            value = int(str(raw).replace(" ", ""))
        except ValueError as exc:
            raise _fail(defn, "must be an integer") from exc
    elif dt in (MetadataDataType.decimal, MetadataDataType.currency):
        text = str(raw).replace(" ", "").replace(" ", "")
        if "," in text and "." not in text:
            text = text.replace(",", ".")
        text = re.sub(r"[^\d.\-]", "", text)
        try:
            dec = Decimal(text)
        except InvalidOperation as exc:
            raise _fail(defn, "must be a number") from exc
        value = str(dec.quantize(Decimal("0.01"))) if dt == MetadataDataType.currency else str(dec)
    elif dt == MetadataDataType.date:
        value = _parse_date(defn, raw).isoformat()
    elif dt == MetadataDataType.datetime:
        try:
            value = datetime.fromisoformat(str(raw)).isoformat()
        except ValueError as exc:
            raise _fail(defn, "must be an ISO date-time") from exc
    elif dt == MetadataDataType.boolean:
        if isinstance(raw, bool):
            value = raw
        elif str(raw).lower() in ("true", "1", "yes", "oui"):
            value = True
        elif str(raw).lower() in ("false", "0", "no", "non"):
            value = False
        else:
            raise _fail(defn, "must be true or false")
    elif dt == MetadataDataType.dropdown:
        value = str(raw)
        if defn.allowed_values and value not in defn.allowed_values:
            raise _fail(defn, "value is not in the allowed list")
    elif dt == MetadataDataType.multi_select:
        items = raw if isinstance(raw, list) else [raw]
        value = [str(i) for i in items]
        if defn.allowed_values and any(v not in defn.allowed_values for v in value):
            raise _fail(defn, "one or more values are not allowed")
    elif dt == MetadataDataType.calculated:
        raise _fail(defn, "calculated fields cannot be set directly")
    else:  # pragma: no cover
        raise _fail(defn, "unsupported data type")

    if dt in (MetadataDataType.integer, MetadataDataType.decimal, MetadataDataType.currency):
        num = Decimal(str(value))
        if "min" in rules and num < Decimal(str(rules["min"])):
            raise _fail(defn, f"must be ≥ {rules['min']}")
        if "max" in rules and num > Decimal(str(rules["max"])):
            raise _fail(defn, f"must be ≤ {rules['max']}")
    return value


def _parse_date(defn: MetadataDefinition, raw: Any) -> date:
    if isinstance(raw, date):
        return raw
    text = str(raw).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise _fail(defn, "must be a date (YYYY-MM-DD or DD/MM/YYYY)")
