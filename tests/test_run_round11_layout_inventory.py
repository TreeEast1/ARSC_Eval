from __future__ import annotations

import builtins
import ctypes
import importlib.util
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("layout_launcher", ROOT / "scripts/run_round11_layout_inventory.py")
assert SPEC and SPEC.loader
launcher = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = launcher
SPEC.loader.exec_module(launcher)

GEN_SPEC = importlib.util.spec_from_file_location("layout_binding_generator_for_launcher", ROOT / "scripts/create_round11_layout_execution_binding.py")
assert GEN_SPEC and GEN_SPEC.loader
generator = importlib.util.module_from_spec(GEN_SPEC)
GEN_SPEC.loader.exec_module(generator)
GIT = Path(r"D:\Tools\MinGit\mingw64\bin\git.exe")

_WORKER_SPEC = importlib.util.spec_from_file_location(
    "layout_worker_under_launcher_test", ROOT / "src/arsc_eval/round11_layout_worker.py"
)
assert _WORKER_SPEC and _WORKER_SPEC.loader
worker_module = importlib.util.module_from_spec(_WORKER_SPEC)
_WORKER_SPEC.loader.exec_module(worker_module)

ARSC_SOURCES = {rel: (ROOT / rel).read_bytes() for rel in launcher.REQUIRED_ARSC_EVAL_SOURCES}
ARSC_SHA = {rel: launcher.sha256(data) for rel, data in ARSC_SOURCES.items()}


def _allow_reviewed_h0_for_binding_create(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate only generation-time HEAD; all H0 ls-tree calls remain real."""
    original = generator.git_output

    def git_output(git: Path, *args: str) -> str:
        if args == ("rev-parse", "HEAD"):
            return generator.H0
        return original(git, *args)

    monkeypatch.setattr(generator, "git_output", git_output)


def test_duplicate_json_key_rejected() -> None:
    with pytest.raises(launcher.StaticGateError, match="duplicate"):
        launcher.strict_document(b'{"a":1,"a":2}\n', "synthetic")


def test_declared_input_path_is_lexical_only(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("filesystem input touch")

    monkeypatch.setattr(Path, "resolve", forbidden)
    monkeypatch.setattr(Path, "exists", forbidden)
    value = launcher.declared_input_path("data/external/daadx_official/archive.bin")
    assert str(value).endswith(os.path.join("data", "external", "daadx_official", "archive.bin"))


def test_static_gate_materializes_inputs_without_touching_run_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_reviewed_h0_for_binding_create(monkeypatch)
    binding = generator.create_binding(python=Path(sys.executable), git=GIT)
    binding_data = generator.canonical(binding)
    h1 = "a" * 40
    h2 = "b" * 40
    memo_rel = launcher.REVIEW_MEMO_PATH.relative_to(ROOT).as_posix()
    memo_data = b"synthetic result-blind review\n"
    review = {
        "schema_version": launcher.REVIEW_SCHEMA,
        "decision": launcher.REVIEW_DECISION,
        "reviewer_role": "independent_result_blind_layout_execution_reviewer",
        "binding_head_h1": h1,
        "binding": {"path": launcher.BINDING_PATH.relative_to(ROOT).as_posix(), "bytes": len(binding_data), "sha256": launcher.sha256(binding_data), "schema_version": launcher.BINDING_SCHEMA},
        "review_memo": {"path": memo_rel, "bytes": len(memo_data), "sha256": launcher.sha256(memo_data)},
        "run_configuration": {key: binding[key] for key in ("source_reviewed_head_h0", "toolchain", "launcher_process", "worker_process", "formal_run", "artifact_contract", "resource_bounds")},
        "input_declarations": binding["authorities"],
        "capabilities": binding["capabilities"],
        "one_shot": {"attempt": "layout_inventory_attempt01", "retry": False, "delete": False, "recover": False},
        "claim_boundary": launcher.CLAIM_BOUNDARY,
        "self_authentication": False,
        "external_anchor_required": True,
        "test_evidence": {"evidence": [{"argv": ["python", "-m", "pytest"], "exit_code": 0, "passed": True, "stdout_sha256": "A" * 64}]},
    }
    review_data = launcher.canonical(review)
    memo_path = ROOT.joinpath(*Path(memo_rel).parts)
    mapping = {launcher.BINDING_PATH: binding_data, launcher.REVIEW_PATH: review_data, memo_path: memo_data}
    original_stable = launcher.stable_read

    def stable(path: Path, **kwargs) -> bytes:
        return mapping[path] if path in mapping else original_stable(path, **kwargs)

    artifact_bytes = {item["path"]: (ROOT.joinpath(*Path(item["path"]).parts)).read_bytes() for item in binding["artifacts"]}

    def git_call(_git: Path, *args: str, check: bool = True):
        if args == ("rev-parse", "HEAD"):
            out = h2
        elif args == ("rev-parse", "HEAD^"):
            out = h1
        elif args == ("rev-list", "--parents", "-n", "1", h2):
            out = h2 + " " + h1
        elif args == ("rev-list", "--parents", "-n", "1", h1):
            out = h1 + " " + generator.H0
        elif args[:2] == ("diff", "--name-only"):
            if args[2:] == (h1, h2):
                out = launcher.REVIEW_PATH.relative_to(ROOT).as_posix() + "\n" + memo_rel
            else:
                out = "\n".join(("src/arsc_eval/round11_layout_worker.py", "src/arsc_eval/round11_layout_runner.py", "tests/test_round11_layout_runner.py", "scripts/create_round11_layout_execution_binding.py", "scripts/run_round11_layout_inventory.py", "tests/test_create_round11_layout_execution_binding.py", "tests/test_run_round11_layout_inventory.py", launcher.BINDING_PATH.relative_to(ROOT).as_posix()))
        elif args[0] == "ls-tree":
            rel = args[-1]
            if rel == launcher.BINDING_PATH.relative_to(ROOT).as_posix():
                data = binding_data
            elif rel == launcher.REVIEW_PATH.relative_to(ROOT).as_posix():
                data = review_data
            elif rel == memo_rel:
                data = memo_data
            else:
                data = artifact_bytes[rel]
            out = f"100644 blob {launcher.git_blob(data)}\t{rel}"
        else:
            raise AssertionError(args)
        return __import__("subprocess").CompletedProcess(args, 0, out + "\n", "")

    forbidden = {
        ROOT / binding["authorities"]["receipt"]["path"],
        ROOT / binding["authorities"]["manifest"]["path"],
        ROOT / binding["authorities"]["archive"]["path"],
    }
    controls = {Path(binding["formal_run"][key]) for key in ("claim_path", "staging_path", "final_path")}
    original_lstat = launcher.os.lstat

    def lstat(path):
        item = Path(path)
        if item in forbidden:
            raise AssertionError("run input touched before claim")
        if item in controls:
            raise FileNotFoundError(item)
        return original_lstat(path)

    monkeypatch.setattr(launcher, "stable_read", stable)
    monkeypatch.setattr(launcher, "git_call", git_call)
    monkeypatch.setattr(launcher.os, "lstat", lstat)
    def synthetic_lease(path: Path, leases: list, **kwargs) -> bytes:
        return stable(path, **kwargs)

    monkeypatch.setattr(launcher, "lease_and_read", synthetic_lease)
    for name, _rel, _package in launcher.ARSC_EVAL_DEP_ORDER:
        monkeypatch.delitem(sys.modules, name, raising=False)
    authority = launcher.validate_static_authority(expected_launch_head=h2, expected_reviewer_sha256=launcher.sha256(review_data), git_executable=GIT)
    assert authority.inputs.receipt_path in forbidden
    assert authority.inputs.manifest_path in forbidden
    assert authority.inputs.archive_path in forbidden
    assert authority.inputs.timeout_seconds == 21600
    assert authority.inputs.closure_reserve_seconds == 1800
    authority.close()


@pytest.mark.parametrize("bad", [0, 1])
def test_reviewer_boolean_integer_is_rejected(bad: int) -> None:
    evidence = {"evidence": [{"argv": ["pytest"], "exit_code": 0, "passed": bad, "stdout_sha256": "A" * 64}]}
    with pytest.raises(launcher.StaticGateError, match="passed type"):
        launcher.validate_test_evidence(evidence)


def test_arbitrary_reviewer_evidence_is_rejected() -> None:
    with pytest.raises(launcher.StaticGateError, match="fields"):
        launcher.validate_test_evidence({"synthetic": True})


def test_git_wrapper_is_rejected() -> None:
    with pytest.raises(launcher.StaticGateError, match="wrapper"):
        launcher._require_real_git(Path(r"D:\Tools\MinGit\cmd\git.exe"))


@pytest.mark.skipif(os.name != "nt", reason="Windows lease semantics")
def test_windows_lease_reads_same_handle_and_denies_mutation(tmp_path: Path) -> None:
    target = tmp_path / "authority.bin"
    target.write_bytes(b"bound-authority")
    lease = launcher.WindowsReadLease(target)
    try:
        original_read = lease._read_file
        observed_handles: list[int] = []

        def observed_read(handle, *args):
            observed_handles.append(handle)
            return original_read(handle, *args)

        lease._read_file = observed_read
        assert lease.read(max_bytes=1024) == b"bound-authority"
        assert observed_handles and set(observed_handles) == {lease._handle}
        with pytest.raises(PermissionError):
            target.write_bytes(b"replacement")
        with pytest.raises(PermissionError):
            target.unlink()
        with pytest.raises(PermissionError):
            tmp_path.rename(tmp_path.with_name(tmp_path.name + "-renamed"))
    finally:
        lease.close()
        lease.close()
    target.write_bytes(b"replacement")


@pytest.mark.skipif(os.name != "nt", reason="Windows lease semantics")
def test_windows_lease_rejects_reparse_leaf(tmp_path: Path) -> None:
    target = tmp_path / "target.bin"
    link = tmp_path / "link.bin"
    target.write_bytes(b"content")
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(launcher.StaticGateError, match="reparse"):
        launcher.WindowsReadLease(link)


def test_windows_abi_layout_is_exact() -> None:
    assert ctypes.sizeof(launcher._FileTime) == 8
    assert ctypes.sizeof(launcher._HandleInfo) == 52
    assert [getattr(launcher._HandleInfo, name).offset for name, _ in launcher._HandleInfo._fields_] == [0, 4, 12, 20, 28, 32, 36, 40, 44, 48]
    assert ctypes.sizeof(launcher._AttributeTagInfo) == 8


@pytest.mark.skipif(os.name != "nt", reason="Windows lease semantics")
def test_windows_lease_rejects_relative_path() -> None:
    with pytest.raises(launcher.StaticGateError, match="absolute"):
        launcher.WindowsReadLease(Path("relative.bin"))


@pytest.mark.skipif(os.name != "nt", reason="Windows lease semantics")
def test_windows_lease_caps_and_link_count(tmp_path: Path) -> None:
    exact = tmp_path / "exact.bin"
    exact.write_bytes(b"1234")
    lease = launcher.WindowsReadLease(exact)
    try:
        assert lease.read(max_bytes=4) == b"1234"
    finally:
        lease.close()

    overflow = launcher.WindowsReadLease(exact)
    try:
        with pytest.raises(launcher.StaticGateError, match="cap"):
            overflow.read(max_bytes=3)
    finally:
        overflow.close()

    linked = tmp_path / "linked.bin"
    os.link(exact, linked)
    hardlink = launcher.WindowsReadLease(exact)
    try:
        with pytest.raises(launcher.StaticGateError, match="link policy"):
            hardlink.read()
    finally:
        hardlink.close()


def test_missing_external_anchor_rejected_before_static_file_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launcher, "stable_read", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("read")))
    with pytest.raises(launcher.StaticGateError, match="HEAD pin"):
        launcher.validate_static_authority(expected_launch_head="bad", expected_reviewer_sha256="A" * 64, git_executable=GIT)


def _canonical_argv(
    executable: str = r"C:\repo\python.exe",
    script: str = r"C:\repo\scripts\run_round11_layout_inventory.py",
) -> list[str]:
    return [
        executable, "-I", "-S", "-B", script,
        "--expected-launch-head", "a" * 40,
        "--expected-reviewer-sha256", "A" * 64,
        "--git-executable", r"C:\repo\git.exe",
        "--execute",
    ]


def _synthetic_flags(**overrides) -> types.SimpleNamespace:
    base = {
        "isolated": 1,
        "no_user_site": 1,
        "no_site": 1,
        "safe_path": True,
        "dont_write_bytecode": 1,
        "ignore_environment": 1,
    }
    base.update(overrides)
    return types.SimpleNamespace(**base)


def _clean_modules() -> dict[str, object]:
    return {name: module for name, module in sys.modules.items() if name != "arsc_eval" and not name.startswith("arsc_eval.")}


def test_startup_attestation_accepts_canonical_synthetic(monkeypatch: pytest.MonkeyPatch) -> None:
    argv = _canonical_argv()
    monkeypatch.setattr(sys, "modules", _clean_modules())
    launcher.validate_startup_attestation(argv, _synthetic_flags(), argv[0], argv[4])


def test_main_attests_actual_sys_orig_argv_first(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = ["ORIGINAL", "NOT", "RECONSTRUCTED"]
    observed: list[object] = []

    class StopHere(RuntimeError):
        pass

    def capture(orig_argv, *_args):
        observed.append(orig_argv)
        raise StopHere

    monkeypatch.setattr(sys, "orig_argv", sentinel)
    monkeypatch.setattr(sys, "argv", ["forged-script-argv"])
    monkeypatch.setattr(launcher, "validate_startup_attestation", capture)
    with pytest.raises(StopHere):
        launcher.main()
    assert len(observed) == 1 and observed[0] is sentinel


@pytest.mark.parametrize(
    "flag",
    ["isolated", "no_user_site", "no_site", "safe_path", "dont_write_bytecode", "ignore_environment"],
)
def test_startup_attestation_rejects_incorrect_flag(monkeypatch: pytest.MonkeyPatch, flag: str) -> None:
    argv = _canonical_argv()
    bad = 0 if flag != "safe_path" else False
    monkeypatch.setattr(sys, "modules", _clean_modules())
    with pytest.raises(launcher.StaticGateError):
        launcher.validate_startup_attestation(argv, _synthetic_flags(**{flag: bad}), argv[0], argv[4])


def test_startup_attestation_rejects_missing_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    argv = _canonical_argv()
    monkeypatch.setattr(sys, "modules", _clean_modules())
    with pytest.raises(launcher.StaticGateError, match="argv length"):
        launcher.validate_startup_attestation(argv[1:], _synthetic_flags(), argv[0], argv[4])


def test_startup_attestation_rejects_reordered_interpreter_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    argv = _canonical_argv()
    reordered = [argv[0], "-S", "-I", "-B", argv[4], *argv[5:]]
    monkeypatch.setattr(sys, "modules", _clean_modules())
    with pytest.raises(launcher.StaticGateError, match="interpreter flags"):
        launcher.validate_startup_attestation(reordered, _synthetic_flags(), argv[0], argv[4])


def test_startup_attestation_rejects_reordered_launcher_options(monkeypatch: pytest.MonkeyPatch) -> None:
    argv = _canonical_argv()
    reordered = argv[:5] + argv[7:9] + argv[5:7] + argv[9:]
    monkeypatch.setattr(sys, "modules", _clean_modules())
    with pytest.raises(launcher.StaticGateError, match="option order"):
        launcher.validate_startup_attestation(reordered, _synthetic_flags(), argv[0], argv[4])


def test_startup_attestation_rejects_extra_interpreter_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    argv = _canonical_argv()
    extra = [argv[0], "-I", "-S", "-B", "-X", "dev", *argv[4:]]
    monkeypatch.setattr(sys, "modules", _clean_modules())
    with pytest.raises(launcher.StaticGateError, match="extra interpreter flags"):
        launcher.validate_startup_attestation(extra, _synthetic_flags(), argv[0], argv[4])


def test_startup_attestation_rejects_wrong_script(monkeypatch: pytest.MonkeyPatch) -> None:
    argv = _canonical_argv()
    monkeypatch.setattr(sys, "modules", _clean_modules())
    with pytest.raises(launcher.StaticGateError, match="script path"):
        launcher.validate_startup_attestation(argv, _synthetic_flags(), argv[0], r"C:\repo\other.py")


def test_startup_attestation_rejects_wrong_executable(monkeypatch: pytest.MonkeyPatch) -> None:
    argv = _canonical_argv()
    monkeypatch.setattr(sys, "modules", _clean_modules())
    with pytest.raises(launcher.StaticGateError, match="executable"):
        launcher.validate_startup_attestation(argv, _synthetic_flags(), r"C:\repo\other_python.exe", argv[4])


@pytest.mark.parametrize("name", ["arsc_eval", "arsc_eval.round11_layout_control"])
def test_startup_attestation_rejects_preloaded_arsc_eval(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    argv = _canonical_argv()
    modules = _clean_modules()
    modules[name] = object()
    monkeypatch.setattr(sys, "modules", modules)
    with pytest.raises(launcher.StaticGateError, match="preloaded"):
        launcher.validate_startup_attestation(argv, _synthetic_flags(), argv[0], argv[4])


def test_preloaded_arsc_eval_module_pure() -> None:
    assert launcher._preloaded_arsc_eval_module({}) is None
    assert launcher._preloaded_arsc_eval_module({"arsc_eval": 1}) == "arsc_eval"
    assert launcher._preloaded_arsc_eval_module({"arsc_eval.round11_layout_control": 1}) == "arsc_eval.round11_layout_control"


def _fake_modules(package_rel: str, control_rel: str, formal_rel: str) -> dict[str, types.SimpleNamespace]:
    return {
        "arsc_eval": types.SimpleNamespace(__file__=str(ROOT.joinpath("src", *Path(package_rel).parts))),
        "arsc_eval.round11_layout_control": types.SimpleNamespace(__file__=str(ROOT.joinpath("src", *Path(control_rel).parts))),
        "arsc_eval.round11_layout_formal_runner": types.SimpleNamespace(__file__=str(ROOT.joinpath("src", *Path(formal_rel).parts))),
    }


def test_verified_import_paths_accepts_bound_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    mods = _fake_modules(
        "arsc_eval/__init__.py",
        "arsc_eval/round11_layout_control.py",
        "arsc_eval/round11_layout_formal_runner.py",
    )
    monkeypatch.setattr(sys, "modules", mods)
    launcher.validate_verified_import_paths()


def test_verified_import_paths_rejects_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    mods = _fake_modules(
        "other/__init__.py",
        "arsc_eval/round11_layout_control.py",
        "arsc_eval/round11_layout_formal_runner.py",
    )
    monkeypatch.setattr(sys, "modules", mods)
    with pytest.raises(launcher.StaticGateError, match="verified module path"):
        launcher.validate_verified_import_paths()


# ---------------------------------------------------------------------------
# WindowsReadLease.close fail-closed (deterministic, no real handles)
# ---------------------------------------------------------------------------


def _fake_lease(*, close_returns: dict[int, int]) -> tuple[launcher.WindowsReadLease, list[int]]:
    lease = object.__new__(launcher.WindowsReadLease)
    lease._kernel32 = None
    lease._handle = 1001
    lease._ancestor_handles = [2001, 2002, 2003]
    calls: list[int] = []

    def fake_close(handle):
        calls.append(handle)
        return close_returns.get(handle, 1)

    lease._close = fake_close
    return lease, calls


def test_windows_lease_close_fails_closed_after_attempting_all_handles(monkeypatch: pytest.MonkeyPatch) -> None:
    lease, calls = _fake_lease(close_returns={1001: 0, 2002: 0})
    monkeypatch.setattr(lease, "_close", lease._close)
    with pytest.raises(launcher.StaticGateError, match="static authority close failed"):
        lease.close()
    # Every held handle is attempted exactly once, leaf first then ancestors.
    assert calls == [1001, 2003, 2002, 2001]
    assert lease._handle is None and lease._ancestor_handles == []
    # Idempotent: a second close tries nothing and raises nothing.
    calls.clear()
    lease.close()
    assert calls == []


def test_windows_lease_close_success_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    lease, calls = _fake_lease(close_returns={})
    monkeypatch.setattr(lease, "_close", lease._close)
    lease.close()
    assert calls == [1001, 2003, 2002, 2001]
    assert lease._handle is None and lease._ancestor_handles == []
    calls.clear()
    lease.close()
    assert calls == []


class _HostileArscEvalFinder:
    def __init__(self) -> None:
        self.invoked: list[str] = []

    def find_spec(self, fullname, path=None, target=None):
        self.invoked.append(fullname)
        if fullname == "arsc_eval" or fullname.startswith("arsc_eval."):
            raise AssertionError(f"hostile arsc_eval meta_path find_spec invoked for {fullname}")
        return None


def _clear_arsc_eval(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(sys.modules):
        if name == "arsc_eval" or name.startswith("arsc_eval."):
            monkeypatch.delitem(sys.modules, name, raising=False)


# ---------------------------------------------------------------------------
# Launcher load_arsc_eval_source_only negative tests
# ---------------------------------------------------------------------------


def test_launcher_load_arsc_eval_hostile_meta_path_never_invoked(monkeypatch: pytest.MonkeyPatch) -> None:
    finder = _HostileArscEvalFinder()
    original_meta_path = list(sys.meta_path)
    _clear_arsc_eval(monkeypatch)
    monkeypatch.setattr(sys, "meta_path", [finder, *original_meta_path])
    try:
        control, formal = launcher.load_arsc_eval_source_only(dict(ARSC_SOURCES), dict(ARSC_SHA))
        assert control.__name__ == "arsc_eval.round11_layout_control"
        assert formal.__name__ == "arsc_eval.round11_layout_formal_runner"
    finally:
        _clear_arsc_eval(monkeypatch)
    assert not any(name == "arsc_eval" or name.startswith("arsc_eval.") for name in finder.invoked)


def test_launcher_load_sha_mismatch_fails_before_exec(monkeypatch: pytest.MonkeyPatch) -> None:
    tampered = dict(ARSC_SOURCES)
    first_rel = launcher.REQUIRED_ARSC_EVAL_SOURCES[0]
    tampered[first_rel] = tampered[first_rel] + b"# tampered"
    _clear_arsc_eval(monkeypatch)
    compiled = []
    original_compile = builtins.compile

    def record_compile(*args, **kwargs):
        compiled.append(args)
        return original_compile(*args, **kwargs)

    monkeypatch.setattr(builtins, "compile", record_compile)
    with pytest.raises(launcher.StaticGateError, match="sha differs"):
        launcher.load_arsc_eval_source_only(tampered, dict(ARSC_SHA))
    assert compiled == []
    for name, _rel, _package in launcher.ARSC_EVAL_DEP_ORDER:
        assert name not in sys.modules


def test_launcher_load_exec_failure_rolls_back_sys_modules_and_package_attributes(monkeypatch: pytest.MonkeyPatch) -> None:
    real_module_type = types.ModuleType
    created: list[types.ModuleType] = []

    def recording_module_type(name, doc=None):
        module = real_module_type(name, doc)
        created.append(module)
        return module

    module_bytes = dict(ARSC_SOURCES)
    expected = dict(ARSC_SHA)
    _clear_arsc_eval(monkeypatch)
    sentinel = {
        name: value
        for name, value in sys.modules.items()
        if name not in {n for n, _r, _p in launcher.ARSC_EVAL_DEP_ORDER}
    }
    monkeypatch.setattr(launcher, "types", types.SimpleNamespace(ModuleType=recording_module_type))
    calls = {"n": 0}
    original_compile = builtins.compile

    def fail_on_last_compile(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == len(launcher.ARSC_EVAL_DEP_ORDER):
            raise SyntaxError("synthetic compile failure on last module")
        return original_compile(*args, **kwargs)

    monkeypatch.setattr(builtins, "compile", fail_on_last_compile)
    with pytest.raises(SyntaxError):
        launcher.load_arsc_eval_source_only(module_bytes, expected)
    # Every inserted arsc_eval key was removed.
    for name, _rel, _package in launcher.ARSC_EVAL_DEP_ORDER:
        assert name not in sys.modules
    # Package attributes attached before the failure were rolled back.
    package = created[0]
    assert package.__name__ == "arsc_eval"
    for _name, _rel, _package in launcher.ARSC_EVAL_DEP_ORDER[1:]:
        child = _name.rsplit(".", 1)[1]
        assert not hasattr(package, child)
    # Non-arsc_eval modules were preserved (only arsc_eval keys were touched).
    for name, value in sentinel.items():
        assert sys.modules.get(name) is value


# ---------------------------------------------------------------------------
# Worker _attest_startup negative tests (worker loaded as a test module)
# ---------------------------------------------------------------------------


def _worker_flags(**overrides) -> types.SimpleNamespace:
    base = {
        "isolated": 1,
        "no_user_site": 1,
        "no_site": 1,
        "safe_path": True,
        "dont_write_bytecode": 1,
        "ignore_environment": 1,
    }
    base.update(overrides)
    return types.SimpleNamespace(**base)


def _worker_orig_argv(*, flags=("-I", "-S", "-B"), script=None, tail=None) -> list[str]:
    script = script if script is not None else str(Path(worker_module.__file__).resolve())
    tail = tail if tail is not None else ["--control-fd", "7", "--expected-bytes", "123", "--expected-sha256", "A" * 64]
    return [str(sys.executable), *flags, script, *tail]


def _attest(monkeypatch: pytest.MonkeyPatch, argv, *, exe=None, flags=None):
    monkeypatch.setattr(sys, "orig_argv", argv)
    monkeypatch.setattr(sys, "executable", exe if exe is not None else argv[0])
    monkeypatch.setattr(sys, "flags", flags if flags is not None else _worker_flags())
    worker_module._attest_startup()


def test_worker_attest_startup_accepts_canonical(monkeypatch: pytest.MonkeyPatch) -> None:
    _attest(monkeypatch, _worker_orig_argv())


def test_worker_attest_startup_rejects_missing_args(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="argv length"):
        _attest(monkeypatch, _worker_orig_argv()[:10])


def test_worker_attest_startup_rejects_reordered_interpreter_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="interpreter flags"):
        _attest(monkeypatch, _worker_orig_argv(flags=("-S", "-I", "-B")))


def test_worker_attest_startup_rejects_extra_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="argv length"):
        _attest(monkeypatch, _worker_orig_argv(flags=("-I", "-S", "-B", "-X")))


def test_worker_attest_startup_rejects_wrong_executable(monkeypatch: pytest.MonkeyPatch) -> None:
    argv = _worker_orig_argv()
    with pytest.raises(ValueError, match="executable"):
        _attest(monkeypatch, argv, exe=r"C:\repo\other_python.exe")


def test_worker_attest_startup_rejects_wrong_script(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="script"):
        _attest(monkeypatch, _worker_orig_argv(script=r"C:\repo\other.py"))


# ---------------------------------------------------------------------------
# Worker _load_verified_inventory negative tests
# ---------------------------------------------------------------------------


def test_worker_load_rejects_preloaded_namespace(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_arsc_eval(monkeypatch)
    monkeypatch.setitem(sys.modules, "arsc_eval", object())
    with pytest.raises(ValueError, match="preloaded"):
        worker_module._load_verified_inventory()


def test_worker_load_rejects_sha_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_arsc_eval(monkeypatch)
    monkeypatch.setattr(worker_module.Path, "read_bytes", lambda _self: b"tampered inventory source")
    with pytest.raises(ValueError, match="SHA256 differs"):
        worker_module._load_verified_inventory()


def test_worker_load_hostile_meta_path_never_invoked(monkeypatch: pytest.MonkeyPatch) -> None:
    finder = _HostileArscEvalFinder()
    original_meta_path = list(sys.meta_path)
    _clear_arsc_eval(monkeypatch)
    monkeypatch.setattr(sys, "meta_path", [finder, *original_meta_path])
    try:
        module = worker_module._load_verified_inventory()
        assert module.__name__ == "arsc_eval.round11_layout_inventory"
    finally:
        sys.modules.pop("arsc_eval.round11_layout_inventory", None)
        sys.modules.pop("arsc_eval", None)
    assert not any(name == "arsc_eval" or name.startswith("arsc_eval.") for name in finder.invoked)


def test_worker_load_matching_sha_compile_failure_rolls_back_namespace(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_arsc_eval(monkeypatch)
    sentinel = {name: value for name, value in sys.modules.items()}

    def boom(*args, **kwargs):
        raise SyntaxError("synthetic worker compile failure")

    monkeypatch.setattr(builtins, "compile", boom)
    with pytest.raises(SyntaxError):
        worker_module._load_verified_inventory()
    assert "arsc_eval" not in sys.modules
    assert "arsc_eval.round11_layout_inventory" not in sys.modules
    for name, value in sentinel.items():
        assert sys.modules.get(name) is value


# ---------------------------------------------------------------------------
# Real subprocess probe: python -I -S -B isolation
# ---------------------------------------------------------------------------


def test_isolated_interpreter_flags_via_real_subprocess() -> None:
    probe = (
        "import sys\n"
        "print(int(sys.flags.no_site))\n"
        "print(int(any('site-packages' in item.lower() for item in sys.path)))\n"
        "print(int(any('dist-packages' in item.lower() for item in sys.path)))\n"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-c", probe],
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
        errors="strict",
    )
    lines = result.stdout.splitlines()
    assert lines[0] == "1"
    assert lines[1] == "0"
    assert lines[2] == "0"
