"""API integration tests: the quality endpoint returns a recorded decision and
the decision log is append-only.
"""
from io import BytesIO

import cv2
import numpy as np
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _structured_image(mean: float = 128.0, amplitude: float = 60.0) -> np.ndarray:
    height, width = 300, 400
    yy, xx = np.mgrid[0:height, 0:width]
    rng = np.random.default_rng(0)
    image = mean + amplitude * np.sin(xx / 12.0) * np.sin(yy / 12.0) + rng.normal(0, 8, size=(height, width))
    return np.clip(image, 0, 255).astype(np.uint8)


def _png_bytes(image: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", image)
    assert ok
    return buf.tobytes()


def test_health_reports_opencv_5(monkeypatch) -> None:
    monkeypatch.setattr("app.main.database_health", lambda: True)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["opencv"].startswith("5.")


def test_cors_allows_local_frontend_origin() -> None:
    response = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_good_image_allows_proceed() -> None:
    response = client.post(
        "/api/quality",
        data={"view": "front"},
        files={"file": ("front.png", _png_bytes(_structured_image()), "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "proceed"
    assert body["view"] == "front"
    assert body["imageFingerprint"]["sha256"]
    assert body["provisionalThresholds"] is True


def test_blurry_image_requests_recapture() -> None:
    blurred = cv2.GaussianBlur(_structured_image(), (0, 0), 12)
    response = client.post(
        "/api/quality",
        data={"view": "side"},
        files={"file": ("side.png", _png_bytes(blurred), "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "recapture"
    assert any("blurry" in reason for reason in body["reasons"])


def test_dark_image_requests_recapture() -> None:
    dark = (_structured_image() * 0.07).astype(np.uint8)
    response = client.post(
        "/api/quality",
        data={"view": "front"},
        files={"file": ("front.png", _png_bytes(dark), "image/png")},
    )
    assert response.status_code == 200
    assert response.json()["decision"] == "recapture"


def test_invalid_view_rejected() -> None:
    response = client.post(
        "/api/quality",
        data={"view": "back"},
        files={"file": ("back.png", _png_bytes(_structured_image()), "image/png")},
    )
    assert response.status_code == 400


def test_undecodable_file_rejected() -> None:
    response = client.post(
        "/api/quality",
        data={"view": "front"},
        files={"file": ("front.txt", b"not an image", "text/plain")},
    )
    assert response.status_code == 400


def test_persisted_decisions_require_admin() -> None:
    assert client.get("/api/decisions").status_code == 401
