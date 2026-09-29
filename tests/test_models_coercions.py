from __future__ import annotations

from datetime import datetime

import pytest

from epcube_api import LiveSnapshot, ModeConfig


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0.70", 0.7),
        ("15kWh", 15.0),
        ("15.0kWh", 15.0),
        ("1,5", 1.5),
        (12, 12.0),
        ("", None),
        (None, None),
        ("-", None),
        ("abc", None),
        ("-3.5", -3.5),
    ],
)
def test_float_coercion(raw: object, expected: float | None):
    assert LiveSnapshot.model_validate({"solarPower": raw}).solar_power == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1", True),
        (1, True),
        ("true", True),
        ("YES", True),
        (True, True),
        ("0", False),
        (0, False),
        ("false", False),
        ("no", False),
        ("", None),
        (None, None),
    ],
)
def test_bool_coercion(raw: object, expected: bool | None):
    assert LiveSnapshot.model_validate({"isOnline": raw}).is_online == expected


def test_unrecognised_values_become_none_not_validation_errors():
    # Odd fields degrade to None; handing them to pydantic would reject the whole snapshot.
    assert LiveSnapshot.model_validate({"isOnline": "maybe"}).is_online is None
    assert LiveSnapshot.model_validate({"defCreateTime": "not a date"}).def_create_time is None
    assert ModeConfig.model_validate({"devId": ["a", "list"]}).dev_id is None
    assert ModeConfig.model_validate({"activeWeek": "not a list"}).active_week == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-09-02 07:19:05", datetime(2026, 9, 2, 7, 19, 5)),
        ("2026-09-01 12:19", datetime(2026, 9, 1, 12, 19)),
        ("2026-09-02T07:19:05", datetime(2026, 9, 2, 7, 19, 5)),
        ("2026-09-02", datetime(2026, 9, 2)),
        ("", None),
    ],
)
def test_datetime_coercion(raw: object, expected: datetime | None):
    assert LiveSnapshot.model_validate({"defCreateTime": raw}).def_create_time == expected


def test_datetime_coercion_from_epoch():
    seconds = LiveSnapshot.model_validate({"defCreateTime": 1756800000}).def_create_time
    millis = LiveSnapshot.model_validate({"defCreateTime": 1756800000000}).def_create_time
    assert seconds == millis


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(1, "1"), ("1", "1"), (1.0, "1"), (1.5, "1.5"), (True, "1"), (False, "0"), ("", None)],
)
def test_str_coercion(raw: object, expected: str | None):
    assert ModeConfig.model_validate({"devId": raw}).dev_id == expected


def test_str_list_coercion():
    config = ModeConfig.model_validate({"activeWeek": [1, 2, 3]})
    assert config.active_week == ["1", "2", "3"]
    assert ModeConfig.model_validate({"activeWeek": None}).active_week == []
    assert ModeConfig.model_validate({}).active_week == []


def test_int_coercion_of_nonsense_is_none():
    assert LiveSnapshot.model_validate({"batterySoc": "abc"}).battery_soc is None


def test_api_dump_uses_the_wire_names():
    dumped = LiveSnapshot.model_validate({"devId": "1", "backUpPower": 5}).api_dump()
    assert dumped["devId"] == "1"
    assert dumped["backUpPower"] == 5.0


def test_unusable_container_values_coerce_to_none():
    assert LiveSnapshot.model_validate({"solarPower": [1, 2]}).solar_power is None
    assert LiveSnapshot.model_validate({"batterySoc": {"a": 1}}).battery_soc is None


def test_coercion_branches_for_numeric_inputs():
    assert LiveSnapshot.model_validate({"isOnline": 2.5}).is_online is True
    assert LiveSnapshot.model_validate({"isOnline": 0.0}).is_online is False
    assert LiveSnapshot.model_validate({"defCreateTime": 0}).def_create_time is not None
    assert ModeConfig.model_validate({"devId": True}).dev_id == "1"


def test_coercers_reject_containers_across_every_type():
    # A list or dict where a scalar belongs must degrade to None, not raise.
    assert LiveSnapshot.model_validate({"isOnline": ["x"]}).is_online is None
    assert LiveSnapshot.model_validate({"defCreateTime": ["x"]}).def_create_time is None
