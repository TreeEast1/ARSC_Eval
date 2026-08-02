from __future__ import annotations

import hashlib
import json
import os
import struct
import sys
import time
import zlib
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from arsc_eval import round11_layout_control as control  # noqa: E402
from arsc_eval import round11_layout_formal_runner as formal  # noqa: E402

PYTHON = Path(sys.executable).resolve()
WORKER = (ROOT / "src/arsc_eval/round11_layout_worker.py").resolve()
RECEIPT_SCHEMA = "SYNTHETIC_RECEIPT_V1"
MANIFEST_SCHEMA = "SYNTHETIC_MANIFEST_V1"


def _octal(value: int, width: int) -> bytes:
    digits = f"{value:o}".encode("ascii")
    return b"0" * (width - 1 - len(digits)) + digits + b"\x00"


def _archive(payload: bytes = b"abc") -> bytes:
    header = bytearray(512)
    path = b"safe/file.bin"
    header[: len(path)] = path
    header[100:108] = _octal(0o644, 8)
    header[108:116] = _octal(0, 8)
    header[116:124] = _octal(0, 8)
    header[124:136] = _octal(len(payload), 12)
    header[136:148] = _octal(0, 12)
    header[148:156] = b" " * 8
    header[156:157] = b"0"
    header[257:263] = b"ustar\x00"
    header[263:265] = b"00"
    header[329:337] = _octal(0, 8)
    header[337:345] = _octal(0, 8)
    header[148:156] = f"{sum(header):06o}".encode("ascii") + b"\x00 "
    raw = bytes(header) + payload + b"\x00" * ((-len(payload)) % 512) + b"\x00" * 1024
    compressor = zlib.compressobj(level=6, wbits=-zlib.MAX_WBITS)
    return (
        b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff"
        + compressor.compress(raw)
        + compressor.flush()
        + struct.pack("<II", zlib.crc32(raw), len(raw) & 0xFFFFFFFF)
    )


def _payload(schema: str, value: str) -> bytes:
    return control.canonical_json_bytes({"schema_version": schema, "value": value})


def _setup(
    tmp_path: Path,
    *,
    archive: bytes | None = None,
    receipt_source: bytes | None = None,
    manifest_source: bytes | None = None,
) -> formal.FormalRunInputs:
    root = (tmp_path / "formal").resolve()
    root.mkdir(parents=True)
    archive_bytes = _archive() if archive is None else archive
    trusted = {
        control.ARTIFACTS[0]: _payload("SYNTHETIC_PROTOCOL_V1", "protocol"),
        control.ARTIFACTS[1]: _payload("SYNTHETIC_BINDING_V1", "binding"),
        control.ARTIFACTS[2]: _payload("SYNTHETIC_REVIEWER_V1", "reviewer"),
    }
    receipt_expected = _payload(RECEIPT_SCHEMA, "receipt")
    manifest_expected = _payload(MANIFEST_SCHEMA, "manifest")
    authorities = []
    all_values = {
        **trusted,
        control.ARTIFACTS[3]: receipt_expected,
        control.ARTIFACTS[4]: manifest_expected,
    }
    for index, name in enumerate(control.ARTIFACTS[:5]):
        value = all_values[name]
        authorities.append(
            control.AuthorityExpectation(
                name,
                len(value),
                control.sha256_bytes(value),
                index < 3,
            )
        )
    receipt_path = root / "receipt.source.json"
    manifest_path = root / "manifest.source.json"
    archive_path = root / "archive.source.tar.gz"
    receipt_path.write_bytes(receipt_expected if receipt_source is None else receipt_source)
    manifest_path.write_bytes(manifest_expected if manifest_source is None else manifest_source)
    archive_path.write_bytes(archive_bytes)
    return formal.FormalRunInputs(
        claim_path=root / "attempt.claim",
        staging_path=root / "attempt.staging",
        final_path=root / "attempt.final",
        receipt_path=receipt_path,
        manifest_path=manifest_path,
        archive_path=archive_path,
        trusted_payloads=trusted,
        expectations=control.ClosureExpectations(
            tuple(authorities),
            control.ArchiveExpectation(
                len(archive_bytes), control.sha256_bytes(archive_bytes)
            ),
        ),
        receipt_schema=RECEIPT_SCHEMA,
        manifest_schema=MANIFEST_SCHEMA,
        python_executable=PYTHON,
        worker_path=WORKER,
        timeout_seconds=10,
        random_token="D" * 64,
        require_formal_windows=os.name == "nt",
    )


def _read(final: Path, name: str) -> dict:
    return json.loads((final / name).read_text(encoding="utf-8"))


def test_complete_attempt_publishes_exact_hash_closed_directory(tmp_path: Path) -> None:
    inputs = _setup(tmp_path)
    result = formal.run_formal_layout_attempt(inputs)
    assert result.outcome == control.COMPLETE_OUTCOME
    assert result.completeness == control.COMPLETE_CLOSURE
    assert inputs.claim_path.is_file() and inputs.final_path.is_dir()
    assert not inputs.staging_path.exists()
    assert {item.name for item in inputs.final_path.iterdir()} == set(control.ARTIFACTS)
    results = _read(inputs.final_path, control.RESULTS_NAME)
    assert results["layout_complete"] is True
    assert results["observed_scope"] == "COMPLETE_STREAM"
    summary = _read(inputs.final_path, control.ARTIFACTS[6])
    assert summary["logical_member_count"] == 1
    assert summary["total_regular_payload_bytes"] == 3


def test_receipt_failure_skips_manifest_and_archive(tmp_path: Path) -> None:
    inputs = _setup(tmp_path, receipt_source=b"wrong\n")
    inputs.manifest_path.unlink()
    inputs.archive_path.unlink()
    result = formal.run_formal_layout_attempt(inputs)
    assert result.outcome == control.STOP_OUTCOME
    assert result.failure_stage == "RECEIPT"
    assert (inputs.final_path / control.ARTIFACTS[4]).read_bytes() == b""
    hashes = _read(inputs.final_path, control.ARTIFACTS[5])
    assert hashes["observed_scope"] == "NONE"


def test_manifest_failure_skips_archive(tmp_path: Path) -> None:
    inputs = _setup(tmp_path, manifest_source=b"wrong\n")
    inputs.archive_path.unlink()
    result = formal.run_formal_layout_attempt(inputs)
    assert result.outcome == control.STOP_OUTCOME
    assert result.failure_stage == "MANIFEST"
    assert _read(inputs.final_path, control.ARTIFACTS[5])["observed_scope"] == "NONE"


def test_parser_failure_is_hash_closed_stop(tmp_path: Path) -> None:
    data = b"not-a-gzip-stream"
    inputs = _setup(tmp_path, archive=data)
    result = formal.run_formal_layout_attempt(inputs)
    assert result.outcome == control.STOP_OUTCOME
    assert result.failure_stage == "WORKER"
    assert result.failure_code == "PARSER_REJECTED"
    hashes = _read(inputs.final_path, control.ARTIFACTS[5])
    assert hashes["observed_scope"] == "COMPLETE_STREAM"
    assert hashes["observed_sha256"] == control.sha256_bytes(data)


def test_archive_open_failure_is_none_scope(tmp_path: Path) -> None:
    inputs = _setup(tmp_path)
    inputs.archive_path.unlink()
    result = formal.run_formal_layout_attempt(inputs)
    assert result.failure_code == "ARCHIVE_OPEN_FAILURE"
    hashes = _read(inputs.final_path, control.ARTIFACTS[5])
    assert hashes["observed_scope"] == "NONE"
    assert hashes["observed_bytes"] == 0 and hashes["observed_sha256"] is None


def test_complete_scan_with_wrong_expected_hash_is_archive_stop(tmp_path: Path) -> None:
    inputs = _setup(tmp_path)
    inputs = replace(
        inputs,
        expectations=control.ClosureExpectations(
            inputs.expectations.authorities,
            control.ArchiveExpectation(inputs.expectations.archive.bytes, "E" * 64),
        ),
    )
    result = formal.run_formal_layout_attempt(inputs)
    assert result.failure_stage == "ARCHIVE"
    assert result.failure_code == "ARCHIVE_DIGEST_MISMATCH"
    hashes = _read(inputs.final_path, control.ARTIFACTS[5])
    assert hashes["observed_scope"] == "COMPLETE_STREAM"
    assert hashes["complete_stream_matches_expected"] is False


def test_early_parser_rejection_records_real_supplied_prefix(tmp_path: Path) -> None:
    raw = b"X" * (8 * 1024 * 1024)
    compressor = zlib.compressobj(level=0, wbits=-zlib.MAX_WBITS)
    data = (
        b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff"
        + compressor.compress(raw)
        + compressor.flush()
        + struct.pack("<II", zlib.crc32(raw), len(raw) & 0xFFFFFFFF)
    )
    inputs = _setup(tmp_path, archive=data)
    result = formal.run_formal_layout_attempt(inputs)
    assert result.outcome == control.STOP_OUTCOME
    assert 0 < result.supplied_bytes < len(data)
    hashes = _read(inputs.final_path, control.ARTIFACTS[5])
    assert hashes["observed_scope"] == "SUPPLIED_PREFIX"
    assert hashes["observed_sha256"] == control.sha256_bytes(
        data[: result.supplied_bytes]
    )


def test_finalize_failure_preserves_claim_and_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _setup(tmp_path)

    def fail(*args, **kwargs):
        raise OSError("synthetic finalize failure")

    monkeypatch.setattr(formal.control, "finalize_and_publish", fail)
    with pytest.raises(OSError, match="finalize"):
        formal.run_formal_layout_attempt(inputs)
    assert inputs.claim_path.is_file() and inputs.staging_path.is_dir()
    assert not inputs.final_path.exists()


def test_post_publish_verification_crossing_deadline_is_not_returned_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = replace(
        _setup(tmp_path), timeout_seconds=1.0, closure_reserve_seconds=0.1
    )
    original_finalize = formal.control.finalize_and_publish
    published = False

    def finalize(*args, **kwargs):
        nonlocal published
        result = original_finalize(*args, **kwargs)
        published = True
        return result

    def monotonic() -> float:
        return 102.0 if published else 100.0

    monkeypatch.setattr(formal.control, "finalize_and_publish", finalize)
    monkeypatch.setattr(formal, "time", SimpleNamespace(monotonic=monotonic))
    with pytest.raises(
        formal.FormalRunnerInfrastructureError,
        match="deadline expired before formal completion",
    ):
        formal.run_formal_layout_attempt(inputs)
    assert inputs.claim_path.is_file() and inputs.final_path.is_dir()
    assert not inputs.staging_path.exists()


def test_existing_claim_prevents_second_attempt_before_input_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _setup(tmp_path)
    formal.run_formal_layout_attempt(inputs)
    touched = []
    original_open = formal.os.open

    def track(path, *args, **kwargs):
        if Path(path) in {inputs.receipt_path, inputs.manifest_path, inputs.archive_path}:
            touched.append(Path(path))
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(formal.os, "open", track)
    with pytest.raises(FileExistsError):
        formal.run_formal_layout_attempt(inputs)
    assert touched == []


def test_authority_symlink_is_nonpublishable(tmp_path: Path) -> None:
    inputs = _setup(tmp_path)
    target = inputs.receipt_path.with_suffix(".target")
    inputs.receipt_path.replace(target)
    try:
        inputs.receipt_path.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink unavailable")
    with pytest.raises(formal.FormalRunnerInfrastructureError, match="path type"):
        formal.run_formal_layout_attempt(inputs)
    assert inputs.claim_path.is_file() and inputs.staging_path.is_dir()
    assert not inputs.final_path.exists()


@pytest.mark.parametrize("which", ["receipt", "archive"])
def test_hardlinked_input_is_nonpublishable(tmp_path: Path, which: str) -> None:
    inputs = _setup(tmp_path)
    path = inputs.receipt_path if which == "receipt" else inputs.archive_path
    os.link(path, path.with_suffix(path.suffix + ".hardlink"))
    with pytest.raises(formal.FormalRunnerInfrastructureError):
        formal.run_formal_layout_attempt(inputs)
    assert inputs.claim_path.is_file() and inputs.staging_path.is_dir()
    assert not inputs.final_path.exists()


def test_oversized_authority_is_publishable_stop_without_overcap_copy(
    tmp_path: Path,
) -> None:
    inputs = _setup(tmp_path)
    inputs.receipt_path.write_bytes(
        b"x" * (control.ARTIFACT_CAPS[control.ARTIFACTS[3]] + 1)
    )
    result = formal.run_formal_layout_attempt(inputs)
    assert result.failure_stage == "RECEIPT"
    assert result.failure_code == "AUTHORITY_SIZE_MISMATCH"
    assert (inputs.final_path / control.ARTIFACTS[3]).read_bytes() == b""


def test_expired_authority_deadline_creates_empty_without_source_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _setup(tmp_path)
    destination = (inputs.claim_path.parent / control.ARTIFACTS[3]).resolve()
    touched = []
    original_open = formal.os.open

    def track(path, *args, **kwargs):
        if Path(path) == inputs.receipt_path:
            touched.append(True)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(formal.os, "open", track)
    result = formal._copy_authority(
        inputs.receipt_path,
        destination,
        inputs.expectations.authorities[3],
        RECEIPT_SCHEMA,
        time.monotonic() - 1,
    )
    assert result.failure_code == "AUTHORITY_TIMEOUT"
    assert destination.read_bytes() == b"" and touched == []
