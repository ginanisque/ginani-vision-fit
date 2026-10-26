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
- `POST /api/quality` — authenticated multipart form: `view` (`front`|`side`) + `consent` + `file`
  (image). Returns a decision record (VF-0, exposure + blur only; 20 MiB limit).
- `POST /api/capture` — authenticated multipart form: `view` + `consent` + `file`. Consent-gated
  exposure/blur, contrast-silhouette framing, cord candidate and pose-landmark
  posture evidence (VF-2).
- `POST /api/turn-video` — authenticated multipart form: `consent` + `file` (video). Duration,
  sampled exposure/blur and pose-orientation turn coverage (VF-2).
- `POST /api/measurement-estimates` — authenticated multipart form: `consent`, `height_mm`,
  `external_vision_consent`, `front`, `side`, and `back`. Runs the tailoring-keypoint workflow only
  when the customer separately consents to Roboflow processing, executes each published
  ordered path, and returns segment evidence, confidence, blocked paths, and a targeted review
  action. With `session_id`, it reuses stored keypoints and persists candidates into the linked
  measurement table. It does not use silhouette labels as measurement points.
- `GET  /api/decisions` — Neon-backed capture analyses (admin only).
- `GET  /api/measurements/definitions` — versioned backend measurement registry.
- `POST /api/measurement-tables` — create a pending measurement table for a subject.
- `GET  /api/measurement-tables/{id}` — retrieve a table in `mm`, `cm` or `in`.
- `PUT  /api/measurement-tables/{id}/measurements/{key}` — record an estimated or reviewed value.
- `GET  /api/admin/measurement-paths` — list published and draft ordered keypoint paths.
- `PUT  /api/admin/measurement-paths/{key}/draft` — create or update an admin path draft.
- `POST /api/admin/measurement-paths/{key}/publish` — publish an immutable path version; existing
  measurement-table rows retain their original definition version.
- `DELETE /api/capture-sessions/{id}` — remove the authenticated caller's photos, analysis data and
  linked measurement table.

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
- Capture sessions and linked measurement tables are automatically deleted after 30 inactive days
  by default (`VISIONFIT_RETENTION_DAYS=30`), or sooner through the authenticated delete endpoint.
- Values are stored canonically in millimetres; estimated values require confidence and admin review.

## VF-3 calibration training

VF-3 runtime geometry is the sum of calibrated segments between annotated tailoring keypoints.
The body outline is used only to establish each view's pixel scale. Missing keypoint segments block
a measurement; the service never falls back silently to the old ellipse approximation.

The geometry estimator is intentionally separate from learned correction. Save professionally
measured labels in CSV columns named `raw_<measurement>_mm` and `tape_<measurement>_mm`, with one
row per consenting subject. Fit an auditable baseline profile with:

```bash
PYTHONPATH=. ./.venv/bin/python scripts/train_measurement_calibration.py labels.csv models/vf3-calibration.json
```

Set `VISIONFIT_MEASUREMENT_MODEL_PATH=models/vf3-calibration.json` when running the API. The API
returns the loaded model version and its observed MAE as uncertainty. Synthetic reference images
must not be included as accuracy labels.

Validate every COCO export before training. The validator rejects source-video leakage across
splits, fewer than 50 images, fewer than five manifested subjects, and missing subject provenance.
Start from `../docs/subject_manifest.example.csv`; every exported source group must have exactly one row:

```bash
./.venv/bin/python scripts/validate_coco_dataset.py ../../dataset-training/export.zip \
  --manifest ../../dataset-training/subjects.csv
```

## AWS container

`Dockerfile` packages the pinned OpenCV 5 service, the optional MediaPipe Pose runtime and the
included task model. For a one-task ECS Express Mode deployment, frontend URL configuration,
health checks and first-test steps, see [`../deploy/AWS_DEPLOYMENT.md`](../deploy/AWS_DEPLOYMENT.md).

## Neon persistence

The Postgres migrations are in [`migrations`](migrations/).
See [`migrations/README.md`](migrations/README.md) for connection and setup instructions.
