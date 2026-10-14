"""VisionFit OpenCV processing service.

Exposes consent-gated photo and video checks, plus the original quality endpoint.
The decision log is in-memory; captures are analyzed but not persisted.
"""
from __future__ import annotations

import cv2
import numpy as np
import os
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .config import DEFAULT_THRESHOLDS
from .decisions import DecisionLog, build_decision
from .posture import estimate_pose, load_pose, view_orientation

app = FastAPI(title="VisionFit quality service", version="0.1.0")


def _cors_origins() -> list[str]:
    """Only allow browser origins explicitly configured for this deployment."""
    value = os.getenv("VISIONFIT_CORS_ORIGINS", "http://localhost:5173")
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

VALID_VIEWS = {"front", "side"}
MIN_DIMENSION = 64


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "opencv": cv2.__version__}


@app.post("/api/quality")
async def quality(view: str = Form(...), file: UploadFile = File(...)) -> dict:
    if view not in VALID_VIEWS:
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
def decisions(limit: int = 20) -> dict:
    return {"records": log.list(limit)}

# VF-2 uses its own endpoint so VF-0's narrower contract remains compatible.
from .capture import capture_decision

MAX_CAPTURE_BYTES = 20 * 1024 * 1024


@app.post('/api/capture')
async def capture(view: str = Form(...), consent: bool = Form(False), file: UploadFile = File(...)) -> dict:
    if not consent:
        raise HTTPException(403, 'Explicit consent is required before processing')
    if view not in VALID_VIEWS:
        raise HTTPException(400, 'view must be front or side')
    data = await file.read(MAX_CAPTURE_BYTES + 1)
    if len(data) > MAX_CAPTURE_BYTES:
        raise HTTPException(413, 'Image exceeds 20 MiB')
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR) if data else None
    if image is None or min(image.shape[:2]) < MIN_DIMENSION:
        raise HTTPException(400, 'Select a decodable image at least 64 pixels in each dimension')
    record = capture_decision(view, image, data)
    log.append(record)
    return record

# A slow turn is analysed by sampling a fixed number of frames across the clip, so
# the user does not need to time the recording precisely. This generous cap only
# rejects absurdly long uploads (the 50 MiB upload limit applies separately).
MAX_TURN_SECONDS = 90.0


def turn_coverage(reader, count: float, duration: float) -> dict:
    """Sample frames across a turn clip and derive view-orientation coverage."""
    pose = load_pose()
    model_available = pose is not None
    seen: set[str] = set()
    orientations = []
    for i in range(20):
        fraction = (i + 0.5) / 20.0
        reader.set(cv2.CAP_PROP_POS_FRAMES, int(count * fraction))
        ok, frame = reader.read()
        if not ok:
            continue
        landmarks = estimate_pose(frame, pose)
        orientation = view_orientation(landmarks) if landmarks else 'unknown'
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
    )


@app.post('/api/turn-video')
async def turn_video(consent: bool = Form(False), file: UploadFile = File(...)) -> dict:
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

        coverage = turn_coverage(reader, count, duration)

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
        log.append(record)
        return record
    finally:
        if reader is not None: reader.release()
        if path: os.unlink(path)
