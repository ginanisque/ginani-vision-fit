"""VisionFit OpenCV service with Neon persistence, Auth, and private storage."""
from __future__ import annotations

import cv2
import numpy as np
import os
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .config import DEFAULT_THRESHOLDS
from .decisions import DecisionLog, build_decision
from .posture import estimate_pose, load_pose, view_orientation
from .auth import SessionUser, current_user, require_admin, router as auth_router
from .capture_store import (
    admin_capture_session, admin_capture_sessions, ensure_session, persist_analysis, recent_decisions,
    session_tailoring_keypoints,
)
from .database import database_health
from .measurements import REGISTRY_VERSION, persist_runtime_estimates, published_measurement_paths, router as measurements_router
from .roboflow import analyze_keypoint_capture, analyze_measurement_capture, configuration_status as roboflow_status
from .circumference import _apply_profile, _load_calibration_profile, estimate_back_measurements
from .path_estimation import calculate_ordered_path, normalize_keypoints, view_scale_mm_per_pixel

app = FastAPI(title="VisionFit quality service", version="0.1.0")
app.include_router(auth_router)
app.include_router(measurements_router)


@app.get("/")
def root() -> dict:
    return {
        "service": "Ginani VisionFit API",
        "status": "ok",
        "docs": "/docs",
        "health": "/api/health",
        "measurementDefinitions": "/api/measurements/definitions",
    }


def _cors_origins() -> list[str]:
    """Only allow browser origins explicitly configured for this deployment."""
    value = os.getenv(
        "VISIONFIT_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:5174,http://127.0.0.1:5174",
    )
    return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]

# Local development convenience: the Vite frontend proxies /api to this service,
# so CORS is a fallback only.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)

log = DecisionLog()

QUALITY_VIEWS = {"front", "side"}
CAPTURE_VIEWS = {"front", "side", "back"}
MIN_DIMENSION = 64


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "opencv": cv2.__version__, "database": "ok" if database_health() else "unavailable",
            "measurementVision": roboflow_status()}


@app.post("/api/quality")
async def quality(view: str = Form(...), file: UploadFile = File(...)) -> dict:
    if view not in QUALITY_VIEWS:
        raise HTTPException(status_code=400, detail="view must be 'front' or 'side'")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")

    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="could not decode image")

    if image.shape[0] < MIN_DIMENSION or image.shape[1] < MIN_DIMENSION:
        raise HTTPException(status_code=400, detail="image too small to evaluate")

    record = build_decision(view, image, data, DEFAULT_THRESHOLDS)
    log.append(record)
    return record


@app.get("/api/decisions")
def decisions(limit: int = 20, _admin: SessionUser = Depends(require_admin)) -> dict:
    return {"records": recent_decisions(limit)}


@app.get("/api/admin/capture-sessions")
def capture_sessions(limit: int = 100, _admin: SessionUser = Depends(require_admin)) -> dict:
    return {"sessions": admin_capture_sessions(limit)}


@app.get("/api/admin/capture-sessions/{session_id}")
def capture_session_detail(session_id: str, _admin: SessionUser = Depends(require_admin)) -> dict:
    detail = admin_capture_session(session_id)
    if detail is None:
        raise HTTPException(404, "Capture session not found")
    return detail

# VF-2 uses its own endpoint so VF-0's narrower contract remains compatible.
from .capture import capture_decision

MAX_CAPTURE_BYTES = 20 * 1024 * 1024


@app.post('/api/measurement-estimates')
async def measurement_estimates(
    consent: bool = Form(False), height_mm: float = Form(...),
    session_id: str | None = Form(None),
    front: UploadFile = File(...), side: UploadFile = File(...), back: UploadFile = File(...),
    user: SessionUser = Depends(current_user),
) -> dict:
    """Execute published ordered tailoring-keypoint paths across three calibrated views."""
    if not consent:
        raise HTTPException(403, 'Explicit consent is required before processing')
    if not 1000 <= height_mm <= 2500:
        raise HTTPException(422, 'Height must be between 1000 and 2500 mm')
    images = {}
    encoded = {}
    for view, upload in (("front", front), ("side", side), ("back", back)):
        data = await upload.read(MAX_CAPTURE_BYTES + 1)
        if len(data) > MAX_CAPTURE_BYTES:
            raise HTTPException(413, 'Image exceeds 20 MiB')
        image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR) if data else None
        if image is None or min(image.shape[:2]) < MIN_DIMENSION:
            raise HTTPException(400, 'Select decodable front, side and back images at least 64 pixels in each dimension')
        images[view] = image
        encoded[view] = data
    try:
        stored = session_tailoring_keypoints(user, session_id) if session_id else {}
    except PermissionError as error:
        raise HTTPException(404, str(error)) from error
    try:
        from concurrent.futures import ThreadPoolExecutor
        points_by_view = {
            view: normalize_keypoints(stored.get(view, []), images[view].shape[1], images[view].shape[0])
            for view in images
        }
        views_needing_inference = [view for view, points in points_by_view.items() if not points]
        predictions = {}
        if views_needing_inference:
            with ThreadPoolExecutor(max_workers=len(views_needing_inference)) as executor:
                futures = {view: executor.submit(analyze_keypoint_capture, encoded[view])
                           for view in views_needing_inference}
                predictions = {view: future.result() for view, future in futures.items()}
            for view, prediction in predictions.items():
                if prediction.get("status") == "complete":
                    points_by_view[view] = normalize_keypoints(
                        prediction["output"], images[view].shape[1], images[view].shape[0],
                    )
        failures = {
            view: prediction.get("error", prediction.get("reason", "keypoint workflow unavailable"))
            for view, prediction in predictions.items() if prediction.get("status") != "complete"
        }
        if not any(points_by_view.values()):
            reason = "; ".join(f"{view}: {message}" for view, message in failures.items())
            raise HTTPException(503, "Tailoring keypoints are unavailable. " + reason)
        scales = {}
        scale_failures = {}
        for view, image in images.items():
            try:
                scales[view] = view_scale_mm_per_pixel(image, height_mm)
            except ValueError as error:
                scale_failures[view] = str(error)
        results = [calculate_ordered_path(path, points_by_view, scales) for path in published_measurement_paths()]
        estimated = [result for result in results if result["status"] == "estimated"]
        blocked = [result for result in results if result["status"] == "blocked"]
        profile = _load_calibration_profile()
        measurements = []
        persisted_estimates = []
        for result in estimated:
            default_mae = 45.0 if result["pathType"] == "circumference" else 30.0
            value_mm, uncertainty_mm = _apply_profile(result["key"], result["valueMm"], profile, default_mae)
            persisted_estimates.append({**result, "valueMm": round(value_mm, 2)})
            measurements.append({
                "key": result["key"], "displayName": result["displayName"],
                "value": round(value_mm / 10, 1), "unit": "cm",
                "rawValueMm": result["valueMm"], "uncertaintyMm": round(uncertainty_mm, 1),
                "confidence": result["confidence"], "requiresReview": True,
                "sourceViews": result["sourceViews"], "provenance": "published ordered tailoring-keypoint path",
                "orderedPoints": result["orderedPoints"], "segments": result["segments"],
                "pathVersion": result["pathVersion"], "pathVersionId": result["pathVersionId"],
            })
        persistence = (persist_runtime_estimates(user=user, session_id=session_id,
                                                 estimates=persisted_estimates,
                                                 model_version=profile["version"])
                       if session_id else None)
        target = min(measurements, key=lambda item: item["confidence"]) if measurements else None
        if blocked:
            action = "Recapture or correct the view-specific keypoints listed under blocked measurements."
            manual_check = {"key": blocked[0]["key"], "displayName": blocked[0]["displayName"],
                            "reason": "Missing required segment evidence"}
        else:
            action = f"Confirm {target['displayName']} with a tape." if target else "No automated paths are available."
            manual_check = ({"key": target["key"], "displayName": target["displayName"],
                             "reason": "Lowest keypoint confidence"} if target else
                            {"key": "capture", "displayName": "Capture", "reason": "No automated paths"})
        return {
            "status": "review_required", "modelVersion": profile["version"],
            "keypointWorkflowVersion": os.getenv("ROBOFLOW_KEYPOINT_WORKFLOW_ID") or "stored-capture-points",
            "registryVersion": REGISTRY_VERSION, "method": "published ordered tailoring-keypoint paths + calibration profile",
            "warning": "Keypoint path lengths are review-only until validated against professional tape measurements.",
            "orientations": {"front": "front", "side": "side", "back": "back"},
            "levels": {"front": {}, "side": {}, "back": {}},
            "trainingFeatures": {"heightMm": height_mm, "rawMeasurementsMm": {item["key"]: item["rawValueMm"] for item in measurements}},
            "recommendedAction": action, "targetedManualCheck": manual_check,
            "measurements": measurements, "blockedMeasurements": blocked,
            "detectedKeypoints": {view: sorted(points) for view, points in points_by_view.items()},
            "predictionFailures": failures, "scaleFailures": scale_failures,
            **(persistence or {}),
        }
    except HTTPException:
        raise
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.post('/api/capture')
async def capture(
    view: str = Form(...), consent: bool = Form(False), session_id: str | None = Form(None),
    height_mm: float | None = Form(None), file: UploadFile = File(...),
    user: SessionUser = Depends(current_user),
) -> dict:
    if not consent:
        raise HTTPException(403, 'Explicit consent is required before processing')
    if view not in CAPTURE_VIEWS:
        raise HTTPException(400, 'view must be front, side or back')
    data = await file.read(MAX_CAPTURE_BYTES + 1)
    if len(data) > MAX_CAPTURE_BYTES:
        raise HTTPException(413, 'Image exceeds 20 MiB')
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR) if data else None
    if image is None or min(image.shape[:2]) < MIN_DIMENSION:
        raise HTTPException(400, 'Select a decodable image at least 64 pixels in each dimension')
    record = capture_decision(view, image, data)
    record["measurementVision"] = analyze_measurement_capture(data)
    keypoint_model = record["measurementVision"].get("models", {}).get("keypoints", {})
    if keypoint_model.get("status") == "complete":
        tailoring_points = normalize_keypoints(keypoint_model.get("output", {}), image.shape[1], image.shape[0])
        record.setdefault("evidence", []).extend({
            "kind": "tailoring-keypoint", "label": point.key, "confidence": point.confidence,
            "box": {"x": round(point.x), "y": round(point.y), "width": 2, "height": 2},
        } for point in tailoring_points.values())
    try:
        capture_session_id = ensure_session(user, session_id, height_mm)
    except PermissionError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    persisted = persist_analysis(
        user=user, session_id=capture_session_id, view=view, data=data,
        content_type=file.content_type or "application/octet-stream", record=record,
        width=image.shape[1], height=image.shape[0],
    )
    record.update(persisted)
    log.append(record)
    return record

# A slow turn is analysed by sampling a fixed number of frames across the clip, so
# the user does not need to time the recording precisely. This generous cap only
# rejects absurdly long uploads (the 50 MiB upload limit applies separately).
MAX_TURN_SECONDS = 90.0


def turn_coverage(reader, count: float, duration: float, height_mm: float | None = None) -> dict:
    """Sample frames across a turn clip and derive view-orientation coverage."""
    pose = load_pose()
    model_available = pose is not None
    seen: set[str] = set()
    orientations = []
    back_measurements = None
    best_back_visibility = -1.0
    for i in range(20):
        fraction = (i + 0.5) / 20.0
        reader.set(cv2.CAP_PROP_POS_FRAMES, int(count * fraction))
        ok, frame = reader.read()
        if not ok:
            continue
        landmarks = estimate_pose(frame, pose)
        orientation = view_orientation(landmarks) if landmarks else 'unknown'
        if orientation == 'back' and landmarks and height_mm is not None:
            visibility = min(
                landmarks[name].visibility
                for name in ('left_shoulder', 'right_shoulder', 'left_hip', 'right_hip')
            )
            if visibility > best_back_visibility:
                try:
                    back_measurements = estimate_back_measurements(frame, height_mm, landmarks)
                    back_measurements['timeSeconds'] = round(duration * fraction, 2)
                    best_back_visibility = visibility
                except ValueError:
                    pass
        if orientation != 'unknown':
            seen.add(orientation)
        orientations.append(dict(timeSeconds=round(duration * fraction, 2), orientation=orientation))

    required = {'front', 'back', 'side'}
    missing = sorted(required - seen)
    if not model_available:
        status = 'unknown'
    elif not missing:
        status = 'complete'
    else:
        status = 'incomplete'
    return dict(
        status=status,
        seenViews=sorted(seen),
        missingViews=missing,
        orientations=orientations,
        method='pose-landmark orientation' if model_available else 'pose model unavailable',
        backMeasurements=back_measurements,
    )


@app.post('/api/turn-video')
async def turn_video(
    consent: bool = Form(False), session_id: str | None = Form(None),
    height_mm: float | None = Form(None),
    file: UploadFile = File(...), user: SessionUser = Depends(current_user),
) -> dict:
    """Bounded local video inspection; temporary source is always deleted."""
    import hashlib
    import os
    import tempfile
    import uuid
    from datetime import datetime, timezone
    if not consent:
        raise HTTPException(403, 'Explicit consent is required before processing')
    data = await file.read(50 * 1024 * 1024 + 1)
    if len(data) > 50 * 1024 * 1024:
        raise HTTPException(413, 'Video exceeds 50 MiB')
    path = None
    reader = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.video', delete=False) as tmp:
            path = tmp.name
            tmp.write(data)
        reader = cv2.VideoCapture(path)
        fps = float(reader.get(cv2.CAP_PROP_FPS))
        count = float(reader.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = count / fps if fps > 0 else 0
        if not reader.isOpened() or not np.isfinite(duration) or duration <= 0:
            raise HTTPException(400, 'Video cannot be decoded; try MP4 or WebM')
        if duration > MAX_TURN_SECONDS:
            raise HTTPException(400, f'Video is too long to process; record one slow turn (maximum {int(MAX_TURN_SECONDS)} seconds).')
        samples = []
        for fraction in (.1, .3, .5, .7, .9):
            reader.set(cv2.CAP_PROP_POS_FRAMES, int(count * fraction))
            ok, frame = reader.read()
            if not ok: continue
            from .quality import evaluate_quality
            result = evaluate_quality(frame)
            samples.append(dict(timeSeconds=round(duration*fraction, 2),
                                quality='pass' if result.passed else 'fail', reasons=list(result.reasons)))

        coverage = turn_coverage(reader, count, duration, height_mm)

        recapture = len(samples) != 5 or any(s['quality'] == 'fail' for s in samples)
        reasons = []
        if len(samples) != 5 or any(s['quality'] == 'fail' for s in samples):
            reasons.append('One or more sampled video frames are missing, blurry or poorly exposed; record again.')
        if coverage['status'] == 'incomplete':
            recapture = True
            reasons.append('The turn does not show a full rotation: missing ' + ', '.join(coverage['missingViews']) + '.')
        elif coverage['status'] == 'complete':
            reasons.append('The turn shows front, side and back. Confirm it is a single continuous turn with neutral posture.')
        else:
            reasons.append('Rotation completeness could not be verified automatically; a reviewer must confirm a full turn.')

        record = dict(id=str(uuid.uuid4()), view='turn', decision='recapture' if recapture else 'review',
                      imageFingerprint=dict(sha256=hashlib.sha256(data).hexdigest()),
                      checkedAt=datetime.now(timezone.utc).isoformat(), durationSeconds=round(duration,2),
                      samples=samples, turnCoverage=coverage, reasons=reasons,
                      scope='Sampled exposure/blur and pose-orientation turn coverage across the clip. '
                            'Posture quality and single-continuous-turn confirmation still require review.',
                      provisionalThresholds=True)
        try:
            capture_session_id = ensure_session(user, session_id)
        except PermissionError as error:
            raise HTTPException(404, str(error)) from error
        record.update(persist_analysis(
            user=user, session_id=capture_session_id, view="turn", data=data,
            content_type=file.content_type or "application/octet-stream", record=record,
            duration_seconds=duration,
        ))
        log.append(record)
        return record
    finally:
        if reader is not None: reader.release()
        if path: os.unlink(path)
