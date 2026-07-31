"""One-shot formal analyzer for the preregistered Round 10 study.

The ``--preflight-only`` path is outcome blind: it hashes inputs, runs the
test suite, and creates the implementation manifest without importing model
or inference modules.  The default path requires a separately committed,
independent preformal GO decision before it can load a checkpoint.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.corruption_dose_response_v2 import (
    FAMILIES,
    LEVELS,
    NOISE_SEED,
    PARAMETERS,
    PixelCorruptionV2,
    validate_grid,
)
from arsc_eval.corruption_statistics import (
    AXES,
    AXIS_COMPONENTS,
    AXIS_DIRECTIONS,
    ENDPOINT_COMPONENTS,
    MODELS,
    PRACTICAL_THRESHOLDS,
    SAFETY_DIAGNOSTICS,
    all_family_curves_from_clip_counts,
    confidence_diagnostics,
    endpoint_effects,
    family_axis_bottlenecks,
    f1_from_counts,
    harmonic_numbers,
    mean_curve_no_reversal,
    practical_endpoint_pass,
    prepare_seed_clip_statistics,
    quantile_diagnostic,
    run_shared_bootstrap,
    source_clip_membership,
)
from arsc_eval.round10_formal_contract import (
    require_paths_absent,
    unexpected_round10_output_paths,
    validate_atomic_output_layout,
    validate_preformal_go,
)


SEEDS = (43, 44, 45, 46, 47)
SAMPLE_COUNT = 4557
CLIP_COUNT = 3904
BOOTSTRAP_REPLICATES = 5000
BOOTSTRAP_SEED = 20260810
BONFERRONI_PROBABILITY = 0.05 / 12.0
EXPECTED_TEST_COUNT = 94
EXPECTED_TEST_MANIFEST_SHA256 = (
    "89364A265FE4C2EDCA5125D34C4C25D47C96AFB46A5C4A8FE86B649785539004"
)
EXPECTED_IMAGE_INVENTORY_SHA256 = (
    "8034D044D55973917D0719A1CC829EEA002582420D6F7E05BB18F9AFF8894901"
)
IMPLEMENTATION_AUTHORIZATION_SHA256 = (
    "C20541D8E241961944EBD1AC1BB160C7C7FD050895E500A48612F3907E0C9865"
)

AUTHORIZATION_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round10_preregister_reviewer_decision_amendment01.json"
)
REPAIR_AUTHORIZATION_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round10_preformal_reviewer_decision.json"
)
REPAIR_AUTHORIZATION_SHA256 = (
    "A109F38F4EB347B855090D17AE76417B2BD7753DE0968D6FAF65BEC669B260B9"
)
REPAIR_MEMO_PATH = (
    PROJECT_ROOT / "outputs" / "research_review_memo_round10_preformal.md"
)
REPAIR_MEMO_SHA256 = (
    "B6CBADA1B97C041599D89D15E95B8452E93D3BE2D0C2EFD92EC06F6D38836DF6"
)
INCIDENT_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round10_formal_attempt01_incident.json"
)
INCIDENT_SHA256 = (
    "1DA010284B0E6F8311E3A76DDF0E2C0C1015891EE244D92B115C550273C5D712"
)
ATTEMPT01_LOG_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round10_corruption_formal_attempt01.log"
)
ATTEMPT01_LOG_SHA256 = (
    "BB6CCB81A6AF980C5BE35EED3D36DDE9D5E1DABADD2EDAF187011B1A8C22A3CC"
)
INCIDENT_REVIEW_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round10_attempt01_incident_reviewer_decision.json"
)
INCIDENT_REVIEW_SHA256 = (
    "93BAD702B0C6AB33187B05BCECCAF65946CAF6B3EAA542292187A81C2B4A93A0"
)
INCIDENT_REVIEW_MEMO_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "research_review_memo_round10_attempt01_incident.md"
)
INCIDENT_REVIEW_MEMO_SHA256 = (
    "62CC1B1DF19FF68563E6152BA34080FB83925E34082E11C890F30D550C0063DC"
)
PREFLIGHT_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round10_corruption_formal_preflight_amendment02.json"
)
MANIFEST_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round10_corruption_formal_implementation_manifest_amendment02.json"
)
GO_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round10_preformal_reviewer_decision_amendment02.json"
)
STAGING_DIR = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round10_corruption_formal_attempt02.staging"
)
FINAL_DIR = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round10_corruption_formal_attempt02"
)
LOG_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round10_corruption_formal_attempt02.log"
)
ARTIFACT_INDEX_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round10_corruption_artifact_index_attempt02.json"
)

IMPLEMENTATION_ROOT_FILES = (
    "scripts/analyze_round10_corruption.py",
    "scripts/finalize_round10_corruption.py",
    "scripts/launch_round10_corruption_tmux.sh",
    "tests/test_corruption_statistics.py",
    "tests/test_round10_formal_contract.py",
    "tests/test_round10_protocol_validation.py",
    "requirements.txt",
    "requirements-dev.txt",
)
BASE_ALLOWED_ROUND10_OUTPUTS = (
    "outputs/research_review_memo_round10_preregister.md",
    "outputs/research_review_memo_round10_preregister_amendment01.md",
    "outputs/research_review_memo_round10_preformal.md",
    "outputs/research_review_memo_round10_preformal_amendment01.md",
    "outputs/research_review_memo_round10_attempt01_incident.md",
    "outputs/research_review_memo_round10_preformal_amendment02.md",
    "outputs/validity/round10_corruption_dose_response_protocol.json",
    "outputs/validity/round10_corruption_dose_response_protocol_amendment01.json",
    "outputs/validity/round10_corruption_preflight.json",
    "outputs/validity/round10_corruption_preflight_tests.log",
    "outputs/validity/round10_corruption_preflight_attempt02.json",
    "outputs/validity/round10_corruption_preflight_attempt02_tests.log",
    "outputs/validity/round10_preregister_reviewer_decision.json",
    "outputs/validity/round10_preregister_reviewer_decision_amendment01.json",
    "outputs/validity/round10_corruption_formal_implementation_manifest.json",
    "outputs/validity/round10_corruption_formal_preflight.json",
    (
        "outputs/validity/"
        "round10_corruption_formal_implementation_manifest_amendment01.json"
    ),
    "outputs/validity/round10_corruption_formal_preflight_amendment01.json",
    "outputs/validity/round10_preformal_reviewer_decision.json",
    "outputs/validity/round10_preformal_reviewer_decision_amendment01.json",
    "outputs/validity/round10_corruption_formal_attempt01.log",
    "outputs/validity/round10_formal_attempt01_incident.json",
    "outputs/validity/round10_attempt01_incident_reviewer_decision.json",
    (
        "outputs/validity/"
        "round10_corruption_formal_implementation_manifest_amendment02.json"
    ),
    "outputs/validity/round10_corruption_formal_preflight_amendment02.json",
    "outputs/validity/round10_preformal_reviewer_decision_amendment02.json",
)
BASE_ALLOWED_ROUND10_PREFIXES = (
    "outputs/validity/round10_corruption_semantic_audit",
    "outputs/validity/round10_corruption_semantic_audit_amendment01",
)
AXIS_ENDPOINT_INDICES = {
    "A": (0, 1),
    "R": (2,),
    "S": (3, 4),
    "C1": (5, 6, 7),
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def relative(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def sha256_file(path: Path) -> str:
    require(path.is_file(), f"required file missing: {relative(path)}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
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
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    require(isinstance(value, dict), f"expected JSON object: {relative(path)}")
    return value


def json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def write_json_atomic(path: Path, value: Any) -> None:
    temporary = path.with_name(path.name + ".tmp")
    require(not temporary.exists(), f"temporary output already exists: {relative(temporary)}")
    temporary.write_bytes(json_bytes(value))
    os.replace(temporary, path)


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    require(len(rows) > 0, f"cannot write empty CSV: {relative(path)}")
    fieldnames: list[str] = []
    for row in rows:
        for field in row:
            if field not in fieldnames:
                fieldnames.append(field)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def git_output(*arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def require_clean_worktree(
    allowed_untracked: Sequence[str] = (),
) -> str:
    status = git_output(
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    permitted = {f"?? {path}" for path in allowed_untracked}
    unexpected = [
        line for line in status.splitlines() if line and line not in permitted
    ]
    require(
        not unexpected,
        f"formal operation requires a clean worktree: {unexpected}",
    )
    return git_output("rev-parse", "HEAD")


def verify_hash_map(bindings: Mapping[str, str]) -> dict[str, str]:
    observed: dict[str, str] = {}
    for path_text, expected in sorted(bindings.items()):
        path = PROJECT_ROOT / path_text
        digest = sha256_file(path)
        require(
            digest == str(expected).upper(),
            f"SHA256 differs for {path_text}: {digest}",
        )
        observed[path_text] = digest
    return observed


def merge_hash_maps(*maps: Mapping[str, str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for bindings in maps:
        for path, digest in bindings.items():
            normalized = str(digest).upper()
            if path in result:
                require(
                    result[path] == normalized,
                    f"conflicting hash binding for {path}",
                )
            result[path] = normalized
    return dict(sorted(result.items()))


def local_arsc_imports(path: Path) -> set[str]:
    """Return local package files imported by one Python source file."""

    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=relative(path))
    dependencies: set[str] = set()
    uses_package = False
    for node in ast.walk(tree):
        module_names: list[str] = []
        if isinstance(node, ast.ImportFrom) and node.module:
            module_names.append(node.module)
        elif isinstance(node, ast.Import):
            module_names.extend(alias.name for alias in node.names)
        for module_name in module_names:
            if module_name == "arsc_eval":
                uses_package = True
            elif module_name.startswith("arsc_eval."):
                uses_package = True
                first = module_name.split(".")[1]
                candidate = PROJECT_ROOT / "src" / "arsc_eval" / f"{first}.py"
                require(
                    candidate.is_file(),
                    f"unresolved local import {module_name} in {relative(path)}",
                )
                dependencies.add(relative(candidate))
    if uses_package:
        dependencies.add("src/arsc_eval/__init__.py")
    return dependencies


def implementation_dependency_closure() -> tuple[tuple[str, ...], dict[str, list[str]]]:
    """Recursively close every local import reachable from Python roots."""

    pending = list(IMPLEMENTATION_ROOT_FILES)
    closure = set(IMPLEMENTATION_ROOT_FILES)
    imports: dict[str, list[str]] = {}
    while pending:
        path_text = pending.pop()
        path = PROJECT_ROOT / path_text
        require(path.is_file(), f"implementation file missing: {path_text}")
        if path.suffix != ".py":
            continue
        dependencies = local_arsc_imports(path)
        imports[path_text] = sorted(dependencies)
        for dependency in dependencies:
            if dependency not in closure:
                closure.add(dependency)
                pending.append(dependency)
    return tuple(sorted(closure)), dict(sorted(imports.items()))


def all_output_paths() -> list[str]:
    output_root = PROJECT_ROOT / "outputs"
    return [
        relative(path)
        for path in output_root.rglob("*")
        if path.is_file() or path.is_dir()
    ]


def require_no_unexpected_round10_artifacts(
    allow_formal_log: bool = False,
) -> None:
    allowed = list(BASE_ALLOWED_ROUND10_OUTPUTS)
    if allow_formal_log:
        allowed.append(relative(LOG_PATH))
    forbidden = unexpected_round10_output_paths(
        all_output_paths(),
        allowed_exact=allowed,
        allowed_prefixes=BASE_ALLOWED_ROUND10_PREFIXES,
    )
    require(
        not forbidden,
        f"unexpected Round 10 output artifacts exist: {forbidden}",
    )
    if allow_formal_log:
        require(LOG_PATH.is_file(), "tmux formal log sentinel is absent")
    else:
        require(not LOG_PATH.exists(), "formal log already exists")


def validate_authorization() -> dict[str, Any]:
    require(
        sha256_file(AUTHORIZATION_PATH) == IMPLEMENTATION_AUTHORIZATION_SHA256,
        "implementation-only authorization hash differs",
    )
    decision = read_json(AUTHORIZATION_PATH)
    require(
        decision["verdict"]["decision"]
        == "AUTHORIZE_OUTCOME_BLIND_FORMAL_IMPLEMENTATION_ONLY",
        "wrong implementation authorization",
    )
    require(
        decision["verdict"]["formal_implementation_authorized"] is True
        and decision["verdict"]["formal_run_authorized"] is False
        and decision["verdict"]["model_loading_authorized"] is False
        and decision["verdict"]["real_inference_authorized"] is False,
        "implementation authorization scope differs",
    )
    verify_hash_map(decision["reviewed_files_sha256"])
    verify_hash_map(decision["frozen_config_sha256"])
    verify_hash_map(decision["frozen_checkpoint_sha256"])
    verify_hash_map(decision["frozen_calibration_sha256"])
    require(
        sha256_file(REPAIR_AUTHORIZATION_PATH) == REPAIR_AUTHORIZATION_SHA256,
        "preformal STOP repair authorization hash differs",
    )
    require(
        sha256_file(REPAIR_MEMO_PATH) == REPAIR_MEMO_SHA256,
        "preformal STOP memo hash differs",
    )
    repair = read_json(REPAIR_AUTHORIZATION_PATH)
    require(
        repair["verdict"]["decision"]
        == "STOP_REPAIR_ROUND10_FORMAL_IMPLEMENTATION"
        and repair["verdict"]["formal_run_authorized"] is False
        and repair["verdict"]["requires_new_implementation_commit"] is True,
        "preformal STOP repair scope differs",
    )
    require(
        sha256_file(ATTEMPT01_LOG_PATH) == ATTEMPT01_LOG_SHA256,
        "preserved attempt01 failure log hash differs",
    )
    require(
        sha256_file(INCIDENT_PATH) == INCIDENT_SHA256,
        "attempt01 incident record hash differs",
    )
    require(
        sha256_file(INCIDENT_REVIEW_PATH) == INCIDENT_REVIEW_SHA256,
        "attempt01 incident review hash differs",
    )
    require(
        sha256_file(INCIDENT_REVIEW_MEMO_PATH)
        == INCIDENT_REVIEW_MEMO_SHA256,
        "attempt01 incident review memo hash differs",
    )
    incident_review = read_json(INCIDENT_REVIEW_PATH)
    require(
        incident_review["verdict"]["decision"]
        == "AUTHORIZE_OUTCOME_BLIND_ATTEMPT02_INFRASTRUCTURE_REPAIR_ONLY"
        and incident_review["verdict"]["formal_run_authorized"] is False
        and incident_review["verdict"][
            "attempt02_formal_run_authorized"
        ]
        is False,
        "attempt02 infrastructure-only repair scope differs",
    )
    return decision


def read_manifest_records() -> tuple[list[dict[str, Any]], list[str]]:
    manifest = PROJECT_ROOT / "data" / "processed" / "test.jsonl"
    require(
        sha256_file(manifest) == EXPECTED_TEST_MANIFEST_SHA256,
        "test manifest hash differs",
    )
    records: list[dict[str, Any]] = []
    with manifest.open("r", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                value = json.loads(line)
                require(isinstance(value, dict), "manifest row must be an object")
                records.append(value)
    names = [str(record["file_name"]) for record in records]
    require(len(records) == SAMPLE_COUNT, "test row count differs")
    require(len(set(names)) == SAMPLE_COUNT, "test filenames are not unique")
    clip_ids, _, _ = source_clip_membership(names)
    require(int(clip_ids.max()) + 1 == CLIP_COUNT, "source clip count differs")
    return records, names


def verify_image_inventory(names: Sequence[str]) -> dict[str, Any]:
    image_root = PROJECT_ROOT / "data" / "raw" / "lastframe" / "data"
    aggregate = hashlib.sha256()
    total_bytes = 0
    for name in names:
        require(Path(name).name == name, f"noncanonical filename: {name}")
        path = image_root / name
        require(path.is_file(), f"source image missing: {name}")
        size = path.stat().st_size
        total_bytes += size
        aggregate.update(name.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(str(size).encode("ascii"))
        aggregate.update(b"\0")
        aggregate.update(sha256_file(path).encode("ascii"))
        aggregate.update(b"\n")
    digest = aggregate.hexdigest().upper()
    require(digest == EXPECTED_IMAGE_INVENTORY_SHA256, "source image inventory differs")
    return {
        "rows": len(names),
        "source_clip_count": CLIP_COUNT,
        "source_image_total_bytes": total_bytes,
        "ordered_source_image_inventory_sha256": digest,
    }


def validate_frozen_configs(decision: Mapping[str, Any]) -> dict[str, Any]:
    details: dict[str, Any] = {}
    for seed in SEEDS:
        path = PROJECT_ROOT / "configs" / f"rq1_seed{seed}.yaml"
        with path.open("r", encoding="utf-8") as stream:
            config = yaml.safe_load(stream)
        require(config["seed"] == seed, f"config seed differs: {seed}")
        require(config["image_size"] == 224, f"image size differs: {seed}")
        require(config["model"]["backbone"] == "resnet50", "backbone differs")
        require(config["training"]["threshold"] == 0.5, "threshold differs")
        require(config["training"]["batch_size"] == 128, "batch size differs")
        require(config["training"]["num_workers"] == 8, "worker count differs")
        require(config["training"]["amp"] is True, "AMP setting differs")
        require(
            config["paths"]["dataset_root"] == "data/raw/lastframe"
            and config["paths"]["processed_root"] == "data/processed",
            f"data paths differ: {seed}",
        )
        details[str(seed)] = {
            "path": relative(path),
            "sha256": sha256_file(path),
            "image_size": 224,
            "batch_size": 128,
            "num_workers": 8,
            "amp": True,
            "threshold": 0.5,
        }
    verify_hash_map(decision["frozen_config_sha256"])
    return details


def run_tests() -> dict[str, Any]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = "src"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )
    output = (completed.stdout + completed.stderr).strip()
    require(completed.returncode == 0, f"test suite failed:\n{output}")
    match = re.search(r"(\d+) passed", output)
    require(match is not None, f"could not parse test count:\n{output}")
    count = int(match.group(1))
    require(count == EXPECTED_TEST_COUNT, f"expected {EXPECTED_TEST_COUNT} tests, got {count}")
    return {
        "command": f"{sys.executable} -B -m pytest -q -p no:cacheprovider",
        "passed": count,
        "output": output,
    }


def preflight_only() -> int:
    validate_grid()
    validate_atomic_output_layout(STAGING_DIR, FINAL_DIR, LOG_PATH, ARTIFACT_INDEX_PATH)
    require_no_unexpected_round10_artifacts(allow_formal_log=False)
    require_paths_absent(
        (
            PREFLIGHT_PATH,
            MANIFEST_PATH,
            GO_PATH,
            STAGING_DIR,
            FINAL_DIR,
            LOG_PATH,
            ARTIFACT_INDEX_PATH,
            PREFLIGHT_PATH.with_name(PREFLIGHT_PATH.name + ".tmp"),
            MANIFEST_PATH.with_name(MANIFEST_PATH.name + ".tmp"),
        )
    )
    implementation_commit = require_clean_worktree()
    authorization = validate_authorization()
    configs = validate_frozen_configs(authorization)
    records, names = read_manifest_records()
    dataset = verify_image_inventory(names)
    tests = run_tests()
    require_clean_worktree()

    implementation_files, dependency_graph = implementation_dependency_closure()
    implementation_hashes = {
        path: sha256_file(PROJECT_ROOT / path) for path in implementation_files
    }
    repair_authorization = read_json(REPAIR_AUTHORIZATION_PATH)
    preserved_repair_bindings = {
        path: digest
        for path, digest in repair_authorization[
            "reviewed_files_sha256"
        ].items()
        if path not in implementation_hashes
    }
    incident_review = read_json(INCIDENT_REVIEW_PATH)
    preserved_incident_bindings = {
        path: digest
        for path, digest in incident_review[
            "reviewed_files_sha256"
        ].items()
        if path not in implementation_hashes
    }
    review_targets = merge_hash_maps(
        authorization["reviewed_files_sha256"],
        authorization["frozen_config_sha256"],
        authorization["frozen_checkpoint_sha256"],
        authorization["frozen_calibration_sha256"],
        preserved_repair_bindings,
        preserved_incident_bindings,
        implementation_hashes,
        {
            relative(AUTHORIZATION_PATH): IMPLEMENTATION_AUTHORIZATION_SHA256,
            relative(REPAIR_AUTHORIZATION_PATH): REPAIR_AUTHORIZATION_SHA256,
            relative(REPAIR_MEMO_PATH): REPAIR_MEMO_SHA256,
            relative(ATTEMPT01_LOG_PATH): ATTEMPT01_LOG_SHA256,
            relative(INCIDENT_PATH): INCIDENT_SHA256,
            relative(INCIDENT_REVIEW_PATH): INCIDENT_REVIEW_SHA256,
            relative(INCIDENT_REVIEW_MEMO_PATH): (
                INCIDENT_REVIEW_MEMO_SHA256
            ),
            "data/processed/test.jsonl": EXPECTED_TEST_MANIFEST_SHA256,
        },
    )
    manifest = {
        "schema_version": (
            "ARSC_ROUND10_FORMAL_IMPLEMENTATION_MANIFEST_AMENDMENT02_V1"
        ),
        "generated_at_utc": utc_now(),
        "outcome_blind": True,
        "formal_run": False,
        "checkpoint_tensors_loaded": False,
        "model_inference_run": False,
        "round10_nonzero_severity_predictions_read_or_computed": False,
        "round10_nonzero_severity_metric_outcomes_read_or_computed": False,
        "implementation_commit": implementation_commit,
        "authorization": {
            "implementation_only": {
                "path": relative(AUTHORIZATION_PATH),
                "sha256": IMPLEMENTATION_AUTHORIZATION_SHA256,
                "scope": "OUTCOME_BLIND_FORMAL_IMPLEMENTATION_ONLY",
            },
            "repair_stop": {
                "path": relative(REPAIR_AUTHORIZATION_PATH),
                "sha256": REPAIR_AUTHORIZATION_SHA256,
                "decision": "STOP_REPAIR_ROUND10_FORMAL_IMPLEMENTATION",
            },
            "attempt02_infrastructure_repair": {
                "path": relative(INCIDENT_REVIEW_PATH),
                "sha256": INCIDENT_REVIEW_SHA256,
                "decision": (
                    "AUTHORIZE_OUTCOME_BLIND_"
                    "ATTEMPT02_INFRASTRUCTURE_REPAIR_ONLY"
                ),
                "formal_run_authorized": False,
            },
        },
        "frozen_design": {
            "seeds": list(SEEDS),
            "families": list(FAMILIES),
            "levels": list(LEVELS),
            "parameters": {
                family: [float(value) for value in PARAMETERS[family]]
                for family in FAMILIES
            },
            "noise_seed": NOISE_SEED,
            "sample_count": SAMPLE_COUNT,
            "source_clip_count": CLIP_COUNT,
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "bonferroni_one_sided_probability": BONFERRONI_PROBABILITY,
            "numpy_quantile_method": "linear",
        },
        "implementation_files_sha256": dict(sorted(implementation_hashes.items())),
        "local_dependency_closure": {
            "root_files": list(IMPLEMENTATION_ROOT_FILES),
            "closed_file_count": len(implementation_files),
            "dependency_graph": dependency_graph,
            "package_init_bound": "src/arsc_eval/__init__.py"
            in implementation_hashes,
            "graded_response_oracle_bound": (
                "src/arsc_eval/graded_response.py" in implementation_hashes
            ),
        },
        "preformal_review_targets_sha256": review_targets,
        "required_preformal_go": {
            "path": relative(GO_PATH),
            "schema_version": "ARSC_ROUND10_PREFORMAL_REVIEWER_DECISION_V1",
            "decision": "GO_ROUND10_FORMAL_RUN_ATTEMPT02",
            "must_bind_implementation_commit": implementation_commit,
            "must_bind_exact_reviewed_file_set": True,
            "formal_run_remains_unauthorized_until_go": True,
        },
        "one_shot_outputs": {
            "staging_directory": relative(STAGING_DIR),
            "final_directory": relative(FINAL_DIR),
            "log": relative(LOG_PATH),
            "artifact_index": relative(ARTIFACT_INDEX_PATH),
            "restart_or_cache_reuse_allowed": False,
            "interrupted_staging_is_inconclusive_and_blocks_rerun": True,
            "result_json_written_last_before_atomic_directory_rename": True,
            "unknown_round10_output_allowlist_guard": True,
            "direct_analyzer_requires_existing_tmux_log_sentinel": True,
            "attempt01_log_and_incident_preserved": True,
            "attempt02_paths_are_disjoint_from_attempt01": True,
        },
        "formal_artifact_schemas": {
            "seed_logits": "ARSC_ROUND10_SEED_LOGITS_V1",
            "primitives": "ARSC_ROUND10_PRIMITIVES_V1",
            "bootstrap_draws": "ARSC_ROUND10_BOOTSTRAP_DRAWS_V1",
            "results": "ARSC_ROUND10_CORRUPTION_RESULTS_V1",
            "artifact_index": "ARSC_ROUND10_ARTIFACT_INDEX_V1",
        },
    }
    manifest_payload = json_bytes(manifest)
    manifest_sha256 = hashlib.sha256(manifest_payload).hexdigest().upper()
    preflight = {
        "schema_version": "ARSC_ROUND10_FORMAL_PREFLIGHT_AMENDMENT02_V1",
        "generated_at_utc": utc_now(),
        "status": "PASS_OUTCOME_BLIND_IMPLEMENTATION_PREFLIGHT_AMENDMENT02",
        "outcome_blind": True,
        "formal_run": False,
        "checkpoint_tensors_loaded": False,
        "model_inference_run": False,
        "round10_nonzero_severity_predictions_read_or_computed": False,
        "round10_nonzero_severity_metric_outcomes_read_or_computed": False,
        "implementation_commit": implementation_commit,
        "implementation_manifest": {
            "path": relative(MANIFEST_PATH),
            "sha256": manifest_sha256,
        },
        "authorization_sha256": IMPLEMENTATION_AUTHORIZATION_SHA256,
        "repair_authorization_sha256": REPAIR_AUTHORIZATION_SHA256,
        "attempt02_infrastructure_repair_authorization_sha256": (
            INCIDENT_REVIEW_SHA256
        ),
        "dataset": dataset,
        "configs": configs,
        "tests": tests,
        "review_target_count_before_manifest_and_preflight": len(review_targets),
        "formal_artifacts_absent": True,
        "preformal_go_absent": True,
        "closed_stop_defects": [
            "R10_PREFORMAL_B1",
            "R10_PREFORMAL_B2",
            "R10_PREFORMAL_B3",
            "R10_PREFORMAL_B4",
        ],
        "attempt01_incident": {
            "classification": "PREFORMAL_INFRASTRUCTURE_FAILURE_ZERO_OUTCOME",
            "log_sha256": ATTEMPT01_LOG_SHA256,
            "incident_sha256": INCIDENT_SHA256,
            "preserved": True,
        },
        "next_gate": (
            "INDEPENDENT_OUTCOME_BLIND_ATTEMPT02_PREFORMAL_IMPLEMENTATION_REVIEW"
        ),
    }
    manifest_tmp = MANIFEST_PATH.with_name(MANIFEST_PATH.name + ".tmp")
    preflight_tmp = PREFLIGHT_PATH.with_name(PREFLIGHT_PATH.name + ".tmp")
    manifest_tmp.write_bytes(manifest_payload)
    preflight_tmp.write_bytes(json_bytes(preflight))
    os.replace(manifest_tmp, MANIFEST_PATH)
    os.replace(preflight_tmp, PREFLIGHT_PATH)
    print(
        json.dumps(
            {
                "status": preflight["status"],
                "implementation_commit": implementation_commit,
                "tests_passed": tests["passed"],
                "manifest_sha256": manifest_sha256,
                "formal_run": False,
            },
            indent=2,
        ),
        flush=True,
    )
    return 0


def validate_formal_authorization(
    *,
    allow_formal_log: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    require_clean_worktree(
        (relative(LOG_PATH),) if allow_formal_log else (),
    )
    validate_atomic_output_layout(STAGING_DIR, FINAL_DIR, LOG_PATH, ARTIFACT_INDEX_PATH)
    require_no_unexpected_round10_artifacts(
        allow_formal_log=allow_formal_log,
    )
    require_paths_absent((STAGING_DIR, FINAL_DIR, ARTIFACT_INDEX_PATH))
    authorization = validate_authorization()
    manifest = read_json(MANIFEST_PATH)
    preflight = read_json(PREFLIGHT_PATH)
    require(
        manifest["schema_version"]
        == "ARSC_ROUND10_FORMAL_IMPLEMENTATION_MANIFEST_AMENDMENT02_V1"
        and manifest["outcome_blind"] is True
        and manifest["formal_run"] is False,
        "implementation manifest differs",
    )
    require(
        preflight["status"]
        == "PASS_OUTCOME_BLIND_IMPLEMENTATION_PREFLIGHT_AMENDMENT02"
        and preflight["outcome_blind"] is True
        and preflight["formal_run"] is False,
        "formal preflight differs",
    )
    require(
        preflight["implementation_manifest"]["sha256"] == sha256_file(MANIFEST_PATH),
        "preflight-to-manifest hash binding differs",
    )
    require(
        preflight["implementation_commit"] == manifest["implementation_commit"],
        "implementation commit binding differs",
    )
    verify_hash_map(manifest["implementation_files_sha256"])
    verify_hash_map(manifest["preformal_review_targets_sha256"])
    expected_reviewed = merge_hash_maps(
        manifest["preformal_review_targets_sha256"],
        {
            relative(MANIFEST_PATH): sha256_file(MANIFEST_PATH),
            relative(PREFLIGHT_PATH): sha256_file(PREFLIGHT_PATH),
        },
    )
    go = read_json(GO_PATH)
    validate_preformal_go(go, manifest["implementation_commit"], expected_reviewed)
    validate_frozen_configs(authorization)
    records, names = read_manifest_records()
    verify_image_inventory(names)
    return manifest, {"records": records, "names": names, "go": go}


def seed_paths(seed: int) -> dict[str, Path]:
    return {
        "config": PROJECT_ROOT / "configs" / f"rq1_seed{seed}.yaml",
        "action_checkpoint": (
            PROJECT_ROOT
            / "checkpoints"
            / "validity"
            / f"rq1_seed_{seed}"
            / "action_only_best_action.pt"
        ),
        "joint_checkpoint": (
            PROJECT_ROOT
            / "checkpoints"
            / "validity"
            / f"rq1_seed_{seed}"
            / "joint_best_action.pt"
        ),
        "action_calibration": (
            PROJECT_ROOT
            / "outputs"
            / "validity"
            / f"rq1_seed_{seed}"
            / "calibration_action_only.json"
        ),
        "joint_calibration": (
            PROJECT_ROOT
            / "outputs"
            / "validity"
            / f"rq1_seed_{seed}"
            / "calibration_joint.json"
        ),
    }


def load_temperature(path: Path, model_type: str) -> float:
    value = read_json(path)
    require(value["model_type"] == model_type, f"calibration model differs: {relative(path)}")
    temperature = float(value["temperature"])
    require(np.isfinite(temperature) and temperature > 0.0, "invalid temperature")
    return temperature


def run_seed_inference(seed: int, device_arg: str) -> dict[str, np.ndarray]:
    # These imports are deliberately delayed until after the independent GO.
    import torch

    from arsc_eval.engine import make_loader, predict
    from arsc_eval.models import load_checkpoint_model
    from arsc_eval.utils import device_from_arg, load_config, resolve_paths, set_seed

    paths = seed_paths(seed)
    config = load_config(paths["config"])
    resolved = resolve_paths(config)
    device = device_from_arg(device_arg)
    set_seed(seed)
    action_model = load_checkpoint_model(
        str(paths["action_checkpoint"]), "action_only", device
    )
    joint_model = load_checkpoint_model(str(paths["joint_checkpoint"]), "joint", device)
    manifest_path = resolved["processed_root"] / "test.jsonl"
    image_root = resolved["dataset_root"] / "data"
    amp = bool(config["training"]["amp"])
    expected_names: list[str] | None = None
    expected_action_targets: np.ndarray | None = None
    expected_rationale_targets: np.ndarray | None = None

    action_grid = np.empty((3, 5, SAMPLE_COUNT, 4), dtype=np.float32)
    joint_action_grid = np.empty_like(action_grid)
    joint_rationale_grid = np.empty((3, 5, SAMPLE_COUNT, 21), dtype=np.float32)

    def infer(transform: PixelCorruptionV2 | None) -> tuple[dict[str, Any], dict[str, Any]]:
        predictions: list[dict[str, Any]] = []
        for model in (action_model, joint_model):
            loader = make_loader(
                manifest_path,
                image_root,
                int(config["image_size"]),
                int(config["training"]["batch_size"]),
                int(config["training"]["num_workers"]),
                shuffle=False,
                seed=seed,
                pil_transform=transform,
            )
            predictions.append(predict(model, loader, device, amp=amp))
        return predictions[0], predictions[1]

    print(f"[round10] seed={seed} condition=clean start", flush=True)
    clean_action, clean_joint = infer(None)
    expected_names = [str(value) for value in clean_action["file_names"]]
    require(
        expected_names == [str(value) for value in clean_joint["file_names"]],
        "paired models produced different clean file order",
    )
    expected_action_targets = np.asarray(clean_action["action_targets"], dtype=np.float32)
    expected_rationale_targets = np.asarray(clean_joint["rationale_targets"], dtype=np.float32)
    require(
        np.array_equal(expected_action_targets, clean_joint["action_targets"]),
        "clean action targets differ between models",
    )
    require(
        np.array_equal(expected_rationale_targets, clean_action["rationale_targets"]),
        "clean rationale targets differ between models",
    )
    for family_index in range(3):
        action_grid[family_index, 0] = clean_action["action_logits"]
        joint_action_grid[family_index, 0] = clean_joint["action_logits"]
        joint_rationale_grid[family_index, 0] = clean_joint["rationale_logits"]

    for family_index, family in enumerate(FAMILIES):
        for level in LEVELS[1:]:
            print(f"[round10] seed={seed} family={family} level={level} start", flush=True)
            action_prediction, joint_prediction = infer(PixelCorruptionV2(family, level))
            names = [str(value) for value in action_prediction["file_names"]]
            require(names == expected_names, "condition file order differs")
            require(
                names == [str(value) for value in joint_prediction["file_names"]],
                "paired condition file order differs",
            )
            for prediction in (action_prediction, joint_prediction):
                require(
                    np.array_equal(expected_action_targets, prediction["action_targets"]),
                    "action targets changed across conditions",
                )
                require(
                    np.array_equal(expected_rationale_targets, prediction["rationale_targets"]),
                    "rationale targets changed across conditions",
                )
            action_grid[family_index, level] = action_prediction["action_logits"]
            joint_action_grid[family_index, level] = joint_prediction["action_logits"]
            joint_rationale_grid[family_index, level] = joint_prediction["rationale_logits"]
            print(f"[round10] seed={seed} family={family} level={level} done", flush=True)

    del action_model
    del joint_model
    if device.type == "cuda":
        torch.cuda.empty_cache()
    require(expected_names is not None, "missing file names")
    return {
        "file_names": np.asarray(expected_names),
        "action_targets": expected_action_targets,
        "rationale_targets": expected_rationale_targets,
        "action_only_logits": action_grid,
        "joint_action_logits": joint_action_grid,
        "joint_rationale_logits": joint_rationale_grid,
    }


def save_seed_logits(seed: int, payload: Mapping[str, np.ndarray]) -> Path:
    path = STAGING_DIR / f"seed_{seed}_logits.npz"
    metadata = {
        "schema_version": "ARSC_ROUND10_SEED_LOGITS_V1",
        "seed": seed,
        "families": list(FAMILIES),
        "levels": list(LEVELS),
        "parameters": {
            family: [float(value) for value in PARAMETERS[family]]
            for family in FAMILIES
        },
        "level_zero_execution": "one_clean_inference_duplicated_across_families",
        "nonzero_execution": "operator_before_resize",
        "cache_reused": False,
        "restartable": False,
    }
    with path.open("wb") as stream:
        np.savez_compressed(
            stream,
            **payload,
            metadata_json=np.asarray(
                json.dumps(metadata, sort_keys=True, separators=(",", ":"))
            ),
        )
    return path


def prepare_all_seeds(
    payloads: Sequence[Mapping[str, np.ndarray]],
) -> tuple[list[dict[str, Any]], np.ndarray, tuple[str, ...], np.ndarray]:
    base_names = [str(value) for value in payloads[0]["file_names"].tolist()]
    clip_ids, clip_keys, clip_sizes = source_clip_membership(base_names)
    require(len(clip_keys) == CLIP_COUNT, "formal clip count differs")
    prepared: list[dict[str, Any]] = []
    for seed, payload in zip(SEEDS, payloads):
        names = [str(value) for value in payload["file_names"].tolist()]
        require(names == base_names, f"file order differs for seed {seed}")
        require(
            np.array_equal(payload["action_targets"], payloads[0]["action_targets"])
            and np.array_equal(payload["rationale_targets"], payloads[0]["rationale_targets"]),
            f"targets differ for seed {seed}",
        )
        paths = seed_paths(seed)
        prepared.append(
            prepare_seed_clip_statistics(
                payload["action_targets"],
                payload["rationale_targets"],
                payload["action_only_logits"],
                payload["joint_action_logits"],
                payload["joint_rationale_logits"],
                load_temperature(paths["action_calibration"], "action_only"),
                load_temperature(paths["joint_calibration"], "joint"),
                clip_ids,
                CLIP_COUNT,
            )
        )
    return prepared, clip_ids, clip_keys, clip_sizes


def compute_point_results(
    prepared: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, np.ndarray], list[dict[str, Any]]]:
    harmonic = harmonic_numbers(SAMPLE_COUNT)
    seed_curves = {
        axis: np.empty(
            (5, 3, len(AXIS_COMPONENTS[axis]), 5),
            dtype=np.float64,
        )
        for axis in AXES
    }
    bottlenecks = np.empty((5, 3, 4), dtype=np.float64)
    endpoints = np.empty((5, 3, 8), dtype=np.float64)
    diagnostic_rows: list[dict[str, Any]] = []
    action_f1 = np.empty((5, 3, 5, 2, 4), dtype=np.float64)
    action_target_positive = np.empty_like(action_f1, dtype=np.int64)
    action_predicted_positive = np.empty_like(action_f1, dtype=np.int64)
    rationale_f1 = np.empty((5, 3, 5, 21), dtype=np.float64)
    rationale_target_positive = np.empty_like(rationale_f1, dtype=np.int64)
    rationale_predicted_positive = np.empty_like(rationale_f1, dtype=np.int64)
    safety = np.empty((5, 3, 5, 2, len(SAFETY_DIAGNOSTICS)), dtype=np.float64)

    for seed_index, (seed, item) in enumerate(zip(SEEDS, prepared)):
        counts = np.ones(CLIP_COUNT, dtype=np.int64)
        curves = all_family_curves_from_clip_counts(item, counts, harmonic)
        for axis in AXES:
            seed_curves[axis][seed_index] = curves[axis]
            for family_index, family in enumerate(FAMILIES):
                for component_index, component in enumerate(AXIS_COMPONENTS[axis]):
                    for level in LEVELS:
                        diagnostic_rows.append(
                            {
                                "record_type": "primary_curve",
                                "seed": seed,
                                "family": family,
                                "axis": axis,
                                "component": component,
                                "level": level,
                                "value": float(curves[axis][family_index, component_index, level]),
                            }
                        )
        bottlenecks[seed_index] = family_axis_bottlenecks(curves)
        endpoints[seed_index] = endpoint_effects(curves)

        for family_index, family in enumerate(FAMILIES):
            for level in LEVELS:
                for model_index, model in enumerate(MODELS):
                    tp = item["A_tp"][family_index, level, model_index].sum(axis=0)
                    fp = item["A_fp"][family_index, level, model_index].sum(axis=0)
                    fn = item["A_fn"][family_index, level, model_index].sum(axis=0)
                    scores = f1_from_counts(tp, fp, fn)
                    action_f1[seed_index, family_index, level, model_index] = scores
                    action_target_positive[seed_index, family_index, level, model_index] = tp + fn
                    action_predicted_positive[seed_index, family_index, level, model_index] = tp + fp
                    for class_index in range(4):
                        diagnostic_rows.append(
                            {
                                "record_type": "action_class",
                                "seed": seed,
                                "family": family,
                                "axis": "A",
                                "component": model,
                                "level": level,
                                "class_index": class_index,
                                "f1": float(scores[class_index]),
                                "target_positive": int(tp[class_index] + fn[class_index]),
                                "predicted_positive": int(tp[class_index] + fp[class_index]),
                            }
                        )
                    diagnostics = confidence_diagnostics(
                        item["errors"][family_index, level, model_index],
                        item["confidence"][family_index, level, model_index],
                    )
                    for diagnostic_index, name in enumerate(SAFETY_DIAGNOSTICS):
                        value = float(diagnostics[name])
                        safety[
                            seed_index,
                            family_index,
                            level,
                            model_index,
                            diagnostic_index,
                        ] = value
                        diagnostic_rows.append(
                            {
                                "record_type": "safety_diagnostic",
                                "seed": seed,
                                "family": family,
                                "axis": "S",
                                "component": model,
                                "level": level,
                                "diagnostic": name,
                                "value": value,
                            }
                        )
                tp_r = item["R_tp"][family_index, level].sum(axis=0)
                fp_r = item["R_fp"][family_index, level].sum(axis=0)
                fn_r = item["R_fn"][family_index, level].sum(axis=0)
                scores_r = f1_from_counts(tp_r, fp_r, fn_r)
                rationale_f1[seed_index, family_index, level] = scores_r
                rationale_target_positive[seed_index, family_index, level] = tp_r + fn_r
                rationale_predicted_positive[seed_index, family_index, level] = tp_r + fp_r
                for class_index in range(21):
                    diagnostic_rows.append(
                        {
                            "record_type": "rationale_class",
                            "seed": seed,
                            "family": family,
                            "axis": "R",
                            "component": "joint_rationale",
                            "level": level,
                            "class_index": class_index,
                            "f1": float(scores_r[class_index]),
                            "target_positive": int(tp_r[class_index] + fn_r[class_index]),
                            "predicted_positive": int(tp_r[class_index] + fp_r[class_index]),
                        }
                    )
    arrays = {
        **{f"curve_{axis}": values for axis, values in seed_curves.items()},
        "family_axis_bottlenecks": bottlenecks,
        "endpoint_effects": endpoints,
        "action_per_class_f1": action_f1,
        "action_target_positive": action_target_positive,
        "action_predicted_positive": action_predicted_positive,
        "rationale_per_class_f1": rationale_f1,
        "rationale_target_positive": rationale_target_positive,
        "rationale_predicted_positive": rationale_predicted_positive,
        "safety_diagnostics": safety,
    }
    require(
        all(np.all(np.isfinite(value)) for value in arrays.values()),
        "point diagnostics contain nonfinite values",
    )
    return arrays, diagnostic_rows


def save_primitives(
    prepared: Sequence[Mapping[str, Any]],
    clip_ids: np.ndarray,
    clip_keys: Sequence[str],
    clip_sizes: np.ndarray,
    point_arrays: Mapping[str, np.ndarray],
) -> Path:
    payload: dict[str, np.ndarray] = {
        "schema_version": np.asarray("ARSC_ROUND10_PRIMITIVES_V1"),
        "seeds": np.asarray(SEEDS, dtype=np.int16),
        "families": np.asarray(FAMILIES),
        "levels": np.asarray(LEVELS, dtype=np.int8),
        "models": np.asarray(MODELS),
        "axes": np.asarray(AXES),
        "endpoint_components": np.asarray(ENDPOINT_COMPONENTS),
        "safety_diagnostic_names": np.asarray(SAFETY_DIAGNOSTICS),
        "clip_id_by_image": clip_ids,
        "clip_keys": np.asarray(clip_keys),
        "clip_sizes": clip_sizes,
        "action_targets": np.asarray(prepared[0]["action_targets"], dtype=np.uint8),
        "rationale_targets": np.asarray(prepared[0]["rationale_targets"], dtype=np.uint8),
    }
    stack_keys = (
        "action_predictions",
        "rationale_predictions",
        "confidence",
        "errors",
        "group_ids",
        "group_counts",
        "A_tp",
        "A_fp",
        "A_fn",
        "R_tp",
        "R_fp",
        "R_fn",
        "C1_action_clip_sums",
        "C1_rationale_clip_sums",
    )
    for key in stack_keys:
        payload[key] = np.stack([np.asarray(item[key]) for item in prepared])
    payload.update({key: np.asarray(value) for key, value in point_arrays.items()})
    path = STAGING_DIR / "round10_corruption_primitives.npz"
    with path.open("wb") as stream:
        np.savez_compressed(stream, **payload)
    return path


def evaluate_gates(
    point_arrays: Mapping[str, np.ndarray],
    bootstrap: Mapping[str, np.ndarray],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    seed_bottlenecks = point_arrays["family_axis_bottlenecks"]
    endpoints = point_arrays["endpoint_effects"]
    mean_endpoints = endpoints.mean(axis=0)
    practical = practical_endpoint_pass(mean_endpoints)
    gate_draws = bootstrap["family_axis_gate_draws"]
    endpoint_draws = bootstrap["endpoint_draws"]
    gate_results: list[dict[str, Any]] = []
    endpoint_results: list[dict[str, Any]] = []
    bootstrap_rows: list[dict[str, Any]] = []

    for family_index, family in enumerate(FAMILIES):
        for axis_index, axis in enumerate(AXES):
            flat_index = family_index * 4 + axis_index
            draws = gate_draws[:, flat_index]
            pointwise_lower = quantile_diagnostic(draws, 0.025)
            pointwise_upper = quantile_diagnostic(draws, 0.975)
            bonferroni_lower = quantile_diagnostic(draws, BONFERRONI_PROBABILITY)
            seed_values = seed_bottlenecks[:, family_index, axis_index]
            endpoint_indices = AXIS_ENDPOINT_INDICES[axis]
            criteria = {
                "at_least_four_of_five_seed_bottlenecks_strictly_positive": (
                    int(np.sum(seed_values > 0.0)) >= 4
                ),
                "five_seed_unweighted_mean_strictly_positive": (
                    float(seed_values.mean()) > 0.0
                ),
                "bootstrap_bonferroni_lower_strictly_positive": (
                    bonferroni_lower["unrounded_result"] > 0.0
                ),
                "grand_mean_component_curves_have_no_reversal": (
                    mean_curve_no_reversal(
                        point_arrays[f"curve_{axis}"][:, family_index],
                        AXIS_DIRECTIONS[axis],
                    )
                ),
                "all_axis_practical_endpoints_pass": bool(
                    practical[family_index, list(endpoint_indices)].all()
                ),
            }
            passed = all(criteria.values())
            record = {
                "family": family,
                "axis": axis,
                "seed_bottlenecks": [float(value) for value in seed_values],
                "strictly_positive_seed_count": int(np.sum(seed_values > 0.0)),
                "five_seed_unweighted_mean_bottleneck": float(seed_values.mean()),
                "pointwise_95_interval": {
                    "lower": pointwise_lower,
                    "upper": pointwise_upper,
                },
                "bonferroni_one_sided_lower": bonferroni_lower,
                "criteria": criteria,
                "passed": passed,
            }
            gate_results.append(record)
            bootstrap_rows.append(
                {
                    "record_type": "family_axis_gate",
                    "family": family,
                    "axis": axis,
                    "estimate": float(seed_values.mean()),
                    "pointwise_lower": pointwise_lower["unrounded_result"],
                    "pointwise_upper": pointwise_upper["unrounded_result"],
                    "bonferroni_probability": BONFERRONI_PROBABILITY,
                    "bonferroni_lower": bonferroni_lower["unrounded_result"],
                    "passed": passed,
                }
            )
        for endpoint_index, component in enumerate(ENDPOINT_COMPONENTS):
            flat_index = family_index * 8 + endpoint_index
            draws = endpoint_draws[:, flat_index]
            lower = quantile_diagnostic(draws, 0.025)
            upper = quantile_diagnostic(draws, 0.975)
            estimate = float(mean_endpoints[family_index, endpoint_index])
            threshold = float(PRACTICAL_THRESHOLDS[component])
            passed = bool(practical[family_index, endpoint_index])
            endpoint_results.append(
                {
                    "family": family,
                    "component": component,
                    "per_seed_effects": [
                        float(value) for value in endpoints[:, family_index, endpoint_index]
                    ],
                    "unweighted_five_seed_mean_effect": estimate,
                    "threshold": threshold,
                    "comparison": "unrounded_float64_greater_than_or_equal",
                    "passed": passed,
                    "descriptive_pointwise_95_interval": {
                        "lower": lower,
                        "upper": upper,
                    },
                }
            )
            bootstrap_rows.append(
                {
                    "record_type": "practical_endpoint",
                    "family": family,
                    "component": component,
                    "estimate": estimate,
                    "threshold": threshold,
                    "pointwise_lower": lower["unrounded_result"],
                    "pointwise_upper": upper["unrounded_result"],
                    "passed": passed,
                }
            )
    result = {
        "gate_count": 12,
        "passed_gate_count": int(sum(record["passed"] for record in gate_results)),
        "all_twelve_gates_passed": bool(all(record["passed"] for record in gate_results)),
        "family_axis_gates": gate_results,
        "practical_endpoints": endpoint_results,
    }
    return result, bootstrap_rows


def formal_run(device: str, tmux_session: str | None) -> int:
    require(
        tmux_session == "arsc_round10_formal_attempt02",
        "formal analyzer requires the frozen tmux launcher contract",
    )
    manifest, validation = validate_formal_authorization(
        allow_formal_log=True,
    )
    STAGING_DIR.mkdir(parents=False, exist_ok=False)
    print(
        f"[round10] formal attempt02 authorized; implementation={manifest['implementation_commit']}",
        flush=True,
    )
    payloads: list[dict[str, np.ndarray]] = []
    seed_files: list[Path] = []
    for seed in SEEDS:
        payload = run_seed_inference(seed, device)
        payloads.append(payload)
        seed_path = save_seed_logits(seed, payload)
        seed_files.append(seed_path)
        print(f"[round10] seed={seed} logits saved sha256={sha256_file(seed_path)}", flush=True)

    prepared, clip_ids, clip_keys, clip_sizes = prepare_all_seeds(payloads)
    point_arrays, diagnostic_rows = compute_point_results(prepared)
    primitive_path = save_primitives(
        prepared, clip_ids, clip_keys, clip_sizes, point_arrays
    )
    point_csv = STAGING_DIR / "round10_corruption_point_diagnostics.csv"
    write_csv(point_csv, diagnostic_rows)
    print("[round10] point diagnostics complete; bootstrap start", flush=True)

    def bootstrap_progress(completed: int, total: int) -> None:
        print(f"[round10] bootstrap {completed}/{total}", flush=True)

    bootstrap = run_shared_bootstrap(
        prepared,
        replicates=BOOTSTRAP_REPLICATES,
        seed=BOOTSTRAP_SEED,
        progress=bootstrap_progress,
        progress_every=100,
    )
    bootstrap_path = STAGING_DIR / "round10_corruption_bootstrap_draws.npz"
    with bootstrap_path.open("wb") as stream:
        np.savez_compressed(
            stream,
            schema_version=np.asarray("ARSC_ROUND10_BOOTSTRAP_DRAWS_V1"),
            **bootstrap,
        )
    gates, bootstrap_rows = evaluate_gates(point_arrays, bootstrap)
    bootstrap_csv = STAGING_DIR / "round10_corruption_bootstrap_summary.csv"
    write_csv(bootstrap_csv, bootstrap_rows)

    produced = [*seed_files, primitive_path, point_csv, bootstrap_path, bootstrap_csv]
    result = {
        "schema_version": "ARSC_ROUND10_CORRUPTION_RESULTS_V1",
        "generated_at_utc": utc_now(),
        "status": "COMPLETE",
        "formal_run": True,
        "attempt": "attempt02",
        "implementation_commit": manifest["implementation_commit"],
        "formal_go": {
            "path": relative(GO_PATH),
            "sha256": sha256_file(GO_PATH),
            "decision": validation["go"]["verdict"]["decision"],
        },
        "design": manifest["frozen_design"],
        "data": {
            "sample_count": SAMPLE_COUNT,
            "source_clip_count": CLIP_COUNT,
            "test_manifest_sha256": EXPECTED_TEST_MANIFEST_SHA256,
            "source_image_inventory_sha256": EXPECTED_IMAGE_INVENTORY_SHA256,
            "clip_id_by_image_array_sha256": array_sha256(clip_ids),
            "clip_sizes_array_sha256": array_sha256(clip_sizes),
        },
        "bootstrap": {
            "replicates": BOOTSTRAP_REPLICATES,
            "seed": BOOTSTRAP_SEED,
            "rng": "numpy.random.default_rng",
            "seed_draw_size": 5,
            "clip_draw_size": CLIP_COUNT,
            "family_axis_gate_draw_shape": list(
                bootstrap["family_axis_gate_draws"].shape
            ),
            "endpoint_draw_shape": list(bootstrap["endpoint_draws"].shape),
            "seed_position_draw_shape": list(
                bootstrap["seed_position_draws"].shape
            ),
            "clip_position_draw_shape": list(
                bootstrap["clip_position_draws"].shape
            ),
            "expanded_image_count_shape": list(
                bootstrap["expanded_image_counts"].shape
            ),
            "bonferroni_fixed_gate_count": 12,
            "one_sided_probability": BONFERRONI_PROBABILITY,
            "quantile_method": "linear",
        },
        "gate_result": gates,
        "verdict": (
            "ROUND10_FULL_PREREGISTERED_PASS"
            if gates["all_twelve_gates_passed"]
            else "ROUND10_PARTIAL_OR_FAIL"
        ),
        "artifact_sha256_before_result_json": {
            relative(FINAL_DIR / path.name): sha256_file(path)
            for path in produced
        },
        "serialization": {
            "raw_logits_float_dtype": "float32_lossless_npz",
            "derived_statistics_float_dtype": "float64",
            "result_json_written_last": True,
            "staging_renamed_atomically_after_result": True,
            "cache_reuse": False,
        },
        "claim_boundary": (
            "BDD-OIA-internal joint metric-by-model-by-operator dose-response "
            "for the frozen population, five historical ResNet-50 seeds, "
            "fixed thresholds/calibrations, and three synthetic grids only."
        ),
    }
    result_path = STAGING_DIR / "round10_corruption_results.json"
    result_path.write_bytes(json_bytes(result))
    os.replace(STAGING_DIR, FINAL_DIR)
    print(
        f"[round10] COMPLETE verdict={result['verdict']} final={relative(FINAL_DIR)}",
        flush=True,
    )
    return 0


def guard_only() -> int:
    manifest, _ = validate_formal_authorization(
        allow_formal_log=False,
    )
    print(
        json.dumps(
            {
                "status": "PASS_FORMAL_PRESTART_GUARD",
                "implementation_commit": manifest["implementation_commit"],
                "formal_run": False,
                "formal_log_absent": True,
                "unknown_round10_artifacts_absent": True,
            },
            indent=2,
        ),
        flush=True,
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="perform the outcome-blind implementation preflight only",
    )
    parser.add_argument(
        "--guard-only",
        action="store_true",
        help="validate the committed GO and exhaustive prestart guard",
    )
    parser.add_argument("--tmux-session")
    parser.add_argument("--device", default="auto")
    args = parser.parse_args()
    require(
        not (args.preflight_only and args.guard_only),
        "preflight-only and guard-only are mutually exclusive",
    )
    return args


def main() -> int:
    args = parse_args()
    if args.preflight_only:
        return preflight_only()
    if args.guard_only:
        return guard_only()
    return formal_run(args.device, args.tmux_session)


if __name__ == "__main__":
    raise SystemExit(main())
