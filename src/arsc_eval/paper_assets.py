"""Shared loaders and writers for the ARSC paper asset pipeline.

Every function here reads *frozen* artifacts produced by the original
experiment rounds and never recomputes a model forward pass.  The pipeline is
deliberately torch-free so the paper tables and figures can be regenerated in
a plain numpy environment: ``arsc_eval.utils`` imports torch at module scope,
which the training and inference scripts need but the analysis scripts do not.

Terminology used throughout the paper assets (see
``docs/paper/ARSC_CLAIMS_AND_TERMINOLOGY.md``):

======  ==================================================================
Axis    Operationalisation in this repository
======  ==================================================================
``A``   Action Performance -- 4-action Macro-F1 at threshold 0.5.
``R``   Rationale-label Performance -- 21-class rationale Macro/Micro-F1.
``S``   Selective Risk & Calibration -- AURC, UAR@90, ECE.
``C``   Prediction Stability under semantics-preserving perturbations --
        clean vs perturbed thresholded action-set flip rate.
======  ==================================================================
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VALIDITY_DIR = PROJECT_ROOT / "outputs" / "validity"
PAPER_DIR = PROJECT_ROOT / "outputs" / "paper"

FROZEN_SEEDS: tuple[int, ...] = (43, 44, 45, 46, 47)
FROZEN_THRESHOLD = 0.5
PERTURBATION_FAMILIES: tuple[str, ...] = ("brightness", "blur", "noise")

MODEL_ACTION = "Action-Only"
MODEL_JOINT = "Joint Action-Rationale"
MODELS: tuple[str, ...] = (MODEL_ACTION, MODEL_JOINT)

#: Short labels for figures and narrow table columns.
MODEL_SHORT = {MODEL_ACTION: "Action-Only", MODEL_JOINT: "Joint"}

AXIS_ORDER: tuple[str, ...] = ("A", "R", "S", "C1")

AXIS_NAMES = {
    "A": "Action Performance",
    "R": "Rationale-label Performance",
    "S": "Selective Risk & Calibration",
    "C1": "Prediction Stability",
}

AXIS_OPERATIONALISATION = {
    "A": "4-action Macro-F1 @ 0.5",
    "R": "21-class rationale Macro-F1 @ 0.5",
    "S": "AURC / UAR@90 / ECE (exact-set error, calibrated)",
    "C1": "clean vs perturbed action-set flip rate @ 0.5",
}

#: What each axis explicitly does *not* measure.  Quoted in the figures and
#: tables so a reader cannot pick up the stronger reading by accident.
AXIS_NOT = {
    "A": "not a safety guarantee",
    "R": "not reasoning faithfulness",
    "S": "not 'Safety'; a selective-prediction operating characteristic",
    "C1": "not real-road robustness, not evidence faithfulness",
}

#: Direction of improvement for every metric the paper assets report.
LOWER_IS_BETTER = {
    "aurc": True,
    "unsafe_acceptance_rate_90": True,
    "ece": True,
    "ece_calibrated": True,
    "ece_uncalibrated": True,
    "action_flip_rate": True,
    "action_macro_f1": False,
    "action_micro_f1": False,
    "rationale_macro_f1": False,
    "rationale_micro_f1": False,
    "rationale_jaccard": False,
}

#: Pre-registered practical-equivalence margin for delta Action Macro-F1.
ACTION_EQUIVALENCE_MARGIN = 0.03


# --------------------------------------------------------------------------
# IO helpers (torch-free)
# --------------------------------------------------------------------------
def rooted(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def write_json(path: str | Path, value: Any) -> Path:
    output = rooted(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return output


def read_json(path: str | Path) -> Any:
    return json.loads(rooted(path).read_text(encoding="utf-8"))


def write_csv(
    path: str | Path,
    rows: Sequence[Mapping[str, Any]],
    fieldnames: Iterable[str] | None = None,
) -> Path:
    output = rooted(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"refusing to write an empty table to {output}")
    names = list(fieldnames) if fieldnames is not None else list(rows[0])
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=names)
        writer.writeheader()
        writer.writerows(rows)
    return output


def write_markdown_table(
    path: str | Path,
    title: str,
    preamble: Sequence[str],
    header: Sequence[str],
    rows: Sequence[Sequence[Any]],
    notes: Sequence[str] = (),
) -> Path:
    """Write a GitHub-flavoured markdown table with provenance notes."""

    output = rooted(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [f"# {title}", ""]
    lines.extend(preamble)
    if preamble:
        lines.append("")
    lines.append("| " + " | ".join(str(cell) for cell in header) + " |")
    lines.append("| " + " | ".join("---" for _ in header) + " |")
    for row in rows:
        cells = [
            "" if cell is None else str(cell).replace("|", "\\|")
            for cell in row
        ]
        lines.append("| " + " | ".join(cells) + " |")
    if notes:
        lines.extend(["", "## Notes", ""])
        lines.extend(f"- {note}" for note in notes)
    lines.append("")
    output.write_text("\n".join(lines), encoding="utf-8")
    return output


def format_signed(value: float, digits: int = 6) -> str:
    return f"{value:+.{digits}f}"


def format_interval(lower: float, upper: float, digits: int = 6) -> str:
    return f"[{lower:+.{digits}f}, {upper:+.{digits}f}]"


def sha256_of(path: str | Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with rooted(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


# --------------------------------------------------------------------------
# Frozen artifact loaders
# --------------------------------------------------------------------------
RQ1_SUMMARY_PATH = VALIDITY_DIR / "rq1_multiseed_summary.json"
ROUND10_DIR = VALIDITY_DIR / "round10_corruption_formal_attempt02"
ROUND10_RESULTS_PATH = ROUND10_DIR / "round10_corruption_results.json"
ROUND10_DIAGNOSTICS_PATH = ROUND10_DIR / "round10_corruption_point_diagnostics.csv"
ROUND12_RESULTS_PATH = VALIDITY_DIR / "round12_existing_outputs_results.json"


def load_rq1_summary() -> dict[str, Any]:
    """The frozen Round 5 five-seed aggregation."""

    return read_json(RQ1_SUMMARY_PATH)


def rq1_metric_rows(summary: Mapping[str, Any] | None = None) -> dict[str, dict[str, float]]:
    """Frozen Round 5 metric summary keyed by metric name."""

    summary = summary if summary is not None else load_rq1_summary()
    return {row["metric"]: row for row in summary["metric_summary"]}


def rq1_seed_metrics(
    summary: Mapping[str, Any] | None = None,
) -> dict[int, dict[str, float]]:
    """Frozen Round 5 per-seed point estimates."""

    summary = summary if summary is not None else load_rq1_summary()
    return {
        int(seed): values for seed, values in summary["raw_seed_metrics"].items()
    }


def load_round10_results() -> dict[str, Any]:
    return read_json(ROUND10_RESULTS_PATH)


def load_round10_diagnostics() -> list[dict[str, str]]:
    """Rows of the frozen Round 10 point-diagnostics table."""

    with ROUND10_DIAGNOSTICS_PATH.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def round10_primary_curves() -> dict[tuple[str, str, str], dict[int, list[float]]]:
    """Frozen Round 10 dose-response curves.

    Returns a mapping from ``(family, axis, component)`` to
    ``{severity_level: [value per seed in FROZEN_SEEDS order]}``.
    """

    curves: dict[tuple[str, str, str], dict[int, dict[int, float]]] = {}
    for row in load_round10_diagnostics():
        if row["record_type"] != "primary_curve":
            continue
        key = (row["family"], row["axis"], row["component"])
        level = int(row["level"])
        seed = int(row["seed"])
        curves.setdefault(key, {}).setdefault(level, {})[seed] = float(row["value"])
    ordered: dict[tuple[str, str, str], dict[int, list[float]]] = {}
    for key, by_level in curves.items():
        ordered[key] = {
            level: [by_seed[seed] for seed in FROZEN_SEEDS]
            for level, by_seed in sorted(by_level.items())
        }
    return ordered


def load_round12_results() -> dict[str, Any]:
    return read_json(ROUND12_RESULTS_PATH)


def seed_output_dir(seed: int) -> Path:
    return VALIDITY_DIR / f"rq1_seed_{seed}"


def load_seed_temperatures(seed: int) -> dict[str, float]:
    """Frozen temperature-scaling result for one seed."""

    directory = seed_output_dir(seed)
    result = {}
    for model, filename, expected in (
        (MODEL_ACTION, "calibration_action_only.json", "action_only"),
        (MODEL_JOINT, "calibration_joint.json", "joint"),
    ):
        payload = read_json(directory / filename)
        if payload["model_type"] != expected:
            raise RuntimeError(f"wrong model calibration in {filename}")
        result[model] = float(payload["temperature"])
    return result


def load_seed_cache(seed: int) -> dict[str, np.ndarray]:
    """Frozen lossless logit cache for one seed."""

    path = seed_output_dir(seed) / "prediction_cache" / "rq1_lossless.npz"
    with np.load(path, allow_pickle=False) as archive:
        return {key: np.asarray(archive[key]) for key in archive.files}


def load_seed_metrics_json(seed: int) -> dict[str, Any]:
    """Frozen per-seed Round 5 metric record (includes per-class F1)."""

    return read_json(seed_output_dir(seed) / "rq1_metrics.json")


def provenance(paths: Iterable[str | Path]) -> list[dict[str, str]]:
    """SHA-256 provenance records for the frozen inputs an asset consumed."""

    records = []
    for path in paths:
        resolved = rooted(path)
        records.append(
            {
                "path": str(resolved.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "sha256": sha256_of(resolved),
            }
        )
    return records
