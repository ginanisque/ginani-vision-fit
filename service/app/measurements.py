"""Versioned measurement registry and Neon-backed measurement tables.

Measurements are stored canonically in millimetres.  This module deliberately
separates the table contract from vision inference: capture analysis may propose
a value later, but it must also state its method, source views and confidence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .auth import SessionUser, require_admin
from .database import connection

Unit = Literal["mm", "cm", "in"]
View = Literal["front", "side", "back"]
Status = Literal["pending", "estimated", "reviewed", "unavailable"]

REGISTRY_VERSION = "1.4.0"
BODY_MEASUREMENT_POLICY = (
    "Exact body measurement — no garment ease or seam allowance. "
    "Ease is controlled in Pattern CAD."
)
IMAGE_PLANE_WARNING = (
    "Image-plane distances are not body-surface lengths or circumferences. "
    "A measurement value requires calibrated scale and the declared measurement path."
)


@dataclass(frozen=True)
class MeasurementDefinition:
    key: str
    display_name: str
    scope: Literal["core", "future"]
    category: str
    path: Literal["circumference", "straight", "surface"]
    required_views: tuple[View, ...]
    required_landmarks: tuple[str, ...]
    calculation: str
    pattern_cad_names: tuple[str, ...]
    pattern_cad_landmark: str | None


DEFINITIONS = (
    MeasurementDefinition("bust", "Bust", "core", "Circumference", "circumference", ("front", "side"), ("bust_level", "front_silhouette", "side_silhouette"), "calibrated_cross_section", ("bust", "full bust"), "bust"),
    MeasurementDefinition("underbust", "Underbust", "core", "Circumference", "circumference", ("front", "side"), ("underbust_level", "front_silhouette", "side_silhouette"), "calibrated_cross_section", ("under bust", "underbust"), "underBust"),
    MeasurementDefinition("bust_point", "Bust point length", "core", "Bust control", "surface", ("front",), ("side_neck_point", "bust_apex"), "surface_path", ("bust point", "bust point length"), None),
    MeasurementDefinition("bust_span", "Bust span", "core", "Bust control", "straight", ("front",), ("left_bust_apex", "right_bust_apex"), "calibrated_point_distance", ("bust span",), None),
    MeasurementDefinition("bust_radius", "Bust radius", "core", "Bust control", "straight", ("front", "side"), ("bust_apex", "underbust_point"), "calibrated_point_distance", ("bust radius",), None),
    MeasurementDefinition("waist", "Waist", "core", "Circumference", "circumference", ("front", "side", "back"), ("waist_cord", "front_silhouette", "side_silhouette"), "calibrated_cross_section", ("waist", "natural waist"), "waist"),
    MeasurementDefinition("front_shoulder", "Front shoulder", "core", "Upper body width", "straight", ("front",), ("left_shoulder", "right_shoulder"), "calibrated_point_distance", ("front shoulder", "shoulder width", "across shoulder"), "shoulder"),
    MeasurementDefinition("back_shoulder", "Back shoulder", "core", "Upper body width", "surface", ("back",), ("left_shoulder", "right_shoulder", "back_surface"), "surface_path", ("back shoulder",), "shoulder"),
    MeasurementDefinition("across_chest", "Across chest", "core", "Upper body width", "surface", ("front",), ("left_shoulder", "right_shoulder", "front_silhouette"), "surface_path", ("across chest", "chest width"), "acrossChest"),
    MeasurementDefinition("across_back", "Across back", "core", "Upper body width", "surface", ("back",), ("left_shoulder", "right_shoulder", "back_silhouette"), "surface_path", ("across back",), None),
    MeasurementDefinition("nape_to_waist", "Nape to waist", "core", "Vertical length", "straight", ("back",), ("nape", "waist_cord"), "calibrated_point_distance", ("nape to waist", "back length"), "napeToWaist"),
    MeasurementDefinition("full_front_length", "Full front length", "core", "Vertical length", "surface", ("front", "side"), ("side_neck_point", "chest_contour", "waist_cord"), "surface_path", ("full front length",), None),
    MeasurementDefinition("side_waist_to_knee", "Side waist to knee", "future", "Lower body length", "surface", ("side",), ("side_waist", "knee_level", "side_surface"), "surface_path", ("side waist to knee", "waist to knee"), "sideWaistToKnee"),
)
DEFINITION_BY_KEY = {definition.key: definition for definition in DEFINITIONS}


def _to_mm(value: float, unit: Unit) -> float:
    return value if unit == "mm" else value * 10 if unit == "cm" else value * 25.4


def _from_mm(value: float, unit: Unit) -> float:
    converted = value if unit == "mm" else value / 10 if unit == "cm" else value / 25.4
    return round(converted, 2)


class CreateTableRequest(BaseModel):
    subject_id: str = Field(min_length=1, max_length=200)
    capture_session_id: str | None = Field(default=None, max_length=100)
    unit: Unit = "cm"


class MeasurementValueRequest(BaseModel):
    value: float = Field(gt=0)
    unit: Unit = "cm"
    status: Literal["estimated", "reviewed"] = "estimated"
    method: str = Field(min_length=1, max_length=200)
    source_views: list[View] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)
    notes: str = Field(default="", max_length=1000)


router = APIRouter(prefix="/api", tags=["measurements"])


def _definition_json(definition: MeasurementDefinition) -> dict:
    data = asdict(definition)
    return {
        "key": data["key"],
        "displayName": data["display_name"],
        "scope": data["scope"],
        "category": data["category"],
        "path": data["path"],
        "requiredViews": list(data["required_views"]),
        "requiredLandmarks": list(data["required_landmarks"]),
        "calculation": data["calculation"],
        "patternCadNames": list(data["pattern_cad_names"]),
        "patternCadLandmark": data["pattern_cad_landmark"],
    }


def _load_table(table_id: str, unit: Unit) -> dict | None:
    with connection() as conn:
        table = conn.execute(
            """select mt.id, mt.registry_version, mt.created_at, mt.updated_at,
                      u.id customer_id, u.email customer_email
                 from measurement_tables mt join app_users u on u.id = mt.customer_id
                where mt.id = %s""",
            (table_id,),
        ).fetchone()
        if table is None:
            return None
        rows = conn.execute(
            """select d.key, d.display_name, d.scope, d.category, d.path::text,
                      d.required_views::text[], d.required_landmarks, d.calculation_method,
                      d.pattern_cad_names, d.pattern_cad_landmark,
                      v.value_mm, v.status::text, v.method, v.source_views::text[],
                      v.confidence, v.notes
                 from measurement_values v
                 join measurement_definitions d on d.key = v.measurement_key
                where v.table_id = %s
                order by d.created_at, d.key""",
            (table_id,),
        ).fetchall()
    return {
        "id": str(table["id"]),
        "subjectId": str(table["customer_id"]),
        "subjectEmail": table["customer_email"],
        "registryVersion": table["registry_version"],
        "createdAt": table["created_at"].isoformat(),
        "updatedAt": table["updated_at"].isoformat(),
        "unit": unit,
        "rows": [
            {
                "key": row["key"], "displayName": row["display_name"], "scope": row["scope"],
                "category": row["category"], "path": row["path"],
                "requiredViews": row["required_views"], "requiredLandmarks": row["required_landmarks"],
                "calculation": row["calculation_method"], "patternCadNames": row["pattern_cad_names"],
                "patternCadLandmark": row["pattern_cad_landmark"],
                "value": None if row["value_mm"] is None else _from_mm(float(row["value_mm"]), unit),
                "unit": unit, "status": row["status"], "method": row["method"],
                "sourceViews": row["source_views"],
                "confidence": None if row["confidence"] is None else float(row["confidence"]),
                "notes": row["notes"], "requiresReview": row["status"] != "reviewed",
            }
            for row in rows
        ],
    }


@router.get("/measurements/definitions")
async def measurement_definitions(scope: Literal["core", "future", "all"] = Query("all")) -> dict:
    selected = DEFINITIONS if scope == "all" else tuple(d for d in DEFINITIONS if d.scope == scope)
    return {
        "version": REGISTRY_VERSION,
        "bodyMeasurementPolicy": BODY_MEASUREMENT_POLICY,
        "warning": IMAGE_PLANE_WARNING,
        "definitions": [_definition_json(definition) for definition in selected],
    }


@router.post("/measurement-tables", status_code=201)
async def create_measurement_table(
    request: CreateTableRequest, admin: SessionUser = Depends(require_admin)
) -> dict:
    with connection() as conn:
        customer = conn.execute(
            "select id from app_users where id::text = %s or lower(email) = lower(%s)",
            (request.subject_id, request.subject_id),
        ).fetchone()
        if customer is None:
            raise HTTPException(404, "Customer not found; the customer must sign in first")
        if request.capture_session_id:
            capture = conn.execute(
                "select id from capture_sessions where id::text = %s and customer_id = %s",
                (request.capture_session_id, customer["id"]),
            ).fetchone()
            if capture is None:
                raise HTTPException(404, "Capture session not found for this person")
        table = conn.execute(
            """insert into measurement_tables
                    (customer_id, capture_session_id, registry_version, preferred_unit, created_by)
                 values (%s, %s, %s, %s, %s) returning id""",
            (customer["id"], request.capture_session_id, REGISTRY_VERSION, request.unit, admin.id),
        ).fetchone()
    return _load_table(str(table["id"]), request.unit)


@router.get("/measurement-tables/{table_id}")
async def get_measurement_table(
    table_id: str, unit: Unit = Query("cm"), _admin: SessionUser = Depends(require_admin)
) -> dict:
    table = _load_table(table_id, unit)
    if table is None:
        raise HTTPException(404, "Measurement table not found")
    return table


@router.put("/measurement-tables/{table_id}/measurements/{key}")
async def set_measurement_value(
    table_id: str,
    key: str,
    request: MeasurementValueRequest,
    unit: Unit = Query("cm"),
    admin: SessionUser = Depends(require_admin),
) -> dict:
    definition = DEFINITION_BY_KEY.get(key)
    if definition is None:
        raise HTTPException(404, "Unknown measurement key")
    unexpected_views = sorted(set(request.source_views) - set(definition.required_views))
    if unexpected_views:
        raise HTTPException(422, f"Views not declared for {key}: {', '.join(unexpected_views)}")
    if request.status == "estimated" and request.confidence is None:
        raise HTTPException(422, "Estimated measurements require confidence")
    reviewed = request.status == "reviewed"
    with connection() as conn:
        updated = conn.execute(
            """update measurement_values
                  set value_mm = %s, status = %s, method = %s, source_views = %s::capture_view[],
                      confidence = %s, notes = %s, reviewed_by = %s,
                      reviewed_at = case when %s then now() else null end
                where table_id = %s and measurement_key = %s returning id""",
            (round(_to_mm(request.value, request.unit), 3), request.status, request.method,
             list(dict.fromkeys(request.source_views)), request.confidence, request.notes,
             admin.id if reviewed else None, reviewed, table_id, key),
        ).fetchone()
        if updated is None:
            raise HTTPException(404, "Measurement table not found")
    return _load_table(table_id, unit)


@router.get("/admin/customers")
async def list_customers(_admin: SessionUser = Depends(require_admin)) -> dict:
    with connection() as conn:
        rows = conn.execute(
            """select u.id, u.email, u.display_name, u.role::text,
                      count(distinct cs.id) capture_count, max(cs.created_at) latest_capture_at
                 from app_users u left join capture_sessions cs on cs.customer_id = u.id
                where u.active
                group by u.id order by max(cs.created_at) desc nulls last, u.created_at desc"""
        ).fetchall()
    return {"customers": [
        {"id": str(row["id"]), "email": row["email"], "displayName": row["display_name"],
         "role": row["role"], "captureCount": row["capture_count"],
         "latestCaptureAt": row["latest_capture_at"].isoformat() if row["latest_capture_at"] else None}
        for row in rows
    ]}


@router.get("/admin/capture-sessions/{session_id}/measurement-analysis")
async def measurement_analysis(session_id: str, _admin: SessionUser = Depends(require_admin)) -> dict:
    """Explain whether each measurement has the capture evidence it declares."""
    with connection() as conn:
        session = conn.execute(
            "select id, height_mm from capture_sessions where id::text = %s", (session_id,),
        ).fetchone()
        if session is None:
            raise HTTPException(404, "Capture session not found")
        view_rows = conn.execute(
            "select distinct view::text view from capture_assets where session_id = %s", (session_id,),
        ).fetchall()
        landmark_rows = conn.execute(
            """select distinct dl.landmark_key from detected_landmarks dl
                 join analysis_runs ar on ar.id = dl.analysis_run_id where ar.session_id = %s""",
            (session_id,),
        ).fetchall()
    available_views = {row["view"] for row in view_rows}
    available_landmarks = {row["landmark_key"] for row in landmark_rows}
    analyses = []
    for definition in DEFINITIONS:
        missing_views = sorted(set(definition.required_views) - available_views)
        missing_landmarks = sorted(set(definition.required_landmarks) - available_landmarks)
        missing_calibration = session["height_mm"] is None
        status = "ready_for_estimation" if not missing_views and not missing_landmarks and not missing_calibration else "blocked"
        analyses.append({
            **_definition_json(definition), "status": status,
            "missingViews": missing_views, "missingLandmarks": missing_landmarks,
            "missingCalibration": missing_calibration,
            "message": "Required evidence is available; compute an estimate and send it for review."
                if status == "ready_for_estimation" else "Capture or landmark evidence is incomplete.",
        })
    return {
        "sessionId": session_id, "heightMm": float(session["height_mm"]) if session["height_mm"] else None,
        "availableViews": sorted(available_views), "availableLandmarks": sorted(available_landmarks),
        "readyCount": sum(item["status"] == "ready_for_estimation" for item in analyses),
        "blockedCount": sum(item["status"] == "blocked" for item in analyses),
        "measurements": analyses,
    }
