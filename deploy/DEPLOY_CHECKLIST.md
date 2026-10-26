# VisionFit — deployment checklist

Consolidated production settings. These live in the AWS console, **not** in committed
files: the server `.env` is gitignored. The deploy script supports creating a new service or
updating the existing service when `ECS_SERVICE_ARN` is set.

## Canonical URLs

| Role | URL |
| --- | --- |
| Frontend (Amplify) | `https://visionfit.ginani.net` |
| Backend API (ECS Express) | `https://gi-4bffebb94e7c42ebaa6094d36fde44ad.ecs.us-east-1.on.aws` |

## Settings to apply

### 1. Amplify — App settings → Environment variables

| Variable | Value |
| --- | --- |
| `VITE_VISIONFIT_API_URL` | `https://gi-4bffebb94e7c42ebaa6094d36fde44ad.ecs.us-east-1.on.aws` (no trailing slash) |
| `VITE_NEON_AUTH_URL` | the Neon Auth endpoint (same value as `NEON_AUTH_BASE_URL` in the server `.env`) |

Save, then **redeploy** so the values are baked into the next build.
The consent-aware frontend was published to the production Amplify `main` branch on 26 October
2026 and verified at the custom domain.

### 2. ECS — service → update → Environment variables

Before deploying the new API image, run Neon migrations 007 and 008 in order using the direct
connection, as documented in `service/migrations/README.md`.
For the production project, both migrations were applied and verified on 26 October 2026.

| Variable | Value |
| --- | --- |
| `VISIONFIT_CORS_ORIGINS` | `https://visionfit.ginani.net,http://localhost:5173` |
| `VISIONFIT_RETENTION_DAYS` | `30` |

In the Secrets Manager JSON secret referenced by ECS, set `ROBOFLOW_ENABLED` to `true` and confirm
the API key, workspace, and `ROBOFLOW_KEYPOINT_WORKFLOW_ID` belong to the intended deployed
keypoint workflow. The deployment script injects these keys from Secrets Manager. For this existing
service, set `ECS_SERVICE_ARN` to its ARN and run `aws-ecs-express.sh` to update the existing ECS
Express service and force tasks to load the new secret values. This mode does not create a second
service.

## Verification

1. `curl https://gi-4bffebb94e7c42ebaa6094d36fde44ad.ecs.us-east-1.on.aws/api/health`
   → `{"status":"ok","opencv":"5.0.0",...}`
2. Open `https://visionfit.ginani.net`, sign in, and submit one consented slow-turn video. Confirm the
   separate-photo fallback remains accessible.
3. Browser devtools → Network: requests hit the `gi-4bffebb...on.aws` host with no CORS errors.
4. `/api/health` reports `measurementVision.keypointsReady: true` without revealing the workflow ID.
5. In a test account, opt in to Roboflow keypoint processing and confirm all three captures return
   keypoint evidence. Then repeat without opting in and confirm no image is sent to Roboflow.

## References

- `AMPLIFY_HOSTING.md` — Amplify build, custom domain, SPA routing
- `AWS_DEPLOYMENT.md` — ECS Express Mode API deployment and first-test runbook
