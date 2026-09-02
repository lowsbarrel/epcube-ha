"""Shared model configuration and the coercions the EP Cube API makes necessary.

The API is loose about types in ways that would make strict models useless:

* numbers arrive as strings about half the time (`"15"`, `"0.70"`)
* booleans arrive as `"1"` / `"0"` / `1` / `0` / `true`
* capacities arrive with their unit glued on (`"15kWh"`)
* timestamps are `"YYYY-MM-DD HH:MM:SS"` with no zone, sometimes without seconds
* empty values are `""` as often as `null`

So every field goes through a `BeforeValidator` that normalises the value before
pydantic sees it. Unknown fields are kept rather than dropped (`extra="allow"`),
because this API is undocumented and the next firmware may add something.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, TypeVar

from pydantic import BaseModel, BeforeValidator, ConfigDict
from pydantic.alias_generators import to_camel

T = TypeVar("T")

_EMPTY = {None, "", "null", "NULL", "-"}


def _blank_to_none(value: Any) -> Any:
    if isinstance(value, str) and value.strip() in _EMPTY:
        return None
    return value


def _to_float(value: Any) -> Any:
    """`"0.70"` -> 0.7, `"15kWh"` -> 15.0, `""` -> None."""
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
    # Anything else (a list, a dict) is unusable; None keeps the rest of the
    # response parseable instead of failing validation over one field.
    return None


def _to_int(value: Any) -> Any:
    result = _to_float(value)
    return None if result is None else int(result)


def _to_bool(value: Any) -> Any:
    """The API expresses booleans as 1/0, "1"/"0", or true/false."""
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
    # Unrecognised: None, not the raw value. Passing it through would fail
    # validation and take the whole response down over one odd field.
    return None


_DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d",
)


def _to_datetime(value: Any) -> Any:
    """Naive datetimes, as sent.

    The API reports the same instant twice in `homeDeviceInfo` -- once in UTC and
    once in the site's local zone, each with its zone name alongside -- so
    attaching a zone here would be guessing. `LiveSnapshot` exposes both.
    """
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
    """Identifiers are ints in one response and strings in the next; pick one."""
    value = _blank_to_none(value)
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(int(value)) if float(value).is_integer() else str(value)
    return None


def _to_str_list(value: Any) -> Any:
    """`activeWeek` comes back as ints but has to be sent as strings.

    Absent or unusable becomes an empty list, never None: the field is declared
    as a list and a None would fail validation.
    """
    value = _blank_to_none(value)
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [_to_str(item) for item in value if _to_str(item) is not None]
    return []


# Annotated aliases used throughout the models.
ApiFloat = Annotated[float | None, BeforeValidator(_to_float)]
ApiInt = Annotated[int | None, BeforeValidator(_to_int)]
ApiBool = Annotated[bool | None, BeforeValidator(_to_bool)]
ApiStr = Annotated[str | None, BeforeValidator(_to_str)]
ApiDateTime = Annotated[datetime | None, BeforeValidator(_to_datetime)]
ApiStrList = Annotated[list[str], BeforeValidator(_to_str_list)]


class EpCubeModel(BaseModel):
    """Base for every response model.

    Fields are named in snake_case and mapped to the API's camelCase
    automatically; where the API's own spelling is irregular (or misspelled), the
    field carries an explicit alias. Both spellings are accepted on input.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="allow",
        str_strip_whitespace=True,
        arbitrary_types_allowed=True,
    )

    @property
    def extras(self) -> dict[str, Any]:
        """Fields the API returned that this model does not name.

        Worth checking after a firmware update: anything new shows up here
        before it gets a proper field.
        """
        return dict(self.__pydantic_extra__ or {})

    def api_dump(self) -> dict[str, Any]:
        """Serialise back to the API's own field names."""
        return self.model_dump(by_alias=True, exclude_none=True)


class EpCubeRequest(EpCubeModel):
    """Base for request bodies.

    `exclude_none` is deliberately *not* applied when these are serialised: the
    switchMode endpoint treats an absent field as "reset this to default", so a
    request model must emit every field it declares, every time.
    """

    def api_dump(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_none=False)
