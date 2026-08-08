"""Result-blind draft for the Round 13 synthetic MTMM study (V3).

V3 is a **result-blind preclaim supersession of the committed V2 artifact**
(commit ``ba00c2e``), not a retry and not a scientific verdict.  V3 reuses the
V2 frozen design, evaluation vocabulary, worlds, and replacement orders
byte-for-byte; **nothing is resampled**.  The rendered contract additionally
freezes, as *new* V3 machine-readable contracts, the directed C1 pairing
scheme, the refined ``S_fixture`` error-seed and analytic tie-aware AURC, the
generator hash-ordering, the R tensor, the deterministic world bootstrap
manifest/shuffle, the gate-status mapping, and the deterministic 3840 raw-cell
key manifest.  These are all result-blind specifications; the module contains
no observed metric value, no confidence interval, no gate decision, and no
scientific verdict.

The only two scientific verdict strings remain the unchanged V1/V2 pair frozen
in ``FINAL_VERDICTS``.  Process statuses (``SUPERSEDED_PRECLAIM`` and
``IMPLEMENTATION_FAILURE``) are explicitly not scientific verdicts, and
``IMPLEMENTATION_FAILURE`` is never a third verdict.

V3 keeps the V2 lineage record as ``lineage.supersedes`` and adds an isolated
V3 declaration block recording the exact V2 frozen-protocol digest, the frozen
Git commit ``ba00c2e``, attempt ``round13_attempt03`` and claim schema
``ARSC_ROUND13_SYNTHETIC_MTMM_CLAIM_V3``.

Importing this module performs no filesystem writes and no formal execution.
"""

from __future__ import annotations

import hashlib
import json
import math
import copy
from typing import Any

from arsc_eval.round13_synthetic_mtmm import (
    BASELINES,
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    DOSES,
    FAMILIES,
    FAMILY_Q,
    FEATURE_COUNT,
    FINAL_VERDICTS,
    FORMULAS,
    GENERATORS,
    MANIPULATIONS,
    METRICS,
    NAMESPACE,
    NONZERO_DOSES,
    ROWS_PER_WORLD,
    WORLD_COUNT,
)

# ---------------------------------------------------------------------------
# V3 schema / output path (requirement 1).
# ---------------------------------------------------------------------------
SCHEMA_VERSION = "arsc-round13-synthetic-mtmm-protocol-v3"
FROZEN_PROTOCOL_OUTPUT = "outputs/validity/round13_synthetic_mtmm_v3_frozen_protocol.json"
V3_PROTOCOL_NAME = "round13_synthetic_mtmm_v3_frozen_protocol.json"

# ---------------------------------------------------------------------------
# Immutable lineage binding the exact committed V2 frozen protocol and the
# frozen Git commit ba00c2e (requirement 1/4).
# ---------------------------------------------------------------------------
V2_PROTOCOL_REL = "outputs/validity/round13_synthetic_mtmm_v2_frozen_protocol.json"
V2_PROTOCOL_SHA256 = "38AF706B42B0CECCED97D3A5925CDE1360ED2C79FB3AE36680DC02E83DB432E5"
V2_COMMIT = "ba00c2e88b22a3fd503955f8f39c4e1548a18d31"
V2_SCHEMA = "arsc-round13-synthetic-mtmm-protocol-v2"
PRIOR_ATTEMPT = "round13_attempt02"
PRECLAIM_PHASE = "PRECLAIM_RESULT_BLIND"
SUPERSEDED_STATUS = "SUPERSEDED_PRECLAIM"


V3_REASON_CODES = (
    "C1_PAIR_MAPPING",
    "S_DIGEST_AND_TIE_CONFLICT",
    "GENERATOR_HASH_SEMANTICS",
    "SPARSE_ACTIVE_SEMANTICS",
    "R_AGGREGATION_AND_EXCLUSION",
    "BASELINE_BOUNDARY_SEMANTICS",
    "BOOTSTRAP_SHUFFLE_SEMANTICS",
    "CELL_MANIFEST_COMPLETENESS",
    "GATE_TO_VERDICT_MAPPING",
)

LINEAGE = {
    "supersedes": {
        "path": V2_PROTOCOL_REL,
        "sha256": V2_PROTOCOL_SHA256,
        "schema": V2_SCHEMA,
        "commit": V2_COMMIT,
        "prior_attempt": PRIOR_ATTEMPT,
        "phase": PRECLAIM_PHASE,
        "formal_claim_absent": True,
        "status": SUPERSEDED_STATUS,
        "reason_codes": list(V3_REASON_CODES),
        "kind": "result-blind preclaim supersession of the committed V2 artifact; neither a retry nor a scientific verdict",
        "no_resampling_of_worlds_or_orders": True,
    }
}

# ---------------------------------------------------------------------------
# Formal one-shot V3 execution contract.  All V3 formal paths use the
# round13_synthetic_mtmm_v3_* set; attempt is round13_attempt03 and the claim
# schema is ARSC_ROUND13_SYNTHETIC_MTMM_CLAIM_V3.  The runner refuses when any
# legacy V1/V2 formal artifact or any V3 formal artifact exists.
# ---------------------------------------------------------------------------
FORMAL_EXECUTION_SCHEMA = "ARSC_ROUND13_SYNTHETIC_MTMM_CLAIM_V3"
FORMAL_ATTEMPT = "round13_attempt03"
FORMAL_CLAIM_NAME = "round13_synthetic_mtmm_v3_formal_claim.json"
FORMAL_RESULTS_NAME = "round13_synthetic_mtmm_v3_results.json"
FORMAL_VERDICT_NAME = "round13_synthetic_mtmm_v3_verdict.json"
FORMAL_INDEX_NAME = "round13_synthetic_mtmm_v3_artifact_index.json"
FORMAL_CLAIM_PATH = "outputs/validity/round13_synthetic_mtmm_v3_formal_claim.json"

V3_PREFORMAL_ARTIFACT_RELS = (
    FORMAL_CLAIM_NAME,
    FORMAL_RESULTS_NAME,
    FORMAL_VERDICT_NAME,
    FORMAL_INDEX_NAME,
)
V3_ARTIFACT_ALLOWLIST = (
    V3_PROTOCOL_NAME,
    *V3_PREFORMAL_ARTIFACT_RELS,
)

# Legacy V1 and V2 formal artifacts must all be absent before a V3 run.
V2_LEGACY_FORMAL_ARTIFACT_RELS = (
    "round13_synthetic_mtmm_v2_formal_claim.json",
    "round13_synthetic_mtmm_v2_results.json",
    "round13_synthetic_mtmm_v2_verdict.json",
    "round13_synthetic_mtmm_v2_artifact_index.json",
)
V1_LEGACY_FORMAL_ARTIFACT_RELS = (
    "round13_synthetic_mtmm_formal_claim.json",
    "round13_synthetic_mtmm_results.json",
    "round13_synthetic_mtmm_verdict.json",
    "round13_synthetic_mtmm_artifact_index.json",
)

V3_ONE_SHOT = {
    "formal_claim_is_permanent": True,
    "infrastructure_failure_consumes_claim": True,
    "retry_allowed": False,
    "delete_or_recover_claim_allowed": False,
    "attempt": FORMAL_ATTEMPT,
    "claim_path": FORMAL_CLAIM_PATH,
    "claim_schema": FORMAL_EXECUTION_SCHEMA,
    "approval_marker": "independent GO_RUN_V3 approval required",
    "scientific_verdict_count": 2,
    "process_statuses_are_not_scientific_verdicts": True,
    "preclaim_refusal": {
        "status": "PREFORMAL_REFUSAL_V3",
        "claim_consumed": False,
        "kind": "preformal refusal before any durable V3 claim is acquired",
    },
    "postclaim_failure": {
        "status": "POSTCLAIM_INFRASTRUCTURE_FAILURE_V3",
        "claim_consumed": True,
        "kind": "postclaim infrastructure failure consumes the one-attempt V3 claim; no retry; no delete",
    },
    "infrastructure_status": {
        "value": "IMPLEMENTATION_FAILURE",
        "is_a_scientific_verdict": False,
        "note": "IMPLEMENTATION_FAILURE is an infrastructure/implementation status, never a third scientific verdict; the only two scientific verdicts are FINAL_VERDICTS.",
    },
    "claim_binding": {
        "binds_v3_protocol_sha256": True,
        "binds_runner_and_source_hashes": True,
        "binds_approval": "GO_RUN_V3",
        "approval_is_independent_of_formal_runner": True,
    },
}

V3_HASH_CLOSURE = {
    "index": FORMAL_INDEX_NAME,
    "allowlist": list(V3_ARTIFACT_ALLOWLIST),
    "index_records": [V3_PROTOCOL_NAME, FORMAL_RESULTS_NAME, FORMAL_VERDICT_NAME],
    "index_self_excluded": True,
    "claim_cycle_excluded": True,
    "claim_is_not_rewritten": True,
    "closure_rule": "index hashes V3 protocol, results, and verdict; subsequent Git commit and independent H3 closure bind permanent claim and index",
    "v2_lineage_transitively_closed_by_v3_protocol": True,
    "postclaim_failure_consumes_claim": True,
}

# ---------------------------------------------------------------------------
# Canonical / digest helpers (mirror V1/V2 so digests compose deterministically).
# ---------------------------------------------------------------------------


def _digest(text: str) -> bytes:
    return hashlib.sha256(text.encode("utf-8")).digest()


def _hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest().upper()


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        + "\n"
    ).encode("utf-8")


def hash_order_ascending(prefix: str, values: list[int]) -> list[int]:
    """Deterministic feature-id order: seed prefix + ':' + actual feature id decimal;
    sort by SHA-256 digest bytes ascending (interpreted unsigned big-endian); an
    exact digest collision (astronomically unlikely) is broken by ascending feature
    id ('collision feature id')."""
    keyed: list[tuple[int, int]] = sorted(
        (int.from_bytes(_digest(f"{prefix}:{value}"), "big"), value) for value in values
    )
    return [value for _digest_int, value in keyed]


def _order_digest(order: list[int]) -> str:
    payload = b"".join(value.to_bytes(4, "big") for value in order)
    return hashlib.sha256(payload).hexdigest().upper()


# ---------------------------------------------------------------------------
# Directed C1 pairs (requirement: directed C1 pairs).
#   * 1024 clean rows x all 3 nuisance feature IDs ascending => 3072 pairs/world
#   * XOR mapping: nuisance_row = clean_row XOR (1 << nuisance_feature_id)
#   * exact pair ID, dose affects all pairs anchored at an affected clean row
#   * action changed iff any of the 4 action bits differs
#   * rationale = mean Jaccard over the 4 actions, then mean over all pairs
# ---------------------------------------------------------------------------
NUISANCE_COUNT = 3
PAIRS_PER_WORLD = ROWS_PER_WORLD * NUISANCE_COUNT  # 1024 * 3 == 3072
C1_XOR_MAPPING = "nuisance_row = clean_row XOR (1 << nuisance_feature_id)"


def c1_pair_id(world_index: int, clean_row: int, nuisance_feature_id: int) -> str:
    """Exact directed C1 pair ID.

    Format is the canonical ``world_{w:02d}:row_{row:04d}:nuisance_{feature}``;
    ``nuisance_{feature}`` is the actual nuisance feature ID (no zero padding,
    matching ``feature_roles.nuisance``).
    """
    return (
        f"world_{world_index:02d}:row_{clean_row:04d}:nuisance_{nuisance_feature_id}"
    )


def c1_pair_sha256(pair_id: str) -> str:
    """SHA-256 (UTF-8) of the exact canonical C1 pair ID."""
    return _hex(pair_id)


def _world_index_from_id(world_id: str) -> int:
    prefix, suffix = world_id.split("_", 1)
    if prefix != "world":
        raise ValueError(f"invalid world_id: {world_id!r}")
    return int(suffix)


def build_directed_c1_pairs(
    world: dict[str, Any], *, nuisance_feature_ids: list[int] | None = None
) -> list[dict[str, Any]]:
    """All 3072 directed C1 pairs for one world.

    ``world`` must be the actual frozen world record (its ``world_id`` and
    ``feature_roles.nuisance`` are authoritative).  If ``nuisance_feature_ids``
    is omitted it is taken from ``world["feature_roles"]["nuisance"]``.

    Validation raises ValueError (never assert):
      * exactly 3 unique nuisance ID values must be supplied;
      * every nuisance ID must be in 0..FEATURE_COUNT-1 (0..9);
      * the set of nuisance IDs must equal the world's frozen nuisance roles.

    Ordering is frozen as: row ascending, then within a row the nuisance
    feature actual ID ascending.  Each pair serializes as canonical JSON UTF-8
    plus a trailing newline (``canonical_json_bytes``).
    """
    if not isinstance(world, dict):
        raise ValueError("build_directed_c1_pairs requires the actual frozen world dict")
    world_id = world.get("world_id")
    if not isinstance(world_id, str) or not world_id.startswith("world_"):
        raise ValueError(f"world must carry a 'world_' prefixed world_id, got {world_id!r}")
    world_index = _world_index_from_id(world_id)
    frozen_nuisance = world.get("feature_roles", {}).get("nuisance")
    if not isinstance(frozen_nuisance, list) or len(frozen_nuisance) != NUISANCE_COUNT:
        raise ValueError("world feature_roles.nuisance must be exactly the 3 nuisance feature IDs")
    if nuisance_feature_ids is None:
        ids = list(frozen_nuisance)
    else:
        ids = list(nuisance_feature_ids)
    if len(ids) != NUISANCE_COUNT or len(set(ids)) != NUISANCE_COUNT:
        raise ValueError("nuisance_feature_ids must contain exactly 3 unique nuisance feature IDs")
    if any(int(i) not in range(FEATURE_COUNT) for i in ids):
        raise ValueError("nuisance feature IDs must be within 0..9")
    if set(int(i) for i in ids) != set(int(i) for i in frozen_nuisance):
        raise ValueError("nuisance_feature_ids must equal the world's frozen feature_roles.nuisance")

    pairs: list[dict[str, Any]] = []
    for clean_row in range(ROWS_PER_WORLD):
        for f in sorted(int(i) for i in ids):  # nuisance actual ID ascending
            nuisance_row = clean_row ^ (1 << f)
            pair_id = c1_pair_id(world_index, clean_row, f)
            record: dict[str, Any] = {
                "pair_id": pair_id,
                "pair_sha256": c1_pair_sha256(pair_id),
                "world_index": world_index,
                "clean_row": clean_row,
                "nuisance_feature_id": f,
                "nuisance_row": nuisance_row,
                "xor_bit": f,
                "directed": True,
            }
            pairs.append(record)
    if len(pairs) != PAIRS_PER_WORLD:
        raise ValueError(f"expected exactly {PAIRS_PER_WORLD} directed pairs per world")
    return pairs


def c1_serialize_pair(pair: dict[str, Any]) -> bytes:
    """Canonical JSON UTF-8 + newline serialization of a directed C1 pair."""
    return canonical_json_bytes(pair)


def c1_build_manifest(worlds: list[dict[str, Any]]) -> dict[str, Any]:
    """32 per-world manifest hashes plus the global V3 C1 manifest hash.

    Each pair is serialized as canonical JSON UTF-8 + a newline
    (``canonical_json_bytes(record)``).  Per-world manifest payload is the
    concatenation of the canonical full pair records (not only IDs) in row
    ascending then nuisance actual-ID ascending order (the exact
    ``build_directed_c1_pairs`` order); the per-world manifest hash covers that
    raw byte payload.  The global payload is the concatenation of the per-world
    raw payloads in world order (worlds sorted by increasing world_index), and
    the global manifest hash covers that concatenated byte payload.
    """
    per_world: dict[str, dict[str, Any]] = {}
    ordered_worlds = sorted(worlds, key=lambda w: _world_index_from_id(w["world_id"]))
    global_payload = b""
    for world in ordered_worlds:
        world_index = _world_index_from_id(world["world_id"])
        pairs = build_directed_c1_pairs(world)
        payload = b"".join(c1_serialize_pair(p) for p in pairs)
        per_world[str(world_index)] = {
            "world_index": world_index,
            "pair_count": len(pairs),
            "manifest_sha256": hashlib.sha256(payload).hexdigest().upper(),
        }
        global_payload += payload
    return {
        "per_world": per_world,
        "per_world_count": len(per_world),
        "total_pairs": sum(record["pair_count"] for record in per_world.values()),
        "global_manifest_sha256": hashlib.sha256(global_payload).hexdigest().upper(),
    }


def build_directed_c1_contract(design: dict[str, Any]) -> dict[str, Any]:
    """Freeze the full directed C1 machine-readable contract over a design.

    ``design`` must carry the 32 frozen worlds (``design["worlds"]``); the
    contract embeds the exact C1 manifest built from those worlds and freezes
    every C1 framing rule result-blind (no observed outputs).
    """
    worlds = design.get("worlds")
    if not isinstance(worlds, list) or len(worlds) != WORLD_COUNT:
        raise ValueError("design.worlds must be the exact 32 frozen worlds for the directed C1 contract")
    manifest = c1_build_manifest(worlds)
    return {
        "pair_id_format": (
            "exact pair_id = world_{world_index:02d}:row_{clean_row:04d}:nuisance_{nuisance_feature_id}; "
            "nuisance_feature_id is the actual nuisance feature ID (no zero padding)"
        ),
        "pair_order": (
            "row ascending (clean_row 0..1023), then within a row the nuisance "
            "feature actual ID ascending (the exact build_directed_c1_pairs order)"
        ),
        "paired_cells_per_world": PAIRS_PER_WORLD,
        "clean_rows": ROWS_PER_WORLD,
        "nuisance_count": NUISANCE_COUNT,
        "nuisance_feature_ids_ascending": True,
        "xor_mapping": C1_XOR_MAPPING,
        "rerun_generator_baseline_at_paired_row": True,
        "dose_anchoring": (
            "dose affects all 3 pairs anchored at an affected clean row; the immutable "
            "clean-channel output is always left unchanged and only the paired output "
            "(shared output) of each affected anchored clean row is overwritten, so the "
            "overwrite applies solely to the paired output of affected anchored clean rows"
        ),
        "action_changed_rule": (
            "C1_action counts a pair as changed iff any of the 4 action bits differs "
            "(any 4-bit vector difference); the change is binary with no ties"
        ),
        "action_denominator": PAIRS_PER_WORLD,
        "rationale_denominator": PAIRS_PER_WORLD,
        "rationale_aggregation": (
            "mean Jaccard over the 4 actions (per pair), then mean over all pairs"
        ),
        "empty_vs_empty_jaccard": 1.0,
        "causal_bits_truth_invariant": (
            "nuisance-only pairs never recompute truth; ground-truth causal bits are "
            "unchanged across each pair, so any changed prediction is a genuine C1 violation"
        ),
        "serialization_framing": (
            "each pair record serialized canonically (canonical_json_bytes: compact "
            "JSON UTF-8 + newline); per-world manifest payload = concatenation of "
            "canonical pair records in row-then-nuisance-ID order; global payload = "
            "concatenation of the per-world raw payloads in world order"
        ),
        "manifest": manifest,
    }


def c1_pair_action_changed(clean_actions: list[int], nuisance_actions: list[int]) -> int:
    """Action changed iff any of the 4 bits differs (binary, no ties)."""
    if len(clean_actions) != ACTION_COUNT or len(nuisance_actions) != ACTION_COUNT:
        raise ValueError("C1 action change requires exactly 4 clean and 4 nuisance action bits")
    return int(any(int(a) != int(b) for a, b in zip(clean_actions, nuisance_actions)))


def jaccard(clean_support: list[int], nuisance_support: list[int]) -> float:
    """Jaccard = |A intersection B| / |A union B|; empty-vs-empty counts 1.0."""
    a = set(clean_support)
    b = set(nuisance_support)
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / len(union)


def c1_pair_rationale_jaccard(
    clean_supports: list[list[int]], nuisance_supports: list[list[int]]
) -> float:
    """Mean Jaccard over the 4 actions (per pair)."""
    if len(clean_supports) != ACTION_COUNT or len(nuisance_supports) != ACTION_COUNT:
        raise ValueError("C1 rationale aggregation requires exactly 4 clean and 4 nuisance supports")
    return float(
        sum(
            jaccard(cs, ns)
            for cs, ns in zip(clean_supports, nuisance_supports)
        )
        / ACTION_COUNT
    )


# ---------------------------------------------------------------------------
# S fixture error vector (requirement: S seed / per-world error vector digest).
#   * exact seed namespace:  S_fixture:{world decimal}:{row 4digit zero-padded}
#   * full digest unsigned big-endian mod5  (error_i == 1 iff digest mod 5 == 0)
#   * analytic tie-aware AURC only (no hash jitter, no row order)
# ---------------------------------------------------------------------------
S_FIXTURE_NAMESPACE_FMT = f"{NAMESPACE}:S_fixture:{{world_decimal}}:{{row_4digit}}"
S_DIGEST_BIG_ENDIAN_MOD = 5


def s_fixture_seed_bytes(world_index: int, row: int) -> bytes:
    if not (0 <= world_index < WORLD_COUNT):
        raise ValueError(
            f"S fixture world_index out of bounds 0..{WORLD_COUNT - 1}: {world_index}"
        )
    if not (0 <= row < ROWS_PER_WORLD):
        raise ValueError(
            f"S fixture row out of bounds 0..{ROWS_PER_WORLD - 1}: {row}"
        )
    return f"{NAMESPACE}:S_fixture:{world_index}:{row:04d}".encode("utf-8")


def s_error_index(world_index: int, row: int) -> int:
    """Full SHA-256 digest interpreted as unsigned big-endian, mod 5."""
    if not (0 <= world_index < WORLD_COUNT):
        raise ValueError(
            f"S fixture world_index out of bounds 0..{WORLD_COUNT - 1}: {world_index}"
        )
    if not (0 <= row < ROWS_PER_WORLD):
        raise ValueError(
            f"S fixture row out of bounds 0..{ROWS_PER_WORLD - 1}: {row}"
        )
    digest = hashlib.sha256(s_fixture_seed_bytes(world_index, row)).digest()
    return int.from_bytes(digest, "big") % S_DIGEST_BIG_ENDIAN_MOD


def s_error_flag(world_index: int, row: int) -> int:
    if not (0 <= world_index < WORLD_COUNT):
        raise ValueError(
            f"S fixture world_index out of bounds 0..{WORLD_COUNT - 1}: {world_index}"
        )
    if not (0 <= row < ROWS_PER_WORLD):
        raise ValueError(
            f"S fixture row out of bounds 0..{ROWS_PER_WORLD - 1}: {row}"
        )
    return 1 if s_error_index(world_index, row) == 0 else 0


def s_build_world_error_vector(
    world_index: int, rows: int = ROWS_PER_WORLD
) -> dict[str, Any]:
    """Per-world error vector (error_0..error_{rows-1}) and its digest builder."""
    if not (0 <= world_index < WORLD_COUNT):
        raise ValueError(
            f"S fixture world_index out of bounds 0..{WORLD_COUNT - 1}: {world_index}"
        )
    if not (0 < rows <= ROWS_PER_WORLD):
        raise ValueError(f"S fixture row span out of bounds 1..{ROWS_PER_WORLD}: {rows}")
    vec = [s_error_flag(world_index, r) for r in range(rows)]
    payload = b"".join(bytes([int(v)]) for v in vec)
    return {
        "world_index": world_index,
        "error_vector": vec,
        "error_count": sum(1 for v in vec if v),
        "byte_sha256": hashlib.sha256(payload).hexdigest().upper(),
        "expected_error_fraction": "expected probability is exactly 0.2 = 5^-1 per row under the hash rule, deterministic no resampling, but the observed deterministic sample error count / proportion is not forced to equal 0.2",
        "au_intake": "analytic tie-aware AURC only; hash jitter and row order never enter it",
    }


def s_fixture_manifest() -> dict[str, Any]:
    """Exactly 32 S fixture records (world_index, error_count, byte_sha256) and the
    global SHA over ``canonical_json_bytes(records)``."""
    records = [
        {
            "world_index": w,
            "error_count": s_build_world_error_vector(w)["error_count"],
            "byte_sha256": s_build_world_error_vector(w)["byte_sha256"],
        }
        for w in range(WORLD_COUNT)
    ]
    if len(records) != WORLD_COUNT:
        raise ValueError(
            f"s_fixture_manifest must contain exactly {WORLD_COUNT} records"
        )
    for w, record in enumerate(records):
        if record["world_index"] != w or not isinstance(record["error_count"], int) or not isinstance(record["byte_sha256"], str):
            raise ValueError(f"s_fixture_manifest record malformed for world {w}")
    return {
        "records": records,
        "record_count": len(records),
        "global_sha256": hashlib.sha256(canonical_json_bytes(records)).hexdigest().upper(),
    }


def build_s_fixture_contract() -> dict[str, Any]:
    """Freeze the full S fixture machine-readable contract.

    Result-blind: it fixes the absolute example seed bytes, the payload
    framing, the digest rule, the analytic tie-aware AURC semantics, and the
    embedded 32-record manifest (no observed sample output enters it).
    """
    manifest = s_fixture_manifest()
    example_seed = s_fixture_seed_bytes(0, 0).decode("utf-8")
    return {
        "example_coordinates": {"world_index": 0, "row": 0},
        "example_seed_utf8": example_seed,
        "seed_string_format": S_FIXTURE_NAMESPACE_FMT,
        "seed_encoding": "UTF-8",
        "payload": "1024 one-byte flags ascending over canonical rows 0..1023 (the i-th flag is error_i as a single byte 0 or 1)",
        "payload_byte_count": ROWS_PER_WORLD,
        "digest_rule": "full SHA-256 digest unsigned big-endian mod 5",
        "error_rule": "error_i = 1 iff (full SHA-256 digest unsigned big-endian mod 5) == 0",
        "expected_probability": 0.2,
        "probability_semantics": "expected analytic probability 0.2 = 1/5 per row (deterministic; not an exact sample proportion)",
        "action_semantics": "action0 XOR error: on error rows action 0 is flipped (XOR 1) and the other three actions are unchanged",
        "risk_semantics": "risk = error (each row's risk flag equals its error flag)",
        "analytic_tie_aurc": (
            "group rows by exact scalar confidence descending; for a tie group of size m "
            "with z errors, after p earlier rows with u errors, the expected risk at "
            "within-group position k=1..m is (u+k*z/m)/(p+k); AURC = arithmetic mean of "
            "these expected risks over all N=1024 accepted-row positions; S = -AURC"
        ),
        "au_intake": "analytic tie-aware AURC only; no hash jitter, no row order",
        "manifest": manifest,
    }


# ---------------------------------------------------------------------------
# Generator hash ordering / exact result-blind generator contract.
#   * Deterministic and result-blind; nothing is resampled and no new
#     v3_hash_order seed family is introduced.
#   * Each generator's frozen hash_seeds prefixes are read from
#     design['generators']; '{world_index}' is substituted with the plain
#     decimal world index.
#   * Feature hashing candidate bytes: UTF-8 seed_prefix + ':' + actual
#     feature ID decimal (no padding); SHA-256 digest bytes ascending; an
#     exact digest collision is broken by ascending actual feature ID.
#   * Ordering scope is world-global (not per-row), then candidate-subset
#     slicing. Memberships are length-10 bit vectors and scores length-10
#     vectors over actual feature IDs 0..9.
# ---------------------------------------------------------------------------
GENERATOR_SCORES = {
    "oracle_causal": 1.0,
    "sparse_causal": 0.8,
    "diffuse_causal_plus_decoy": 0.6,
    "proxy_shortcut": 0.4,
    "random_matched_sparsity": 0.2,
    "anti_causal_adversarial": 0.0,
}

GENERATOR_ORDER = tuple(GENERATOR_SCORES)

# Frozen manipulation order (the V2 dict insertion order, byte-for-byte), reused
# for the raw-cell manifest enumeration axis and exported as a V3 contract.
MANIPULATION_ORDER = tuple(MANIPULATIONS)

ACTION_SEMANTICS = {
    "oracle_causal": "action = exact ground-truth causal action vector (truth)",
    "sparse_causal": "action = exact ground-truth causal action vector (truth)",
    "diffuse_causal_plus_decoy": "action = exact ground-truth causal action vector (truth)",
    "proxy_shortcut": "action = exact ground-truth causal action vector (truth)",
    "random_matched_sparsity": "action = exact V2 random action seed semantics: per action a and row i predict truth XOR (SHA256(generator action seed:world:i:a) least-significant bit)",
    "anti_causal_adversarial": "action = bitwise complement of the exact ground-truth causal action vector",
}


def _generator_seed(
    generators: dict[str, Any], name: str, seed_key: str, world_index: int
) -> str:
    seeds = generators.get(name, {}).get("hash_seeds")
    if not isinstance(seeds, dict) or seed_key not in seeds:
        raise ValueError(f"generator {name!r} must freeze hash_seed {seed_key!r}")
    template = seeds[seed_key]
    if not isinstance(template, str) or "{world_index}" not in template:
        raise ValueError(
            f"generator {name!r} seed {seed_key!r} must carry a {{world_index}} placeholder"
        )
    return template.format(world_index=world_index)


def _feature_membership(ordered: list[int]) -> list[int]:
    return [1 if f in set(ordered) else 0 for f in range(FEATURE_COUNT)]


def _feature_scores(scored: dict[int, float]) -> list[float]:
    return [scored.get(f, 0.0) for f in range(FEATURE_COUNT)]


def _generator_cell(
    generators: dict[str, Any],
    world: dict[str, Any],
    world_index: int,
    generator: str,
    support: list[int],
) -> tuple[list[int], list[int], list[float]]:
    """Return (ordered_features, membership, score_vector) for one (world, action)."""
    if not isinstance(support, list) or not support:
        raise ValueError(
            f"action support must be a non-empty feature-id list for world {world_index!r} "
            f"generator {generator!r}"
        )
    if generator == "oracle_causal":
        ordered = sorted(support)
        scored = {f: 1.0 - r / 10 for r, f in enumerate(ordered)}
    elif generator == "sparse_causal":
        seed = _generator_seed(generators, generator, "rationale", world_index)
        ordered_all = hash_order_ascending(seed, support)
        k = int(math.ceil(len(support) / 2))
        ordered = ordered_all[:k]
        scored = {f: 1.0 - r / 10 for r, f in enumerate(ordered)}
    elif generator == "diffuse_causal_plus_decoy":
        seed = _generator_seed(generators, generator, "decoy_order", world_index)
        roles = world["feature_roles"]
        causal = sorted(roles["causal"])  # all four world causal role IDs ascending
        proxy = hash_order_ascending(seed, roles["proxy"])
        nuisance = hash_order_ascending(seed, roles["nuisance"])
        ordered = causal + proxy + nuisance
        if len(set(ordered)) != FEATURE_COUNT or len(ordered) != FEATURE_COUNT:
            raise ValueError(
                f"diffuse generator ordered features must cover all 10 exactly once for "
                f"world {world_index!r}"
            )
        scored = {}
        for r, f in enumerate(causal):
            scored[f] = 1.0 - r / 100
        for r, f in enumerate(proxy):
            scored[f] = 0.6 - r / 100
        for r, f in enumerate(nuisance):
            scored[f] = 0.2 - r / 100
    elif generator == "proxy_shortcut":
        causal = sorted(support)
        seen: set[int] = set()
        ordered = []
        for c in causal:
            p = world["proxy_partners"][str(c)]
            if p not in seen:
                seen.add(p)
                ordered.append(p)
        scored = {f: 1.0 - r / 10 for r, f in enumerate(ordered)}
    elif generator == "random_matched_sparsity":
        seed = _generator_seed(generators, generator, "selection", world_index)
        ordered_all = hash_order_ascending(seed, list(range(FEATURE_COUNT)))
        ordered = ordered_all[: len(support)]
        scored = {f: 1.0 - r / 10 for r, f in enumerate(ordered)}
    elif generator == "anti_causal_adversarial":
        seed = _generator_seed(generators, generator, "noncausal_order", world_index)
        decoy_unique = sorted(set(world["decoy_features"]))
        noncausal = hash_order_ascending(seed, decoy_unique)
        causal = sorted(world["feature_roles"]["causal"])  # all four world causal role IDs ascending
        ordered = noncausal + causal
        if len(set(ordered)) != FEATURE_COUNT or len(ordered) != FEATURE_COUNT:
            raise ValueError(
                f"anti generator ordered features must cover all 10 exactly once for "
                f"world {world_index!r}"
            )
        scored = {}
        for r, f in enumerate(noncausal):
            scored[f] = 1.0 - r / 20
        for r, f in enumerate(causal):
            scored[f] = 0.2 - r / 100
    else:
        raise ValueError(f"unknown frozen generator {generator!r}")
    membership = _feature_membership(ordered)
    score_vector = _feature_scores(scored)
    if len(membership) != FEATURE_COUNT or len(score_vector) != FEATURE_COUNT:
        raise ValueError(
            f"membership and score vectors must have length {FEATURE_COUNT} for world "
            f"{world_index!r} generator {generator!r}"
        )
    return ordered, membership, score_vector


def build_generator_contract(design: dict[str, Any]) -> dict[str, Any]:
    """Exact result-blind generator hash-ordering contract.

    Reads the frozen ``hash_seeds`` prefixes from ``design['generators']`` and the
    frozen worlds from ``design['worlds']``.  For each world and each of the four
    action supports it computes the exact ordered features, length-10 membership
    bit vector, and length-10 score vector, records the SHA-256 of the canonical
    JSON bytes of each record, and embeds all ``world_00`` records plus a global
    golden manifest SHA over all canonical records.

    All checks use explicit ValueError (never assert).
    """
    if not isinstance(design, dict):
        raise ValueError("build_generator_contract requires the design dict")
    if "generators" not in design or "worlds" not in design:
        raise ValueError("design must carry frozen 'generators' and 'worlds'")
    generators = design["generators"]
    worlds = design["worlds"]
    if not isinstance(worlds, list) or not worlds:
        raise ValueError("design must freeze a non-empty worlds list")
    if not isinstance(generators, dict) or set(generators) != set(GENERATOR_ORDER):
        raise ValueError(
            "design generator set must equal the frozen generator vocabulary "
            "(validate by set equality only, never by dict iteration order)"
        )
    raw_records: list[dict[str, Any]] = []
    for world_index, world in enumerate(worlds):
        supports = world.get("action_rationale_supports")
        if not isinstance(supports, list) or len(supports) != 4:
            raise ValueError(
                f"world must freeze exactly four action rationale supports (got world_index {world_index!r})"
            )
        for generator in GENERATOR_ORDER:
            for action in range(4):
                ordered, membership, score_vector = _generator_cell(
                    generators, world, world_index, generator, supports[action]
                )
                record = {
                    "world_id": world.get("world_id"),
                    "world_index": world_index,
                    "generator": generator,
                    "action": action,
                    "ordered_features": ordered,
                    "membership": membership,
                    "score_vector": score_vector,
                }
                raw_records.append(record)
    records_with_sha: list[dict[str, Any]] = []
    for record in raw_records:
        digest = hashlib.sha256(canonical_json_bytes(record)).hexdigest().upper()
        records_with_sha.append(dict(record, record_sha256=digest))
    payload = b"".join(canonical_json_bytes(r) for r in raw_records)
    world00 = [r for r in records_with_sha if r["world_index"] == 0]
    if len(world00) != len(generators) * 4:
        raise ValueError("world_00 embedding must cover every generator x action")
    return {
        "schema": "arsc-round13-synthetic-mtmm-generator-contract-v3",
        "generator_order": list(GENERATOR_ORDER),
        "action_semantics": dict(ACTION_SEMANTICS),
        "full_feature_generators": ["diffuse_causal_plus_decoy", "anti_causal_adversarial"],
        "full_feature_causal_band": (
            "diffuse_causal_plus_decoy and anti_causal_adversarial use ALL four world "
            "feature_roles.causal IDs ascending for every action (the 'entire feature set "
            "participates'), with all proxy/nuisance decoys; their ordered features are exactly "
            "all 10 unique feature IDs. Oracle/sparse/proxy/random per-action support rules are unchanged."
        ),
        "ordering_scope": "world-global (not per-row), then candidate subset slicing",
        "membership": "feature membership bit vector (length 10) over actual feature IDs 0..9",
        "score_vector_length": 10,
        "candidate_rule": "UTF-8 seed_prefix + ':' + actual feature ID decimal (no padding); SHA-256 digest bytes ascending; exact digest collision broken by ascending actual feature ID",
        "no_new_seed_family": True,
        "world_00": {
            "world_id": world00[0]["world_id"] if world00 else None,
            "world_index": 0,
            "records": world00,
        },
        "record_count": len(raw_records),
        "golden_manifest_sha256": hashlib.sha256(payload).hexdigest().upper(),
    }


# ---------------------------------------------------------------------------
# R tensor (requirement: R tensor / support_f1).
#   Each experiment cell carries per-cell prediction/truth tensors of shape
#   [1024, 4, 10] (row, action, feature).  TP/FP/FN are aggregated over the 1024
#   rows for each action-feature, then the mean over the 40 cells is taken; zero
#   denominator -> 1; support_f1 identical to R.  There is no world dimension
#   inside a cell (the authoritative evaluation R_formula is per-cell).
# ---------------------------------------------------------------------------
ACTION_COUNT = 4
R_MEAN_CELLS = ACTION_COUNT * FEATURE_COUNT  # 40
R_TENSOR_SHAPE = [ROWS_PER_WORLD, ACTION_COUNT, FEATURE_COUNT]  # per-cell [1024,4,10]


def r_cell_f1(tp: int, fp: int, fn: int) -> float:
    """2*TP/(2*TP+FP+FN); zero denominator -> 1.0."""
    denom = 2 * tp + fp + fn
    return 1.0 if denom == 0 else (2.0 * tp / denom)


def r_tensor_contract() -> dict[str, Any]:
    return {
        # Return a fresh list so a caller mutating contract['r_tensor']['shape']
        # cannot corrupt the module-level R_TENSOR_SHAPE constant.
        "shape": list(R_TENSOR_SHAPE),
        "dimension_names": ["row", "action", "feature"],
        "per_cell": [
            "each experiment cell holds prediction/truth tensors of shape [1024,4,10] (row, action, feature)",
            "TP/FP/FN are aggregated over the 1024 rows for each action-feature, then the mean over the 40 cells is taken",
            "no world dimension exists inside a cell",
        ],
        "per_action_feature_counts": "TP/FP/FN aggregated over the 1024 rows per action-feature (40 cells); mean over the 40 cells",
        "mean_cells": R_MEAN_CELLS,
        "zero_denominator": 1.0,
        "support_f1_identical": "support_f1 uses exactly R_formula semantics (identical to R) with the same zero-denominator rule",
    }


# ---------------------------------------------------------------------------
# Deterministic world bootstrap (requirement: bootstrap manifest / shuffle).
#   * index digest rule: namespace:bootstrap:20260813:{replicate:05d}:{position:02d}
#   * full digest unsigned big-endian mod32  (world index)
#   * manifest SHA helper; deterministic hash-sorted shuffle key/algorithm
#   * exact finite/tie/quantile rules (linear quantile, ties averaged; no NaN)
# ---------------------------------------------------------------------------
BOOTSTRAP_SEED_FMT = f"{NAMESPACE}:bootstrap:{BOOTSTRAP_SEED}:{{replicate:05d}}:{{position:02d}}"


def bootstrap_replicate_world(replicate: int, position: int) -> int:
    """Deterministic world index drawn for one shared-bootstrap cell.

    Explicit contract bounds (never assert):
      * ``replicate`` must be a non-bool int in 0..BOOTSTRAP_DRAWS-1 (0..9999);
      * ``position`` must be a non-bool int in 0..WORLD_COUNT-1 (0..31).

    Index rule: ``SHA256(NAMESPACE:bootstrap:BOOTSTRAP_SEED:{replicate:05d}:{position:02d})``
    taken as a full digests as big-endian integer mod WORLD_COUNT.  No RNG and no
    numpy are involved; the result is identical on every interpreter/version.
    """
    if isinstance(replicate, bool) or not isinstance(replicate, int):
        raise ValueError(
            f"bootstrap replicate must be a non-bool int, got {replicate!r}"
        )
    if not (0 <= replicate < BOOTSTRAP_DRAWS):
        raise ValueError(
            f"bootstrap replicate must be in 0..{BOOTSTRAP_DRAWS - 1}, got {replicate}"
        )
    if isinstance(position, bool) or not isinstance(position, int):
        raise ValueError(
            f"bootstrap position must be a non-bool int, got {position!r}"
        )
    if not (0 <= position < WORLD_COUNT):
        raise ValueError(
            f"bootstrap position must be in 0..{WORLD_COUNT - 1}, got {position}"
        )
    seed = BOOTSTRAP_SEED_FMT.format(replicate=replicate, position=position)
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return int.from_bytes(digest, "big") % WORLD_COUNT


def bootstrap_example_seed_bytes() -> bytes:
    """UTF-8 seed bytes for replicate 0, position 0 (the canonical example)."""
    return BOOTSTRAP_SEED_FMT.format(replicate=0, position=0).encode("utf-8")


def bootstrap_example_replicate0_position0() -> int:
    """Exact bootstrap world index for replicate 0, position 0."""
    return bootstrap_replicate_world(0, 0)


def bootstrap_payload_bytes(replicates: int = BOOTSTRAP_DRAWS) -> bytes:
    """Exact serialized bootstrap payload.

    ``BOOTSTRAP_DRAWS`` (10000) replicate rows x ``WORLD_COUNT`` (32) positions
    in **replicate-major** order; each entry is the world index encoded as an
    unsigned 4-byte big-endian integer.  The manifest SHA-256 is taken over this
    exact byte payload.
    """
    return b"".join(
        bootstrap_replicate_world(r, position).to_bytes(4, "big")
        for r in range(replicates)
        for position in range(WORLD_COUNT)
    )


# ---------------------------------------------------------------------------
# Deterministic shuffle permutations (requirement: shuffle manifest).
#   * common generator set = the five GENERATOR_ORDER members excluding
#     anti_causal_adversarial (anti_causal_adversarial is never a matched cell)
#   * matched cells: 32 bootstrap positions x 5 common generators x 4 doses
#     (0.0, 0.25, 0.75, 1.0) = 640 cells; dose 0.5 is excluded
#   * canonical matched-cell order (frozen): bootstrap_position p in 0..31
#     (p stays identity even when the world repeats), then common generators in
#     GENERATOR_ORDER, then dose ascending; source_world = bootstrap_replicate_world(r,p)
#   * exact matched_cell_id:
#       {bootstrap_position:02d}:{source_world:02d}:{generator}:{dose:.2f}
#   * per bootstrap replicate r in 0..9999 and permutation draw q in 0..9999:
#       seed = NAMESPACE:shuffle:{r:05d}:{q:05d}
#       candidate key = seed + ':' + matched_cell_id; sort the full SHA-256
#       digest bytes ascending (interpreted unsigned big-endian); an exact
#       digest collision is broken by ascending canonical cell index
#   * assignment orientation: permuted_label[target_j] = canonical_label[order[j]]
#     where order[j] is the canonical cell index at sorted position j; the one
#     same permutation is synchronously applied to A/R/S/C1 and both C1
#     components; the family is absent from the permutation identity
#   * application order: bootstrap resampling first; then the permutation
#   * the full 10000x10000x640 universe is never materialized or hashed during
#     import/build; golden evidence is frozen for r=0 only (canonical skeleton
#     SHA including records and hashes of the permutation payloads for the fixed
#     small draw set q=0,1,9999); the total counts are nevertheless frozen
#   * no library RNG / no numpy / no version-dependent sort
# ---------------------------------------------------------------------------
COMMON_GENERATORS: tuple[str, ...] = tuple(
    g for g in GENERATOR_ORDER if g != "anti_causal_adversarial"
)
MATCHED_DOSES: tuple[float, ...] = (0.0, 0.25, 0.75, 1.0)
MATCHED_CELL_COUNT = WORLD_COUNT * len(COMMON_GENERATORS) * len(MATCHED_DOSES)  # 640
# 10000 permutation draws q per bootstrap replicate r (draws are indexed q, not
# by a cell position).
SHUFFLE_PERMUTATIONS_PER_BOOTSTRAP = BOOTSTRAP_DRAWS
SHUFFLE_KEY_FMT = f"{NAMESPACE}:shuffle:{{r:05d}}:{{q:05d}}"


def matched_cell_id(
    bootstrap_position: int, source_world: int, generator: str, dose: float
) -> str:
    """Exact canonical matched-cell ID (no NAMESPACE prefix)."""
    return f"{bootstrap_position:02d}:{source_world:02d}:{generator}:{dose:.2f}"


def canonical_matched_cells(replicate: int) -> list[dict[str, Any]]:
    """Canonical matched-cell records for bootstrap replicate ``replicate``.

    Contract bounds (never assert):
      * ``replicate`` must be a non-bool int in 0..BOOTSTRAP_DRAWS-1.

    Order is frozen: bootstrap position p in 0..31 (``p`` stays identity even
    when the world repeats because the position is not canonicalized by world),
    then common generators in ``GENERATOR_ORDER``, then dose ascending over
    ``MATCHED_DOSES`` (0.0, 0.25, 0.75, 1.0).  ``source_world`` equals
    ``bootstrap_replicate_world(replicate, p)``.  Exactly ``MATCHED_CELL_COUNT``
    (640) records are returned.  Each record explicitly carries the integer
    ``canonical_label``, which is 1 for the low (non-corrupted) doses 0.0 and
    0.25 and 0 for the high doses 0.75 and 1.0.  Because the label rule is a
    function of the exact frozen dose, the derivation yields exactly 320 ones
    and 320 zeros across the 640 canonical records.
    """
    if isinstance(replicate, bool) or not isinstance(replicate, int):
        raise ValueError(f"replicate must be a non-bool int, got {replicate!r}")
    if not (0 <= replicate < BOOTSTRAP_DRAWS):
        raise ValueError(
            f"replicate must be in 0..{BOOTSTRAP_DRAWS - 1}, got {replicate}"
        )
    records: list[dict[str, Any]] = []
    for bootstrap_position in range(WORLD_COUNT):
        source_world = bootstrap_replicate_world(replicate, bootstrap_position)
        for generator in COMMON_GENERATORS:
            for dose in MATCHED_DOSES:
                # Exact label rule: integer 1 for dose 0.0 or 0.25, integer 0
                # for dose 0.75 or 1.0.  Derived only from the frozen
                # MATCHED_DOSES order, so exactly half the canonical records
                # carry canonical_label 1 and exactly half carry 0.
                canonical_label = (
                    1 if dose in (MATCHED_DOSES[0], MATCHED_DOSES[1]) else 0
                )
                records.append(
                    {
                        "bootstrap_position": bootstrap_position,
                        "source_world": source_world,
                        "generator": generator,
                        "dose": dose,
                        "canonical_label": canonical_label,
                        "matched_cell_id": matched_cell_id(
                            bootstrap_position, source_world, generator, dose
                        ),
                    }
                )
    if len(records) != MATCHED_CELL_COUNT:
        raise ValueError(
            f"matched cell manifest must contain exactly {MATCHED_CELL_COUNT} cells, "
            f"got {len(records)}"
        )
    return records


def shuffle_permutation(replicate: int, permutation_draw: int) -> list[int]:
    """Deterministic permutation of the ``MATCHED_CELL_COUNT`` (640) canonical
    matched-cell indices for bootstrap replicate ``replicate`` and permutation
    draw ``permutation_draw``.

    Contract bounds (never assert):
      * ``replicate`` must be a non-bool int in 0..BOOTSTRAP_DRAWS-1;
      * ``permutation_draw`` must be a non-bool int in
        0..SHUFFLE_PERMUTATIONS_PER_BOOTSTRAP-1 (0..9999).

    Seed = ``NAMESPACE:shuffle:{replicate:05d}:{permutation_draw:05d}``; for
    every canonical cell the candidate key is ``seed + ':' + matched_cell_id``.
    Cells are sorted by the full SHA-256 digest bytes ascending (interpreted
    unsigned big-endian); an exact digest collision is broken by ascending
    canonical cell index.  The returned list ``order`` gives the canonical cell
    index at each sorted position j, with the frozen assignment orientation
    ``permuted_label[target_j] = canonical_label[order[j]]``.
    """
    if isinstance(replicate, bool) or not isinstance(replicate, int):
        raise ValueError(
            f"shuffle replicate must be a non-bool int, got {replicate!r}"
        )
    if not (0 <= replicate < BOOTSTRAP_DRAWS):
        raise ValueError(
            f"shuffle replicate must be in 0..{BOOTSTRAP_DRAWS - 1}, got {replicate}"
        )
    if isinstance(permutation_draw, bool) or not isinstance(permutation_draw, int):
        raise ValueError(
            f"permutation draw must be a non-bool int, got {permutation_draw!r}"
        )
    if not (0 <= permutation_draw < SHUFFLE_PERMUTATIONS_PER_BOOTSTRAP):
        raise ValueError(
            f"permutation draw must be in "
            f"0..{SHUFFLE_PERMUTATIONS_PER_BOOTSTRAP - 1}, got {permutation_draw}"
        )
    seed = SHUFFLE_KEY_FMT.format(r=replicate, q=permutation_draw)
    records = canonical_matched_cells(replicate)
    keyed = sorted(
        (
            int.from_bytes(_digest(f"{seed}:{rec['matched_cell_id']}"), "big"),
            index,
        )
        for index, rec in enumerate(records)
    )
    return [index for _digest_int, index in keyed]


def _permutation_payload_bytes(permutation: list[int]) -> bytes:
    """Exact serialized 640-index payload: each canonical cell index as an
    unsigned 4-byte big-endian integer, concatenated in sorted-position order."""
    return b"".join(index.to_bytes(4, "big") for index in permutation)


def shuffle_golden_evidence() -> dict[str, Any]:
    """Deterministic golden evidence for the shuffle algorithm.

    Frozen at r=0 only (a small fixed set of permutation draws q=0,1,9999, each
    hashing its 640-index payload).  The full 10000x10000x640 universe is never
    materialized during import/build; the total counts are nevertheless frozen
    in the calling contract.

    Fail-closed (ValueError, never assert): before any hashing, the canonical
    matched-cell record count must be exactly 640 and the canonical_label counts
    must be exactly 320 ones and 320 zeros.  These verify the exact label rule
    (integer 1 for dose 0.0 or 0.25, integer 0 for dose 0.75 or 1.0) so the
    ``canonical_skeleton_sha256`` hash below binds the complete 640-value label
    vector.
    """
    records = canonical_matched_cells(0)
    if not isinstance(records, list) or len(records) != MATCHED_CELL_COUNT:
        raise ValueError(
            f"golden shuffle evidence must have exactly {MATCHED_CELL_COUNT} "
            f"canonical matched cells, got {len(records)}"
        )
    label_values = [rec.get("canonical_label") for rec in records]
    ones = sum(1 for v in label_values if v == 1)
    zeros = sum(1 for v in label_values if v == 0)
    if ones != MATCHED_CELL_COUNT // 2 or zeros != MATCHED_CELL_COUNT // 2:
        raise ValueError(
            f"golden shuffle evidence canonical_label counts must be exactly "
            f"{MATCHED_CELL_COUNT // 2} ones and {MATCHED_CELL_COUNT // 2} zeros, "
            f"got {ones} ones and {zeros} zeros"
        )
    draws = (0, 1, 9999)
    return {
        "replicate": 0,
        "matched_cell_count": MATCHED_CELL_COUNT,
        "canonical_skeleton_sha256": hashlib.sha256(
            canonical_json_bytes(records)
        ).hexdigest().upper(),
        "permutation_draws": list(draws),
        "permutation_payload_sha256": [
            hashlib.sha256(_permutation_payload_bytes(shuffle_permutation(0, q)))
            .hexdigest()
            .upper()
            for q in draws
        ],
        "assignment_orientation": (
            "permuted_label[target_j] = canonical_label[order[j]]"
        ),
        "family_absent_from_permutation_identity": True,
        "applied_synchronously_to": ["A", "R", "S", "C1", "C1_components"],
        "dose_0_5_excluded": True,
        "bootstrap_first": True,
    }


def hash_sorted_shuffle(key: str, size: int) -> list[int]:
    """Deterministic hash-sorted permutation: sort values by SHA-256 digest of
    'key:value' ascending; collisions (impossible for distinct values) broken by
    ascending value.  Used for bootstrap permutation labels."""
    return hash_order_ascending(key, list(range(size)))


def bootstrap_manifest_sha(replicates: int = BOOTSTRAP_DRAWS) -> str:
    """SHA-256 (uppercase hex) over the exact serialized bootstrap payload.

    Payload = BOOTSTRAP_DRAWS x WORLD_COUNT world indices, replicate-major,
    each unsigned 4-byte big-endian (i.e. ``bootstrap_payload_bytes``).
    """
    if isinstance(replicates, bool) or not isinstance(replicates, int):
        raise ValueError("replicates must be a non-bool int")
    if not (0 < replicates <= BOOTSTRAP_DRAWS):
        raise ValueError(
            f"replicates must be in 1..{BOOTSTRAP_DRAWS}, got {replicates}"
        )
    return hashlib.sha256(bootstrap_payload_bytes(replicates)).hexdigest().upper()


def bootstrap_manifest(replicates: int = BOOTSTRAP_DRAWS) -> list[list[int]]:
    return [
        [bootstrap_replicate_world(r, position) for position in range(WORLD_COUNT)]
        for r in range(replicates)
    ]


BOOTSTRAP_QUANTILE_RULES = {
    "seed": BOOTSTRAP_SEED,
    "draws": BOOTSTRAP_DRAWS,
    "unit": "world",
    "shared_draws": True,
    "index_digest_rule": BOOTSTRAP_SEED_FMT,
    "index_mod": "full SHA-256 digest unsigned big-endian mod 32 -> exact world index",
    "shuffle_algorithm": (
        "deterministic 640-cell permutation per bootstrap replicate r: for "
        "permutation draw q the seed is NAMESPACE:shuffle:{r:05d}:{q:05d}; "
        "candidate key = seed + ':' + matched_cell_id; sort the full SHA-256 "
        "digest bytes ascending (exact digest collision broken by ascending "
        "canonical cell index); assignment "
        "permuted_label[target_j] = canonical_label[order[j]]; one same "
        "permutation applied synchronously to A/R/S/C1 and both C1 components",
    ),
    "shuffle_permutations_per_bootstrap": SHUFFLE_PERMUTATIONS_PER_BOOTSTRAP,
    "matched_cell_count": MATCHED_CELL_COUNT,
    "matched_doses": list(MATCHED_DOSES),
    "bootstrap_first": True,
    "quantile_method": "numpy.quantile(method='linear') over the finite shared world-bootstrap replicate distribution",
    "finite_rule": "any non-finite bootstrap quantile aborts as IMPLEMENTATION_FAILURE",
    "tie_rule": "within-group ties are averaged analytically (never resampled hash jitter)",
    "dose_0_5_excluded": True,
}


def build_resampling_contract() -> dict[str, Any]:
    """Build the exact machine-readable deterministic resampling contract.

    Freezes, as pure byte-level spec (no numpy, no library RNG, no version
    dependence), both the shared world-bootstrap manifest and the paired
    shuffle permutations, together with the exact quantile and metric
    semantics:
      * quantile lower probability .0125 and upper .9875 are computed on the
        finite shared-bootstrap replicate distribution algorithmically as
        linear interpolation between adjacent sorted finite values (not a
        numpy-version-dependent call);
      * a constant input series defines Kendall tau-b as 0;
      * AUROC uses exact midrank ties; a degenerate (uncomputable) class makes
        the metric uncomputable => IMPLEMENTATION_FAILURE;
      * NaN / non-finite values are forbidden everywhere.
    """
    example_seed = bootstrap_example_seed_bytes()
    return {
        "schema": "arsc-round13-synthetic-mtmm-resampling-contract-v3",
        "bootstrap": {
            "seed": BOOTSTRAP_SEED,
            "draws": BOOTSTRAP_DRAWS,
            "unit": "world",
            "shared_draws": True,
            "replicate_bounds": f"replicate r in 0..{BOOTSTRAP_DRAWS - 1}; position in 0..{WORLD_COUNT - 1}",
            "index_digest_rule": BOOTSTRAP_SEED_FMT,
            "index_mod": "full SHA-256 digest unsigned big-endian mod 32 -> exact world index",
            "payload": {
                "replicate_major": True,
                "replicates": BOOTSTRAP_DRAWS,
                "positions_per_replicate": WORLD_COUNT,
                "entry_encoding": "world index unsigned 4-byte big-endian",
                "total_entries": BOOTSTRAP_DRAWS * WORLD_COUNT,
                "example_replicate": 0,
                "example_position": 0,
                "example_seed_utf8": example_seed.decode("utf-8"),
                "example_seed_bytes": list(example_seed),
                "example_index": bootstrap_example_replicate0_position0(),
            },
            "manifest_sha256": bootstrap_manifest_sha(),
        },
        "shuffle": {
            "bootstrap_replicates": BOOTSTRAP_DRAWS,
            "permutations_per_bootstrap": SHUFFLE_PERMUTATIONS_PER_BOOTSTRAP,
            "key_format": SHUFFLE_KEY_FMT,
            "matched_cell_count": MATCHED_CELL_COUNT,
            "matched_doses": list(MATCHED_DOSES),
            "common_generators": list(COMMON_GENERATORS),
            "canonical_order": "bootstrap_position 0..31 -> common generator (GENERATOR_ORDER) -> dose [0.0,0.25,0.75,1.0]",
            "canonical_label_rule": "canonical_label is the integer 1 for the low doses dose in [0.0, 0.25] and the integer 0 for the high doses dose in [0.75, 1.0]; each record in canonical_matched_cells carries this exact integer",
            "count_labels_ones": len([d for d in MATCHED_DOSES if d in (MATCHED_DOSES[0], MATCHED_DOSES[1])]) * WORLD_COUNT * len(COMMON_GENERATORS),
            "count_labels_zeros": len([d for d in MATCHED_DOSES if d not in (MATCHED_DOSES[0], MATCHED_DOSES[1])]) * WORLD_COUNT * len(COMMON_GENERATORS),
            "digest_order": "full SHA-256 digest bytes ascending unsigned big-endian over seed + ':' + matched_cell_id; exact digest collision broken by ascending canonical cell index",
            "assignment_orientation": "permuted_label[target_j] = canonical_label[order[j]]",
            "synchronously_applied_to": ["A", "R", "S", "C1", "C1_components"],
            "family_absent_from_permutation_identity": True,
            "application": "bootstrap resampling is applied first; then the permutation reassigns the high/low label vector within the bootstrap-resampled matched cells in canonical matched-cell order; dose 0.5 excluded",
            "entry_encoding": "canonical matched-cell index unsigned 4-byte big-endian",
            "golden_evidence": shuffle_golden_evidence(),
        },
        "quantile": {
            "lower_probability": 0.0125,
            "upper_probability": 0.9875,
            "method_algorithmic": "linear interpolation between adjacent sorted finite values of the finite shared world-bootstrap replicate distribution; specified algorithmically, not as a numpy-version-dependent call",
            "finite_only": True,
            "nonfinite_aborts": "IMPLEMENTATION_FAILURE",
        },
        "metrics": {
            "kendall_constant_defined": 0,
            "auroc_tie_rule": "exact midrank ties",
            "auroc_degenerate_class": "uncomputable => IMPLEMENTATION_FAILURE",
            "nan_nonfinite_forbidden": True,
        },
    }


# ---------------------------------------------------------------------------
# Exact machine gate contract and evaluator (requirement: exact gate contract;
# IMPLEMENTATION_FAILURE is an infrastructure status, never a third verdict).
#
# Only two scientific verdicts exist (FINAL_VERDICTS); PASS_VERDICT and
# NOT_VALIDATED_VERDICT are per-gate/per-family scientific verdicts.
# IMPLEMENTATION_FAILURE is an infrastructure/implementation status kept separate
# from both.
# ---------------------------------------------------------------------------
PASS_VERDICT = "ROUND13_SYNTHETIC_METRIC_FAMILY_PASS"
NOT_VALIDATED_VERDICT = "ROUND13_SYNTHETIC_METRIC_FAMILY_NOT_VALIDATED"
INFRASTRUCTURE_STATUS = "IMPLEMENTATION_FAILURE"

# Family metric gates: for every family A/R/S/C1 and every reported metric, store
# a ``point`` and a ``corrected_lower`` numeric gate with its exact operator and
# threshold.  Both operator symbols and threshold values are identical across all
# four families.  Threshold values:
#   point           >=  .70 (kendall_tau_b) | .80 (high_low_auroc) | .30 (mtmm_gap)
#   corrected_lower >   .50 (kendall_tau_b) | .70 (high_low_auroc) | .20 (mtmm_gap)
_FAMILY_METRIC_GATES: dict[str, dict[str, tuple[str, float]]] = {
    "kendall_tau_b": {"point": (">=", 0.70), "corrected_lower": (">", 0.50)},
    "high_low_auroc": {"point": (">=", 0.80), "corrected_lower": (">", 0.70)},
    "mtmm_gap": {"point": (">=", 0.30), "corrected_lower": (">", 0.20)},
}

FAMILY_GATE_SPECS: dict[str, dict[str, dict[str, dict[str, Any]]]] = {
    family: {
        metric: {
            gate_op: {
                "kind": "numeric",
                "operator": operator,
                "threshold": threshold,
            }
            for gate_op, (operator, threshold) in metric_gates.items()
        }
        for metric, metric_gates in _FAMILY_METRIC_GATES.items()
    }
    for family in FAMILIES
}

# Global gates: prior-analysis / engineering gates plus completeness and ranking
# report booleans.  ``oracle_destroyed_standardized_difference`` is an engineering
# gate whose numeric failure is IMPLEMENTATION_FAILURE (never a scientific
# verdict).  ``nuisance_shuffle_auroc`` uses a closed interval [0.45, 0.55].
GLOBAL_GATE_SPECS: dict[str, dict[str, Any]] = {
    "nuisance_non_target.corrected_upper": {
        "kind": "numeric",
        "operator": "<",
        "threshold": 0.10,
    },
    "nuisance_shuffle_auroc": {
        "kind": "interval",
        "lower": 0.45,
        "upper": 0.55,
    },
    "lowo_delta_r2.point": {"kind": "numeric", "operator": ">=", "threshold": 0.15},
    "lowo_delta_r2.corrected_lower": {
        "kind": "numeric",
        "operator": ">",
        "threshold": 0.10,
    },
    "oracle_destroyed_standardized_difference": {
        "kind": "numeric",
        "operator": ">=",
        "threshold": 0.50,
        "failure_class": INFRASTRUCTURE_STATUS,
    },
    "completeness.raw_cells": {"kind": "boolean", "expected": True},
    "completeness.matched_cells": {"kind": "boolean", "expected": True},
    "completeness.rankings": {"kind": "boolean", "expected": True},
    "completeness.baselines": {"kind": "boolean", "expected": True},
    "ranking_reports.full_rankings": {"kind": "boolean", "expected": True},
    "ranking_reports.concordance": {"kind": "boolean", "expected": True},
    "ranking_reports.top1_regret": {"kind": "boolean", "expected": True},
    "ranking_reports.reversal_rate": {"kind": "boolean", "expected": True},
}

# Exact ordered gate-ID tuple.  Family gates first (family, then metric, then
# point / corrected_lower), then the global gates in the frozen spec order above.
_FAMILY_GATE_METRICS = ("kendall_tau_b", "high_low_auroc", "mtmm_gap")
_FAMILY_GATE_OPERATORS = ("point", "corrected_lower")

REQUIRED_GATE_IDS: tuple[str, ...] = (
    tuple(
        f"{family}.{metric}.{gate_op}"
        for family in FAMILIES
        for metric in _FAMILY_GATE_METRICS
        for gate_op in _FAMILY_GATE_OPERATORS
    )
    + tuple(GLOBAL_GATE_SPECS)
)


def _gate_spec(gate_id: str) -> dict[str, Any] | None:
    """Resolve the exact spec for a required gate ID, or None if unknown."""
    if gate_id in GLOBAL_GATE_SPECS:
        return GLOBAL_GATE_SPECS[gate_id]
    if "." in gate_id:
        family, metric, gate_op = gate_id.split(".")
        family_spec = FAMILY_GATE_SPECS.get(family)
        if family_spec is not None:
            return family_spec.get(metric, {}).get(gate_op)
    return None


def _numeric_passes(spec: dict[str, Any], value: float) -> bool:
    """Evaluate one numeric/interval gate against an exact finite value."""
    if spec.get("kind") == "interval":
        return spec["lower"] <= value <= spec["upper"]
    operator = spec["operator"]
    threshold = spec["threshold"]
    if operator == ">=":
        return value >= threshold
    if operator == ">":
        return value > threshold
    if operator == "<":
        return value < threshold
    if operator == "<=":
        return value <= threshold
    if operator == "==":
        return value == threshold
    return False


def evaluate_gate_values(values: Any) -> str:
    """Exact evaluator over a gate-values dict.  Returns one of PASS_VERDICT,
    NOT_VALIDATED_VERDICT, or INFRASTRUCTURE_STATUS.

    The evaluator trusts nothing from the caller: no ``passed`` / ``computed`` /
    status flags are read from ``values``; the verdict is recomputed purely from
    the supplied per-gate numeric/boolean values plus the frozen specs.  A value
    container that is not a dict, that has missing or extra gate IDs, that is
    empty, that carries a boolean where a number is required, that carries a
    non-finite or uncomputable marker, or that reports a boolean-false
    completeness/report gate fails as IMPLEMENTATION_FAILURE.  A failed
    ``oracle_destroyed_standardized_difference`` gate is IMPLEMENTATION_FAILURE
    (an engineering gate); an ordinary numeric gate failure is NOT_VALIDATED.
    """
    # Reject non-dict values container.
    if not isinstance(values, dict):
        return INFRASTRUCTURE_STATUS

    # Empty dict must never PASS.
    if not values:
        return INFRASTRUCTURE_STATUS

    # Exact key set (no missing, no extra IDs).
    if set(values) != set(REQUIRED_GATE_IDS):
        return INFRASTRUCTURE_STATUS

    for gate_id in REQUIRED_GATE_IDS:
        value = values[gate_id]
        spec = _gate_spec(gate_id)
        if spec is None:
            return INFRASTRUCTURE_STATUS

        if spec.get("kind") == "boolean":
            # A completeness / ranking-report gate must be exactly True.  Anything
            # else (False, 0/1 numeric, marker, None) is an infrastructure problem.
            if value is not True:
                return INFRASTRUCTURE_STATUS
            continue

        # Numeric / interval gate.  bool is explicitly rejected as a number.
        if isinstance(value, bool):
            return INFRASTRUCTURE_STATUS
        if not isinstance(value, (int, float)):
            # uncomputable marker (None, str, etc.) or wrong type.
            return INFRASTRUCTURE_STATUS
        numeric = float(value)
        if not math.isfinite(numeric):
            return INFRASTRUCTURE_STATUS

        if not _numeric_passes(spec, numeric):
            failure_class = spec.get("failure_class")
            if failure_class is not None:
                return failure_class  # oracle/engineering gate: IMPLEMENTATION_FAILURE
            return NOT_VALIDATED_VERDICT  # ordinary numeric gate failure

    return PASS_VERDICT


def build_gate_contract(values: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the exact machine-readable gate contract.

    Embeds every family and global gate spec, the exact ordered gate-ID tuple,
    the required gate count, and the fixed pass/fail semantics.  If ``values`` is
    supplied it is evaluated with the exact evaluator (PASS iff exact key set and
    all gates pass) and the resulting status is embedded as ``evaluated_status``.
    """
    contract: dict[str, Any] = {
        "schema": "arsc-round13-synthetic-mtmm-gate-contract-v3",
        "pass_rule": (
            "PASS iff the exact required gate key set is present (no missing, no "
            "extra) and every gate passes its exact preregistered bound; non-dict "
            "/ missing / extra / empty, bool-as-number, nonfinite, and "
            "uncomputable markers, boolean-false completeness/report gates, and a "
            "failed oracle_destroyed_standardized_difference gate are "
            "IMPLEMENTATION_FAILURE; an ordinary numeric gate failure is "
            "NOT_VALIDATED.  Empty dict must never PASS."
        ),
        "numeric_failure": NOT_VALIDATED_VERDICT,
        "infrastructure_failure": INFRASTRUCTURE_STATUS,
        "never_a_third_verdict": True,
        "required_gate_ids": list(REQUIRED_GATE_IDS),
        "required_gate_count": len(REQUIRED_GATE_IDS),
        "order_frozen": True,
        "family_gate_specs": copy.deepcopy(FAMILY_GATE_SPECS),
        "global_gate_specs": copy.deepcopy(GLOBAL_GATE_SPECS),
    }
    if values is not None:
        contract["evaluated_status"] = evaluate_gate_values(values)
    return contract


def _boundary_gate_check() -> bool:
    """Pure internal boundary validation (no test file, no output writes)."""
    # No duplicate gate IDs and the exact required count.
    if len(REQUIRED_GATE_IDS) != len(set(REQUIRED_GATE_IDS)):
        raise ValueError("REQUIRED_GATE_IDS contains duplicate gate IDs")
    expected = (
        len(FAMILIES) * len(_FAMILY_GATE_METRICS) * len(_FAMILY_GATE_OPERATORS)
        + len(GLOBAL_GATE_SPECS)
    )
    if len(REQUIRED_GATE_IDS) != expected:
        raise ValueError(
            f"REQUIRED_GATE_IDS has {len(REQUIRED_GATE_IDS)} IDs; expected {expected}"
        )
    # Every required ID resolves to a real spec; global gate IDs are required.
    for gate_id in REQUIRED_GATE_IDS:
        if _gate_spec(gate_id) is None:
            raise ValueError(f"REQUIRED_GATE_IDS entry {gate_id!r} has no gate spec")
    if not (set(GLOBAL_GATE_SPECS) <= set(REQUIRED_GATE_IDS)):
        raise ValueError("GLOBAL_GATE_SPECS contains IDs not present in REQUIRED_GATE_IDS")
    if GLOBAL_GATE_SPECS["oracle_destroyed_standardized_difference"][
        "failure_class"
    ] != INFRASTRUCTURE_STATUS:
        raise ValueError(
            "oracle_destroyed_standardized_difference failure_class must be "
            f"INFRASTRUCTURE_STATUS ({INFRASTRUCTURE_STATUS!r})"
        )
    return True


# Deprecated gate-status classifier / family aggregator.  They are now thin
# wrappers over the exact evaluator and cannot bypass it.
def classify_gate_status(values: dict[str, Any] | None) -> str:
    """Deprecated alias: calls the exact evaluator without bypass."""
    return evaluate_gate_values(values)


def aggregate_family_verdict(values: dict[str, Any] | None) -> str:
    """Deprecated alias: calls the exact evaluator without bypass."""
    return evaluate_gate_values(values)


# ---------------------------------------------------------------------------
# Deterministic 3840 raw-cell key manifest and per-axis exclusions/count digests.
#   Manifest enumeration order is world -> generator (GENERATOR_ORDER) ->
#   manipulation -> dose; 3840 = world_count(32) x generators(6) x
#   manipulations(4) x doses(5).
# ---------------------------------------------------------------------------
RAW_CELL_SHAPE = (WORLD_COUNT, len(GENERATORS), len(MANIPULATIONS), len(DOSES))
RAW_CELL_COUNT = WORLD_COUNT * len(DOSES) * len(GENERATORS) * len(MANIPULATIONS)  # 3840


def raw_cell_key(
    world_index: int, dose: float, generator: str, manipulation: str
) -> dict[str, Any]:
    key = (
        f"{NAMESPACE}:cell:{world_index:02d}:{dose:.2f}:{generator}:{manipulation}"
    )
    return {
        "key": key,
        "sha256": _hex(key),
        "world_index": world_index,
        "dose": dose,
        "generator": generator,
        "manipulation": manipulation,
    }


def raw_cell_manifest() -> list[dict[str, Any]]:
    cells: list[dict[str, Any]] = []
    for w in range(WORLD_COUNT):
        for gen in GENERATOR_ORDER:
            for manip in tuple(MANIPULATIONS):
                for dose in DOSES:
                    cells.append(raw_cell_key(w, dose, gen, manip))
    if len(cells) != RAW_CELL_COUNT:
        raise ValueError(f"raw-cell manifest must contain exactly {RAW_CELL_COUNT} cells, got {len(cells)}")
    keys = [c["key"] for c in cells]
    if len(set(keys)) != RAW_CELL_COUNT:
        raise ValueError(
            f"raw-cell manifest must contain exactly {RAW_CELL_COUNT} unique keys, got {len(set(keys))} unique"
        )
    return cells


def r_structural_exclusions(design: dict[str, Any]) -> dict[str, Any]:
    """Result-blind structural R-axis exclusions computed from the frozen design.

    For every world and every generator in ``GENERATOR_ORDER``, for each of the 4
    actions the generator's exact baseline rationale (``_generator_cell``
    membership) is compared with the destroyed-endpoint membership.  The
    destroyed rationale endpoint is the bitwise complement of the ground-truth
    10-feature membership: ``destroyed[f] == 1`` for features **not** in that
    action's frozen rationale support and ``0`` for features that are.  A
    (world, generator) pair is structurally excluded only when the generator's
    baseline membership equals the destroyed membership on **all 4** actions.

    Exclusion is decided purely from the frozen structural memberships; it never
    infers the destroyed endpoint from ``GENERATOR_SCORES`` (q) or from any
    observed output.  Returns ``records`` (sorted by world_index then
    GENERATOR_ORDER), ``record_count``, and ``global_sha256`` over
    ``canonical_json_bytes(records)``.
    """
    if not isinstance(design, dict):
        raise ValueError("r_structural_exclusions requires the design dict")
    if "generators" not in design or "worlds" not in design:
        raise ValueError("design must carry frozen 'generators' and 'worlds'")
    generators = design["generators"]
    worlds = design["worlds"]
    if not isinstance(worlds, list) or len(worlds) != WORLD_COUNT:
        raise ValueError(
            "r_structural_exclusions requires the exact 32 frozen worlds"
        )
    if not isinstance(generators, dict) or set(generators) != set(GENERATOR_ORDER):
        raise ValueError(
            "design generator set must equal the frozen generator vocabulary "
            "(validate by set equality only, never by dict iteration order)"
        )

    records: list[dict[str, Any]] = []
    for world_index, world in enumerate(worlds):
        supports = world.get("action_rationale_supports")
        if not isinstance(supports, list) or len(supports) != ACTION_COUNT:
            raise ValueError(
                "world must freeze exactly four action rationale supports "
                f"(got world_index {world_index!r})"
            )
        for generator in GENERATOR_ORDER:
            equal_for_all_actions = True
            for action in range(ACTION_COUNT):
                support = supports[action]
                if (
                    not isinstance(support, list)
                    or not support
                    or any(
                        isinstance(f, bool) or not isinstance(f, int)
                        for f in support
                    )
                ):
                    raise ValueError(
                        f"action rationale support must be a non-empty int list "
                        f"for world {world_index!r} action {action!r}"
                    )
                _, membership, _ = _generator_cell(
                    generators, world, world_index, generator, support
                )
                destroyed = [
                    1 if f not in set(support) else 0 for f in range(FEATURE_COUNT)
                ]
                if membership != destroyed:
                    equal_for_all_actions = False
                    break
            if equal_for_all_actions:
                records.append(
                    {
                        "world_id": world.get("world_id"),
                        "generator": generator,
                        "reason": (
                            "generator baseline rationale membership equals the "
                            "destroyed-endpoint membership (bit=1 for features "
                            "outside the frozen action rationale support) on every "
                            "action; structurally excluded from the R dose-response gate"
                        ),
                    }
                )

    records.sort(
        key=lambda r: (_world_index_from_id(r["world_id"]), list(GENERATOR_ORDER).index(r["generator"]))
    )
    for record in records:
        if not record["world_id"]:
            raise ValueError("r_structural_exclusions record missing world_id")

    return {
        "records": records,
        "record_count": len(records),
        "global_sha256": hashlib.sha256(
            canonical_json_bytes(records)
        ).hexdigest().upper(),
        "endpoint_rule": (
            "destroyed membership = bitwise complement of the ground-truth "
            "10-feature action rationale support"
        ),
    }


# ---------------------------------------------------------------------------
# Deterministic raw-cell manifest contract (V3).  The raw 3840-key manifest is
# enumerated in the frozen order world -> GENERATOR_ORDER -> MANIPULATION_ORDER
# -> DOSES and its SHA-256 is canonical_json_bytes(raw key list).  Per-axis
# gate admissibility, per family x generator admissibility, the MTMM
# intersection, the leave-one-world-out (LOwO) union, full-rankings and
# five-baselines key sets, and the frozen R structural record manifest are all
# derived deterministically from the frozen design (never from observed q).
# ---------------------------------------------------------------------------
_AXIS_MANIPULATION = {
    "A": "action_correctness_degradation",
    "R": "rationale_correctness_degradation",
    "S": "selective_ranking_degradation",
    "C1": "nuisance_consistency_degradation",
}
_AXIS_EXCLUSION_REASON = {
    "A": "anti_causal_adversarial (destroyed endpoint) is excluded from the A dose-response gate",
    "R": "world-generator baseline rationale equals the destroyed endpoint (r_structural_exclusions)",
    "S": "generator with quality q == 0 (frozen design row_confidence_contract.generator_quality) is excluded from the S ranking gate",
    "C1": "nuisance consistency is admissible for every raw cell",
}
MTMM_NAMESPACE = (
    "ARSC_ROUND13_SYNTHETIC_MTMM_V1:mtmm:{world:02d}:{generator}:{dose:.2f}"
)
MTMM_EXPECTED_COUNT = 800
LOWO_EXPECTED_COUNT = 3520


def build_cell_manifest_contract(design: dict[str, Any]) -> dict[str, Any]:
    """Result-blind V3 raw-cell manifest contract computed from the frozen design.

    Uses the existing ``raw_cell_manifest()`` (exact 3840 unique keys in the
    order world -> GENERATOR_ORDER -> MANIPULATION_ORDER -> DOSES) and the
    existing ``r_structural_exclusions(design)`` for R-axis admissibility.  The
    S-axis ``q == 0`` gate reads the frozen
    ``design.row_confidence_contract.generator_quality``; ``q`` is never used
    as an R proxy.  All key-set digests are ``canonical_json_bytes`` of the key
    list, uppercased SHA-256.
    """
    if not isinstance(design, dict):
        raise ValueError("build_cell_manifest_contract requires the design dict")
    raw = raw_cell_manifest()
    raw_keys = [c["key"] for c in raw]
    if len(raw) != RAW_CELL_COUNT or len(set(raw_keys)) != RAW_CELL_COUNT:
        raise ValueError(
            f"raw-cell manifest must contain exactly {RAW_CELL_COUNT} unique keys, "
            f"got {len(raw)} cells / {len(set(raw_keys))} unique"
        )
    # Exact frozen enumeration order: world -> GENERATOR_ORDER -> MANIPULATION_ORDER -> DOSES.
    expected = [
        raw_cell_key(w, dose, gen, manip)["key"]
        for w in range(WORLD_COUNT)
        for gen in GENERATOR_ORDER
        for manip in MANIPULATION_ORDER
        for dose in DOSES
    ]
    if expected != raw_keys:
        raise ValueError(
            "raw-cell manifest must be enumerated in world -> GENERATOR_ORDER -> "
            "MANIPULATION_ORDER -> DOSES order"
        )

    def _sha(keys: list[str]) -> str:
        return hashlib.sha256(canonical_json_bytes(keys)).hexdigest().upper()

    raw_sha = _sha(raw_keys)
    r_excl = r_structural_exclusions(design)
    r_records = r_excl["records"]
    r_excl_pairs = {
        (str(record["world_id"]), str(record["generator"])) for record in r_records
    }

    def _world_id(world_index: int) -> str:
        return f"world_{world_index:02d}"

    gen_quality = design.get("row_confidence_contract", {}).get(
        "generator_quality", {}
    )
    if not isinstance(gen_quality, dict) or set(gen_quality) != set(GENERATOR_ORDER):
        raise ValueError(
            "design row_confidence_contract.generator_quality must cover exactly the "
            "frozen generator vocabulary"
        )
    q_zero_generators = {
        g for g, q in gen_quality.items() if float(q) == 0.0
    }

    def _axis_admissible(cell: dict[str, Any]) -> bool:
        manip = cell["manipulation"]
        if manip == _AXIS_MANIPULATION["A"]:
            return cell["generator"] != "anti_causal_adversarial"
        if manip == _AXIS_MANIPULATION["R"]:
            return (_world_id(cell["world_index"]), cell["generator"]) not in r_excl_pairs
        if manip == _AXIS_MANIPULATION["S"]:
            return cell["generator"] not in q_zero_generators
        if manip == _AXIS_MANIPULATION["C1"]:
            return True
        raise ValueError(f"unknown manipulation {manip!r} in raw-cell manifest")

    axes: dict[str, Any] = {}
    family_x_generator: dict[str, Any] = {}
    for family in FAMILIES:
        manip = _AXIS_MANIPULATION[family]
        cells = [c for c in raw if c["manipulation"] == manip]
        admissible = [c for c in cells if _axis_admissible(c)]
        excluded = [c for c in cells if not _axis_admissible(c)]
        axes[family] = {
            "manipulation": manip,
            "exclusion_rule": _AXIS_EXCLUSION_REASON[family],
            "total_raw": {"count": len(cells), "keys": [c["key"] for c in cells],
                          "sha256": _sha([c["key"] for c in cells])},
            "admissible": {"count": len(admissible),
                           "keys": [c["key"] for c in admissible],
                           "sha256": _sha([c["key"] for c in admissible])},
            "excluded": {
                "count": len(excluded),
                "records": [c for c in excluded],
                "reasons": _AXIS_EXCLUSION_REASON[family],
                "keys": [c["key"] for c in excluded],
                "sha256": _sha([c["key"] for c in excluded]),
            },
        }
        fg: dict[str, Any] = {}
        for gen in GENERATOR_ORDER:
            gen_cells = [c for c in cells if c["generator"] == gen]
            gen_admissible = [c for c in gen_cells if _axis_admissible(c)]
            raw_expected = RAW_CELL_COUNT // (len(FAMILIES) * len(GENERATOR_ORDER))
            fg[gen] = {
                "raw_expected": raw_expected,
                "raw_actual": len(gen_cells),
                "gate_expected": len(gen_admissible),
                "excluded_count": len(gen_cells) - len(gen_admissible),
                "reason": (
                    "admissible" if len(gen_cells) == len(gen_admissible)
                    else _AXIS_EXCLUSION_REASON[family]
                ),
            }
        family_x_generator[family] = fg

    # MTMM intersection: (world, generator, dose) admissible in all four axes.
    triple_in = {
        (w, g, d)
        for w in range(WORLD_COUNT)
        for g in GENERATOR_ORDER
        for d in DOSES
        if _axis_admissible(
            {"manipulation": _AXIS_MANIPULATION["A"], "generator": g,
             "world_index": w}
        )
        and _axis_admissible(
            {"manipulation": _AXIS_MANIPULATION["R"], "generator": g,
             "world_index": w}
        )
        and _axis_admissible(
            {"manipulation": _AXIS_MANIPULATION["S"], "generator": g,
             "world_index": w}
        )
    }
    mtmm_keys = [
        MTMM_NAMESPACE.format(world=w, generator=g, dose=d)
        for w in range(WORLD_COUNT)
        for g in GENERATOR_ORDER
        for d in DOSES
        if (w, g, d) in triple_in
    ]
    per_gen_counts = {g: 0 for g in GENERATOR_ORDER}
    for key in mtmm_keys:
        # generator is the second NAMESPACE-part after ':mtmm:'.
        per_gen_counts[next(gg for gg in GENERATOR_ORDER if gg in key)] += 1
    mtmm = {
        "namespace": NAMESPACE,
        "key_template": "ARSC_ROUND13_SYNTHETIC_MTMM_V1:mtmm:{world:02d}:{generator}:{dose:.2f}",
        "expected_approximation": MTMM_EXPECTED_COUNT,
        "keys": mtmm_keys,
        "count": len(mtmm_keys),
        "unique_count": len(set(mtmm_keys)),
        "sha256": _sha(mtmm_keys),
        "per_generator_counts": per_gen_counts,
    }

    # LOwO union: every raw cell admissible under its own manipulation rule,
    # listed in the canonical raw order (world -> gen -> manip -> dose).
    lowo_keys = [c["key"] for c in raw if _axis_admissible(c)]
    lowo = {
        "kind": "union over the four families of the raw cells admissible under their own manipulation rule",
        "expected_approximation": LOWO_EXPECTED_COUNT,
        "keys": lowo_keys,
        "count": len(lowo_keys),
        "unique_count": len(set(lowo_keys)),
        "sha256": _sha(lowo_keys),
    }

    def _requires_all(why: str) -> dict[str, Any]:
        return {
            "requires": why,
            "keys": raw_keys,
            "count": len(raw_keys),
            "unique_count": RAW_CELL_COUNT,
            "sha256": raw_sha,
        }

    full_rankings = _requires_all(
        "full_rankings require all 3840 raw cells (all six generators, all four families)"
    )
    five_baselines = _requires_all(
        "five_baselines require all 3840 raw cells / all six generators"
    )

    return {
        "shape": list(RAW_CELL_SHAPE),
        "raw_cell_count": RAW_CELL_COUNT,
        "generator_order": list(GENERATOR_ORDER),
        "manipulation_order": list(MANIPULATION_ORDER),
        "enumeration_order": "world -> generator (GENERATOR_ORDER) -> manipulation (MANIPULATION_ORDER) -> dose (DOSES)",
        "keys": raw_keys,
        "key_count": len(raw_keys),
        "unique_key_count": len(set(raw_keys)),
        "key_manifest_sha256": raw_sha,
        "axes": axes,
        "family_x_generator": family_x_generator,
        "mtmm_intersection": mtmm,
        "lowo_union": lowo,
        "full_rankings": full_rankings,
        "five_baselines": five_baselines,
        "r_structural_manifest": {
            "record_count": len(r_records),
            "records": r_records,
            "global_sha256": r_excl["global_sha256"],
            "endpoint_rule": r_excl["endpoint_rule"],
        },
        "invariants": {
            "no_missing_cell": True,
            "no_duplicate_key": len(raw_keys) == len(set(raw_keys)),
            "raw_exact_3840_unique": len(raw_keys) == len(set(raw_keys)) == RAW_CELL_COUNT,
        },
    }


def build_authoritative_evaluation(v2_evaluation: dict[str, Any]) -> dict[str, Any]:
    """Return the authoritative V3 evaluation from a frozen V2 evaluation dict.

    The input is deep-copied (never mutated) and the copy is made authoritative
    by marking ``v3_semantic_contracts_are_authoritative`` True and by replacing
    the C1 / S / R / support_f1 semantic contracts with the authoritative V3
    forms tied to the directed C1 paired design:

      * ``C1_action_formula`` uses per world exactly 3072 directed nuisance
        pairs; C1_action = 1 - mean binary any-4-bit-action-vector-changed
        (aggregate over pairs then over the world); the immutable clean channel
        stays unchanged and only the paired output of each affected anchored
        clean row is overwritten;
      * ``C1_rationale_formula`` uses the same directed 3072 pairs per world;
        C1_rationale = mean over pairs of the mean Jaccard across the 4 actions,
        with empty-vs-empty counted as 1.0 (aggregate pair then world);
      * ``S_formula`` uses analytic exact-tie grouping ``(u+k*z/m)/(p+k)`` with
        no row split and no hash split (results are analytic, never jittered);
      * ``R_formula`` is a per-cell ``[1024,4,10]`` tensor whose TP/FP/FN counts
        are accumulated across the 1024 rows per action-feature, then the mean
        over the 40 cells is taken; a zero denominator computes 1;
      * ``support_f1`` is a deep copy of the authoritative ``R_formula``.

    Only the ``formulas`` block changes; metrics and baselines remain frozen.
    """
    evaluation = copy.deepcopy(v2_evaluation)
    evaluation["v3_semantic_contracts_are_authoritative"] = True
    formulas = evaluation["formulas"]
    formulas["C1_action_formula"] = {
        "formula": (
            "C1_action = 1 - mean over all 3072 directed nuisance pairs per world "
            "of (1 if any of the 4 action bits changed else 0); per world exactly "
            "3072 directed nuisance pairs; a pair's action change is binary (any "
            "4-bit action-vector difference); aggregate over pairs then over the world"
        ),
        "truth": (
            "nuisance-only directed pairs never recompute truth (nuisance features "
            "are not causal); the immutable clean-channel output always remains "
            "unchanged and only the paired output (shared output) of each affected "
            "anchored clean row is overwritten, so any changed prediction on a paired "
            "output is a genuine C1 violation"
        ),
        "tie_handling": "a 4-bit action-vector change is binary; no ties",
        "direction": "higher is better (fewer changed action vectors)",
        "edge_cases": (
            "per world exactly 3072 directed nuisance pairs (all 1024 clean rows x "
            "3 nuisance feature IDs ascending); C1_action is always computable over "
            "this fixed paired set"
        ),
    }
    formulas["C1_rationale_formula"] = {
        "formula": (
            "C1_rationale = mean over all 3072 directed pairs per world of the mean "
            "Jaccard across the 4 actions between the clean and paired-nuisance "
            "rationale supports; Jaccard = |A intersect B| / |A union B|; "
            "empty-vs-empty counts 1.0; aggregate over pairs then over the world"
        ),
        "truth": (
            "nuisance-only directed pairs never recompute truth (nuisance features "
            "are not causal); Jaccard is computed between the immutable clean-channel "
            "rationale and the overwritten paired-rationale output of the same "
            "affected anchored clean row"
        ),
        "tie_handling": "mean Jaccard over the 4 actions within a pair; pairs never recompute truth",
        "direction": "higher is better",
        "edge_cases": (
            "per world exactly 3072 directed nuisance pairs; |A union B| = 0 implies "
            "both supports are empty and gives 1.0"
        ),
    }
    s_formula = formulas["S_formula"]
    s_formula["formula"] = (
        "S = -AURC computed by analytic exact-tie grouping (u+k*z/m)/(p+k); "
        "ties are grouped exactly with no row split and no hash split"
    )
    s_formula["tie_handling"] = (
        "analytic exact-tie grouping (u+k*z/m)/(p+k); no row split and no hash split"
    )
    formulas["R_formula"] = {
        "formula": "per-cell tensor shape [1024,4,10]; TP/FP/FN accumulated across the 1024 rows per action-feature; mean over the 40 cells; zero denominator -> 1",
        "truth": "against the recomputed per-action causal support membership (instantiated Boolean expressions) for the world/dose",
        "tie_handling": "counts summed over 1024 rows per action-feature; mean over the 40 cells; no split",
        "direction": "higher is better",
        "edge_cases": "zero denominator (2*TP+FP+FN == 0) computes 1.0 for that cell",
    }
    formulas["support_f1"] = copy.deepcopy(formulas["R_formula"])
    return evaluation


# ---------------------------------------------------------------------------
# Baseline-boundary helpers (requirement: deletion/insertion masks and the
# causal-boundary flip order).  These are pure functions backing the
# ``baseline_boundary`` semantics: deletion/insertion masks zero/restore the
# top-k ranked aggregate features and causal-boundary flips run in
# SHA256(NAMESPACE:causal_boundary:w:i:feature) ascending-digest order.
# ---------------------------------------------------------------------------


def _permutation_ok(ranking: Any) -> bool:
    return (
        isinstance(ranking, list)
        and len(ranking) == 10
        and all(isinstance(f, int) and not isinstance(f, bool) for f in ranking)
        and sorted(ranking) == list(range(10))
    )


def deletion_masked_row(original_row: int, ranking: list[int], k: int) -> int:
    """Zero the bits at ``ranking[:k]`` (the top-k ranked aggregate features).

    ``original_row`` must be a non-bool int in 0..1023, ``ranking`` an exact
    permutation of the feature ids 0..9, and ``k`` a non-bool int in 0..10.
    Bit ``f`` refers to ``1 << f``.
    """
    if isinstance(original_row, bool) or not isinstance(original_row, int):
        raise ValueError("original_row must be an int (not a bool)")
    if not 0 <= original_row <= 1023:
        raise ValueError("original_row must be in 0..1023")
    if not _permutation_ok(ranking):
        raise ValueError("ranking must be an exact permutation of feature ids 0..9")
    if isinstance(k, bool) or not isinstance(k, int):
        raise ValueError("k must be an int (not a bool)")
    if not 0 <= k <= 10:
        raise ValueError("k must be in 0..10")
    clear = 0
    for feature in ranking[:k]:
        clear |= 1 << feature
    return original_row & ~clear


def insertion_masked_row(original_row: int, ranking: list[int], k: int) -> int:
    """Restore only the ``original_row`` bits at ``ranking[:k]`` starting from zero.

    Validation matches ``deletion_masked_row``.  Bits in ``ranking[:k]`` are
    copied from ``original_row``; every other bit stays zero.
    """
    if isinstance(original_row, bool) or not isinstance(original_row, int):
        raise ValueError("original_row must be an int (not a bool)")
    if not 0 <= original_row <= 1023:
        raise ValueError("original_row must be in 0..1023")
    if not _permutation_ok(ranking):
        raise ValueError("ranking must be an exact permutation of feature ids 0..9")
    if isinstance(k, bool) or not isinstance(k, int):
        raise ValueError("k must be an int (not a bool)")
    if not 0 <= k <= 10:
        raise ValueError("k must be in 0..10")
    result = 0
    for feature in ranking[:k]:
        if original_row & (1 << feature):
            result |= 1 << feature
    return result


def causal_boundary_order(world_index: int, row: int, causal_ids: list[int]) -> list[int]:
    """Order the four causal-boundary features flips at a (world, row) cell.

    ``world_index`` must be a non-bool int in 0..31, ``row`` a non-bool int in
    0..1023, and ``causal_ids`` exactly four unique feature ids 0..9.  Each
    feature f is keyed by UTF8 ``NAMESPACE:causal_boundary:{world_index}:{row:04d}:{f}``
    sorted by SHA-256 digest bytes ascending with the feature id as the tiebreak.
    """
    if isinstance(world_index, bool) or not isinstance(world_index, int):
        raise ValueError("world_index must be an int (not a bool)")
    if not 0 <= world_index <= 31:
        raise ValueError("world_index must be in 0..31")
    if isinstance(row, bool) or not isinstance(row, int):
        raise ValueError("row must be an int (not a bool)")
    if not 0 <= row <= 1023:
        raise ValueError("row must be in 0..1023")
    if (
        not isinstance(causal_ids, list)
        or len(causal_ids) != 4
        or len(set(causal_ids)) != 4
        or not all(
            isinstance(f, int) and not isinstance(f, bool) and 0 <= f <= 9
            for f in causal_ids
        )
    ):
        raise ValueError("causal_ids must contain exactly four unique feature ids 0..9")
    keyed = sorted(
        (
            _digest(f"{NAMESPACE}:causal_boundary:{world_index}:{row:04d}:{feature}"),
            feature,
        )
        for feature in causal_ids
    )
    return [feature for _digest_bytes, feature in keyed]


def causal_boundary_manifest(worlds: list[dict[str, Any]]) -> dict[str, Any]:
    """32 per-world causal-boundary manifest hashes plus the global V3 hash.

    For every world (world_index 0..31) and every row 0..1023 the four actual
    world causal feature IDs (``feature_roles.causal``, exactly four unique
    IDs) are flipped in ``SHA256(NAMESPACE:causal_boundary:world:row:feature)``
    digest-ascending order; the per-cell record is ``{world_index, row, order}``.
    Each record serializes as canonical JSON UTF-8 plus a newline
    (``canonical_json_bytes(record)``).  The per-world manifest payload is the
    concatenation of the canonical records over rows 0..1023 ascending; the
    global payload is the concatenation of the per-world raw payloads in world
    order (worlds sorted by increasing world_index).  Both the per-world and
    global manifest hashes are embedded together with the exact serialization
    framing.
    """
    if not isinstance(worlds, list) or len(worlds) != WORLD_COUNT:
        raise ValueError(
            "causal_boundary_manifest requires exactly the 32 frozen worlds"
        )
    ordered_worlds = sorted(worlds, key=lambda w: _world_index_from_id(w["world_id"]))
    if len(ordered_worlds) != WORLD_COUNT:
        raise ValueError(
            "causal_boundary_manifest world set must resolve to exactly 32 worlds"
        )
    per_world: dict[str, dict[str, Any]] = {}
    global_payload = b""
    for world in ordered_worlds:
        world_index = _world_index_from_id(world["world_id"])
        causal = world.get("feature_roles", {}).get("causal")
        if (
            not isinstance(causal, list)
            or len(causal) != 4
            or len(set(int(i) for i in causal)) != 4
            or any(int(i) not in range(FEATURE_COUNT) for i in causal)
        ):
            raise ValueError(
                "world feature_roles.causal must be exactly four unique feature IDs 0..9"
            )
        causal_ids = sorted(int(i) for i in causal)  # actual causal IDs ascending
        payload = b""
        for row in range(ROWS_PER_WORLD):
            order = causal_boundary_order(world_index, row, causal_ids)
            record: dict[str, Any] = {
                "world_index": world_index,
                "row": row,
                "order": order,
            }
            payload += canonical_json_bytes(record)
        per_world[str(world_index)] = {
            "world_index": world_index,
            "causal_feature_ids": causal_ids,
            "row_count": ROWS_PER_WORLD,
            "manifest_sha256": hashlib.sha256(payload).hexdigest().upper(),
        }
        global_payload += payload
    if len(per_world) != WORLD_COUNT:
        raise ValueError("causal_boundary_manifest must cover exactly 32 worlds")
    return {
        "per_world": per_world,
        "per_world_count": len(per_world),
        "total_records": len(per_world) * ROWS_PER_WORLD,
        "serialization_framing": (
            "each record {'world_index','row','order'} serialized canonically "
            "(canonical_json_bytes: compact JSON UTF-8 + newline); per-world "
            "manifest payload = concatenation of the canonical records over rows "
            "0..1023 ascending; global payload = concatenation of the per-world "
            "raw payloads in world order"
        ),
        "global_manifest_sha256": hashlib.sha256(global_payload).hexdigest().upper(),
    }


def build_baseline_boundary_contract(design: dict[str, Any]) -> dict[str, Any]:
    """Freeze the full baseline-boundary machine-readable contract.

    ``design`` must carry the 32 frozen worlds (``design[\"worlds\"]``).  The
    contract freezes the five exact baseline rules (deletion_auc, insertion_auc,
    infidelity, max_sensitivity, support_f1), the causal-boundary exact seed
    format / feature candidates / digest sort-collision / prefixes / recompute /
    never-C1 framing, the golden deletion/insertion masks, and the embedded
    causal-boundary manifest, all result-blind (no observed outputs).
    """
    worlds = design.get("worlds")
    if not isinstance(worlds, list) or len(worlds) != WORLD_COUNT:
        raise ValueError(
            "design.worlds must be the exact 32 frozen worlds for the baseline-boundary contract"
        )
    manifest = causal_boundary_manifest(worlds)
    golden_ranking = list(range(FEATURE_COUNT))  # 0..9
    golden_row = 5
    golden_masks: list[dict[str, Any]] = []
    for k in (0, 3, 10):
        golden_masks.append(
            {
                "row": golden_row,
                "ranking": list(golden_ranking),
                "k": k,
                "deletion_masked_row": deletion_masked_row(
                    golden_row, golden_ranking, k
                ),
                "insertion_masked_row": insertion_masked_row(
                    golden_row, golden_ranking, k
                ),
            }
        )
    return {
        "baselines": {
            "deletion_auc": {
                "rule": (
                    "at each k=0..10, rerun the same generator at the masked row "
                    "(deletion_masked_row zeroes the bits at ranking[:k]) and score "
                    "the response against the original unmasked truth"
                ),
                "mask_semantics": (
                    "deletion_masked_row(original_row, ranking, k) zeroes the bits "
                    "at ranking[:k]; k runs 0..10 (11 points)"
                ),
                "auc_semantics": (
                    "11-point k/10 trapezoid AUC over deletion accuracies; "
                    "higher-ranked aggregate features removed first"
                ),
                "direction": BASELINES["deletion_auc"],
            },
            "insertion_auc": {
                "rule": (
                    "at each k=0..10, rerun the same generator at the restored row "
                    "(insertion_masked_row restores only the original_row bits at "
                    "ranking[:k] starting from zero) and score the response against "
                    "the original unmasked truth"
                ),
                "mask_semantics": (
                    "insertion_masked_row(original_row, ranking, k) restores only "
                    "the ranking[:k] bits copied from original_row; every other bit "
                    "stays zero; k runs 0..10 (11 points)"
                ),
                "auc_semantics": (
                    "11-point k/10 trapezoid AUC over insertion accuracies; "
                    "higher-ranked ranking[:k] features are inserted first"
                ),
                "direction": BASELINES["insertion_auc"],
            },
            "infidelity": {
                "rule": (
                    "uniform over all 1024 binary masks in canonical integer order "
                    "0..1023; actual generator f_scalar = arithmetic mean of the 4 "
                    "output scores across the 4 actions"
                ),
                "truth": (
                    "scored against the original unmasked truth; masks never alter "
                    "the ground-truth action/rationale"
                ),
                "direction": BASELINES["infidelity"],
            },
            "max_sensitivity": {
                "rule": (
                    "max sensitivity of the actual aggregate generator g against "
                    "all 10 Hamming-distance-1 single-feature counterfactuals"
                ),
                "truth": (
                    "scored against the original unmasked truth; counterfactuals "
                    "never alter the ground-truth action/rationale"
                ),
                "direction": BASELINES["max_sensitivity"],
            },
            "support_f1": {
                "rule": (
                    "exactly the authoritative R tensor: support_f1 is a deep copy "
                    "of R_formula with identical per-cell TP/FP/FN accumulated over "
                    "the 1024 rows per action-feature and mean over the 40 cells; "
                    "zero denominator -> 1"
                ),
                "direction": BASELINES["support_f1"],
            },
        },
        "model_output_recomputed_on_masked_or_counterfactual_input": True,
        "scoring_truth_recomputed": False,
        "truth_intake": (
            "all five baselines score the response against the original unmasked "
            "truth; the model output is recomputed on the masked/counterfactual "
            "input but the scoring truth is never recomputed; causal-boundary pairs "
            "never feed the C1 gate"
        ),
        "causal_boundary": {
            "seed_key_format": (
                f"{NAMESPACE}:causal_boundary:{{world_index}}:{{row:04d}}:{{feature}}"
            ),
            "feature_candidates": (
                "the four actual world feature_roles.causal IDs ascending (sorted)"
            ),
            "digest_sort": (
                "sorted by full SHA-256 digest bytes ascending over "
                "SHA256(NAMESPACE:causal_boundary:world_index:row:feature) "
                "keyed per causal feature"
            ),
            "digest_collision": (
                "an exact digest collision is broken by ascending actual feature id"
            ),
            "prefixes": (
                "enumerate all nonempty prefixes of the four causal features "
                "(prefixes 1..4)"
            ),
            "recompute_truth": True,
            "never_c1": "causal-boundary pairs never feed the C1 gate",
        },
        "golden_masks": {
            "row": golden_row,
            "ranking": list(golden_ranking),
            "k_values": [0, 3, 10],
            "examples": golden_masks,
        },
        "mask_functions": {
            "deletion": "deletion_masked_row",
            "insertion": "insertion_masked_row",
        },
        "manifest": manifest,
    }


# ---------------------------------------------------------------------------
# Contract building (requirement 1/7).  Worlds/orders are copied byte-for-byte
# from the supplied, parsed, result-blind V2 frozen protocol (pure
# build_contract(v2_protocol); design/evaluation/worlds/orders never resampled).
# ---------------------------------------------------------------------------
def _expected_gate_mapping() -> dict[str, Any]:
    """Deterministic expected ``gate_mapping`` dict (source of truth for the
    contract and for exact-equality validation)."""
    return {
        "pass_rule": (
            "PASS iff the exact required gate key set is present and every gate "
            "passes its exact preregistered bound (see gate_contract)"
        ),
        "gate_contract": build_gate_contract(),
        "numeric_failure": NOT_VALIDATED_VERDICT,
        "infrastructure_failure": INFRASTRUCTURE_STATUS,
        "never_a_third_verdict": True,
        "note": (
            "IMPLEMENTATION_FAILURE is an infrastructure/implementation status, "
            "never a third scientific verdict; the only two scientific verdicts "
            "are FINAL_VERDICTS."
        ),
    }


def _expected_formal_execution() -> dict[str, Any]:
    """Deterministic expected ``formal_execution`` dict constructed from
    ``V3_ONE_SHOT`` / the artifact lists / ``V3_HASH_CLOSURE`` / the legacy
    artifact lists / ``FINAL_VERDICTS``.  It is the single source of truth for
    both contract construction and exact-equality validation."""
    return {
        # one_shot and hash_closure are deep-copied so caller tampering with the
        # contract cannot corrupt the module-level V3_ONE_SHOT / V3_HASH_CLOSURE.
        "one_shot": copy.deepcopy(V3_ONE_SHOT),
        "artifact_allowlist": list(V3_ARTIFACT_ALLOWLIST),
        "preclaim_forbidden_artifacts": list(V3_PREFORMAL_ARTIFACT_RELS),
        "hash_closure": copy.deepcopy(V3_HASH_CLOSURE),
        "legacy_v1_artifacts_forbidden": list(V1_LEGACY_FORMAL_ARTIFACT_RELS),
        "legacy_v2_artifacts_forbidden": list(V2_LEGACY_FORMAL_ARTIFACT_RELS),
        "possible_scientific_verdicts": list(FINAL_VERDICTS),
        "scientific_verdict_count": len(FINAL_VERDICTS),
    }


def build_contract(
    v2_protocol: dict[str, Any], *, include_replacement_orders: bool = True
) -> dict[str, Any]:
    if v2_protocol.get("schema_version") != V2_SCHEMA or v2_protocol.get("result_blind") is not True:
        raise ValueError("caller must supply the exact parsed result-blind V2 frozen protocol")
    design = copy.deepcopy(v2_protocol["design"])
    evaluation = build_authoritative_evaluation(v2_protocol["evaluation"])
    if not include_replacement_orders:
        design.pop("replacement_orders", None)
    contract: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "result_blind": True,
        "prior_protocol_status": SUPERSEDED_STATUS,
        "lineage": copy.deepcopy(LINEAGE),
        "directed_c1": build_directed_c1_contract(design),
        "s_fixture": build_s_fixture_contract(),
        "generator_hash_ordering": build_generator_contract(design),
        "r_tensor": r_tensor_contract(),
        "baseline_boundary": build_baseline_boundary_contract(design),
        "resampling": build_resampling_contract(),
        "gate_mapping": _expected_gate_mapping(),
        "raw_cell_manifest": build_cell_manifest_contract(design),
        "design": design,
        "evaluation": evaluation,
        "formal_execution": _expected_formal_execution(),
    }
    validate_contract(contract, v2_protocol, require_orders=include_replacement_orders)
    return contract


def validate_contract(
    contract: dict[str, Any],
    v2_protocol: dict[str, Any],
    *,
    require_orders: bool = True,
) -> None:
    """Result-blind structural validation of a V3 contract against the committed V2
    protocol input (no resampling of worlds/orders)."""
    if contract.get("result_blind") is not True:
        raise ValueError("protocol must remain result-blind")
    if contract.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("protocol schema version must be the V3 schema")
    if contract.get("prior_protocol_status") != SUPERSEDED_STATUS:
        raise ValueError("V2 prior protocol status must be SUPERSEDED_PRECLAIM")
    if contract.get("lineage") != LINEAGE:
        raise ValueError("lineage must equal the exact frozen LINEAGE dict exactly")
    if contract.get("gate_mapping") != _expected_gate_mapping():
        raise ValueError(
            "gate_mapping must equal the exact _expected_gate_mapping()"
        )
    if contract.get("formal_execution") != _expected_formal_execution():
        raise ValueError(
            "formal_execution must equal the exact _expected_formal_execution()"
        )
    design = contract["design"]
    v2_design = v2_protocol["design"]
    for key in (
        "world_count",
        "feature_count",
        "rows_per_world",
        "feature_role_counts",
        "doses",
        "worlds",
        "manipulations",
        "boundary_controls",
        "row_confidence_contract",
        "attribution_aggregation",
    ):
        if design.get(key) != v2_design.get(key):
            raise ValueError(f"V3 resampled or changed frozen V2 design field: {key}")
    for generator in v2_design["generators"]:
        if design["generators"][generator] != v2_design["generators"][generator]:
            raise ValueError(f"V3 changed frozen V2 generator fields: {generator}")
    if contract["evaluation"] != build_authoritative_evaluation(v2_protocol["evaluation"]):
        raise ValueError("V3 evaluation must equal the authoritative V3 evaluation built from frozen V2")
    if contract["evaluation"]["metrics"] != METRICS:
        raise ValueError("V3 evaluation metrics must match the frozen vocabulary")
    if contract["evaluation"]["baselines"] != BASELINES:
        raise ValueError("V3 evaluation baselines must match the frozen vocabulary")
    directed = contract.get("directed_c1", {})
    if directed != build_directed_c1_contract(contract["design"]):
        raise ValueError("directed C1 contract must equal the exact recomputed build_directed_c1_contract(design)")
    directed = contract.get("directed_c1", {})
    if directed.get("paired_cells_per_world") != PAIRS_PER_WORLD:
        raise ValueError("directed C1 must freeze exactly 3072 pairs per world")
    if directed.get("action_denominator") != PAIRS_PER_WORLD:
        raise ValueError("directed C1 action denominator must be exactly 3072")
    if directed.get("rationale_denominator") != PAIRS_PER_WORLD:
        raise ValueError("directed C1 rationale denominator must be exactly 3072")
    if directed.get("nuisance_count") != NUISANCE_COUNT:
        raise ValueError("directed C1 must use exactly 3 nuisance features")
    s_fixture = contract.get("s_fixture", {})
    if s_fixture != build_s_fixture_contract():
        raise ValueError("S fixture contract must equal the exact recomputed build_s_fixture_contract()")
    s_fixture = contract.get("s_fixture", {})
    if S_FIXTURE_NAMESPACE_FMT not in s_fixture.get("seed_string_format", ""):
        raise ValueError("S fixture seed string format contract changed")
    if s_fixture.get("digest_rule") != "full SHA-256 digest unsigned big-endian mod 5":
        raise ValueError("S fixture digest-rule contract changed")
    if contract["generator_hash_ordering"] != build_generator_contract(contract["design"]):
        raise ValueError(
            "generator hash-ordering contract must equal the exact recomputed build_generator_contract(design)"
        )
    baseline_boundary = contract.get("baseline_boundary")
    recomputed_baseline_boundary = build_baseline_boundary_contract(contract["design"])
    if baseline_boundary != recomputed_baseline_boundary:
        raise ValueError(
            "baseline boundary contract must equal the exact recomputed build_baseline_boundary_contract(design)"
        )
    if (
        baseline_boundary.get("manifest")
        != causal_boundary_manifest(contract["design"]["worlds"])
    ):
        raise ValueError(
            "baseline-boundary causal manifest must equal the exact recomputed causal_boundary_manifest(design.worlds)"
        )
    gate_contract = contract.get("gate_mapping", {}).get("gate_contract")
    if gate_contract != build_gate_contract():
        raise ValueError(
            "gate contract must equal the exact recomputed build_gate_contract()"
        )
    resampling = contract.get("resampling", {})
    if resampling != build_resampling_contract():
        raise ValueError(
            "resampling contract must equal the exact recomputed build_resampling_contract()"
        )
    r_tensor = contract.get("r_tensor", {})
    if r_tensor != r_tensor_contract():
        raise ValueError(
            "r_tensor contract must equal the exact recomputed r_tensor_contract()"
        )
    raw = contract.get("raw_cell_manifest", {})
    if raw != build_cell_manifest_contract(contract["design"]):
        raise ValueError(
            "raw-cell manifest must equal the exact recomputed build_cell_manifest_contract(design)"
        )
    formal = contract["formal_execution"]
    if formal["one_shot"]["attempt"] != FORMAL_ATTEMPT:
        raise ValueError("V3 attempt label must be round13_attempt03")
    if formal["one_shot"]["claim_schema"] != FORMAL_EXECUTION_SCHEMA:
        raise ValueError("V3 claim schema must be ARSC_ROUND13_SYNTHETIC_MTMM_CLAIM_V3")
    if tuple(formal["possible_scientific_verdicts"]) != FINAL_VERDICTS:
        raise ValueError("exactly two scientific verdict strings are frozen")
    if formal["scientific_verdict_count"] != 2:
        raise ValueError("exactly two scientific verdicts are required")
    if formal["artifact_allowlist"] != list(V3_ARTIFACT_ALLOWLIST):
        raise ValueError("V3 artifact allowlist must contain protocol/claim/results/verdict/index")
    if formal["preclaim_forbidden_artifacts"] != list(V3_PREFORMAL_ARTIFACT_RELS):
        raise ValueError("V3 preclaim-forbidden artifact list changed")
    if formal["hash_closure"] != V3_HASH_CLOSURE:
        raise ValueError("V3 hash closure changed")
    if formal["one_shot"]["postclaim_failure"]["claim_consumed"] is not True:
        raise ValueError("postclaim failure must consume the one-attempt claim")
    if formal["one_shot"]["retry_allowed"] is not False:
        raise ValueError("postclaim retry must not be allowed")
    if formal["one_shot"]["infrastructure_status"]["is_a_scientific_verdict"]:
        raise ValueError("IMPLEMENTATION_FAILURE must never be a scientific verdict")
    if formal["one_shot"]["infrastructure_status"]["value"] != INFRASTRUCTURE_STATUS:
        raise ValueError("infrastructure status value changed")
    if formal["one_shot"]["scientific_verdict_count"] != 2:
        raise ValueError("exactly two scientific verdicts are required")
    if require_orders:
        orders = contract["design"].get("replacement_orders", [])
        if orders != v2_design.get("replacement_orders"):
            raise ValueError("V3 replacement orders must be copied from frozen V2 bytes")
        expected = WORLD_COUNT * len(GENERATORS) * len(MANIPULATIONS) * len(NONZERO_DOSES)
        if len(orders) != expected:
            raise ValueError("replacement order coverage mismatch")
        for record in orders:
            order = record["permutation"]
            if sorted(order) != list(range(ROWS_PER_WORLD)) or _order_digest(order) != record[
                "permutation_sha256"
            ]:
                raise ValueError("invalid replacement permutation or digest")


__all__ = [
    "ACTION_COUNT",
    "BASELINES",
    "BOOTSTRAP_QUANTILE_RULES",
    "BOOTSTRAP_SEED_FMT",
    "BOOTSTRAP_DRAWS",
    "BOOTSTRAP_SEED",
    "C1_XOR_MAPPING",
    "DOSES",
    "FAMILIES",
    "FAMILY_Q",
    "FEATURE_COUNT",
    "FINAL_VERDICTS",
    "FORMAL_ATTEMPT",
    "FORMAL_CLAIM_NAME",
    "FORMAL_CLAIM_PATH",
    "FORMAL_EXECUTION_SCHEMA",
    "FORMAL_INDEX_NAME",
    "FORMAL_RESULTS_NAME",
    "FORMAL_VERDICT_NAME",
    "FORMULAS",
    "FROZEN_PROTOCOL_OUTPUT",
    "GENERATOR_ORDER",
    "GENERATOR_SCORES",
    "GENERATORS",
    "INFRASTRUCTURE_STATUS",
    "LINEAGE",
    "MANIPULATIONS",
    "METRICS",
    "NAMESPACE",
    "NONZERO_DOSES",
    "NOT_VALIDATED_VERDICT",
    "NUISANCE_COUNT",
    "PAIRS_PER_WORLD",
    "PASS_VERDICT",
    "PRECLAIM_PHASE",
    "PRIOR_ATTEMPT",
    "R_MEAN_CELLS",
    "R_TENSOR_SHAPE",
    "RAW_CELL_COUNT",
    "RAW_CELL_SHAPE",
    "ROWS_PER_WORLD",
    "SCHEMA_VERSION",
    "S_DIGEST_BIG_ENDIAN_MOD",
    "S_FIXTURE_NAMESPACE_FMT",
    "SUPERSEDED_STATUS",
    "V1_LEGACY_FORMAL_ARTIFACT_RELS",
    "V2_COMMIT",
    "V2_LEGACY_FORMAL_ARTIFACT_RELS",
    "V2_PROTOCOL_REL",
    "V2_PROTOCOL_SHA256",
    "V2_SCHEMA",
    "V3_ARTIFACT_ALLOWLIST",
    "V3_HASH_CLOSURE",
    "V3_ONE_SHOT",
    "V3_PREFORMAL_ARTIFACT_RELS",
    "V3_PROTOCOL_NAME",
    "WORLD_COUNT",
    "aggregate_family_verdict",
    "bootstrap_manifest",
    "bootstrap_manifest_sha",
    "bootstrap_replicate_world",
    "build_authoritative_evaluation",
    "build_baseline_boundary_contract",
    "build_contract",
    "build_directed_c1_contract",
    "build_directed_c1_pairs",
    "build_generator_contract",
    "build_s_fixture_contract",
    "c1_build_manifest",
    "c1_pair_action_changed",
    "c1_pair_id",
    "c1_pair_rationale_jaccard",
    "c1_pair_sha256",
    "canonical_json_bytes",
    "causal_boundary_manifest",
    "causal_boundary_order",
    "classify_gate_status",
    "deletion_masked_row",
    "hash_order_ascending",
    "hash_sorted_shuffle",
    "insertion_masked_row",
    "jaccard",
    "r_cell_f1",
    "r_structural_exclusions",
    "r_tensor_contract",
    "raw_cell_key",
    "raw_cell_manifest",
    "s_build_world_error_vector",
    "s_error_flag",
    "s_error_index",
    "s_fixture_manifest",
    "s_fixture_seed_bytes",
    "validate_contract",
]
