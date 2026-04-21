"""Path-aware decoding for OJS wire objects."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ojs._utils import parse_datetime
from ojs.errors import OJSValidationError


@dataclass(frozen=True, slots=True)
class WireDecoder:
    """Decode one JSON object while retaining its path for diagnostics."""

    data: Mapping[str, Any]
    path: str

    @classmethod
    def object(cls, value: object, path: str) -> WireDecoder:
        if not isinstance(value, Mapping):
            raise _invalid(path, "object", value)
        if not all(isinstance(key, str) for key in value):
            raise OJSValidationError(f"invalid wire value at {path}: object keys must be strings")
        return cls(value, path)

    def value(self, field: str, default: Any = None) -> Any:
        return self.data.get(field, default)

    def required_string(self, field: str) -> str:
        path = self._field_path(field)
        if field not in self.data:
            raise OJSValidationError(f"invalid wire value at {path}: field is required")
        value = self.data[field]
        if not isinstance(value, str):
            raise _invalid(path, "string", value)
        return value

    def string(self, field: str, default: str | None = None) -> str | None:
        value = self.data.get(field, default)
        if value is None:
            return None
        if not isinstance(value, str):
            raise _invalid(self._field_path(field), "string", value)
        return value

    def integer(self, field: str, default: int | None = None) -> int | None:
        value = self.data.get(field, default)
        if value is None:
            return None
        if not isinstance(value, int) or isinstance(value, bool):
            raise _invalid(self._field_path(field), "integer", value)
        return value

    def number(self, field: str, default: float = 0.0) -> float:
        value = self.data.get(field, default)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise _invalid(self._field_path(field), "number", value)
        return float(value)

    def array(self, field: str, default: list[Any] | None = None) -> list[Any]:
        value = self.data.get(field, [] if default is None else default)
        if not isinstance(value, list):
            raise _invalid(self._field_path(field), "array", value)
        return value

    def string_array(self, field: str, default: list[str] | None = None) -> list[str]:
        values = self.array(field, [] if default is None else default)
        for index, value in enumerate(values):
            if not isinstance(value, str):
                raise _invalid(f"{self._field_path(field)}[{index}]", "string", value)
        return values

    def mapping(
        self,
        field: str,
        default: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        value = self.data.get(field, {} if default is None else default)
        decoder = self.object(value, self._field_path(field))
        return dict(decoder.data)

    def optional_mapping(self, field: str) -> dict[str, Any] | None:
        value = self.data.get(field)
        if value is None:
            return None
        decoder = self.object(value, self._field_path(field))
        return dict(decoder.data)

    def datetime(self, field: str, *, required: bool = False) -> datetime | None:
        path = self._field_path(field)
        if field not in self.data:
            if required:
                raise OJSValidationError(f"invalid wire value at {path}: field is required")
            return None
        value = self.data[field]
        if value is None:
            if required:
                raise _invalid(path, "ISO 8601 timestamp", value)
            return None
        if isinstance(value, datetime):
            return value
        if not isinstance(value, str):
            raise _invalid(path, "ISO 8601 timestamp", value)
        return parse_datetime(value, path=path)

    def child(self, field: str) -> WireDecoder:
        return self.object(self.data.get(field), self._field_path(field))

    def _field_path(self, field: str) -> str:
        return f"{self.path}.{field}"


def _invalid(path: str, expected: str, value: object) -> OJSValidationError:
    return OJSValidationError(
        f"invalid wire value at {path}: expected {expected}, got {type(value).__name__}"
    )


__all__ = ["WireDecoder"]
