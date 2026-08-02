from __future__ import annotations

import json
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "src/arsc_eval/round11_phase1_control.py"
SPEC = importlib.util.spec_from_file_location("round11_phase1_control", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)
AMENDMENT = ROOT / "outputs/validity/round11_daadx_phase1_diagnostic_amendment.json"
SHA = "A" * 64
TOKEN = "B" * 64


def _results(*, passed: bool = True):
    states = {f"G{index}": "PASS" for index in range(4)}
    if not passed:
        states["G2"] = "FAIL"
    states.update({f"G{index}": MODULE.DEFERRED for index in range(4, 8)})
    return {
        "schema_version": MODULE.RESULTS_SCHEMA,
        "phase": MODULE.PHASE,
        "attempt": MODULE.ATTEMPT,
        "outcome": MODULE.PASS_OUTCOME if passed else MODULE.STOP_OUTCOME,
        "gates": states,
        "is_formal_g0_g8_verdict": False,
        "training_authorized": False,
    }


def _payloads(*, passed: bool = True):
    payloads = {name: f"payload:{name}\n".encode() for name in MODULE.PAYLOAD_NAMES}
    payloads["round11_daadx_phase1_results.json"] = MODULE.canonical_json_bytes(
        _results(passed=passed)
    )
    return payloads


def test_artifacts_match_frozen_amendment_exactly() -> None:
    amendment = json.loads(AMENDMENT.read_text(encoding="utf-8"))
    assert tuple(amendment["artifact_contract"]["exact_files"]) == MODULE.ARTIFACTS
    assert MODULE.INDEX_NAME == MODULE.ARTIFACTS[-1]
    assert set(amendment["outcomes"]) == {MODULE.PASS_OUTCOME, MODULE.STOP_OUTCOME}


def test_claim_exact_payload_is_durable_and_never_reused(tmp_path: Path) -> None:
    claim = (tmp_path / "claim.json").resolve()
    payload = MODULE.acquire_persistent_claim(
        claim, binding_sha256=SHA, random_token=TOKEN
    )
    assert claim.read_bytes() == payload
    assert json.loads(payload) == MODULE.claim_payload(SHA, TOKEN)
    assert MODULE.claim_payload(SHA.lower(), TOKEN.lower())["random_token"] == TOKEN
    with pytest.raises(FileExistsError, match="already exists"):
        MODULE.acquire_persistent_claim(claim, binding_sha256=SHA, random_token=TOKEN)
    assert claim.read_bytes() == payload


@pytest.mark.parametrize("error_type", [RuntimeError, KeyboardInterrupt])
def test_failure_after_claim_creation_leaves_blocking_residue(
    tmp_path: Path, error_type
) -> None:
    claim = (tmp_path / "claim.json").resolve()
    def crash(_path: Path) -> None:
        raise error_type("injected crash")

    with pytest.raises(error_type, match="injected crash"):
        MODULE.acquire_persistent_claim(
            claim, binding_sha256=SHA, random_token=TOKEN, after_create_hook=crash
        )
    assert claim.exists() and claim.read_bytes() == b""
    with pytest.raises(FileExistsError):
        MODULE.acquire_persistent_claim(claim, binding_sha256=SHA, random_token=TOKEN)


@pytest.mark.parametrize("failure", ["file", "directory"])
def test_initial_durability_failure_blocks_and_never_reaches_hook(
    tmp_path: Path, failure: str
) -> None:
    claim = (tmp_path / "claim.json").resolve()
    reached: list[bool] = []
    def fail_file(_descriptor: int) -> None:
        raise OSError("injected file fsync failure")
    def fail_directory(_path: Path) -> None:
        raise OSError("injected directory fsync failure")

    kwargs = {
        "file_fsync": fail_file if failure == "file" else os.fsync,
        "directory_fsync": fail_directory if failure == "directory" else MODULE.sync_directory_strict,
    }
    with pytest.raises(OSError, match="injected"):
        MODULE.acquire_persistent_claim(
            claim,
            binding_sha256=SHA,
            random_token=TOKEN,
            after_create_hook=lambda _path: reached.append(True),
            **kwargs,
        )
    assert claim.exists()
    assert reached == []
    with pytest.raises(FileExistsError):
        MODULE.acquire_persistent_claim(claim, binding_sha256=SHA, random_token=TOKEN)


def test_claim_path_replacement_is_detected_and_replacement_blocks(tmp_path: Path) -> None:
    claim = (tmp_path / "claim.json").resolve()
    replacement = tmp_path / "replacement"
    replacement.write_bytes(b"replacement")
    prevented: list[bool] = []
    def replace(_path: Path) -> None:
        try:
            os.replace(replacement, claim)
        except PermissionError:
            prevented.append(True)

    try:
        MODULE.acquire_persistent_claim(
            claim, binding_sha256=SHA, random_token=TOKEN, after_create_hook=replace
        )
    except MODULE.Phase1ControlError as error:
        assert "path/inode changed" in str(error)
        assert not prevented and claim.read_bytes() == b"replacement"
    else:
        assert prevented and json.loads(claim.read_text(encoding="utf-8"))["schema_version"] == MODULE.CLAIM_SCHEMA
    with pytest.raises(FileExistsError):
        MODULE.acquire_persistent_claim(claim, binding_sha256=SHA, random_token=TOKEN)


@pytest.mark.parametrize("failure", ["second_file", "second_directory"])
def test_post_durability_sync_failure_still_blocks(
    tmp_path: Path, failure: str
) -> None:
    claim = (tmp_path / "claim.json").resolve()
    file_calls = 0
    directory_calls = 0
    reached: list[bool] = []
    def file_sync(descriptor: int) -> None:
        nonlocal file_calls
        file_calls += 1
        if failure == "second_file" and file_calls == 2:
            raise OSError("injected second file fsync failure")
        os.fsync(descriptor)
    def directory_sync(path: Path) -> None:
        nonlocal directory_calls
        directory_calls += 1
        if failure == "second_directory" and directory_calls == 2:
            raise OSError("injected second directory fsync failure")
        MODULE.sync_directory_strict(path)

    with pytest.raises(OSError, match="injected second"):
        MODULE.acquire_persistent_claim(
            claim,
            binding_sha256=SHA,
            random_token=TOKEN,
            after_create_hook=lambda _path: reached.append(True),
            file_fsync=file_sync,
            directory_fsync=directory_sync,
        )
    assert reached == [True]
    assert claim.exists()
    with pytest.raises(FileExistsError):
        MODULE.acquire_persistent_claim(claim, binding_sha256=SHA, random_token=TOKEN)


def test_final_directory_sync_cannot_silently_replace_claim(tmp_path: Path) -> None:
    claim = (tmp_path / "claim.json").resolve()
    replacement = tmp_path / "replacement"
    replacement.write_bytes(b"replacement")
    calls = 0
    prevented: list[bool] = []
    def directory_sync(path: Path) -> None:
        nonlocal calls
        calls += 1
        MODULE.sync_directory_strict(path)
        if calls == 2:
            try:
                os.replace(replacement, claim)
            except PermissionError:
                prevented.append(True)

    try:
        payload = MODULE.acquire_persistent_claim(
            claim,
            binding_sha256=SHA,
            random_token=TOKEN,
            directory_fsync=directory_sync,
        )
    except MODULE.Phase1ControlError as error:
        assert "path/inode changed" in str(error)
        assert not prevented and claim.read_bytes() == b"replacement"
    else:
        assert prevented and claim.read_bytes() == payload
    with pytest.raises(FileExistsError):
        MODULE.acquire_persistent_claim(claim, binding_sha256=SHA, random_token=TOKEN)


def test_two_process_claim_race_has_exactly_one_winner(tmp_path: Path) -> None:
    claim = (tmp_path / "claim.json").resolve()
    code = (
        "from pathlib import Path; "
        "from arsc_eval.round11_phase1_control import acquire_persistent_claim; "
        "import sys; "
        f"p=Path({str(claim)!r}); "
        "\ntry:\n acquire_persistent_claim(p,binding_sha256='A'*64,random_token='B'*64)\n"
        "except FileExistsError:\n sys.exit(23)\n"
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT / "src")
    processes = [
        subprocess.Popen([sys.executable, "-c", code], cwd=ROOT, env=environment)
        for _ in range(2)
    ]
    codes = sorted(process.wait(timeout=20) for process in processes)
    assert codes == [0, 23]
    assert json.loads(claim.read_text(encoding="utf-8"))["schema_version"] == MODULE.CLAIM_SCHEMA


def test_existing_symlink_claim_rejected_when_supported(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_bytes(b"target")
    claim = (tmp_path / "claim.json").resolve()
    try:
        claim.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink unavailable")
    with pytest.raises(FileExistsError):
        MODULE.acquire_persistent_claim(claim, binding_sha256=SHA, random_token=TOKEN)
    assert target.read_bytes() == b"target"


@pytest.mark.parametrize(
    "mutate,message",
    [
        (lambda r: r.__setitem__("training_authorized", True), "training"),
        (lambda r: r.__setitem__("is_formal_g0_g8_verdict", True), "formal"),
        (lambda r: r["gates"].__setitem__("G4", "PASS"), "G4"),
        (lambda r: r["gates"].__setitem__("G8", "PASS"), "gate field"),
        (lambda r: r.__setitem__("outcome", MODULE.STOP_OUTCOME), "outcome"),
        (lambda r: r.__setitem__("extra", 1), "field set"),
    ],
)
def test_invalid_results_fail_closed(mutate, message: str) -> None:
    result = _results()
    mutate(result)
    with pytest.raises(MODULE.Phase1ControlError, match=message):
        MODULE.validate_results_payload(result)


@pytest.mark.parametrize("passed", [True, False])
def test_atomic_publication_and_full_closure(tmp_path: Path, passed: bool) -> None:
    staging = (tmp_path / "attempt.staging").resolve()
    final = (tmp_path / "attempt").resolve()
    MODULE.publish_phase1_atomically(staging, final, _payloads(passed=passed))
    assert not staging.exists()
    assert MODULE.verify_phase1_closure(final)
    assert {item.name for item in final.iterdir()} == set(MODULE.ARTIFACTS)
    index = json.loads((final / MODULE.INDEX_NAME).read_text(encoding="utf-8"))
    assert index["artifact_count"] == 15
    assert all(row["path"] != MODULE.INDEX_NAME for row in index["artifacts"])


def test_rename_failure_preserves_complete_staging(tmp_path: Path) -> None:
    staging = (tmp_path / "attempt.staging").resolve()
    final = (tmp_path / "attempt").resolve()
    def fail_rename(_source: Path, _target: Path) -> None:
        raise OSError("injected rename failure")

    with pytest.raises(OSError, match="injected rename failure"):
        MODULE.publish_phase1_atomically(
            staging, final, _payloads(), rename_func=fail_rename
        )
    assert staging.is_dir() and not final.exists()
    assert {item.name for item in staging.iterdir()} == set(MODULE.ARTIFACTS)


def test_competitor_final_is_preserved_and_staging_retained(tmp_path: Path) -> None:
    staging = (tmp_path / "attempt.staging").resolve()
    final = (tmp_path / "attempt").resolve()
    def competitor(_source: Path, target: Path) -> None:
        target.mkdir()
        (target / "owner").write_bytes(b"competitor")
        raise FileExistsError("competitor won")

    with pytest.raises(FileExistsError, match="competitor won"):
        MODULE.publish_phase1_atomically(
            staging, final, _payloads(), rename_func=competitor
        )
    assert (final / "owner").read_bytes() == b"competitor"
    assert staging.is_dir()


@pytest.mark.parametrize("which", ["staging", "final"])
def test_preexisting_publication_path_blocks_without_mutation(tmp_path: Path, which: str) -> None:
    staging = (tmp_path / "attempt.staging").resolve()
    final = (tmp_path / "attempt").resolve()
    target = staging if which == "staging" else final
    target.mkdir()
    (target / "owner").write_bytes(b"owner")
    with pytest.raises(FileExistsError, match="already exists"):
        MODULE.publish_phase1_atomically(staging, final, _payloads())
    assert (target / "owner").read_bytes() == b"owner"


def test_tamper_or_extra_file_breaks_closure(tmp_path: Path) -> None:
    final = (tmp_path / "attempt").resolve()
    MODULE.publish_phase1_atomically((tmp_path / "staging").resolve(), final, _payloads())
    (final / "round11_daadx_phase1.log").write_bytes(b"tampered")
    assert not MODULE.verify_phase1_closure(final)
    (final / "extra").write_bytes(b"extra")
    assert not MODULE.verify_phase1_closure(final)


@pytest.mark.parametrize("target", ["index", "results"])
def test_duplicate_key_or_noncanonical_json_breaks_closure(tmp_path: Path, target: str) -> None:
    final = (tmp_path / "attempt").resolve()
    MODULE.publish_phase1_atomically((tmp_path / "staging").resolve(), final, _payloads())
    path = final / (
        MODULE.INDEX_NAME if target == "index" else "round11_daadx_phase1_results.json"
    )
    raw = path.read_bytes()
    if target == "index":
        changed = raw.replace(b'"artifact_count":15', b'"artifact_count":999,"artifact_count":15')
    else:
        changed = raw.replace(b'"training_authorized":false', b'"training_authorized":true,"training_authorized":false')
    path.write_bytes(changed)
    assert not MODULE.verify_phase1_closure(final)


def test_artifact_path_replacement_during_read_is_detected(tmp_path: Path) -> None:
    path = tmp_path / "artifact"
    replacement = tmp_path / "replacement"
    path.write_bytes(b"original")
    replacement.write_bytes(b"replacement")
    prevented: list[bool] = []
    def replace(target: Path) -> None:
        try:
            os.replace(replacement, target)
        except PermissionError:
            prevented.append(True)

    try:
        value = MODULE.read_regular_stable(path, after_open_hook=replace)
    except MODULE.Phase1ControlError as error:
        assert "path/inode changed" in str(error)
        assert not prevented
    else:
        assert prevented and value == b"original"


def test_post_rehash_failure_retains_blocking_final(tmp_path: Path) -> None:
    staging = (tmp_path / "staging").resolve()
    final = (tmp_path / "final").resolve()
    def rename_then_tamper(source: Path, target: Path) -> None:
        MODULE.rename_directory_no_replace(source, target)
        (target / "round11_daadx_phase1.log").write_bytes(b"tampered")

    with pytest.raises(MODULE.Phase1ControlError, match="post-publish"):
        MODULE.publish_phase1_atomically(
            staging, final, _payloads(), rename_func=rename_then_tamper
        )
    assert final.is_dir() and not staging.exists()
    assert not MODULE.verify_phase1_closure(final)
    with pytest.raises(FileExistsError):
        MODULE.publish_phase1_atomically(staging, final, _payloads())
