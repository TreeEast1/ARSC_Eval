"""Result-blind Gate 0 authorization for the Round 12 existing-outputs analysis.

This is the standalone Round 12 formal-runner driver.  Before any metric value, bootstrap
draw, or NPZ payload is ever loaded, it verifies that an independent reviewer
has frozen an execution decision (``GO_RUN_ROUND12_FORMAL_ATTEMPT01``) that
binds the exact on-disk bytes (SHA-256) of the runner, the Round 12 core and
canonical metrics modules, the runner/core test modules, the frozen Round 12
protocol, the scientific direction decision and the protocol prereview
decision, and the two Round 10 NPZ input archives.

Contract / boundaries enforced here:

* Result-blind and fail-closed: nothing reads NumPy payloads.  No ``numpy``
  module is imported and ``numpy.load`` is never reached.  ``authorize_before_data_access``
  only computes SHA-256 hashes of whole files and parses JSON documents.
  ``sha256_file`` and ``read_json`` reject symlinks and non-regular files.
* No forbidden access: DAAD-X, model/checkpoint/inference and image code paths
  are never imported or touched.
* The future GO_RUN JSON, the scientific direction decision, and the future
  protocol prereview decision are referenced by constant but are NOT required
  to exist at import time; authorization raises if any of them is absent.
  The runner/core test modules are only hash-bound when the GO_RUN JSON binds
  them (fail closed if the bound path is absent).
* The GO_RUN bindings list must contain exactly one entry per canonical binding
  key; duplicate keys are rejected before insertion and a length mismatch
  fails closed.
* After authorization succeeds, the runner lazily loads only frozen allowlisted
  primitive arrays, invokes the frozen pure statistics/serialization layers,
  and publishes the five reserved outputs with staging, rollback, and the
  artifact index last. Existing outputs are never overwritten.

Only ``main`` (found under ``__main__``) performs the gate and the stop; importing
this module has no side effects and touches no data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
from pathlib import Path
from typing import Any, Mapping, Sequence


# ---------------------------------------------------------------------------
# Canonical repository paths (frozen forward-looking contracts).
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]

# Future independent execution authorization issued by the Round 12 analysis
# runner's execution reviewer.  Absent today; must exist when a formal run is
# attempted.
GO_RUN_PATH = ROOT / "outputs/validity/round12_analysis_runner_reviewer_decision.json"

# Frozen Round 12 protocol produced by scripts/freeze_round12_existing_outputs_protocol.py.
PROTOCOL_PATH = (
    ROOT / "outputs/validity/round12_existing_outputs_frozen_protocol.json"
)

# Scientific-direction reviewer decision consumed by the freeze step
# (GO_FREEZE_ONE_ANALYSIS).  It selected the single direction; it does NOT by
# itself authorize implementation execution.
DIRECTION_DECISION_PATH = (
    ROOT / "outputs/validity/round12_existing_outputs_reviewer_decision.json"
)

# Subsequent independent prereview of the *frozen* result-blind protocol
# (GO_IMPLEMENT_ROUND12_RESULT_BLIND).  Authorizes implementing the frozen
# protocol; still distinct from the runner execution GO.
PROTOCOL_PREREVIEW_PATH = (
    ROOT / "outputs/validity/round12_frozen_protocol_reviewer_decision.json"
)

# Existing Round 10 formal outputs that Round 12 re-analyzes (structurally
# inspected and hash-bound only; values are never loaded here).
PRIMITIVES_PATH = (
    ROOT
    / "outputs/validity/round10_corruption_formal_attempt02"
    / "round10_corruption_primitives.npz"
)
DRAWS_PATH = (
    ROOT
    / "outputs/validity/round10_corruption_formal_attempt02"
    / "round10_corruption_bootstrap_draws.npz"
)

# Round 12 existing-outputs core statistics module.
ROUND12_CORE_PATH = ROOT / "src/arsc_eval/round12_existing_outputs.py"

# Canonical metrics helpers reused by the Round 12 core.
CANONICAL_METRICS_PATH = ROOT / "src/arsc_eval/corruption_statistics.py"

# Future independent runner tests for this module (may not exist yet).
RUNNER_TESTS_PATH = ROOT / "tests/test_run_round12_existing_outputs_analysis.py"

# Core statistics module tests (present; hash-bound when the GO_RUN binds them).
CORE_TESTS_PATH = ROOT / "tests/test_round12_existing_outputs.py"

OUTPUT_SERIALIZER_PATH = ROOT / "src/arsc_eval/round12_output_serializers.py"
OUTPUT_SERIALIZER_TESTS_PATH = ROOT / "tests/test_round12_output_serializers.py"

RUNNER_PATH = Path(__file__).resolve()

# ---------------------------------------------------------------------------
# Fixed authorization schema / decision identifiers.
# ---------------------------------------------------------------------------
GO_RUN_SCHEMA = "ARSC_ROUND12_ANALYSIS_RUNNER_REVIEWER_DECISION_V1"
GO_RUN_DECISION = "GO_RUN_ROUND12_FORMAL_ATTEMPT01"
PROTOCOL_STATUS = "FROZEN_RESULT_BLIND_PROTOCOL_ONLY"
DIRECTION_DECISION = "GO_FREEZE_ONE_ANALYSIS"
PROTOCOL_PREREVIEW_DECISION = "GO_IMPLEMENT_ROUND12_RESULT_BLIND"

# Exact canonical binding keys -> the on-disk path each one must resolve to.
# Fail closed: the GO_RUN bindings list must contain exactly one entry per key
# (duplicates rejected before insertion), every key must appear, and the on-disk
# SHA-256 at that path must match the binding value.
BINDING_KEYS: tuple[str, ...] = (
    "runner",
    "round12-core",
    "canonical-metrics",
    "runner-tests",
    "core-tests",
    "output-serializer",
    "output-serializer-tests",
    "frozen-protocol",
    "direction-decision",
    "protocol-prereview",
    "primitives",
    "draws",
)
BINDING_PATHS: Mapping[str, Path] = {
    "runner": RUNNER_PATH,
    "round12-core": ROUND12_CORE_PATH,
    "canonical-metrics": CANONICAL_METRICS_PATH,
    "runner-tests": RUNNER_TESTS_PATH,
    "core-tests": CORE_TESTS_PATH,
    "output-serializer": OUTPUT_SERIALIZER_PATH,
    "output-serializer-tests": OUTPUT_SERIALIZER_TESTS_PATH,
    "frozen-protocol": PROTOCOL_PATH,
    "direction-decision": DIRECTION_DECISION_PATH,
    "protocol-prereview": PROTOCOL_PREREVIEW_PATH,
    "primitives": PRIMITIVES_PATH,
    "draws": DRAWS_PATH,
}


# ---------------------------------------------------------------------------
# Small read / hash / assert helpers (stdlib only).
# ---------------------------------------------------------------------------
def require(condition: bool, message: str) -> None:
    """Fail closed unless ``condition`` holds, with an explicit message."""
    if not condition:
        raise ValueError(message)


def require_regular_file(path: Path) -> None:
    """Fail closed unless ``path`` is an existing regular (non-symlink) file."""
    require(not path.is_symlink(), f"path must not be a symlink: {path}")
    require(path.is_file(), f"required regular file missing: {path}")


def sha256_file(path: Path) -> str:
    """Return the upper-hex SHA-256 of ``path``, failing if it is not a file."""
    require_regular_file(path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def relative(path: Path) -> str:
    """Return the repo-relative canonical POSIX path for a path inside ROOT."""
    return path.resolve().relative_to(ROOT).as_posix()


def read_json(path: Path) -> dict[str, Any]:
    """Read a UTF-8 JSON object, failing closed on malformed or non-object JSON."""
    require_regular_file(path)
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    require(isinstance(value, dict), f"expected a JSON object: {relative(path)}")
    return value


def validate_protocol_gate(protocol: Mapping[str, Any]) -> None:
    """Fail unless the frozen Round 12 protocol is still result-blind and idle.

    Formal execution may only proceed against a protocol that has not yet run:
    status ``FROZEN_RESULT_BLIND_PROTOCOL_ONLY``, ``result_blind`` true, and no
    formal run / outcome / bootstrap already recorded in ``execution``.
    """
    require(
        protocol.get("status") == PROTOCOL_STATUS,
        "protocol is not the frozen result-blind protocol",
    )
    require(
        protocol.get("result_blind") is True,
        "protocol is not result-blind",
    )
    execution = protocol.get("execution")
    require(isinstance(execution, dict), "protocol execution record missing")
    require(
        execution.get("formal_run") is False,
        "protocol already marks a formal run as executed",
    )
    require(
        execution.get("outcome_computed") is False,
        "protocol already marks the outcome as computed",
    )
    require(
        execution.get("bootstrap_executed") is False,
        "protocol already marks bootstrap execution",
    )


def _validate_sha256_hex(value: str) -> None:
    """Fail closed unless ``value`` is a canonical 64-char hex SHA-256."""
    require(
        len(value) == 64
        and all(ch in "0123456789abcdefABCDEF" for ch in value),
        f"SHA-256 digest must be 64 hex characters: {value!r}",
    )


def protocol_npz_entries(protocol: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """Validate and return the two frozen NPZ allowlist entries (no NPZ reads)."""
    inputs = protocol.get("inputs")
    require(isinstance(inputs, Mapping), "protocol inputs record is missing")
    keyed = inputs.get("npz_allowlists")
    require(isinstance(keyed, Mapping), "protocol NPZ allowlists are missing")
    expected_paths = {relative(PRIMITIVES_PATH), relative(DRAWS_PATH)}
    require(set(keyed) == expected_paths, "protocol NPZ allowlist paths mismatch")
    validated: dict[str, Mapping[str, Any]] = {}
    for path_text in sorted(expected_paths):
        entry = keyed[path_text]
        require(isinstance(entry, Mapping), f"invalid NPZ allowlist entry: {path_text}")
        items = entry.get("items")
        require(isinstance(items, list), f"NPZ allowlist items missing: {path_text}")
        require(entry.get("key_count") == len(items), f"NPZ key_count mismatch: {path_text}")
        keys: list[str] = []
        for item in items:
            require(isinstance(item, Mapping), f"invalid NPZ item: {path_text}")
            key = item.get("key")
            require(isinstance(key, str) and bool(key), f"invalid NPZ item key: {path_text}")
            require(key not in keys, f"duplicate NPZ item key {key!r}: {path_text}")
            require(isinstance(item.get("shape"), list), f"NPZ item shape missing: {key}")
            require(isinstance(item.get("dtype"), str), f"NPZ item dtype missing: {key}")
            keys.append(key)
        sha = entry.get("sha256")
        require(isinstance(sha, str), f"NPZ protocol SHA missing: {path_text}")
        _validate_sha256_hex(sha)
        validated[path_text] = entry
    return validated


def validate_protocol_npz_hashes(protocol: Mapping[str, Any]) -> None:
    """Bind the reviewed protocol's archive hashes to current whole-file bytes."""
    entries = protocol_npz_entries(protocol)
    for path in (PRIMITIVES_PATH, DRAWS_PATH):
        expected = str(entries[relative(path)]["sha256"]).upper()
        require(
            sha256_file(path) == expected,
            f"NPZ SHA differs from frozen protocol: {relative(path)}",
        )


def _listed_bindings_for_bindings_map(
    document: Mapping[str, Any],
) -> dict[str, tuple[str, str]]:
    """Return {key: (canonical_path, expected_sha256)} from the bindings list.

    The bindings list must contain exactly one entry per canonical binding key
    (length 10, every canonical key present, no duplicates), each with a
    nonempty path and a canonical 64-char hex SHA-256.  Any structural or
    content violation fails closed before any on-disk hash is computed.
    """
    raw = document.get("bindings")
    require(
        isinstance(raw, list) and len(raw) == len(BINDING_KEYS),
        "GO_RUN bindings must contain exactly "
        f"{len(BINDING_KEYS)} entries (one per canonical key)",
    )
    result: dict[str, tuple[str, str]] = {}
    for entry in raw:
        require(isinstance(entry, dict), "GO_RUN binding entry must be an object")
        key_text = entry.get("key")
        require(
            isinstance(key_text, str) and key_text in BINDING_KEYS,
            f"GO_RUN binding key must be one of {BINDING_KEYS}: {key_text!r}",
        )
        require(
            key_text not in result,
            f"duplicate GO_RUN binding key: {key_text!r}",
        )
        path_text = entry.get("path")
        require(
            isinstance(path_text, str) and bool(path_text.strip()),
            f"GO_RUN binding path must be nonempty for key {key_text!r}",
        )
        sha_text = str(entry.get("sha256", ""))
        _validate_sha256_hex(sha_text)
        result[key_text] = (path_text, sha_text)
    return result


# ---------------------------------------------------------------------------
# Authorization gate (before any data access).
# ---------------------------------------------------------------------------
def authorize_before_data_access() -> None:
    """Verify the full GO_RUN execution contract and protocol gate.

    Raises (fail closed) on any of:

    * missing / malformed GO_RUN JSON,
    * unexpected GO_RUN schema or decision,
    * a binding set that is not exactly the ten canonical keys (one entry each,
      unique, with a nonempty path and a canonical 64-hex SHA-256),
    * any on-disk SHA-256 differing from the bound value (including the NPZ
      archives and the future tests, if bound),
    * any binding path resolving outside the repository,
    * a protocol that is not still ``FROZEN_RESULT_BLIND_PROTOCOL_ONLY``,
      not result-blind, or that already records formal computation.
    """
    go_run = read_json(GO_RUN_PATH)
    require(
        go_run.get("schema_version") == GO_RUN_SCHEMA,
        "unexpected GO_RUN schema",
    )
    require(
        go_run.get("decision") == GO_RUN_DECISION,
        "reviewer does not authorize the Round 12 formal attempt01 run",
    )
    require(go_run.get("result_blind") is True, "GO_RUN must be result_blind")
    require(
        go_run.get("execution_scope")
        == {
            "attempt": "attempt01",
            "maximum_formal_executions": 1,
            "formal_run_authorized": True,
        },
        "GO_RUN execution_scope must authorize exactly one formal attempt01",
    )

    listed = _listed_bindings_for_bindings_map(go_run)
    require(
        set(listed) == set(BINDING_KEYS),
        "GO_RUN bindings do not cover exactly the canonical ten keys",
    )
    for key in BINDING_KEYS:
        canonical, expected = listed[key]
        path = BINDING_PATHS[key]
        require(
            relative(path) == canonical,
            f"GO_RUN binding path for {key!r} differs from canonical "
            f"{canonical!r}",
        )
        actual = sha256_file(path)
        require(
            actual == expected.upper(),
            f"SHA-256 mismatch for {key!r} {canonical}: {actual}",
        )

    # Protocol gate: the frozen protocol must still be result-blind and idle.
    protocol = read_json(PROTOCOL_PATH)
    validate_protocol_gate(protocol)
    validate_protocol_npz_hashes(protocol)

    # Direction reviewer decision (GO_FREEZE): validates the scientific result-
    # blind direction decision recognized by the freeze step.  Validation here
    # is separate from, and in addition to, the structural GO_RUN hash binding.
    direction = read_json(DIRECTION_DECISION_PATH)
    require(
        isinstance(direction.get("schema_version"), str)
        and direction.get("decision") == DIRECTION_DECISION,
        "direction reviewer decision is not the expected GO_FREEZE decision",
    )

    # Protocol prereview decision (GO_IMPLEMENT): a distinct, subsequent
    # independent prereview authorizing implementation of the *frozen*
    # result-blind protocol.  It is still distinct from the runner execution GO.
    prereview = read_json(PROTOCOL_PREREVIEW_PATH)
    require(
        isinstance(prereview.get("schema_version"), str)
        and prereview.get("decision") == PROTOCOL_PREREVIEW_DECISION,
        "protocol prereview decision is not the expected GO_IMPLEMENT decision",
    )

    # The frozen protocol's authorization must bind the direction decision
    # (path and digest) so execution is gated on the exact reviewed direction.
    authorization = protocol.get("authorization") or {}
    decision_path = authorization.get("decision_path")
    decision_sha = authorization.get("decision_sha256")
    require(
        isinstance(decision_path, str)
        and decision_path == relative(DIRECTION_DECISION_PATH),
        "frozen protocol does not bind the expected direction decision path",
    )
    require(
        isinstance(decision_sha, str)
        and decision_sha.upper() == sha256_file(DIRECTION_DECISION_PATH),
        "frozen protocol does not bind the direction decision digest",
    )


def validate_npz_headers_after_authorization(
    path: Path, entry: Mapping[str, Any]
) -> None:
    """Compare every frozen array shape/dtype using NPY headers only."""
    import zipfile

    import numpy as np

    require_regular_file(path)
    items = entry["items"]
    expected_members = [str(item["key"]) + ".npy" for item in items]
    with zipfile.ZipFile(path, mode="r") as archive:
        actual_members = archive.namelist()
        require(
            len(actual_members) == len(set(actual_members)),
            f"duplicate NPZ ZIP member: {relative(path)}",
        )
        require(
            set(actual_members) == set(expected_members),
            f"NPZ member set differs from frozen protocol: {relative(path)}",
        )
        for item in items:
            key = str(item["key"])
            with archive.open(key + ".npy", mode="r") as stream:
                version = np.lib.format.read_magic(stream)
                require(
                    version in {(1, 0), (2, 0)},
                    f"unsupported NPY header version for {key}: {version}",
                )
                if version == (1, 0):
                    shape, _fortran_order, dtype = np.lib.format.read_array_header_1_0(stream)
                else:
                    shape, _fortran_order, dtype = np.lib.format.read_array_header_2_0(stream)
            require(
                tuple(item["shape"]) == tuple(shape),
                f"NPZ shape differs from frozen protocol: {key}",
            )
            require(
                str(item["dtype"]) == str(dtype),
                f"NPZ dtype differs from frozen protocol: {key}",
            )


def load_formal_inputs_after_authorization(
    protocol: Mapping[str, Any],
    primitives_path: Path = PRIMITIVES_PATH,
    draws_path: Path = DRAWS_PATH,
) -> dict[str, Any]:
    """Load and bundle the Round 12 formal NPZ inputs after authorization.

    The authorization gate has already bound the exact on-disk bytes of the
    primitive and draw archives, so this loader may safely read their NumPy
    payloads.  It verifies the exact archived key set against the frozen
    protocol's expected per-archive items, then copies only
    ``REQUIRED_INPUT_KEYS`` from the primitives archive and the three bootstrap
    draw arrays into a fresh bundle (a plain ``dict``), never exposing the raw
    ``NpzFile`` handles outside the function.
    """
    import numpy as np

    from arsc_eval.round12_existing_outputs import REQUIRED_INPUT_KEYS

    keyed = protocol["inputs"]["npz_allowlists"]
    require(relative(primitives_path) in keyed, "primitives allowlist entry missing")
    require(relative(draws_path) in keyed, "draws allowlist entry missing")

    validate_npz_headers_after_authorization(
        primitives_path, keyed[relative(primitives_path)]
    )
    validate_npz_headers_after_authorization(draws_path, keyed[relative(draws_path)])

    bundle: dict[str, Any] = {}

    with np.load(primitives_path, allow_pickle=False) as primitives:
        expected_primitives = {
            str(item["key"])
            for item in keyed[relative(primitives_path)]["items"]
        }
        require(
            set(primitives.files) == expected_primitives,
            "primitives archive key set differs from the frozen protocol",
        )
        for key in REQUIRED_INPUT_KEYS:
            require(key in primitives.files, f"missing required input key: {key}")
            bundle[key] = np.array(primitives[key], copy=True)

    with np.load(draws_path, allow_pickle=False) as draws:
        expected_draws = {
            str(item["key"])
            for item in keyed[relative(draws_path)]["items"]
        }
        require(
            set(draws.files) == expected_draws,
            "draws archive key set differs from the frozen protocol",
        )
        draw_keys = (
            "seed_position_draws",
            "clip_position_draws",
            "expanded_image_counts",
        )
        for key in draw_keys:
            require(key in draws.files, f"missing draw array: {key}")
            bundle[key] = np.array(draws[key], copy=True)

    return bundle


# ---------------------------------------------------------------------------
# One-shot formal output publication (called only after authorization).
# ---------------------------------------------------------------------------
FORMAL_OUTPUT_RELATIVE_PATHS: tuple[Path, ...] = (
    Path("outputs/validity/round12_existing_outputs_results.json"),
    Path("outputs/validity/round12_existing_outputs_point_diagnostics.csv"),
    Path("outputs/validity/round12_existing_outputs_component_draws.npz"),
    Path("outputs/validity/round12_existing_outputs_artifact_index.json"),
    Path("outputs/validity/round12_existing_outputs_protocol.log"),
)
ATTEMPT_CLAIM_RELATIVE_PATH = Path(
    "outputs/validity/.round12_existing_outputs_attempt01.claim"
)
FORMAL_PUBLISH_ORDER: tuple[Path, ...] = (
    FORMAL_OUTPUT_RELATIVE_PATHS[0],
    FORMAL_OUTPUT_RELATIVE_PATHS[1],
    FORMAL_OUTPUT_RELATIVE_PATHS[2],
    FORMAL_OUTPUT_RELATIVE_PATHS[4],
    FORMAL_OUTPUT_RELATIVE_PATHS[3],  # index is the commit marker and is last
)


def preflight_formal_outputs_absent(*, root: Path = ROOT) -> None:
    """Fail before formal data access unless every target/temp is absent."""
    root = root.resolve()
    parent = root / "outputs" / "validity"
    require(parent.exists() and parent.is_dir(), "formal output directory is missing")
    require(not parent.is_symlink(), "formal output directory must not be a symlink")
    claim = root / ATTEMPT_CLAIM_RELATIVE_PATH
    require(
        not claim.exists() and not claim.is_symlink(),
        "Round 12 attempt01 claim already exists; stale claims require human audit",
    )
    for relative_path in FORMAL_OUTPUT_RELATIVE_PATHS:
        target = root / relative_path
        require(target.parent == parent, f"formal target escaped output directory: {relative_path}")
        require(
            not target.exists() and not target.is_symlink(),
            f"formal target already exists: {relative_path}",
        )
        legacy_temporary = target.with_name(target.name + ".tmp.round12_attempt01")
        require(
            not legacy_temporary.exists() and not legacy_temporary.is_symlink(),
            f"formal temporary already exists: {legacy_temporary.name}",
        )
        require(
            not any(parent.glob(target.name + ".tmp.round12_attempt01.*")),
            f"owned formal temporary already exists for: {target.name}",
        )


def acquire_attempt_claim(*, root: Path = ROOT) -> str:
    """Atomically reserve the sole formal attempt before any NPZ access.

    The claim is intentionally retained after both success and failure.  A
    stale claim therefore stops automatically and requires human audit rather
    than silently permitting a second formal computation.
    """
    preflight_formal_outputs_absent(root=root)
    root = root.resolve()
    claim = root / ATTEMPT_CLAIM_RELATIVE_PATH
    token = secrets.token_hex(16)
    require(
        len(token) == 32 and all(character in "0123456789abcdef" for character in token),
        "generated claim token is invalid",
    )
    try:
        with claim.open("xb") as stream:
            stream.write((token + "\n").encode("ascii"))
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise ValueError(
            "Round 12 attempt01 claim already exists; concurrent/stale attempt blocked"
        ) from error
    _fsync_directory(claim.parent)
    return token


def require_attempt_claim(*, root: Path, token: str) -> Path:
    """Verify that ``token`` owns the fixed, persistent attempt claim."""
    require(
        isinstance(token, str)
        and len(token) == 32
        and all(character in "0123456789abcdef" for character in token),
        "claim token must be 32 lowercase hex characters",
    )
    claim = root.resolve() / ATTEMPT_CLAIM_RELATIVE_PATH
    require_regular_file(claim)
    require(claim.read_bytes() == (token + "\n").encode("ascii"), "attempt claim token mismatch")
    return claim


def _fsync_directory(path: Path) -> None:
    """Best-effort directory fsync; unsupported on some Windows filesystems."""
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def publish_formal_payloads_transaction(
    payloads: Mapping[Path, bytes],
    *,
    root: Path = ROOT,
    claim_token: str,
    replace_func: Any = os.link,
) -> None:
    """Publish exactly five outputs with staging and rollback on failure.

    No existing target is overwritten.  All bytes are durably staged before
    the first rename; the artifact index is renamed last as the commit marker.
    A caught failure removes every target created by this attempt and every
    temporary sibling before propagating the original exception.
    """
    require(isinstance(payloads, Mapping), "payloads must be a mapping")
    normalized: dict[Path, bytes] = {}
    for raw_path, raw_bytes in payloads.items():
        require(isinstance(raw_path, Path), "payload path keys must be Path objects")
        normalized[raw_path] = raw_bytes
    require(
        set(normalized) == set(FORMAL_OUTPUT_RELATIVE_PATHS),
        "formal payload paths differ from the exact frozen output set",
    )
    for path, payload in normalized.items():
        require(isinstance(payload, bytes), f"formal payload must be bytes: {path}")

    root = root.resolve()
    require_attempt_claim(root=root, token=claim_token)
    parent = root / "outputs" / "validity"
    require(parent.exists() and parent.is_dir(), "formal output directory is missing")
    require(not parent.is_symlink(), "formal output directory must not be a symlink")

    targets = {relative_path: root / relative_path for relative_path in FORMAL_OUTPUT_RELATIVE_PATHS}
    temporaries = {
        relative_path: target.with_name(
            target.name + ".tmp.round12_attempt01." + claim_token
        )
        for relative_path, target in targets.items()
    }
    for relative_path, target in targets.items():
        require(target.parent == parent, f"formal target escaped output directory: {relative_path}")
        require(not target.exists() and not target.is_symlink(), f"formal target already exists: {relative_path}")
        temporary = temporaries[relative_path]
        require(
            not temporary.exists() and not temporary.is_symlink(),
            f"formal temporary already exists: {temporary.name}",
        )

    owned_temporaries: list[Path] = []
    published: list[Path] = []
    try:
        for relative_path in FORMAL_OUTPUT_RELATIVE_PATHS:
            temporary = temporaries[relative_path]
            with temporary.open("xb") as stream:
                owned_temporaries.append(temporary)
                stream.write(normalized[relative_path])
                stream.flush()
                os.fsync(stream.fileno())

        for relative_path in FORMAL_PUBLISH_ORDER:
            temporary = temporaries[relative_path]
            target = targets[relative_path]
            # The default hard-link publish is atomic and refuses an existing
            # target, unlike os.replace which could overwrite a racing writer.
            replace_func(temporary, target)
            published.append(target)
            if temporary.exists():
                temporary.unlink()
        _fsync_directory(parent)
    except BaseException:
        cleanup_failures: list[str] = []
        for path in reversed(published):
            try:
                if path.exists() or path.is_symlink():
                    path.unlink()
            except OSError as error:
                cleanup_failures.append(f"{path}: {error}")
        for path in owned_temporaries:
            try:
                if path.exists() or path.is_symlink():
                    path.unlink()
            except OSError as error:
                cleanup_failures.append(f"{path}: {error}")
        _fsync_directory(parent)
        if cleanup_failures:
            raise RuntimeError("formal output rollback incomplete: " + "; ".join(cleanup_failures))
        raise


# ---------------------------------------------------------------------------
# Entry point (no CLI arguments).
# ---------------------------------------------------------------------------
def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse invocation arguments.

    There are deliberately no CLI options: the runner always authorizes against
    the one canonical GO_RUN document and frozen protocol paths, so an operator
    cannot redirect or weaken the gate through a caller-supplied path.
    """
    parser = argparse.ArgumentParser()
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    parse_args(argv)
    authorize_before_data_access()
    claim_token = acquire_attempt_claim(root=ROOT)

    # Everything outcome-bearing is imported/read strictly after authorization.
    from arsc_eval.round12_existing_outputs import round12_statistics
    from arsc_eval.round12_output_serializers import build_formal_payloads

    protocol = read_json(PROTOCOL_PATH)
    bundle = load_formal_inputs_after_authorization(protocol)
    seed_position_draws = bundle.pop("seed_position_draws")
    clip_position_draws = bundle.pop("clip_position_draws")
    expanded_image_counts = bundle.pop("expanded_image_counts")
    statistics = round12_statistics(
        bundle,
        seed_position_draws,
        clip_position_draws,
        expanded_image_counts=expanded_image_counts,
        expected_replicates=5000,
    )

    # Revalidate every reviewed byte immediately before building/publishing
    # provenance, catching mutations that occurred after the initial gate.
    authorize_before_data_access()

    binding_records = [
        {
            "key": key,
            "path": relative(BINDING_PATHS[key]),
            "sha256": sha256_file(BINDING_PATHS[key]),
        }
        for key in BINDING_KEYS
    ]
    provenance = {
        "go_run_decision": GO_RUN_DECISION,
        "go_run_path": relative(GO_RUN_PATH),
        "go_run_sha256": sha256_file(GO_RUN_PATH),
        "bindings": binding_records,
    }
    input_bindings = {
        "frozen_protocol": binding_records[BINDING_KEYS.index("frozen-protocol")],
        "primitives": binding_records[BINDING_KEYS.index("primitives")],
        "draws": binding_records[BINDING_KEYS.index("draws")],
    }
    payloads = build_formal_payloads(statistics, provenance, input_bindings)
    publish_formal_payloads_transaction(payloads, root=ROOT, claim_token=claim_token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
