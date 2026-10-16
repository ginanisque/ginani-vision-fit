# VisionFit Roboflow measurement models

VisionFit uses two complementary custom models. Generic COCO checkpoints are useful for experiments,
but they do not supply tailoring landmarks such as bust apex, underbust, natural waist, or floor level.

## Model pair

1. **RF-DETR Keypoint** — a custom skeleton for garment landmarks.
2. **RF-DETR Segmentation Medium** — a person/body-outline mask for front, side, and back evidence.

OpenCV and MediaPipe remain responsible for inexpensive capture quality, framing, orientation, and
posture gates. Roboflow predictions are measurement evidence, not automatically approved measurements.

## Keypoint annotation schema

Start with this versioned skeleton and keep left/right names explicit:

- crown, nape, left/right side-neck point
- left/right shoulder tip
- left/right bust apex, bust level centre, underbust level centre
- left/right waist, front/back waist centre
- left/right high hip, left/right full hip
- left/right elbow, wrist, crotch, knee, ankle, heel and floor contact

Annotate visibility and do not guess an occluded landmark. Label front, side, and back views separately.
Capture varied body shapes, skin tones, fitted garments, lighting, cameras, backgrounds, and clinically
safe/consented adult subjects. Keep each person in only one of train, validation, or test to prevent leakage.

## Segmentation annotation

Label the visible body/clothing silhouette as a single instance. Exclude shadows, loose background objects,
and helpers. Decide once whether hair and footwear belong to the mask; for body dimensions they normally do
not. Record that policy in the dataset version notes.

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

The backend stores trimmed structured model output in the analysis decision. A later normalization adapter
must map the exact Workflow output schema into `detected_landmarks` and silhouette geometry after the first
workflow versions are known.
