# VisionFit evaluation evidence

**Evidence date:** 26 October 2026

## Reproduce the automated checks

```bash
cd visionfit/service
./.venv/bin/python -m pytest -q

cd ../frontend
npm ci
npm test
npm run build
```

Latest local run: **84 backend tests passed; 54 frontend tests passed; TypeScript check and Vite
production build passed.** The backend environment uses OpenCV 5.0.0.93, which reports runtime
version 5.0.0.

Coverage includes dark and blurred images, consent and authorization rejection, the 20 MiB quality
upload limit, capture evidence, opt-in gating for Roboflow, ordered keypoint path execution,
missing-segment blocking, persistence contracts, and frontend opt-in/deletion interactions.
Fixtures are synthetic and unit/API-level; they are not representative of human body diversity or
real camera conditions.

## Browser test status

The Playwright end-to-end suite is configured as:

```bash
cd visionfit/frontend
npm run test:e2e
```

It could not launch Chromium in this environment because the system library `libnspr4.so` is
missing. Therefore this run provides no browser-level result. Re-run it in an environment with
Playwright's Linux browser dependencies installed and follow with real-device camera/MediaRecorder
testing.

## Measurement evaluation limits

- There are no professionally tape-measured adult labels or held-out participants in this evidence.
- No mean/median absolute error or tolerance-band coverage is claimed.
- Thresholds for exposure, blur, posture, framing, turn coverage, and image scale remain provisional.
- The keypoint and path tests establish code behavior, not model recall or measurement accuracy.
- Missing points block a measurement; underbust circumference is not automated.
- Every measurement estimate remains review-required. No export is enabled by this evaluation.

## Production status at evaluation

The current local environment reports the Roboflow keypoint workflow as configured and ready. The
public API previously reported keypoint inference disabled. Production could not be updated or
retested because this workspace could not complete AWS CLI authentication. Production readiness
must be rechecked after applying migration 008, updating the existing ECS Express service, and
running an authenticated opt-in capture with a test account.

This project does not include COOL; there is no COOL version, workload execution trace, or COOL
benchmark evidence.
