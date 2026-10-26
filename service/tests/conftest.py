"""Keep the backend test suite independent of the developer's local ``.env``.

``app.main`` reads ``VISIONFIT_CORS_ORIGINS`` once at import time to build its
CORS allow-list. A developer's local ``.env`` can override that value, which
would flip ``test_cors_allows_local_frontend_origin`` and, more generally, let
machine-local state change test results. Pinning the value here — before any
application module is imported — keeps the suite hermetic: ``load_dotenv``
never overrides an environment variable that is already set.
"""

import os

os.environ.setdefault(
    "VISIONFIT_CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174",
)
os.environ.setdefault("ROBOFLOW_ENABLED", "false")
os.environ.setdefault("VISIONFIT_RETENTION_ENABLED", "false")
