"""Exclusively publish the result-blind Round 13 V2 preregistration protocol.

V2 is a **result-blind preclaim supersession** of V1.  This freezer:

* binds the already-frozen V1 protocol bytes (``v1_frozen_bytes_sha256``), the
  V1 and V2 specification modules, this freezer, and the V2 tests;
* records the immutable lineage (V1 path / V1 SHA-256 / V1 schema /
  prior_attempt round13_attempt01 / formal_claim_absent / SUPERSEDED_PRECLAIM);
* publishes the V2 protocol to the single canonical output
  ``outputs/validity/round13_synthetic_mtmm_v2_frozen_protocol.json`` using
  canonical compact JSON and exclusive no-overwrite publication;
* refuses when any legacy V1 formal artifact or any V2 formal artifact exists.

Execute with:  python scripts/freeze_round13_synthetic_mtmm_v2_protocol.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any

from arsc_eval.round13_synthetic_mtmm_v2 import (
    FROZEN_PROTOCOL_OUTPUT,
    LINEAGE,
    V1_PROTOCOL_REL,
    V2_BOUND_SOURCE_RELS,
    build_contract,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / FROZEN_PROTOCOL_OUTPUT
V1_FROZEN_PROTOCOL = ROOT / V1_PROTOCOL_REL

# Sources bound by the V2 frozen protocol (V1/V2 spec, V2 freezer, V2 tests),
# derived from the single shared V2_BOUND_SOURCE_RELS tuple so the bound-source
# key set cannot drift between build and verify.
BOUND_SOURCES = tuple(ROOT / relative for relative in V2_BOUND_SOURCE_RELS)


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def sha256_file(path: Path) -> str:
    raw, _identity = stable_read(path, ROOT)
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


def v1_frozen_bytes_sha256(root: Path) -> str:
    """Bind the already-frozen V1 protocol bytes (must exist before freezing V2)."""
    raw, _identity_value = stable_read(root / V1_PROTOCOL_REL, root)
    return hashlib.sha256(raw).hexdigest().upper()


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
    v2_names = (
        "round13_synthetic_mtmm_v2_formal_claim.json",
        "round13_synthetic_mtmm_v2_results.json",
        "round13_synthetic_mtmm_v2_verdict.json",
        "round13_synthetic_mtmm_v2_artifact_index.json",
    )
    legacy_names = (
        "round13_synthetic_mtmm_formal_claim.json",
        "round13_synthetic_mtmm_results.json",
        "round13_synthetic_mtmm_verdict.json",
        "round13_synthetic_mtmm_artifact_index.json",
    )
    if _any_present(root, legacy_names) or _any_present(root, v2_names):
        raise FileExistsError("legacy V1 or V2 formal artifact already exists; V2 preregistration is closed")


def build_frozen_protocol(root: Path) -> dict[str, Any]:
    refuse_if_formal_artifacts(root)
    v1_raw, _v1_identity = stable_read(root / V1_PROTOCOL_REL, root)
    v1_bytes_sha = hashlib.sha256(v1_raw).hexdigest().upper()
    if v1_bytes_sha != LINEAGE["supersedes"]["sha256"]:
        raise ValueError(
            "V1 frozen bytes SHA-256 differs from the awaited lineage digest "
            f"({v1_bytes_sha} != {LINEAGE['supersedes']['sha256']})"
        )
    source_snapshot = {
        path.relative_to(ROOT).as_posix(): stable_read(path, ROOT)
        for path in BOUND_SOURCES
    }
    v1_protocol = json.loads(v1_raw.decode("utf-8"))
    if canonical_json_bytes(v1_protocol) != v1_raw:
        raise ValueError("V1 frozen protocol bytes are not canonical compact JSON")
    v1_spec_rel = "src/arsc_eval/round13_synthetic_mtmm.py"
    expected_v1_spec_sha = v1_protocol["provenance"]["bound_sources"][v1_spec_rel]
    actual_v1_spec_sha = hashlib.sha256(source_snapshot[v1_spec_rel][0]).hexdigest().upper()
    if actual_v1_spec_sha != expected_v1_spec_sha:
        raise ValueError("imported V1 source bytes do not match frozen V1 provenance")
    protocol = build_contract(v1_protocol, include_replacement_orders=True)
    protocol["provenance"] = {
        "bound_sources": {
            relative: hashlib.sha256(snapshot[0]).hexdigest().upper()
            for relative, snapshot in source_snapshot.items()
        },
        "v1_frozen_bytes_sha256": v1_bytes_sha,
        "v2_protocol_schema_sha256": hashlib.sha256(
            canonical_json_bytes(build_contract(v1_protocol, include_replacement_orders=False))
        ).hexdigest().upper(),
    }
    for path in BOUND_SOURCES:
        relative = path.relative_to(ROOT).as_posix()
        after_raw, after_identity = stable_read(path, ROOT)
        before_raw, before_identity = source_snapshot[relative]
        if after_identity != before_identity or after_raw != before_raw:
            raise RuntimeError(f"bound source changed during build: {relative}")
    refuse_if_formal_artifacts(root)
    return protocol


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
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor = os.open(candidate, flags, 0o644)
    try:
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
    finally:
        os.close(descriptor)
    refuse_if_formal_artifacts(root)
    try:
        os.lstat(final_path)
    except FileNotFoundError:
        pass
    else:
        raise FileExistsError(final_path)
    os.link(candidate, final_path)
    published_raw, _published_identity = stable_read(final_path, root)
    if published_raw != payload:
        raise OSError("published protocol verification mismatch")
    os.unlink(candidate)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = Path(os.path.abspath(args.output))
    if output != Path(os.path.abspath(DEFAULT_OUTPUT)):
        raise ValueError("Round13 V2 protocol output path is frozen")
    payload = canonical_json_bytes(build_frozen_protocol(ROOT))
    publish_exclusive(output, payload, root=ROOT)
    print(f"FROZEN {output} bytes={len(payload)} sha256={hashlib.sha256(payload).hexdigest().upper()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
