from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from arsc_eval import round11_layout_control as control  # noqa: E402
from arsc_eval.round11_layout_inventory import DEFAULT_LIMITS  # noqa: E402


SHA = "A" * 64
TOKEN = "B" * 64
PROTOCOL = ROOT / "outputs/validity/round11_daadx_layout_inventory_protocol.json"


ARCHIVE_BYTES = 100
ARCHIVE_SHA = "C" * 64


def _results(*, complete: bool, empty: bool = False) -> dict:
    statuses = {name: "OBSERVED_COMPLETE" for name in control.PAYLOAD_NAMES}
    if not complete:
        inventory_status = "ABSENT_REPRESENTED_EMPTY" if empty else "OBSERVED_PARTIAL"
        statuses[control.PUBLIC_NAME] = inventory_status
        statuses[control.RESTRICTED_NAME] = inventory_status
    return {
        "schema_version": control.RESULTS_SCHEMA,
        "phase": control.PHASE,
        "attempt": control.ATTEMPT,
        "outcome": control.COMPLETE_OUTCOME if complete else control.STOP_OUTCOME,
        "completeness": control.COMPLETE_CLOSURE if complete else control.STOP_CLOSURE,
        "layout_complete": complete,
        "observed_scope": "COMPLETE_STREAM" if complete else "SUPPLIED_PREFIX",
        "first_failure_stage": None if complete else "ARCHIVE_FEED",
        "first_failure_code": None if complete else "SYNTHETIC_POLICY_FAILURE",
        "artifact_status": statuses,
        "is_phase1_or_g0_g8_verdict": False,
        "external_validity_established": False,
        "training_authorized": False,
    }


def _authority_payload(name: str) -> bytes:
    return f"synthetic-authority:{name}\n".encode()


def _expectations() -> control.ClosureExpectations:
    authorities = tuple(
        control.AuthorityExpectation(
            name=name,
            bytes=len(_authority_payload(name)),
            sha256=control.sha256_bytes(_authority_payload(name)),
            required_complete=index < 3,
        )
        for index, name in enumerate(control.ARTIFACTS[:5])
    )
    return control.ClosureExpectations(
        authorities=authorities,
        archive=control.ArchiveExpectation(ARCHIVE_BYTES, ARCHIVE_SHA),
    )


def _inventories(rows: int) -> tuple[bytes, bytes]:
    public = bytearray(control.PUBLIC_HEADER)
    restricted = bytearray()
    for ordinal in range(1, rows + 1):
        path = f"private/path/{ordinal:06d}.bin"
        raw_hash = control.sha256_bytes(path.encode("utf-8"))
        resolved_hash = raw_hash
        public.extend(
            f"{ordinal},{raw_hash},{resolved_hash},REGULAR,1,\n".encode("ascii")
        )
        restricted.extend(
            control.canonical_json_bytes(
                {
                    "member_ordinal": ordinal,
                    "member_type": "REGULAR",
                    "pax_flags": [],
                    "pax_path": None,
                    "raw_header_path": path,
                    "raw_path_sha256": raw_hash,
                    "resolved_path": path,
                    "resolved_path_sha256": resolved_hash,
                    "size": 1,
                }
            )
        )
    return bytes(public), bytes(restricted)


def _populate(
    staging: Path,
    *,
    complete: bool = True,
    rows: int = 1,
    empty: bool = False,
) -> None:
    public, restricted = _inventories(0 if empty else rows)
    for name in control.PAYLOAD_NAMES:
        payload = f"synthetic:{name}\n".encode()
        if name in control.ARTIFACTS[:5]:
            payload = _authority_payload(name)
        elif name == control.ARTIFACTS[5]:
            payload = control.canonical_json_bytes(
                {
                    "schema_version": control.ARCHIVE_HASHES_SCHEMA,
                    "phase": control.PHASE,
                    "attempt": control.ATTEMPT,
                    "expected_bytes": ARCHIVE_BYTES,
                    "expected_sha256": ARCHIVE_SHA,
                    "observed_scope": "COMPLETE_STREAM" if complete else "SUPPLIED_PREFIX",
                    "observed_bytes": ARCHIVE_BYTES if complete else 5,
                    "observed_sha256": ARCHIVE_SHA if complete else "D" * 64,
                    "complete_stream_matches_expected": complete,
                }
            )
        elif name == control.ARTIFACTS[6]:
            metrics = {
                "uncompressed_tar_stream_bytes": rows * 1024 + 1024,
                "raw_header_count": rows,
                "logical_member_count": rows,
                "regular_member_count": rows,
                "directory_member_count": 0,
                "total_regular_payload_bytes": rows,
                "post_end_zero_padding_bytes": 0,
            }
            if not complete:
                metrics = {field: None for field in metrics}
            payload = control.canonical_json_bytes(
                {
                    "schema_version": control.SUMMARY_SCHEMA,
                    "phase": control.PHASE,
                    "attempt": control.ATTEMPT,
                    "status": "COMPLETE" if complete else "INCONCLUSIVE",
                    "public_rows_observed": 0 if empty else rows,
                    "restricted_rows_observed": 0 if empty else rows,
                    **metrics,
                }
            )
        elif name == control.PUBLIC_NAME:
            payload = public
        elif name == control.RESTRICTED_NAME:
            payload = restricted
        if name == control.RESULTS_NAME:
            payload = control.canonical_json_bytes(
                _results(complete=complete, empty=empty)
            )
        (staging / name).write_bytes(payload)


def _staging(
    tmp_path: Path,
) -> tuple[Path, Path, control.ClaimAcquisition]:
    acquisition = control.acquire_persistent_claim(
        (tmp_path / "claim.json").resolve(),
        binding_sha256=SHA,
        random_token=TOKEN,
    )
    staging = (tmp_path / "attempt.staging").resolve()
    final = (tmp_path / "attempt").resolve()
    control.create_exclusive_staging(acquisition.lease, staging, final)
    return staging, final, acquisition


def _update_json(path: Path, **changes: object) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    value.update(changes)
    path.write_bytes(control.canonical_json_bytes(value))


def _replace_inventory_path(staging: Path, ordinal: int, path: str) -> None:
    raw_hash = control.sha256_bytes(path.encode("utf-8"))
    public_path = staging / control.PUBLIC_NAME
    public_lines = public_path.read_bytes().splitlines(keepends=True)
    fields = public_lines[ordinal].rstrip(b"\n").split(b",")
    fields[1] = raw_hash.encode("ascii")
    fields[2] = raw_hash.encode("ascii")
    public_lines[ordinal] = b",".join(fields) + b"\n"
    public_path.write_bytes(b"".join(public_lines))

    restricted_path = staging / control.RESTRICTED_NAME
    restricted_lines = restricted_path.read_bytes().splitlines(keepends=True)
    row = json.loads(restricted_lines[ordinal - 1])
    row.update(
        {
            "raw_header_path": path,
            "raw_path_sha256": raw_hash,
            "resolved_path": path,
            "resolved_path_sha256": raw_hash,
        }
    )
    restricted_lines[ordinal - 1] = control.canonical_json_bytes(row)
    restricted_path.write_bytes(b"".join(restricted_lines))


def test_constants_match_frozen_protocol_exactly() -> None:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    assert tuple(protocol["artifact_contract"]["exact_files"]) == control.ARTIFACTS
    assert protocol["execution_control"]["claim_path"].endswith(
        ".round11_daadx_layout_inventory_attempt01.claim"
    )
    assert set(protocol["outcomes"]) == {
        control.COMPLETE_OUTCOME,
        control.STOP_OUTCOME,
    }
    assert control.ARTIFACT_CAPS[control.PUBLIC_NAME] == protocol["resource_bounds"][
        "max_public_inventory_output_bytes"
    ]
    assert control.ARTIFACT_CAPS[control.RESTRICTED_NAME] == protocol["resource_bounds"][
        "max_restricted_path_seal_output_bytes"
    ]
    assert control.ARTIFACT_CAPS[control.LOG_NAME] == protocol["resource_bounds"][
        "max_execution_log_output_bytes"
    ]


def test_claim_is_exact_durable_and_never_reused(tmp_path: Path) -> None:
    claim = (tmp_path / "claim.json").resolve()
    acquisition = control.acquire_persistent_claim(
        claim, binding_sha256=SHA, random_token=TOKEN
    )
    assert claim.read_bytes() == acquisition.payload
    assert json.loads(acquisition.payload) == control.claim_payload(SHA, TOKEN)
    with pytest.raises(FileExistsError, match="already exists"):
        control.acquire_persistent_claim(
            claim, binding_sha256=SHA, random_token=TOKEN
        )
    assert claim.read_bytes() == acquisition.payload
    acquisition.lease.close()


@pytest.mark.parametrize("error_type", [RuntimeError, KeyboardInterrupt])
def test_failure_after_claim_create_retains_blocking_zero_entry(
    tmp_path: Path, error_type
) -> None:
    claim = (tmp_path / "claim.json").resolve()

    def crash(_path: Path) -> None:
        raise error_type("injected")

    with pytest.raises(error_type, match="injected"):
        control.acquire_persistent_claim(
            claim,
            binding_sha256=SHA,
            random_token=TOKEN,
            after_create_hook=crash,
        )
    assert claim.is_file() and claim.read_bytes() == b""
    with pytest.raises(FileExistsError):
        control.acquire_persistent_claim(
            claim, binding_sha256=SHA, random_token=TOKEN
        )


@pytest.mark.parametrize("failure", ["file", "directory"])
def test_initial_claim_durability_failure_retains_entry_and_skips_hook(
    tmp_path: Path, failure: str
) -> None:
    claim = (tmp_path / "claim.json").resolve()
    reached = []

    def fail_file(_descriptor: int) -> None:
        raise OSError("injected file fsync")

    def fail_directory(_path: Path) -> None:
        raise OSError("injected directory fsync")

    with pytest.raises(OSError, match="injected"):
        control.acquire_persistent_claim(
            claim,
            binding_sha256=SHA,
            random_token=TOKEN,
            after_create_hook=lambda _path: reached.append(True),
            file_fsync=fail_file if failure == "file" else os.fsync,
            directory_fsync=(
                fail_directory if failure == "directory" else control.sync_directory_strict
            ),
        )
    assert claim.exists() and reached == []


def test_two_process_claim_race_has_one_winner(tmp_path: Path) -> None:
    claim = (tmp_path / "claim.json").resolve()
    code = (
        "from pathlib import Path; import sys; "
        "from arsc_eval.round11_layout_control import acquire_persistent_claim; "
        f"p=Path({str(claim)!r});\n"
        "try:\n acquire_persistent_claim(p,binding_sha256='A'*64,random_token='B'*64)\n"
        "except FileExistsError:\n sys.exit(23)\n"
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT / "src")
    processes = [
        subprocess.Popen([sys.executable, "-c", code], cwd=ROOT, env=environment)
        for _ in range(2)
    ]
    assert sorted(process.wait(timeout=20) for process in processes) == [0, 23]
    assert json.loads(claim.read_text(encoding="utf-8"))["schema_version"] == control.CLAIM_SCHEMA


def test_claim_path_replacement_is_detected_or_prevented(tmp_path: Path) -> None:
    claim = (tmp_path / "claim.json").resolve()
    replacement = tmp_path / "replacement"
    replacement.write_bytes(b"replacement")
    prevented = []

    def replace(_path: Path) -> None:
        try:
            os.replace(replacement, claim)
        except PermissionError:
            prevented.append(True)

    try:
        acquisition = control.acquire_persistent_claim(
            claim,
            binding_sha256=SHA,
            random_token=TOKEN,
            after_create_hook=replace,
        )
    except control.LayoutControlError as error:
        assert "path/inode changed" in str(error)
        assert not prevented and claim.read_bytes() == b"replacement"
    else:
        assert prevented and claim.read_bytes() == acquisition.payload
        acquisition.lease.close()
    with pytest.raises(FileExistsError):
        control.acquire_persistent_claim(
            claim, binding_sha256=SHA, random_token=TOKEN
        )


def test_staging_creation_is_exclusive_and_failure_residue_is_retained(
    tmp_path: Path,
) -> None:
    acquisition = control.acquire_persistent_claim(
        (tmp_path / "claim.json").resolve(), binding_sha256=SHA, random_token=TOKEN
    )
    staging = (tmp_path / "attempt.staging").resolve()
    final = (tmp_path / "attempt").resolve()
    control.create_exclusive_staging(acquisition.lease, staging, final)
    assert staging.is_dir()
    with pytest.raises(FileExistsError):
        control.create_exclusive_staging(acquisition.lease, staging, final)
    acquisition.lease.close()


def test_staging_final_alias_rejected_before_creation(tmp_path: Path) -> None:
    acquisition = control.acquire_persistent_claim(
        (tmp_path / "claim.json").resolve(), binding_sha256=SHA, random_token=TOKEN
    )
    alias = (tmp_path / "attempt").resolve()
    with pytest.raises(control.LayoutControlError, match="alias"):
        control.create_exclusive_staging(acquisition.lease, alias, alias)
    assert not alias.exists()
    acquisition.lease.close()


def test_claim_and_parent_are_held_against_unlink_or_replacement_on_windows(
    tmp_path: Path,
) -> None:
    claim = (tmp_path / "claim.json").resolve()
    acquisition = control.acquire_persistent_claim(
        claim, binding_sha256=SHA, random_token=TOKEN
    )
    if os.name == "nt":
        with pytest.raises(PermissionError):
            claim.unlink()
        moved = tmp_path.with_name(tmp_path.name + "-moved")
        with pytest.raises(PermissionError):
            os.rename(tmp_path, moved)
        acquisition.lease.verify_claim()
    else:
        pytest.skip("formal lifetime delete-denial is Windows-only")
    acquisition.lease.close()


def test_claim_content_tamper_is_prevented_or_detected(tmp_path: Path) -> None:
    claim = (tmp_path / "claim.json").resolve()
    acquisition = control.acquire_persistent_claim(
        claim, binding_sha256=SHA, random_token=TOKEN
    )
    try:
        claim.write_bytes(b"tampered")
    except PermissionError:
        acquisition.lease.verify_claim()
    else:
        with pytest.raises(control.LayoutControlError, match="claim bytes changed"):
            acquisition.lease.verify_claim()
    acquisition.lease.close()


def test_failed_staging_directory_sync_retains_residue(tmp_path: Path) -> None:
    acquisition = control.acquire_persistent_claim(
        (tmp_path / "claim.json").resolve(), binding_sha256=SHA, random_token=TOKEN
    )
    staging = (tmp_path / "other.staging").resolve()
    final = (tmp_path / "other").resolve()

    def fail_sync(_path: Path) -> None:
        raise OSError("injected directory sync")

    with pytest.raises(OSError, match="injected"):
        control.create_exclusive_staging(
            acquisition.lease, staging, final, directory_fsync=fail_sync
        )
    assert staging.is_dir()
    acquisition.lease.close()


def test_whole_staging_tree_swap_is_prevented_or_detected(tmp_path: Path) -> None:
    staging, final, acquisition = _staging(tmp_path)
    _populate(staging)
    original = (tmp_path / "original-aside").resolve()
    attacker = (tmp_path / "attacker").resolve()
    attacker.mkdir()
    _populate(attacker)
    try:
        os.rename(staging, original)
    except PermissionError:
        assert os.name == "nt"
        acquisition.lease.verify_staging()
    else:
        os.rename(attacker, staging)
        with pytest.raises(control.LayoutControlError, match="leased path identity"):
            control.finalize_and_publish(
                acquisition.lease,
                staging,
                final,
                expectations=_expectations(),
            )
    acquisition.lease.close()


@pytest.mark.parametrize("complete", [True, False])
def test_complete_and_hash_closed_stop_publish_exact_streaming_closure(
    tmp_path: Path, complete: bool
) -> None:
    staging, final, acquisition = _staging(tmp_path)
    rows = 5_000 if complete else 1
    _populate(staging, complete=complete, rows=rows)
    control.finalize_and_publish(
        acquisition.lease,
        staging,
        final,
        expectations=_expectations(),
    )
    assert not staging.exists() and final.is_dir()
    assert control.verify_layout_closure(final, acquisition.lease, _expectations())
    assert {item.name for item in final.iterdir()} == set(control.ARTIFACTS)
    index = json.loads((final / control.INDEX_NAME).read_text(encoding="utf-8"))
    assert index["artifact_count"] == 11
    restricted = next(
        row for row in index["artifacts"] if row["path"] == control.RESTRICTED_NAME
    )
    if complete:
        assert restricted["bytes"] > 1_048_576
    else:
        assert restricted["bytes"] > 0
    acquisition.lease.close()


def test_hash_closed_stop_accepts_exact_empty_inventory_representation(
    tmp_path: Path,
) -> None:
    staging, final, acquisition = _staging(tmp_path)
    _populate(staging, complete=False, empty=True)
    control.finalize_and_publish(
        acquisition.lease, staging, final, expectations=_expectations()
    )
    assert control.verify_layout_closure(final, acquisition.lease, _expectations())
    assert (final / control.PUBLIC_NAME).read_bytes() == control.PUBLIC_HEADER
    assert (final / control.RESTRICTED_NAME).read_bytes() == b""
    acquisition.lease.close()


def test_hash_closed_stop_accepts_bound_optional_authority_absence(
    tmp_path: Path,
) -> None:
    staging, final, acquisition = _staging(tmp_path)
    _populate(staging, complete=False, empty=True)
    receipt = control.ARTIFACTS[3]
    (staging / receipt).write_bytes(b"")
    results = json.loads((staging / control.RESULTS_NAME).read_text(encoding="utf-8"))
    results["artifact_status"][receipt] = "ABSENT_REPRESENTED_EMPTY"
    (staging / control.RESULTS_NAME).write_bytes(control.canonical_json_bytes(results))
    control.finalize_and_publish(
        acquisition.lease, staging, final, expectations=_expectations()
    )
    assert control.verify_layout_closure(final, acquisition.lease, _expectations())
    acquisition.lease.close()


@pytest.mark.parametrize(
    "mutate,message",
    [
        (lambda r: r.__setitem__("training_authorized", True), "training"),
        (lambda r: r.__setitem__("external_validity_established", True), "external"),
        (lambda r: r.__setitem__("is_phase1_or_g0_g8_verdict", True), "G0-G8"),
        (lambda r: r.__setitem__("outcome", "INFRASTRUCTURE_ABORT"), "outcome"),
        (lambda r: r.__setitem__("completeness", "NONPUBLISHABLE_RESIDUE"), "closure"),
        (lambda r: r.__setitem__("layout_complete", True), "layout complete"),
        (lambda r: r["artifact_status"].__setitem__(control.RESULTS_NAME, "OBSERVED_PARTIAL"), "incomplete"),
        (lambda r: r.__setitem__("extra", 1), "field set"),
    ],
)
def test_invalid_or_infrastructure_results_cannot_publish(mutate, message: str) -> None:
    result = _results(complete=False)
    mutate(result)
    with pytest.raises(control.LayoutControlError, match=message):
        control.validate_results(result)


def test_duplicate_or_noncanonical_results_fail_before_index(tmp_path: Path) -> None:
    staging, final, acquisition = _staging(tmp_path)
    _populate(staging)
    path = staging / control.RESULTS_NAME
    raw = path.read_bytes()
    path.write_bytes(raw.replace(b'"training_authorized":false', b'"training_authorized":false,"training_authorized":false'))
    with pytest.raises(control.LayoutControlError, match="duplicate"):
        control.finalize_and_publish(
            acquisition.lease, staging, final, expectations=_expectations()
        )
    assert staging.is_dir() and not final.exists() and not (staging / control.INDEX_NAME).exists()
    acquisition.lease.close()


def test_substituted_required_authority_rejected(tmp_path: Path) -> None:
    staging, final, acquisition = _staging(tmp_path)
    _populate(staging)
    (staging / control.ARTIFACTS[0]).write_bytes(b"substituted\n")
    with pytest.raises(control.LayoutControlError, match="authority differs"):
        control.finalize_and_publish(
            acquisition.lease, staging, final, expectations=_expectations()
        )
    assert not (staging / control.INDEX_NAME).exists()
    acquisition.lease.close()


@pytest.mark.parametrize(
    "contradiction",
    ["scope", "summary", "absent_nonempty", "raw_public"],
)
def test_contradictory_hash_closed_stop_is_rejected(
    tmp_path: Path, contradiction: str
) -> None:
    staging, final, acquisition = _staging(tmp_path)
    _populate(staging, complete=False, rows=1, empty=contradiction == "absent_nonempty")
    if contradiction == "scope":
        hashes = json.loads((staging / control.ARTIFACTS[5]).read_text(encoding="utf-8"))
        hashes.update(
            {
                "observed_scope": "COMPLETE_STREAM",
                "observed_bytes": ARCHIVE_BYTES,
                "observed_sha256": ARCHIVE_SHA,
                "complete_stream_matches_expected": True,
            }
        )
        (staging / control.ARTIFACTS[5]).write_bytes(
            control.canonical_json_bytes(hashes)
        )
    elif contradiction == "summary":
        (staging / control.ARTIFACTS[6]).write_bytes(b"not-json\n")
    elif contradiction == "absent_nonempty":
        (staging / control.RESTRICTED_NAME).write_bytes(b"42 nonempty bytes")
    else:
        (staging / control.PUBLIC_NAME).write_bytes(
            control.PUBLIC_HEADER
            + b"1,raw/private/path,"
            + b"F" * 64
            + b",REGULAR,1,\n"
        )
    with pytest.raises((control.LayoutControlError, json.JSONDecodeError, UnicodeError)):
        control.finalize_and_publish(
            acquisition.lease, staging, final, expectations=_expectations()
        )
    assert not (staging / control.INDEX_NAME).exists()
    acquisition.lease.close()


def test_rename_failure_preserves_complete_indexed_staging(tmp_path: Path) -> None:
    staging, final, acquisition = _staging(tmp_path)
    _populate(staging)

    def fail(_source: Path, _target: Path) -> None:
        raise OSError("injected rename")

    with pytest.raises(OSError, match="injected"):
        control.finalize_and_publish(
            acquisition.lease,
            staging,
            final,
            expectations=_expectations(),
            rename_func=fail,
        )
    assert staging.is_dir() and not final.exists()
    assert {item.name for item in staging.iterdir()} == set(control.ARTIFACTS)
    acquisition.lease.close()


def test_competitor_final_is_preserved_and_staging_retained(tmp_path: Path) -> None:
    staging, final, acquisition = _staging(tmp_path)
    _populate(staging)

    def competitor(_source: Path, target: Path) -> None:
        target.mkdir()
        (target / "owner").write_bytes(b"competitor")
        raise FileExistsError("competitor")

    with pytest.raises(FileExistsError, match="competitor"):
        control.finalize_and_publish(
            acquisition.lease,
            staging,
            final,
            expectations=_expectations(),
            rename_func=competitor,
        )
    assert (final / "owner").read_bytes() == b"competitor"
    assert {item.name for item in staging.iterdir()} == set(control.ARTIFACTS)
    acquisition.lease.close()


def test_postrename_tamper_leaves_blocking_unverified_final(tmp_path: Path) -> None:
    staging, final, acquisition = _staging(tmp_path)
    _populate(staging)

    def rename_then_tamper(source: Path, target: Path) -> None:
        control.rename_directory_no_replace(source, target)
        (target / control.LOG_NAME).write_bytes(b"tampered")

    with pytest.raises(control.LayoutControlError, match="post-publish"):
        control.finalize_and_publish(
            acquisition.lease,
            staging,
            final,
            expectations=_expectations(),
            rename_func=rename_then_tamper,
        )
    assert final.is_dir() and not staging.exists()
    assert not control.verify_layout_closure(final, acquisition.lease, _expectations())
    acquisition.lease.close()


def test_tamper_extra_symlink_or_hardlink_breaks_closure(tmp_path: Path) -> None:
    staging, final, acquisition = _staging(tmp_path)
    _populate(staging)
    control.finalize_and_publish(
        acquisition.lease, staging, final, expectations=_expectations()
    )
    (final / control.LOG_NAME).write_bytes(b"tampered")
    assert not control.verify_layout_closure(final, acquisition.lease, _expectations())
    (final / "extra").write_bytes(b"extra")
    assert not control.verify_layout_closure(final, acquisition.lease, _expectations())
    acquisition.lease.close()


def test_extra_entry_inserted_during_verification_is_caught(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging, final, acquisition = _staging(tmp_path)
    _populate(staging)
    control.finalize_and_publish(
        acquisition.lease, staging, final, expectations=_expectations()
    )
    original = control.digest_regular_stable
    calls = 0

    def insert(path: Path, **kwargs):
        nonlocal calls
        calls += 1
        observed = original(path, **kwargs)
        if calls == 3:
            (final / "concurrent-extra").write_bytes(b"extra")
        return observed

    monkeypatch.setattr(control, "digest_regular_stable", insert)
    assert not control.verify_layout_closure(
        final, acquisition.lease, _expectations()
    )
    acquisition.lease.close()


def test_stream_digest_cap_and_replacement_are_fail_closed(tmp_path: Path) -> None:
    path = (tmp_path / "artifact").resolve()
    replacement = tmp_path / "replacement"
    path.write_bytes(b"original")
    replacement.write_bytes(b"replacement")
    with pytest.raises(control.LayoutControlError, match="byte cap"):
        control.digest_regular_stable(path, max_bytes=1)
    prevented = []

    def replace(target: Path) -> None:
        try:
            os.replace(replacement, target)
        except PermissionError:
            prevented.append(True)

    try:
        observed = control.digest_regular_stable(
            path, max_bytes=100, after_open_hook=replace
        )
    except control.LayoutControlError as error:
        assert "path/inode changed" in str(error)
        assert not prevented
    else:
        assert prevented and observed.sha256 == control.sha256_bytes(b"original")


def test_stream_digest_rejects_hardlink_and_symlink(tmp_path: Path) -> None:
    target = (tmp_path / "target").resolve()
    hardlink = (tmp_path / "hardlink").resolve()
    target.write_bytes(b"owned")
    os.link(target, hardlink)
    with pytest.raises(control.LayoutControlError, match="hard-linked"):
        control.digest_regular_stable(hardlink, max_bytes=100)
    hardlink.unlink()
    symlink = (tmp_path / "symlink").resolve()
    try:
        symlink.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink unavailable")
    with pytest.raises((OSError, control.LayoutControlError)):
        control.digest_regular_stable(symlink, max_bytes=100)


def test_existing_index_or_missing_payload_blocks_publication(tmp_path: Path) -> None:
    staging, final, acquisition = _staging(tmp_path)
    _populate(staging)
    (staging / control.INDEX_NAME).write_bytes(b"owner")
    with pytest.raises(control.LayoutControlError, match="already exists"):
        control.finalize_and_publish(
            acquisition.lease, staging, final, expectations=_expectations()
        )
    (staging / control.INDEX_NAME).unlink()
    (staging / control.PUBLIC_NAME).unlink()
    with pytest.raises(control.LayoutControlError, match="allowlist"):
        control.finalize_and_publish(
            acquisition.lease, staging, final, expectations=_expectations()
        )
    acquisition.lease.close()


def test_boolean_archive_byte_count_is_rejected(tmp_path: Path) -> None:
    staging, _, acquisition = _staging(tmp_path)
    _populate(staging)
    archive_path = staging / control.ARTIFACTS[5]
    archive = json.loads(archive_path.read_text(encoding="utf-8"))
    archive["observed_bytes"] = True
    archive_path.write_bytes(control.canonical_json_bytes(archive))
    assert not control.verify_layout_closure(
        staging, acquisition.lease, _expectations()
    )
    acquisition.lease.close()


def test_boolean_restricted_numeric_field_is_rejected(tmp_path: Path) -> None:
    staging, _, acquisition = _staging(tmp_path)
    _populate(staging)
    restricted_path = staging / control.RESTRICTED_NAME
    row = json.loads(restricted_path.read_text(encoding="utf-8"))
    row["member_ordinal"] = True
    restricted_path.write_bytes(control.canonical_json_bytes(row))
    assert not control.verify_layout_closure(
        staging, acquisition.lease, _expectations()
    )
    acquisition.lease.close()


def test_malformed_external_types_are_fail_closed(tmp_path: Path) -> None:
    staging, _, acquisition = _staging(tmp_path)
    _populate(staging)
    results_path = staging / control.RESULTS_NAME
    results = json.loads(results_path.read_text(encoding="utf-8"))
    results["artifact_status"][control.LOG_NAME] = []
    results_path.write_bytes(control.canonical_json_bytes(results))
    assert not control.verify_layout_closure(
        staging, acquisition.lease, _expectations()
    )
    acquisition.lease.close()


def test_partial_stop_preserves_restricted_terminal_fragment(tmp_path: Path) -> None:
    staging, final, acquisition = _staging(tmp_path)
    _populate(staging, complete=False)
    restricted_path = staging / control.RESTRICTED_NAME
    truncated = restricted_path.read_bytes()[:-5]
    restricted_path.write_bytes(truncated)
    _update_json(
        staging / control.ARTIFACTS[6],
        public_rows_observed=1,
        restricted_rows_observed=0,
    )
    control.finalize_and_publish(
        acquisition.lease, staging, final, expectations=_expectations()
    )
    assert (final / control.RESTRICTED_NAME).read_bytes() == truncated
    assert control.verify_layout_closure(final, acquisition.lease, _expectations())
    acquisition.lease.close()


def test_partial_stop_accepts_only_one_public_lead_row(tmp_path: Path) -> None:
    staging, final, acquisition = _staging(tmp_path)
    _populate(staging, complete=False)
    (staging / control.RESTRICTED_NAME).write_bytes(b"")
    _update_json(
        staging / control.ARTIFACTS[6],
        public_rows_observed=1,
        restricted_rows_observed=0,
    )
    control.finalize_and_publish(
        acquisition.lease, staging, final, expectations=_expectations()
    )
    assert control.verify_layout_closure(final, acquisition.lease, _expectations())
    acquisition.lease.close()

    second = tmp_path / "two"
    second.mkdir()
    staging, final, acquisition = _staging(second)
    _populate(staging, complete=False, rows=2)
    (staging / control.RESTRICTED_NAME).write_bytes(b"")
    _update_json(
        staging / control.ARTIFACTS[6],
        public_rows_observed=2,
        restricted_rows_observed=0,
    )
    with pytest.raises(control.LayoutControlError, match="more than one"):
        control.finalize_and_publish(
            acquisition.lease, staging, final, expectations=_expectations()
        )
    acquisition.lease.close()


def test_complete_oversized_regular_member_is_rejected(tmp_path: Path) -> None:
    staging, final, acquisition = _staging(tmp_path)
    _populate(staging)
    oversized = DEFAULT_LIMITS.max_single_regular_member_bytes + 1
    public_path = staging / control.PUBLIC_NAME
    fields = public_path.read_bytes().splitlines()[1].split(b",")
    fields[4] = str(oversized).encode("ascii")
    public_path.write_bytes(control.PUBLIC_HEADER + b",".join(fields) + b"\n")
    restricted_path = staging / control.RESTRICTED_NAME
    restricted = json.loads(restricted_path.read_text(encoding="utf-8"))
    restricted["size"] = oversized
    restricted_path.write_bytes(control.canonical_json_bytes(restricted))
    _update_json(
        staging / control.ARTIFACTS[6], total_regular_payload_bytes=oversized
    )
    with pytest.raises(control.LayoutControlError, match="size cap"):
        control.finalize_and_publish(
            acquisition.lease, staging, final, expectations=_expectations()
        )
    acquisition.lease.close()


@pytest.mark.parametrize(
    "changes",
    [
        {"total_regular_payload_bytes": 2},
        {"regular_member_count": 0, "directory_member_count": 1},
        {"raw_header_count": DEFAULT_LIMITS.max_raw_headers + 1},
        {
            "uncompressed_tar_stream_bytes":
            DEFAULT_LIMITS.max_uncompressed_tar_stream_bytes + 512
        },
        {
            "post_end_zero_padding_bytes":
            DEFAULT_LIMITS.max_post_end_zero_padding_bytes + 1
        },
    ],
)
def test_complete_summary_aggregate_or_cap_mismatch_is_rejected(
    tmp_path: Path, changes: dict[str, int]
) -> None:
    staging, final, acquisition = _staging(tmp_path)
    _populate(staging)
    _update_json(staging / control.ARTIFACTS[6], **changes)
    with pytest.raises(control.LayoutControlError):
        control.finalize_and_publish(
            acquisition.lease, staging, final, expectations=_expectations()
        )
    acquisition.lease.close()


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ("private/path/000001.bin", "duplicate resolved path"),
        ("PRIVATE/path/000001.bin", "casefold Unicode path collision"),
    ],
)
def test_complete_duplicate_or_casefold_collision_is_rejected(
    tmp_path: Path, replacement: str, message: str
) -> None:
    staging, final, acquisition = _staging(tmp_path)
    _populate(staging, rows=2)
    _replace_inventory_path(staging, 2, replacement)
    with pytest.raises(control.LayoutControlError, match=message):
        control.finalize_and_publish(
            acquisition.lease, staging, final, expectations=_expectations()
        )
    acquisition.lease.close()


def test_pax_flag_order_must_match_parser_emission_order() -> None:
    first = "GLOBAL_KEY_SHA256:" + "A" * 64
    second = "GLOBAL_KEY_SHA256:" + "B" * 64
    assert control._validate_flag_bytes(f"{first}|{second}".encode()) == (
        first,
        second,
    )
    with pytest.raises(control.LayoutControlError, match="flag order"):
        control._validate_flag_bytes(f"{second}|{first}".encode())
