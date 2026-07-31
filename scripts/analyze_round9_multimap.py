"""Run the one-shot preregistered Round 9 20-map robustness analysis.

``--preflight-only`` hashes structural artifacts, runs synthetic tests, and
reproduces the historical q0 bridge from the frozen Round 8 primitives. It
does not read new-map q>0 source rows or compute any q>0 metric. The default
mode additionally requires a hash-bound independent reviewer GO, repeats the
q0 bridge, then performs the single frozen point/bootstrap run.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.constants import ACTION_NAMES, RATIONALE_NAMES
from arsc_eval.graded_response import (
    AXIS_DIRECTIONS,
    MODEL_KEYS,
    PERTURBATION_KEYS,
    axis_bottlenecks,
    confidence_diagnostics,
    graded_axis_curves,
)
from arsc_eval.internal_validity import (
    action_flip_samples,
    rationale_jaccard_samples,
)
from arsc_eval.metrics import multilabel_f1
from arsc_eval.multimap_response import (
    grand_mean_curve_has_no_reversal,
    round9_axis_gate,
)
from arsc_eval.multimap_statistics import (
    curves_from_component_counts,
    harmonic_numbers,
    prepare_component_statistics,
)


VALIDITY_ROOT = PROJECT_ROOT / "outputs" / "validity"
PROTOCOL_PATH = VALIDITY_ROOT / "round9_multimap_protocol.json"
MAP_PATH = VALIDITY_ROOT / "round9_multimap_maps.npz"
MAP_MANIFEST_PATH = VALIDITY_ROOT / "round9_multimap_map_manifest.json"
COMPONENT_PATH = VALIDITY_ROOT / "round9_multimap_components.npz"
COMPONENT_MANIFEST_PATH = (
    VALIDITY_ROOT / "round9_multimap_component_manifest.json"
)
PREOUTCOME_AUDIT_PATH = (
    VALIDITY_ROOT / "round9_multimap_preoutcome_independent_audit.json"
)
PREOUTCOME_MANIFEST_PATH = (
    VALIDITY_ROOT / "round9_multimap_preoutcome_run_manifest.json"
)
PREIMPLEMENTATION_MEMO_PATH = (
    PROJECT_ROOT / "outputs" / "research_review_memo_round9_preimplementation.md"
)
SALT_REPLAY_AUDIT_PATH = (
    VALIDITY_ROOT / "round9_multimap_salt_replay_audit.json"
)
ROUND8_PRIMITIVES_PATH = (
    VALIDITY_ROOT / "round8_graded_response_primitives.npz"
)
ROUND8_RESULT_PATH = (
    VALIDITY_ROOT / "round8_graded_response_results.json"
)
PREFLIGHT_PATH = VALIDITY_ROOT / "round9_multimap_formal_preflight.json"
IMPLEMENTATION_MANIFEST_PATH = (
    VALIDITY_ROOT / "round9_multimap_formal_implementation_manifest.json"
)
REVIEWER_DECISION_PATH = (
    VALIDITY_ROOT / "round9_independent_reviewer_decision.json"
)
RESULT_PATH = VALIDITY_ROOT / "round9_multimap_results.json"
POINT_PATH = VALIDITY_ROOT / "round9_multimap_primitives.npz"
DRAW_PATH = VALIDITY_ROOT / "round9_multimap_bootstrap_draws.npz"
POINT_CSV_PATH = VALIDITY_ROOT / "round9_multimap_point_diagnostics.csv"
BOOTSTRAP_CSV_PATH = (
    VALIDITY_ROOT / "round9_multimap_bootstrap_summary.csv"
)
FORMAL_LOG_PATH = VALIDITY_ROOT / "round9_multimap_formal.log"

MAP_IDS = tuple(f"map{index:02d}" for index in range(20))
SEEDS = (43, 44, 45, 46, 47)
Q_VALUES = (0.0, 0.25, 0.5, 0.75, 1.0)
AXES = ("A", "R", "S", "C1")
AXIS_INDEX = {axis: index for index, axis in enumerate(AXES)}
ACTION_CLASS_NAMES = tuple(ACTION_NAMES)
RATIONALE_CLASS_NAMES = tuple(RATIONALE_NAMES)
S_DIAGNOSTICS = (
    "tie_averaged_aurc",
    "canonical_stable_aurc",
    "unsafe_acceptance_rate_90",
    "correctness_auroc",
    "ece",
    "exact_set_error_rate",
    "highest_confidence_decile_error_rate",
    "lowest_confidence_decile_error_rate",
)
SAMPLE_COUNT = 4557
COMPONENT_COUNT = 1625
REPLICATES = 2000
BOOTSTRAP_SEED = 20260809
THRESHOLD = 0.5
EXPECTED_INPUT_HASHES = {
    PROTOCOL_PATH: (
        "B8E180ECB3CDCE2F34EC987BDE33F9B8FEFE0D60509962C09D69811FD7D7F5F3"
    ),
    MAP_PATH: (
        "9F540646ABF101800F5BC65AF272F4906C57EBFA94BEBB78B909DD52F1E627F4"
    ),
    MAP_MANIFEST_PATH: (
        "1163E8AC6638FFD145167D0F3F5CFDEB6829A876FBAD7C4F06B14C3F0E37E7DB"
    ),
    COMPONENT_PATH: (
        "23C86D0B87C55287033531A66D0E78182263A2734A23C966D431B09DF0298272"
    ),
    COMPONENT_MANIFEST_PATH: (
        "AC7A688A1F0603DFA2D9CD3C9AE16FB000CB1B8B26427B589AD4DE24716CFBE9"
    ),
    PREOUTCOME_AUDIT_PATH: (
        "1E39F5F28591BE692B62204F79C2BB0CD1AFD0FFE954C7B232ABBCF3E63B8ADD"
    ),
    PREOUTCOME_MANIFEST_PATH: (
        "73F8F6A2A2EE7CE270C9C63F306A0149CC9C181A40F996A88C6E1AB12FB9FB79"
    ),
    PREIMPLEMENTATION_MEMO_PATH: (
        "2622B53D5C158066EAD48F730391743CD3277D3A0527FD59E8153C66EAEB8135"
    ),
    SALT_REPLAY_AUDIT_PATH: (
        "7D6472182906B7D442337BC44555BEC6C639B07B7426FF31AC27319C40124C2E"
    ),
    ROUND8_PRIMITIVES_PATH: (
        "6E51FB8842C6A6510364415C9D2D19C2307363024C34C8C7DE00DB57DCC7160C"
    ),
    ROUND8_RESULT_PATH: (
        "4CD0FCD16ED4A3BAE1D378FD10B3A44705F2433FDF3C3E15A26FBCE303AF6FD3"
    ),
}
FORMAL_ARTIFACT_OUTPUTS = (
    RESULT_PATH,
    POINT_PATH,
    DRAW_PATH,
    POINT_CSV_PATH,
    BOOTSTRAP_CSV_PATH,
)


def staging_path(path: Path) -> Path:
    return path.with_name(path.name + ".attempt01.tmp")


STAGING_OUTPUTS = tuple(
    staging_path(path) for path in FORMAL_ARTIFACT_OUTPUTS
)
PRE_RUN_OUTPUTS = (
    *FORMAL_ARTIFACT_OUTPUTS,
    *STAGING_OUTPUTS,
    FORMAL_LOG_PATH,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-only", action="store_true")
    return parser.parse_args()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def relative(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def array_sha256(values: np.ndarray) -> str:
    array = np.ascontiguousarray(values)
    digest = hashlib.sha256()
    digest.update(str(array.dtype).encode("ascii"))
    digest.update(str(array.shape).encode("ascii"))
    digest.update(array.tobytes())
    return digest.hexdigest().upper()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def run_tests(expected_count: int = 63) -> dict[str, Any]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    command = [
        sys.executable,
        "-m",
        "unittest",
        "discover",
        "-s",
        "tests",
        "-p",
        "test_*.py",
        "-v",
    ]
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    combined = completed.stdout + completed.stderr
    require(completed.returncode == 0, "full unit-test suite failed")
    require(
        f"Ran {expected_count} tests" in combined,
        f"expected {expected_count} tests",
    )
    require("\nOK" in combined, "unit-test suite did not report OK")
    return {
        "command": command,
        "expected_count": expected_count,
        "return_code": completed.returncode,
        "all_passed": True,
        "byte_stable_evidence": (
            "semantic return code, exact test count, and OK marker; "
            "wall-clock timing text is intentionally not hashed"
        ),
    }


def verify_frozen_hashes() -> dict[str, Any]:
    observed = {}
    for path, expected in EXPECTED_INPUT_HASHES.items():
        require(path.exists(), f"missing frozen input: {relative(path)}")
        digest = sha256_file(path)
        require(digest == expected, f"hash mismatch: {relative(path)}")
        observed[relative(path)] = digest
    return observed


def run_preflight() -> dict[str, Any]:
    require(
        not PREFLIGHT_PATH.exists()
        and not IMPLEMENTATION_MANIFEST_PATH.exists(),
        "formal preflight already exists; refusing to overwrite",
    )
    require(
        not any(path.exists() for path in PRE_RUN_OUTPUTS),
        "a formal Round 9 output already exists",
    )
    git_status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    require(not git_status, "worktree must be clean before formal preflight")
    git_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    hashes = verify_frozen_hashes()
    protocol = read_json(PROTOCOL_PATH)
    audit = read_json(PREOUTCOME_AUDIT_PATH)
    salt_replay = read_json(SALT_REPLAY_AUDIT_PATH)
    require(
        protocol["protocol_id"] == "ARSC_ROUND9_MULTIMAP_ROBUSTNESS_V1"
        and protocol["hierarchical_bootstrap"]["replicates"] == REPLICATES
        and protocol["hierarchical_bootstrap"]["seed"] == BOOTSTRAP_SEED,
        "protocol constants differ",
    )
    require(audit["all_passed"] is True, "preoutcome audit is not PASS")
    require(
        salt_replay["status"] == "PASS"
        and salt_replay["summary"]["maps_replayed"] == 20,
        "independent salt replay is not PASS",
    )
    tests = run_tests()
    q0_bridge = verify_q0_bridge_before_new_outcomes(
        load_round8_primitive_arrays(),
        read_json(ROUND8_RESULT_PATH),
        read_json(MAP_MANIFEST_PATH),
    )
    implementation_paths = (
        Path(__file__).resolve(),
        PROJECT_ROOT / "src" / "arsc_eval" / "multimap_statistics.py",
        PROJECT_ROOT / "src" / "arsc_eval" / "multimap_response.py",
        PROJECT_ROOT / "src" / "arsc_eval" / "graded_response.py",
        PROJECT_ROOT / "tests" / "test_multimap_statistics.py",
        PROJECT_ROOT / "tests" / "test_multimap_response.py",
        PROJECT_ROOT / "tests" / "test_graded_response.py",
        PROJECT_ROOT / "scripts" / "verify_round9_salt_replay.py",
        PROJECT_ROOT / "scripts" / "verify_round9_preoutcome_artifacts.py",
        PROJECT_ROOT / "scripts" / "launch_round9_multimap_tmux.sh",
    )
    implementation_hashes = {
        relative(path): sha256_file(path) for path in implementation_paths
    }
    preflight = {
        "study": "Round 9 formal implementation preflight",
        "status": "PASS_AWAITING_INDEPENDENT_REVIEWER_GO",
        "checks": {
            "frozen_input_hashes_match": True,
            "independent_preoutcome_audit_passed": True,
            "independent_salt_to_cycle_to_map_replay_passed": True,
            "formal_outputs_absent": True,
            "full_synthetic_and_repository_tests_passed": True,
            "round8_primitive_archive_opened_for_q0_bridge_only": True,
            "complete_round8_q0_bridge_passed": True,
            "new_map_q_greater_than_zero_source_rows_read": False,
            "new_map_q_greater_than_zero_metric_outcomes_computed": False,
        },
        "frozen_hashes": hashes,
        "implementation_hashes": implementation_hashes,
        "tests": tests,
        "q0_bridge": q0_bridge,
        "formal_implementation_commit": git_commit,
        "worktree_clean_before_preflight": True,
        "formal_run_permitted": False,
        "formal_implementation_commit": git_commit,
        "worktree_clean_before_preflight": True,
        "required_reviewer_decision": {
            "path": relative(REVIEWER_DECISION_PATH),
            "decision": "GO",
            "formal_run_authorized": True,
            "authorized_attempt": "attempt01",
            "new_map_q_greater_than_zero_outcomes_seen": False,
            "replicates": REPLICATES,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "map_count": len(MAP_IDS),
            "seed_count": len(SEEDS),
            "reviewed_hashes": (
                "must bind every path checked by the formal runner"
            ),
        },
    }
    write_json(PREFLIGHT_PATH, preflight)
    manifest = {
        "study": "Round 9 formal implementation/input manifest",
        "status": "FROZEN_AWAITING_INDEPENDENT_REVIEWER_GO",
        "formal_run_permitted": False,
        "input_hashes": hashes,
        "implementation_hashes": implementation_hashes,
        "preflight": {
            "path": relative(PREFLIGHT_PATH),
            "sha256": sha256_file(PREFLIGHT_PATH),
        },
        "formal_outputs_absent": {
            relative(path): not path.exists() for path in PRE_RUN_OUTPUTS
        },
        "frozen_design": {
            "maps": 20,
            "seeds": list(SEEDS),
            "q": list(Q_VALUES),
            "component_count_per_map": COMPONENT_COUNT,
            "replicates": REPLICATES,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "statistic_order": (
                "map occurrence and seed bottleneck first; mean selected "
                "seed positions within occurrence; mean 20 occurrences"
            ),
        },
        "formal_output_schema": {
            relative(RESULT_PATH): "completion-marker JSON; written last",
            relative(POINT_PATH): {
                "primary_curve_shapes": {
                    "A": [20, 5, 2, 5],
                    "R": [20, 5, 1, 5],
                    "S": [20, 5, 2, 5],
                    "C1": [20, 5, 3, 5],
                },
                "map_seed_axis_bottlenecks": [20, 5, 4],
                "map_mean_axis_bottlenecks": [20, 4],
                "required_full_diagnostics": True,
            },
            relative(DRAW_PATH): {
                "axis_draw_shapes": {
                    axis: [REPLICATES] for axis in AXES
                },
                "selected_map_positions": [REPLICATES, 20],
                "selected_seed_positions": [REPLICATES, 5],
                "expanded_image_counts": [REPLICATES, 20],
            },
            relative(POINT_CSV_PATH): {
                "columns": [
                    "map_id",
                    "seed",
                    "axis",
                    "model",
                    "q",
                    "metric",
                    "estimate",
                    "gate_component",
                    "expected_direction",
                ]
            },
            relative(BOOTSTRAP_CSV_PATH): {
                "rows": 4,
                "axis_order": list(AXES),
            },
            relative(FORMAL_LOG_PATH): "tmux one-shot log",
        },
    }
    write_json(IMPLEMENTATION_MANIFEST_PATH, manifest)
    return {
        "preflight": {
            "path": relative(PREFLIGHT_PATH),
            "sha256": sha256_file(PREFLIGHT_PATH),
        },
        "implementation_manifest": {
            "path": relative(IMPLEMENTATION_MANIFEST_PATH),
            "sha256": sha256_file(IMPLEMENTATION_MANIFEST_PATH),
        },
        "tests": tests,
    }


def reviewer_binding_paths() -> tuple[Path, ...]:
    return (
        PROTOCOL_PATH,
        MAP_PATH,
        MAP_MANIFEST_PATH,
        COMPONENT_PATH,
        COMPONENT_MANIFEST_PATH,
        PREOUTCOME_AUDIT_PATH,
        PREOUTCOME_MANIFEST_PATH,
        PREIMPLEMENTATION_MEMO_PATH,
        SALT_REPLAY_AUDIT_PATH,
        ROUND8_PRIMITIVES_PATH,
        ROUND8_RESULT_PATH,
        PREFLIGHT_PATH,
        IMPLEMENTATION_MANIFEST_PATH,
        Path(__file__).resolve(),
        PROJECT_ROOT / "src" / "arsc_eval" / "multimap_statistics.py",
        PROJECT_ROOT / "src" / "arsc_eval" / "multimap_response.py",
        PROJECT_ROOT / "tests" / "test_multimap_statistics.py",
        PROJECT_ROOT / "tests" / "test_multimap_response.py",
        PROJECT_ROOT / "scripts" / "verify_round9_salt_replay.py",
        PROJECT_ROOT / "scripts" / "verify_round9_preoutcome_artifacts.py",
        PROJECT_ROOT / "scripts" / "launch_round9_multimap_tmux.sh",
    )


def verify_reviewer_go() -> dict[str, Any]:
    require(REVIEWER_DECISION_PATH.exists(), "reviewer decision is missing")
    decision = read_json(REVIEWER_DECISION_PATH)
    exact = {
        "decision": "GO",
        "formal_run_authorized": True,
        "authorized_attempt": "attempt01",
        "new_map_q_greater_than_zero_outcomes_seen": False,
        "replicates": REPLICATES,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "map_count": len(MAP_IDS),
        "seed_count": len(SEEDS),
    }
    for key, expected in exact.items():
        require(
            decision.get(key) == expected,
            f"reviewer decision field differs: {key}",
        )
    reviewed = decision.get("reviewed_hashes", {})
    for path in reviewer_binding_paths():
        key = relative(path)
        require(
            reviewed.get(key) == sha256_file(path),
            f"reviewer did not bind current hash: {key}",
        )
    memo_path = PROJECT_ROOT / decision["memo_path"]
    require(
        memo_path.exists()
        and decision["memo_sha256"] == sha256_file(memo_path),
        "reviewer memo hash mismatch",
    )
    return decision


def load_round8_primitive_arrays() -> dict[str, np.ndarray]:
    with np.load(ROUND8_PRIMITIVES_PATH, allow_pickle=False) as archive:
        expected_keys = {
            "file_names",
            "action_targets",
            "rationale_targets",
            "source_maps",
            "component_image_offsets",
            "component_image_indices",
            "component_id_by_image",
        }
        for seed in SEEDS:
            for model in MODEL_KEYS:
                expected_keys.update(
                    {
                        f"seed_{seed}_{model}_action_predictions",
                        f"seed_{seed}_{model}_exact_set_errors",
                        f"seed_{seed}_{model}_confidence",
                    }
                )
                for perturbation in PERTURBATION_KEYS:
                    expected_keys.add(
                        f"seed_{seed}_{model}_{perturbation}"
                        "_action_predictions"
                    )
            expected_keys.add(
                f"seed_{seed}_joint_rationale_predictions"
            )
            for perturbation in PERTURBATION_KEYS:
                expected_keys.add(
                    f"seed_{seed}_joint_{perturbation}"
                    "_rationale_predictions"
                )
        require(
            set(archive.files) == expected_keys,
            "Round 8 primitive exact key allowlist differs",
        )
        primitive_arrays = {
            key: archive[key].copy() for key in archive.files
        }
    require(len(primitive_arrays) == 87, "Round 8 primitive schema differs")
    return primitive_arrays


def load_map_component_inputs(
    primitive_arrays: dict[str, np.ndarray],
) -> tuple[
    dict[str, np.ndarray],
    dict[str, dict[str, np.ndarray]],
]:
    with np.load(MAP_PATH, allow_pickle=False) as archive:
        map_arrays = {
            "file_names": archive["file_names"].copy(),
            **{
                map_id: archive[f"{map_id}_source_maps"].copy()
                for map_id in MAP_IDS
            },
        }
    require(
        np.array_equal(
            primitive_arrays["file_names"], map_arrays["file_names"]
        ),
        "primitive and map filename order differs",
    )
    with np.load(COMPONENT_PATH, allow_pickle=False) as archive:
        components = {
            map_id: {
                "offsets": archive[
                    f"{map_id}_component_image_offsets"
                ].copy(),
                "images": archive[
                    f"{map_id}_component_image_indices"
                ].copy(),
                "ids": archive[
                    f"{map_id}_component_id_by_image"
                ].copy(),
            }
            for map_id in MAP_IDS
        }
    return map_arrays, components


def primitive_for_seed(
    arrays: dict[str, np.ndarray], seed: int
) -> dict[str, Any]:
    return {
        "action_targets": arrays["action_targets"],
        "rationale_targets": arrays["rationale_targets"],
        "action_predictions": {
            model: arrays[f"seed_{seed}_{model}_action_predictions"]
            for model in MODEL_KEYS
        },
        "exact_set_errors": {
            model: arrays[f"seed_{seed}_{model}_exact_set_errors"]
            for model in MODEL_KEYS
        },
        "confidence": {
            model: arrays[f"seed_{seed}_{model}_confidence"]
            for model in MODEL_KEYS
        },
        "action_perturbed_predictions": {
            perturbation: {
                model: arrays[
                    f"seed_{seed}_{model}_{perturbation}"
                    "_action_predictions"
                ]
                for model in MODEL_KEYS
            }
            for perturbation in PERTURBATION_KEYS
        },
        "rationale_predictions": arrays[
            f"seed_{seed}_joint_rationale_predictions"
        ],
        "rationale_perturbed_predictions": {
            perturbation: arrays[
                f"seed_{seed}_joint_{perturbation}"
                "_rationale_predictions"
            ]
            for perturbation in PERTURBATION_KEYS
        },
    }


def verify_q0_bridge_before_new_outcomes(
    primitive_arrays: dict[str, np.ndarray],
    round8: dict[str, Any],
    map_manifest: dict[str, Any],
) -> dict[str, Any]:
    """Verify the complete Round 8 q0 bridge before any q>0 metric call."""

    identity = np.arange(SAMPLE_COUNT, dtype=np.int64)
    for map_id in MAP_IDS:
        q0 = map_manifest["maps"][map_id]["audit"]["by_severity"][
            "0.0"
        ]
        require(
            q0["active_images"] == 0
            and q0["fixed_points"] == SAMPLE_COUNT
            and q0["bijection"] is True,
            f"{map_id} manifest q0 is not identity",
        )
    identity_stack = np.tile(identity, (5, 1))
    maximum_difference = 0.0

    def compare(left: Any, right: Any) -> None:
        nonlocal maximum_difference
        if left is None or right is None:
            require(left is right, "q0 None-valued diagnostic mismatch")
            return
        maximum_difference = max(
            maximum_difference, abs(float(left) - float(right))
        )

    for seed in SEEDS:
        primitive = primitive_for_seed(primitive_arrays, seed)
        historical = round8["point_estimates_by_seed"][str(seed)]
        curves = graded_axis_curves(primitive, identity_stack)
        for axis in AXES:
            expected = np.asarray(
                historical["primary_curves"][axis], dtype=np.float64
            )[:, 0]
            maximum_difference = max(
                maximum_difference,
                float(np.max(np.abs(curves[axis][:, 0] - expected))),
            )
        for model in MODEL_KEYS:
            action = multilabel_f1(
                primitive["action_targets"],
                primitive["action_predictions"][model].astype(np.float64),
                list(ACTION_CLASS_NAMES),
                THRESHOLD,
            )
            expected_action = historical["A"][model][0]
            compare(action["macro_f1"], expected_action["macro_f1"])
            compare(action["micro_f1"], expected_action["micro_f1"])
            for name in ACTION_CLASS_NAMES:
                compare(
                    action["per_class_f1"][name],
                    expected_action["per_class_f1"][name],
                )
            safety = confidence_diagnostics(
                primitive["exact_set_errors"][model],
                primitive["confidence"][model],
            )
            expected_safety = historical["S"][model][0]
            for name in S_DIAGNOSTICS:
                compare(safety[name], expected_safety[name])
            expected_c1 = historical["C1"]["action"][model][0]
            c1_values = []
            for perturbation in PERTURBATION_KEYS:
                value = float(
                    action_flip_samples(
                        primitive["action_predictions"][model],
                        primitive["action_perturbed_predictions"][
                            perturbation
                        ][model],
                        THRESHOLD,
                    ).mean()
                )
                compare(value, expected_c1[perturbation])
                c1_values.append(value)
            compare(float(np.mean(c1_values)), expected_c1["mean_three"])

        rationale = multilabel_f1(
            primitive["rationale_targets"],
            primitive["rationale_predictions"].astype(np.float64),
            list(RATIONALE_CLASS_NAMES),
            THRESHOLD,
        )
        expected_rationale = historical["R"]["joint"][0]
        compare(rationale["macro_f1"], expected_rationale["macro_f1"])
        compare(rationale["micro_f1"], expected_rationale["micro_f1"])
        for name in RATIONALE_CLASS_NAMES:
            compare(
                rationale["per_class_f1"][name],
                expected_rationale["per_class_f1"][name],
            )
        expected_c1_r = historical["C1"]["rationale"]["joint"][0]
        rationale_values = []
        for perturbation in PERTURBATION_KEYS:
            value = float(
                rationale_jaccard_samples(
                    primitive["rationale_predictions"],
                    primitive["rationale_perturbed_predictions"][
                        perturbation
                    ],
                    THRESHOLD,
                ).mean()
            )
            compare(value, expected_c1_r[perturbation])
            rationale_values.append(value)
        compare(float(np.mean(rationale_values)), expected_c1_r["mean_three"])
    require(maximum_difference <= 1e-14, "complete q0 bridge mismatch")
    return {
        "all_20_q0_maps_identity": True,
        "all_20_full_sample_q0_rows_identical_by_construction": True,
        "Round8_primary_and_full_diagnostics_reproduced": True,
        "maximum_abs_difference": maximum_difference,
        "new_map_q_greater_than_zero_source_rows_read_before_bridge": False,
        "new_map_q_greater_than_zero_outcomes_computed_before_bridge": False,
    }


def append_row(
    rows: list[dict[str, Any]],
    map_id: str,
    seed: int,
    axis: str,
    model: str,
    q: float,
    metric: str,
    estimate: Any,
    gate_component: bool,
    direction: str,
) -> None:
    rows.append(
        {
            "map_id": map_id,
            "seed": seed,
            "axis": axis,
            "model": model,
            "q": q,
            "metric": metric,
            "estimate": estimate,
            "gate_component": gate_component,
            "expected_direction": direction,
        }
    )


def point_outcomes(
    primitive_arrays: dict[str, np.ndarray],
    map_arrays: dict[str, np.ndarray],
    components: dict[str, dict[str, np.ndarray]],
) -> tuple[dict[str, np.ndarray], list[Any], list[dict[str, Any]]]:
    shape_prefix = (len(MAP_IDS), len(SEEDS))
    primary = {
        "A": np.empty((*shape_prefix, 2, 5), dtype=np.float64),
        "R": np.empty((*shape_prefix, 1, 5), dtype=np.float64),
        "S": np.empty((*shape_prefix, 2, 5), dtype=np.float64),
        "C1": np.empty((*shape_prefix, 3, 5), dtype=np.float64),
    }
    arrays: dict[str, np.ndarray] = {
        "map_ids": np.asarray(MAP_IDS),
        "seeds": np.asarray(SEEDS, dtype=np.int64),
        "q_values": np.asarray(Q_VALUES, dtype=np.float64),
        "axis_names": np.asarray(AXES),
        "A_micro_f1": np.empty((*shape_prefix, 2, 5)),
        "A_per_class_f1": np.empty((*shape_prefix, 2, 5, 4)),
        "A_target_positive_count": np.empty(
            (*shape_prefix, 2, 5, 4), dtype=np.int64
        ),
        "A_predicted_positive_count": np.empty(
            (*shape_prefix, 2, 5, 4), dtype=np.int64
        ),
        "R_micro_f1": np.empty((*shape_prefix, 5)),
        "R_per_class_f1": np.empty((*shape_prefix, 5, 21)),
        "R_target_positive_count": np.empty(
            (*shape_prefix, 5, 21), dtype=np.int64
        ),
        "R_predicted_positive_count": np.empty(
            (*shape_prefix, 5, 21), dtype=np.int64
        ),
        "S_diagnostics": np.empty((*shape_prefix, 2, 5, 8)),
        "S_diagnostic_names": np.asarray(S_DIAGNOSTICS),
        "C1_action_per_perturbation": np.empty(
            (*shape_prefix, 2, 5, 3)
        ),
        "C1_rationale_per_perturbation": np.empty(
            (*shape_prefix, 5, 3)
        ),
        "perturbation_names": np.asarray(PERTURBATION_KEYS),
        "action_class_names": np.asarray(ACTION_CLASS_NAMES),
        "rationale_class_names": np.asarray(RATIONALE_CLASS_NAMES),
    }
    prepared_by_map: list[Any] = []
    rows: list[dict[str, Any]] = []
    for map_index, map_id in enumerate(MAP_IDS):
        source_maps = map_arrays[map_id]
        per_seed_prepared = []
        for seed_index, seed in enumerate(SEEDS):
            primitive = primitive_for_seed(primitive_arrays, seed)
            curves = graded_axis_curves(primitive, source_maps)
            for axis in AXES:
                primary[axis][map_index, seed_index] = curves[axis]
            per_seed_prepared.append(
                prepare_component_statistics(
                    primitive,
                    source_maps,
                    components[map_id]["offsets"],
                    components[map_id]["images"],
                    components[map_id]["ids"],
                )
            )
            for q_index, (q, source) in enumerate(
                zip(Q_VALUES, source_maps)
            ):
                for model_index, model in enumerate(MODEL_KEYS):
                    targets = primitive["action_targets"][source]
                    predictions = primitive["action_predictions"][model]
                    detail = multilabel_f1(
                        targets,
                        predictions.astype(np.float64),
                        list(ACTION_CLASS_NAMES),
                        THRESHOLD,
                    )
                    arrays["A_micro_f1"][
                        map_index, seed_index, model_index, q_index
                    ] = detail["micro_f1"]
                    for class_index, name in enumerate(ACTION_CLASS_NAMES):
                        arrays["A_per_class_f1"][
                            map_index,
                            seed_index,
                            model_index,
                            q_index,
                            class_index,
                        ] = detail["per_class_f1"][name]
                        arrays["A_target_positive_count"][
                            map_index,
                            seed_index,
                            model_index,
                            q_index,
                            class_index,
                        ] = int(targets[:, class_index].sum())
                        arrays["A_predicted_positive_count"][
                            map_index,
                            seed_index,
                            model_index,
                            q_index,
                            class_index,
                        ] = int(predictions[:, class_index].sum())
                    append_row(
                        rows, map_id, seed, "A", model, q,
                        "macro_f1", detail["macro_f1"], True, "decreasing"
                    )
                    append_row(
                        rows, map_id, seed, "A", model, q,
                        "micro_f1", detail["micro_f1"], False,
                        "diagnostic_only"
                    )
                    require(
                        abs(
                            detail["macro_f1"]
                            - curves["A"][model_index, q_index]
                        )
                        <= 1e-15,
                        "A point/curve mismatch",
                    )
                    for class_index, name in enumerate(ACTION_CLASS_NAMES):
                        append_row(
                            rows, map_id, seed, "A", model, q,
                            f"per_class_f1::{name}",
                            detail["per_class_f1"][name], False,
                            "diagnostic_only",
                        )
                        append_row(
                            rows, map_id, seed, "A", model, q,
                            f"target_positive_count::{name}",
                            arrays["A_target_positive_count"][
                                map_index,
                                seed_index,
                                model_index,
                                q_index,
                                class_index,
                            ],
                            False,
                            "diagnostic_only",
                        )
                        append_row(
                            rows, map_id, seed, "A", model, q,
                            f"predicted_positive_count::{name}",
                            arrays["A_predicted_positive_count"][
                                map_index,
                                seed_index,
                                model_index,
                                q_index,
                                class_index,
                            ],
                            False,
                            "diagnostic_only",
                        )
                    diagnostics = confidence_diagnostics(
                        primitive["exact_set_errors"][model],
                        primitive["confidence"][model][source],
                    )
                    for diagnostic_index, name in enumerate(S_DIAGNOSTICS):
                        value = diagnostics[name]
                        arrays["S_diagnostics"][
                            map_index,
                            seed_index,
                            model_index,
                            q_index,
                            diagnostic_index,
                        ] = np.nan if value is None else value
                        append_row(
                            rows, map_id, seed, "S", model, q, name,
                            value, name == "tie_averaged_aurc",
                            "increasing" if name == "tie_averaged_aurc"
                            else "diagnostic_only"
                        )
                    for perturbation_index, perturbation in enumerate(
                        PERTURBATION_KEYS
                    ):
                        flip = float(
                            action_flip_samples(
                                predictions,
                                primitive[
                                    "action_perturbed_predictions"
                                ][perturbation][model][source],
                                THRESHOLD,
                            ).mean()
                        )
                        arrays["C1_action_per_perturbation"][
                            map_index,
                            seed_index,
                            model_index,
                            q_index,
                            perturbation_index,
                        ] = flip
                        append_row(
                            rows, map_id, seed, "C1", model, q,
                            f"action_flip::{perturbation}", flip, False,
                            "diagnostic_only",
                        )
                    action_mean = float(
                        arrays["C1_action_per_perturbation"][
                            map_index,
                            seed_index,
                            model_index,
                            q_index,
                        ].mean()
                    )
                    require(
                        abs(
                            action_mean
                            - curves["C1"][model_index, q_index]
                        )
                        <= 1e-15,
                        "C1 action point/curve mismatch",
                    )
                    append_row(
                        rows, map_id, seed, "C1", model, q,
                        "action_flip::mean_three", action_mean, True,
                        "increasing",
                    )

                rationale_targets = primitive["rationale_targets"][source]
                rationale_predictions = primitive["rationale_predictions"]
                detail = multilabel_f1(
                    rationale_targets,
                    rationale_predictions.astype(np.float64),
                    list(RATIONALE_CLASS_NAMES),
                    THRESHOLD,
                )
                arrays["R_micro_f1"][
                    map_index, seed_index, q_index
                ] = detail["micro_f1"]
                for class_index, name in enumerate(RATIONALE_CLASS_NAMES):
                    arrays["R_per_class_f1"][
                        map_index, seed_index, q_index, class_index
                    ] = detail["per_class_f1"][name]
                    arrays["R_target_positive_count"][
                        map_index, seed_index, q_index, class_index
                    ] = int(rationale_targets[:, class_index].sum())
                    arrays["R_predicted_positive_count"][
                        map_index, seed_index, q_index, class_index
                    ] = int(rationale_predictions[:, class_index].sum())
                append_row(
                    rows, map_id, seed, "R", "joint", q, "macro_f1",
                    detail["macro_f1"], True, "decreasing"
                )
                append_row(
                    rows, map_id, seed, "R", "joint", q, "micro_f1",
                    detail["micro_f1"], False, "diagnostic_only"
                )
                require(
                    abs(detail["macro_f1"] - curves["R"][0, q_index])
                    <= 1e-15,
                    "R point/curve mismatch",
                )
                for class_index, name in enumerate(RATIONALE_CLASS_NAMES):
                    append_row(
                        rows, map_id, seed, "R", "joint", q,
                        f"per_class_f1::{name}",
                        detail["per_class_f1"][name], False,
                        "diagnostic_only",
                    )
                    append_row(
                        rows, map_id, seed, "R", "joint", q,
                        f"target_positive_count::{name}",
                        arrays["R_target_positive_count"][
                            map_index, seed_index, q_index, class_index
                        ],
                        False,
                        "diagnostic_only",
                    )
                    append_row(
                        rows, map_id, seed, "R", "joint", q,
                        f"predicted_positive_count::{name}",
                        arrays["R_predicted_positive_count"][
                            map_index, seed_index, q_index, class_index
                        ],
                        False,
                        "diagnostic_only",
                    )
                for perturbation_index, perturbation in enumerate(
                    PERTURBATION_KEYS
                ):
                    score = float(
                        rationale_jaccard_samples(
                            rationale_predictions,
                            primitive["rationale_perturbed_predictions"][
                                perturbation
                            ][source],
                            THRESHOLD,
                        ).mean()
                    )
                    arrays["C1_rationale_per_perturbation"][
                        map_index,
                        seed_index,
                        q_index,
                        perturbation_index,
                    ] = score
                    append_row(
                        rows, map_id, seed, "C1", "joint", q,
                        f"rationale_jaccard::{perturbation}", score,
                        False, "diagnostic_only",
                    )
                rationale_mean = float(
                    arrays["C1_rationale_per_perturbation"][
                        map_index, seed_index, q_index
                    ].mean()
                )
                require(
                    abs(rationale_mean - curves["C1"][2, q_index])
                    <= 1e-15,
                    "C1 rationale point/curve mismatch",
                )
                append_row(
                    rows, map_id, seed, "C1", "joint", q,
                    "rationale_jaccard::mean_three", rationale_mean,
                    True, "decreasing",
                )
        prepared_by_map.append(per_seed_prepared)
        print(
            json.dumps(
                {
                    "point_and_component_precompute_map_completed": map_id,
                    "maps_completed": map_index + 1,
                    "maps_total": len(MAP_IDS),
                }
            ),
            flush=True,
        )
    arrays.update(
        {f"{axis}_primary_curves": values for axis, values in primary.items()}
    )
    bottlenecks = np.empty((20, 5, 4), dtype=np.float64)
    for map_index in range(20):
        for seed_index in range(5):
            values = axis_bottlenecks(
                {
                    axis: primary[axis][map_index, seed_index]
                    for axis in AXES
                }
            )
            for axis in AXES:
                bottlenecks[
                    map_index, seed_index, AXIS_INDEX[axis]
                ] = values[axis]
    arrays["map_seed_axis_bottlenecks"] = bottlenecks
    arrays["map_mean_axis_bottlenecks"] = bottlenecks.mean(axis=1)
    return arrays, prepared_by_map, rows


def run_bootstrap(
    prepared_by_map: list[Any],
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    draws = {
        axis: np.empty(REPLICATES, dtype=np.float64) for axis in AXES
    }
    selected_maps_all = np.empty((REPLICATES, 20), dtype=np.int16)
    selected_seeds_all = np.empty((REPLICATES, 5), dtype=np.int8)
    image_counts = np.empty((REPLICATES, 20), dtype=np.int32)
    map_digest = hashlib.sha256()
    seed_digest = hashlib.sha256()
    component_digest = hashlib.sha256()
    component_counts_by_map = [
        len(prepared_by_map[map_index][0]["component_sizes"])
        for map_index in range(20)
    ]
    require(
        component_counts_by_map == [COMPONENT_COUNT] * 20,
        "frozen artifacts do not contain 1625 components per map",
    )
    maximum_bootstrap_images = max(
        component_counts_by_map[map_index]
        * int(prepared_by_map[map_index][0]["component_sizes"].max())
        for map_index in range(20)
    )
    harmonic = harmonic_numbers(maximum_bootstrap_images)
    first_draw = None
    last_draw = None
    for replicate in range(REPLICATES):
        selected_maps = rng.integers(0, 20, size=20)
        selected_seeds = rng.integers(0, 5, size=5)
        selected_maps_all[replicate] = selected_maps
        selected_seeds_all[replicate] = selected_seeds
        map_digest.update(selected_maps.astype("<i8").tobytes())
        seed_digest.update(selected_seeds.astype("<i8").tobytes())
        occurrence_values = []
        occurrence_component_hashes = []
        for occurrence, map_position in enumerate(selected_maps):
            component_count = component_counts_by_map[int(map_position)]
            selected_components = rng.integers(
                0, component_count, size=component_count
            )
            component_bytes = selected_components.astype("<i8").tobytes()
            component_digest.update(component_bytes)
            occurrence_component_hashes.append(
                hashlib.sha256(component_bytes).hexdigest().upper()
            )
            component_counts = np.bincount(
                selected_components, minlength=component_count
            ).astype(np.int64)
            prepared_seeds = prepared_by_map[int(map_position)]
            image_counts[replicate, occurrence] = int(
                component_counts @ prepared_seeds[0]["component_sizes"]
            )
            per_seed = {}
            for seed_position in np.unique(selected_seeds):
                curves = curves_from_component_counts(
                    prepared_seeds[int(seed_position)],
                    component_counts,
                    harmonic,
                )
                per_seed[int(seed_position)] = axis_bottlenecks(curves)
            occurrence_values.append(
                {
                    axis: float(
                        np.mean(
                            [
                                per_seed[int(position)][axis]
                                for position in selected_seeds
                            ]
                        )
                    )
                    for axis in AXES
                }
            )
        for axis in AXES:
            draws[axis][replicate] = float(
                np.mean([value[axis] for value in occurrence_values])
            )
        detail = {
            "replicate": replicate,
            "selected_map_positions": selected_maps.tolist(),
            "selected_seed_positions": selected_seeds.tolist(),
            "component_draw_sha256_by_occurrence": (
                occurrence_component_hashes
            ),
            "expanded_image_count_by_occurrence": (
                image_counts[replicate].tolist()
            ),
        }
        if replicate == 0:
            first_draw = detail
        if replicate == REPLICATES - 1:
            last_draw = detail
        if (replicate + 1) % 25 == 0:
            print(
                json.dumps(
                    {
                        "hierarchical_bootstrap_completed": replicate + 1,
                        "bootstrap_total": REPLICATES,
                    }
                ),
                flush=True,
            )
    draw_arrays = {
        **draws,
        "selected_map_positions": selected_maps_all,
        "selected_seed_positions": selected_seeds_all,
        "expanded_image_counts": image_counts,
    }
    diagnostics = {
        "replicates": REPLICATES,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "map_draw_stream_sha256": map_digest.hexdigest().upper(),
        "seed_draw_stream_sha256": seed_digest.hexdigest().upper(),
        "component_draw_stream_sha256": (
            component_digest.hexdigest().upper()
        ),
        "first_draw": first_draw,
        "last_draw": last_draw,
        "expanded_image_count": {
            "minimum": int(image_counts.min()),
            "maximum": int(image_counts.max()),
            "mean": float(image_counts.mean()),
        },
        "hierarchy": {
            "one_shared_seed_vector_per_replicate": True,
            "one_independent_component_draw_per_map_occurrence": True,
            "component_draw_shared_across_selected_seeds_axes_q_models": True,
            "bottleneck_before_seed_and_map_averaging": True,
            "component_count_derived_from_each_selected_map": True,
            "component_counts_by_map": component_counts_by_map,
        },
    }
    return draw_arrays, diagnostics


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_npz(path: Path, arrays: dict[str, np.ndarray]) -> None:
    with path.open("wb") as stream:
        np.savez_compressed(stream, **arrays)


def main() -> int:
    args = parse_args()
    if args.preflight_only:
        result = run_preflight()
        print(json.dumps(result, indent=2))
        return 0

    require(PREFLIGHT_PATH.exists(), "formal preflight is missing")
    require(
        IMPLEMENTATION_MANIFEST_PATH.exists(),
        "formal implementation manifest is missing",
    )
    require(
        not any(path.exists() for path in FORMAL_ARTIFACT_OUTPUTS),
        "formal output already exists; refusing to overwrite",
    )
    verify_frozen_hashes()
    reviewer_decision = verify_reviewer_go()
    primitive_arrays = load_round8_primitive_arrays()
    round8 = read_json(ROUND8_RESULT_PATH)
    q0_bridge = verify_q0_bridge_before_new_outcomes(
        primitive_arrays, round8, read_json(MAP_MANIFEST_PATH)
    )
    map_arrays, components = load_map_component_inputs(primitive_arrays)
    point_arrays, prepared_by_map, rows = point_outcomes(
        primitive_arrays, map_arrays, components
    )

    bridge_difference = q0_bridge["maximum_abs_difference"]

    draw_arrays, bootstrap_diagnostics = run_bootstrap(prepared_by_map)
    map_mean = point_arrays["map_mean_axis_bottlenecks"]
    axis_summaries = {}
    axis_gates = {}
    for axis in AXES:
        axis_index = AXIS_INDEX[axis]
        curves = point_arrays[f"{axis}_primary_curves"]
        no_reversal = grand_mean_curve_has_no_reversal(
            curves, AXIS_DIRECTIONS[axis]
        )
        interval = np.quantile(
            draw_arrays[axis], [0.025, 0.975], method="linear"
        ).tolist()
        gate = round9_axis_gate(
            map_mean[:, axis_index], interval, no_reversal
        )
        axis_gates[axis] = gate["passed"]
        axis_summaries[axis] = {
            **gate,
            "map_specific_means": {
                map_id: float(map_mean[index, axis_index])
                for index, map_id in enumerate(MAP_IDS)
            },
            "bootstrap_draw_sha256": array_sha256(draw_arrays[axis]),
            "grand_mean_component_curves": curves.mean(
                axis=(0, 1)
            ).tolist(),
            "grand_sd_component_curves": curves.reshape(
                -1, curves.shape[2], curves.shape[3]
            )
            .std(axis=0, ddof=1)
            .tolist(),
        }
    full_pass = bool(all(axis_gates.values()))

    point_arrays["input_round8_primitives_sha256"] = np.asarray(
        [sha256_file(ROUND8_PRIMITIVES_PATH)]
    )
    for name, values in point_arrays.items():
        array = np.asarray(values)
        if np.issubdtype(array.dtype, np.number):
            require(np.all(np.isfinite(array)), f"nonfinite point array: {name}")
    for name, values in draw_arrays.items():
        require(
            np.all(np.isfinite(values)), f"nonfinite bootstrap array: {name}"
        )
    require(
        point_arrays["map_seed_axis_bottlenecks"].shape == (20, 5, 4)
        and point_arrays["map_mean_axis_bottlenecks"].shape == (20, 4),
        "bottleneck output shapes differ",
    )
    require(
        all(draw_arrays[axis].shape == (REPLICATES,) for axis in AXES),
        "axis bootstrap draw shape differs",
    )

    point_staging = staging_path(POINT_PATH)
    draw_staging = staging_path(DRAW_PATH)
    point_csv_staging = staging_path(POINT_CSV_PATH)
    bootstrap_csv_staging = staging_path(BOOTSTRAP_CSV_PATH)
    result_staging = staging_path(RESULT_PATH)
    write_npz(point_staging, point_arrays)
    write_npz(draw_staging, draw_arrays)
    write_csv(point_csv_staging, rows)
    bootstrap_rows = [
        {
            "axis": axis,
            "positive_map_count": axis_summaries[axis][
                "positive_map_count"
            ],
            "grand_mean": axis_summaries[axis]["grand_mean"],
            "ci_lower": axis_summaries[axis]["bootstrap_interval"][0],
            "ci_upper": axis_summaries[axis]["bootstrap_interval"][1],
            "grand_mean_no_reversal": axis_summaries[axis]["subgates"][
                "grand_mean_component_curves_no_reversal"
            ],
            "passed": axis_summaries[axis]["passed"],
        }
        for axis in AXES
    ]
    write_csv(bootstrap_csv_staging, bootstrap_rows)
    all_zero_rationale = [
        name
        for index, name in enumerate(RATIONALE_CLASS_NAMES)
        if int(primitive_arrays["rationale_targets"][:, index].sum()) == 0
    ]
    result = {
        "study": "BDD-OIA Round 9 20-map graded-response robustness",
        "status": (
            "ROUND9_FULL_PASS"
            if full_pass
            else "ROUND9_FAIL_OR_INCONCLUSIVE"
        ),
        "completed_formal_attempt": "attempt01",
        "scope": {
            "dataset": "BDD-OIA frozen test population",
            "maps_are_external_datasets": False,
            "training": False,
            "inference": False,
            "new_data": False,
        },
        "provenance": {
            "protocol": {
                "path": relative(PROTOCOL_PATH),
                "sha256": sha256_file(PROTOCOL_PATH),
            },
            "formal_preflight": {
                "path": relative(PREFLIGHT_PATH),
                "sha256": sha256_file(PREFLIGHT_PATH),
            },
            "implementation_manifest": {
                "path": relative(IMPLEMENTATION_MANIFEST_PATH),
                "sha256": sha256_file(IMPLEMENTATION_MANIFEST_PATH),
            },
            "independent_reviewer_decision": {
                "path": relative(REVIEWER_DECISION_PATH),
                "sha256": sha256_file(REVIEWER_DECISION_PATH),
                "memo_path": reviewer_decision["memo_path"],
                "memo_sha256": reviewer_decision["memo_sha256"],
            },
            "round8_primitives": {
                "path": relative(ROUND8_PRIMITIVES_PATH),
                "sha256": sha256_file(ROUND8_PRIMITIVES_PATH),
            },
        },
        "frozen_design": {
            "maps": list(MAP_IDS),
            "seeds": list(SEEDS),
            "q": list(Q_VALUES),
            "replicates": REPLICATES,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "component_count_per_map": COMPONENT_COUNT,
            "round8_map_excluded_from_primary": True,
        },
        "point_results": {
            "map_seed_axis_bottlenecks": {
                map_id: {
                    str(seed): {
                        axis: float(
                            point_arrays["map_seed_axis_bottlenecks"][
                                map_index,
                                seed_index,
                                AXIS_INDEX[axis],
                            ]
                        )
                        for axis in AXES
                    }
                    for seed_index, seed in enumerate(SEEDS)
                }
                for map_index, map_id in enumerate(MAP_IDS)
            },
            "round8_q0_bridge_max_abs_difference": bridge_difference,
            "round8_q0_bridge": q0_bridge,
            "all_zero_rationale_classes": all_zero_rationale,
            "diagnostics_csv_rows": len(rows),
        },
        "hierarchical_bootstrap": bootstrap_diagnostics,
        "axis_summaries": axis_summaries,
        "decisions": {
            "axis_gates": axis_gates,
            "full_Round9_measurement_pass": full_pass,
            "all_20_maps_reported": True,
        },
        "artifacts": {
            relative(path): {
                "sha256": sha256_file(staging_path(path)),
                "bytes": staging_path(path).stat().st_size,
            }
            for path in (
                POINT_PATH,
                DRAW_PATH,
                POINT_CSV_PATH,
                BOOTSTRAP_CSV_PATH,
            )
        },
        "claim_boundary": {
            "if_passed_supports": (
                "The four Round 8 BDD-OIA graded response gates are "
                "robust across 20 prefixed outcome-blind legal map "
                "realizations under the frozen map-by-seed-by-association-"
                "component conditional inference."
            ),
            "does_not_support": read_json(PROTOCOL_PATH)[
                "claim_boundaries"
            ]["PASS_does_not_support"],
        },
        "failure_policy": (
            "Preserve every result. Round 9 terminates the BDD-OIA "
            "map-realization line regardless of PASS or FAIL."
        ),
    }
    write_json(result_staging, result)
    for staged, final in (
        (point_staging, POINT_PATH),
        (draw_staging, DRAW_PATH),
        (point_csv_staging, POINT_CSV_PATH),
        (bootstrap_csv_staging, BOOTSTRAP_CSV_PATH),
        (result_staging, RESULT_PATH),
    ):
        os.replace(staged, final)
    print(
        json.dumps(
            {
                "status": result["status"],
                "axis_gates": axis_gates,
                "axis_grand_means": {
                    axis: axis_summaries[axis]["grand_mean"]
                    for axis in AXES
                },
                "axis_intervals": {
                    axis: axis_summaries[axis]["bootstrap_interval"]
                    for axis in AXES
                },
                "result": relative(RESULT_PATH),
                "result_sha256": sha256_file(RESULT_PATH),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
