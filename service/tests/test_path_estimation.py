import pytest

from app.path_estimation import calculate_ordered_path, normalize_keypoints


def test_normalizes_nested_roboflow_keypoints():
    payload = {"predictions": [{"keypoints": [
        {"class_name": "bust_point_left", "x": 0.25, "y": 0.5, "confidence": 0.9},
        {"class_name": "bust_point_right", "x": 300, "y": 200, "confidence": 0.8},
    ]}]}
    points = normalize_keypoints(payload, 400, 600)
    assert points["bust_point_left"].x == 100
    assert points["bust_point_left"].y == 300
    assert points["bust_point_right"].x == 300


def test_executes_closed_bust_path_in_published_order():
    names = ["bust_level_left_side", "bust_point_left", "bust_level_center_front",
             "bust_point_right", "bust_level_right_side", "bust_level_center_back"]
    front = normalize_keypoints([{"name": name, "x": index * 10, "y": 10, "confidence": .9}
                                 for index, name in enumerate(names[:-1])], 100, 100)
    back = normalize_keypoints([
        {"name": "bust_level_right_side", "x": 50, "y": 10, "confidence": .8},
        {"name": "bust_level_center_back", "x": 25, "y": 10, "confidence": .8},
        {"name": "bust_level_left_side", "x": 0, "y": 10, "confidence": .8},
    ], 100, 100)
    result = calculate_ordered_path({
        "id": "bust-v2", "measurementKey": "bust", "displayName": "Bust", "version": 2,
        "path": "circumference", "closed": True, "orderedPoints": names,
        "segmentViews": ["front", "front", "front", "front", "back", "back"],
        "requiredViews": ["front", "back"],
    }, {"front": front, "back": back}, {"front": 2.0, "back": 2.0})
    assert result["status"] == "estimated"
    assert result["valueMm"] == pytest.approx(180)
    assert [segment["view"] for segment in result["segments"]][-2:] == ["back", "back"]


def test_blocks_instead_of_inventing_a_missing_segment():
    points = normalize_keypoints([{"name": "a_point", "x": 0, "y": 0}], 100, 100)
    result = calculate_ordered_path({
        "id": "test-v1", "measurementKey": "test", "displayName": "Test", "version": 1,
        "path": "straight", "closed": False, "orderedPoints": ["a_point", "b_point"],
        "segmentViews": ["front"],
        "requiredViews": ["front"],
    }, {"front": points}, {"front": 1.0})
    assert result["status"] == "blocked"
    assert result["missingSegments"] == [{"from": "a_point", "to": "b_point", "view": "front"}]


def test_selects_one_person_instead_of_mixing_instances():
    payload = {"predictions": [
        {"confidence": .7, "width": 50, "height": 100, "keypoints": [
            {"name": "a_point", "x": 10, "y": 10, "confidence": .99},
        ]},
        {"confidence": .9, "width": 100, "height": 200, "keypoints": [
            {"name": "a_point", "x": 70, "y": 20, "confidence": .8},
            {"name": "b_point", "x": 90, "y": 20, "confidence": .8},
        ]},
    ]}
    points = normalize_keypoints(payload, 100, 200)
    assert set(points) == {"a_point", "b_point"}
    assert points["a_point"].x == 70
