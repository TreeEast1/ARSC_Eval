"""Tests for ``arsc_eval.round13_v3_runner.collect_preclaim_evidence``.

These tests target the current read-only public entry point
``collect_preclaim_evidence(root)``.  Every test builds a deterministic,
miniature git repository under ``tmp_path`` (initialised and committed with
subprocess ``git`` only inside that tmp root), containing exactly the fixed
relative module files and a canonical miniature V3 protocol whose digest is
bound by monkeypatching ``runner.PROTOCOL_SHA256``.  The running interpreter is
monkeypatched (``sys.executable`` / ``sys.version``) and the
installed-distributions manifest is replaced by a deterministic provider.

No old GO/claim/decision API (``validate_go_payload``, ``build_claim_payload``,
``validate_preclaim``, ``GOExpected``, GO constants) exists in the module and
none is used here.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Real interpreter captured before the ``Fixtures`` monkeypatches
# ``sys.executable`` to a fake in-repo executable.  Used only to build the
# local ``filter.evil.clean`` command so the marker helper runs with a real
# interpreter if git ever invoked it.
REAL_PYTHON = sys.executable

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import arsc_eval.round13_v3_runner as runner

PY_VERSION = "3.12.0 (fake interpreter for binding test)"

# Tokens that must never appear in the neutral evidence (the module emits an
# authority-free, AWAIT preclaim body).
_FORBIDDEN_KEY_TOKENS = ("approval", "claim", "decision", "go")
_FORBIDDEN_VALUE_TOKENS = ("approval", "claim", "decision")


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"git {' '.join(args)!r} failed in {root}:\n{result.stderr.strip()}"
    )
    return result.stdout.strip()


class Fixtures:
    """Miniature tmp git root with the fixed files + canonical mini protocol."""

    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.root = root

        # --- frozen miniature protocol (digest patched to the file's own) -----
        protocol_object = {
            "schema_version": runner.PROTOCOL_SCHEMA,
            "result_blind": True,
            "formal_execution": {
                "one_shot": {
                    "attempt": runner.FORMAL_ATTEMPT,
                    "claim_schema": runner.CLAIM_SCHEMA,
                    "claim_path": runner.CLAIM_PATH_REL.as_posix(),
                    "formal_claim_is_permanent": True,
                    "retry_allowed": False,
                    "infrastructure_status": {"value": "IMPLEMENTATION_FAILURE"},
                }
            },
        }
        self.protocol_bytes = runner.canonical_json_bytes(protocol_object)
        protocol_path = root / runner.PROTOCOL_REL
        protocol_path.parent.mkdir(parents=True, exist_ok=True)
        protocol_path.write_bytes(self.protocol_bytes)
        monkeypatch.setattr(
            runner, "PROTOCOL_SHA256", runner.sha256_bytes(self.protocol_bytes)
        )

        # --- fixed relative source + dependency manifests ---------------------
        self.runner_bytes = b"# runner placeholder\nRUN = 1\n"
        self.tests_bytes = b"# tests placeholder\nRUN = 1\n"
        self.req_bytes = b"numpy==1.26\n"
        self.req_dev_bytes = b"-r requirements.txt\npytest>=9.0\n"

        (root / runner.RUNNER_REL).parent.mkdir(parents=True, exist_ok=True)
        (root / runner.RUNNER_REL).write_bytes(self.runner_bytes)
        (root / runner.TESTS_REL).parent.mkdir(parents=True, exist_ok=True)
        (root / runner.TESTS_REL).write_bytes(self.tests_bytes)
        (root / runner.REQUIREMENTS_REL).write_bytes(self.req_bytes)
        (root / runner.REQUIREMENTS_DEV_REL).write_bytes(self.req_dev_bytes)

        # --- running interpreter snapshot (monkeypatched) ---------------------
        exe_dir = root / "bin"
        exe_dir.mkdir(parents=True, exist_ok=True)
        self.exe_path = exe_dir / "fake_python"
        self.exe_bytes = b"#!/usr/bin/env python\nexit(0)\n"
        self.exe_path.write_bytes(self.exe_bytes)
        monkeypatch.setattr(sys, "executable", str(self.exe_path))
        monkeypatch.setattr(sys, "version", PY_VERSION)

        # --- deterministic installed-distributions manifest provider ----------
        monkeypatch.setattr(
            runner,
            "_installed_distributions_manifest",
            lambda: [("numpy", "1.26.0"), ("torch", "2.8.0")],
        )

        # --- git init + commit (subprocess git only under tmp) -----------------
        _git(root, "init", "-b", "main")
        _git(root, "config", "user.name", "test")
        _git(root, "config", "user.email", "test@example.com")
        _git(root, "add", "--all")
        _git(root, "commit", "-m", "seed evidence fixture")
        self.commit = _git(root, "rev-parse", "HEAD")

    def collect(self) -> dict:
        return runner.collect_preclaim_evidence(self.root)


@pytest.fixture
def fx(tmp_path, monkeypatch) -> Fixtures:
    return Fixtures(tmp_path, monkeypatch)


def _assert_no_forbidden(evidence: dict) -> None:
    """No recursive key/value carries approval/claim/decision semantics.

    The single allowed use of the literal ``GO_RUN`` remains the AWAIT status
    value itself; every key is free of ``go``.
    """
    stack = [evidence]
    while stack:
        node = stack.pop()
        for key, value in node.items():
            key_lower = key.casefold()
            assert not any(token in key_lower for token in _FORBIDDEN_KEY_TOKENS), (
                f"forbidden key token in key {key!r}"
            )
            if isinstance(value, str):
                value_lower = value.casefold()
                assert not any(
                    token in value_lower for token in _FORBIDDEN_VALUE_TOKENS
                ), f"forbidden value token in {key!r} = {value!r}"
            elif isinstance(value, dict):
                stack.append(value)


# ---------------------------------------------------------------------------
# Test A: success evidence — exact AWAIT status, not-run / no-authority, and
# no approval/claim/decision semantics anywhere.
# ---------------------------------------------------------------------------
def test_a_success_evidence_exact_status(fx) -> None:
    evidence = fx.collect()

    assert evidence["schema_version"] == runner.EVIDENCE_SCHEMA
    assert evidence["status"] == runner.EVIDENCE_STATUS
    assert evidence["status"] == "AWAIT_EXTERNAL_AUTHORIZATION_V3"
    assert evidence["not_run"] is True
    assert evidence["authority_absent"] is True
    assert evidence["implementation"] == fx.commit

    assert set(evidence["bound_sources"]) == {
        "runner",
        "tests",
        "requirements",
        "requirements_dev",
    }

    # Expected environment keys: the interpreter snapshot, the resolved real git
    # executable snapshot (path/size/SHA), and the installed-distributions SHA.
    assert set(evidence["environment"]) == {
        "python_executable",
        "git_executable",
        "installed_distributions",
    }
    git_env = evidence["environment"]["git_executable"]
    assert set(git_env) == {"path", "size", "sha256"}
    assert os.path.isabs(git_env["path"])
    assert isinstance(git_env["size"], int) and git_env["size"] > 0
    assert isinstance(git_env["sha256"], str) and len(git_env["sha256"]) == 64

    # Neutral, authority-free body: no approval/claim/decision semantics and no
    # bare GO_RUN execution key.
    _assert_no_forbidden(evidence)


# ---------------------------------------------------------------------------
# Test B: zero-write — every file's bytes and mtime are unchanged.
# ---------------------------------------------------------------------------
def _snapshot_tree(root: Path) -> dict[str, tuple[bytes, int]]:
    snapshot: dict[str, tuple[bytes, int]] = {}
    for dirpath, _dirnames, filenames in os.walk(str(root)):
        for name in filenames:
            p = Path(dirpath) / name
            stat = p.stat()
            snapshot[str(p.relative_to(root))] = (p.read_bytes(), stat.st_mtime_ns)
    return snapshot


def test_b_zero_write_snapshot(fx) -> None:
    before = _snapshot_tree(fx.root)

    fx.collect()

    after = _snapshot_tree(fx.root)
    assert after == before, "collect_preclaim_evidence must not write any file"


# ---------------------------------------------------------------------------
# Test C: modifying the committed runner file or creating a formal artifact
# must fail closed with V3RunnerError.
# ---------------------------------------------------------------------------
def test_c_modified_runner_file_fails(fx) -> None:
    # Pure worktree tamper: the committed blob and the index still match the
    # seed; only the raw worktree bytes differ, so the raw HEAD-blob-vs-worktree
    # comparison must fail closed.  No staging is needed (and it would wrongly
    # exercise the index-vs-HEAD path instead of the byte comparison).
    runner_file = fx.root / runner.RUNNER_REL
    runner_file.write_bytes(b"# tampered\n")

    with pytest.raises(runner.V3RunnerError):
        fx.collect()


def test_c_staged_tamper_with_restored_worktree_fails(fx) -> None:
    # Save the committed runner bytes, tamper the runner, stage it (creating a
    # differing staged blob and index entry), then restore the worktree to the
    # original committed bytes WITHOUT staging the restore.  The worktree and
    # the committed HEAD blob now match, but the index still carries the staged
    # tamper, so the index-vs-HEAD closure must fail closed while the snapshot
    # stays unchanged (zero writes).
    runner_file = fx.root / runner.RUNNER_REL
    original = runner_file.read_bytes()

    runner_file.write_bytes(b"# staged tamper\n")
    _git(fx.root, "add", "--", runner.RUNNER_REL)
    runner_file.write_bytes(original)  # restore worktree; do NOT stage again

    before = _snapshot_tree(fx.root)
    with pytest.raises(runner.V3RunnerError):
        fx.collect()
    after = _snapshot_tree(fx.root)

    assert after == before, "collection must remain zero-write"


def test_c_new_formal_artifact_fails(fx) -> None:
    artifact = fx.root / "outputs" / "validity" / runner.FORMAL_CLAIM_NAME
    artifact.write_bytes(b"{}")

    with pytest.raises(runner.V3RunnerError, match="formal artifact"):
        fx.collect()


# ---------------------------------------------------------------------------
# Test D: ambient GIT_* environment variables must fail closed before any git
# subprocess is spawned (no decoy workspace write can occur).
# ---------------------------------------------------------------------------
def test_d_ambient_git_dir_work_tree_raises_before_git_call(fx, monkeypatch) -> None:
    decoy = fx.root / "decoy_repo"
    decoy.mkdir()
    monkeypatch.setenv("GIT_DIR", str(decoy / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(decoy))

    # Any subprocess git spawn would be a violation; fail loudly if attempted.
    def _fail_if_run(*args, **kwargs):
        raise AssertionError("git subprocess must not be invoked")

    monkeypatch.setattr(runner.subprocess, "run", _fail_if_run)

    with pytest.raises(runner.V3RunnerError, match="GIT_"):
        fx.collect()

    # The decoy workspace was never written/initialised by collection.
    assert list(decoy.iterdir()) == []


# ---------------------------------------------------------------------------
# Test E: a local ``core.fsmonitor`` hook pointed at a marker script must never
# execute; evidence collection stays zero-write and the marker stays absent.
# ---------------------------------------------------------------------------
def test_e_core_fsmonitor_marker_not_executed_zero_write(fx) -> None:
    marker_trigger = fx.root / "bin" / "fsmonitor_executed_marker"
    marker_script = fx.root / "bin" / "fsmonitor_hook.py"
    marker_script.write_text(
        "import pathlib\n"
        "pathlib.Path(%r).write_text('executed', encoding='utf-8')\n"
        % str(marker_trigger),
        encoding="utf-8",
    )

    # Configure local core.fsmonitor to the marker script.  Collection must
    # override this to false so the hook never runs.
    fsmonitor_cmd = f'"{sys.executable}" "{marker_script.as_posix()}"'
    _git(fx.root, "config", "--local", "core.fsmonitor", fsmonitor_cmd)

    before = _snapshot_tree(fx.root)
    evidence = fx.collect()
    after = _snapshot_tree(fx.root)

    assert after == before, "evidence collection must remain zero-write"
    assert not marker_trigger.exists(), "core.fsmonitor hook must not execute"


# ---------------------------------------------------------------------------
# Test F: a ``refs/replace/<HEAD>`` entry (git replace ref at the HEAD commit)
# must fail closed with V3RunnerError before any git subprocess runs, without
# writing anything to the workspace.
# ---------------------------------------------------------------------------
def test_f_replace_ref_fails_closed_no_writes(fx) -> None:
    replace_ref = (
        fx.root / ".git" / "refs" / "replace" / fx.commit
    )
    replace_ref.parent.mkdir(parents=True, exist_ok=True)
    replace_ref.write_bytes(b"0000000000000000000000000000000000000000\n")

    before = _snapshot_tree(fx.root)
    with pytest.raises(runner.V3RunnerError, match="replace"):
        fx.collect()
    after = _snapshot_tree(fx.root)

    # Collection must not mutate any file (including the injected dummy ref).
    assert after == before, "evidence collection must remain zero-write"


# ---------------------------------------------------------------------------
# Test G: a local ``filter.evil.clean`` hook assigned to the fixed runner via
# .gitattributes must never execute.  Raw worktree-vs-committed-blob drift must
# fail closed with V3RunnerError and the marker stays absent / zero-write.
# ---------------------------------------------------------------------------
def test_g_git_clean_filter_never_executes_and_raw_drift_fails(fx) -> None:
    # Assign an evil clean filter to the fixed runner and commit the attributes
    # file only, so the committed runner blob stays the pristine seed content.
    gitattributes = fx.root / ".gitattributes"
    gitattributes.write_text("src/arsc_eval/round13_v3_runner.py filter=evil\n")
    _git(fx.root, "add", "--", ".gitattributes")
    _git(fx.root, "commit", "-m", "add evil filter attributes")
    fx.commit = _git(fx.root, "rev-parse", "HEAD")

    # Helper: writes the marker path (argv[1]) then pipes stdin to stdout, so a
    # clean filter would both leave an on-disk trace and stay an identity
    # transform.
    helper = fx.root / "bin" / "evil_clean_helper.py"
    marker = fx.root / "bin" / "evil_clean_executed_marker"
    helper.write_text(
        "import pathlib\n"
        "import sys\n"
        "pathlib.Path(sys.argv[1]).write_bytes(b'executed')\n"
        "sys.stdout.buffer.write(sys.stdin.buffer.read())\n"
    )

    # Configure only the local clean command; the process driver remains unset.
    clean_cmd = f'"{REAL_PYTHON}" "{helper.as_posix()}" "{marker.as_posix()}"'
    _git(fx.root, "config", "--local", "filter.evil.clean", clean_cmd)

    # Tamper the fixed runner so the committed blob and the worktree differ.
    runner_file = fx.root / runner.RUNNER_REL
    runner_file.write_bytes(b"# raw drift under evil filter\n")

    before = _snapshot_tree(fx.root)
    with pytest.raises(runner.V3RunnerError):
        fx.collect()
    after = _snapshot_tree(fx.root)

    # Raw worktree-vs-blob drift must fail closed without ever invoking the
    # evil clean filter: nothing (including the marker) may be written.
    assert after == before, "collection must remain zero-write"
    assert not marker.exists(), "git clean filter must never execute"
