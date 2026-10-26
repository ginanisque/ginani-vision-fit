# VisionFit architecture

```mermaid
flowchart LR
    Person[Customer / reviewer browser]
    Amplify[AWS Amplify<br/>React + TypeScript + Vite]
    Auth[Neon Auth<br/>sign-in and browser token]
    ECS[AWS ECS Express Mode<br/>FastAPI + OpenCV 5 + MediaPipe]
    CV[OpenCV capture checks<br/>quality, framing, video]
    Provider[Roboflow keypoint workflow<br/>only after separate opt-in]
    DB[(Neon Postgres<br/>users, consent, paths, results)]
    Store[(Private Neon Object Storage<br/>capture photos and videos)]
    Retention[Retention worker<br/>30 inactive days by default]

    Person --> Amplify
    Amplify <--> Auth
    Amplify -->|bearer-authenticated, consented uploads| ECS
    ECS -->|verify JWT using JWKS| Auth
    ECS --> CV
    CV -->|quality decision / evidence| ECS
    ECS -->|opt-in images only| Provider
    Provider -->|keypoints and confidence| ECS
    ECS -->|persist metadata and estimates| DB
    ECS -->|private image/video objects| Store
    DB --> Retention
    Retention -->|delete expired session rows| DB
    Retention -->|delete corresponding objects| Store
```

## Decision and action loop

1. OpenCV checks exposure, blur, framing and capture evidence. A failed capture asks for a retake;
   uncertain posture or framing requests human review.
2. If the customer separately opts in, the service sends capture images to the Roboflow keypoint
   workflow. The stored keypoints and their confidence become input to the administrator-published,
   versioned COCO v6 measurement paths.
3. A missing keypoint segment blocks the affected value and identifies the view/segment to correct.
   Successful path execution still returns `review_required`; it never approves a body profile.
4. Measurement estimates must be checked with a tape. No accuracy claim or export approval is
   inferred from passing image-quality checks.

The measurement path is deterministic orchestration over computer-vision output; it is not a
general-purpose autonomous agent. No COOL component is part of the current workload.
