"""Tests for the proposed, non-authoritative Round 13 V3 envelope schema generator.

These tests operate on **synthetic schema metadata only**.  They:

* load the generator script as a module **without** executing ``main()`` and
  never write to any real workspace path;
* check **exact byte reproduction** of the committed docs JSON against the
  generator's deterministic canonical bytes, and **repeated byte equality**;
* verify every JSON Schema object node is fully closed
  (``additionalProperties: false``);
* verify every required binding (decision ``GO_RUN_V3``, attempt
  ``round13_attempt03``, protocol schema+sha256, neutral evidence
  schema+digest, implementation/runtime identity, single-use/replay-refusal,
  and the empty future authority-authentication shape);
* assert the **absence** of ``examples``/``default``/``enum`` and forbidden
  concrete authorization-instance values (no nonce/signature/envelope-id
  value, no instance/claim/approval key);
* assert the generator exposes **no instance/claim/replay/used/Win32/data/
  metric** APIs or imports, and that no output is emitted under
  ``outputs/`` (outside formal outputs);
* assert the committed neutral runner (`round13_v3_runner.py`) **never imports
  or consumes** the generator or the schema.

Because the generator has **no** CLI schema-output path, these tests do not run
the writer at all: they exercise only the pure bytes (and the committed fixed
document, read-only).
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import inspect
import json
import os
import subprocess
import sys
import time
from copy import deepcopy
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]

GENERATOR_REL = (
    "scripts/generate_round13_v3_external_authorization_envelope_schema_v0_proposed.py"
)
SCHEMA_REL = "docs/design/round13_v3_external_authorization_envelope_schema_v0_proposed.json"
RUNNER_REL = "src/arsc_eval/round13_v3_runner.py"


def _load_generator():
    """Load the generator script as a module without executing main()."""
    spec = importlib.util.spec_from_file_location(
        "_proposed_envelope_schema_generator", ROOT / GENERATOR_REL
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not create module spec for the generator script")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GEN = _load_generator()
COMMITTED_RAW = (ROOT / SCHEMA_REL).read_bytes()
COMMITTED_DOC = json.loads(COMMITTED_RAW.decode("utf-8"))


# ---------------------------------------------------------------------------
# (1) Exact reproduction and repeated byte equality against the committed doc.
# ---------------------------------------------------------------------------
def test_committed_json_is_exactly_the_generator_canonical_bytes() -> None:
    expected = GEN.canonical_bytes()
    assert COMMITTED_RAW == expected
    # The committed file must be strictly canonical (single LF, no BOM, no
    # trailing whitespace beyond the single LF).
    assert COMMITTED_RAW.endswith(b"\n")
    assert COMMITTED_RAW.count(b"\n") == 1
    assert not COMMITTED_RAW.startswith(b"\xef\xbb\xbf")


def test_repeated_byte_equality_is_stable() -> None:
    first = GEN.canonical_bytes()
    second = GEN.canonical_bytes()
    third = GEN.canonical_bytes()
    assert first == second == third
    assert len(first) == len(COMMITTED_RAW)
    assert hashlib.sha256(first).hexdigest() == hashlib.sha256(COMMITTED_RAW).hexdigest()


# ---------------------------------------------------------------------------
# (2) Fully closed objects: every JSON Schema object node has
#     ``additionalProperties: false``.
# ---------------------------------------------------------------------------
def _walk_dicts(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk_dicts(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_dicts(item)


def test_every_json_schema_object_is_fully_closed() -> None:
    for node in _walk_dicts(GEN.SCHEMA_DOC):
        if node.get("type") == "object" or "properties" in node or "required" in node:
            assert node.get("additionalProperties") is False, (
                f"object node not closed with additionalProperties=false: {node}"
            )
    # Root is an object and must be closed too.
    assert GEN.SCHEMA_DOC.get("additionalProperties") is False


# ---------------------------------------------------------------------------
# (3) Required bindings.
# ---------------------------------------------------------------------------
def test_required_bindings_are_present_and_exact() -> None:
    doc = GEN.SCHEMA_DOC
    prop = doc["properties"]

    assert doc["type"] == "object"
    required = set(doc["required"])
    assert {
        "package_status",
        "envelope_schema",
        "decision",
        "attempt",
        "protocol",
        "implementation_identity",
        "neutral_evidence",
        "independent_authority_authentication",
        "single_use",
    } <= required

    # Decision and package status constrained as const.
    assert prop["package_status"]["const"] == "PROPOSED_NOT_GO_RUN"
    assert prop["envelope_schema"]["const"] == GEN.SCHEMA_ID
    assert prop["decision"]["const"] == "GO_RUN_V3"
    assert prop["attempt"]["const"] == "round13_attempt03"

    # Protocol: schema + sha256.  Neutral evidence: schema + digest.
    protocol = prop["protocol"]
    assert set(protocol["required"]) == {"schema", "sha256"}
    assert protocol["properties"]["schema"]["const"] == (
        "arsc-round13-synthetic-mtmm-protocol-v3"
    )
    assert protocol["properties"]["sha256"]["pattern"] == "^[0-9A-Fa-f]{64}$"

    evidence = prop["neutral_evidence"]
    assert set(evidence["required"]) == {"schema", "digest"}
    assert evidence["properties"]["schema"]["const"] == (
        "ARSC_ROUND13_SYNTHETIC_MTMM_PREFLIGHT_EVIDENCE_V3"
    )
    assert evidence["properties"]["digest"]["pattern"] == "^[0-9A-Fa-f]{64}$"

    # Implementation identity: runner path+sha256, runtime version+exe sha256.
    ident = prop["implementation_identity"]
    assert set(ident["required"]) == {"runner", "runtime"}
    runner = ident["properties"]["runner"]
    runtime = ident["properties"]["runtime"]
    assert set(runner["required"]) == {"path", "sha256"}
    assert runner["properties"]["sha256"]["pattern"] == "^[0-9A-Fa-f]{64}$"
    assert set(runtime["required"]) == {"version", "executable_sha256"}
    assert runtime["properties"]["executable_sha256"]["pattern"] == "^[0-9A-Fa-f]{64}$"

    # Independent authority authentication is a required future field shape.
    auth = prop["independent_authority_authentication"]
    assert auth["type"] == "object"
    assert auth["additionalProperties"] is False
    assert auth["properties"] == {}
    assert auth["required"] == []
    assert "independent_authority_authentication" in required

    # Single-use / replay-refusal semantics.
    single = prop["single_use"]
    assert set(single["required"]) == {"replay_refusal", "max_uses"}
    assert single["properties"]["replay_refusal"]["const"] is True
    assert single["properties"]["max_uses"]["const"] == 1


# ---------------------------------------------------------------------------
# (4) Absence of examples/default/enum and forbidden concrete instance values.
# ---------------------------------------------------------------------------
def test_no_examples_default_or_enum_anywhere() -> None:
    for node in _walk_dicts(GEN.SCHEMA_DOC):
        assert "examples" not in node, f"forbidden examples key: {node}"
        assert "example" not in node, f"forbidden example key: {node}"
        assert "default" not in node, f"forbidden default key: {node}"
        assert "enum" not in node, f"forbidden enum key: {node}"


def test_no_concrete_nonce_signature_or_envelope_id_key() -> None:
    # No property key anywhere is a nonce / signature / concrete envelope-id.
    # This is the structural (key-based) check only; no raw JSON substring scan
    # of the canonical bytes is performed.
    for node in _walk_dicts(GEN.SCHEMA_DOC):
        for key in node:
            assert key not in {
                "nonce",
                "signature",
                "envelope_id",
                "envelope-id",
                "envelope_id_value",
                "instance",
                "claim",
                "approval",
            }, f"forbidden concrete auth key present: {key}"


def test_authority_auth_is_only_an_empty_future_shape() -> None:
    # Independent authority authentication is a required closed *future field
    # shape*: its properties are intentionally empty.  Note that the root schema
    # carries the unsatisfiable sentinel ``"not": {}``, so under Draft-07 every
    # instance (including any envelope-shaped body built for this field) is
    # rejected — the field is a structural placeholder awaiting a separate
    # future authoritative schema.
    auth = GEN.SCHEMA_DOC["properties"]["independent_authority_authentication"]
    assert auth["properties"] == {}
    assert auth["required"] == []
    assert auth["additionalProperties"] is False
    # The root is unsatisfiable under Draft-07.
    assert GEN.SCHEMA_DOC.get("not") == {}


def test_root_schema_has_exact_not_key_with_empty_object() -> None:
    # The root deliberately carries the sentinel keyword ``"not": {}`` so that
    # under Draft-07 every instance is rejected.  It must be an exact empty
    # object, not absent and not containing a rule.
    assert "not" in GEN.SCHEMA_DOC
    assert GEN.SCHEMA_DOC["not"] == {}
    assert type(GEN.SCHEMA_DOC["not"]) is dict
    assert list(GEN.SCHEMA_DOC["not"].keys()) == []


def test_draft7_rejects_all_synthetic_values() -> None:
    # The proposed root is unsatisfiable under Draft-07: ``"not": {}`` rejects
    # every instance.  Feed only arbitrary synthetic values (not an
    # envelope-shaped object) and assert the Draft7Validator rejects each one.
    validator = jsonschema.Draft7Validator(GEN.SCHEMA_DOC)
    synthetic_values = [
        None,
        0,
        "",
        [],
        {},
        {"unrelated": "metadata"},
    ]
    for bad in synthetic_values:
        errors = list(validator.iter_errors(bad))
        assert errors, f"expected Draft-07 rejection for synthetic value: {bad!r}"


# ---------------------------------------------------------------------------
# (5) Generator source: no instance/claim/replay/used/Win32/data/metric APIs
#     or imports.
# ---------------------------------------------------------------------------
_FORBIDDEN_IMPORT_PREFIXES = ("win32", "ctypes", "data", "metrics", "metric", "arsc_eval")
_FORBIDDEN_DEFINED_NAMES = {
    "build_envelope",
    "parse_envelope",
    "load_envelope",
    "verify_envelope",
    "validate_envelope",
    "create_envelope",
    "replay_store",
    "used_writer",
    "mark_used",
    "claim_writer",
    "claim",
    "write_used",
}


def test_generator_source_has_no_forbidden_imports_or_apis() -> None:
    source = (ROOT / GENERATOR_REL).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(ROOT / GENERATOR_REL))

    import_names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                import_names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                import_names.append(node.module)

    for name in import_names:
        assert not name.startswith(_FORBIDDEN_IMPORT_PREFIXES), (
            f"forbidden import: {name}"
        )

    # No defined function/class/method name matches a forbidden API term.
    defined_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            defined_names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            defined_names.add(node.name)
    assert not _FORBIDDEN_DEFINED_NAMES.intersection(defined_names), (
        f"forbidden API defined in generator: {_FORBIDDEN_DEFINED_NAMES & defined_names}"
    )


# ---------------------------------------------------------------------------
# (6) Outside formal outputs: the generator never writes under outputs/.
# ---------------------------------------------------------------------------
def test_generator_output_is_outside_formal_outputs() -> None:
    assert Path(SCHEMA_REL).parts[:2] == ("docs", "design")
    assert "outputs" not in Path(SCHEMA_REL).parts
    assert GEN.DEFAULT_REL == SCHEMA_REL
    # No write path in the generator may descend into outputs/valdity.
    assert GEN.DEFAULT_REL.split("/")[0] == "docs"
    assert "outputs" not in GEN.DEFAULT_REL


# ---------------------------------------------------------------------------
# (7) The committed neutral runner never imports or consumes the generator or
#     the proposed schema.
# ---------------------------------------------------------------------------
def test_runner_never_imports_or_consumes_generator_or_schema() -> None:
    runner_source = (ROOT / RUNNER_REL).read_text(encoding="utf-8")
    assert "round13_v3_external_authorization_envelope_schema_v0_proposed" not in runner_source
    assert "generate_round13_v3_external_authorization_envelope_schema_v0_proposed" not in runner_source
    # No import reference to the generator module name either.
    tree = ast.parse(runner_source, filename=str(ROOT / RUNNER_REL))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "external_authorization_envelope" not in alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                assert "external_authorization_envelope" not in node.module


# ---------------------------------------------------------------------------
# (8) build_schema_doc / check_canonical behave purely and round-trip.
# ---------------------------------------------------------------------------
def test_build_and_check_round_trip_against_committed() -> None:
    built = GEN.build_schema_doc()
    assert built == GEN.SCHEMA_DOC
    assert built is not GEN.SCHEMA_DOC  # independent deep copy
    # check_canonical accepts a faithful copy and reproduces committed bytes.
    assert GEN.check_canonical(COMMITTED_DOC) == COMMITTED_RAW
    assert GEN.check_canonical(built) == COMMITTED_RAW
    # Tampering is rejected.
    tampered = deepcopy(built)
    tampered["properties"]["decision"]["const"] = "MALFORMED"
    with pytest.raises(ValueError):
        GEN.check_canonical(tampered)


# ---------------------------------------------------------------------------
# (9) Zero-parameter signatures and the exact fixed docs/design path.
# ---------------------------------------------------------------------------
def test_canonical_bytes_takes_zero_parameters() -> None:
    signature = inspect.signature(GEN.canonical_bytes)
    assert len(signature.parameters) == 0


def test_write_new_fixed_doc_takes_zero_parameters() -> None:
    signature = inspect.signature(GEN.write_new_fixed_doc)
    assert len(signature.parameters) == 0


def test_default_rel_is_exact_fixed_docs_design_path() -> None:
    assert GEN.DEFAULT_REL == SCHEMA_REL
    assert Path(SCHEMA_REL).parts[:2] == ("docs", "design")


# ---------------------------------------------------------------------------
# (10) CLI boundary: read-only modes keep the fixed docs byte- and mtime-identical.
# ---------------------------------------------------------------------------
def _run_generator(*argv: str):
    """Run the generator as a subprocess from the repo root, bytecode-off."""
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, GENERATOR_REL, *argv],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def _assert_docs_unchanged(snapshot_bytes: bytes, snapshot_mtime_ns: int) -> None:
    assert (ROOT / SCHEMA_REL).read_bytes() == snapshot_bytes
    assert (ROOT / SCHEMA_REL).stat().st_mtime_ns == snapshot_mtime_ns


def test_cli_no_args_is_read_only_and_passes() -> None:
    doc_bytes = (ROOT / SCHEMA_REL).read_bytes()
    doc_mtime_ns = (ROOT / SCHEMA_REL).stat().st_mtime_ns
    result = _run_generator()
    assert result.returncode == 0, result.stdout + result.stderr
    _assert_docs_unchanged(doc_bytes, doc_mtime_ns)


def test_cli_check_flag_is_read_only_and_passes() -> None:
    doc_bytes = (ROOT / SCHEMA_REL).read_bytes()
    doc_mtime_ns = (ROOT / SCHEMA_REL).stat().st_mtime_ns
    result = _run_generator("--check")
    assert result.returncode == 0, result.stdout + result.stderr
    _assert_docs_unchanged(doc_bytes, doc_mtime_ns)


def test_cli_bogus_flag_is_rejected_and_non_destructive() -> None:
    doc_bytes = (ROOT / SCHEMA_REL).read_bytes()
    doc_mtime_ns = (ROOT / SCHEMA_REL).stat().st_mtime_ns
    result = _run_generator("--bogus")
    assert result.returncode != 0
    _assert_docs_unchanged(doc_bytes, doc_mtime_ns)


def test_cli_check_and_write_new_are_mutually_exclusive_and_non_destructive() -> None:
    doc_bytes = (ROOT / SCHEMA_REL).read_bytes()
    doc_mtime_ns = (ROOT / SCHEMA_REL).stat().st_mtime_ns
    result = _run_generator("--check", "--write-new")
    assert result.returncode != 0
    _assert_docs_unchanged(doc_bytes, doc_mtime_ns)
