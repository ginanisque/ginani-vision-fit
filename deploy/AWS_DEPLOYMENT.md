# Deploy VisionFit's OpenCV API to AWS

This deploys the **processing API** as a container on Amazon ECS Express Mode. The frontend can
remain hosted separately and call this API. The service runs OpenCV 5 and MediaPipe Pose, verifies
Neon Auth JWTs, writes application data to Neon Postgres, and stores captures privately in Neon
Object Storage. ECS receives credentials from AWS Secrets Manager rather than from the image.
The VF-3 runtime calls the configured Roboflow keypoint Workflow and executes published ordered
COCO v6 paths; segmentation is optional and is never used as a measurement-point sequence.

## Why ECS Express Mode

AWS has closed App Runner to new customers. AWS recommends ECS Express Mode as the simple
container-based path; it provisions Fargate, a load balancer, health checks, scaling and networking.
This still creates billable AWS resources. For a short test, the deployment script fixes the service
at one task. Review the AWS estimate and grant terms before running it.

## Prerequisites

- An AWS account with the grant applied, in the region you intend to use.
- Docker Desktop (or Docker Engine) and AWS CLI v2 installed locally.
- AWS CLI credentials with permission to use ECR and ECS Express Mode.
- The IAM roles required by ECS Express Mode: `ecsTaskExecutionRole` and
  `ecsInfrastructureRoleForExpressServices`. Use the AWS console's ECS Express Mode setup guidance
  to create them if they are not already present.
- A Secrets Manager JSON secret whose execution role can read, containing these keys:
  `DATABASE_URL_POOLED`, `NEON_AUTH_BASE_URL`, `NEON_AUTH_JWKS_URL`,
  `AWS_ENDPOINT_URL_S3`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_REGION`, `S3_BUCKET`,
  `ROBOFLOW_ENABLED`, `ROBOFLOW_API_KEY`, `ROBOFLOW_WORKSPACE`, and
  `ROBOFLOW_KEYPOINT_WORKFLOW_ID`. Set `ROBOFLOW_ENABLED=true` only after the customer-facing
  Roboflow disclosure is deployed and the keypoint workflow has been verified.
- A bash-compatible terminal (WSL or Git Bash on Windows).

## Deploy the API

From the project folder, set the region and the two role ARNs. The default CORS origin permits a
local test frontend at `http://localhost:5173`; add the eventual frontend origin as a comma-separated
value. Then run the script:

```bash
export AWS_REGION=us-east-1
export ECS_EXECUTION_ROLE_ARN='arn:aws:iam::YOUR_ACCOUNT_ID:role/ecsTaskExecutionRole'
export ECS_INFRASTRUCTURE_ROLE_ARN='arn:aws:iam::YOUR_ACCOUNT_ID:role/ecsInfrastructureRoleForExpressServices'
export VISIONFIT_RUNTIME_SECRET_ARN='arn:aws:secretsmanager:REGION:ACCOUNT:secret:visionfit/runtime-RANDOM'
export VISIONFIT_BOOTSTRAP_ADMIN_EMAILS='your-admin@example.com'
export VISIONFIT_CORS_ORIGINS='https://visionfit.ginani.net,http://localhost:5173'
export VISIONFIT_RETENTION_DAYS=30
bash visionfit/deploy/aws-ecs-express.sh
```

The script creates an ECR repository if needed, builds and pushes the service image, and asks ECS
Express Mode to create or update a one-task service with 1 vCPU, 2 GiB of memory and `/api/health`
checks. It references individual JSON keys from Secrets Manager and prints no credentials. The execution
role must allow `secretsmanager:GetSecretValue` for this secret.
The script injects the Roboflow keypoint settings from the same secret and sets the data-retention
period. Capture photos are sent to the provider only after the customer separately opts in in the
consent screen. Capture sessions and linked measurement tables are deleted after 30 inactive days
by default; a customer can also delete them immediately from the review screen.
Creating the load balancer and Fargate task can incur charges even during testing. Delete the ECS
Express Mode service and its associated resources when the test is over if you do not want it to
continue running.

When the deployment finishes, copy the service URL from the ECS console and check:

```bash
curl https://gi-4bffebb94e7c42ebaa6094d36fde44ad.ecs.us-east-1.on.aws/api/health
```

The response should include `"status":"ok"` and OpenCV version `5.0.0`.

## Point the frontend at AWS

Before building the frontend, set `VITE_VISIONFIT_API_URL` to the API origin (no trailing slash):

```bash
cd visionfit/frontend
VITE_VISIONFIT_API_URL=https://gi-4bffebb94e7c42ebaa6094d36fde44ad.ecs.us-east-1.on.aws npm run build
```

For Windows PowerShell, use `$env:VITE_VISIONFIT_API_URL="https://gi-4bffebb94e7c42ebaa6094d36fde44ad.ecs.us-east-1.on.aws"` before
`npm run build`. The API must also allow the frontend's exact origin through
`VISIONFIT_CORS_ORIGINS`. Re-deploy the API with that origin before opening the browser app from a
different domain. Local development leaves the setting blank and continues to use Vite's `/api`
proxy.

## First test

Use your own test capture only after confirming consent is enabled in the interface. Test one front
photo, one side photo and one slow-turn video. Confirm the browser network requests go to the
AWS service and `/api/health` reports OpenCV 5. A successful check means the AWS-hosted service ran
the current provisional quality/framing/posture pipeline; it does not establish measurement
accuracy or approve a body profile. The thresholds still need validation against tape measurements.

For an existing service, set `ECS_SERVICE_ARN` to its ARN and rerun the same script; it invokes the
ECS Express Mode update operation instead of creating another service. Replacing ECS task secrets
requires a new deployment so tasks receive the latest secret values.
