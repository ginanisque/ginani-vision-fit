import asyncio
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.auth import SessionUser
from app.measurements import (
    DEFINITIONS,
    REGISTRY_VERSION,
    MeasurementValueRequest,
    MeasurementPathRequest,
    _from_mm,
    _to_mm,
    measurement_definitions,
    set_measurement_value,
    validate_measurement_path,
)


def run(awaitable):
    return asyncio.run(awaitable)


ADMIN = SessionUser(id=uuid4(), auth_subject="admin-test", email="admin@example.test", role="admin")


def test_registry_exposes_versioned_domain_definitions():
    body = run(measurement_definitions("all"))
    assert body["version"] == REGISTRY_VERSION
    assert len(body["definitions"]) == len(DEFINITIONS) == 14
    waist = next(item for item in body["definitions"] if item["key"] == "waist")
    assert waist["requiredViews"] == ["front", "back"]
    assert waist["path"] == "circumference"
    assert waist["requiredLandmarks"] == [
        "waist_left_side", "waist_center_front", "waist_right_side", "waist_center_back",
    ]


def test_measurements_use_millimetres_as_canonical_unit():
    assert _to_mm(72.5, "cm") == 725
    assert _from_mm(725, "cm") == 72.5
    assert _to_mm(10, "in") == 254
    assert _from_mm(254, "in") == 10


def test_estimate_requires_confidence_and_declared_views(monkeypatch):
    with pytest.raises(HTTPException) as missing_confidence:
        run(set_measurement_value(
            str(uuid4()), "front_shoulder",
            MeasurementValueRequest(value=38, method="calibrated_point_distance", source_views=["front"]),
            "cm", ADMIN,
        ))
    assert missing_confidence.value.status_code == 422

    class Result:
        def fetchone(self):
            return {"required_views": ["front"]}

    class Connection:
        def execute(self, *_args, **_kwargs):
            return Result()

    class ConnectionContext:
        def __enter__(self):
            return Connection()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr("app.measurements.connection", lambda: ConnectionContext())

    with pytest.raises(HTTPException) as wrong_view:
        run(set_measurement_value(
            str(uuid4()), "front_shoulder",
            MeasurementValueRequest(value=38, method="manual", source_views=["back"], confidence=0.5),
            "cm", ADMIN,
        ))
    assert wrong_view.value.status_code == 422


def test_unknown_measurement_is_404_without_database_access():
    with pytest.raises(HTTPException) as missing_measurement:
        run(set_measurement_value(
            str(uuid4()), "not-real",
            MeasurementValueRequest(value=10, method="manual", status="reviewed"),
            "cm", ADMIN,
        ))
    assert missing_measurement.value.status_code == 404


def test_ordered_surface_path_is_valid():
    validate_measurement_path(MeasurementPathRequest(
        path="surface", closed=False,
        ordered_points=["left_side_neck", "left_bust_apex", "left_front_waist_below_bust"],
        segment_views=["front", "front"],
        required_views=["front", "side"], calculation_method="surface_path",
    ))


@pytest.mark.parametrize("path_request,message", [
    (MeasurementPathRequest(path="straight", ordered_points=["a_point", "b_point", "c_point"], segment_views=["front", "front"], required_views=["front"], calculation_method="point_distance"), "exactly two"),
    (MeasurementPathRequest(path="circumference", closed=False, ordered_points=["left_side", "center_front", "right_side"], segment_views=["front", "front"], required_views=["front"], calculation_method="closed_surface_path"), "closed path"),
    (MeasurementPathRequest(path="surface", ordered_points=["same_point", "same_point"], segment_views=["front"], required_views=["front"], calculation_method="surface_path"), "once"),
])
def test_invalid_path_relationships_are_rejected(path_request, message):
    with pytest.raises(HTTPException, match=message):
        validate_measurement_path(path_request)
