# Deploy VisionFit's OpenCV API to AWS

This deploys the **processing API** as a container on Amazon ECS Express Mode. The frontend can
remain hosted separately and call this API. The service runs OpenCV 5, MediaPipe Pose and the
included pose model. It does not use a database: the decision log is in memory and resets when a
container restarts. Uploaded images are analyzed in memory; turn videos use a temporary file that
the API deletes after analysis.

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
- A bash-compatible terminal (WSL or Git Bash on Windows).

## Deploy the API

From the project folder, set the region and the two role ARNs. The default CORS origin permits a
local test frontend at `http://localhost:5173`; add the eventual frontend origin as a comma-separated
value. Then run the script:

```bash
export AWS_REGION=us-east-1
export ECS_EXECUTION_ROLE_ARN='arn:aws:iam::YOUR_ACCOUNT_ID:role/ecsTaskExecutionRole'
export ECS_INFRASTRUCTURE_ROLE_ARN='arn:aws:iam::YOUR_ACCOUNT_ID:role/ecsInfrastructureRoleForExpressServices'
export VISIONFIT_CORS_ORIGINS='http://localhost:5173'
bash visionfit/deploy/aws-ecs-express.sh
```

The script creates an ECR repository if needed, builds and pushes the service image, and asks ECS
Express Mode to create a one-task service with 1 vCPU, 2 GiB of memory and `/api/health` checks. It
prints no credentials.
Creating the load balancer and Fargate task can incur charges even during testing. Delete the ECS
Express Mode service and its associated resources when the test is over if you do not want it to
continue running.

When the deployment finishes, copy the service URL from the ECS console and check:

```bash
curl https://YOUR_SERVICE_HOST/api/health
```

The response should include `"status":"ok"` and OpenCV version `5.0.0`.

## Point the frontend at AWS

Before building the frontend, set `VITE_VISIONFIT_API_URL` to the API origin (no trailing slash):

```bash
cd visionfit/frontend
VITE_VISIONFIT_API_URL=https://YOUR_SERVICE_HOST npm run build
```

For Windows PowerShell, use `$env:VITE_VISIONFIT_API_URL="https://YOUR_SERVICE_HOST"` before
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

The deployment script is a **create** workflow for a new service name. Do not run it again to update
an existing service; use the ECS console's update workflow or add the documented ECS Express Mode
update command after the first deployment.
