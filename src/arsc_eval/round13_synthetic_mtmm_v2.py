"""Result-blind preclaim supersession draft for the Round 13 synthetic MTMM study (V2).

V2 is a **result-blind preclaim supersession of V1**, not a retry and not a
scientific verdict.  It deliberately reuses the V1 frozen worlds, feature
roles, rule selections, replacement orders, generator qualities, namespace, and
all existing seed strings byte-for-byte; nothing is resampled.  The module
contains no observed metric value, no confidence interval, no gate decision,
and no scientific verdict.  Process statuses (``SUPERSEDED_PRECLAIM``,
``PREFORMAL_REFUSAL_V2``, ``POSTCLAIM_INFRASTRUCTURE_FAILURE_V2``,
``GO_RUN_V2``) are explicitly not scientific verdicts.

The only two scientific verdict strings remain the unchanged V1 pair frozen in
``FINAL_VERDICTS``.

V2 freezes in (a) exact Boolean semantics including the even-majority
tie rule and the four-input threshold, and (b) the exact random-action seed
bytes for the ``random_matched_sparsity`` generator.  These were the reported
reason codes for the unpinned V1 interpretation; V2 pins them.
"""

from __future__ import annotations

import hashlib
import json
import re
import copy
import os
import stat
from pathlib import Path
from typing import Any, Callable

from arsc_eval import round13_synthetic_mtmm as v1
from arsc_eval.round13_synthetic_mtmm import (
    ATTRIBUTION_AGGREGATION,
    BASELINES,
    BOUNDARY_CONTROLS,
    DOSES,
    ESTIMANDS,
    FAMILIES,
    FAMILY_Q,
    FINAL_VERDICTS,
    FORMULAS,
    GATES,
    GENERATORS,
    MANIPULATIONS,
    METRICS,
    NAMESPACE,
    NONZERO_DOSES,
    RANKING_REPORTS,
    ROW_CONFIDENCE_CONTRACT,
    ROWS_PER_WORLD,
    RULE_BANK,
    WORLD_COUNT,
)

# ---------------------------------------------------------------------------
# V2 schema / output path (requirement 1).
# ---------------------------------------------------------------------------
SCHEMA_VERSION = "arsc-round13-synthetic-mtmm-protocol-v2"
FROZEN_PROTOCOL_OUTPUT = "outputs/validity/round13_synthetic_mtmm_v2_frozen_protocol.json"
V2_PROTOCOL_NAME = "round13_synthetic_mtmm_v2_frozen_protocol.json"

# ---------------------------------------------------------------------------
# Immutable lineage record binding the exact V1 artifact (requirement 4).
# ---------------------------------------------------------------------------
V1_PROTOCOL_REL = "outputs/validity/round13_synthetic_mtmm_frozen_protocol.json"
V1_PROTOCOL_SHA256 = "7C32F1DB779B1D99FA7118E496196DD325930E169055637639AE66806DF4890C"
V1_SCHEMA = "arsc-round13-synthetic-mtmm-protocol-v1"
PRIOR_ATTEMPT = "round13_attempt01"
PRECLAIM_PHASE = "PRECLAIM_RESULT_BLIND"
SUPERSEDED_STATUS = "SUPERSEDED_PRECLAIM"

V1_REASON_CODES = (
    "UNPINNED_EVEN_MAJORITY_THRESHOLD",
    "RANDOM_ACTION_SEED_BYTES",
)

LINEAGE = {
    "supersedes": {
        "path": V1_PROTOCOL_REL,
        "sha256": V1_PROTOCOL_SHA256,
        "schema": V1_SCHEMA,
        "prior_attempt": PRIOR_ATTEMPT,
        "phase": PRECLAIM_PHASE,
        "formal_claim_absent": True,
        "status": SUPERSEDED_STATUS,
        "reason_codes": list(V1_REASON_CODES),
        "kind": "result-blind preclaim supersession; neither a retry nor a scientific verdict",
    }
}

# ---------------------------------------------------------------------------
# The exact, shared tuple of the four V2 bound source relative paths.  Both the
# freezer (scripts/freeze_round13_synthetic_mtmm_v2_protocol.py) and the frozen
# byte verifier (verify_v2_frozen_bytes) derive their bound-source set from this
# single tuple so the provenance key set cannot drift between build and verify:
#   index 0: V1 specification source
#   index 1: V2 specification source
#   index 2: the V2 freezer source
#   index 3: the V2 tests
# ---------------------------------------------------------------------------
V2_BOUND_SOURCE_RELS = (
    "src/arsc_eval/round13_synthetic_mtmm.py",
    "src/arsc_eval/round13_synthetic_mtmm_v2.py",
    "scripts/freeze_round13_synthetic_mtmm_v2_protocol.py",
    "tests/test_round13_synthetic_mtmm_v2.py",
)

# ---------------------------------------------------------------------------
# Frozen Boolean semantics (requirement 2).  Ties are false.
# MAJORITY(v1..vn)=1 iff sum(v)>=floor(n/2)+1; for n=4 the threshold is 3.
# ---------------------------------------------------------------------------
def majority(vals: list[int]) -> int:
    """Freeze MAJORITY with strict majority: 1 iff sum>=floor(n/2)+1; ties false."""
    n = len(vals)
    threshold = n // 2 + 1
    return 1 if sum(vals) >= threshold else 0


def and_op(left: int, right: int) -> int:
    return int(bool(left) and bool(right))


def or_op(left: int, right: int) -> int:
    return int(bool(left) or bool(right))


def xor_op(left: int, right: int) -> int:
    return int(bool(left)) ^ int(bool(right))


def parity(vals: list[int]) -> int:
    return sum(int(bool(v)) for v in vals) % 2


BOOLEAN_SEMANTICS = {
    "AND": "a AND b = 1 iff a=1 and b=1; else 0",
    "OR": "a OR b = 1 iff a=1 or b=1; else 0",
    "XOR": "a XOR b = 1 iff exactly one of a,b is 1; else 0",
    "PARITY": "PARITY(v1..vn)=sum(v) mod 2",
    "MAJORITY": (
        "MAJORITY(v1..vn)=1 iff sum(v)>=floor(n/2)+1; ties are false; "
        "for n=4 the threshold is floor(4/2)+1=3"
    ),
    "MAJORITY_THRESHOLD": "floor(n/2)+1",
    "MAJORITY_TIES": False,
    "FOUR_INPUT_THRESHOLD": 3,
}

# ---------------------------------------------------------------------------
# Frozen random-action seed bytes (requirement 3).
# UTF-8 string format:
#   ARSC_ROUND13_SYNTHETIC_MTMM_V1:generator_seed:random_matched_sparsity:action:{world}:{row:04d}:{action}
# SHA-256, digest[31]&1, XOR with truth.  No other interpretation.
# ---------------------------------------------------------------------------
RANDOM_MATCHED_ACTION_ROLE = "random_matched_sparsity"
EXAMPLE_RANDOM_ACTION_SEED = (
    b"ARSC_ROUND13_SYNTHETIC_MTMM_V1:generator_seed:random_matched_sparsity:action:0:0000:0"
)


def random_action_seed_bytes(world_index: int, row: int, action: int) -> bytes:
    """Return the exact frozen UTF-8 seed bytes for a random action cell."""
    seed = (
        f"{NAMESPACE}:generator_seed:random_matched_sparsity:action:"
        f"{world_index}:{row:04d}:{action}"
    )
    return seed.encode("utf-8")


def random_action_lsb(seed_bytes: bytes) -> int:
    """SHA-256 then digest[31]&1; the only permitted interpretation."""
    digest = hashlib.sha256(seed_bytes).digest()
    return digest[31] & 1


def random_matched_sparsity_action_bit(world_id: str, row: int, action: int, truth: int) -> int:
    """Predicted random action bit = truth XOR (SHA256(seed) digest[31] & 1)."""
    world_index = int(world_id.split("_")[1])
    seed = random_action_seed_bytes(world_index, row, action)
    return int(bool(truth)) ^ random_action_lsb(seed)


# ---------------------------------------------------------------------------
# Formal one-shot V2 execution contract (requirement 5).  All V2 formal paths
# use round13_synthetic_mtmm_v2_*; attempt is round13_attempt02; claim schema
# is ARSC_ROUND13_SYNTHETIC_MTMM_CLAIM_V2.  Preflight/formal runner refuses
# when any legacy V1 formal artifact or any V2 formal artifact exists.
# ---------------------------------------------------------------------------
FORMAL_EXECUTION_SCHEMA = "ARSC_ROUND13_SYNTHETIC_MTMM_CLAIM_V2"
FORMAL_ATTEMPT = "round13_attempt02"
FORMAL_CLAIM_NAME = "round13_synthetic_mtmm_v2_formal_claim.json"
FORMAL_RESULTS_NAME = "round13_synthetic_mtmm_v2_results.json"
FORMAL_VERDICT_NAME = "round13_synthetic_mtmm_v2_verdict.json"
FORMAL_INDEX_NAME = "round13_synthetic_mtmm_v2_artifact_index.json"
FORMAL_CLAIM_PATH = "outputs/validity/round13_synthetic_mtmm_v2_formal_claim.json"

V2_PREFORMAL_ARTIFACT_RELS = (
    FORMAL_CLAIM_NAME,
    FORMAL_RESULTS_NAME,
    FORMAL_VERDICT_NAME,
    FORMAL_INDEX_NAME,
)
V2_ARTIFACT_ALLOWLIST = (
    V2_PROTOCOL_NAME,
    *V2_PREFORMAL_ARTIFACT_RELS,
)

# Legacy V1 formal artifacts (the V1 claim/result/verdict/index set) must also
# be absent before a V2 run may proceed.
V1_LEGACY_FORMAL_ARTIFACT_RELS = (
    "round13_synthetic_mtmm_formal_claim.json",
    "round13_synthetic_mtmm_results.json",
    "round13_synthetic_mtmm_verdict.json",
    "round13_synthetic_mtmm_artifact_index.json",
)

V2_ONE_SHOT = {
    "formal_claim_is_permanent": True,
    "infrastructure_failure_consumes_claim": True,
    "retry_allowed": False,
    "delete_or_recover_claim_allowed": False,
    "attempt": FORMAL_ATTEMPT,
    "claim_path": FORMAL_CLAIM_PATH,
    "claim_schema": FORMAL_EXECUTION_SCHEMA,
    "approval_marker": "independent GO_RUN_V2 approval required",
    "preclaim_refusal": {
        "status": "PREFORMAL_REFUSAL_V2",
        "claim_consumed": False,
        "kind": "preformal refusal before any durable V2 claim is acquired",
    },
    "postclaim_failure": {
        "status": "POSTCLAIM_INFRASTRUCTURE_FAILURE_V2",
        "claim_consumed": True,
        "kind": "postclaim infrastructure failure consumes the one-attempt V2 claim; no retry; no delete",
    },
    "claim_binding": {
        "binds_v2_protocol_sha256": True,
        "binds_runner_and_source_hashes": True,
        "binds_approval": "GO_RUN_V2",
        "approval_is_independent_of_formal_runner": True,
    },
    "scientific_verdict_count": 2,
    "process_statuses_are_not_scientific_verdicts": True,
}

V2_HASH_CLOSURE = {
    "index": FORMAL_INDEX_NAME,
    "allowlist": list(V2_ARTIFACT_ALLOWLIST),
    "index_records": [V2_PROTOCOL_NAME, FORMAL_RESULTS_NAME, FORMAL_VERDICT_NAME],
    "index_self_excluded": True,
    "claim_cycle_excluded": True,
    "claim_is_not_rewritten": True,
    "closure_rule": "index hashes V2 protocol, results, and verdict; subsequent Git commit and independent H3 closure bind permanent claim and index",
    "v1_lineage_transitively_closed_by_v2_protocol": True,
    "postclaim_failure_consumes_claim": True,
}

# ---------------------------------------------------------------------------
# Hash / canonical helpers (mirror V1 so digests compose deterministically).
# ---------------------------------------------------------------------------
def _digest(text: str) -> bytes:
    return hashlib.sha256(text.encode("utf-8")).digest()


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest().upper()


def _hash_order(key: str, size: int) -> list[int]:
    return sorted(range(size), key=lambda value: _digest(f"{key}:{value:04d}"))


def _order_digest(order: list[int]) -> str:
    payload = b"".join(value.to_bytes(4, "big") for value in order)
    return hashlib.sha256(payload).hexdigest().upper()


def _rule_variables(template: str) -> list[int]:
    return [int(index) for index in re.findall(r"x(\d+)", template)]


def _instantiate_expression(template: str, causal: list[int]) -> str:
    return re.sub(r"x(\d+)", lambda match: f"f_{causal[int(match.group(1))]}", template)


def _expression_support(expression: str) -> list[int]:
    return sorted({int(index) for index in re.findall(r"f_(\d+)", expression)})


# ---------------------------------------------------------------------------
# Contract building (requirement 1/7).  Worlds/orders are reused byte-for-byte
# from V1 (build_worlds / build_replacement_orders are never resampled).
# ---------------------------------------------------------------------------
def build_contract(v1_protocol: dict[str, Any], *, include_replacement_orders: bool = True) -> dict[str, Any]:
    if v1_protocol.get("schema_version") != V1_SCHEMA or v1_protocol.get("result_blind") is not True:
        raise ValueError("caller must supply the exact parsed result-blind V1 frozen protocol")
    design = copy.deepcopy(v1_protocol["design"])
    evaluation = copy.deepcopy(v1_protocol["evaluation"])
    if not include_replacement_orders:
        design.pop("replacement_orders", None)
    design["generators"]["random_matched_sparsity"]["action_generation"] = (
        "for action a on row i, predict truth XOR (SHA256(exact V2 random_action.seed_string_format UTF-8 bytes).digest()[31] & 1)"
    )
    contract: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "result_blind": True,
        "prior_protocol_status": SUPERSEDED_STATUS,
        "lineage": LINEAGE,
        "boolean_semantics": BOOLEAN_SEMANTICS,
        "random_action": {
            "namespace": NAMESPACE,
            "generator": "random_matched_sparsity",
            "role": "action",
            "seed_string_format": (
                f"{NAMESPACE}:generator_seed:random_matched_sparsity:action:"
                "{world_index_decimal}:{row_4digit_zero_padded}:{action_decimal}"
            ),
            "example_bytes": EXAMPLE_RANDOM_ACTION_SEED.decode("utf-8"),
            "hash": "SHA-256 take digest[31]&1 and XOR with truth",
            "no_alternative_interpretation": True,
        },
        "design": design,
        "evaluation": evaluation,
        "formal_execution": {
            "one_shot": V2_ONE_SHOT,
            "artifact_allowlist": list(V2_ARTIFACT_ALLOWLIST),
            "preclaim_forbidden_artifacts": list(V2_PREFORMAL_ARTIFACT_RELS),
            "hash_closure": V2_HASH_CLOSURE,
            "legacy_artifacts_forbidden": list(V1_LEGACY_FORMAL_ARTIFACT_RELS),
            "possible_scientific_verdicts": list(FINAL_VERDICTS),
            "scientific_verdict_count": len(FINAL_VERDICTS),
        },
    }
    validate_contract(contract, v1_protocol, require_orders=include_replacement_orders)
    return contract


def validate_contract(contract: dict[str, Any], v1_protocol: dict[str, Any], *, require_orders: bool = True) -> None:
    if contract.get("result_blind") is not True:
        raise ValueError("protocol must remain result-blind")
    if contract.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("protocol schema version must be the V2 schema")
    if contract.get("prior_protocol_status") != SUPERSEDED_STATUS:
        raise ValueError("V1 prior protocol status must be SUPERSEDED_PRECLAIM")
    lineage = contract.get("lineage", {}).get("supersedes", {})
    if lineage.get("path") != V1_PROTOCOL_REL:
        raise ValueError("lineage must bind the V1 frozen protocol path")
    if lineage.get("sha256") != V1_PROTOCOL_SHA256:
        raise ValueError("lineage must bind the exact V1 SHA-256")
    if lineage.get("schema") != V1_SCHEMA:
        raise ValueError("lineage must bind the V1 schema")
    if lineage.get("prior_attempt") != PRIOR_ATTEMPT:
        raise ValueError("lineage prior_attempt must be round13_attempt01")
    if lineage.get("phase") != PRECLAIM_PHASE:
        raise ValueError("lineage phase must be PRECLAIM_RESULT_BLIND")
    if lineage.get("formal_claim_absent") is not True:
        raise ValueError("lineage formal_claim_absent must be true")
    if lineage.get("reason_codes") != list(V1_REASON_CODES):
        raise ValueError("lineage reason codes changed")
    design = contract["design"]
    v1_design = v1_protocol["design"]
    for key in (
        "world_count", "feature_count", "rows_per_world", "feature_role_counts",
        "doses", "worlds", "manipulations", "boundary_controls",
        "row_confidence_contract", "attribution_aggregation",
    ):
        if design.get(key) != v1_design.get(key):
            raise ValueError(f"V2 resampled or changed frozen V1 design field: {key}")
    for generator, record in v1_design["generators"].items():
        candidate = dict(design["generators"][generator])
        baseline = dict(record)
        if generator == "random_matched_sparsity":
            candidate.pop("action_generation", None)
            baseline.pop("action_generation", None)
        if candidate != baseline:
            raise ValueError(f"V2 changed frozen V1 generator fields: {generator}")
    if contract["evaluation"] != v1_protocol["evaluation"]:
        raise ValueError("V2 evaluation must be copied byte-semantically from frozen V1")
    boolean = contract.get("boolean_semantics", {})
    if boolean.get("MAJORITY_TIES") is not False:
        raise ValueError("MAJORITY ties must be false")
    if boolean.get("FOUR_INPUT_THRESHOLD") != 3:
        raise ValueError("four-input MAJORITY threshold must be 3")
    if (
        not contract["evaluation"]["formulas"] == FORMULAS
        or not contract["evaluation"]["metrics"] == METRICS
        or not contract["evaluation"]["baselines"] == BASELINES
    ):
        raise ValueError("V2 evaluation vocabulary must match the frozen V1 vocabulary")
    formal = contract["formal_execution"]
    if formal["one_shot"]["attempt"] != FORMAL_ATTEMPT:
        raise ValueError("V2 attempt label must be round13_attempt02")
    if formal["one_shot"]["claim_schema"] != FORMAL_EXECUTION_SCHEMA:
        raise ValueError("V2 claim schema must be ARSC_ROUND13_SYNTHETIC_MTMM_CLAIM_V2")
    if tuple(formal["possible_scientific_verdicts"]) != FINAL_VERDICTS:
        raise ValueError("exactly two scientific verdict strings are frozen")
    if formal["scientific_verdict_count"] != 2:
        raise ValueError("exactly two scientific verdicts are required")
    if formal["artifact_allowlist"] != list(V2_ARTIFACT_ALLOWLIST):
        raise ValueError("V2 artifact allowlist must contain protocol/claim/results/verdict/index")
    if formal["preclaim_forbidden_artifacts"] != list(V2_PREFORMAL_ARTIFACT_RELS):
        raise ValueError("V2 preclaim-forbidden artifact list changed")
    if formal["hash_closure"] != V2_HASH_CLOSURE:
        raise ValueError("V2 hash closure changed")
    if formal["one_shot"]["postclaim_failure"]["claim_consumed"] is not True:
        raise ValueError("postclaim failure must consume the one-attempt claim")
    if formal["one_shot"]["retry_allowed"] is not False:
        raise ValueError("postclaim retry must not be allowed")
    if formal["one_shot"]["delete_or_recover_claim_allowed"] is not False:
        raise ValueError("postclaim delete/recover must not be allowed")
    if not formal["one_shot"]["claim_binding"]["binds_v2_protocol_sha256"]:
        raise ValueError("V2 claim must bind the exact V2 protocol")
    if not formal["one_shot"]["claim_binding"]["binds_runner_and_source_hashes"]:
        raise ValueError("V2 claim must bind runner/source hashes")
    if formal["one_shot"]["claim_binding"]["binds_approval"] != "GO_RUN_V2":
        raise ValueError("V2 claim must bind the independent GO_RUN_V2 approval")
    if require_orders:
        orders = contract["design"].get("replacement_orders", [])
        if orders != v1_design.get("replacement_orders"):
            raise ValueError("V2 replacement orders must be copied from frozen V1 bytes")
        expected = WORLD_COUNT * len(GENERATORS) * len(MANIPULATIONS) * len(NONZERO_DOSES)
        if len(orders) != expected:
            raise ValueError("replacement order coverage mismatch")
        for record in orders:
            order = record["permutation"]
            if sorted(order) != list(range(ROWS_PER_WORLD)) or _order_digest(order) != record["permutation_sha256"]:
                raise ValueError("invalid replacement permutation or digest")


# ---------------------------------------------------------------------------
# V2 preflight / formal-run refusal logic (requirement 5).  The runner refuses
# if any legacy V1 formal artifact or any V2 formal artifact exists on disk.
# ---------------------------------------------------------------------------
def _is_link_or_reparse(info: os.stat_result) -> bool:
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(info.st_mode) or bool(flag and getattr(info, "st_file_attributes", 0) & flag)


def _stable_read_relative(root: Path, relative_path: str) -> bytes:
    """Stable-read a workspace-relative regular file with no-follow/reparse guards.

    The lexical path must stay inside the workspace, no component may be a
    symlink or reparse point, the file must be a regular file read with
    ``O_NOFOLLOW``, and its identity (device / inode / size / mtime) plus size
    must be unchanged across the read.
    """
    root_abs = Path(os.path.abspath(root))
    path = Path(os.path.abspath(root_abs / relative_path))
    if os.path.commonpath((str(root_abs), str(path))) != str(root_abs):
        raise ValueError(f"relative path escapes workspace: {relative_path}")
    current = root_abs
    for part in path.relative_to(root_abs).parts:
        current = current / part
        info = os.lstat(current)
        if _is_link_or_reparse(info):
            raise ValueError(f"path contains symlink/reparse component: {current}")
    before = os.lstat(path)
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"stable regular file required: {path}")
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        opened = os.fstat(descriptor)
        blocks = []
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            blocks.append(block)
        after_handle = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    after_path = os.lstat(path)
    identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
    if identity(before) != identity(opened) or identity(opened) != identity(after_handle) or identity(before) != identity(after_path):
        raise RuntimeError(f"file identity changed during read: {path}")
    raw = b"".join(blocks)
    if len(raw) != before.st_size:
        raise RuntimeError(f"file size changed during read: {path}")
    return raw


def _stable_read_v1(root: Path) -> bytes:
    return _stable_read_relative(root, V1_PROTOCOL_REL)


def _formal_artifact_paths(root: Path) -> list[Path]:
    return [
        Path(os.path.abspath(root / "outputs" / "validity" / name))
        for name in V2_PREFORMAL_ARTIFACT_RELS + V1_LEGACY_FORMAL_ARTIFACT_RELS
    ]


def refuse_if_formal_artifacts_exist(root: Path) -> None:
    """V2 preflight refuses when any legacy V1 or any V2 formal artifact exists."""
    present = []
    for path in _formal_artifact_paths(root):
        current = Path(os.path.abspath(root))
        for part in path.relative_to(current).parts[:-1]:
            current = current / part
            try:
                parent_info = os.lstat(current)
            except FileNotFoundError:
                break
            if _is_link_or_reparse(parent_info):
                raise ValueError(f"formal artifact parent is symlink/reparse: {current}")
        try:
            os.lstat(path)
        except FileNotFoundError:
            continue
        present.append(str(path))
    if present:
        raise FileExistsError(
            "legacy V1 or V2 formal artifact already present; V2 run is refused: "
            f"{present}"
        )


def run_preflight(root: Path) -> dict[str, Any]:
    """Deterministic result-blind V2 preflight (no claim, no outcomes, no GO_RUN).

    The preflight verifies the lineage record, that V2 does not resample the V1
    worlds/replacement orders, that the V2 contract is structurally valid, and
    that no legacy V1 or V2 formal artifact exists.  It writes nothing and
    never issues GO_RUN_V2.
    """
    root = Path(os.path.abspath(root))
    refuse_if_formal_artifacts_exist(root)
    raw = _stable_read_v1(root)
    if hashlib.sha256(raw).hexdigest().upper() != V1_PROTOCOL_SHA256:
        raise ValueError("V1 frozen protocol SHA-256 mismatch")
    v1_protocol = json.loads(raw.decode("utf-8"))
    build_contract(v1_protocol, include_replacement_orders=True)
    refuse_if_formal_artifacts_exist(root)
    return {
        "status": "PREFLIGHT_V2_PASS",
        "status_is_not_go_run": True,
        "status_is_not_a_scientific_verdict": True,
        "attempt": FORMAL_ATTEMPT,
        "schema_version": SCHEMA_VERSION,
        "result_blind": True,
        "lineage_verified": True,
        "v2_paths_verified": True,
        "worlds_resampled": False,
        "replacement_orders_resampled": False,
        "legacy_or_v2_formal_artifacts_present": False,
        "scientific_verdict_count": 2,
    }


# ---------------------------------------------------------------------------
# V2 frozen-protocol byte verification helper (requirement 7 source binding).
# ---------------------------------------------------------------------------
def verify_v2_frozen_bytes(root: Path) -> bytes:
    """Rebuild the expected V2 frozen protocol from V1 bytes and bound sources,
    then require the on-disk frozen bytes to match exactly.

    The verifier stable-reads both the frozen V2 protocol and the frozen V1
    protocol, canonical-checks and SHA-checks V1, parses it, builds the expected
    full V2 contract (with replacement orders), computes the exact bound-source
    hashes from the shared ``V2_BOUND_SOURCE_RELS`` tuple, computes the schema
    hash from the order-less contract, and rejects unless
    ``canonical_json_bytes(expected) == raw``.
    """
    raw_v2 = _stable_read_relative(root, FROZEN_PROTOCOL_OUTPUT)
    raw_v1 = _stable_read_v1(root)
    v1_obj = json.loads(raw_v1.decode("utf-8"))
    if canonical_json_bytes(v1_obj) != raw_v1:
        raise ValueError("V1 frozen protocol bytes are not canonical compact JSON")
    if hashlib.sha256(raw_v1).hexdigest().upper() != V1_PROTOCOL_SHA256:
        raise ValueError("V1 frozen protocol SHA-256 mismatch")
    expected = build_contract(v1_obj, include_replacement_orders=True)
    bound_sources = {
        relative: hashlib.sha256(_stable_read_relative(root, relative)).hexdigest().upper()
        for relative in V2_BOUND_SOURCE_RELS
    }
    schema_hash = hashlib.sha256(
        canonical_json_bytes(build_contract(v1_obj, include_replacement_orders=False))
    ).hexdigest().upper()
    expected["provenance"] = {
        "bound_sources": bound_sources,
        "v1_frozen_bytes_sha256": V1_PROTOCOL_SHA256,
        "v2_protocol_schema_sha256": schema_hash,
    }
    if canonical_json_bytes(expected) != raw_v2:
        raise ValueError("V2 frozen protocol bytes do not match the rebuilt expected provenance contract")
    return raw_v2


__all__ = [
    "BOOLEAN_SEMANTICS",
    "EXAMPLE_RANDOM_ACTION_SEED",
    "FINAL_VERDICTS",
    "FORMAL_ATTEMPT",
    "FORMAL_CLAIM_PATH",
    "FORMAL_CLAIM_NAME",
    "FORMAL_EXECUTION_SCHEMA",
    "FORMAL_INDEX_NAME",
    "FORMAL_RESULTS_NAME",
    "FORMAL_VERDICT_NAME",
    "FROZEN_PROTOCOL_OUTPUT",
    "GENERATORS",
    "LINEAGE",
    "MANIPULATIONS",
    "NAMESPACE",
    "PRIOR_ATTEMPT",
    "PRECLAIM_PHASE",
    "RANDOM_MATCHED_ACTION_ROLE",
    "SCHEMA_VERSION",
    "SUPERSEDED_STATUS",
    "V1_LEGACY_FORMAL_ARTIFACT_RELS",
    "V1_PROTOCOL_REL",
    "V1_PROTOCOL_SHA256",
    "V1_REASON_CODES",
    "V1_SCHEMA",
    "V2_ARTIFACT_ALLOWLIST",
    "V2_BOUND_SOURCE_RELS",
    "V2_PREFORMAL_ARTIFACT_RELS",
    "V2_HASH_CLOSURE",
    "V2_ONE_SHOT",
    "WORLD_COUNT",
    "and_op",
    "build_contract",
    "majority",
    "or_op",
    "parity",
    "random_action_lsb",
    "random_action_seed_bytes",
    "random_matched_sparsity_action_bit",
    "refuse_if_formal_artifacts_exist",
    "run_preflight",
    "verify_v2_frozen_bytes",
    "xor_op",
]
