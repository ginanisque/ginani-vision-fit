"""Optional Roboflow Workflows boundary for measurement-oriented vision models.

This integration is deliberately disabled until the operator supplies workflow
IDs, an API key, and explicitly enables third-party processing. The current
OpenCV/MediaPipe capture checks remain the local baseline.
"""
from __future__ import annotations

import base64
import json
import os
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def configuration_status() -> dict:
    workspace = os.getenv("ROBOFLOW_WORKSPACE", "").strip()
    keypoint = os.getenv("ROBOFLOW_KEYPOINT_WORKFLOW_ID", "").strip()
    segmentation = os.getenv("ROBOFLOW_SEGMENTATION_WORKFLOW_ID", "").strip()
    has_key = bool(os.getenv("ROBOFLOW_API_KEY", "").strip())
    enabled = _truthy("ROBOFLOW_ENABLED")
    configured = bool(workspace and keypoint and segmentation and has_key)
    return {
        "enabled": enabled,
        "configured": configured,
        "provider": "roboflow_workflows",
        "keypointWorkflow": keypoint or None,
        "segmentationWorkflow": segmentation or None,
        "ready": enabled and configured,
        "reason": None if enabled and configured else (
            "Set ROBOFLOW_ENABLED=true after consent/privacy approval." if configured
            else "Roboflow workspace, API key, and both workflow IDs are required."
        ),
    }


def _trim(value, depth: int = 0):
    """Keep structured predictions while refusing large rendered-image payloads."""
    if depth > 8:
        return "[nested output omitted]"
    if isinstance(value, dict):
        return {
            str(key): _trim(item, depth + 1)
            for key, item in value.items()
            if str(key).lower() not in {"image", "visualization", "output_image", "base64"}
        }
    if isinstance(value, list):
        return [_trim(item, depth + 1) for item in value[:500]]
    if isinstance(value, str) and len(value) > 4000:
        return value[:4000] + "…"
    return value


def _run_workflow(workflow_id: str, image: bytes) -> dict:
    workspace = os.environ["ROBOFLOW_WORKSPACE"].strip()
    api_key = os.environ["ROBOFLOW_API_KEY"].strip()
    endpoint = f"https://serverless.roboflow.com/{workspace}/workflows/{workflow_id}"
    payload = json.dumps({
        "api_key": api_key,
        "inputs": {"image": {"type": "base64", "value": base64.b64encode(image).decode("ascii")}},
    }).encode("utf-8")
    request = Request(endpoint, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=45) as response:
            return {"status": "complete", "output": _trim(json.load(response))}
    except HTTPError as error:
        detail = error.read(1000).decode("utf-8", "replace")
        return {"status": "failed", "error": f"Roboflow returned HTTP {error.code}: {detail}"}
    except (URLError, TimeoutError) as error:
        return {"status": "failed", "error": f"Roboflow request failed: {error}"}


def analyze_measurement_capture(image: bytes) -> dict:
    status = configuration_status()
    if not status["ready"]:
        return {**status, "status": "disabled"}
    workflows = {
        "keypoints": os.environ["ROBOFLOW_KEYPOINT_WORKFLOW_ID"].strip(),
        "segmentation": os.environ["ROBOFLOW_SEGMENTATION_WORKFLOW_ID"].strip(),
    }
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {name: executor.submit(_run_workflow, workflow, image) for name, workflow in workflows.items()}
        outputs = {name: future.result() for name, future in futures.items()}
    return {
        **status,
        "status": "complete" if all(item["status"] == "complete" for item in outputs.values()) else "failed",
        "models": outputs,
    }
