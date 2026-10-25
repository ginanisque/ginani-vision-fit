"""Execute published measurement paths against tailoring keypoint predictions."""
from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from .circumference import _silhouette
from .posture import estimate_pose, load_pose


@dataclass(frozen=True)
class TailoringPoint:
    key: str
    x: float
    y: float
    confidence: float


POINT_NAME_FIELDS = ("class_name", "keypoint_class_name", "name", "label", "key")


def normalize_keypoints(payload: object, width: int, height: int) -> dict[str, TailoringPoint]:
    """Normalize one Roboflow person instance into pixel coordinates.

    Workflow responses may contain several people. Combining the highest-confidence
    point from every person creates a synthetic body, so select one complete,
    high-confidence instance before normalizing its keypoints.
    """
    found: dict[str, TailoringPoint] = {}

    def add(item: dict) -> None:
        name = next((str(item[field]) for field in POINT_NAME_FIELDS if item.get(field)), "")
        if not name or "x" not in item or "y" not in item:
            return
        try:
            x, y = float(item["x"]), float(item["y"])
            confidence = float(item.get("confidence", item.get("score", 1.0)))
        except (TypeError, ValueError):
            return
        if abs(x) <= 1 and abs(y) <= 1:
            x, y = x * width, y * height
        if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(confidence)):
            return
        if not (0 <= x <= width and 0 <= y <= height):
            return
        key = name.strip().lower().replace("-", " ").replace(" ", "_")
        point = TailoringPoint(key, x, y, max(0.0, min(1.0, confidence)))
        if key not in found or point.confidence > found[key].confidence:
            found[key] = point

    def walk(value: object) -> None:
        if isinstance(value, dict):
            add(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    instances: list[tuple[tuple[int, float, float], object]] = []

    def find_instances(value: object) -> None:
        if isinstance(value, dict):
            keypoints = value.get("keypoints")
            if isinstance(keypoints, list):
                named = sum(
                    isinstance(item, dict)
                    and any(item.get(field) for field in POINT_NAME_FIELDS)
                    and "x" in item and "y" in item
                    for item in keypoints
                )
                if named:
                    try:
                        confidence = float(value.get("confidence", value.get("score", 0.0)) or 0.0)
                        area = float(value.get("width", 0.0) or 0.0) * float(value.get("height", 0.0) or 0.0)
                    except (TypeError, ValueError):
                        confidence, area = 0.0, 0.0
                    instances.append(((named, confidence, area), keypoints))
                    return
            for child in value.values():
                find_instances(child)
        elif isinstance(value, list):
            for child in value:
                find_instances(child)

    find_instances(payload)
    walk(max(instances, key=lambda item: item[0])[1] if instances else payload)
    return found


def view_scale_mm_per_pixel(image: np.ndarray, height_mm: float) -> float:
    """Use the body outline only to calibrate pixels; it is not a measurement path."""
    if not 1000 <= height_mm <= 2500:
        raise ValueError("Height must be between 1000 and 2500 mm")
    pose = load_pose()
    landmarks = estimate_pose(image, pose) if pose is not None else None
    if landmarks is None:
        raise ValueError("Full-body pose is required to calibrate keypoint distances")
    mask = _silhouette(image, landmarks)
    rows = np.flatnonzero(np.any(mask > 0, axis=1))
    if len(rows) < image.shape[0] * 0.35:
        raise ValueError("Body outline is too short for height calibration")
    return height_mm / float(rows[-1] - rows[0] + 1)


def calculate_ordered_path(
    definition: dict,
    points_by_view: dict[str, dict[str, TailoringPoint]],
    scales_by_view: dict[str, float],
) -> dict:
    points = list(definition["orderedPoints"])
    pairs = list(zip(points, points[1:]))
    if definition["closed"]:
        pairs.append((points[-1], points[0]))
    segments = []
    missing = []
    total_mm = 0.0
    segment_views = list(definition.get("segmentViews", []))
    if len(segment_views) != len(pairs):
        raise ValueError(f"{definition['measurementKey']} has an invalid segment-view mapping")
    for index, (start, end) in enumerate(pairs):
        required_view = segment_views[index]
        candidates = []
        for view in (required_view,):
            start_point = points_by_view.get(view, {}).get(start)
            end_point = points_by_view.get(view, {}).get(end)
            if start_point and end_point and view in scales_by_view:
                candidates.append((min(start_point.confidence, end_point.confidence), view, start_point, end_point))
        if not candidates:
            missing.append({"from": start, "to": end, "view": required_view})
            continue
        confidence, view, start_point, end_point = max(candidates, key=lambda item: item[0])
        pixel_length = math.hypot(end_point.x - start_point.x, end_point.y - start_point.y)
        length_mm = pixel_length * scales_by_view[view]
        total_mm += length_mm
        segments.append({
            "from": start, "to": end, "view": view, "lengthMm": round(length_mm, 2),
            "confidence": round(confidence, 4),
            "fromPoint": {"x": round(start_point.x, 2), "y": round(start_point.y, 2)},
            "toPoint": {"x": round(end_point.x, 2), "y": round(end_point.y, 2)},
        })
    if missing:
        return {"key": definition["measurementKey"], "displayName": definition["displayName"],
                "status": "blocked", "missingSegments": missing, "segments": segments}
    confidence = min(segment["confidence"] for segment in segments)
    return {
        "key": definition["measurementKey"], "displayName": definition["displayName"],
        "status": "estimated", "valueMm": round(total_mm, 2), "confidence": round(confidence, 4),
        "pathVersion": definition["version"], "pathVersionId": definition["id"],
        "pathType": definition["path"],
        "closed": definition["closed"], "orderedPoints": points, "segments": segments,
        "sourceViews": sorted({segment["view"] for segment in segments}),
    }
