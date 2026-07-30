"""Audit a sparse VLA4CoDrive sample before any model training.

This script is deliberately descriptive.  It verifies cross-modal joins,
schema, trajectories, videos, language leakage cues, and 2D-label availability.
It does not create final action/rationale labels and never authorizes training.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from statistics import mean, median

import cv2

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WINDOW_RE = re.compile(
    r"^(?P<town>Town.+?)_Weather(?P<weather>.+?)_scene"
    r"(?P<scene>\d+)_win(?P<window>\d+)$"
)
BRAKING_EVENTS_RE = re.compile(r"\b(\d+)\s+braking events?\b", re.I)
LEXICON_PATTERNS = {
    "traffic_signal_or_sign": re.compile(
        r"\b(?:traffic light|traffic signal|traffic sign|stop sign)\b", re.I
    ),
    "lead_or_parked_vehicle": re.compile(
        r"\b(?:lead(?:ing)? (?:car|vehicle)|parked (?:car|vehicle)|"
        r"car in front|vehicle in front)\b",
        re.I,
    ),
    "crossing_or_oncoming_vehicle": re.compile(
        r"\b(?:crossing|oncoming) (?:car|vehicle|traffic)\b", re.I
    ),
    "pedestrian_or_cyclist": re.compile(
        r"\b(?:pedestrian|cyclist|bicyclist|rider)\b", re.I
    ),
    "lane_or_road_geometry": re.compile(
        r"\b(?:lane|road geometry|road blockage|blocked road|curve)\b", re.I
    ),
    "junction_or_route_constraint": re.compile(
        r"\b(?:intersection|junction|turn left|turn right|route)\b", re.I
    ),
    "visibility_or_weather_hazard": re.compile(
        r"\b(?:fog|rain|snow|glare|visibility|night)\b", re.I
    ),
}
ACTION_LEAKAGE_RE = re.compile(
    r"\b(?:brak(?:e|es|ed|ing)|stop(?:s|ped|ping)?|"
    r"accelerat(?:e|es|ed|ing)|turn(?:s|ed|ing)?|"
    r"driv(?:e|es|ing)|moving|speed(?:s|ing)?)\b",
    re.I,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root", default="data/external/VLA4CoDrive_probe_repo"
    )
    parser.add_argument(
        "--output",
        default="outputs/validity/vla4codrive_probe_feasibility.json",
    )
    return parser.parse_args()


def rooted(path: str) -> Path:
    value = Path(path)
    return value if value.is_absolute() else PROJECT_ROOT / value


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_window_identity(path: Path, modality_root: Path) -> dict[str, object]:
    relative = path.relative_to(modality_root)
    if len(relative.parts) < 3:
        raise ValueError(f"unexpected window path: {relative}")
    weather, vehicle = relative.parts[0], relative.parts[1]
    match = WINDOW_RE.fullmatch(path.stem)
    if match is None:
        raise ValueError(f"unexpected window filename: {path.name}")
    parsed = match.groupdict()
    if parsed["weather"] != weather:
        raise ValueError(
            f"weather mismatch in path and filename: {path.as_posix()}"
        )
    scene = int(parsed["scene"])
    window = int(parsed["window"])
    canonical_scene_key = f"{parsed['town'].lower()}::scene{scene:03d}"
    return {
        "weather": weather,
        "vehicle": vehicle,
        "town": parsed["town"],
        "scene": scene,
        "window": window,
        "canonical_scene_key": canonical_scene_key,
        "window_key": (
            f"{weather}::{vehicle}::{parsed['town']}::"
            f"scene{scene:03d}::win{window:02d}"
        ),
    }


def count_rising_edges(values: list[bool]) -> int:
    previous = False
    count = 0
    for value in values:
        current = bool(value)
        if current and not previous:
            count += 1
        previous = current
    return count


def lexicon_flags(text: str) -> dict[str, bool]:
    return {
        name: pattern.search(text) is not None
        for name, pattern in LEXICON_PATTERNS.items()
    }


def numeric_summary(values: list[float]) -> dict[str, float | int | None]:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    if not finite:
        return {"count": 0, "minimum": None, "median": None, "mean": None, "maximum": None}
    ordered = sorted(finite)
    return {
        "count": len(finite),
        "minimum": ordered[0],
        "median": median(ordered),
        "mean": mean(ordered),
        "maximum": ordered[-1],
    }


def git_value(root: Path, *arguments: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), *arguments],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main() -> int:
    args = parse_args()
    root = rooted(args.root)
    action_root = root / "Action"
    language_root = root / "Language"
    action_paths = sorted(action_root.rglob("*.json"))
    language_paths = sorted(language_root.rglob("*.json"))
    video_paths = sorted((root / "Vision").rglob("*.mp4"))
    coco_paths = sorted(
        (root / "Vision").glob("*/Labels_2D/COCO/instances_all.json")
    )

    action_by_key: dict[str, dict] = {}
    action_schema_failures = []
    frame_counts = []
    trajectory_counts = []
    speeds = []
    accelerations = []
    extreme_acceleration_frames = 0
    nonfinite_numeric_frames = 0
    brake_rising_edges: dict[str, int] = {}
    brake_positive_frames: dict[str, int] = {}
    final_trajectory_axis_0 = []
    final_trajectory_axis_1 = []
    for path in action_paths:
        identity = parse_window_identity(path, action_root)
        data = load_json(path)
        frames = data.get("frames", [])
        key = str(identity["window_key"])
        action_by_key[key] = {
            "identity": identity,
            "path": path,
            "data": data,
        }
        frame_counts.append(len(frames))
        if len(frames) != int(data.get("num_frames", -1)):
            action_schema_failures.append(
                {"window_key": key, "reason": "num_frames_mismatch"}
            )
        pressed = [bool(frame.get("brakePressed", False)) for frame in frames]
        brake_rising_edges[key] = count_rising_edges(pressed)
        brake_positive_frames[key] = sum(
            float(frame.get("brake", 0.0)) > 0.0 for frame in frames
        )
        for frame in frames:
            values = [
                float(frame.get("vEgo", float("nan"))),
                float(frame.get("aEgo", float("nan"))),
                float(frame.get("brake", float("nan"))),
            ]
            if not all(math.isfinite(value) for value in values):
                nonfinite_numeric_frames += 1
            speeds.append(values[0])
            accelerations.append(values[1])
            if abs(values[1]) > 50.0:
                extreme_acceleration_frames += 1
            trajectory = frame.get("trajectory", [])
            trajectory_counts.append(len(trajectory))
        if frames:
            final_trajectory = frames[-1].get("trajectory", [])
            if final_trajectory and len(final_trajectory[-1]) >= 2:
                final_trajectory_axis_0.append(float(final_trajectory[-1][0]))
                final_trajectory_axis_1.append(float(final_trajectory[-1][1]))

    language_by_key: dict[str, dict] = {}
    language_schema_failures = []
    lexicon_counts: Counter[str] = Counter()
    reasoning_with_action_leakage = 0
    declared_braking_event_windows = 0
    declared_braking_event_matches_rising_edges = 0
    for path in language_paths:
        identity = parse_window_identity(path, language_root)
        data = load_json(path)
        key = str(identity["window_key"])
        language_by_key[key] = {
            "identity": identity,
            "path": path,
            "data": data,
        }
        required = {
            "scene_id",
            "window_id",
            "start_frame",
            "end_frame",
            "frames",
            "caption",
            "context",
            "description",
            "reasoning",
        }
        missing = sorted(required.difference(data))
        if missing:
            language_schema_failures.append(
                {"window_key": key, "reason": "missing_keys", "keys": missing}
            )
        reasoning = str(data.get("reasoning", ""))
        for name, active in lexicon_flags(reasoning).items():
            if active:
                lexicon_counts[name] += 1
        if ACTION_LEAKAGE_RE.search(reasoning):
            reasoning_with_action_leakage += 1
        text = " ".join(
            str(data.get(field, ""))
            for field in ("title", "caption", "context")
        )
        declared = BRAKING_EVENTS_RE.search(text)
        if declared is not None:
            declared_braking_event_windows += 1
            if (
                key in brake_rising_edges
                and int(declared.group(1)) == brake_rising_edges[key]
            ):
                declared_braking_event_matches_rising_edges += 1

    action_keys = set(action_by_key)
    language_keys = set(language_by_key)
    paired_keys = sorted(action_keys.intersection(language_keys))
    union_keys = action_keys.union(language_keys)

    videos = []
    readable_videos = 0
    for path in video_paths:
        capture = cv2.VideoCapture(str(path))
        opened = capture.isOpened()
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) if opened else 0
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)) if opened else 0
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)) if opened else 0
        fps = float(capture.get(cv2.CAP_PROP_FPS)) if opened else 0.0
        capture.release()
        if opened and frame_count > 0:
            readable_videos += 1
        videos.append(
            {
                "path": str(path.relative_to(root)),
                "opened": opened,
                "frame_count": frame_count,
                "width": width,
                "height": height,
                "fps": fps,
            }
        )

    coco_summaries = []
    for path in coco_paths:
        data = load_json(path)
        category_name = {
            int(category["id"]): str(category["name"])
            for category in data.get("categories", [])
        }
        annotation_counts: Counter[str] = Counter()
        for annotation in data.get("annotations", []):
            annotation_counts[
                category_name.get(
                    int(annotation["category_id"]),
                    f"unknown_{annotation['category_id']}",
                )
            ] += 1
        image_names = [
            str(image.get("file_name", ""))
            for image in data.get("images", [])
        ]
        coco_summaries.append(
            {
                "path": str(path.relative_to(root)),
                "images": len(image_names),
                "annotations": len(data.get("annotations", [])),
                "categories": category_name,
                "annotations_per_category": dict(annotation_counts),
                "example_image_names": image_names[:10],
            }
        )

    artifact_paths = action_paths + language_paths + coco_paths + video_paths
    provenance = {
        "repository": git_value(root, "remote", "get-url", "origin"),
        "commit": git_value(root, "rev-parse", "HEAD"),
        "sparse_checkout": (
            (root / ".git" / "info" / "sparse-checkout").read_text(
                encoding="utf-8"
            )
            if (root / ".git" / "info" / "sparse-checkout").exists()
            else None
        ),
        "sha256": {
            str(path.relative_to(root)): sha256(path)
            for path in artifact_paths
        },
        "analysis_script_sha256": sha256(Path(__file__)),
    }

    join_completeness = len(paired_keys) / max(len(union_keys), 1)
    action_schema_rate = (
        (len(action_paths) - len(action_schema_failures))
        / max(len(action_paths), 1)
    )
    language_schema_rate = (
        (len(language_paths) - len(language_schema_failures))
        / max(len(language_paths), 1)
    )
    video_readability_rate = readable_videos / max(len(video_paths), 1)
    technical_gate = {
        "minimum_paired_windows_10": len(paired_keys) >= 10,
        "join_completeness_at_least_0_95": join_completeness >= 0.95,
        "action_schema_rate_1_00": action_schema_rate == 1.0,
        "language_schema_rate_1_00": language_schema_rate == 1.0,
        "video_readability_rate_at_least_0_95": (
            len(video_paths) > 0 and video_readability_rate >= 0.95
        ),
        "coco_labels_present": bool(coco_summaries)
        and all(item["annotations"] > 0 for item in coco_summaries),
    }
    technical_gate["passed"] = all(technical_gate.values())

    summary = {
        "phase": "small_sample_feasibility_only",
        "training_authorized": False,
        "root": str(root.relative_to(PROJECT_ROOT)),
        "counts": {
            "action_windows": len(action_paths),
            "language_windows": len(language_paths),
            "paired_action_language_windows": len(paired_keys),
            "videos": len(video_paths),
            "coco_files": len(coco_paths),
            "canonical_scenes": len(
                {
                    item["identity"]["canonical_scene_key"]
                    for item in action_by_key.values()
                }
            ),
        },
        "cross_modal_join": {
            "completeness": join_completeness,
            "action_only_keys": sorted(action_keys - language_keys),
            "language_only_keys": sorted(language_keys - action_keys),
        },
        "action_schema": {
            "valid_window_rate": action_schema_rate,
            "failures": action_schema_failures,
            "frame_counts": dict(Counter(frame_counts)),
            "trajectory_point_counts": dict(Counter(trajectory_counts)),
            "speed_m_per_s": numeric_summary(speeds),
            "acceleration_reported": numeric_summary(accelerations),
            "abs_acceleration_above_50_frames": extreme_acceleration_frames,
            "nonfinite_numeric_frames": nonfinite_numeric_frames,
            "brake_rising_edges_per_window": dict(
                Counter(brake_rising_edges.values())
            ),
            "positive_brake_frames_per_window": dict(
                Counter(brake_positive_frames.values())
            ),
            "last_frame_future_trajectory_final_axis_0": numeric_summary(
                final_trajectory_axis_0
            ),
            "last_frame_future_trajectory_final_axis_1": numeric_summary(
                final_trajectory_axis_1
            ),
            "pre_registered_action_mapping_ready": False,
            "blocking_reason": (
                "coordinate sign/unit and terminal speed/future-brake "
                "availability still require audit"
            ),
        },
        "language_schema": {
            "valid_window_rate": language_schema_rate,
            "failures": language_schema_failures,
            "exploratory_reasoning_lexicon_counts": dict(lexicon_counts),
            "reasoning_action_word_rate": (
                reasoning_with_action_leakage / max(len(language_paths), 1)
            ),
            "declared_braking_event_windows": declared_braking_event_windows,
            "declared_count_matches_brake_rising_edges": (
                declared_braking_event_matches_rising_edges
            ),
            "declared_count_match_rate": (
                declared_braking_event_matches_rising_edges
                / max(declared_braking_event_windows, 1)
            ),
            "ontology_confirmed": False,
        },
        "videos": videos,
        "video_readability_rate": video_readability_rate,
        "coco": coco_summaries,
        "technical_gate": technical_gate,
        "hard_gate_status": {
            "minimum_200_window_feasibility_audit": (
                len(paired_keys) >= 200
            ),
            "minimum_150_canonical_scenes": False,
            "minimum_5000_valid_windows": False,
            "action_semantics_audited": False,
            "rationale_ontology_audited": False,
            "split_frozen": False,
            "bbox_ceg_audited": False,
            "weather_pairing_audited": False,
            "go_to_training": False,
        },
        "provenance": provenance,
    }
    output_path = rooted(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if technical_gate["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
