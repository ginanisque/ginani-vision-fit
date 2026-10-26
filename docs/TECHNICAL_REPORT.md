# Ginani VisionFit — technical report

**Status:** working prototype; production keypoint inference and human measurement validation are
not yet verified.

## Problem and users

VisionFit guides a customer through consent, height entry, and front/side/back image capture. It
aims to give garment specialists traceable body-landmark and measurement evidence rather than
presenting an unreviewed image-derived number as a tailoring measurement.

## System design

The React, TypeScript and Vite client is hosted as a static app on AWS Amplify. The Python/FastAPI
service runs in an AWS ECS Express Mode container. Neon Auth supplies browser identity; the API
verifies bearer tokens against its JWKS endpoint. Neon Postgres stores consent, capture metadata,
landmarks, versioned measurement paths, and result records. Capture binaries are kept in private
Neon Object Storage. The data flow and review/recapture loop are shown in
[`ARCHITECTURE.md`](./ARCHITECTURE.md).

The container pins `opencv-python-headless==5.0.0.93` (OpenCV 5.0.0). OpenCV handles image decode,
exposure and blur checks, framing evidence, and video sampling. MediaPipe Pose supplies posture and
turn-orientation landmarks. Measurement geometry uses administrator-published ordered COCO v6
keypoint paths; body outlines are used only for capture evidence and height-based scale calibration.
If keypoints or required segments are unavailable, the service blocks the affected estimate.

Roboflow is an optional, external keypoint provider. Calls are gated by an additional, per-session
customer opt-in, separate from the general capture and model-training consent. Segmentation is not
part of the measurement path. Provider API credentials and workflow identifiers are injected into
ECS from AWS Secrets Manager; the browser receives neither.

## Decisions, review, and safety

The capture workflow converts low-quality evidence into recapture requests and uncertain evidence
into human review. The estimate endpoint returns segment-level provenance, confidence, blocked paths,
and a targeted manual check. It always marks estimates as requiring review. Underbust circumference
remains manual until a separate closed keypoint loop is defined. A human tape measurement is still
required; the system has no validated accuracy claim or export approval path.

Customers can delete a capture session and its linked measurement table immediately. By default,
inactive sessions and linked measurement tables are removed after 30 days. The cleanup deletes
private objects before their database references and logs failures so a later run can retry.

## Deployment and operation

Build and local run commands are in [`../README.md`](../README.md). ECS and Amplify configuration,
Secrets Manager keys, update workflow, CORS settings, and live smoke tests are in
[`../deploy/AWS_DEPLOYMENT.md`](../deploy/AWS_DEPLOYMENT.md) and
[`../deploy/DEPLOY_CHECKLIST.md`](../deploy/DEPLOY_CHECKLIST.md). Database migrations are listed in
[`../service/migrations/README.md`](../service/migrations/README.md).

The deployment update script can target an existing ECS Express service using `ECS_SERVICE_ARN`.
It injects the Roboflow settings from Secrets Manager and sets the retention worker on. Production
must receive migration 008 and a new ECS deployment before the new consent schema and keypoint
configuration are active.

## Evaluation and limitations

Automated tests cover API authorization and consent, upload bounds, image-quality failure cases,
keypoint normalization/path execution, missing-path blocking, unit conversions, and frontend capture
behavior. They use synthetic fixtures and do not measure real-person accuracy. Posture, framing,
camera position, cord placement, height calibration and the measurement paths remain provisional.
No evaluation against professional tape measurements is available.

The reproducible test commands and evidence limitations are recorded in
[`EVALUATION.md`](./EVALUATION.md). Production endpoint reachability is not evidence that the remote
Roboflow workflow is configured or that an authenticated customer capture succeeds.
