"""Stage-1 read-only preflight for the Round 13 synthetic MTMM protocol.

This module implements only the deterministic, result-blind checks that a
later reviewer uses to decide whether Round 13 may proceed.  It deliberately
contains no observed metric value, no confidence interval, no gate decision,
and no scientific verdict.  ``PREFLIGHT_STAGE1_PASS`` is an infrastructure
preflight status only: it is neither ``GO_RUN`` nor any two scientific verdicts.

Scope enforced here:

* Verify the tracked frozen protocol path exists, that its exact awaited
  SHA-256 binds it, and that its bytes are the compact canonical JSON
  representation (``sort_keys`` + ``separators=(",", ":")`` + trailing
  newline, as produced by the Round 13 freeze script).
* Verify ``schema_version`` and ``result_blind``, the exact 32 worlds and the
  3072 replacement cells, and that the three bound source files still match
  the ``provenance.bound_sources`` digests recorded inside the protocol.
* Verify that the four reserved formal artifacts (claim/results/verdict/index)
  are still absent on disk so preregistration has not been closed.
* Deterministically enumerate row integers 0..1023 (feature k = bit k),
  evaluate only the frozen eight rule templates with a small hand-written
  evaluator (never ``eval``/``exec``), compile the four action truth bits per
  world, verify the instantiated expressions and rationale supports, and
  return a compact summary with counts and action prevalences.

This module imports nothing and writes nothing.  ``run_preflight`` is pure;
only ``Path``/``hashlib``/``json``/``re`` are used.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable

# Canonical repository paths frozen for Round 13 stage-1 preflight.
PROTOCOL_REL = Path("outputs/validity/round13_synthetic_mtmm_frozen_protocol.json")
BOUND_SOURCES_REL = (
    Path("src/arsc_eval/round13_synthetic_mtmm.py"),
    Path("scripts/freeze_round13_synthetic_mtmm_protocol.py"),
    Path("tests/test_round13_synthetic_mtmm.py"),
)
# Reserved formal artifacts: preregistration is closed if any of these exists.
FORMAL_RESERVED_RELS = (
    Path("outputs/validity/round13_synthetic_mtmm_formal_claim.json"),
    Path("outputs/validity/round13_synthetic_mtmm_results.json"),
    Path("outputs/validity/round13_synthetic_mtmm_verdict.json"),
    Path("outputs/validity/round13_synthetic_mtmm_artifact_index.json"),
)

EXPECTED_PROTOCOL_SHA256 = (
    "7C32F1DB779B1D99FA7118E496196DD325930E169055637639AE66806DF4890C"
)
EXPECTED_PROTOCOL_SCHEMA = "arsc-round13-synthetic-mtmm-protocol-v1"
WORLD_COUNT = 32
ROWS_PER_WORLD = 1024
ACTION_COUNT = 4
REPLACEMENT_CELLS = 3072

# The frozen eight rule templates (RULE_BANK in round13_synthetic_mtmm.py).
RULE_BANK = (
    "x0 AND x1",
    "x0 OR x1",
    "x0 XOR x1",
    "MAJORITY(x0,x1,x2)",
    "x0 AND (x1 OR x2)",
    "(x0 AND x1) OR (x2 AND x3)",
    "PARITY(x0,x1,x2)",
    "MAJORITY(x0,x1,x2,x3)",
)

STATUS_PREFLIGHT_STAGE1_PASS = "PREFLIGHT_STAGE1_PASS"


def require(condition: bool, message: str) -> None:
    """Fail closed unless ``condition`` holds, with an explicit message."""
    if not condition:
        raise ValueError(message)


def canonical_json_bytes(value: Any) -> bytes:
    """Return the Round 13 compact canonical JSON bytes (with trailing LF)."""
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def sha256_file(path: Path) -> str:
    """Return the upper-hex SHA-256 of a regular file."""
    require(not path.is_symlink(), f"path must not be a symlink: {path}")
    require(path.is_file(), f"required regular file missing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


# ---------------------------------------------------------------------------
# Tiny hand-written Boolean-template evaluator (no eval/exec).
# ---------------------------------------------------------------------------
_TOKEN_RE = re.compile(r"\s*(x\d+|[A-Za-z]+|[,()])")


def _tokenize(template: str) -> list[str]:
    tokens: list[str] = []
    position = 0
    while position < len(template):
        match = _TOKEN_RE.match(template, position)
        if not match:
            raise ValueError(f"invalid rule template near: {template[position:]!r}")
        position = match.end()
        tokens.append(match.group(1))
    return tokens


def _eval_atom(tokens: list[str], index: int, values: list[bool]) -> tuple[bool, int]:
    if index >= len(tokens):
        raise ValueError("unexpected end of rule template")
    token = tokens[index]
    if token.startswith("x"):
        variable = int(token[1:])
        if variable >= len(values):
            raise ValueError(f"rule template references x{variable} beyond causal width")
        return values[variable], index + 1
    if token in ("MAJORITY", "PARITY"):
        if index + 1 >= len(tokens) or tokens[index + 1] != "(":
            raise ValueError(f"{token} must open with '('")
        index += 2  # skip MAJORITY/PARITY and '('
        items: list[bool] = []
        while True:
            value, index = _eval_or(tokens, index, values)
            items.append(value)
            if index >= len(tokens):
                raise ValueError("unterminated argument list")
            if tokens[index] == ",":
                index += 1
                continue
            if tokens[index] == ")":
                index += 1
                break
            raise ValueError("expected ',' or ')' in argument list")
        if token == "MAJORITY":
            return items.count(True) > len(items) / 2, index
        return (sum(items) % 2) == 1, index
    if token == "(":
        value, index = _eval_or(tokens, index + 1, values)
        if index >= len(tokens) or tokens[index] != ")":
            raise ValueError("unbalanced parentheses in rule template")
        return value, index + 1
    raise ValueError(f"unexpected token {token!r} in rule template")


def _eval_and(tokens: list[str], index: int, values: list[bool]) -> tuple[bool, int]:
    left, index = _eval_atom(tokens, index, values)
    while index < len(tokens) and tokens[index] == "AND":
        right, index = _eval_atom(tokens, index + 1, values)
        left = left and right
    return left, index


def _eval_xor(tokens: list[str], index: int, values: list[bool]) -> tuple[bool, int]:
    left, index = _eval_and(tokens, index, values)
    while index < len(tokens) and tokens[index] == "XOR":
        right, index = _eval_and(tokens, index + 1, values)
        left = left != right
    return left, index


def _eval_or(tokens: list[str], index: int, values: list[bool]) -> tuple[bool, int]:
    left, index = _eval_xor(tokens, index, values)
    while index < len(tokens) and tokens[index] == "OR":
        right, index = _eval_xor(tokens, index + 1, values)
        left = left or right
    return left, index


def evaluate_template(template: str, values: list[bool]) -> bool:
    """Evaluate one frozen rule template over a row's variable values."""
    tokens = _tokenize(template)
    result, index = _eval_or(tokens, 0, values)
    if index != len(tokens):
        raise ValueError("trailing tokens in rule template")
    return result


def compile_template(template: str) -> Callable[[list[bool]], bool]:
    """Pre-compile a rule template into a callable over a values list."""
    tokens = _tokenize(template)

    def compiled(values: list[bool]) -> bool:
        result, index = _eval_or(tokens, 0, values)
        if index != len(tokens):
            raise ValueError("trailing tokens in rule template")
        return result

    return compiled


def instantiate_expression(template: str, causal: list[int]) -> str:
    """Instantiate a rule template over the world's causal feature indices."""
    return re.sub(r"x(\d+)", lambda match: f"f_{causal[int(match.group(1))]}", template)


def expression_support(expression: str) -> list[int]:
    """Return the sorted feature indices referenced by an instantiated expression."""
    return sorted({int(index) for index in re.findall(r"f_(\d+)", expression)})


def row_feature_bits(row_integer: int, features: list[int]) -> list[bool]:
    """Feature k of a canonical row integer is bit k; return bits for features."""
    return [((row_integer >> feature) & 1) == 1 for feature in features]


# ---------------------------------------------------------------------------
# Protocol verification.
# ---------------------------------------------------------------------------
def verify_protocol_bytes(protocol_path: Path) -> bytes:
    """Verify path, exact SHA-256, and compact canonical JSON round-trip."""
    require(not protocol_path.is_symlink(), "frozen protocol must not be a symlink")
    require(protocol_path.is_file(), f"frozen protocol missing: {protocol_path}")
    raw = protocol_path.read_bytes()
    require(
        hashlib.sha256(raw).hexdigest().upper() == EXPECTED_PROTOCOL_SHA256,
        "frozen protocol SHA-256 differs from the awaited digest",
    )
    # Compact canonical JSON: one trailing LF, no interior whitespace, and a
    # byte-for-byte round-trip through compact canonical re-serialization.
    require(
        raw.endswith(b"\n") and b"\n" not in raw[:-1],
        "frozen protocol is not the compact canonical single-line encoding",
    )
    require(
        canonical_json_bytes(json.loads(raw.decode("utf-8"))) == raw,
        "frozen protocol bytes are not the compact canonical JSON encoding",
    )
    return raw


def verify_protocol_header(protocol: dict[str, Any]) -> None:
    require(
        protocol.get("schema_version") == EXPECTED_PROTOCOL_SCHEMA,
        "protocol schema version differs from the awaited value",
    )
    require(protocol.get("result_blind") is True, "protocol must remain result-blind")


def verify_design_counts(protocol: dict[str, Any]) -> None:
    design = protocol.get("design")
    require(isinstance(design, dict), "protocol design record is missing")
    worlds = design.get("worlds")
    require(isinstance(worlds, list) and len(worlds) == WORLD_COUNT, "world count is not 32")
    for world in worlds:
        require(isinstance(world, dict), "world record must be an object")
        require(world.get("row_count") == ROWS_PER_WORLD, "world row count is not 1024")
        roles = world.get("feature_roles")
        require(
            isinstance(roles, dict)
            and [len(roles[name]) for name in ("causal", "proxy", "nuisance")] == [4, 3, 3],
            "world feature roles are not the 4/3/3 partition",
        )
        templates = world.get("action_rule_templates")
        require(
            isinstance(templates, list) and len(templates) == ACTION_COUNT,
            "world must freeze exactly four action rule templates",
        )
    orders = design.get("replacement_orders")
    require(
        isinstance(orders, list) and len(orders) == REPLACEMENT_CELLS,
        "replacement cell count is not 3072",
    )


def verify_bound_sources(protocol: dict[str, Any], root: Path) -> None:
    provenance = protocol.get("provenance")
    require(isinstance(provenance, dict), "protocol provenance record is missing")
    bound = provenance.get("bound_sources")
    require(isinstance(bound, dict), "protocol bound_sources record is missing")
    require(
        set(bound) == {path.as_posix() for path in BOUND_SOURCES_REL},
        "protocol bound_sources do not match the frozen source allowlist",
    )
    for rel in BOUND_SOURCES_REL:
        source = root / rel
        require(
            sha256_file(source) == str(bound[rel.as_posix()]),
            f"bound source SHA-256 differs: {rel.as_posix()}",
        )


def verify_formal_artifacts_absent(root: Path) -> None:
    for rel in FORMAL_RESERVED_RELS:
        candidate = root / rel
        require(
            not candidate.exists() and not candidate.is_symlink(),
            f"formal artifact already present; preregistration is closed: {rel.as_posix()}",
        )


def verify_world_rules(
    world: dict[str, Any],
) -> list[list[bool]]:
    """Verify instantiated expressions/supports and compile 4 action truth bits/world."""
    causal = world["feature_roles"]["causal"]
    templates = world["action_rule_templates"]
    expressions = world["action_expressions"]
    supports = world["action_rationale_supports"]
    require(
        world.get("action_supports_match_expressions") is True
        or all(world.get("action_supports_match_expressions", [])),
        "world rules fail the expression/support match invariant",
    )
    compiled = []
    for index, template in enumerate(templates):
        require(template in RULE_BANK, f"rule template is not from the frozen bank: {template}")
        expected_expression = instantiate_expression(template, causal)
        require(
            expressions[index] == expected_expression,
            "instantiated expression differs from the frozen protocol",
        )
        require(
            supports[index] == expression_support(expected_expression),
            "rationale support differs from the instantiated expression",
        )
        compiled.append(compile_template(template))
    # Enumerate rows 0..1023 with feature k = bit k; compile 4 action truths.
    per_world_truth: list[list[bool]] = []
    for row_integer in range(ROWS_PER_WORLD):
        bits = row_feature_bits(row_integer, causal)
        truth = [fn(bits) for fn in compiled]
        per_world_truth.append(truth)
    return per_world_truth


def run_preflight(root: Path) -> dict[str, Any]:
    """Run the full stage-1 preflight and return a compact deterministic summary."""
    protocol_root = root.resolve()
    protocol_path = protocol_root / PROTOCOL_REL
    raw = verify_protocol_bytes(protocol_path)
    protocol = json.loads(raw.decode("utf-8"))
    verify_protocol_header(protocol)
    verify_design_counts(protocol)
    verify_bound_sources(protocol, protocol_root)
    verify_formal_artifacts_absent(protocol_root)

    worlds = protocol["design"]["worlds"]
    rule_templates_seen: set[str] = set()
    action_ones_total = 0
    per_action_ones = [0] * ACTION_COUNT
    for world in worlds:
        templates = world["action_rule_templates"]
        rule_templates_seen.update(templates)
        for truth_row in verify_world_rules(world):
            for action in range(ACTION_COUNT):
                per_action_ones[action] += int(truth_row[action])
                action_ones_total += int(truth_row[action])

    total_rows = WORLD_COUNT * ROWS_PER_WORLD
    action_bits_total = ACTION_COUNT * total_rows
    per_action_prevalence = [round(count / total_rows, 9) for count in per_action_ones]
    action_prevalence = round(action_ones_total / action_bits_total, 9)

    return {
        "status": STATUS_PREFLIGHT_STAGE1_PASS,
        "protocol_path": PROTOCOL_REL.as_posix(),
        "protocol_sha256": EXPECTED_PROTOCOL_SHA256,
        "schema_version": protocol.get("schema_version"),
        "result_blind": protocol.get("result_blind"),
        "world_count": len(worlds),
        "rows_per_world": ROWS_PER_WORLD,
        "total_rows": total_rows,
        "replacement_cells": len(protocol["design"]["replacement_orders"]),
        "bound_source_count": len(protocol["provenance"]["bound_sources"]),
        "bound_sources_match": True,
        "formal_artifacts_present": False,
        "rule_templates_covered": len(rule_templates_seen),
        "rule_templates_all_frozen": rule_templates_seen == set(RULE_BANK),
        "instantiated_expressions_verified": True,
        "rationale_supports_verified": True,
        "action_bits_total": action_bits_total,
        "action_ones_total": action_ones_total,
        "action_prevalence": action_prevalence,
        "per_action_ones": per_action_ones,
        "per_action_prevalence": per_action_prevalence,
        "preflight_status_is_only_stage1": True,
    }
