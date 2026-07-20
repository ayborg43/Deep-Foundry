"""Validation and export helpers for model-assisted structured extraction."""

from __future__ import annotations

import csv
import io
import json
import re
from typing import Any

from django.conf import settings


class ExtractionError(ValueError):
    pass


def validate_field_schema(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict) or not schema:
        raise ExtractionError("Extraction schema must be a non-empty object.")
    if len(schema) > settings.EXTRACTION_MAX_FIELDS:
        raise ExtractionError(
            f"Extraction schemas are limited to {settings.EXTRACTION_MAX_FIELDS} fields."
        )
    validated: dict[str, Any] = {}
    for raw_name, prototype in schema.items():
        name = str(raw_name).strip()
        if not name or len(name) > 100 or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_ -]*", name):
            raise ExtractionError(f"Invalid extraction field name {raw_name!r}.")
        if isinstance(prototype, dict):
            raise ExtractionError("Nested objects are not supported in extraction schemas.")
        if isinstance(prototype, list):
            if len(prototype) > 1:
                raise ExtractionError(
                    f"Array field {name!r} must be empty or contain one type example."
                )
            if prototype and isinstance(prototype[0], (dict, list)):
                raise ExtractionError(f"Array field {name!r} must contain primitive values.")
        elif prototype is not None and not isinstance(prototype, (str, int, float, bool)):
            raise ExtractionError(f"Field {name!r} has an unsupported type.")
        validated[name] = prototype
    return validated


def _coerce(value: Any, prototype: Any, field: str) -> Any:
    if isinstance(prototype, list):
        values = value if isinstance(value, list) else ([] if value in (None, "") else [value])
        if len(values) > settings.EXTRACTION_MAX_ARRAY_ITEMS:
            values = values[: settings.EXTRACTION_MAX_ARRAY_ITEMS]
        item_prototype = prototype[0] if prototype else ""
        return [_coerce(item, item_prototype, field) for item in values]
    if prototype is None or isinstance(prototype, str):
        return "" if value is None else str(value)[: settings.EXTRACTION_MAX_VALUE_CHARS]
    if isinstance(prototype, bool):
        if isinstance(value, bool):
            return value
        normalized = str(value).strip().lower()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0", ""}:
            return False
        raise ExtractionError(f"Field {field!r} must be a boolean.")
    if isinstance(prototype, int) and not isinstance(prototype, bool):
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ExtractionError(f"Field {field!r} must be an integer.") from exc
    if isinstance(prototype, float):
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ExtractionError(f"Field {field!r} must be a number.") from exc
    return value


def validate_extracted_data(data: Any, schema: dict[str, Any]) -> dict[str, Any]:
    validated_schema = validate_field_schema(schema)
    if not isinstance(data, dict):
        raise ExtractionError("Extracted data must be an object.")
    return {
        field: _coerce(data.get(field), prototype, field)
        for field, prototype in validated_schema.items()
    }


def parse_model_json(content: str, schema: dict[str, Any]) -> dict[str, Any]:
    text = str(content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExtractionError("The extraction model did not return valid JSON.") from exc
    return validate_extracted_data(value, schema)


def extract_labeled_values(text: str, schema: dict[str, Any]) -> dict[str, Any]:
    """Deterministic fallback used by the built-in tool.

    It extracts explicit ``field: value`` labels and never invents a value.
    Deep Research uses the model-assisted path and validates it with the same
    schema before persistence.
    """
    validated = validate_field_schema(schema)
    result: dict[str, Any] = {}
    for field, prototype in validated.items():
        match = re.search(
            rf"(?im)^\s*{re.escape(field)}\s*[:=-]\s*(.+?)\s*$",
            text,
        )
        raw: Any = match.group(1).strip() if match else None
        if isinstance(prototype, list) and isinstance(raw, str):
            raw = [item.strip() for item in raw.split(",") if item.strip()]
        result[field] = _coerce(raw, prototype, field)
    return result


def safe_csv_cell(value: Any) -> str:
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)
    elif value is None:
        text = ""
    else:
        text = str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return f"'{text}"
    return text


def extraction_to_csv(data: dict[str, Any]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(data.keys())
    writer.writerow([safe_csv_cell(value) for value in data.values()])
    return output.getvalue()
