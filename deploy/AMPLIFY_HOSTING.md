# Host the VisionFit frontend with AWS Amplify

The public landing page and authenticated capture app are one Vite application. Amplify builds
`frontend/` using the repository-level `amplify.yml` and publishes its `dist/` directory.

## Target

- Public URL: `https://visionfit.ginani.net`
- Repository: `https://github.com/ginanisque/ginani-vision-fit`
- Production branch: `main`
- App root: `frontend`
- Backend API: the existing VisionFit ECS Express service

This is one website: the custom subdomain is the public address of the Amplify deployment, not a
second deployment.

## Deployment-user permissions

The CLI identity that creates the hosting app needs Amplify access and, when managing the custom
domain's Route 53 records, limited DNS access. A deployment administrator can attach a temporary
customer-managed policy like this and remove it after setup:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ManageVisionFitAmplifyHosting",
      "Effect": "Allow",
      "Action": "amplify:*",
      "Resource": "*"
    },
    {
      "Sid": "ManageVisionFitDns",
      "Effect": "Allow",
      "Action": [
        "route53:ListHostedZones",
        "route53:ListHostedZonesByName",
        "route53:GetHostedZone",
        "route53:ListResourceRecordSets",
        "route53:ChangeResourceRecordSets",
        "route53:GetChange"
      ],
      "Resource": "*"
    }
  ]
}
```

For tighter production permissions, restrict `route53:ChangeResourceRecordSets` to the hosted-zone
ARN after its ID is known.

## Amplify environment variables

Configure these in Amplify Hosting under **App settings → Environment variables**:

```text
VITE_VISIONFIT_API_URL=https://YOUR_ECS_SERVICE_HOST
VITE_NEON_AUTH_URL=https://YOUR_NEON_AUTH_HOST
```

Both values become part of the browser build. Never put the Neon database URL, storage access
keys, JWT secrets, or AWS credentials in an Amplify frontend environment variable.

## Custom domain

In Amplify Hosting, open **Hosting → Custom domains**, add `ginani.net`, and map the
`visionfit` subdomain to the production branch. Amplify provisions the HTTPS certificate. If the
domain is hosted in Route 53, Amplify can configure the DNS records; otherwise copy the displayed
verification and CNAME records to the DNS provider for `ginani.net`.

Add the final frontend origin to the API configuration exactly as follows and update the ECS
service:

```text
VISIONFIT_CORS_ORIGINS=https://visionfit.ginani.net,http://localhost:5173
```

## SPA routing

If client-side routes are added later, configure an Amplify rewrite from `/<*>` to `/index.html`
with status `200`. The current interface uses a single document and does not require a rewrite.

## Release check

1. Confirm the Amplify build is green and the custom domain certificate is issued.
2. Open the landing page and verify the banner, logo, measurement image, and favicons.
3. Select **Start VisionFit**, create or sign in to a test account, and complete one consented test capture.
4. Confirm browser requests use the ECS HTTPS hostname and do not fail CORS.
5. Sign in as the configured bootstrap administrator and verify the admin workspace is hidden from customers.
