"""Add paired uncertainty estimates and a direct CEG model comparison.

The existing required outputs are deliberately left untouched.  This script
writes a reusable per-sample logit cache plus two additive result artifacts:

* ``outputs/internal_validity_bootstrap.json``
* ``outputs/internal_validity_bootstrap.csv``

The first run performs inference for both trained models.  Later runs reuse the
cache when all model/config/manifest fingerprints still match.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.engine import make_loader
from arsc_eval.data import read_jsonl
from arsc_eval.internal_validity import (
    PERTURBATIONS,
    mask_metric_estimates,
    paired_bootstrap,
    prepare_probabilities,
    summarize_families,
    test_metric_estimates,
)
from arsc_eval.models import load_checkpoint_model
from arsc_eval.utils import (
    device_from_arg,
    json_safe,
    load_config,
    resolve_paths,
    write_json,
)


CACHE_SCHEMA_VERSION = 1
DEFAULT_CACHE = "outputs/prediction_cache/internal_validity_predictions.npz"
DEFAULT_JSON = "outputs/internal_validity_bootstrap.json"
DEFAULT_CSV = "outputs/internal_validity_bootstrap.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate/reuse per-sample predictions and compute paired "
            "bootstrap confidence intervals for BDD-OIA ARSC metrics."
        )
    )
    parser.add_argument("--config", default="configs/experiment.yaml")
    parser.add_argument(
        "--action-checkpoint",
        default="checkpoints/action_only_best_action.pt",
    )
    parser.add_argument(
        "--joint-checkpoint",
        default="checkpoints/joint_best_action.pt",
    )
    parser.add_argument("--calibration", default="outputs/calibration.json")
    parser.add_argument(
        "--mask-manifest",
        default="data/processed/masks/manifest.jsonl",
        help=(
            "Mask manifest. v2 manifests may include localized_action_indices "
            "and detected_class for rationale-bound stratified CEG."
        ),
    )
    parser.add_argument("--cache", default=DEFAULT_CACHE)
    parser.add_argument("--output-json", default=DEFAULT_JSON)
    parser.add_argument("--output-csv", default=DEFAULT_CSV)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--bootstrap-replicates", type=int, default=2000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260730)
    parser.add_argument("--confidence-level", type=float, default=0.95)
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Ignore a valid prediction cache and run inference again.",
    )
    parser.add_argument(
        "--analysis-only",
        action="store_true",
        help="Refuse inference; fail if the cache is missing or stale.",
    )
    return parser.parse_args()


def rooted(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else PROJECT_ROOT / value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(resolved)


def file_fingerprint(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    stat = path.stat()
    return {
        "path": display_path(path),
        "bytes": stat.st_size,
        "sha256": sha256_file(path),
    }


def cache_source_metadata(
    config: dict[str, Any],
    paths: dict[str, Path],
    action_checkpoint: Path,
    joint_checkpoint: Path,
    mask_manifest: Path,
) -> dict[str, Any]:
    processed = paths["processed_root"]
    sources = {
        "config": Path(config["_config_path"]),
        "action_checkpoint": action_checkpoint,
        "joint_checkpoint": joint_checkpoint,
        "model_code": PROJECT_ROOT / "src" / "arsc_eval" / "models.py",
        "data_code": PROJECT_ROOT / "src" / "arsc_eval" / "data.py",
        "test_manifest": processed / "test.jsonl",
        "mask_manifest": mask_manifest,
    }
    for perturbation in PERTURBATIONS:
        sources[f"{perturbation}_manifest"] = (
            processed / "perturbations" / f"{perturbation}.jsonl"
        )
    return {
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "image_size": int(config["image_size"]),
        "sources": {
            name: file_fingerprint(path) for name, path in sources.items()
        },
    }


def make_eval_loader(
    config: dict[str, Any],
    manifest: Path,
    image_root: Path,
    path_key: str = "file_name",
):
    return make_loader(
        manifest,
        image_root,
        int(config["image_size"]),
        int(config["training"]["batch_size"]),
        int(config["training"]["num_workers"]),
        shuffle=False,
        path_key=path_key,
    )


@torch.inference_mode()
def predict_pair(
    action_model: torch.nn.Module,
    joint_model: torch.nn.Module,
    loader,
    device: torch.device,
    amp: bool,
    keep_rationales: bool,
) -> dict[str, np.ndarray]:
    """Run both models over exactly the same loader order."""

    action_model.eval()
    joint_model.eval()
    action_logits = []
    joint_action_logits = []
    joint_rationale_logits = []
    action_targets = []
    rationale_targets = []
    file_names: list[str] = []
    for batch in loader:
        images = batch["image"].to(device, non_blocking=True)
        with torch.autocast(
            device_type=device.type,
            dtype=torch.float16,
            enabled=amp and device.type == "cuda",
        ):
            action_output = action_model(images)
            joint_output = joint_model(images)
        action_logits.append(
            action_output["action_logits"].float().cpu().numpy()
        )
        joint_action_logits.append(
            joint_output["action_logits"].float().cpu().numpy()
        )
        if keep_rationales:
            joint_rationale_logits.append(
                joint_output["rationale_logits"].float().cpu().numpy()
            )
        action_targets.append(batch["actions"].float().numpy())
        rationale_targets.append(batch["rationales"].float().numpy())
        file_names.extend(str(name) for name in batch["file_name"])

    if not action_logits:
        raise ValueError("prediction loader was empty")
    result = {
        "file_names": np.asarray(file_names, dtype=np.str_),
        "action_targets": np.concatenate(action_targets).astype(
            np.float32, copy=False
        ),
        "rationale_targets": np.concatenate(rationale_targets).astype(
            np.float32, copy=False
        ),
        "action_logits": np.concatenate(action_logits).astype(
            np.float32, copy=False
        ),
        "joint_action_logits": np.concatenate(joint_action_logits).astype(
            np.float32, copy=False
        ),
    }
    if keep_rationales:
        result["joint_rationale_logits"] = np.concatenate(
            joint_rationale_logits
        ).astype(np.float32, copy=False)
    return result


def assert_aligned(
    reference: dict[str, np.ndarray],
    candidate: dict[str, np.ndarray],
    label: str,
) -> None:
    for key in ("file_names", "action_targets", "rationale_targets"):
        if not np.array_equal(reference[key], candidate[key]):
            raise ValueError(f"{label} is not aligned on {key}")


def add_prediction_group(
    payload: dict[str, np.ndarray],
    prefix: str,
    predictions: dict[str, np.ndarray],
    include_targets: bool,
    include_rationales: bool,
) -> None:
    if include_targets:
        payload[f"{prefix}_file_names"] = predictions["file_names"]
        payload[f"{prefix}_action_targets"] = predictions["action_targets"]
        payload[f"{prefix}_rationale_targets"] = predictions[
            "rationale_targets"
        ]
    payload[f"{prefix}_action_logits"] = predictions["action_logits"]
    payload[f"{prefix}_joint_action_logits"] = predictions[
        "joint_action_logits"
    ]
    if include_rationales:
        payload[f"{prefix}_joint_rationale_logits"] = predictions[
            "joint_rationale_logits"
        ]


def generate_cache_arrays(
    config: dict[str, Any],
    paths: dict[str, Path],
    action_checkpoint: Path,
    joint_checkpoint: Path,
    mask_manifest: Path,
    device: torch.device,
) -> dict[str, np.ndarray]:
    action_model = load_checkpoint_model(
        str(action_checkpoint), "action_only", device
    )
    joint_model = load_checkpoint_model(
        str(joint_checkpoint), "joint", device
    )
    amp = bool(config["training"]["amp"])
    processed = paths["processed_root"]

    clean_loader = make_eval_loader(
        config,
        processed / "test.jsonl",
        paths["dataset_root"] / "data",
    )
    clean = predict_pair(
        action_model,
        joint_model,
        clean_loader,
        device,
        amp,
        keep_rationales=True,
    )
    payload: dict[str, np.ndarray] = {}
    add_prediction_group(
        payload,
        "test_clean",
        clean,
        include_targets=True,
        include_rationales=True,
    )
    # The analysis module uses shorter canonical target field names.
    payload["test_file_names"] = payload.pop("test_clean_file_names")
    payload["test_action_targets"] = payload.pop(
        "test_clean_action_targets"
    )
    payload["test_rationale_targets"] = payload.pop(
        "test_clean_rationale_targets"
    )

    for perturbation in PERTURBATIONS:
        loader = make_eval_loader(
            config,
            processed / "perturbations" / f"{perturbation}.jsonl",
            PROJECT_ROOT,
            "perturbed_path",
        )
        predictions = predict_pair(
            action_model,
            joint_model,
            loader,
            device,
            amp,
            keep_rationales=True,
        )
        assert_aligned(clean, predictions, f"{perturbation} perturbation")
        add_prediction_group(
            payload,
            f"test_{perturbation}",
            predictions,
            include_targets=False,
            include_rationales=True,
        )

    mask_records = read_jsonl(mask_manifest)
    mask_predictions: dict[str, dict[str, np.ndarray]] = {}
    for condition, path_key in (
        ("clean", "clean_path"),
        ("critical", "critical_path"),
        ("noncritical", "noncritical_path"),
    ):
        loader = make_eval_loader(
            config, mask_manifest, PROJECT_ROOT, path_key
        )
        mask_predictions[condition] = predict_pair(
            action_model,
            joint_model,
            loader,
            device,
            amp,
            keep_rationales=False,
        )
    assert_aligned(
        mask_predictions["clean"],
        mask_predictions["critical"],
        "critical masks",
    )
    assert_aligned(
        mask_predictions["clean"],
        mask_predictions["noncritical"],
        "noncritical masks",
    )
    for condition, predictions in mask_predictions.items():
        add_prediction_group(
            payload,
            f"mask_{condition}",
            predictions,
            include_targets=condition == "clean",
            include_rationales=False,
        )
    payload["mask_file_names"] = payload.pop("mask_clean_file_names")
    payload["mask_action_targets"] = payload.pop(
        "mask_clean_action_targets"
    )
    payload["mask_rationale_targets"] = payload.pop(
        "mask_clean_rationale_targets"
    )
    if all("localized_action_indices" in record for record in mask_records):
        action_mask = np.zeros(
            (len(mask_records), payload["mask_action_targets"].shape[1]),
            dtype=np.uint8,
        )
        for row, record in enumerate(mask_records):
            for action_index in record["localized_action_indices"]:
                action_mask[row, int(action_index)] = 1
        if np.any(action_mask.sum(axis=1) == 0):
            raise ValueError(
                "mask manifest has an empty rationale-action binding"
            )
        payload["mask_action_dimension_mask"] = action_mask
    payload["mask_detected_class"] = np.asarray(
        [
            str(record.get("detected_class", "unknown"))
            for record in mask_records
        ],
        dtype=np.str_,
    )
    return payload


def save_cache(
    path: Path,
    arrays: dict[str, np.ndarray],
    metadata: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(arrays)
    payload["metadata_json"] = np.asarray(
        json.dumps(metadata, sort_keys=True, separators=(",", ":")),
        dtype=np.str_,
    )
    np.savez_compressed(path, **payload)


def load_cache(
    path: Path,
    expected_metadata: dict[str, Any],
) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as archive:
        if "metadata_json" not in archive:
            raise ValueError("cache has no metadata_json")
        actual_metadata = json.loads(str(archive["metadata_json"].item()))
        if actual_metadata != expected_metadata:
            raise ValueError(
                "cache provenance does not match current checkpoints, "
                "config, code, or manifests"
            )
        arrays = {
            name: archive[name].copy()
            for name in archive.files
            if name != "metadata_json"
        }
    return arrays


def write_flat_csv(path: Path, families: list[dict[str, Any]]) -> None:
    columns = [
        "Cohort",
        "Condition",
        "Metric",
        "Preferred_Direction",
        "Samples",
        "Comparison_Type",
        "Model",
        "Reference_Model",
        "Contrast_Direction",
        "Estimate",
        "CI_Lower",
        "CI_Upper",
        "Bootstrap_Probability_GT_Zero",
        "Bootstrap_Probability_LT_Zero",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for family in families:
            common = {
                "Cohort": family["cohort"],
                "Condition": family["condition"],
                "Metric": family["metric"],
                "Preferred_Direction": family["preferred_direction"],
                "Samples": family["samples"],
            }
            for estimate in family["model_estimates"]:
                writer.writerow(
                    {
                        **common,
                        "Comparison_Type": "model_estimate",
                        "Model": estimate["model"],
                        "Reference_Model": "",
                        "Contrast_Direction": "",
                        "Estimate": estimate["estimate"],
                        "CI_Lower": estimate["ci_lower"],
                        "CI_Upper": estimate["ci_upper"],
                        "Bootstrap_Probability_GT_Zero": "",
                        "Bootstrap_Probability_LT_Zero": "",
                    }
                )
            for contrast in family["paired_contrasts"]:
                writer.writerow(
                    {
                        **common,
                        "Comparison_Type": "paired_contrast",
                        "Model": contrast["model"],
                        "Reference_Model": contrast["reference_model"],
                        "Contrast_Direction": contrast["direction"],
                        "Estimate": contrast["estimate"],
                        "CI_Lower": contrast["ci_lower"],
                        "CI_Upper": contrast["ci_upper"],
                        "Bootstrap_Probability_GT_Zero": contrast[
                            "bootstrap_probability_gt_zero"
                        ],
                        "Bootstrap_Probability_LT_Zero": contrast[
                            "bootstrap_probability_lt_zero"
                        ],
                    }
                )


def main() -> int:
    args = parse_args()
    if args.bootstrap_replicates < 100:
        raise ValueError("--bootstrap-replicates must be at least 100")
    if not 0 < args.confidence_level < 1:
        raise ValueError("--confidence-level must be between zero and one")
    if args.refresh_cache and args.analysis_only:
        raise ValueError("--refresh-cache and --analysis-only conflict")

    config = load_config(args.config)
    paths = resolve_paths(config)
    action_checkpoint = rooted(args.action_checkpoint)
    joint_checkpoint = rooted(args.joint_checkpoint)
    calibration_path = rooted(args.calibration)
    mask_manifest = rooted(args.mask_manifest)
    cache_path = rooted(args.cache)
    output_json = rooted(args.output_json)
    output_csv = rooted(args.output_csv)

    calibration = json.loads(
        calibration_path.read_text(encoding="utf-8")
    )
    temperature = float(calibration["temperature"])
    metadata = cache_source_metadata(
        config,
        paths,
        action_checkpoint,
        joint_checkpoint,
        mask_manifest,
    )

    cache_status = "reused"
    arrays: dict[str, np.ndarray] | None = None
    if cache_path.is_file() and not args.refresh_cache:
        try:
            arrays = load_cache(cache_path, metadata)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
            if args.analysis_only:
                raise RuntimeError(f"cannot reuse prediction cache: {error}")
    if arrays is None:
        if args.analysis_only:
            raise FileNotFoundError(
                f"valid prediction cache not found: {cache_path}"
            )
        cache_status = "generated"
        arrays = generate_cache_arrays(
            config,
            paths,
            action_checkpoint,
            joint_checkpoint,
            mask_manifest,
            device_from_arg(args.device),
        )
        save_cache(cache_path, arrays, metadata)

    threshold = float(config["training"]["threshold"])
    prepared = prepare_probabilities(arrays, temperature, threshold)
    test_count = len(arrays["test_action_targets"])
    mask_count = len(arrays["mask_action_targets"])

    seed_sequence = np.random.SeedSequence(args.bootstrap_seed)
    test_seed, mask_seed = seed_sequence.spawn(2)
    test_estimates, test_draws = paired_bootstrap(
        lambda indices: test_metric_estimates(
            prepared, threshold, indices
        ),
        sample_count=test_count,
        replicates=args.bootstrap_replicates,
        rng=np.random.default_rng(test_seed),
    )
    mask_estimates, mask_draws = paired_bootstrap(
        lambda indices: mask_metric_estimates(prepared, indices),
        sample_count=mask_count,
        replicates=args.bootstrap_replicates,
        rng=np.random.default_rng(mask_seed),
    )
    estimates = {**test_estimates, **mask_estimates}
    draws = {**test_draws, **mask_draws}
    sample_sizes = {
        ("clean", "official_test"): test_count,
        ("consistency", "brightness"): test_count,
        ("consistency", "blur"): test_count,
        ("consistency", "noise"): test_count,
        ("consistency", "mean_three"): test_count,
        ("critical_masks", "detector_subset"): mask_count,
    }
    if "mask_action_dimension_mask" in arrays:
        sample_sizes.pop(("critical_masks", "detector_subset"))
        rationale_bound_estimates, rationale_bound_draws = paired_bootstrap(
            lambda indices: mask_metric_estimates(
                prepared, indices, "rationale_bound_all"
            ),
            sample_count=mask_count,
            replicates=args.bootstrap_replicates,
            rng=np.random.default_rng(mask_seed),
        )
        estimates = {**test_estimates, **rationale_bound_estimates}
        draws = {**test_draws, **rationale_bound_draws}
        sample_sizes[("critical_masks", "rationale_bound_all")] = mask_count

        detected_classes = np.asarray(arrays["mask_detected_class"])
        stratum_sequences = mask_seed.spawn(len(np.unique(detected_classes)))
        for detected_class, stratum_seed in zip(
            np.unique(detected_classes),
            stratum_sequences,
            strict=True,
        ):
            subset = np.flatnonzero(detected_classes == detected_class)
            if len(subset) < 20:
                continue
            condition = f"rationale_bound_class_{detected_class}"

            def stratum_compute(
                local_indices: np.ndarray | None,
                subset_indices: np.ndarray = subset,
                stratum_condition: str = condition,
            ):
                selected = (
                    subset_indices
                    if local_indices is None
                    else subset_indices[local_indices]
                )
                return mask_metric_estimates(
                    prepared, selected, stratum_condition
                )

            stratum_estimates, stratum_draws = paired_bootstrap(
                stratum_compute,
                sample_count=len(subset),
                replicates=args.bootstrap_replicates,
                rng=np.random.default_rng(stratum_seed),
            )
            estimates.update(stratum_estimates)
            draws.update(stratum_draws)
            sample_sizes[("critical_masks", condition)] = len(subset)
    families = summarize_families(
        estimates,
        draws,
        sample_sizes,
        args.confidence_level,
    )

    result = {
        "analysis": (
            "BDD-OIA internal-validity extension with direct Action-Only "
            "versus Joint CEG and paired sample bootstrap"
        ),
        "does_not_modify_primary_outputs": True,
        "prediction_cache": {
            "path": display_path(cache_path),
            "status": cache_status,
            "schema_version": CACHE_SCHEMA_VERSION,
            "test_samples": test_count,
            "mask_samples": mask_count,
            "source_fingerprints": metadata["sources"],
            "calibration": file_fingerprint(calibration_path),
        },
        "bootstrap": {
            "method": "paired nonparametric percentile bootstrap",
            "unit": (
                "official test example; the three perturbations remain "
                "clustered within example for mean-three metrics"
            ),
            "replicates": args.bootstrap_replicates,
            "seed": args.bootstrap_seed,
            "confidence_level": args.confidence_level,
            "same_resample_indices_across_models": True,
            "multiple_comparison_correction": None,
        },
        "metric_definitions": {
            "causal_evidence_gap": (
                "mean[(p_clean_positive - p_critical_positive) - "
                "(p_clean_positive - p_noncritical_positive)]; "
                "equivalently mean[p_noncritical_positive - "
                "p_critical_positive]"
            ),
            "positive_action_probability": (
                "pilot masks: mean probability over all positive ground-truth "
                "actions"
            ),
            "rationale_bound_action_probability": (
                "v2 masks: mean probability assigned to the annotated binary "
                "state of action dimensions associated with the localized "
                "rationale"
            ),
            "action_error": (
                "any mismatch in the thresholded four-label action set"
            ),
            "confidence": "maximum of the four action probabilities",
            "threshold": threshold,
            "temperature": temperature,
            "mask_target_policy": (
                "rationale_bound_ground_truth_action_state"
                if "mask_action_dimension_mask" in arrays
                else "all_positive_ground_truth_actions"
            ),
        },
        "families": families,
        "methodological_caveats": [
            (
                "The detector-conditioned mask subset is non-random; its CEG "
                "interval does not generalize to test examples without a "
                "matching COCO detection."
            ),
            (
                "CEG is a controlled occlusion sensitivity contrast, not a "
                "causal identification result. A larger value can also arise "
                "from mask artifacts or model fragility."
            ),
            (
                "The clean term cancels algebraically in the current CEG. "
                "Clean predictions are retained to report and audit the two "
                "component probability drops."
            ),
            (
                "Joint-Calibrated is the same Joint checkpoint with scalar "
                "action temperature scaling, not an independently trained "
                "model; rationale metrics are therefore identical."
            ),
            (
                "Percentile intervals quantify sampling uncertainty for this "
                "single trained seed only; they do not include training-seed "
                "or detector uncertainty and are not multiplicity-adjusted."
            ),
            (
                "Maximum positive-label probability is preserved as the "
                "primary confidence definition for comparability, although "
                "it does not represent confidence in negative labels for a "
                "multilabel prediction."
            ),
            (
                "Cache provenance hashes checkpoints, manifests, config, and "
                "model/data code, but not every generated image byte."
            ),
        ],
    }
    write_json(output_json, json_safe(result))
    write_flat_csv(output_csv, families)

    ceg_family = next(
        family
        for family in families
        if family["metric"] == "causal_evidence_gap"
    )
    print(
        json.dumps(
            {
                "output_json": display_path(output_json),
                "output_csv": display_path(output_csv),
                "cache": display_path(cache_path),
                "cache_status": cache_status,
                "causal_evidence_gap": ceg_family,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
