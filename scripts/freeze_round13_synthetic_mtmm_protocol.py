"""Exclusively publish the result-blind Round 13 preregistration protocol."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from arsc_eval.round13_synthetic_mtmm import build_contract

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "outputs/validity/round13_synthetic_mtmm_frozen_protocol.json"
FORMAL_RESERVED = (
    ROOT / "outputs/validity/round13_synthetic_mtmm_formal_claim.json",
    ROOT / "outputs/validity/round13_synthetic_mtmm_results.json",
    ROOT / "outputs/validity/round13_synthetic_mtmm_verdict.json",
    ROOT / "outputs/validity/round13_synthetic_mtmm_artifact_index.json",
)
BOUND_SOURCES = (
    ROOT / "src/arsc_eval/round13_synthetic_mtmm.py",
    ROOT / "scripts/freeze_round13_synthetic_mtmm_protocol.py",
    ROOT / "tests/test_round13_synthetic_mtmm.py",
)


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"required bound source missing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def build_frozen_protocol() -> dict[str, Any]:
    if any(path.exists() for path in FORMAL_RESERVED):
        raise FileExistsError("formal claim/result artifact already exists; preregistration is closed")
    protocol = build_contract(include_replacement_orders=True)
    protocol["provenance"] = {
        "bound_sources": {
            path.relative_to(ROOT).as_posix(): sha256_file(path) for path in BOUND_SOURCES
        },
        "protocol_schema_sha256": hashlib.sha256(
            canonical_json_bytes(build_contract(include_replacement_orders=False))
        ).hexdigest().upper(),
    }
    return protocol


def publish_exclusive(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags, 0o644)
    try:
        written = 0
        while written < len(payload):
            count = os.write(descriptor, payload[written:])
            if count <= 0:
                raise OSError("zero-byte write during exclusive publication")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()
    if output != DEFAULT_OUTPUT.resolve():
        raise ValueError("Round13 protocol output path is frozen")
    payload = canonical_json_bytes(build_frozen_protocol())
    publish_exclusive(output, payload)
    print(f"FROZEN {output} bytes={len(payload)} sha256={hashlib.sha256(payload).hexdigest().upper()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
