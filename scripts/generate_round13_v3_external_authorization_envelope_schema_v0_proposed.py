"""Generate the proposed, non-authoritative Round 13 V3 external authorization envelope schema.

Package status: **PROPOSED / NOT_GO_RUN**.  This generator and its output are
design-only and non-authoritative: they create no approval, claim, attempt,
consumption, run, or data access of any kind.  Nothing here may be interpreted
as a parseable authorization instance, and no concrete nonce, signature, or
envelope-id is ever produced.

Scope (strict and exclusive):

* This script only **builds, canonicalizes, checks, and (via an explicit flag)
  writes** the proposed canonical JSON Schema document at the single fixed docs
  path derived from this file
  ``docs/design/round13_v3_external_authorization_envelope_schema_v0_proposed.json``.
  There is no caller-selected root or output path; the repository root is always
  ``parents[1]`` of this script.
* It **accepts no envelope payload**: there is no positional CLI input and no
  API that accepts a concrete authorization envelope to build an instance.
* The CLI is read-only by default and for ``--check``: both re-run an exact,
  repeatable byte comparison of the committed fixed docs JSON against the
  deterministic canonical bytes.  Only ``--write-new`` publishes anything, and
  it uses an exclusive ``CREATE_NEW`` open so it can **never overwrite** an
  existing document.  Unknown flags and mutually exclusive flags are rejected.
* It **exposes no instance builder/parser/loader/verifier**, no replay store, no
  ``used`` writer, no claim/writer, no Win32 API, no data access, and no metric
  API.  The public surface is limited to the schema constants plus the pure
  ``build_schema_doc``/``canonical_bytes``/``check_canonical``/``check_fixed_doc``
  helpers and the exclusive ``write_new_fixed_doc`` (write is never reachable by
  default).
* Canonical bytes are deterministic: ``json.dumps(..., sort_keys=True,
  separators=(\",\", \":\"), ensure_ascii=True)`` plus one trailing LF.  No time,
  random, environment, workspace read, or network input is consulted.

The committed schema root is deliberately unsatisfiable under Draft-07: it
carries the sentinel keyword ``"not": {}`` so **every** instance (including an
otherwise structurally conforming envelope) is rejected.  That sentinel is part
of V0 and will be removed only by a separate future authoritative schema, never
by mutating this V0 document.

Run with:
    python scripts/generate_round13_v3_external_authorization_envelope_schema_v0_proposed.py
    python scripts/generate_round13_v3_external_authorization_envelope_schema_v0_proposed.py --check
    python scripts/generate_round13_v3_external_authorization_envelope_schema_v0_proposed.py --write-new
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Fixed repository root and fixed output path (both derived from __file__).
# The caller can never select a root or output path.
# ---------------------------------------------------------------------------
REPO_ROOT: Path = Path(__file__).resolve().parents[1]
DEFAULT_REL = "docs/design/round13_v3_external_authorization_envelope_schema_v0_proposed.json"
SCHEMA_PATH: Path = REPO_ROOT / DEFAULT_REL

# ---------------------------------------------------------------------------
# Schema identity / fixed binding constants (all non-authoritative proposed).
# ---------------------------------------------------------------------------
SCHEMA_ID = "ARSC_ROUND13_V3_EXTERNAL_AUTHORIZATION_ENVELOPE_V0_PROPOSED"
PACKAGE_STATUS_CONST = "PROPOSED_NOT_GO_RUN"
DECISION_CONST = "GO_RUN_V3"
ATTEMPT_CONST = "round13_attempt03"
PROTOCOL_SCHEMA_CONST = "arsc-round13-synthetic-mtmm-protocol-v3"
EVIDENCE_SCHEMA_CONST = "ARSC_ROUND13_SYNTHETIC_MTMM_PREFLIGHT_EVIDENCE_V3"

_HEX64_PATTERN = "^[0-9A-Fa-f]{64}$"

# ---------------------------------------------------------------------------
# The proposed canonical JSON Schema document.  Every object node carries
# ``additionalProperties: false`` (fully closed).  No ``examples``, ``default``,
# ``enum``, concrete instance, nonce, signature, or envelope-id value appears.
#
# The root carries the deliberate unsatisfiable sentinel ``"not": {}``: under
# Draft-07 an empty schema matches every value, so ``not: {}`` rejects every
# instance.  V0 is therefore intentionally unsatisfiable and authorizes nothing.
# Only a separate future authoritative schema - never mutation of V0 - may
# remove that sentinel.
#
# The independent authority authentication metadata is required only as a
# closed *future field shape* (its properties are intentionally empty) and
# must later be fleshed out by a separately frozen and independently reviewed
# authoritative envelope schema.
# ---------------------------------------------------------------------------
SCHEMA_DOC: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "$id": "https://arsc.invalid/round13/v3/external-authorization-envelope/v0-proposed",
    "title": "ARSC Round13 V3 External Authorization Envelope Schema V0 (Proposed, Non-Authoritative)",
    "description": (
        "Non-authoritative PROPOSED schema. This document is design-only and "
        "NOT_GO_RUN; it creates no approval, claim, attempt, consumption, or "
        "data access. It structurally requires the future binding categories "
        "for a one-shot external authorization envelope but carries no concrete "
        "authorization instance, no nonce, no signature, no envelope-id value, "
        "no example, and no default. Independent authority authentication is "
        "expressed only as a required future field shape to be completed by a "
        "separately frozen and independently reviewed authoritative schema. "
        "The root carries the sentinel keyword 'not': {} so that, under "
        "Draft-07, every instance is rejected; only a separate future "
        "authoritative schema may remove that sentinel, never mutation of V0."
    ),
    "type": "object",
    "not": {},
    "properties": {
        "package_status": {"const": PACKAGE_STATUS_CONST},
        "envelope_schema": {"const": SCHEMA_ID},
        "decision": {"const": DECISION_CONST},
        "attempt": {"const": ATTEMPT_CONST},
        "protocol": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "schema": {"const": PROTOCOL_SCHEMA_CONST},
                "sha256": {"type": "string", "pattern": _HEX64_PATTERN},
            },
            "required": ["schema", "sha256"],
        },
        "implementation_identity": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "runner": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "path": {"type": "string"},
                        "sha256": {"type": "string", "pattern": _HEX64_PATTERN},
                    },
                    "required": ["path", "sha256"],
                },
                "runtime": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "version": {"type": "string"},
                        "executable_sha256": {"type": "string", "pattern": _HEX64_PATTERN},
                    },
                    "required": ["version", "executable_sha256"],
                },
            },
            "required": ["runner", "runtime"],
        },
        "neutral_evidence": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "schema": {"const": EVIDENCE_SCHEMA_CONST},
                "digest": {"type": "string", "pattern": _HEX64_PATTERN},
            },
            "required": ["schema", "digest"],
        },
        "independent_authority_authentication": {
            "type": "object",
            "additionalProperties": False,
            "properties": {},
            "required": [],
        },
        "single_use": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "replay_refusal": {"const": True},
                "max_uses": {"const": 1},
            },
            "required": ["replay_refusal", "max_uses"],
        },
    },
    "required": [
        "package_status",
        "envelope_schema",
        "decision",
        "attempt",
        "protocol",
        "implementation_identity",
        "neutral_evidence",
        "independent_authority_authentication",
        "single_use",
    ],
    "additionalProperties": False,
}

__all__ = (
    "DEFAULT_REL",
    "REPO_ROOT",
    "SCHEMA_PATH",
    "SCHEMA_ID",
    "PACKAGE_STATUS_CONST",
    "DECISION_CONST",
    "ATTEMPT_CONST",
    "PROTOCOL_SCHEMA_CONST",
    "EVIDENCE_SCHEMA_CONST",
    "SCHEMA_DOC",
    "build_schema_doc",
    "canonical_bytes",
    "check_canonical",
    "check_fixed_doc",
    "write_new_fixed_doc",
)


def build_schema_doc() -> dict[str, Any]:
    """Return an independent deep copy of the proposed schema document.

    This is a pure builder of the *schema document only*; it never accepts or
    returns a concrete authorization envelope.
    """
    return deepcopy(SCHEMA_DOC)


def canonical_bytes() -> bytes:
    """Return the deterministic canonical JSON bytes for the schema document.

    Deterministic ``json.dumps(sort_keys=True, separators=(\",\", \":\"),
    ensure_ascii=True)`` of ``SCHEMA_DOC`` plus one trailing LF.  No
    time/random/env/workspace/network is consulted.  It accepts no value
    argument: the canonical bytes are always computed for the fixed ``SCHEMA_DOC``.
    """
    return (
        json.dumps(
            SCHEMA_DOC,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def check_canonical(value: Any) -> bytes:
    """Fully validate ``value`` is a faithful schema document and canonicalize.

    It requires ``value`` to be a JSON object equal to ``SCHEMA_DOC`` (deep
    comparison) and returns its canonical bytes.  Raises ``ValueError`` on any
    divergence so a malformed or tampered declaration can never pass.
    """
    if not isinstance(value, dict):
        raise ValueError("schema document must be a JSON object")
    if deepcopy(value) != SCHEMA_DOC:
        raise ValueError("schema document diverges from the proposed SCHEMA_DOC")
    return canonical_bytes()


def check_fixed_doc() -> tuple[bool, bytes]:
    """Read-only, repeatable exact-byte check of the committed fixed docs JSON.

    Returns ``(matches, canonical_payload)`` where ``matches`` is True when the
    existing fixed document equals the deterministic canonical bytes exactly.
    Never writes; safe to repeat.  Raises ``FileNotFoundError`` if the fixed
    document does not exist.
    """
    payload = canonical_bytes()
    existing = SCHEMA_PATH.read_bytes()
    return existing == payload, payload


def _write_exclusive(target: Path, payload: bytes) -> None:
    """Write ``payload`` to ``target`` using exclusive CREATE_NEW no-overwrite.

    The schema doc is design-only and non-authoritative; it is still written
    atomically (single exclusive open, so an existing file is never overwritten)
    and read back and byte-verified so the committed doc always equals the
    deterministic canonical bytes.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor = os.open(target, flags, 0o644)
    try:
        written = 0
        while written < len(payload):
            count = os.write(descriptor, payload[written:])
            if count <= 0:
                raise OSError("zero-byte write while publishing schema document")
            written += count
    finally:
        os.close(descriptor)
    with open(target, "rb") as handle:
        readback = handle.read()
    if readback != payload:
        raise RuntimeError("schema document readback verification mismatch")


def write_new_fixed_doc() -> bytes:
    """Exclusively publish the fixed docs JSON (CREATE_NEW, never overwrite).

    Raises ``FileExistsError`` if the fixed document already exists.  Returns
    the exact canonical bytes that were written (and verified on readback).
    """
    payload = canonical_bytes()
    _write_exclusive(SCHEMA_PATH, payload)
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="generate_round13_v3_external_authorization_envelope_schema_v0_proposed",
        description=(
            "Build/canonicalize/check (read-only) the proposed, non-authoritative "
            "Round 13 V3 envelope schema, optionally publishing it exclusively. "
            "Accepts no envelope payload and no caller-selected root or output "
            "path."
        ),
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--check",
        action="store_true",
        help=(
            "Read-only: verify the fixed docs JSON is byte-exact canonical. "
            "This is also the default behaviour when no flag is given."
        ),
    )
    group.add_argument(
        "--write-new",
        action="store_true",
        help=(
            "Exclusively publish the fixed docs JSON using CREATE_NEW; fails "
            "instead of ever overwriting an existing document."
        ),
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """Execute the generator CLI (build, check, or exclusively publish).

    Accepts no envelope payload.  The default and ``--check`` are read-only,
    repeatable exact-byte checks of the fixed docs JSON.  ``--write-new``
    publishes exclusively and never overwrites.  Unknown flags and mutually
    exclusive flags are rejected by the parser.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.write_new:
        try:
            payload = write_new_fixed_doc()
        except FileExistsError:
            print(
                f"refusing to overwrite existing fixed document at {DEFAULT_REL} "
                "(--write-new never overwrites)"
            )
            return 1
        digest = hashlib.sha256(payload).hexdigest().upper()
        print(
            f"Wrote new proposed schema document {DEFAULT_REL} "
            f"({len(payload)} bytes, sha256 {digest})"
        )
        return 0

    # Default and --check are the same read-only verification path.
    matches, payload = check_fixed_doc()
    digest = hashlib.sha256(payload).hexdigest().upper()
    if matches:
        print(
            f"OK: fixed docs JSON at {DEFAULT_REL} is byte-exact canonical "
            f"({len(payload)} bytes, sha256 {digest})"
        )
        return 0
    print(
        f"MISMATCH: fixed docs JSON at {DEFAULT_REL} differs from canonical bytes "
        f"(expected sha256 {digest})"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
