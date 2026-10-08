from __future__ import annotations

from datetime import datetime
from enum import IntEnum
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict
from pydantic.alias_generators import to_camel

_EMPTY = {None, "", "null", "NULL", "-"}


def _blank_to_none(value: Any) -> Any:
    if isinstance(value, str) and value.strip() in _EMPTY:
        return None
    return value


def _to_float(value: Any) -> Any:
    value = _blank_to_none(value)
    if value is None or isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        cleaned = value.strip().replace(",", ".")
        # strip a trailing unit: kWh, W, V, A, %, m
        number = ""
        for char in cleaned:
            if char.isdigit() or char in "+-.eE":
                number += char
            else:
                break
        try:
            return float(number)
        except ValueError:
            return None
    return None


def _to_int(value: Any) -> Any:
    result = _to_float(value)
    return None if result is None else int(result)


def _to_bool(value: Any) -> Any:
    value = _blank_to_none(value)
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off"}:
            return False
    return None


_DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d",
)


def _to_datetime(value: Any) -> Any:
    value = _blank_to_none(value)
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        # epoch seconds or milliseconds
        seconds = value / 1000 if value > 1e11 else value
        return datetime.fromtimestamp(seconds)
    if isinstance(value, str):
        text = value.strip()
        for fmt in _DATETIME_FORMATS:
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
    return None


def _to_str(value: Any) -> Any:
    value = _blank_to_none(value)
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(int(value)) if float(value).is_integer() else str(value)
    return None


def _to_str_list(value: Any) -> list[str]:
    value = _blank_to_none(value)
    if isinstance(value, (list, tuple)):
        return [text for text in map(_to_str, value) if text is not None]
    return []


def to_int_enum[E: IntEnum](kind: type[E], raw: str | int | None) -> E | None:
    if raw is None:
        return None
    try:
        return kind(int(raw))
    except ValueError:
        return None


ApiFloat = Annotated[float | None, BeforeValidator(_to_float)]
ApiInt = Annotated[int | None, BeforeValidator(_to_int)]
ApiBool = Annotated[bool | None, BeforeValidator(_to_bool)]
ApiStr = Annotated[str | None, BeforeValidator(_to_str)]
ApiDateTime = Annotated[datetime | None, BeforeValidator(_to_datetime)]
ApiStrList = Annotated[list[str], BeforeValidator(_to_str_list)]


class EpCubeModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="allow",
        str_strip_whitespace=True,
        arbitrary_types_allowed=True,
    )

    @property
    def extras(self) -> dict[str, Any]:
        return dict(self.__pydantic_extra__ or {})

    def api_dump(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_none=True)
