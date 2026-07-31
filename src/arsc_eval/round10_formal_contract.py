"""Strict outcome-blind authorization and one-shot output guards."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


GO_SCHEMA = "ARSC_ROUND10_PREFORMAL_REVIEWER_DECISION_V1"
GO_DECISION = "GO_ROUND10_FORMAL_RUN_ATTEMPT02"
EXPECTED_REVIEW_MODE = {
    "outcome_blind": True,
    "checkpoint_tensors_loaded": False,
    "model_constructed_or_loaded": False,
    "model_inference_run": False,
    "round10_nonzero_severity_predictions_read_or_computed": False,
    "round10_nonzero_severity_logits_read_or_computed": False,
    "round10_nonzero_severity_confidences_read_or_computed": False,
    "round10_nonzero_severity_metric_outcomes_read_or_computed": False,
    "formal_run_started": False,
    "formal_implementation_modified": False,
}
REQUIRED_FORMAL_ARTIFACT_NAMES = (
    "seed_43_logits.npz",
    "seed_44_logits.npz",
    "seed_45_logits.npz",
    "seed_46_logits.npz",
    "seed_47_logits.npz",
    "round10_corruption_primitives.npz",
    "round10_corruption_point_diagnostics.csv",
    "round10_corruption_bootstrap_draws.npz",
    "round10_corruption_bootstrap_summary.csv",
    "round10_corruption_results.json",
)
PRE_RESULT_ARTIFACT_NAMES = REQUIRED_FORMAL_ARTIFACT_NAMES[:-1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_preformal_go(
    decision: Mapping[str, Any],
    implementation_commit: str,
    expected_reviewed_hashes: Mapping[str, str],
) -> None:
    require(decision["schema_version"] == GO_SCHEMA, "wrong GO schema")
    review = decision["review_mode"]
    require(
        set(review) == set(EXPECTED_REVIEW_MODE),
        "GO review_mode field set differs",
    )
    for name, expected in EXPECTED_REVIEW_MODE.items():
        require(
            type(review[name]) is bool and review[name] is expected,
            f"GO review mode differs: {name}",
        )
    verdict = decision["verdict"]
    require(
        verdict["decision"] == GO_DECISION,
        "formal-run GO decision differs",
    )
    require(
        verdict["formal_run_authorized"] is True,
        "formal run is not authorized",
    )
    require(
        verdict["authorized_attempt"] == "attempt02",
        "wrong authorized attempt",
    )
    bindings = decision["bindings"]
    require(
        bindings["implementation_commit"] == implementation_commit,
        "GO implementation commit differs",
    )
    reviewed = decision["reviewed_files_sha256"]
    require(
        set(reviewed) == set(expected_reviewed_hashes),
        "GO reviewed path set differs",
    )
    require(
        all(
            reviewed[path] == digest
            for path, digest in expected_reviewed_hashes.items()
        ),
        "GO reviewed file hash differs",
    )


def require_paths_absent(paths: Sequence[Path]) -> None:
    existing = sorted(str(path) for path in paths if path.exists())
    require(not existing, f"one-shot artifacts already exist: {existing}")


def validate_atomic_output_layout(
    staging_dir: Path,
    final_dir: Path,
    log_path: Path,
    artifact_index_path: Path,
) -> None:
    paths = (staging_dir, final_dir, log_path, artifact_index_path)
    require(len(set(paths)) == 4, "formal output paths must be distinct")
    require(
        staging_dir.parent == final_dir.parent,
        "staging and final directories must share a parent volume",
    )
    require(
        staging_dir.name.endswith(".staging"),
        "staging directory must be visibly marked",
    )
    require(
        "attempt02" in final_dir.name,
        "final directory must identify attempt02",
    )


def unexpected_round10_output_paths(
    paths: Sequence[str],
    allowed_exact: Sequence[str],
    allowed_prefixes: Sequence[str],
) -> list[str]:
    """Return every unknown Round 10 path under outputs.

    A strict allowlist is safer here than trying to predict every possible
    cache, temporary, staging, or run-artifact spelling.
    """

    exact = {
        str(Path(path)).replace("\\", "/").rstrip("/")
        for path in allowed_exact
    }
    prefix_roots = tuple(
        str(Path(path)).replace("\\", "/").rstrip("/")
        for path in allowed_prefixes
    )
    unexpected = set()
    for raw_path in paths:
        path = str(Path(raw_path)).replace("\\", "/").rstrip("/")
        lowered = path.lower()
        if not lowered.startswith("outputs/") or "round10" not in lowered:
            continue
        if path in exact or any(
            path == prefix or path.startswith(prefix + "/")
            for prefix in prefix_roots
        ):
            continue
        unexpected.add(path)
    return sorted(unexpected)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def validate_formal_artifacts(
    final_dir: Path,
    project_root: Path,
    result: Mapping[str, Any],
) -> dict[str, str]:
    """Validate the exact final file set and the nine internal hashes."""

    require(final_dir.is_dir(), "formal final directory is absent")
    relative_entries = sorted(
        path.relative_to(final_dir).as_posix()
        for path in final_dir.rglob("*")
    )
    require(
        relative_entries == sorted(REQUIRED_FORMAL_ARTIFACT_NAMES),
        "formal artifact path set differs",
    )
    internal = result["artifact_sha256_before_result_json"]
    expected_paths = {
        (final_dir / name).relative_to(project_root).as_posix()
        for name in PRE_RESULT_ARTIFACT_NAMES
    }
    require(
        set(internal) == expected_paths,
        "result internal artifact path set differs",
    )
    observed = {
        (final_dir / name).relative_to(project_root).as_posix(): sha256_file(
            final_dir / name
        )
        for name in PRE_RESULT_ARTIFACT_NAMES
    }
    require(
        all(
            type(internal[path]) is str
            and internal[path].upper() == digest
            for path, digest in observed.items()
        ),
        "result internal artifact hash differs",
    )
    return observed
