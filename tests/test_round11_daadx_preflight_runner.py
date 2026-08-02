from __future__ import annotations

import csv
import io
import json
import subprocess
import sys
import tarfile
from collections import namedtuple
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_round11_daadx_preflight as runner
from arsc_eval.daadx_preflight import (
    GateStatus,
    STOP_VERDICT,
    canonical_json_sha256,
    sha256_file,
)


def make_tar_gz(
    path: Path,
    members: list[tuple[str, bytes | None, str]],
) -> Path:
    with tarfile.open(path, mode="w:gz", format=tarfile.PAX_FORMAT) as archive:
        for name, payload, kind in members:
            info = tarfile.TarInfo(name)
            info.mtime = 1
            if kind == "file":
                assert payload is not None
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
            elif kind == "directory":
                info.type = tarfile.DIRTYPE
                info.size = 0
                archive.addfile(info)
            elif kind == "symlink":
                info.type = tarfile.SYMTYPE
                info.linkname = "target"
                archive.addfile(info)
            else:
                raise AssertionError(kind)
    return path


def valid_protocol(tmp_path: Path) -> dict:
    final = tmp_path / "attempt01"
    staging = tmp_path / "attempt01.staging"
    return {
        "schema_version": runner.PROTOCOL_SCHEMA,
        "attempt": "attempt01",
        "result_blind": True,
        "direction": "DAADX_PREFLIGHT_FIRST_THEN_CANDIDATE_A_IF_STOP",
        "authorization": "DAADX_DOWNLOAD_AND_GROUP_INTEGRITY_PREFLIGHT_ONLY",
        "training_authorized": False,
        "repository": {"implementation_sha256": {}},
        "official_input": {
            "url": "https://cvit.iiit.ac.in/images/datasets/daadx/daadx.tar.gz",
            "expected_content_length_bytes": runner.EXPECTED_ARCHIVE_BYTES,
            "expected_unique_uuid_count": runner.EXPECTED_UUIDS,
            "expected_front_binding_count": runner.EXPECTED_UUIDS,
        },
        "group_split": {"split_name_normalization": {"val": "validation"}},
        "formal_output": {
            "staging": str(staging),
            "final": str(final),
            "log": str(tmp_path / "protocol-log-alias.log"),
            "artifact_index": str(tmp_path / "protocol-index-alias.json"),
            "required_artifacts": list(runner.REQUIRED_ARTIFACTS),
        },
    }


def valid_operational(tmp_path: Path) -> dict:
    return {
        "schema_version": "ARSC_ROUND11_DAADX_OPERATIONAL_CONTRACT_V1",
        "archive_layout": {
            "annotation_members": {
                "train": "annotations/train.csv",
                "val": "annotations/val.csv",
                "test": "annotations/test.csv",
            },
            "front_member_regex": r"front/(?P<uuid>[^/]+)\.mp4",
            "provenance_member": "metadata/provenance.csv",
            "provenance_allowed_classes": list(
                runner._PROVENANCE_REQUIREMENTS
            ),
            "uuid_column": "uuid",
        },
        "media_tools": {
            "ffmpeg": {"path": sys.executable, "sha256": sha256_file(sys.executable)},
            "ffprobe": {"path": sys.executable, "sha256": sha256_file(sys.executable)},
        },
        "archive_bounds": {
            "max_raw_headers": 100,
            "max_members": 100,
            "max_member_bytes": 1024 * 1024,
            "max_uncompressed_member_bytes": 4 * 1024 * 1024,
            "max_tar_stream_bytes": 16 * 1024 * 1024,
        },
        "scratch": {
            "root": str(tmp_path),
            "work_directory_name": "round11-test.restricted",
            "minimum_free_bytes": 1,
            "maximum_total_written_bytes": 4 * 1024 * 1024,
            "maximum_single_file_bytes": 1024 * 1024,
            "front_lifecycle": "EXTRACT_ONE_PROBE_REHASH_DELETE",
        },
        "label_worker": {
            "python_executable": sys.executable,
            "python_sha256": sha256_file(sys.executable),
            "isolation_flags": ["-I"],
            "timeout_seconds": 60,
            "environment_policy": "CLEAN_ALLOWLIST_NO_PYTHONPATH_NO_USER_SITE",
        },
        "artifact_topology": {
            "mode": "ATOMIC_FINAL_DIRECTORY_WITH_LOGICAL_READONLY_ALIASES",
            "external_alias_materialization": "FORBIDDEN_TO_PRESERVE_ATOMICITY",
            "internal_log_name": "round11_daadx_preflight.log",
            "internal_index_name": "round11_daadx_artifact_index.json",
        },
        "phase_policy": {
            "all_G0_G1_G2_G3_pass": "PREFLIGHT_PHASE1_DIAGNOSTIC_ONLY_NO_FORMAL_PUBLISH",
            "any_G0_G1_G2_fail": "FORMAL_STOP_WITH_CLOSED_ARTIFACTS",
            "G3_fail_after_G0_G1_G2_pass": "FORMAL_STOP_SHORT_CIRCUIT_G4_G7_INCONCLUSIVE",
        },
    }


def write_execution_review(
    tmp_path: Path,
    protocol_path: Path,
    operational: dict,
    **overrides,
) -> Path:
    review = {
        "schema_version": runner.EXECUTION_REVIEW_SCHEMA,
        "decision": runner.EXECUTION_GO,
        "reviewer_role": runner.EXECUTION_REVIEWER_ROLE,
        "protocol_path": runner._relative(protocol_path),
        "protocol_sha256": sha256_file(protocol_path),
        "runner_path": runner._relative(runner.RUNNER_PATH),
        "runner_sha256": sha256_file(runner.RUNNER_PATH),
        "runner_tests_path": runner._relative(runner.RUNNER_TEST_PATH),
        "runner_tests_sha256": sha256_file(runner.RUNNER_TEST_PATH),
        "core_path": runner._relative(runner.CORE_PATH),
        "core_sha256": sha256_file(runner.CORE_PATH),
        "operational_contract_sha256": canonical_json_sha256(operational),
        "training_authorized": False,
        "attempt": "attempt01",
    }
    review.update(overrides)
    path = tmp_path / "independent-execution-review.json"
    path.write_text(json.dumps(review), encoding="utf-8")
    return path


def valid_binding(
    protocol_path: Path,
    operational: dict,
    reviewer_path: Path,
) -> dict:
    return {
        "schema_version": runner.EXECUTION_BINDING_SCHEMA,
        "decision": runner.EXECUTION_GO,
        "protocol_path": runner._relative(protocol_path),
        "protocol_sha256": sha256_file(protocol_path),
        "runner_path": runner._relative(runner.RUNNER_PATH),
        "runner_sha256": sha256_file(runner.RUNNER_PATH),
        "runner_tests_path": runner._relative(runner.RUNNER_TEST_PATH),
        "runner_tests_sha256": sha256_file(runner.RUNNER_TEST_PATH),
        "core_path": runner._relative(runner.CORE_PATH),
        "core_sha256": sha256_file(runner.CORE_PATH),
        "reviewer_decision_path": runner._relative(reviewer_path),
        "reviewer_decision_sha256": sha256_file(reviewer_path),
        "operational_contract": operational,
        "operational_contract_sha256": canonical_json_sha256(operational),
        "training_authorized": False,
        "attempt": "attempt01",
    }


def _test_bounds() -> runner.ArchiveBounds:
    return runner.ArchiveBounds(100, 100, 1024 * 1024, 4 * 1024 * 1024, 16 * 1024 * 1024)


def test_archive_audit_hashes_every_regular_member_and_redacts_later(
    tmp_path: Path,
) -> None:
    canary = "SECRET_SESSION_TOKEN"
    archive = make_tar_gz(
        tmp_path / "valid.tar.gz",
        [
            ("daadx/", None, "directory"),
            (f"daadx/{canary}/front.mp4", b"video-bytes", "file"),
            ("annotations/train.csv", b"uuid,label\nu1,TOP_SECRET_LABEL\n", "file"),
        ],
    )
    audit = runner.audit_archive(archive, archive.stat().st_size, bounds=_test_bounds())
    assert audit.double_read_match and audit.gzip_integrity and audit.tar_integrity
    files = [member for member in audit.members if member.member_type == "regular_file"]
    assert len(files) == 2
    assert all(len(member.content_sha256 or "") == 64 for member in files)

    payloads = runner.build_attempt_payloads(
        protocol_bytes=b"{}\n",
        receipt={},
        archive_audit=audit,
        label_seal=None,
        binding_rows=[],
        probe_rows=[],
        provenance=None,
        gate_statuses={"G0": "PASS"},
        notes=["synthetic audit"],
    )
    public_bytes = b"".join(payloads.values())
    assert canary.encode() not in public_bytes
    assert b"TOP_SECRET_LABEL" not in public_bytes


@pytest.mark.parametrize(
    "members",
    [
        [("front/a.mp4", b"a", "file"), ("front/A.mp4", b"b", "file")],
        [("front/a.mp4:ads", b"a", "file")],
        [("front///", None, "directory")],
        [("front/link", None, "symlink")],
        [("../escape", b"a", "file")],
        [("front/CON.txt", b"a", "file")],
    ],
)
def test_archive_audit_rejects_case_path_type_and_platform_hazards(
    tmp_path: Path, members: list[tuple[str, bytes | None, str]]
) -> None:
    archive = make_tar_gz(tmp_path / "unsafe.tar.gz", members)
    with pytest.raises(runner.ArchiveSafetyError):
        runner.audit_archive(archive, archive.stat().st_size, bounds=_test_bounds())


def test_archive_audit_rejects_wrong_exact_byte_count(tmp_path: Path) -> None:
    archive = make_tar_gz(tmp_path / "small.tar.gz", [("a", b"x", "file")])
    with pytest.raises(runner.ArchiveSafetyError, match="bytes differ"):
        runner.audit_archive(
            archive, archive.stat().st_size + 1, bounds=_test_bounds()
        )


def test_archive_audit_enforces_stream_bounds_and_rejects_gnu_longname(
    tmp_path: Path,
) -> None:
    archive = make_tar_gz(
        tmp_path / "bounded.tar.gz", [("front/a.mp4", b"1234", "file")]
    )
    too_small = runner.ArchiveBounds(100, 100, 3, 100, 1024 * 1024)
    with pytest.raises(runner.ArchiveSafetyError, match="size bound"):
        runner.audit_archive(archive, archive.stat().st_size, bounds=too_small)

    gnu = tmp_path / "gnu-long.tar.gz"
    with tarfile.open(gnu, "w:gz", format=tarfile.GNU_FORMAT) as handle:
        info = tarfile.TarInfo("front/" + "x" * 140 + ".mp4")
        info.size = 1
        handle.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(runner.ArchiveSafetyError, match="typeflag"):
        runner.audit_archive(gnu, gnu.stat().st_size, bounds=_test_bounds())


def test_safe_extraction_uses_only_allowlist_and_hashed_names(tmp_path: Path) -> None:
    archive = make_tar_gz(
        tmp_path / "extract.tar.gz",
        [("front/u1.mp4", b"eligible", "file"), ("front/u2.mp4", b"not-selected", "file")],
    )
    audit = runner.audit_archive(archive, archive.stat().st_size, bounds=_test_bounds())
    destination = tmp_path / "restricted"
    outputs = runner.extract_selected_regular_members(
        archive, audit, ["front/u1.mp4"], destination
    )
    assert set(outputs) == {"front/u1.mp4"}
    assert outputs["front/u1.mp4"].read_bytes() == b"eligible"
    assert "u1" not in outputs["front/u1.mp4"].name
    assert len(list(destination.iterdir())) == 1
    with pytest.raises(FileExistsError):
        runner.extract_selected_regular_members(
            archive, audit, ["front/u1.mp4"], destination
        )


def test_front_binding_is_exact_and_never_substitutes(tmp_path: Path) -> None:
    archive = make_tar_gz(
        tmp_path / "binding.tar.gz",
        [
            ("front/u1.mp4", b"one", "file"),
            ("front/u2.mp4", b"two", "file"),
            ("front/u2-copy.mp4", b"duplicate", "file"),
        ],
    )
    audit = runner.audit_archive(archive, archive.stat().st_size, bounds=_test_bounds())
    passed, rows, internal = runner.build_front_bindings(
        (("u1", "train"), ("u2", "test"), ("u3", "val")),
        audit,
        r"front/(?P<uuid>u\d)(?:-copy)?\.mp4",
    )
    assert not passed
    assert [row["front_binding_status"] for row in rows] == ["PASS", "AMBIGUOUS", "MISSING"]
    assert internal == {"u1": "front/u1.mp4"}


def test_fronts_are_probed_one_at_a_time_rehashed_and_deleted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = make_tar_gz(
        tmp_path / "fronts.tar.gz",
        [("front/u1.mp4", b"one", "file"), ("front/u2.mp4", b"two", "file")],
    )
    audit = runner.audit_archive(
        archive, archive.stat().st_size, bounds=_test_bounds()
    )
    scratch_root = tmp_path / "scratch"
    scratch_root.mkdir()
    work = scratch_root / "eligible-front"
    observed_file_counts = []

    def fake_probe(video_path: Path, **kwargs):
        observed_file_counts.append(len(list(video_path.parent.iterdir())))
        return runner.MediaProbe("h264", 30.0, 1.0, 3, 3, 10, 10, True, "")

    monkeypatch.setattr(runner, "probe_and_full_decode", fake_probe)
    passed, rows = runner.probe_front_members_one_at_a_time(
        archive,
        audit,
        {"u1": "front/u1.mp4", "u2": "front/u2.mp4"},
        scratch=runner.ScratchContract(scratch_root, "unused", 1, 100, 100),
        work_directory=work,
        ffprobe_path=Path(sys.executable),
        ffmpeg_path=Path(sys.executable),
    )
    assert passed and len(rows) == 2
    assert observed_file_counts == [1, 1]
    assert list(work.iterdir()) == []


def test_front_scratch_oserror_maps_to_explicit_g2_failure_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = make_tar_gz(
        tmp_path / "front-io.tar.gz", [("front/u1.mp4", b"one", "file")]
    )
    audit = runner.audit_archive(
        archive, archive.stat().st_size, bounds=_test_bounds()
    )
    scratch_root = tmp_path / "scratch-io"
    scratch_root.mkdir()
    Usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr(runner.shutil, "disk_usage", lambda _: Usage(100, 100, 0))
    passed, rows = runner.probe_front_members_one_at_a_time(
        archive,
        audit,
        {"u1": "front/u1.mp4"},
        scratch=runner.ScratchContract(scratch_root, "unused", 1, 100, 100),
        work_directory=scratch_root / "work",
        ffprobe_path=Path(sys.executable),
        ffmpeg_path=Path(sys.executable),
    )
    assert not passed
    assert rows[0]["full_decode_pass"] is False
    assert rows[0]["error"] == "OSError"


def test_label_seal_worker_process_output_contains_no_canaries(tmp_path: Path) -> None:
    files = {}
    for split, uuid, canary in (
        ("train", "u1", "LABEL_CANARY_A"),
        ("val", "u2", "LABEL_CANARY_B"),
        ("test", "u3", "LABEL_CANARY_C"),
    ):
        path = tmp_path / f"{split}.csv"
        path.write_text(f"uuid,maneuver,rationale\n{uuid},{canary},{canary}\n", encoding="utf-8")
        files[split] = path
    result = runner.invoke_label_seal_worker(
        files,
        tmp_path,
        worker_contract=valid_operational(tmp_path)["label_worker"],
        expected_uuid_count=3,
    )
    serialized = json.dumps(result)
    assert result["unique_uuid_count"] == 3
    assert "LABEL_CANARY" not in serialized
    assert set(result) == {
        "schema_version",
        "parser_version",
        "source_sha256",
        "unique_uuid_count",
        "uuid_split_rows",
        "individual_labels_exposed",
    }


@pytest.mark.parametrize(
    ("field", "bad_value", "message"),
    [
        ("schema_version", "ARSC_WRONG_LABEL_SEAL_V1", "schema version"),
        ("parser_version", "ARSC_WRONG_PARSER_V1", "parser version"),
        ("source_sha256", {"train": "0" * 64}, "source SHA"),
    ],
)
def test_parent_rejects_worker_schema_parser_and_source_sha_counterexamples(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    bad_value,
    message: str,
) -> None:
    files: dict[str, Path] = {}
    for split, uuid in (("train", "u1"), ("val", "u2"), ("test", "u3")):
        path = tmp_path / f"{split}.csv"
        path.write_text(f"uuid,label\n{uuid},secret\n", encoding="utf-8")
        files[split] = path

    def fake_worker(command, **_kwargs):
        output = Path(command[command.index("--output") + 1])
        result = {
            "schema_version": "ARSC_ROUND11_DAADX_LABEL_SEAL_V1",
            "parser_version": "ARSC_DAADX_UUID_SPLIT_SEAL_V1",
            "source_sha256": {
                split: sha256_file(path) for split, path in files.items()
            },
            "unique_uuid_count": 3,
            "uuid_split_rows": [["u1", "train"], ["u2", "val"], ["u3", "test"]],
            "individual_labels_exposed": False,
        }
        result[field] = bad_value
        output.write_text(json.dumps(result), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_worker)
    with pytest.raises(runner.ContractError, match=message):
        runner.invoke_label_seal_worker(
            files,
            tmp_path,
            worker_contract=valid_operational(tmp_path)["label_worker"],
            expected_uuid_count=3,
        )


def test_g3_accepts_only_authoritative_or_complete_auditable_provenance() -> None:
    records = [
        {"uuid": "u1", "provenance_class": "AUTHORITATIVE_SESSION_ID", "session_id": "s1"},
        {
            "uuid": "u2",
            "provenance_class": "AUDITABLE_ACQUISITION_RIG_SESSION",
            "acquisition_timestamp": "2020-01-01T00:00:00Z",
            "camera_rig_signature": "rig",
            "multiview_sync_signature": "sync",
        },
        {"uuid": "u3", "provenance_class": "MULTIVIEW_SYNC_ONLY", "multiview_sync_signature": "sync"},
        {"uuid": "u4", "provenance_class": "AUDITABLE_ACQUISITION_RIG_SESSION", "multiview_sync_signature": "sync"},
    ]
    result = runner.assess_source_provenance({"u1", "u2", "u3", "u4", "u5"}, records)
    assert not result.passed
    assert result.accepted_count == 2
    assert result.missing_uuids == ("u5",)
    assert result.invalid_uuids == ("u3", "u4")
    public = json.dumps(result.public_rows)
    assert "s1" not in public
    assert "2020-01-01" not in public


def test_provenance_csv_rejects_any_unfrozen_label_column() -> None:
    with pytest.raises(runner.ContractError, match="label columns"):
        runner.parse_provenance_csv(
            b"uuid,provenance_class,maneuver\nu1,AUTHORITATIVE_SESSION_ID,Stop\n"
        )


@pytest.mark.parametrize(
    "header",
    [
        "uuid,provenance_class,uuid",
        "uuid,uuid,provenance_class",
        "uuid,session_id",
        "provenance_class,session_id",
        "uuid,provenance_class,Session_ID",
    ],
)
def test_provenance_csv_header_is_unique_and_exactly_allowlisted(
    header: str,
) -> None:
    with pytest.raises(runner.ContractError):
        runner.parse_provenance_csv(
            f"{header}\nu1,AUTHORITATIVE_SESSION_ID,s1\n".encode("utf-8")
        )


def test_provenance_csv_rejects_unterminated_quote() -> None:
    with pytest.raises(runner.ContractError, match="strict CSV"):
        runner.parse_provenance_csv(
            b'uuid,provenance_class,session_id\nu1,AUTHORITATIVE_SESSION_ID,"unterminated\n'
        )


def test_provenance_csv_rejects_rows_wider_than_header() -> None:
    with pytest.raises(runner.ContractError, match="width differs"):
        runner.parse_provenance_csv(
            b"uuid,provenance_class,session_id\nu1,AUTHORITATIVE_SESSION_ID,s1,unexpected\n"
        )


def test_probe_uses_explicit_tools_and_requires_equal_full_decode_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ffprobe = tmp_path / "ffprobe.exe"
    ffmpeg = tmp_path / "ffmpeg.exe"
    video = tmp_path / "video.mp4"
    for path in (ffprobe, ffmpeg, video):
        path.write_bytes(b"x")
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        if command[0] == str(ffprobe):
            output = json.dumps(
                {
                    "streams": [
                        {
                            "codec_name": "h264",
                            "avg_frame_rate": "30/1",
                            "duration": "1.0",
                            "nb_read_frames": "3",
                            "width": 1280,
                            "height": 720,
                        }
                    ],
                    "format": {"duration": "1.0"},
                }
            )
        else:
            output = "frame=1\nframe=3\nprogress=end\n"
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    result = runner.probe_and_full_decode(
        video, ffprobe_path=ffprobe.resolve(), ffmpeg_path=ffmpeg.resolve()
    )
    assert result.full_decode_pass and result.decoded_frame_count == 3
    assert commands[0][0] == str(ffprobe.resolve())
    assert commands[1][0] == str(ffmpeg.resolve())
    assert "-xerror" in commands[1] and "-threads" in commands[1]


def test_execution_authority_requires_exact_runner_binding(tmp_path: Path) -> None:
    protocol = valid_protocol(tmp_path)
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text(json.dumps(protocol), encoding="utf-8")
    with pytest.raises(runner.ContractError, match="binding is absent"):
        runner.validate_execution_authority(
            protocol_path, None, require_binding_in_head=False
        )
    operational = valid_operational(tmp_path)
    review_path = write_execution_review(tmp_path, protocol_path, operational)
    binding = valid_binding(protocol_path, operational, review_path)
    binding_path = tmp_path / "binding.json"
    binding_path.write_text(json.dumps(binding), encoding="utf-8")
    view = runner.validate_execution_authority(
        protocol_path, binding_path, require_binding_in_head=False
    )
    assert view.protocol["attempt"] == "attempt01"
    assert view.operational_contract == operational
    binding["runner_sha256"] = "0" * 64
    binding_path.write_text(json.dumps(binding), encoding="utf-8")
    with pytest.raises(runner.ContractError, match="mismatch"):
        runner.validate_execution_authority(
            protocol_path, binding_path, require_binding_in_head=False
        )


def test_not_run_draft_binding_is_never_execution_authority(tmp_path: Path) -> None:
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text(json.dumps(valid_protocol(tmp_path)), encoding="utf-8")
    operational = valid_operational(tmp_path)
    review_path = write_execution_review(tmp_path, protocol_path, operational)
    binding = valid_binding(protocol_path, operational, review_path)
    binding["decision"] = "NOT_RUN_DRAFT_ONLY"
    binding_path = tmp_path / "not-run.json"
    binding_path.write_text(json.dumps(binding), encoding="utf-8")
    with pytest.raises(runner.ContractError, match="decision"):
        runner.validate_execution_authority(
            protocol_path, binding_path, require_binding_in_head=False
        )


def test_authority_requires_core_and_independent_review_reciprocal_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text(json.dumps(valid_protocol(tmp_path)), encoding="utf-8")
    operational = valid_operational(tmp_path)
    review_path = write_execution_review(tmp_path, protocol_path, operational)
    binding = valid_binding(protocol_path, operational, review_path)
    binding_path = tmp_path / "binding.json"
    binding_path.write_text(json.dumps(binding), encoding="utf-8")

    checked: list[Path] = []
    monkeypatch.setattr(runner, "_require_head_exact", lambda path: checked.append(path))
    runner.validate_execution_authority(protocol_path, binding_path)
    assert runner.CORE_PATH in checked
    assert review_path in checked
    assert protocol_path in checked

    binding["core_sha256"] = "0" * 64
    binding_path.write_text(json.dumps(binding), encoding="utf-8")
    with pytest.raises(runner.ContractError, match="core_sha256"):
        runner.validate_execution_authority(
            protocol_path, binding_path, require_binding_in_head=False
        )


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("schema_version", "ARSC_ROUND11_IMPLEMENTATION_REVIEWER_DECISION_V1"),
        ("decision", "GO_FREEZE_PROTOCOL"),
        ("reviewer_role", "self_asserted_by_binding"),
        ("core_sha256", "0" * 64),
        ("operational_contract_sha256", "F" * 64),
    ],
)
def test_authority_rejects_non_go_or_nonreciprocal_reviewer_decision(
    tmp_path: Path, field: str, bad_value: str
) -> None:
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text(json.dumps(valid_protocol(tmp_path)), encoding="utf-8")
    operational = valid_operational(tmp_path)
    review_path = write_execution_review(
        tmp_path, protocol_path, operational, **{field: bad_value}
    )
    binding = valid_binding(protocol_path, operational, review_path)
    # A binding's self-declared role cannot rescue an invalid independent decision.
    binding["reviewer_role"] = runner.EXECUTION_REVIEWER_ROLE
    binding_path = tmp_path / "binding.json"
    binding_path.write_text(json.dumps(binding), encoding="utf-8")
    with pytest.raises(runner.ContractError, match="reviewer decision"):
        runner.validate_execution_authority(
            protocol_path, binding_path, require_binding_in_head=False
        )


def test_protocol_contract_fails_before_archive_when_layout_or_topology_missing(
    tmp_path: Path,
) -> None:
    protocol = valid_protocol(tmp_path)
    operational = valid_operational(tmp_path)
    view = runner.validate_protocol_contract(
        protocol, {"operational_contract": operational}
    )
    assert view.staging.name.endswith(".staging") and view.final.name == "attempt01"
    missing = valid_operational(tmp_path)
    del missing["archive_layout"]
    with pytest.raises(runner.ContractError, match="field set"):
        runner.validate_protocol_contract(
            protocol, {"operational_contract": missing}
        )
    override = valid_operational(tmp_path)
    override["duplicate_edges"] = {"broad": {"phash_each_max": 99}}
    with pytest.raises(runner.ContractError, match="field set"):
        runner.validate_protocol_contract(
            protocol, {"operational_contract": override}
        )


def test_real_frozen_protocol_accepts_additive_operational_topology(
    tmp_path: Path,
) -> None:
    protocol = json.loads(
        (ROOT / "outputs/validity/round11_daadx_preflight_protocol.json").read_text(
            encoding="utf-8"
        )
    )
    operational = valid_operational(tmp_path)
    view = runner.validate_protocol_contract(
        protocol, {"operational_contract": operational}
    )
    assert view.protocol["duplicate_edges"]["broad"]["phash_each_max"] == 10
    assert view.protocol["group_split"]["salt"] == "ARSC-DAADX-R11-GROUP-SPLIT-V1"
    assert view.logical_aliases == (
        (
            "outputs/validity/round11_daadx_preflight_attempt01.log",
            "outputs/validity/round11_daadx_preflight_attempt01/round11_daadx_preflight.log",
        ),
        (
            "outputs/validity/round11_daadx_artifact_index.json",
            "outputs/validity/round11_daadx_preflight_attempt01/round11_daadx_artifact_index.json",
        ),
    )


def test_g3_failure_cascades_to_inconclusive_and_publishes_closed_stop(
    tmp_path: Path,
) -> None:
    provenance = runner.ProvenanceAssessment(
        passed=False,
        eligible_count=2,
        accepted_count=1,
        missing_uuids=("u2",),
        invalid_uuids=(),
        public_rows=(),
    )
    payloads = runner.build_attempt_payloads(
        protocol_bytes=b"{}\n",
        receipt={"synthetic": True},
        archive_audit=None,
        label_seal={"individual_labels_exposed": False},
        binding_rows=[],
        probe_rows=[],
        provenance=provenance,
        gate_statuses={
            "G0": GateStatus.PASS,
            "G1": GateStatus.PASS,
            "G2": GateStatus.PASS,
            "G3": GateStatus.FAIL,
            "G4": GateStatus.INCONCLUSIVE,
            "G5": GateStatus.INCONCLUSIVE,
            "G6": GateStatus.INCONCLUSIVE,
            "G7": GateStatus.INCONCLUSIVE,
        },
        notes=["G3 failed; downstream gates remain inconclusive"],
    )
    staging, final = tmp_path / "attempt.staging", tmp_path / "attempt"
    runner.publish_attempt_atomically(staging, final, payloads)
    assert not staging.exists() and final.is_dir()
    assert runner.verify_artifact_closure(final)
    assert {path.name for path in final.iterdir()} == set(runner.REQUIRED_ARTIFACTS)
    results = json.loads(
        (final / "round11_daadx_preflight_results.json").read_text(encoding="utf-8")
    )
    assert results["verdict"] == STOP_VERDICT
    assert results["training_authorized"] is False
    assert results["gates"]["G8"] == "PENDING_EXTERNAL_CLOSURE"
    assert all(results["gates"][gate] == "INCONCLUSIVE" for gate in ("G4", "G5", "G6", "G7"))
    with pytest.raises(FileExistsError):
        runner.publish_attempt_atomically(staging, final, payloads)
    extra = final / "unexpected-directory"
    extra.mkdir()
    assert not runner.verify_artifact_closure(final)
    extra.rmdir()
    (final / "round11_daadx_download_receipt.json").write_text("tampered", encoding="utf-8")
    assert not runner.verify_artifact_closure(final)


@pytest.mark.parametrize(
    ("failure_stage", "expected"),
    [
        (
            "annotation_missing",
            {"G0": "PASS", "G1": "FAIL", "G2": "INCONCLUSIVE", "G3": "INCONCLUSIVE"},
        ),
        (
            "label_seal",
            {"G0": "PASS", "G1": "FAIL", "G2": "INCONCLUSIVE", "G3": "INCONCLUSIVE"},
        ),
        (
            "front_extract",
            {"G0": "PASS", "G1": "PASS", "G2": "FAIL", "G3": "PASS"},
        ),
        (
            "provenance_absent",
            {"G0": "PASS", "G1": "PASS", "G2": "PASS", "G3": "FAIL"},
        ),
        (
            "provenance_parse",
            {"G0": "PASS", "G1": "PASS", "G2": "PASS", "G3": "FAIL"},
        ),
        (
            "provenance_taxonomy",
            {"G0": "PASS", "G1": "PASS", "G2": "PASS", "G3": "FAIL"},
        ),
    ],
)
def test_formal_stage_failures_are_gate_local_and_still_close_16_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
    expected: dict[str, str],
) -> None:
    protocol = valid_protocol(tmp_path)
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text(json.dumps(protocol), encoding="utf-8")
    operational = valid_operational(tmp_path)
    view = runner.OperationalView(
        protocol=protocol,
        binding={},
        operational_contract=operational,
        staging=Path(protocol["formal_output"]["staging"]),
        final=Path(protocol["formal_output"]["final"]),
        logical_aliases=(),
        archive_bounds=_test_bounds(),
        scratch=runner.ScratchContract(
            tmp_path,
            operational["scratch"]["work_directory_name"],
            1,
            1024,
            1024,
        ),
    )
    audit = runner.ArchiveAudit(
        archive_bytes=1,
        sha256_read_1="A" * 64,
        sha256_read_2="A" * 64,
        double_read_match=True,
        gzip_integrity=True,
        tar_integrity=True,
        raw_header_count=0,
        member_count=0,
        uncompressed_member_bytes=0,
        tar_stream_bytes=1024,
        members=(),
    )
    monkeypatch.setattr(runner, "validate_execution_authority", lambda *_a, **_k: view)
    monkeypatch.setattr(runner, "_load_and_validate_receipt", lambda *_a, **_k: {})
    monkeypatch.setattr(runner, "_tool_from_operational", lambda *_a, **_k: Path(sys.executable))
    monkeypatch.setattr(runner, "audit_archive", lambda *_a, **_k: audit)
    monkeypatch.setattr(runner, "_check_scratch_selection", lambda *_a, **_k: None)

    def fake_extract(*_args, **_kwargs):
        if failure_stage == "annotation_missing":
            raise KeyError("annotations/train.csv")
        return {
            member: tmp_path / f"{split}.csv"
            for split, member in operational["archive_layout"]["annotation_members"].items()
        }

    def fake_seal(*_args, **_kwargs):
        if failure_stage == "label_seal":
            raise runner.ContractError("blind worker rejected seal")
        return {
            "schema_version": "ARSC_ROUND11_DAADX_LABEL_SEAL_V1",
            "parser_version": "ARSC_DAADX_UUID_SPLIT_SEAL_V1",
            "source_sha256": {},
            "unique_uuid_count": runner.EXPECTED_UUIDS,
            "uuid_split_rows": [["u1", "train"]],
            "individual_labels_exposed": False,
        }

    def fake_probe(*_args, **_kwargs):
        if failure_stage == "front_extract":
            raise KeyError("front/u1.mp4")
        return True, [{"uuid": "u1", "full_decode_pass": True}]

    def fake_provenance_read(*_args, **_kwargs):
        if failure_stage == "provenance_absent":
            raise KeyError("metadata/provenance.csv")
        if failure_stage == "provenance_taxonomy":
            return b"uuid,provenance_class\nu1,UNFROZEN_CLASS\n"
        return b"uuid,provenance_class,session_id\nu1,AUTHORITATIVE_SESSION_ID,s1\n"

    monkeypatch.setattr(runner, "extract_selected_regular_members", fake_extract)
    monkeypatch.setattr(runner, "invoke_label_seal_worker", fake_seal)
    monkeypatch.setattr(
        runner,
        "build_front_bindings",
        lambda *_a, **_k: (True, [], {"u1": "front/u1.mp4"}),
    )
    monkeypatch.setattr(runner, "probe_front_members_one_at_a_time", fake_probe)
    monkeypatch.setattr(runner, "read_regular_member_bytes", fake_provenance_read)
    if failure_stage == "provenance_parse":
        monkeypatch.setattr(
            runner,
            "parse_provenance_csv",
            lambda *_a, **_k: (_ for _ in ()).throw(csv.Error("bad csv")),
        )

    args = SimpleNamespace(
        protocol=protocol_path,
        execution_binding=None,
        download_receipt=tmp_path / "receipt.json",
        archive=tmp_path / "archive.tar.gz",
    )
    assert runner.run_formal(args) == 0
    final = Path(protocol["formal_output"]["final"])
    assert {path.name for path in final.iterdir()} == set(runner.REQUIRED_ARTIFACTS)
    results = json.loads(
        (final / "round11_daadx_preflight_results.json").read_text(encoding="utf-8")
    )
    assert {gate: results["gates"][gate] for gate in expected} == expected


def test_all_phase1_gates_pass_cannot_build_formal_stop_payload() -> None:
    with pytest.raises(runner.ContractError, match="cannot be published"):
        runner.build_attempt_payloads(
            protocol_bytes=b"{}",
            receipt={},
            archive_audit=None,
            label_seal=None,
            binding_rows=[],
            probe_rows=[],
            provenance=runner.ProvenanceAssessment(True, 1, 1, (), (), ()),
            gate_statuses={gate: "PASS" for gate in ("G0", "G1", "G2", "G3")},
            notes=["phase1 pass"],
        )


def test_log_rejects_exit_marker_injection() -> None:
    with pytest.raises(runner.ContractError, match="exit markers"):
        runner.build_attempt_payloads(
            protocol_bytes=b"{}",
            receipt={},
            archive_audit=None,
            label_seal=None,
            binding_rows=[],
            probe_rows=[],
            provenance=None,
            gate_statuses={},
            notes=["EXIT_CODE=0"],
        )


def test_runner_has_no_training_or_model_dependencies() -> None:
    source = runner.RUNNER_PATH.read_text(encoding="utf-8")
    for forbidden in ("import torch", "ultralytics", "load_checkpoint", "model_logits"):
        assert forbidden not in source
