"""Independently audit every Round 9 preoutcome artifact.

This verifier deliberately does not import the map/component construction
modules.  It reconstructs graded maps from the stored cycle partitions and
recomputes connected components with a separate union/find implementation.
It reads filenames, clip IDs, source indices, and component indices only.
No targets, predictions, confidences, errors, or metric outcomes are opened.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALIDITY_ROOT = PROJECT_ROOT / "outputs" / "validity"
PROTOCOL_PATH = VALIDITY_ROOT / "round9_multimap_protocol.json"
MAP_PATH = VALIDITY_ROOT / "round9_multimap_maps.npz"
MAP_MANIFEST_PATH = VALIDITY_ROOT / "round9_multimap_map_manifest.json"
COMPONENT_PATH = VALIDITY_ROOT / "round9_multimap_components.npz"
COMPONENT_MANIFEST_PATH = (
    VALIDITY_ROOT / "round9_multimap_component_manifest.json"
)
AUDIT_OUTPUT = (
    VALIDITY_ROOT / "round9_multimap_preoutcome_independent_audit.json"
)
TEST_LOG_OUTPUT = (
    VALIDITY_ROOT / "round9_multimap_preoutcome_tests.log"
)
MANIFEST_OUTPUT = (
    VALIDITY_ROOT / "round9_multimap_preoutcome_run_manifest.json"
)

MAP_IDS = tuple(f"map{index:02d}" for index in range(20))
SALTS = tuple(f"arsc-round9-map{index:02d}" for index in range(20))
Q_VALUES = (0.0, 0.25, 0.5, 0.75, 1.0)
ACTIVE_IMAGES = (0, 1140, 2278, 3418, 4557)
SAMPLE_COUNT = 4557
CLIP_COUNT = 3904
COMPONENT_COUNT = 1625
PREREGISTRATION_COMMIT = "2dda1524d77974f12092979293ebd4b9ddc98f7b"
FORMAL_OUTPUTS = (
    VALIDITY_ROOT / "round9_multimap_results.json",
    VALIDITY_ROOT / "round9_multimap_primitives.npz",
    VALIDITY_ROOT / "round9_multimap_bootstrap_draws.npz",
    VALIDITY_ROOT / "round9_multimap_formal.log",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def relative(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def array_sha256(values: np.ndarray) -> str:
    return hashlib.sha256(
        np.ascontiguousarray(values).tobytes()
    ).hexdigest().upper()


def clip_group_independent(file_name: str) -> str:
    return re.sub(r"_(?:1|3)$", "", Path(file_name).stem)


def independent_component_labels(
    clip_group_ids: np.ndarray,
    q1_source: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Recompute q1 graph components without importing formal code."""

    clip_ids = np.asarray(clip_group_ids, dtype=np.int64)
    source = np.asarray(q1_source, dtype=np.int64)
    parent = list(range(CLIP_COUNT))

    def root(node: int) -> int:
        while parent[node] != node:
            node = parent[node]
        return node

    def union(left: int, right: int) -> None:
        left_root = root(left)
        right_root = root(right)
        if left_root == right_root:
            return
        if left_root < right_root:
            parent[right_root] = left_root
        else:
            parent[left_root] = right_root

    for destination, source_index in enumerate(source.tolist()):
        union(
            int(clip_ids[destination]),
            int(clip_ids[source_index]),
        )
    roots = np.asarray(
        [root(clip_id) for clip_id in range(CLIP_COUNT)],
        dtype=np.int64,
    )
    ordered_roots = sorted(set(roots.tolist()))
    root_to_component = {
        component_root: index
        for index, component_root in enumerate(ordered_roots)
    }
    component_by_clip = np.asarray(
        [root_to_component[int(value)] for value in roots],
        dtype=np.int64,
    )
    return component_by_clip, component_by_clip[clip_ids]


def pack_independent(labels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    values = np.asarray(labels, dtype=np.int64)
    members = [
        np.flatnonzero(values == component).astype(np.int64)
        for component in range(int(values.max()) + 1)
    ]
    offsets = np.zeros(len(members) + 1, dtype=np.int64)
    offsets[1:] = np.cumsum(
        np.asarray([len(indices) for indices in members], dtype=np.int64)
    )
    return offsets, np.concatenate(members)


def reconstruct_source_maps(
    pair_cycles: np.ndarray,
    final_triplet: np.ndarray,
) -> np.ndarray:
    identity = np.arange(SAMPLE_COUNT, dtype=np.int64)
    cycles = [
        tuple(int(value) for value in pair)
        for pair in np.asarray(pair_cycles).tolist()
    ]
    cycles.append(tuple(int(value) for value in final_triplet.tolist()))
    rebuilt = []
    for q in Q_VALUES:
        source = identity.copy()
        if q == 1.0:
            active_cycles = cycles
        else:
            pair_count = int(np.floor(q * SAMPLE_COUNT / 2.0 + 0.5))
            active_cycles = cycles[:pair_count]
        for cycle in active_cycles:
            for destination, source_index in zip(
                cycle, (*cycle[1:], cycle[0])
            ):
                source[destination] = source_index
        rebuilt.append(source)
    return np.stack(rebuilt)


def run_full_tests() -> dict[str, Any]:
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
    TEST_LOG_OUTPUT.write_text(combined, encoding="utf-8")
    require(completed.returncode == 0, "full unit-test suite failed")
    require("Ran 61 tests" in combined, "expected 61-test count not found")
    require(re.search(r"\nOK\s*$", combined) is not None, "test log lacks OK")
    return {
        "command": command,
        "return_code": completed.returncode,
        "expected_test_count": 61,
        "all_passed": True,
        "log": {
            "path": relative(TEST_LOG_OUTPUT),
            "sha256": sha256_file(TEST_LOG_OUTPUT),
            "bytes": TEST_LOG_OUTPUT.stat().st_size,
        },
    }


def main() -> int:
    for output in (AUDIT_OUTPUT, TEST_LOG_OUTPUT, MANIFEST_OUTPUT):
        require(not output.exists(), f"refusing to overwrite {relative(output)}")
    require(
        not any(path.exists() for path in FORMAL_OUTPUTS),
        "a formal Round 9 output exists before reviewer GO",
    )

    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    map_manifest = json.loads(
        MAP_MANIFEST_PATH.read_text(encoding="utf-8")
    )
    component_manifest = json.loads(
        COMPONENT_MANIFEST_PATH.read_text(encoding="utf-8")
    )
    require(
        protocol["status"]
        == "FROZEN_BEFORE_NEW_MAP_Q_GREATER_THAN_ZERO_OUTCOMES",
        "protocol status is not preoutcome-frozen",
    )
    require(
        tuple(protocol["map_realizations"]["map_ids"]) == MAP_IDS,
        "protocol map IDs differ",
    )
    require(
        tuple(protocol["map_realizations"]["salts"]) == SALTS,
        "protocol salts differ",
    )
    require(
        tuple(protocol["frozen_inputs"]["q_values"]) == Q_VALUES,
        "protocol q grid differs",
    )
    require(
        tuple(protocol["frozen_inputs"]["active_images"]) == ACTIVE_IMAGES,
        "protocol active-image grid differs",
    )
    require(
        protocol["hierarchical_bootstrap"]["replicates"] == 2000
        and protocol["hierarchical_bootstrap"]["seed"] == 20260809,
        "bootstrap settings differ",
    )
    require(
        map_manifest["protocol"]["sha256"] == sha256_file(PROTOCOL_PATH),
        "map manifest protocol hash mismatch",
    )
    require(
        map_manifest["artifact"]["sha256"] == sha256_file(MAP_PATH),
        "map artifact hash mismatch",
    )
    require(
        component_manifest["frozen_inputs"]["protocol"]["sha256"]
        == sha256_file(PROTOCOL_PATH),
        "component manifest protocol hash mismatch",
    )
    require(
        component_manifest["frozen_inputs"]["map_artifact"]["sha256"]
        == sha256_file(MAP_PATH),
        "component manifest map hash mismatch",
    )
    require(
        component_manifest["artifact"]["sha256"]
        == sha256_file(COMPONENT_PATH),
        "component artifact hash mismatch",
    )

    expected_map_keys = {
        "file_names",
        "clip_group_names",
        "clip_group_ids",
        "q_values",
        "active_images",
    } | {
        f"{map_id}_{suffix}"
        for map_id in MAP_IDS
        for suffix in ("pair_cycles", "final_triplet", "source_maps")
    }
    with np.load(MAP_PATH, allow_pickle=False) as archive:
        require(
            set(archive.files) == expected_map_keys,
            "map archive contains missing or unexpected keys",
        )
        file_names = archive["file_names"].copy()
        stored_clip_names = archive["clip_group_names"].copy()
        stored_clip_ids = archive["clip_group_ids"].copy()
        require(
            np.array_equal(
                archive["q_values"], np.asarray(Q_VALUES, dtype=np.float64)
            ),
            "stored q grid differs",
        )
        require(
            np.array_equal(
                archive["active_images"],
                np.asarray(ACTIVE_IMAGES, dtype=np.int64),
            ),
            "stored active-image grid differs",
        )
        map_arrays = {
            map_id: {
                suffix: archive[f"{map_id}_{suffix}"].copy()
                for suffix in (
                    "pair_cycles",
                    "final_triplet",
                    "source_maps",
                )
            }
            for map_id in MAP_IDS
        }

    require(file_names.shape == (SAMPLE_COUNT,), "filename shape differs")
    names = [str(value) for value in file_names.tolist()]
    require(len(set(names)) == SAMPLE_COUNT, "filenames are not unique")
    require(
        array_sha256(file_names)
        == protocol["frozen_inputs"]["filename_order_sha256"],
        "filename-order hash mismatch",
    )
    derived_clip_names = sorted(
        {clip_group_independent(name) for name in names}
    )
    require(len(derived_clip_names) == CLIP_COUNT, "clip count differs")
    require(
        np.array_equal(stored_clip_names, np.asarray(derived_clip_names)),
        "stored clip names differ from independent derivation",
    )
    clip_to_id = {
        clip_name: index
        for index, clip_name in enumerate(derived_clip_names)
    }
    derived_clip_ids = np.asarray(
        [clip_to_id[clip_group_independent(name)] for name in names],
        dtype=np.int64,
    )
    require(
        np.array_equal(stored_clip_ids, derived_clip_ids),
        "stored clip IDs differ from independent derivation",
    )

    expected_component_keys = {
        f"{map_id}_{suffix}"
        for map_id in MAP_IDS
        for suffix in (
            "component_id_by_clip",
            "component_id_by_image",
            "component_clip_offsets",
            "component_clip_ids",
            "component_image_offsets",
            "component_image_indices",
        )
    }
    with np.load(COMPONENT_PATH, allow_pickle=False) as archive:
        require(
            set(archive.files) == expected_component_keys,
            "component archive contains missing or unexpected keys",
        )
        stored_components = {
            map_id: {
                suffix: archive[f"{map_id}_{suffix}"].copy()
                for suffix in (
                    "component_id_by_clip",
                    "component_id_by_image",
                    "component_clip_offsets",
                    "component_clip_ids",
                    "component_image_offsets",
                    "component_image_indices",
                )
            }
            for map_id in MAP_IDS
        }

    identity = np.arange(SAMPLE_COUNT, dtype=np.int64)
    q1_hashes: list[str] = []
    partition_hashes: list[str] = []
    maps_report: dict[str, Any] = {}
    for map_id in MAP_IDS:
        pair_cycles = map_arrays[map_id]["pair_cycles"]
        final_triplet = map_arrays[map_id]["final_triplet"]
        source_maps = map_arrays[map_id]["source_maps"]
        require(
            pair_cycles.shape == (2277, 2),
            f"{map_id} pair-cycle shape differs",
        )
        require(
            final_triplet.shape == (3,),
            f"{map_id} final-triplet shape differs",
        )
        all_cycle_members = np.concatenate(
            [pair_cycles.reshape(-1), final_triplet]
        )
        require(
            np.array_equal(np.sort(all_cycle_members), identity),
            f"{map_id} cycles do not partition all images",
        )
        rebuilt = reconstruct_source_maps(pair_cycles, final_triplet)
        require(
            np.array_equal(rebuilt, source_maps),
            f"{map_id} source maps differ from independent reconstruction",
        )

        active_sets = []
        per_q = []
        for q_index, source in enumerate(source_maps):
            active = set(np.flatnonzero(source != identity).tolist())
            active_sets.append(active)
            bijection = np.array_equal(np.sort(source), identity)
            same_clip = int(
                np.sum(
                    derived_clip_ids[list(active)]
                    == derived_clip_ids[source[list(active)]]
                )
            )
            per_q.append(
                {
                    "q": Q_VALUES[q_index],
                    "bijection": bool(bijection),
                    "active_images": len(active),
                    "same_clip_active_pairs": same_clip,
                    "fixed_points": int(np.sum(source == identity)),
                }
            )
            require(bijection, f"{map_id} q{q_index} is not a bijection")
            require(
                len(active) == ACTIVE_IMAGES[q_index],
                f"{map_id} q{q_index} active count differs",
            )
            require(
                same_clip == 0,
                f"{map_id} q{q_index} contains a same-clip active pair",
            )
        require(
            all(
                active_sets[index] < active_sets[index + 1]
                for index in range(len(active_sets) - 1)
            ),
            f"{map_id} active sets are not strictly nested",
        )
        require(
            np.array_equal(source_maps[0], identity),
            f"{map_id} q0 is not identity",
        )
        require(
            int(np.sum(source_maps[-1] == identity)) == 0,
            f"{map_id} q1 has a fixed point",
        )
        q1_hashes.append(array_sha256(source_maps[-1]))

        expected_by_clip, expected_by_image = independent_component_labels(
            derived_clip_ids, source_maps[-1]
        )
        require(
            len(np.unique(expected_by_clip)) == COMPONENT_COUNT,
            f"{map_id} component count differs",
        )
        expected_clip_offsets, expected_clip_members = pack_independent(
            expected_by_clip
        )
        expected_image_offsets, expected_image_members = pack_independent(
            expected_by_image
        )
        independently_derived = {
            "component_id_by_clip": expected_by_clip,
            "component_id_by_image": expected_by_image,
            "component_clip_offsets": expected_clip_offsets,
            "component_clip_ids": expected_clip_members,
            "component_image_offsets": expected_image_offsets,
            "component_image_indices": expected_image_members,
        }
        for suffix, expected in independently_derived.items():
            require(
                np.array_equal(stored_components[map_id][suffix], expected),
                f"{map_id} stored {suffix} differs independently",
            )
        closure_by_q = []
        restricted_bijection_by_q = []
        for source in source_maps:
            closure = np.array_equal(
                expected_by_image[source], expected_by_image
            )
            restricted = bool(closure)
            if restricted:
                for component in range(COMPONENT_COUNT):
                    destinations = np.flatnonzero(
                        expected_by_image == component
                    )
                    if not np.array_equal(
                        np.sort(source[destinations]), destinations
                    ):
                        restricted = False
                        break
            closure_by_q.append(bool(closure))
            restricted_bijection_by_q.append(bool(restricted))
        require(
            all(closure_by_q) and all(restricted_bijection_by_q),
            f"{map_id} component closure/restricted bijection failed",
        )
        clip_sizes = np.bincount(
            expected_by_clip, minlength=COMPONENT_COUNT
        )
        image_sizes = np.bincount(
            expected_by_image, minlength=COMPONENT_COUNT
        )
        require(
            int(clip_sizes.min()) >= 2 and int(image_sizes.min()) >= 2,
            f"{map_id} has a singleton component",
        )
        partition_hash = array_sha256(expected_by_image)
        partition_hashes.append(partition_hash)
        require(
            map_manifest["maps"][map_id]["source_array_sha256"]
            == array_sha256(source_maps),
            f"{map_id} map-manifest array hash mismatch",
        )
        require(
            component_manifest["maps"][map_id]["partition_sha256"]
            == partition_hash,
            f"{map_id} component-manifest partition hash mismatch",
        )
        maps_report[map_id] = {
            "source_maps_sha256": array_sha256(source_maps),
            "q1_sha256": q1_hashes[-1],
            "partition_sha256": partition_hash,
            "per_q": per_q,
            "cycles_partition_all_images": True,
            "source_maps_match_independent_reconstruction": True,
            "component_count": COMPONENT_COUNT,
            "components_match_independent_reconstruction": True,
            "source_closure_all_q": all(closure_by_q),
            "restricted_bijection_all_q": all(
                restricted_bijection_by_q
            ),
            "minimum_clips_per_component": int(clip_sizes.min()),
            "minimum_images_per_component": int(image_sizes.min()),
        }

    require(len(set(q1_hashes)) == 20, "q1 maps are not all unique")
    require(
        len(set(partition_hashes)) == 20,
        "component partitions are not all unique",
    )
    require(
        map_manifest["construction_inputs"]["targets_read"] is False
        and map_manifest["construction_inputs"]["predictions_read"] is False
        and map_manifest["construction_inputs"][
            "logits_or_probabilities_read"
        ]
        is False
        and map_manifest["construction_inputs"][
            "confidence_or_errors_read"
        ]
        is False
        and map_manifest["construction_inputs"][
            "new_map_q_greater_than_zero_metric_outcomes_read"
        ]
        is False,
        "map manifest does not assert outcome blindness",
    )
    require(
        component_manifest["derivation"][
            "targets_predictions_logits_probabilities_confidences_errors_or_metric_outcomes_read"
        ]
        is False
        and component_manifest["derivation"][
            "new_map_q_greater_than_zero_metric_outcomes_read"
        ]
        is False,
        "component manifest does not assert outcome blindness",
    )

    test_report = run_full_tests()
    formal_absence = {
        relative(path): not path.exists() for path in FORMAL_OUTPUTS
    }
    require(all(formal_absence.values()), "formal outputs appeared in preflight")
    audit = {
        "study": "Round 9 independent preoutcome artifact audit",
        "status": "PASS_AWAITING_INDEPENDENT_REVIEWER_GO",
        "independence": {
            "imports_formal_map_or_component_code": False,
            "reconstructs_maps_from_stored_cycles": True,
            "recomputes_q1_connected_components": True,
            "reads_only": [
                "protocol and outcome-blind manifests",
                "filename and clip arrays",
                "cycle and source-index arrays",
                "component-index arrays",
            ],
            "does_not_read": [
                "targets",
                "predictions",
                "logits or probabilities",
                "confidence",
                "errors",
                "metric outcomes",
            ],
        },
        "artifact_hashes": {
            relative(path): sha256_file(path)
            for path in (
                PROTOCOL_PATH,
                MAP_PATH,
                MAP_MANIFEST_PATH,
                COMPONENT_PATH,
                COMPONENT_MANIFEST_PATH,
            )
        },
        "exact_gates": {
            "protocol_status_and_constants_match": True,
            "map_archive_exact_key_allowlist": True,
            "component_archive_exact_key_allowlist": True,
            "filename_and_clip_derivation_match": True,
            "all_20_cycles_partition_all_images": True,
            "all_20_map_stacks_match_independent_reconstruction": True,
            "all_q_bijections_nested_and_cross_clip": True,
            "all_20_q1_maps_unique": True,
            "all_20_component_partitions_unique": True,
            "all_components_match_independent_reconstruction": True,
            "all_q_source_closed_and_restricted_bijections": True,
            "all_formal_outcomes_absent": all(formal_absence.values()),
            "full_unit_tests_pass": test_report["all_passed"],
        },
        "maps": maps_report,
        "formal_output_absence": formal_absence,
        "test_report": test_report,
        "outcome_governance_evidence": {
            "new_map_q_greater_than_zero_metric_outcomes_in_artifacts": False,
            "formal_result_files_present": False,
            "builder_archive_key_access_is_allowlisted_in_manifests": True,
            "scope": (
                "Exact for committed code paths, archive contents, and "
                "filesystem artifacts; does not claim to prove the absence "
                "of an unrecorded external computation."
            ),
        },
        "all_passed": True,
    }
    AUDIT_OUTPUT.write_text(
        json.dumps(audit, indent=2) + "\n", encoding="utf-8"
    )

    implementation_paths = (
        PROTOCOL_PATH,
        MAP_PATH,
        MAP_MANIFEST_PATH,
        COMPONENT_PATH,
        COMPONENT_MANIFEST_PATH,
        PROJECT_ROOT / "scripts" / "build_round9_multimap_maps.py",
        PROJECT_ROOT / "scripts" / "build_round9_multimap_components.py",
        PROJECT_ROOT / "scripts" / "verify_round9_preoutcome_artifacts.py",
        PROJECT_ROOT / "src" / "arsc_eval" / "graded_association.py",
        PROJECT_ROOT / "src" / "arsc_eval" / "association_components.py",
        PROJECT_ROOT / "src" / "arsc_eval" / "multimap_response.py",
        PROJECT_ROOT / "tests" / "test_graded_association.py",
        PROJECT_ROOT / "tests" / "test_association_components.py",
        PROJECT_ROOT / "tests" / "test_multimap_response.py",
        AUDIT_OUTPUT,
        TEST_LOG_OUTPUT,
    )
    run_manifest = {
        "study": "Round 9 immutable preoutcome implementation/input manifest",
        "status": "AWAITING_INDEPENDENT_REVIEWER_GO",
        "preregistration_commit": PREREGISTRATION_COMMIT,
        "formal_run_permitted": False,
        "formal_run_blocker": (
            "An independent reviewer must inspect this manifest, protocol, "
            "artifacts, audit, and formal implementation before issuing GO."
        ),
        "files": {
            relative(path): {
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for path in implementation_paths
        },
        "formal_output_absence": formal_absence,
        "test_report": test_report,
        "audit": {
            "path": relative(AUDIT_OUTPUT),
            "sha256": sha256_file(AUDIT_OUTPUT),
            "all_passed": True,
        },
        "outcome_blind_preflight": True,
    }
    MANIFEST_OUTPUT.write_text(
        json.dumps(run_manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": audit["status"],
                "exact_gate_count": len(audit["exact_gates"]),
                "all_passed": audit["all_passed"],
                "q1_map_count": len(set(q1_hashes)),
                "component_partition_count": len(set(partition_hashes)),
                "formal_outputs_absent": all(formal_absence.values()),
                "audit": {
                    "path": relative(AUDIT_OUTPUT),
                    "sha256": sha256_file(AUDIT_OUTPUT),
                },
                "run_manifest": {
                    "path": relative(MANIFEST_OUTPUT),
                    "sha256": sha256_file(MANIFEST_OUTPUT),
                },
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
