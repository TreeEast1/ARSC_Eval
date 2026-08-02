"""Data-agnostic full parent orchestration for Round 11 layout inventory.

The caller supplies declared absolute input paths.  This module validates only
trusted cached bytes before the durable claim; receipt, manifest and archive
paths are first opened after the claim, in that order.  Real execution remains
forbidden until a separate HEAD-exact binding and reviewer GO exist.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Mapping

from . import round11_layout_control as control
from .round11_layout_inventory import DEFAULT_LIMITS
from .round11_layout_runner import WorkerRunObservation, run_layout_worker_supervised


MIB = 1_048_576
PARENT_LOG_SCHEMA = "ARSC_ROUND11_DAADX_LAYOUT_PARENT_LOG_V1"
PARENT_LOG_RESERVE = 1_024


class FormalRunnerInfrastructureError(RuntimeError):
    """The attempt cannot be represented as a publishable hash-closed result."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FormalRunnerInfrastructureError(message)


@dataclass(frozen=True)
class FormalRunInputs:
    claim_path: Path
    staging_path: Path
    final_path: Path
    receipt_path: Path
    manifest_path: Path
    archive_path: Path
    trusted_payloads: Mapping[str, bytes]
    expectations: control.ClosureExpectations
    receipt_schema: str
    manifest_schema: str
    python_executable: Path
    worker_path: Path
    timeout_seconds: float
    closure_reserve_seconds: float = 2.0
    random_token: str | None = None
    require_formal_windows: bool = True


@dataclass(frozen=True)
class FormalRunResult:
    outcome: str
    completeness: str
    failure_stage: str | None
    failure_code: str | None
    final_path: Path
    claim_path: Path
    supplied_bytes: int
    supplied_sha256: str | None


@dataclass(frozen=True)
class _AuthorityCopy:
    status: str
    valid: bool
    failure_code: str | None


def _canonical(value: object) -> bytes:
    return control.canonical_json_bytes(value)


def _validate_preclaim(inputs: FormalRunInputs) -> None:
    require(type(inputs) is FormalRunInputs, "formal input type differs")
    paths = (
        inputs.claim_path,
        inputs.staging_path,
        inputs.final_path,
        inputs.receipt_path,
        inputs.manifest_path,
        inputs.archive_path,
        inputs.python_executable,
        inputs.worker_path,
    )
    require(all(path.is_absolute() for path in paths), "formal path must be absolute")
    require(
        inputs.claim_path.parent
        == inputs.staging_path.parent
        == inputs.final_path.parent,
        "formal output parents differ",
    )
    control.validate_expectations(inputs.expectations)
    required_names = control.ARTIFACTS[:3]
    require(set(inputs.trusted_payloads) == set(required_names), "trusted payload set differs")
    for expectation in inputs.expectations.authorities[:3]:
        value = inputs.trusted_payloads[expectation.name]
        require(type(value) is bytes, f"trusted payload type differs: {expectation.name}")
        require(
            len(value) == expectation.bytes
            and control.sha256_bytes(value) == expectation.sha256,
            f"trusted payload binding differs: {expectation.name}",
        )
    require(
        isinstance(inputs.receipt_schema, str)
        and isinstance(inputs.manifest_schema, str)
        and re.fullmatch(r"[A-Z0-9_]{1,128}", inputs.receipt_schema) is not None
        and re.fullmatch(r"[A-Z0-9_]{1,128}", inputs.manifest_schema) is not None,
        "authority schema declaration differs",
    )
    require(
        type(inputs.timeout_seconds) in {int, float}
        and 0 < inputs.timeout_seconds <= DEFAULT_LIMITS.max_elapsed_seconds,
        "formal timeout differs",
    )
    require(
        type(inputs.closure_reserve_seconds) in {int, float}
        and 0 < inputs.closure_reserve_seconds < inputs.timeout_seconds,
        "closure reserve differs",
    )
    if inputs.random_token is not None:
        require(
            re.fullmatch(r"[0-9A-F]{64}", inputs.random_token) is not None,
            "random token differs",
        )


def _identity(metadata: os.stat_result) -> tuple[int, int, int]:
    return metadata.st_dev, metadata.st_ino, metadata.st_nlink


def _create_empty(path: Path) -> None:
    control._write_owned_file(path, b"", max_bytes=control.ARTIFACT_CAPS[path.name])


def _copy_authority(
    source: Path,
    destination: Path,
    expectation: control.AuthorityExpectation,
    schema: str,
    deadline: float,
) -> _AuthorityCopy:
    """Copy one authority after claim; identity failures remain nonpublishable."""

    if time.monotonic() >= deadline:
        _create_empty(destination)
        return _AuthorityCopy(
            "ABSENT_REPRESENTED_EMPTY", False, "AUTHORITY_TIMEOUT"
        )
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_BINARY", 0)
    )
    try:
        source_fd = os.open(source, flags)
    except OSError as error:
        try:
            metadata = os.lstat(source)
        except OSError:
            metadata = None
        if metadata is not None and (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_nlink != 1
        ):
            raise FormalRunnerInfrastructureError(
                "authority source path type differs"
            ) from error
        _create_empty(destination)
        return _AuthorityCopy("ABSENT_REPRESENTED_EMPTY", False, "AUTHORITY_OPEN_FAILURE")
    destination_fd: int | None = None
    count = 0
    digest = hashlib.sha256()
    timed_out = False
    read_failed = False
    try:
        before = os.fstat(source_fd)
        current = os.lstat(source)
        require(
            stat.S_ISREG(before.st_mode)
            and stat.S_ISREG(current.st_mode)
            and not source.is_symlink()
            and before.st_nlink == 1
            and _identity(before) == _identity(current),
            "authority source identity differs",
        )
        if before.st_size > control.ARTIFACT_CAPS[destination.name]:
            _create_empty(destination)
            return _AuthorityCopy(
                "ABSENT_REPRESENTED_EMPTY", False, "AUTHORITY_SIZE_MISMATCH"
            )
        destination_fd = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o600,
        )
        try:
            control._require_open_path_identity(destination_fd, destination, "authority copy")
            while True:
                if time.monotonic() >= deadline:
                    timed_out = True
                    break
                try:
                    block = os.read(source_fd, MIB)
                except OSError:
                    read_failed = True
                    break
                if not block:
                    break
                count += len(block)
                require(count <= control.ARTIFACT_CAPS[destination.name], "authority exceeds cap")
                digest.update(block)
                view = memoryview(block)
                offset = 0
                while offset < len(view):
                    if time.monotonic() >= deadline:
                        timed_out = True
                        break
                    written = os.write(destination_fd, view[offset:])
                    require(type(written) is int and written > 0, "authority copy write failed")
                    offset += written
                if timed_out:
                    # Only bytes actually written are evidence.  Recompute the
                    # partial destination below rather than trusting source hash.
                    break
            os.fsync(destination_fd)
            control._require_open_path_identity(destination_fd, destination, "authority copy")
        finally:
            os.close(destination_fd)
            destination_fd = None
        after = os.fstat(source_fd)
        current_after = os.lstat(source)
        require(
            _identity(before) == _identity(after) == _identity(current_after)
            and (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            == (after.st_size, after.st_mtime_ns, after.st_ctime_ns),
            "authority source changed during copy",
        )
    finally:
        if destination_fd is not None:
            os.close(destination_fd)
        os.close(source_fd)

    observed = control.digest_regular_stable(
        destination, max_bytes=control.ARTIFACT_CAPS[destination.name]
    )
    if observed.bytes == 0:
        status = "ABSENT_REPRESENTED_EMPTY"
    elif observed == control.FileDigest(expectation.bytes, expectation.sha256):
        status = "OBSERVED_COMPLETE"
    else:
        status = "OBSERVED_PARTIAL"
    if timed_out:
        return _AuthorityCopy(status, False, "AUTHORITY_TIMEOUT")
    if read_failed:
        return _AuthorityCopy(status, False, "AUTHORITY_READ_FAILURE")
    if status != "OBSERVED_COMPLETE":
        return _AuthorityCopy(status, False, "AUTHORITY_DIGEST_MISMATCH")
    try:
        value = control.strict_canonical_json(
            control.read_small_regular_stable(
                destination, max_bytes=control.ARTIFACT_CAPS[destination.name]
            ),
            "authority",
        )
    except (OSError, control.LayoutControlError, UnicodeError, ValueError, TypeError):
        return _AuthorityCopy(status, False, "AUTHORITY_CANONICAL_FAILURE")
    if value.get("schema_version") != schema:
        return _AuthorityCopy(status, False, "AUTHORITY_SCHEMA_FAILURE")
    return _AuthorityCopy(status, True, None)


class _StableArchiveReader:
    def __init__(self, path: Path, expected_bytes: int, identity_failure: list[BaseException]) -> None:
        self.path = path
        self.expected_bytes = expected_bytes
        self.identity_failure = identity_failure
        flags = (
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_BINARY", 0)
        )
        try:
            self.fd = os.open(path, flags)
        except OSError as error:
            try:
                metadata = os.lstat(path)
            except OSError:
                metadata = None
            if metadata is not None and (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_ISLNK(metadata.st_mode)
                or metadata.st_nlink != 1
            ):
                identity_failure.append(error)
            raise
        try:
            self.before = os.fstat(self.fd)
            current = os.lstat(path)
            require(
                stat.S_ISREG(self.before.st_mode)
                and stat.S_ISREG(current.st_mode)
                and not path.is_symlink()
                and self.before.st_nlink == 1
                and _identity(self.before) == _identity(current),
                "archive source identity differs",
            )
            if self.before.st_size != expected_bytes:
                raise OSError("archive declared size differs")
        except BaseException as error:
            os.close(self.fd)
            self.fd = -1
            if isinstance(error, FormalRunnerInfrastructureError):
                identity_failure.append(error)
            raise

    def read(self, size: int = -1) -> bytes:
        require(self.fd >= 0 and 0 < size <= MIB, "archive read size differs")
        return os.read(self.fd, size)

    def close(self) -> None:
        if self.fd < 0:
            return
        try:
            after = os.fstat(self.fd)
            current = os.lstat(self.path)
            require(
                _identity(self.before) == _identity(after) == _identity(current)
                and (self.before.st_size, self.before.st_mtime_ns, self.before.st_ctime_ns)
                == (after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                "archive source changed during feed",
            )
        except BaseException as error:
            self.identity_failure.append(error)
            raise
        finally:
            os.close(self.fd)
            self.fd = -1

    def __enter__(self) -> _StableArchiveReader:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()


def _ensure_empty_inventory(staging: Path) -> None:
    control._write_owned_file(
        staging / control.PUBLIC_NAME,
        control.PUBLIC_HEADER,
        max_bytes=control.ARTIFACT_CAPS[control.PUBLIC_NAME],
    )
    _create_empty(staging / control.RESTRICTED_NAME)


def _parent_log_line(outcome: str, failure_code: str | None) -> bytes:
    return _canonical(
        {
            "event": "PARENT_COMPLETE" if outcome == control.COMPLETE_OUTCOME else "PARENT_STOP",
            "failure_code": failure_code,
            "schema_version": PARENT_LOG_SCHEMA,
        }
    )


def _finish_log(staging: Path, outcome: str, failure_code: str | None, existed: bool) -> None:
    path = staging / control.LOG_NAME
    line = _parent_log_line(outcome, failure_code)
    require(len(line) <= PARENT_LOG_RESERVE, "parent log reserve exceeded")
    if not existed:
        control._write_owned_file(path, line, max_bytes=control.ARTIFACT_CAPS[path.name])
        return
    flags = (
        os.O_WRONLY
        | os.O_APPEND
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_BINARY", 0)
    )
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        control._require_open_path_identity(descriptor, path, "parent log")
        require(before.st_size + len(line) <= control.ARTIFACT_CAPS[path.name], "parent log cap exceeded")
        offset = 0
        while offset < len(line):
            written = os.write(descriptor, line[offset:])
            require(type(written) is int and written > 0, "parent log append failed")
            offset += written
        os.fsync(descriptor)
        control._require_open_path_identity(descriptor, path, "parent log")
    finally:
        os.close(descriptor)


def _archive_hashes(
    expected: control.ArchiveExpectation, observation: WorkerRunObservation | None
) -> tuple[dict[str, object], str]:
    if observation is None or observation.supplied_bytes == 0:
        scope = "NONE"
        observed_bytes = 0
        observed_sha = None
        matches = False
    elif observation.supplied_bytes < expected.bytes:
        scope = "SUPPLIED_PREFIX"
        observed_bytes = observation.supplied_bytes
        observed_sha = observation.supplied_sha256
        matches = False
    else:
        require(observation.supplied_bytes == expected.bytes, "supplied archive exceeds expectation")
        scope = "COMPLETE_STREAM"
        observed_bytes = observation.supplied_bytes
        observed_sha = observation.supplied_sha256
        matches = observed_sha == expected.sha256
    return (
        {
            "schema_version": control.ARCHIVE_HASHES_SCHEMA,
            "phase": control.PHASE,
            "attempt": control.ATTEMPT,
            "expected_bytes": expected.bytes,
            "expected_sha256": expected.sha256,
            "observed_scope": scope,
            "observed_bytes": observed_bytes,
            "observed_sha256": observed_sha,
            "complete_stream_matches_expected": matches,
        },
        scope,
    )


def run_formal_layout_attempt(inputs: FormalRunInputs) -> FormalRunResult:
    """Execute one already-authorized attempt; this API itself grants no run authority."""

    _validate_preclaim(inputs)
    binding = inputs.expectations.authorities[1]
    token = inputs.random_token or secrets.token_hex(32).upper()
    acquisition = control.acquire_persistent_claim(
        inputs.claim_path,
        binding_sha256=binding.sha256,
        random_token=token,
    )
    lease = acquisition.lease
    deadline = time.monotonic() + float(inputs.timeout_seconds)
    observation: WorkerRunObservation | None = None
    archive_identity_failure: list[BaseException] = []
    failure_stage: str | None = None
    failure_code: str | None = None
    receipt_copy = _AuthorityCopy("ABSENT_REPRESENTED_EMPTY", False, None)
    manifest_copy = _AuthorityCopy("ABSENT_REPRESENTED_EMPTY", False, None)
    try:
        control.create_exclusive_staging(
            lease, inputs.staging_path, inputs.final_path
        )
        for name in control.ARTIFACTS[:3]:
            control._write_owned_file(
                inputs.staging_path / name,
                inputs.trusted_payloads[name],
                max_bytes=control.ARTIFACT_CAPS[name],
            )

        receipt_copy = _copy_authority(
            inputs.receipt_path,
            inputs.staging_path / control.ARTIFACTS[3],
            inputs.expectations.authorities[3],
            inputs.receipt_schema,
            deadline,
        )
        if not receipt_copy.valid:
            failure_stage = "RECEIPT"
            failure_code = receipt_copy.failure_code
            _create_empty(inputs.staging_path / control.ARTIFACTS[4])
        else:
            manifest_copy = _copy_authority(
                inputs.manifest_path,
                inputs.staging_path / control.ARTIFACTS[4],
                inputs.expectations.authorities[4],
                inputs.manifest_schema,
                deadline,
            )
            if not manifest_copy.valid:
                failure_stage = "MANIFEST"
                failure_code = manifest_copy.failure_code

        if failure_code is None:
            remaining = deadline - time.monotonic()
            worker_budget = remaining - float(inputs.closure_reserve_seconds)
            if worker_budget <= 0:
                failure_stage = "DEADLINE"
                failure_code = "PRE_WORKER_TIMEOUT"
            else:
                def open_archive() -> BinaryIO:
                    return _StableArchiveReader(
                        inputs.archive_path,
                        inputs.expectations.archive.bytes,
                        archive_identity_failure,
                    )

                observation = run_layout_worker_supervised(
                    open_archive,
                    expected_bytes=inputs.expectations.archive.bytes,
                    expected_sha256=inputs.expectations.archive.sha256,
                    cwd=inputs.staging_path,
                    log_path=inputs.staging_path / control.LOG_NAME,
                    python_executable=inputs.python_executable,
                    worker_path=inputs.worker_path,
                    timeout_seconds=worker_budget,
                    max_log_bytes=control.ARTIFACT_CAPS[control.LOG_NAME]
                    - PARENT_LOG_RESERVE,
                    require_formal_windows=inputs.require_formal_windows,
                )
                if archive_identity_failure:
                    raise FormalRunnerInfrastructureError(
                        "archive source identity failed"
                    ) from archive_identity_failure[0]
                if (
                    observation.supplied_bytes == inputs.expectations.archive.bytes
                    and observation.supplied_sha256 != inputs.expectations.archive.sha256
                ):
                    failure_stage = "ARCHIVE"
                    failure_code = "ARCHIVE_DIGEST_MISMATCH"
                elif not observation.complete:
                    worker_failure = observation.failure_code or "WORKER_FAILURE"
                    failure_stage = (
                        "ARCHIVE"
                        if worker_failure
                        in {"ARCHIVE_OPEN_FAILURE", "ARCHIVE_FEED_FAILURE"}
                        else "WORKER"
                    )
                    failure_code = worker_failure

        if failure_code is None and time.monotonic() >= deadline:
            failure_stage = "DEADLINE"
            failure_code = "POST_WORKER_TIMEOUT"

        if observation is None:
            _ensure_empty_inventory(inputs.staging_path)
        inventory_status = (
            "OBSERVED_COMPLETE"
            if observation is not None and observation.complete
            else "OBSERVED_PARTIAL"
            if observation is not None and observation.ready
            else "ABSENT_REPRESENTED_EMPTY"
        )
        if observation is not None and not observation.ready:
            public = inputs.staging_path / control.PUBLIC_NAME
            restricted = inputs.staging_path / control.RESTRICTED_NAME
            if public.exists() or restricted.exists():
                raise FormalRunnerInfrastructureError(
                    "worker left unclosed pre-READY inventory residue"
                )
            _ensure_empty_inventory(inputs.staging_path)

        inventory = control.validate_inventory_pair(
            inputs.staging_path / control.PUBLIC_NAME,
            inputs.staging_path / control.RESTRICTED_NAME,
            public_status=inventory_status,
            restricted_status=inventory_status,
        )
        complete = failure_code is None and observation is not None and observation.complete
        outcome = control.COMPLETE_OUTCOME if complete else control.STOP_OUTCOME
        if not complete and failure_code is None:
            failure_stage = "PARENT"
            failure_code = "INCOMPLETE_WITHOUT_CAUSE"

        archive_hashes, observed_scope = _archive_hashes(
            inputs.expectations.archive, observation
        )
        control._write_owned_file(
            inputs.staging_path / control.ARTIFACTS[5],
            _canonical(archive_hashes),
            max_bytes=control.ARTIFACT_CAPS[control.ARTIFACTS[5]],
        )
        if complete:
            assert observation is not None and observation.terminal is not None
            worker_summary = observation.terminal["summary"]
            summary_metrics = {
                name: worker_summary[name]
                for name in control._SUMMARY_METRICS
            }
        else:
            summary_metrics = {name: None for name in control._SUMMARY_METRICS}
        summary = {
            "schema_version": control.SUMMARY_SCHEMA,
            "phase": control.PHASE,
            "attempt": control.ATTEMPT,
            "status": "COMPLETE" if complete else "INCONCLUSIVE",
            "public_rows_observed": inventory.public_complete_rows,
            "restricted_rows_observed": inventory.restricted_complete_rows,
            **summary_metrics,
        }
        control._write_owned_file(
            inputs.staging_path / control.ARTIFACTS[6],
            _canonical(summary),
            max_bytes=control.ARTIFACT_CAPS[control.ARTIFACTS[6]],
        )

        statuses = {name: "OBSERVED_COMPLETE" for name in control.PAYLOAD_NAMES}
        statuses[control.ARTIFACTS[3]] = receipt_copy.status
        statuses[control.ARTIFACTS[4]] = manifest_copy.status
        statuses[control.PUBLIC_NAME] = inventory_status
        statuses[control.RESTRICTED_NAME] = inventory_status
        results = {
            "schema_version": control.RESULTS_SCHEMA,
            "phase": control.PHASE,
            "attempt": control.ATTEMPT,
            "outcome": outcome,
            "completeness": control.COMPLETE_CLOSURE if complete else control.STOP_CLOSURE,
            "layout_complete": complete,
            "observed_scope": observed_scope,
            "first_failure_stage": None if complete else failure_stage,
            "first_failure_code": None if complete else failure_code,
            "artifact_status": statuses,
            "is_phase1_or_g0_g8_verdict": False,
            "external_validity_established": False,
            "training_authorized": False,
        }
        control._write_owned_file(
            inputs.staging_path / control.RESULTS_NAME,
            _canonical(results),
            max_bytes=control.ARTIFACT_CAPS[control.RESULTS_NAME],
        )
        _finish_log(
            inputs.staging_path,
            outcome,
            failure_code,
            existed=observation is not None,
        )
        def rename_before_deadline(source: Path, target: Path) -> None:
            if time.monotonic() >= deadline:
                raise FormalRunnerInfrastructureError(
                    "attempt deadline expired before atomic publication"
                )
            control.rename_directory_no_replace(source, target)

        control.finalize_and_publish(
            lease,
            inputs.staging_path,
            inputs.final_path,
            expectations=inputs.expectations,
            rename_func=rename_before_deadline,
        )
        finished_at = time.monotonic()
        if finished_at >= deadline:
            raise FormalRunnerInfrastructureError(
                "attempt deadline expired before formal completion"
            )
        return FormalRunResult(
            outcome,
            control.COMPLETE_CLOSURE if complete else control.STOP_CLOSURE,
            failure_stage,
            failure_code,
            inputs.final_path,
            inputs.claim_path,
            0 if observation is None else observation.supplied_bytes,
            None if observation is None else observation.supplied_sha256,
        )
    finally:
        lease.close()
