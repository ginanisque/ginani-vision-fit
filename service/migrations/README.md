# Neon database setup

1. Create a Neon project and copy both pooled and direct Postgres connection strings.
2. Store them server-side as `DATABASE_URL_POOLED` and `DATABASE_URL`; never expose either in a `VITE_*` variable.
3. Run migrations in numeric order in the Neon SQL Editor, or run:

   ```bash
   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/001_neon_setup.sql
   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/002_managed_auth_cleanup.sql
   ```

The schema stores structured data and private object-storage references. Body images and videos
should remain in private object storage rather than being stored as Postgres binary data.

VisionFit uses Neon Auth. The browser receives only the Neon Auth URL; the backend verifies bearer
tokens through `NEON_AUTH_JWKS_URL`, resolves `app_users`, and enforces the `admin` role. Configure
`VISIONFIT_BOOTSTRAP_ADMIN_EMAILS` before the first admin signs in. The Neon owner connection string
must never reach the browser.
