#!/usr/bin/env python3
"""Reject COCO exports that cannot support honest measurement evaluation."""
from __future__ import annotations

import argparse
import csv
import json
import re
import zipfile
from pathlib import Path


SPLITS = ("train", "valid", "test")


def source_group(filename: str) -> str:
    name = Path(filename).stem
    name = re.sub(r"\.rf\.[0-9a-f]+$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"_(jpg|jpeg|png)$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[_-]frame[_-]?\d+$", "", name, flags=re.IGNORECASE)
    return name.lower()


def validate(archive: Path, minimum_images: int, minimum_subjects: int, manifest: Path | None) -> list[str]:
    errors: list[str] = []
    groups: dict[str, set[str]] = {}
    total = 0
    with zipfile.ZipFile(archive) as bundle:
        for split in SPLITS:
            member = f"{split}/_annotations.coco.json"
            try:
                payload = json.loads(bundle.read(member))
            except KeyError:
                errors.append(f"Missing {member}")
                continue
            images = payload.get("images", [])
            total += len(images)
            for image in images:
                groups.setdefault(source_group(str(image.get("file_name", ""))), set()).add(split)
    leaked = {group: sorted(splits) for group, splits in groups.items() if len(splits) > 1}
    if leaked:
        details = "; ".join(f"{group}: {','.join(splits)}" for group, splits in sorted(leaked.items()))
        errors.append(f"Source sequences cross dataset splits ({details})")
    if total < minimum_images:
        errors.append(f"Dataset has {total} images; at least {minimum_images} are required")
    if manifest is None:
        errors.append("A subject manifest is required to prove subject-level split isolation")
    else:
        with manifest.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        required = {"source_group", "subject_id", "split"}
        if not rows or not required.issubset(rows[0]):
            errors.append("Manifest must contain source_group, subject_id and split columns")
        else:
            subject_splits: dict[str, set[str]] = {}
            manifest_groups: dict[str, tuple[str, str]] = {}
            for row in rows:
                group = row["source_group"].strip().lower()
                subject = row["subject_id"].strip()
                split = row["split"].strip()
                if not group or not subject or split not in SPLITS:
                    errors.append(f"Invalid manifest row: {row}")
                    continue
                if group in manifest_groups:
                    errors.append(f"Manifest contains duplicate source_group: {group}")
                    continue
                manifest_groups[group] = (subject, split)
                subject_splits.setdefault(subject, set()).add(split)
            missing_groups = sorted(set(groups) - set(manifest_groups))
            if missing_groups:
                errors.append("Manifest is missing dataset source groups: " + ", ".join(missing_groups))
            unknown_groups = sorted(set(manifest_groups) - set(groups))
            if unknown_groups:
                errors.append("Manifest contains source groups not found in the dataset: " + ", ".join(unknown_groups))
            for group, split_set in groups.items():
                if group in manifest_groups and manifest_groups[group][1] not in split_set:
                    errors.append(
                        f"Manifest split for {group} is {manifest_groups[group][1]}, "
                        f"but the dataset contains it in {','.join(sorted(split_set))}"
                    )
            crossed = sorted(subject for subject, splits in subject_splits.items() if len(splits) > 1)
            if crossed:
                errors.append("Subjects cross dataset splits: " + ", ".join(crossed))
            if len(subject_splits) < minimum_subjects:
                errors.append(f"Manifest has {len(subject_splits)} subjects; at least {minimum_subjects} are required")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--minimum-images", type=int, default=50)
    parser.add_argument("--minimum-subjects", type=int, default=5)
    args = parser.parse_args()
    errors = validate(args.archive, args.minimum_images, args.minimum_subjects, args.manifest)
    if errors:
        raise SystemExit("Dataset validation failed:\n- " + "\n- ".join(errors))
    print("Dataset validation passed.")


if __name__ == "__main__":
    main()
