"""Audit VLA4CoDrive repository coverage without downloading dataset blobs."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from collections import Counter
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HF_DATASET = "sayedpedramhaeri/VLA4CoDrive"
HF_API = f"https://huggingface.co/api/datasets/{HF_DATASET}"
WINDOW_RE = re.compile(
    r"^(?P<town>Town.+?)_Weather(?P<filename_weather>.+?)_scene"
    r"(?P<scene>\d+)_win(?P<window>\d+)\.json$"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--github-root",
        default="data/external/VLA4CoDrive_probe_repo",
    )
    parser.add_argument(
        "--output",
        default="outputs/validity/vla4codrive_repository_index.json",
    )
    parser.add_argument("--attempts", type=int, default=10)
    return parser.parse_args()


def rooted(path: str) -> Path:
    value = Path(path)
    return value if value.is_absolute() else PROJECT_ROOT / value


def parse_window_path(path: str) -> dict[str, object] | None:
    parts = path.split("/")
    if len(parts) != 4 or parts[0] not in {"Action", "Language"}:
        return None
    modality, weather, vehicle, filename = parts
    match = WINDOW_RE.fullmatch(filename)
    if match is None:
        return None
    fields = match.groupdict()
    scene = int(fields["scene"])
    window = int(fields["window"])
    return {
        "modality": modality,
        "weather": weather,
        "filename_weather": fields["filename_weather"],
        "weather_matches_filename": (
            fields["filename_weather"] == weather
        ),
        "vehicle": vehicle,
        "town": fields["town"],
        "scene": scene,
        "window": window,
        "canonical_scene_key": f"{fields['town'].lower()}::scene{scene:03d}",
    }


def fetch_index(attempts: int) -> dict:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = requests.get(
                HF_API,
                headers={"User-Agent": "ARSC-Eval/1.0"},
                timeout=(30, 180),
            )
            response.raise_for_status()
            payload = response.json()
            if len(payload.get("siblings", [])) < 1000:
                raise RuntimeError("unexpectedly short repository index")
            return payload
        except Exception as error:
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(min(2**attempt, 30))
    raise RuntimeError(f"failed to fetch HF index after {attempts} attempts") from last_error


def summarize_paths(paths: list[str]) -> dict:
    parsed = [record for path in paths if (record := parse_window_path(path))]
    weather_mismatches = [
        record for record in parsed if not record["weather_matches_filename"]
    ]
    scene_keys = {
        str(record["canonical_scene_key"]) for record in parsed
    }
    towns = sorted({str(record["town"]) for record in parsed})
    scenes_by_town: Counter[str] = Counter()
    for town in towns:
        scenes_by_town[town] = len(
            {
                int(record["scene"])
                for record in parsed
                if record["town"] == town
            }
        )
    return {
        "paths": len(paths),
        "root_counts": dict(
            Counter(path.split("/", 1)[0] for path in paths)
        ),
        "window_jsons": len(parsed),
        "window_jsons_by_modality": dict(
            Counter(str(record["modality"]) for record in parsed)
        ),
        "weathers": sorted(
            {str(record["weather"]) for record in parsed}
        ),
        "filename_weathers": sorted(
            {str(record["filename_weather"]) for record in parsed}
        ),
        "weather_filename_mismatch_count": len(weather_mismatches),
        "weather_filename_mismatch_examples": weather_mismatches[:20],
        "vehicles": sorted(
            {str(record["vehicle"]) for record in parsed}
        ),
        "towns": towns,
        "canonical_scene_keys": sorted(scene_keys),
        "canonical_scene_count": len(scene_keys),
        "canonical_scenes_by_town": dict(scenes_by_town),
        "window_indices": sorted(
            {int(record["window"]) for record in parsed}
        ),
    }


def git_paths(root: Path) -> tuple[list[str], dict[str, str | None]]:
    if not (root / ".git").exists():
        return [], {"commit": None, "origin": None}
    paths = subprocess.check_output(
        ["git", "-C", str(root), "ls-tree", "-r", "--name-only", "HEAD"],
        text=True,
    ).splitlines()
    commit = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    origin = subprocess.check_output(
        ["git", "-C", str(root), "remote", "get-url", "origin"], text=True
    ).strip()
    return paths, {"commit": commit, "origin": origin}


def main() -> int:
    args = parse_args()
    payload = fetch_index(args.attempts)
    hf_paths = [
        str(sibling["rfilename"])
        for sibling in payload.get("siblings", [])
    ]
    github_root = rooted(args.github_root)
    local_paths, local_provenance = git_paths(github_root)
    hf_summary = summarize_paths(hf_paths)
    github_summary = summarize_paths(local_paths)
    hf_window_paths = {
        path for path in hf_paths if parse_window_path(path) is not None
    }
    github_window_paths = {
        path for path in local_paths if parse_window_path(path) is not None
    }
    hard_gate = {
        "minimum_two_towns": len(hf_summary["towns"]) >= 2,
        "minimum_150_canonical_scenes": (
            int(hf_summary["canonical_scene_count"]) >= 150
        ),
        "weather_filename_mismatch_count_zero": (
            int(hf_summary["weather_filename_mismatch_count"]) == 0
        ),
    }
    hard_gate["passed"] = all(hard_gate.values())
    summary = {
        "phase": "repository_metadata_audit_only",
        "training_authorized": False,
        "huggingface": {
            "dataset": HF_DATASET,
            "api": HF_API,
            "revision": payload.get("sha"),
            "private": payload.get("private"),
            "gated": payload.get("gated"),
            "used_storage_bytes": payload.get("usedStorage"),
            "license": payload.get("cardData", {}).get("license"),
            **hf_summary,
        },
        "github": {
            **local_provenance,
            **github_summary,
        },
        "window_path_comparison": {
            "shared": len(hf_window_paths.intersection(github_window_paths)),
            "hf_only": len(hf_window_paths - github_window_paths),
            "github_only": len(github_window_paths - hf_window_paths),
            "identical": hf_window_paths == github_window_paths,
        },
        "pre_registered_hard_gate": hard_gate,
        "decision": (
            "STOP_EXTERNAL_TRAINING"
            if not hard_gate["passed"]
            else "CONTINUE_FEASIBILITY"
        ),
    }
    output_path = rooted(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if hard_gate["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
