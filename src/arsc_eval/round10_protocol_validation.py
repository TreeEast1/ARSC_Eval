"""Pure outcome-blind validators for Round 10 amendment 01."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np


FAMILIES = ("brightness", "blur", "noise")
NONZERO_LEVELS = (1, 2, 3, 4)
EXPECTED_PARAMETERS = {
    "brightness": (1.05, 1.10, 1.20, 1.30),
    "blur": (0.5, 1.0, 1.5, 2.0),
    "noise": (2.5, 5.0, 7.5, 10.0),
}
PRACTICAL_THRESHOLDS = {
    "A": {
        "components": ("action_only", "joint"),
        "threshold": 0.01,
    },
    "R": {
        "components": ("joint_rationale",),
        "threshold": 0.01,
    },
    "S": {
        "components": ("action_only", "joint"),
        "threshold": 0.01,
    },
    "C1": {
        "components": (
            "action_only_flip",
            "joint_flip",
            "joint_rationale_jaccard",
        ),
        "threshold": 0.025,
    },
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest().upper()


def expected_sample_indices(
    population_count: int,
    sample_count: int = 100,
    seed: int = 20260810,
) -> np.ndarray:
    require(population_count >= sample_count, "sample exceeds population")
    return np.sort(
        np.random.default_rng(seed).choice(
            population_count,
            size=sample_count,
            replace=False,
        )
    ).astype(np.int64)


def expected_semantic_keys(
    sample_count: int = 100,
) -> list[tuple[int, str, int]]:
    return [
        (audit_index, family, level)
        for audit_index in range(1, sample_count + 1)
        for family in FAMILIES
        for level in NONZERO_LEVELS
    ]


def semantic_key_sha256(
    keys: Sequence[tuple[int, str, int]],
) -> str:
    return canonical_sha256(
        [
            {
                "audit_index": int(index),
                "family": family,
                "level": int(level),
            }
            for index, family, level in keys
        ]
    )


def validate_practical_gate_schema(amendment: Mapping[str, Any]) -> None:
    gates = amendment["replacement_practical_endpoint_gates"]
    require(
        gates["comparison_operator"]
        == (
            "greater than or equal to; no rounding, tolerance, or "
            "printed-value comparison"
        ),
        "wrong practical comparison operator",
    )
    require(
        "observed five-seed mean alone" in gates["statistical_level"],
        "practical statistical level is not the observed five-seed mean",
    )
    require(
        gates["uncertainty_role"].endswith(
            "No pointwise or Bonferroni endpoint confidence bound is an "
            "additional practical-threshold gate."
        ),
        "practical uncertainty role differs",
    )
    for axis, specification in PRACTICAL_THRESHOLDS.items():
        gate = gates[axis]
        require(
            tuple(gate["per_seed_component_effects"])
            == specification["components"],
            f"wrong practical components for {axis}",
        )
        require(
            f">= {specification['threshold']}" in gate["primary_gate"],
            f"wrong practical threshold for {axis}",
        )
        require(
            gate["requires_every_seed_to_meet_threshold"] is False,
            f"unexpected all-seed practical gate for {axis}",
        )


def validate_bootstrap_schema(amendment: Mapping[str, Any]) -> None:
    bootstrap = amendment["replacement_bootstrap_numeric_contract"]
    require(bootstrap["replicates"] == 5000, "wrong bootstrap count")
    require(
        bootstrap["rng"] == "numpy.random.default_rng(20260810)",
        "wrong bootstrap rng",
    )
    require(
        bootstrap["pointwise_interval"]["numpy_method"] == "linear",
        "wrong pointwise quantile method",
    )
    require(
        bootstrap["bonferroni_primary_lower_bound"]["numpy_method"]
        == "linear",
        "wrong Bonferroni quantile method",
    )
    require(
        bootstrap["bonferroni_primary_lower_bound"]["quantile"]
        == 0.05 / 12.0,
        "wrong Bonferroni lower quantile",
    )
    require(
        "five selected-position bottlenecks"
        in bootstrap["replicate_gate_statistic"]
        and "family-axis mean-bottleneck"
        in bootstrap["bonferroni_primary_lower_bound"]["input"],
        "Bonferroni bound has wrong statistic",
    )
    require(
        bootstrap["bonferroni_primary_lower_bound"]["exact_zero_passes"]
        is False,
        "exact zero must fail Bonferroni strict positivity",
    )
    require(
        bootstrap["descriptive_endpoint_bootstrap"][
            "affects_practical_gate"
        ]
        is False,
        "endpoint bootstrap must remain descriptive",
    )
    require(
        bootstrap["seed_sampling"][
            "duplicate_selected_seed_positions_are_retained"
        ]
        is True,
        "duplicate seed draws must be retained",
    )
    require(
        bootstrap["clip_sampling"][
            "duplicate_selected_clip_positions_are_retained"
        ]
        is True,
        "duplicate clip draws must be retained",
    )
    require(
        bootstrap["mandatory_saved_arrays"][
            "family_axis_gate_draws_shape"
        ]
        == [5000, 12],
        "wrong gate draw shape",
    )
    require(
        bootstrap["mandatory_saved_arrays"]["seed_position_draws_shape"]
        == [5000, 5],
        "wrong seed draw shape",
    )
    require(
        bootstrap["mandatory_saved_arrays"]["clip_position_draws_shape"]
        == [5000, 3904],
        "wrong clip draw shape",
    )


def validate_amendment_schema(amendment: Mapping[str, Any]) -> None:
    require(
        amendment["schema_version"]
        == (
            "ARSC_ROUND10_CORRUPTION_DOSE_RESPONSE_PROTOCOL_"
            "AMENDMENT01_V1"
        ),
        "wrong amendment schema",
    )
    repair = amendment["repair_authorization"]
    require(
        repair["decision"] == "STOP/REPAIR_PROTOCOL_PREFLIGHT",
        "wrong repair authorization",
    )
    require(
        repair["outcome_blind_repair_authorized"] is True,
        "repair is not authorized",
    )
    require(
        repair["formal_implementation_authorized"] is False,
        "formal implementation must remain unauthorized",
    )
    require(
        repair["formal_run_authorized"] is False,
        "formal run must remain unauthorized",
    )
    validate_practical_gate_schema(amendment)
    validate_bootstrap_schema(amendment)
    semantic = amendment["replacement_semantic_audit_contract"]
    require(
        semantic["same_frozen_sample_seed"] == 20260810,
        "wrong semantic sample seed",
    )
    require(
        semantic["same_sample_count"] == 100,
        "wrong semantic sample count",
    )
    preflight = amendment["replacement_preflight_contract"]
    require(preflight["attempt"] == "attempt02", "wrong preflight attempt")
    require(
        preflight["formal_implementation_authorized"] is False,
        "preflight must not authorize implementation",
    )
    require(
        preflight["formal_run_authorized"] is False,
        "preflight must not authorize formal run",
    )


def _strict_boolean(value: Any, name: str) -> bool:
    require(type(value) is bool, f"{name} must be a JSON boolean")
    return value


def validate_review_decision(
    decision: Mapping[str, Any],
    valid_keys: Sequence[tuple[int, str, int]],
    expected_bindings: Mapping[str, str],
) -> dict[tuple[int, str, int], Mapping[str, Any]]:
    require(
        decision["schema_version"]
        == "ARSC_ROUND10_SEMANTIC_REVIEW_DECISION_AMENDMENT01_V1",
        "wrong semantic review schema",
    )
    require(
        decision["reviewed_all_30_labelled_contact_sheets"] is True,
        "not all labelled contact sheets were reviewed",
    )
    require(
        decision["reviewed_all_1200_pairs_with_displayed_labels"] is True,
        "not all labelled image-stratum pairs were reviewed",
    )
    bindings = decision["bindings"]
    require(
        set(bindings) == set(expected_bindings),
        "semantic binding key set differs",
    )
    require(
        all(
            bindings[name] == expected
            for name, expected in expected_bindings.items()
        ),
        "semantic binding value differs",
    )
    defaults = decision["default_decisions"]
    require(
        set(defaults)
        == {
            "action_and_rationale_labels_still_applicable",
            "scene_semantics_preserved",
        },
        "wrong default decision fields",
    )
    _strict_boolean(
        defaults["action_and_rationale_labels_still_applicable"],
        "default label-applicability decision",
    )
    _strict_boolean(
        defaults["scene_semantics_preserved"],
        "default scene decision",
    )
    allowed_override_fields = {
        "audit_index",
        "family",
        "level",
        "action_and_rationale_labels_still_applicable",
        "scene_semantics_preserved",
        "review_notes",
    }
    valid_key_set = set(valid_keys)
    overrides: dict[tuple[int, str, int], Mapping[str, Any]] = {}
    for item in decision["overrides"]:
        require(
            set(item) == allowed_override_fields,
            "override fields are missing or extra",
        )
        require(
            type(item["audit_index"]) is int,
            "override audit_index must be an integer",
        )
        require(
            type(item["family"]) is str,
            "override family must be a string",
        )
        require(
            type(item["level"]) is int,
            "override level must be an integer",
        )
        require(
            type(item["review_notes"]) is str,
            "override review_notes must be a string",
        )
        _strict_boolean(
            item["action_and_rationale_labels_still_applicable"],
            "override label-applicability decision",
        )
        _strict_boolean(
            item["scene_semantics_preserved"],
            "override scene decision",
        )
        key = (
            item["audit_index"],
            item["family"],
            item["level"],
        )
        require(key in valid_key_set, "override key is out of grid")
        require(key not in overrides, "duplicate override key")
        overrides[key] = item
    return overrides


def validate_semantic_raw_rows(
    rows: Sequence[Mapping[str, str]],
    selected_indices: Sequence[int],
    selected_records: Sequence[Mapping[str, Any]],
) -> list[tuple[int, str, int]]:
    require(len(rows) == 1200, "raw semantic manifest must have 1200 rows")
    require(
        len(selected_indices) == len(selected_records) == 100,
        "semantic sample must contain 100 aligned records",
    )
    expected_keys = expected_semantic_keys()
    observed_keys: list[tuple[int, str, int]] = []
    for row_number, (row, expected_key) in enumerate(
        zip(rows, expected_keys),
        start=1,
    ):
        key = (
            int(row["audit_index"]),
            row["family"],
            int(row["level"]),
        )
        require(key == expected_key, f"wrong key at raw row {row_number}")
        audit_index, family, level = key
        record = selected_records[audit_index - 1]
        require(
            int(row["dataset_index"])
            == int(selected_indices[audit_index - 1]),
            f"wrong dataset index at raw row {row_number}",
        )
        require(
            row["file_name"] == record["file_name"],
            f"wrong filename at raw row {row_number}",
        )
        require(
            float(row["parameter"])
            == EXPECTED_PARAMETERS[family][level - 1],
            f"wrong parameter at raw row {row_number}",
        )
        require(
            row["action_and_rationale_labels_still_applicable"] == "",
            f"raw decision is not blank at row {row_number}",
        )
        require(
            row["scene_semantics_preserved"] == "",
            f"raw scene decision is not blank at row {row_number}",
        )
        require(
            row["review_notes"] == "",
            f"raw review notes are not blank at row {row_number}",
        )
        observed_keys.append(key)
    require(
        len(set(observed_keys)) == 1200,
        "raw semantic keys are not unique",
    )
    strata = Counter((family, level) for _, family, level in observed_keys)
    require(
        set(strata) == set((f, q) for f in FAMILIES for q in NONZERO_LEVELS),
        "raw semantic strata differ",
    )
    require(
        all(count == 100 for count in strata.values()),
        "every semantic stratum must contain 100 rows",
    )
    return observed_keys


def validate_label_sidecar(
    rows: Sequence[Mapping[str, Any]],
    selected_indices: Sequence[int],
    selected_records: Sequence[Mapping[str, Any]],
) -> None:
    require(len(rows) == 100, "label sidecar must contain 100 rows")
    for offset, (row, dataset_index, record) in enumerate(
        zip(rows, selected_indices, selected_records),
        start=1,
    ):
        require(row["audit_index"] == offset, "wrong sidecar audit index")
        require(
            row["dataset_index"] == int(dataset_index),
            "wrong sidecar dataset index",
        )
        require(
            row["file_name"] == record["file_name"],
            "wrong sidecar filename",
        )
        require(
            row["action_vector"] == record["actions"],
            "wrong sidecar action vector",
        )
        require(
            row["rationale_vector"] == record["rationales"],
            "wrong sidecar rationale vector",
        )
        require(
            len(row["action_vector"]) == 4
            and all(value in (0, 1) for value in row["action_vector"]),
            "invalid sidecar action vector",
        )
        require(
            len(row["rationale_vector"]) == 21
            and all(value in (0, 1) for value in row["rationale_vector"]),
            "invalid sidecar rationale vector",
        )
        require(
            type(row["action_names"]) is list
            and all(type(value) is str for value in row["action_names"]),
            "invalid sidecar action names",
        )
        require(
            type(row["rationale_names"]) is list
            and all(type(value) is str for value in row["rationale_names"]),
            "invalid sidecar rationale names",
        )


def validate_page_hash_binding(
    expected_page_hashes: Mapping[str, str],
    reviewed_page_hashes: Mapping[str, str],
    actual_page_hashes: Mapping[str, str],
) -> None:
    """Require an exact 30-page build/review/filesystem hash binding."""
    require(
        len(expected_page_hashes) == 30,
        "expected page hash map must contain 30 pages",
    )
    require(
        set(reviewed_page_hashes) == set(expected_page_hashes),
        "reviewed page path set differs",
    )
    require(
        set(actual_page_hashes) == set(expected_page_hashes),
        "actual page path set differs",
    )
    require(
        dict(reviewed_page_hashes) == dict(expected_page_hashes),
        "reviewed page hash binding differs",
    )
    require(
        dict(actual_page_hashes) == dict(expected_page_hashes),
        "actual page hash binding differs",
    )


def local_arsc_dependencies(source: str) -> set[str]:
    tree = ast.parse(source)
    dependencies: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level and node.module:
                dependencies.add(
                    f"src/arsc_eval/{node.module.split('.')[0]}.py"
                )
            elif node.module and node.module.startswith("arsc_eval."):
                dependencies.add(
                    "src/arsc_eval/"
                    + node.module.split(".")[1]
                    + ".py"
                )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("arsc_eval."):
                    dependencies.add(
                        "src/arsc_eval/"
                        + alias.name.split(".")[1]
                        + ".py"
                    )
    return dependencies


def validate_bound_local_dependencies(
    source: str,
    bound_paths: Iterable[str],
) -> set[str]:
    dependencies = local_arsc_dependencies(source)
    missing = dependencies - set(bound_paths)
    require(not missing, f"unbound local dependencies: {sorted(missing)}")
    return dependencies


def forbidden_round10_paths(paths: Iterable[str]) -> list[str]:
    patterns = (
        re.compile(r"^scripts/(analyze|launch)_round10_corruption"),
        re.compile(r"^outputs/validity/round10_corruption_formal"),
        re.compile(r"^outputs/validity/round10_corruption_results"),
        re.compile(r"^outputs/validity/round10_corruption_primitives"),
        re.compile(r"^outputs/validity/round10_corruption_bootstrap"),
        re.compile(r"^outputs/validity/round10_corruption_point_diagnostics"),
        re.compile(r"^outputs/validity/round10_corruption_prediction_cache"),
        re.compile(
            r"^outputs/validity/round10_corruption_.*"
            r"(implementation_manifest|run_manifest)"
        ),
        re.compile(
            r"^outputs/validity/round10_corruption_.*"
            r"(\.tmp|\.temp|staging)(/|$)"
        ),
    )
    normalized = [str(Path(path)).replace("\\", "/") for path in paths]
    return sorted(
        {
            path
            for path in normalized
            if any(pattern.search(path) for pattern in patterns)
        }
    )


def require_no_forbidden_round10_paths(paths: Iterable[str]) -> None:
    forbidden = forbidden_round10_paths(paths)
    require(not forbidden, f"forbidden Round 10 artifacts exist: {forbidden}")
