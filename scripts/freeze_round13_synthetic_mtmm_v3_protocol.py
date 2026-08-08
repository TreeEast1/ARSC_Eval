"""Exclusively publish the result-blind Round 13 V3 preregistration protocol.

V3 is a **result-blind preclaim supersession** of the committed V2 artifact
(commit ``ba00c2e``).  This freezer:

* refuses before build when the fixed V2 input
  ``outputs/validity/round13_synthetic_mtmm_v2_frozen_protocol.json`` byte
  SHA-256 differs from the awaited lineage digest, when the reviewed V3 source
  ``src/arsc_eval/round13_synthetic_mtmm_v3.py`` byte SHA-256 differs from its
  pinned digest, or when any V3 frozen protocol / formal claim / results /
  verdict / index artifact already exists;
* stable-reads the exact V2 input bytes and the bound source bytes, derives the
  V3 contract with ``include_replacement_orders=True`` (V2 worlds/orders are
  never resampled), validates it result-blind, and serializes it with the
  V2 canonical compact-JSON convention; and
* publishes to the single canonical output
  ``outputs/validity/round13_synthetic_mtmm_v3_frozen_protocol.json`` using
  exclusive no-overwrite, atomic-safe publication, then re-reads / re-hashes /
  re-parses / re-validates the written bytes.

Execute with:  python scripts/freeze_round13_synthetic_mtmm_v3_protocol.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import types
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

# --- Local literal constants (result-blind, pinned at review/authoring time) ---
# The fixed V2 frozen-protocol input must byte-match V2_EXPECTED_SHA and carry
# schema V2_EXPECTED_SCHEMA.  These are literal here so the freezer does not
# depend on (or re-import) the V3 specification module merely to check lineage.
V2_PROTOCOL_REL = "outputs/validity/round13_synthetic_mtmm_v2_frozen_protocol.json"
V2_EXPECTED_SHA = "38AF706B42B0CECCED97D3A5925CDE1360ED2C79FB3AE36680DC02E83DB432E5"
V2_EXPECTED_SCHEMA = "arsc-round13-synthetic-mtmm-protocol-v2"

# The single canonical V3 frozen-protocol output path.
FROZEN_PROTOCOL_OUTPUT = "outputs/validity/round13_synthetic_mtmm_v3_frozen_protocol.json"

# The V3 artifact filenames (protocol / formal claim / results / verdict /
# index), exactly matching the V3 specification source constants.  They must all
# be absent before a V3 build.
V3_PROTOCOL_NAME = "round13_synthetic_mtmm_v3_frozen_protocol.json"
V3_FORMAL_CLAIM_NAME = "round13_synthetic_mtmm_v3_formal_claim.json"
V3_FORMAL_RESULTS_NAME = "round13_synthetic_mtmm_v3_results.json"
V3_FORMAL_VERDICT_NAME = "round13_synthetic_mtmm_v3_verdict.json"
V3_FORMAL_INDEX_NAME = "round13_synthetic_mtmm_v3_artifact_index.json"
V3_ARTIFACT_ALLOWLIST = (
    V3_PROTOCOL_NAME,
    V3_FORMAL_CLAIM_NAME,
    V3_FORMAL_RESULTS_NAME,
    V3_FORMAL_VERDICT_NAME,
    V3_FORMAL_INDEX_NAME,
)

DEFAULT_OUTPUT = ROOT / FROZEN_PROTOCOL_OUTPUT
V2_FROZEN_PROTOCOL = ROOT / V2_PROTOCOL_REL

# The reviewed V3 specification source byte digest, pinned at review time.
V3_SOURCE_SHA256 = "34ABBBA5F56FFAD91519A3D74E128EDD37E7C9BBD164BCEF89A0349FA9CC46D6"
V3_SOURCE_REL = "src/arsc_eval/round13_synthetic_mtmm_v3.py"

# The shared, exact tuple of the V3 bound source relative paths.  It binds the
# V1 and V2 specification sources (the transitive import dependency chain of the
# V3 spec), the V3 specification source, this V3 freezer, and the V3 test file.
# The bound-source key set cannot drift between build and verify because both
# derive from this single tuple.  Paths are always derived from ``root`` inside
# each function (never from a global absolute root).
BOUND_SOURCE_RELS = (
    "src/arsc_eval/round13_synthetic_mtmm.py",
    "src/arsc_eval/round13_synthetic_mtmm_v2.py",
    "src/arsc_eval/round13_synthetic_mtmm_v3.py",
    "scripts/freeze_round13_synthetic_mtmm_v3_protocol.py",
    "tests/test_round13_synthetic_mtmm_v3.py",
)


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def sha256_file(path: Path) -> str:
    raw, _identity_value = stable_read(path, ROOT)
    return hashlib.sha256(raw).hexdigest().upper()


def _identity(info: os.stat_result) -> tuple[int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def _is_link_or_reparse(info: os.stat_result) -> bool:
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(info, "st_file_attributes", 0)
    return stat.S_ISLNK(info.st_mode) or bool(reparse and attributes & reparse)


def assert_lexical_path_safe(path: Path, root: Path, *, leaf_may_be_missing: bool = False) -> Path:
    root_abs = Path(os.path.abspath(root))
    path_abs = Path(os.path.abspath(path))
    if os.path.commonpath((str(root_abs), str(path_abs))) != str(root_abs):
        raise ValueError(f"path escapes workspace: {path_abs}")
    relative = path_abs.relative_to(root_abs)
    current = root_abs
    components = (Path("."), *relative.parents[::-1], relative)
    checked: set[Path] = set()
    for component in components:
        candidate = root_abs if component == Path(".") else root_abs / component
        if candidate in checked:
            continue
        checked.add(candidate)
        try:
            info = os.lstat(candidate)
        except FileNotFoundError:
            if leaf_may_be_missing:
                break
            raise
        if _is_link_or_reparse(info):
            raise ValueError(f"symlink/reparse component forbidden: {candidate}")
    return path_abs


def stable_read(path: Path, root: Path) -> tuple[bytes, tuple[int, int, int, int, int]]:
    lexical = assert_lexical_path_safe(path, root)
    before = os.lstat(lexical)
    if _is_link_or_reparse(before) or not stat.S_ISREG(before.st_mode):
        raise ValueError(f"stable regular file required: {lexical}")
    descriptor = os.open(
        lexical,
        os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        opened = os.fstat(descriptor)
        if _identity(opened) != _identity(before):
            raise RuntimeError(f"file identity changed before read: {lexical}")
        blocks: list[bytes] = []
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            blocks.append(block)
        after_handle = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    after_path = os.lstat(lexical)
    if _identity(opened) != _identity(after_handle) or _identity(before) != _identity(after_path):
        raise RuntimeError(f"file identity changed during read: {lexical}")
    raw = b"".join(blocks)
    if len(raw) != before.st_size:
        raise RuntimeError(f"stable read size mismatch: {lexical}")
    return raw, _identity(before)


def safe_unlink_exact(path: Path, root: Path) -> None:
    """Remove exactly ``path`` (a normal, non-reparse regular file inside root).

    Refuses to follow any symlink/reparse component, removes only a regular
    file, and never touches preexisting files it did not create.
    """
    lexical = assert_lexical_path_safe(path, root, leaf_may_be_missing=True)
    info = os.lstat(lexical)
    if _is_link_or_reparse(info) or not stat.S_ISREG(info.st_mode):
        raise ValueError(f"refusing to unlink non-regular/link path: {lexical}")
    os.unlink(lexical)


def _any_present(root: Path, names) -> bool:
    for name in names:
        candidate = assert_lexical_path_safe(
            root / "outputs" / "validity" / name, root, leaf_may_be_missing=True
        )
        try:
            os.lstat(candidate)
        except FileNotFoundError:
            continue
        else:
            return True
    return False


def refuse_if_formal_artifacts(root: Path) -> None:
    """Refuse when any V3 frozen protocol / formal claim / results / verdict /
    index artifact already exists (excluding the not-yet-existing output itself).

    ``V3_ARTIFACT_ALLOWLIST`` is exactly ``(V3_PROTOCOL_NAME,
    *V3_PREFORMAL_ARTIFACT_RELS)``, i.e. the V3 frozen protocol plus the V3
    formal claim / results / verdict / index set required to be absent.
    """
    if _any_present(root, V3_ARTIFACT_ALLOWLIST):
        raise FileExistsError(
            "V3 frozen protocol or V3 formal artifact already exists; "
            "V3 preregistration is closed"
        )


def verify_expected_shas(root: Path) -> tuple[bytes, bytes]:
    """Refuse before build if the fixed V2 input or the reviewed V3 source byte
    SHA-256 differs from its awaited digest.  Returns the stable-read input and
    source bytes for the build to reuse (exact stable read, no re-read races).
    """
    v2_raw, _v2_identity = stable_read(root / V2_PROTOCOL_REL, root)
    v2_bytes_sha = hashlib.sha256(v2_raw).hexdigest().upper()
    if v2_bytes_sha != V2_EXPECTED_SHA:
        raise ValueError(
            "V2 frozen bytes SHA-256 differs from the awaited V2 digest "
            f"({v2_bytes_sha} != {V2_EXPECTED_SHA})"
        )
    v3_raw, _v3_identity = stable_read(root / V3_SOURCE_REL, root)
    v3_bytes_sha = hashlib.sha256(v3_raw).hexdigest().upper()
    if v3_bytes_sha != V3_SOURCE_SHA256:
        raise ValueError(
            "V3 source SHA-256 differs from the pinned reviewed digest "
            f"({v3_bytes_sha} != {V3_SOURCE_SHA256})"
        )
    return v2_raw, v3_raw


def load_verified_v3_module(root: Path) -> types.ModuleType:
    """Verify the awaited digests (V2 input, V1/V2 transitive sources via the
    frozen V2 provenance, V3 source) and then construct the V3 spec module by
    exact-byte compilation and execution.  No importlib normal import and no
    ``sys.path`` use occur here; the V3 source is compiled and exec'd from its
    pinned exact bytes over a synthetic ``arsc_eval`` package, so neither the
    package ``__init__.py``, pyc caches, nor verify-to-import file races can
    affect the loaded module.

    Ordering is strict so the freezer never executes a specification module
    whose source is unverified:
      1. ``verify_expected_shas`` confirms the fixed V2 input bytes and the V3
         source bytes match their pinned digests;
      2. the exact verified V2 input bytes are decoded, required to be canonical
         compact JSON, and required to carry the exact awaited schema and
         result-blind flag;
      3. the frozen V2 ``provenance.bound_sources`` must carry exact SHA-256
         entries for the V1 and V2 specification sources (fail closed on
         missing/malformed);
      4. V1 and V2 sources are stable-read before any execution and byte-hash-
         matched to that authoritative provenance; V2 source is verified/bound
         but is never executed because V3 does not import it;
      5. a synthetic ``arsc_eval`` package (``__path__`` -> ``root/src/arsc_eval``,
         ``__init__.py`` never executed) plus the V1 and V3 modules are inserted
         into ``sys.modules`` and the already-verified exact V1/V3 source bytes
         are ``compile``d (``dont_inherit=True``) and ``exec``'d; V3's absolute
         import resolves the already-executed exact V1 module;
      6. any pre-existing ``sys.modules`` entries for the four exact names are
         restored (or removed if absent) in a ``finally`` even on failure;
      7. after execution, V1/V2/V3 are stable-read again and required to be
         byte- and identity-identical with exact hashes against provenance / the
         pinned V3 digest;
      8. the module's expected literal constants are verified against the local
         pinned constants so the freezer and spec cannot silently diverge.
    """
    v2_raw, v3_raw = verify_expected_shas(root)

    # Decode/parse the exact verified V2 input bytes.  Require canonical bytes,
    # the exact awaited schema, and result-blind, exactly as the build requires.
    v2_protocol = json.loads(v2_raw.decode("utf-8"))
    if canonical_json_bytes(v2_protocol) != v2_raw:
        raise ValueError("V2 frozen protocol bytes are not canonical compact JSON")
    if v2_protocol.get("schema_version") != V2_EXPECTED_SCHEMA:
        raise ValueError("V2 frozen protocol schema does not match the awaited V2 schema")
    if v2_protocol.get("result_blind") is not True:
        raise ValueError("V2 frozen protocol must be result-blind")

    # Read the frozen V2 provenance and require exact bound-source hashes for the
    # transitive V1/V2 specification sources.  Fail closed on missing/malformed
    # provenance so an incomplete record can never authorize an unverified exec.
    v2_provenance = v2_protocol.get("provenance")
    if not isinstance(v2_provenance, dict):
        raise ValueError("V2 frozen protocol provenance is missing or malformed")
    v2_bound_sources = v2_provenance.get("bound_sources")
    if not isinstance(v2_bound_sources, dict):
        raise ValueError(
            "V2 frozen protocol provenance bound_sources is missing or malformed"
        )

    v1_spec_rel = "src/arsc_eval/round13_synthetic_mtmm.py"
    v2_spec_rel = "src/arsc_eval/round13_synthetic_mtmm_v2.py"
    expected_v1_spec_sha = v2_bound_sources.get(v1_spec_rel)
    expected_v2_spec_sha = v2_bound_sources.get(v2_spec_rel)
    if not isinstance(expected_v1_spec_sha, str) or not expected_v1_spec_sha:
        raise ValueError(
            "V2 frozen protocol provenance lacks the V1 spec bound-source hash"
        )
    if not isinstance(expected_v2_spec_sha, str) or not expected_v2_spec_sha:
        raise ValueError(
            "V2 frozen protocol provenance lacks the V2 spec bound-source hash"
        )

    # Before any execution, stable-read the V1/V2 sources under root and
    # byte-hash-match them to the authoritative frozen V2 provenance entries.
    # V2 source is verified/bound but is intentionally never executed because V3
    # does not import it.
    v1_raw, v1_identity = stable_read(root / v1_spec_rel, root)
    v1_bytes_sha = hashlib.sha256(v1_raw).hexdigest().upper()
    if v1_bytes_sha != expected_v1_spec_sha:
        raise ValueError(
            "V1 source SHA-256 differs from the frozen V2 provenance hash "
            f"({v1_bytes_sha} != {expected_v1_spec_sha})"
        )
    v2_source_raw, v2_source_identity = stable_read(root / v2_spec_rel, root)
    v2_source_sha = hashlib.sha256(v2_source_raw).hexdigest().upper()
    if v2_source_sha != expected_v2_spec_sha:
        raise ValueError(
            "V2 source SHA-256 differs from the frozen V2 provenance hash "
            f"({v2_source_sha} != {expected_v2_spec_sha})"
        )
    # Capture the exact V3 source bytes and identity we will execute (already
    # hash-verified against V3_SOURCE_SHA256 by verify_expected_shas), so the
    # post-execution check can require byte- and identity-identity.
    v3_stable_raw, v3_identity = stable_read(root / V3_SOURCE_REL, root)
    if v3_stable_raw != v3_raw:
        raise RuntimeError("V3 source bytes changed after digest verification")

    # Save any existing sys.modules entries for the exact names we are about to
    # (re)bind so they can be restored exactly afterward, even on failure.
    module_labels = (
        "arsc_eval",
        "arsc_eval.round13_synthetic_mtmm",
        "arsc_eval.round13_synthetic_mtmm_v2",
        "arsc_eval.round13_synthetic_mtmm_v3",
    )
    saved_modules = {name: sys.modules.get(name) for name in module_labels}

    v1_path = str(root / v1_spec_rel)
    v3_path = str(root / V3_SOURCE_REL)
    try:
        # Synthetic arsc_eval package: __path__ points at the workspace copy but
        # __init__.py is never executed.
        package = types.ModuleType("arsc_eval")
        package.__path__ = [str(root / "src" / "arsc_eval")]
        package.__package__ = "arsc_eval"
        package.__file__ = str(root / "src" / "arsc_eval" / "__init__.py")
        package.__spec__ = None
        sys.modules["arsc_eval"] = package

        # V1: create the module with correct __file__/__package__, insert it,
        # then compile/exec the exact verified bytes.
        v1_module = types.ModuleType("arsc_eval.round13_synthetic_mtmm")
        v1_module.__file__ = v1_path
        v1_module.__package__ = "arsc_eval"
        v1_module.__spec__ = None
        sys.modules["arsc_eval.round13_synthetic_mtmm"] = v1_module
        exec(compile(v1_raw, v1_path, "exec", dont_inherit=True), v1_module.__dict__)

        # V3: create the module, insert it, then compile/exec the already
        # verified exact bytes.  Its absolute import of the V1 module resolves
        # the already-executed exact V1 module above.
        v3_module = types.ModuleType("arsc_eval.round13_synthetic_mtmm_v3")
        v3_module.__file__ = v3_path
        v3_module.__package__ = "arsc_eval"
        v3_module.__spec__ = None
        sys.modules["arsc_eval.round13_synthetic_mtmm_v3"] = v3_module
        exec(compile(v3_raw, v3_path, "exec", dont_inherit=True), v3_module.__dict__)
    finally:
        # Restore all four prior sys.modules entries exactly (or remove if they
        # were absent before), even on failure.
        for name, prior in saved_modules.items():
            if prior is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prior

    # Re-verify all three sources with fresh stable reads after execution:
    # identity and raw bytes must be unchanged and hashes must be exact.
    after_v1_raw, after_v1_identity = stable_read(root / v1_spec_rel, root)
    if after_v1_identity != v1_identity or after_v1_raw != v1_raw:
        raise RuntimeError("V1 source changed after execution")
    after_v1_sha = hashlib.sha256(after_v1_raw).hexdigest().upper()
    if after_v1_sha != expected_v1_spec_sha:
        raise ValueError(
            "V1 source SHA-256 changed after execution "
            f"({after_v1_sha} != {expected_v1_spec_sha})"
        )
    after_v2_raw, after_v2_identity = stable_read(root / v2_spec_rel, root)
    if after_v2_identity != v2_source_identity or after_v2_raw != v2_source_raw:
        raise RuntimeError("V2 source changed after execution")
    after_v2_sha = hashlib.sha256(after_v2_raw).hexdigest().upper()
    if after_v2_sha != expected_v2_spec_sha:
        raise ValueError(
            "V2 source SHA-256 changed after execution "
            f"({after_v2_sha} != {expected_v2_spec_sha})"
        )
    after_v3_raw, after_v3_identity = stable_read(root / V3_SOURCE_REL, root)
    if after_v3_identity != v3_identity or after_v3_raw != v3_raw:
        raise RuntimeError("V3 source changed after execution")
    after_v3_sha = hashlib.sha256(after_v3_raw).hexdigest().upper()
    if after_v3_sha != V3_SOURCE_SHA256:
        raise ValueError(
            "V3 source SHA-256 changed after execution "
            f"({after_v3_sha} != {V3_SOURCE_SHA256})"
        )

    expected_constants = {
        "V2_PROTOCOL_REL": (v3_module.V2_PROTOCOL_REL, V2_PROTOCOL_REL),
        "V2_PROTOCOL_SHA256": (v3_module.V2_PROTOCOL_SHA256, V2_EXPECTED_SHA),
        "V2_SCHEMA": (v3_module.V2_SCHEMA, V2_EXPECTED_SCHEMA),
        "FROZEN_PROTOCOL_OUTPUT": (v3_module.FROZEN_PROTOCOL_OUTPUT, FROZEN_PROTOCOL_OUTPUT),
        "V3_PROTOCOL_NAME": (v3_module.V3_PROTOCOL_NAME, V3_PROTOCOL_NAME),
        "FORMAL_CLAIM_NAME": (v3_module.FORMAL_CLAIM_NAME, V3_FORMAL_CLAIM_NAME),
        "FORMAL_RESULTS_NAME": (v3_module.FORMAL_RESULTS_NAME, V3_FORMAL_RESULTS_NAME),
        "FORMAL_VERDICT_NAME": (v3_module.FORMAL_VERDICT_NAME, V3_FORMAL_VERDICT_NAME),
        "FORMAL_INDEX_NAME": (v3_module.FORMAL_INDEX_NAME, V3_FORMAL_INDEX_NAME),
    }
    for name, (module_value, expected_value) in expected_constants.items():
        if module_value != expected_value:
            raise ValueError(
                f"V3 module constant {name} does not match the pinned freezer value "
                f"({module_value!r} != {expected_value!r})"
            )
    return v3_module


def _build_contract_with_provenance(
    root: Path, module: types.ModuleType, v2_raw: bytes, v2_bytes_sha: str
) -> dict[str, Any]:
    """Build (and validate) the V3 contract with replacement orders, then attach
    the provenance record.  This is the non-refusing core shared by both the
    build and the post-publication verifier.  ``module`` is the verified V3 spec
    module (see ``load_verified_v3_module``); its ``build_contract`` is used for
    schema / contract construction so the freezer never calls an unverified copy.
    """
    v2_protocol = json.loads(v2_raw.decode("utf-8"))
    if canonical_json_bytes(v2_protocol) != v2_raw:
        raise ValueError("V2 frozen protocol bytes are not canonical compact JSON")
    if v2_protocol.get("schema_version") != V2_EXPECTED_SCHEMA:
        raise ValueError("V2 frozen protocol schema does not match the awaited V2 schema")
    if v2_protocol.get("result_blind") is not True:
        raise ValueError("V2 frozen protocol must be result-blind")

    bound_sources = tuple(root / relative for relative in BOUND_SOURCE_RELS)
    source_snapshot = {
        path.relative_to(root).as_posix(): stable_read(path, root) for path in bound_sources
    }

    # Immediately after the stable source_snapshot is created, cross-check the
    # already-verified frozen V2 provenance bound_sources against the snapshot:
    # snapshot V1 and V2 specification sources must byte-hash-match their exact
    # provenance hashes and the snapshot V3 source must byte-hash-match the
    # pinned reviewed digest.  This runs before any contract is built or any
    # provenance is written.  Fail closed on missing/malformed hashes so an
    # incomplete provenance record can never authorize an unverified build or
    # provenance write.
    v2_prov = v2_protocol.get("provenance")
    if not isinstance(v2_prov, dict):
        raise ValueError("V2 frozen protocol provenance is missing or malformed")
    v2_bound_sources = v2_prov.get("bound_sources")
    if not isinstance(v2_bound_sources, dict):
        raise ValueError(
            "V2 frozen protocol provenance bound_sources is missing or malformed"
        )
    v1_spec_rel = "src/arsc_eval/round13_synthetic_mtmm.py"
    v2_spec_rel = "src/arsc_eval/round13_synthetic_mtmm_v2.py"
    expected_v1_spec_sha = v2_bound_sources.get(v1_spec_rel)
    if not isinstance(expected_v1_spec_sha, str) or not expected_v1_spec_sha:
        raise ValueError(
            "V2 frozen protocol provenance lacks the V1 spec bound-source hash"
        )
    expected_v2_spec_sha = v2_bound_sources.get(v2_spec_rel)
    if not isinstance(expected_v2_spec_sha, str) or not expected_v2_spec_sha:
        raise ValueError(
            "V2 frozen protocol provenance lacks the V2 spec bound-source hash"
        )
    actual_v1_spec_sha = hashlib.sha256(source_snapshot[v1_spec_rel][0]).hexdigest().upper()
    if actual_v1_spec_sha != expected_v1_spec_sha:
        raise ValueError(
            "imported V1 source bytes do not match frozen V2 provenance "
            f"({actual_v1_spec_sha} != {expected_v1_spec_sha})"
        )
    actual_v2_spec_sha = hashlib.sha256(source_snapshot[v2_spec_rel][0]).hexdigest().upper()
    if actual_v2_spec_sha != expected_v2_spec_sha:
        raise ValueError(
            "imported V2 source bytes do not match frozen V2 provenance "
            f"({actual_v2_spec_sha} != {expected_v2_spec_sha})"
        )
    actual_v3_spec_sha = hashlib.sha256(source_snapshot[V3_SOURCE_REL][0]).hexdigest().upper()
    if actual_v3_spec_sha != V3_SOURCE_SHA256:
        raise ValueError(
            "V3 source bytes do not match the pinned reviewed digest "
            f"({actual_v3_spec_sha} != {V3_SOURCE_SHA256})"
        )

    protocol = module.build_contract(v2_protocol, include_replacement_orders=True)
    module.validate_contract(protocol, v2_protocol, require_orders=True)
    protocol["provenance"] = {
        "bound_sources": {
            relative: hashlib.sha256(snapshot[0]).hexdigest().upper()
            for relative, snapshot in source_snapshot.items()
        },
        "v2_frozen_bytes_sha256": v2_bytes_sha,
        "v3_protocol_schema_sha256": hashlib.sha256(
            canonical_json_bytes(module.build_contract(v2_protocol, include_replacement_orders=False))
        ).hexdigest().upper(),
    }
    for path in bound_sources:
        relative = path.relative_to(root).as_posix()
        after_raw, after_identity = stable_read(path, root)
        before_raw, before_identity = source_snapshot[relative]
        if after_identity != before_identity or after_raw != before_raw:
            raise RuntimeError(f"bound source changed during build: {relative}")
    return protocol


def build_frozen_protocol(root: Path) -> dict[str, Any]:
    refuse_if_formal_artifacts(root)
    v2_raw, _v3_raw = verify_expected_shas(root)
    v2_bytes_sha = hashlib.sha256(v2_raw).hexdigest().upper()
    module = load_verified_v3_module(root)
    protocol = _build_contract_with_provenance(root, module, v2_raw, v2_bytes_sha)
    refuse_if_formal_artifacts(root)
    return protocol


def _safe_candidate_cleanup(path: Path, root: Path) -> None:
    """Remove exactly ``path`` without following its final leaf component.

    Every ancestor must be lexically safe (no symlink/reparse component,
    verified via ``assert_lexical_path_safe`` on the parent chain).  The exact
    candidate leaf may have been replaced by a symlink/reparse since creation --
    ``os.unlink`` never follows the leaf, so a replaced leaf is unlinked anyway
    -- but it must not be a directory.  Existence is optional: an already-
    removed candidate is a successful no-op.
    """
    assert_lexical_path_safe(path.parent, root)
    lexical = Path(os.path.abspath(path))
    try:
        info = os.lstat(lexical)
    except FileNotFoundError:
        return
    if stat.S_ISDIR(info.st_mode):
        raise ValueError(f"refusing to unlink directory candidate: {lexical}")
    os.unlink(lexical)


def publish_exclusive(path: Path, payload: bytes, *, root: Path = ROOT) -> None:
    final_path = assert_lexical_path_safe(path, root, leaf_may_be_missing=True)
    parent = assert_lexical_path_safe(final_path.parent, root)
    if not stat.S_ISDIR(os.lstat(parent).st_mode):
        raise ValueError(f"output parent is not a directory: {parent}")
    try:
        os.lstat(final_path)
    except FileNotFoundError:
        pass
    else:
        raise FileExistsError(final_path)
    candidate = final_path.with_name(f".{final_path.name}.candidate.tmp")
    assert_lexical_path_safe(candidate, root, leaf_may_be_missing=True)
    descriptor = None
    candidate_created = False
    final_created = False
    opened_identity = None
    try:
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        descriptor = os.open(candidate, flags, 0o644)
        candidate_created = True
        written = 0
        while written < len(payload):
            count = os.write(descriptor, payload[written:])
            if count <= 0:
                raise OSError("zero-byte write during exclusive publication")
            written += count
        os.fsync(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        verified = bytearray()
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            verified.extend(block)
        if bytes(verified) != payload:
            raise OSError("candidate verification mismatch")

        # Hold the descriptor open through the link and post-link verification
        # so the candidate identity is anchored to the exact file that was
        # written and verified above.
        opened = os.fstat(descriptor)
        if _is_link_or_reparse(opened) or not stat.S_ISREG(opened.st_mode):
            raise OSError(f"candidate is not a regular non-reparse file: {candidate}")
        if opened.st_nlink != 1:
            raise OSError(f"candidate nlink is not 1 before link: {opened.st_nlink}")
        opened_identity = _identity(opened)

        # Preserve O_EXCL / no-overwrite: re-refuse formal artifacts and any
        # preexisting final immediately before the hardlink.
        refuse_if_formal_artifacts(root)
        try:
            os.lstat(final_path)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError(final_path)

        # Immediately after refuse_if_formal_artifacts and before os.link,
        # re-lstat the path-level candidate and require it is still the exact
        # regular non-reparse nlink=1 file held open by the descriptor.
        before_link = os.lstat(candidate)
        if _identity(before_link) != opened_identity:
            raise RuntimeError(f"candidate identity changed before link: {candidate}")
        if _is_link_or_reparse(before_link) or not stat.S_ISREG(before_link.st_mode):
            raise RuntimeError(
                f"candidate not regular non-reparse before link: {candidate}"
            )
        if before_link.st_nlink != 1:
            raise RuntimeError(f"candidate nlink is not 1 before link: {before_link.st_nlink}")

        os.link(candidate, final_path)
        final_created = True

        candidate_after = os.lstat(candidate)
        final_after = os.lstat(final_path)
        if _identity(candidate_after) != opened_identity or _identity(final_after) != opened_identity:
            raise RuntimeError(
                f"linked identity mismatch (candidate={candidate} final={final_path})"
            )
        if _is_link_or_reparse(candidate_after) or not stat.S_ISREG(candidate_after.st_mode):
            raise RuntimeError(f"candidate not regular non-reparse after link: {candidate}")
        if _is_link_or_reparse(final_after) or not stat.S_ISREG(final_after.st_mode):
            raise RuntimeError(f"final not regular non-reparse after link: {final_path}")
        if candidate_after.st_nlink != 2 or final_after.st_nlink != 2:
            raise RuntimeError(
                f"linked nlink is not 2 (candidate={candidate_after.st_nlink}, final={final_after.st_nlink})"
            )

        published_raw, published_identity = stable_read(final_path, root)
        if published_identity != opened_identity:
            raise RuntimeError(f"published identity differs from opened candidate: {final_path}")
        if published_raw != payload:
            raise OSError("published protocol verification mismatch")

        # Close the descriptor before unlinking the candidate so the exact file
        # written and verified above is fully closed on the success path.  The
        # file is already fully verified and published, but a close error here is
        # still treated as a hard failure (never swallowed); descriptor is only
        # cleared after the close succeeds so the failure handler can retry it.
        if descriptor is not None:
            os.close(descriptor)
            descriptor = None

        # Unlink the candidate leaf (exact, no-follow).  A success-path unlink
        # error is a hard failure, never swallowed.
        _safe_candidate_cleanup(candidate, root)
        candidate_created = False

        final_final = os.lstat(final_path)
        if _identity(final_final) != opened_identity:
            raise RuntimeError(f"final identity changed after candidate unlink: {final_path}")
        if _is_link_or_reparse(final_final) or not stat.S_ISREG(final_final.st_mode):
            raise RuntimeError(f"final not regular non-reparse after unlink: {final_path}")
        if final_final.st_nlink != 1:
            raise RuntimeError(f"final nlink is not 1 after candidate unlink: {final_final.st_nlink}")

        return
    except BaseException as original_error:
        # Best-effort descriptor close so a close error never blocks unlink
        # cleanup.  Unlink cleanup failures are collected, not silently dropped.
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
            descriptor = None
        failures: list[tuple[Path, Exception]] = []
        # ``final_created`` is True exactly when this invocation's os.link
        # succeeded (os.link refuses when the final already exists), so the
        # final is provably ours to remove.  Remove it with no-follow lexical
        # safety (via _safe_candidate_cleanup) even if its path-level identity
        # now differs from the opened candidate identity (e.g. a replaced or
        # swapped leaf); a preexisting final is never touched because final_created
        # is only set after a success that could not have linked over a preexisting
        # final.  The final and candidate cleanups are attempted independently
        # and their failures aggregated below.
        if final_created:
            try:
                _safe_candidate_cleanup(final_path, root)
            except Exception as exc:
                failures.append((final_path, exc))
        # Candidate cleanup tolerates a replaced leaf (no-follow), never a dir.
        if candidate_created:
            try:
                _safe_candidate_cleanup(candidate, root)
            except Exception as exc:
                failures.append((candidate, exc))
        if failures:
            raise RuntimeError(
                f"cleanup failed after publish error; failures={failures!r}"
            ) from original_error
        raise


def verify_frozen_protocol(root: Path, expected_payload: bytes) -> None:
    """Re-read / re-hash / re-parse / re-validate the published V3 frozen protocol.

    This is called only after the file exists, so it uses the non-refusing build
    core plus the awaited digests rather than ``build_frozen_protocol`` (which
    would refuse on the now-present output artifact).
    """
    raw = stable_read(root / FROZEN_PROTOCOL_OUTPUT, root)[0]
    if raw != expected_payload:
        raise OSError("published protocol verification mismatch after write")
    if hashlib.sha256(raw).hexdigest().upper() != hashlib.sha256(expected_payload).hexdigest().upper():
        raise OSError("published protocol SHA-256 mismatch after write")
    parsed = json.loads(raw.decode("utf-8"))
    if canonical_json_bytes(parsed) != raw:
        raise ValueError("published protocol bytes are not canonical compact JSON")
    v2_raw, _v3_raw = verify_expected_shas(root)
    v2_bytes_sha = hashlib.sha256(v2_raw).hexdigest().upper()
    module = load_verified_v3_module(root)
    rebuilt = _build_contract_with_provenance(root, module, v2_raw, v2_bytes_sha)
    if canonical_json_bytes(rebuilt) != raw:
        raise ValueError("published protocol does not match the rebuilt expected contract")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = Path(os.path.abspath(args.output))
    if output != Path(os.path.abspath(DEFAULT_OUTPUT)):
        raise ValueError("Round13 V3 protocol output path is frozen")
    payload = canonical_json_bytes(build_frozen_protocol(ROOT))
    publish_exclusive(output, payload, root=ROOT)
    try:
        verify_frozen_protocol(ROOT, payload)
    except BaseException as postwrite_error:
        # publish_exclusive already refused a preexisting final, so the final
        # here is the one this invocation created; remove it together with the
        # candidate before propagating the verification failure.  The final and
        # candidate cleanups are attempted independently so an OSError on the
        # first never prevents the second; any cleanup failures are aggregated
        # and reported after both attempts have run.
        candidate = output.with_name(f".{output.name}.candidate.tmp")
        cleanup_failures: list[tuple[Path, Exception]] = []
        for doomed in (output, candidate):
            try:
                safe_unlink_exact(doomed, ROOT)
            except (FileNotFoundError, ValueError):
                pass
            except OSError as exc:
                cleanup_failures.append((doomed, exc))
        if cleanup_failures:
            raise RuntimeError(
                f"cleanup failed after postverify error; failures={cleanup_failures!r}"
            ) from postwrite_error
        raise
    print(f"FROZEN {output} bytes={len(payload)} sha256={hashlib.sha256(payload).hexdigest().upper()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
