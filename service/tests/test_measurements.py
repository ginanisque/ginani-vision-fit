import asyncio
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.auth import SessionUser
from app.measurements import (
    DEFINITIONS,
    REGISTRY_VERSION,
    MeasurementValueRequest,
    _from_mm,
    _to_mm,
    measurement_definitions,
    set_measurement_value,
)


def run(awaitable):
    return asyncio.run(awaitable)


ADMIN = SessionUser(id=uuid4(), auth_subject="admin-test", email="admin@example.test", role="admin")


def test_registry_exposes_versioned_domain_definitions():
    body = run(measurement_definitions("all"))
    assert body["version"] == REGISTRY_VERSION
    assert len(body["definitions"]) == len(DEFINITIONS) == 13
    waist = next(item for item in body["definitions"] if item["key"] == "waist")
    assert waist["requiredViews"] == ["front", "side", "back"]
    assert waist["path"] == "circumference"


def test_measurements_use_millimetres_as_canonical_unit():
    assert _to_mm(72.5, "cm") == 725
    assert _from_mm(725, "cm") == 72.5
    assert _to_mm(10, "in") == 254
    assert _from_mm(254, "in") == 10


def test_estimate_requires_confidence_and_declared_views():
    with pytest.raises(HTTPException) as missing_confidence:
        run(set_measurement_value(
            str(uuid4()), "front_shoulder",
            MeasurementValueRequest(value=38, method="calibrated_point_distance", source_views=["front"]),
            "cm", ADMIN,
        ))
    assert missing_confidence.value.status_code == 422

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
