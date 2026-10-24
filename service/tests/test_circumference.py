import math

import pytest

import numpy as np

from app.circumference import CORE_KEYS, _apply_profile, _width_at, ellipse_perimeter


def test_ellipse_perimeter_is_circle_when_width_equals_depth():
    assert ellipse_perimeter(400, 400) == pytest.approx(math.pi * 400)


def test_ellipse_perimeter_uses_both_front_width_and_side_depth():
    result = ellipse_perimeter(400, 300)
    assert 1090 < result < 1110


def test_ellipse_perimeter_is_symmetric():
    assert ellipse_perimeter(420, 280) == pytest.approx(ellipse_perimeter(280, 420))


def test_straight_width_is_direction_independent_and_ignores_detached_arms():
    mask = np.zeros((40, 100), np.uint8)
    mask[18:23, 30:71] = 255
    mask[18:23, 5:16] = 255
    mask[18:23, 85:96] = 255
    left_to_right = _width_at(mask, 20, 50)
    right_to_left = abs((30 + left_to_right - 1) - 30) + 1
    assert left_to_right == right_to_left == 41


def test_vf3_covers_the_twelve_core_registry_measurements():
    assert len(CORE_KEYS) == 12
    assert set(CORE_KEYS) == {
        "bust", "underbust", "bust_point", "bust_span", "bust_radius", "waist",
        "front_shoulder", "back_shoulder", "across_chest", "across_back",
        "nape_to_waist", "full_front_length",
    }


def test_versioned_profile_corrects_raw_geometry_and_exposes_mae():
    profile = {"factor": {"waist": 1.1}, "biasMm": {"waist": -20}, "maeMm": {"waist": 12}}
    value, mae = _apply_profile("waist", 800, profile, 45)
    assert value == pytest.approx(860)
    assert mae == 12


def test_profile_rejects_non_physical_corrections():
    with pytest.raises(ValueError, match="waist"):
        _apply_profile("waist", 800, {"factor": {"waist": -1}}, 45)
