# VisionFit Roboflow measurement models

VisionFit uses two complementary custom models. Generic COCO checkpoints are useful for experiments,
but they do not supply tailoring landmarks such as bust apex, underbust, natural waist, or floor level.

## Model pair

1. **RF-DETR Keypoint** — a custom skeleton for garment landmarks.
2. **RF-DETR Segmentation Medium** — a person/body-outline mask for front, side, and back evidence.

OpenCV and MediaPipe remain responsible for inexpensive capture quality, framing, orientation, and
posture gates. Roboflow predictions are measurement evidence, not automatically approved measurements.

## Keypoint annotation schema — COCO v6

The runtime uses the exact dataset keys; it does not translate silhouette labels into measurement
points. The v6 export contains:

```text
nape, center_front_neck, side_neck_left, side_neck_right,
bust_point_left, bust_point_right, underbust_left, underbust_right,
waist_below_bust_left, waist_below_bust_right,
waist_center_front, waist_center_back, waist_left_side, waist_right_side,
hip_center_front, hip_center_back, hip_side_right, hip_side_left,
bust_level_center_front, bust_level_center_back,
bust_level_left_side, bust_level_right_side,
across_chest_right, across_chest_left,
shoulder_point_left, shoulder_point_right,
knee_right, knee_left, ankle_left, ankle_right,
across_back_right, across_back_left,
elbow_right, wrist_right, elbow_left, wrist_left
```

The published bust path is:

```text
bust_level_left_side → bust_point_left → bust_level_center_front →
bust_point_right → bust_level_right_side → bust_level_center_back → close
```

The published hip path is:

```text
hip_side_left → hip_center_front → hip_side_right → hip_center_back → close
```

The v6 skeleton already contains these edges. `underbust_left/right` are point endpoints used by
bust radius (`bust_point_left → underbust_left`, with the right-side equivalent available). They do
not define an underbust circumference. No automated underbust-circumference path is published; that
measurement remains manual until a future dataset explicitly defines its complete loop.

Annotate visibility and do not guess an occluded landmark. Label front, side, and back views separately.
Capture varied body shapes, skin tones, fitted garments, lighting, cameras, backgrounds, and clinically
safe/consented adult subjects. Keep each person and all frames from the same source video in only one
of train, validation, or test. Copy `docs/subject_manifest.example.csv`, maintain one row per
source sequence with `source_group,subject_id,split`, then run:

```bash
cd visionfit/service
./.venv/bin/python scripts/validate_coco_dataset.py ../../dataset-training/your-export.zip \
  --manifest ../../dataset-training/subjects.csv
```

## Segmentation annotation and its limited role

Label the visible body/clothing silhouette as a single instance. It is used for capture evidence and
height-to-pixel calibration only. It is not an ordered measurement point and is not summed into bust,
waist, shoulder, or length paths.

## Runtime calculation

For each published definition, the service loads its ordered point names, connects each adjacent pair
in the administrator-assigned segment view, closes circumference loops, converts pixels to
millimetres using per-view height calibration, and returns every segment as evidence. If no permitted
view contains both endpoints, that measurement is blocked.

When output contains several people, the runtime selects one complete primary instance before
normalizing points; it never combines high-confidence points from different people.

## Validation

Evaluate by view and landmark, not only one aggregate score:

- keypoint pixel error normalized by subject height;
- visibility/confidence calibration;
- mask IoU and boundary error at bust, waist, hip, knee, and ankle levels;
- repeatability across repeated captures;
- millimetre error against independently collected tape/scan ground truth;
- failure rates across body-shape and skin-tone cohorts.

Do not release automated values until a held-out validation set establishes acceptable error limits for each
measurement. Until then, estimates stay review-only.

## Connect trained workflows

Create one Roboflow Workflow for each trained model and configure the backend only:

```text
ROBOFLOW_ENABLED=true
ROBOFLOW_API_KEY=...
ROBOFLOW_WORKSPACE=...
ROBOFLOW_KEYPOINT_WORKFLOW_ID=...
ROBOFLOW_SEGMENTATION_WORKFLOW_ID=...
```

The API key must stay in the backend secret store, never in Vite or browser variables. Add these fields to the
AWS Secrets Manager runtime secret before redeploying ECS. Enabling hosted processing uploads consented
captures to Roboflow, so update the privacy notice, retention terms, and data-processing agreement first.

The backend normalizes common Workflow keypoint output shapes into the exact v6 names, stores detected
tailoring points, and executes the currently published path version. `front_silhouette`,
`side_silhouette`, and `back_silhouette` are legacy geometry terms and must not be added to a path.
