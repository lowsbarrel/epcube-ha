import pytest

from custom_components.epcube.battery import BatteryEnergyAccumulator


def test_first_reading_only_anchors():
    acc = BatteryEnergyAccumulator()
    acc.update(10.0)
    assert acc.charged == 0.0
    assert acc.discharged == 0.0


def test_rise_is_charge_fall_is_discharge():
    acc = BatteryEnergyAccumulator()
    acc.update(10.0)
    acc.update(12.0)
    acc.update(11.0)
    assert acc.charged == 2.0
    assert acc.discharged == 1.0


def test_sub_threshold_wobble_is_ignored_but_batches_against_the_anchor():
    acc = BatteryEnergyAccumulator()
    acc.update(10.0)
    # Steps below MIN_DELTA_KWH register only once the running difference from the anchor passes it.
    acc.update(10.02)
    acc.update(10.04)
    assert acc.charged == 0.0
    acc.update(10.06)
    assert acc.charged == pytest.approx(0.06)
    assert acc.discharged == 0.0


def test_none_reading_is_a_no_op():
    acc = BatteryEnergyAccumulator()
    acc.update(10.0)
    acc.update(None)
    acc.update(12.0)
    assert acc.charged == 2.0
