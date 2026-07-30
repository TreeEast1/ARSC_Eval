"""Evaluate one frozen paired seed for clean A/R/S and lossless C1."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.constants import ACTION_NAMES, RATIONALE_NAMES
from arsc_eval.data import make_benign_perturbation
from arsc_eval.engine import make_loader, predict
from arsc_eval.internal_validity import (
    PERTURBATIONS,
    paired_bootstrap,
    percentile_interval,
)
from arsc_eval.metrics import multilabel_f1
from arsc_eval.models import load_checkpoint_model
from arsc_eval.rq1 import (
    MODEL_ACTION,
    MODEL_JOINT,
    prepare_rq1_arrays,
    rq1_metric_estimates,
)
from arsc_eval.utils import (
    device_from_arg,
    json_safe,
    load_config,
    resolve_paths,
    write_json,
)


CACHE_SCHEMA_VERSION = 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--action-checkpoint", required=True)
    parser.add_argument("--joint-checkpoint", required=True)
    parser.add_argument("--action-calibration", required=True)
    parser.add_argument("--joint-calibration", required=True)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--bootstrap-replicates", type=int, default=2000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260731)
    parser.add_argument("--refresh-cache", action="store_true")
    return parser.parse_args()


def rooted(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(PROJECT_ROOT)),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def expected_metadata(
    config: dict[str, Any],
    paths: dict[str, Path],
    action_checkpoint: Path,
    joint_checkpoint: Path,
    semantic_audit: Path,
) -> dict[str, Any]:
    settings = config["perturbations"]
    return {
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "seed": int(config["seed"]),
        "image_size": int(config["image_size"]),
        "test_manifest": fingerprint(
            paths["processed_root"] / "test.jsonl"
        ),
        "action_checkpoint": fingerprint(action_checkpoint),
        "joint_checkpoint": fingerprint(joint_checkpoint),
        "semantic_audit": fingerprint(semantic_audit),
        "perturbations": {
            "execution": "in_memory_no_jpeg_reencoding",
            "brightness_factor": float(settings["brightness_factor"]),
            "blur_radius": float(settings["blur_radius"]),
            "noise_std_255": float(settings["noise_std_255"]),
            "noise_seed": int(settings["noise_seed"]),
        },
    }


def load_cache(path: Path, metadata: dict[str, Any]) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as archive:
        cached_metadata = json.loads(str(archive["metadata_json"].item()))
        if cached_metadata != metadata:
            raise RuntimeError(
                "prediction cache provenance does not match frozen inputs"
            )
        return {key: np.asarray(archive[key]) for key in archive.files}


def run_inference(
    config: dict[str, Any],
    paths: dict[str, Path],
    action_checkpoint: Path,
    joint_checkpoint: Path,
    device_arg: str,
    metadata: dict[str, Any],
) -> dict[str, np.ndarray]:
    device = device_from_arg(device_arg)
    amp = bool(config["training"]["amp"])
    action_model = load_checkpoint_model(
        str(action_checkpoint), "action_only", device
    )
    joint_model = load_checkpoint_model(
        str(joint_checkpoint), "joint", device
    )
    image_root = paths["dataset_root"] / "data"
    manifest = paths["processed_root"] / "test.jsonl"
    settings = config["perturbations"]
    transforms = {
        kind: make_benign_perturbation(
            kind,
            float(settings["brightness_factor"]),
            float(settings["blur_radius"]),
            float(settings["noise_std_255"]),
            int(settings["noise_seed"]),
        )
        for kind in PERTURBATIONS
    }
    payload: dict[str, np.ndarray] = {}
    expected_names: list[str] | None = None
    expected_action_targets: np.ndarray | None = None
    expected_rationale_targets: np.ndarray | None = None
    for condition in ("clean", *PERTURBATIONS):
        pil_transform = None if condition == "clean" else transforms[condition]
        predictions = {}
        for model_type, model in (
            ("action", action_model),
            ("joint", joint_model),
        ):
            loader = make_loader(
                manifest,
                image_root,
                int(config["image_size"]),
                int(config["training"]["batch_size"]),
                int(config["training"]["num_workers"]),
                shuffle=False,
                pil_transform=pil_transform,
            )
            predictions[model_type] = predict(
                model, loader, device, amp=amp
            )
        action_prediction = predictions["action"]
        joint_prediction = predictions["joint"]
        names = [str(value) for value in action_prediction["file_names"]]
        if names != [
            str(value) for value in joint_prediction["file_names"]
        ]:
            raise RuntimeError("paired models produced different file order")
        if expected_names is None:
            expected_names = names
            expected_action_targets = np.asarray(
                action_prediction["action_targets"]
            )
            expected_rationale_targets = np.asarray(
                joint_prediction["rationale_targets"]
            )
        elif names != expected_names:
            raise RuntimeError("perturbation file order changed")
        if not np.array_equal(
            expected_action_targets,
            action_prediction["action_targets"],
        ):
            raise RuntimeError("action targets changed across conditions")
        if not np.array_equal(
            expected_rationale_targets,
            joint_prediction["rationale_targets"],
        ):
            raise RuntimeError("rationale targets changed across conditions")
        payload[f"test_{condition}_action_logits"] = np.asarray(
            action_prediction["action_logits"], dtype=np.float32
        )
        payload[f"test_{condition}_joint_action_logits"] = np.asarray(
            joint_prediction["action_logits"], dtype=np.float32
        )
        payload[f"test_{condition}_joint_rationale_logits"] = np.asarray(
            joint_prediction["rationale_logits"], dtype=np.float32
        )

    assert expected_names is not None
    assert expected_action_targets is not None
    assert expected_rationale_targets is not None
    payload["test_file_names"] = np.asarray(expected_names)
    payload["test_action_targets"] = expected_action_targets.astype(
        np.float32
    )
    payload["test_rationale_targets"] = expected_rationale_targets.astype(
        np.float32
    )
    payload["metadata_json"] = np.asarray(
        json.dumps(metadata, sort_keys=True, separators=(",", ":"))
    )
    return payload


def calibration_temperature(path: Path, expected_model: str) -> float:
    result = json.loads(path.read_text(encoding="utf-8"))
    if result.get("model_type") != expected_model:
        raise RuntimeError(f"wrong calibration model in {path}")
    return float(result["temperature"])


def summarize_bootstrap(
    estimates: dict[str, float],
    draws: dict[str, np.ndarray],
    confidence_level: float = 0.95,
) -> list[dict[str, Any]]:
    rows = []
    for metric in sorted(estimates):
        lower, upper = percentile_interval(
            draws[metric], confidence_level
        )
        rows.append(
            {
                "metric": metric,
                "estimate": float(estimates[metric]),
                "ci_lower": lower,
                "ci_upper": upper,
            }
        )
    return rows


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    paths = resolve_paths(config)
    output_dir = paths["output_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_path = output_dir / "prediction_cache" / "rq1_lossless.npz"
    result_path = output_dir / "rq1_metrics.json"
    semantic_audit = (
        PROJECT_ROOT
        / "outputs"
        / "validity"
        / "perturbation_semantic_audit"
        / "audit_summary.json"
    )
    audit = json.loads(semantic_audit.read_text(encoding="utf-8"))
    if not audit["gate_passed"]:
        raise RuntimeError("C1 semantic audit gate did not pass")

    action_checkpoint = rooted(args.action_checkpoint)
    joint_checkpoint = rooted(args.joint_checkpoint)
    metadata = expected_metadata(
        config,
        paths,
        action_checkpoint,
        joint_checkpoint,
        semantic_audit,
    )
    if cache_path.is_file() and not args.refresh_cache:
        cache = load_cache(cache_path, metadata)
        cache_reused = True
    else:
        cache = run_inference(
            config,
            paths,
            action_checkpoint,
            joint_checkpoint,
            args.device,
            metadata,
        )
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(cache_path, **cache)
        cache_reused = False

    action_temperature = calibration_temperature(
        rooted(args.action_calibration), "action_only"
    )
    joint_temperature = calibration_temperature(
        rooted(args.joint_calibration), "joint"
    )
    prepared = prepare_rq1_arrays(
        cache, action_temperature, joint_temperature
    )
    threshold = float(config["training"]["threshold"])
    rng = np.random.default_rng(args.bootstrap_seed)
    estimates, draws = paired_bootstrap(
        lambda indices: rq1_metric_estimates(
            prepared, threshold, indices
        ),
        len(prepared["action_targets"]),
        args.bootstrap_replicates,
        rng,
    )

    per_class = {}
    for model in (MODEL_ACTION, MODEL_JOINT):
        per_class[model] = multilabel_f1(
            prepared["action_targets"],
            prepared["raw_clean"][model],
            ACTION_NAMES,
            threshold,
        )["per_class_f1"]
    rationale_per_class = multilabel_f1(
        prepared["rationale_targets"],
        prepared["rationale_clean"],
        RATIONALE_NAMES,
        threshold,
    )["per_class_f1"]

    invariance = {}
    for model in (MODEL_ACTION, MODEL_JOINT):
        raw = rq1_metric_estimates(
            {
                **prepared,
                "calibrated_clean": {
                    **prepared["calibrated_clean"],
                    model: prepared["raw_clean"][model],
                },
            },
            threshold,
        )
        invariance[model] = {
            "aurc_absolute_difference": abs(
                estimates[f"aurc::{model}"] - raw[f"aurc::{model}"]
            ),
            "uar90_absolute_difference": abs(
                estimates[f"unsafe_acceptance_rate_90::{model}"]
                - raw[f"unsafe_acceptance_rate_90::{model}"]
            ),
        }

    result = {
        "study": "BDD-OIA RQ1 paired-seed replication",
        "seed": int(config["seed"]),
        "status": "confirmatory_new_seed",
        "samples": int(len(prepared["action_targets"])),
        "threshold": threshold,
        "bootstrap": {
            "unit": "image; paired across models and all perturbations",
            "replicates": args.bootstrap_replicates,
            "seed": args.bootstrap_seed,
            "confidence_level": 0.95,
        },
        "c1_measurement_gate": audit,
        "perturbation_execution": (
            "frozen in-memory PIL transforms before tensor conversion; "
            "no JPEG re-encoding"
        ),
        "temperatures": {
            MODEL_ACTION: action_temperature,
            MODEL_JOINT: joint_temperature,
        },
        "positive_temperature_ranking_invariance": {
            "by_model": invariance,
            "passed": all(
                values["aurc_absolute_difference"] < 1e-12
                and values["uar90_absolute_difference"] < 1e-12
                for values in invariance.values()
            ),
        },
        "metrics": summarize_bootstrap(estimates, draws),
        "per_class_action_f1": per_class,
        "per_class_rationale_f1": rationale_per_class,
        "cache": {
            "path": str(cache_path.relative_to(PROJECT_ROOT)),
            "reused": cache_reused,
            "sha256": sha256_file(cache_path),
            "metadata": metadata,
        },
        "guardrails": [
            "CEG and every v2/v3/v4 mask output are excluded.",
            "Test data are not used for checkpoint, threshold, seed, or "
            "temperature selection.",
            "Seed 42 is an archival pilot and is not part of the primary "
            "five-seed replication.",
        ],
    }
    write_json(result_path, json_safe(result))
    print(
        json.dumps(
            {
                "seed": result["seed"],
                "cache_reused": cache_reused,
                "metrics": result["metrics"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
