# VisionFit quality service (VF-0)

A local Python/FastAPI service with **verified, pinned OpenCV 5** that performs a
real exposure + blur quality check and returns a **recorded decision**
(`recapture` or `proceed`).

## Requirements

- Python 3.12 (the system here lacks `python3-venv`; see setup below).
- OpenCV 5.0.0.93 (pinned in `requirements.txt`). Do **not** substitute OpenCV 4.

## Setup

The workspace image does not have `python3-venv` (no `ensurepip`), so the venv is
created without pip and pip is bootstrapped from the official installer:

```bash
cd visionfit/service
python3 -m venv --without-pip .venv
curl -sSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
./.venv/bin/python /tmp/get-pip.py --quiet
./.venv/bin/python -m pip install -r requirements.txt
```

Verify OpenCV 5:

```bash
./.venv/bin/python -c "import cv2; print(cv2.__version__)"   # 5.0.0
```

## Optional: MediaPipe Pose (posture + turn coverage)

Posture, view orientation and full-turn coverage use MediaPipe Pose landmarks. It is
optional — without it those checks honestly return `unknown` and request human review.

Install **without its OpenCV dependency** so the pinned headless OpenCV 5 stays intact:

```bash
./.venv/bin/python -m pip install --no-deps mediapipe
./.venv/bin/python -m pip install absl-py flatbuffers sounddevice matplotlib
# download the pose model (not bundled)
mkdir -p models
curl -sL -o models/pose_landmarker_full.task \
  'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task'
```

`pip install mediapipe` (with deps) pulls `opencv-contrib-python`, which needs GUI
libraries and would break the headless OpenCV 5 pin — hence the `--no-deps` step.

## Run

```bash
cd visionfit/service
./.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

Endpoints:

- `GET  /api/health` — service + OpenCV version.
- `POST /api/quality` — multipart form: `view` (`front`|`side`) + `file` (image).
  Returns a decision record (VF-0, exposure + blur only).
- `POST /api/capture` — authenticated multipart form: `view` + `consent` + `file`. Consent-gated
  exposure/blur, contrast-silhouette framing, cord candidate and pose-landmark
  posture evidence (VF-2).
- `POST /api/turn-video` — authenticated multipart form: `consent` + `file` (video). Duration,
  sampled exposure/blur and pose-orientation turn coverage (VF-2).
- `GET  /api/decisions` — Neon-backed capture analyses (admin only).
- `GET  /api/measurements/definitions` — versioned backend measurement registry.
- `POST /api/measurement-tables` — create a pending measurement table for a subject.
- `GET  /api/measurement-tables/{id}` — retrieve a table in `mm`, `cm` or `in`.
- `PUT  /api/measurement-tables/{id}/measurements/{key}` — record an estimated or reviewed value.

## Test

```bash
cd visionfit/service
./.venv/bin/python -m pytest -q
```

## Notes

- Quality thresholds are **provisional** and not domain-approved.
- Framing/cord/posture are provisional candidates, not measurement/export approval;
  natural-waist placement, camera level/distance and anatomical completeness require
  human review.
- Posture and turn coverage need MediaPipe (see above); without it they return
  `unknown` and request review.
- Capture metadata, analyses, landmarks, and measurement tables are stored in Neon Postgres.
  Capture binaries are private Neon Object Storage objects; Postgres stores object keys and metadata.
- Values are stored canonically in millimetres; estimated values require confidence and admin review.

## AWS container

`Dockerfile` packages the pinned OpenCV 5 service, the optional MediaPipe Pose runtime and the
included task model. For a one-task ECS Express Mode deployment, frontend URL configuration,
health checks and first-test steps, see [`../deploy/AWS_DEPLOYMENT.md`](../deploy/AWS_DEPLOYMENT.md).

## Neon persistence

The Postgres migrations are in [`migrations`](migrations/).
See [`migrations/README.md`](migrations/README.md) for connection and setup instructions.
