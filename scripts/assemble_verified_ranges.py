"""Generic transport-only chunk concatenation and verification tool.

Given a directory of equal-sized byte-range files named
``chunk_{NNN}.resilient.bin`` together with an ``expected_total`` and
``chunk_bytes``, this tool verifies that the file set is exactly the
partition of ``[0, expected_total)`` into ``chunk_bytes``-sized pieces,
concatenates them in index order into an output file, and publishes a
deterministic JSON manifest.

Properties enforced here:

* Chunk ranges are derived only from ``expected_total`` / ``chunk_bytes``.
* Only exactly-named ``chunk_{index:03d}.resilient.bin`` files are accepted;
  other digit-width variants are treated as extra chunks and rejected.
* Missing chunks, extra same-pattern chunks, wrong chunk sizes, and any chunk
  entry that is a symlink are errors.
* The assembled byte count must equal ``expected_total``.
* Every chunk is stream-hashed once while scanning and re-hashed again while
  appending, so a chunk edited between scan and assembly is rejected.
* Source chunks are never modified; all writes go to temporary files that are
  published with ``os.replace`` and cleaned up on failure.
* After the output is published it is re-streamed to verify size and SHA-256.
* Overwriting an existing output or manifest is refused unless ``--force`` is
  given. Output and manifest must not be symlinks (any symlink is rejected).
  Publishing and post-verification run in a recoverable two-file transaction:
    * by default a new output is removed if publishing the manifest fails;
    * with ``--force`` existing files are first backed up in the same
      directory (copy + fsync). This backup preparation phase is completely
      separated from the publish transaction and its rollback: if the first
      or second backup copy fails, the original output/manifest are never
      touched and ``_rollback_one`` is never called, the backup copies already
      created are best-effort removed (each parent dir fsynced), any backup
      that cannot be removed is retained and reported, and the original error
      is re-raised;
    * only after every existed-before target has a ready backup does any
      publish proceed; on a publish or post-verify failure the existing
      rollback restores old targets from those backups and removes targets
      that did not previously exist, while success removes the backups (and
      fsyncs the parent directory after each removal);
    * rollback of the two targets is independent and best-effort: a target
      that existed before is restored from its backup, one that did not is
      removed. If restoring one target fails, the other is still handled, the
      failed backup is retained on disk, and a :class:`RollbackError` is
      raised carrying the original exception, the per-target restore errors,
      and the retained backup paths.

Individual ``os.replace`` calls are atomic per file; there is no claim of
cross-file atomicity. Between the two publish steps the output and manifest
may transiently refer to different generations.

This module performs no network access and never opens gzip/tar containers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

SCHEMA = "ARSC_ASSEMBLED_RANGES_MANIFEST_V1"
SUFFIX = "resilient.bin"
_READ_BLOCK = 1024 * 1024
CHUNK_RE = re.compile(r"^chunk_(\d+)\.resilient\.bin$")


@dataclass(frozen=True)
class ChunkPlan:
    index: int
    file_name: str
    range_start: int
    byte_count: int


@dataclass(frozen=True)
class ChunkInfo:
    index: int
    path: Path
    file_name: str
    range_start: int
    byte_count: int
    sha256: str


class RollbackError(Exception):
    """Raised when a post-failure rollback could not fully restore a target.

    The original transaction error is chained as ``__cause__``. ``failures``
    is a list of ``(target, backup, error)`` triples describing each target
    that could not be restored; ``backup`` is the retained backup path (or
    ``None`` when the freshly published file could not be removed).
    """

    def __init__(
        self,
        original: BaseException,
        failures: list[tuple[Path, Path | None, BaseException]],
    ) -> None:
        details = []
        for target, backup, error in failures:
            backup_desc = f" retained backup {backup}" if backup is not None else ""
            details.append(f"target {target}{backup_desc} failed: {error}")
        super().__init__("; ".join(details))
        self.original = original
        self.failures = failures


def _rollback_one(
    path: Path, backup: Path | None
) -> tuple[Path, Path | None, BaseException] | None:
    """Best-effort rollback of one published target.

    If an original existed (``backup`` is not ``None``) restore it, consuming
    the backup. Otherwise delete the freshly published ``path`` if present.
    On success returns ``None`` after fsyncing the parent directory. On
    failure returns ``(path, backup, error)`` and leaves a pre-existing
    ``backup`` in place so it can be recovered manually.
    """
    try:
        if backup is not None:
            _replace(backup, path)
        else:
            path.unlink(missing_ok=True)
        _fsync_dir(path.parent)
        return None
    except BaseException as error:
        return (
            path,
            backup if (backup is not None and backup.exists()) else None,
            error,
        )


def compute_ranges(expected_total: int, chunk_bytes: int) -> list[ChunkPlan]:
    """Return the contiguous chunk ranges partitioning ``expected_total``."""
    if expected_total < 0:
        raise ValueError("expected_total must be non-negative")
    if chunk_bytes <= 0:
        raise ValueError("chunk_bytes must be positive")
    plans: list[ChunkPlan] = []
    offset = 0
    index = 0
    while offset < expected_total:
        count = min(chunk_bytes, expected_total - offset)
        plans.append(
            ChunkPlan(
                index=index,
                file_name=f"chunk_{index:03d}.{SUFFIX}",
                range_start=offset,
                byte_count=count,
            )
        )
        offset += count
        index += 1
    return plans


def _stream_cksum(handle) -> tuple[str, int]:
    digest = hashlib.sha256()
    count = 0
    while True:
        block = handle.read(_READ_BLOCK)
        if not block:
            break
        digest.update(block)
        count += len(block)
    return digest.hexdigest(), count


def scan_chunks(chunk_dir: Path, plans: list[ChunkPlan]) -> list[ChunkInfo]:
    """Locate, size-check, and hash every expected chunk; reject extras."""
    expected = {plan.index: plan for plan in plans}
    present: dict[int, Path] = {}
    extra: list[Path] = []
    if chunk_dir.is_dir():
        for child in chunk_dir.iterdir():
            if not child.is_file() and not child.is_symlink():
                continue
            match = CHUNK_RE.fullmatch(child.name)
            if match is None:
                continue
            if child.is_symlink():
                raise ValueError(
                    f"chunk {child.name} is a symlink; symlinks are not allowed"
                )
            index = int(match.group(1))
            if index in expected:
                expected_plan = expected[index]
                # After parsing the index the canonical filename must match
                # exactly what the range plan derives. This accepts the base
                # ``chunk_{index:03d}`` width as well as wider variants needed
                # for indices >= 1000 (e.g. ``chunk_1000.resilient.bin``).
                if child.name != expected_plan.file_name:
                    extra.append(child)
                    continue
                if index in present:
                    raise ValueError(f"duplicate chunk file for index {index}")
                present[index] = child
            else:
                extra.append(child)

    missing = [expected[i].file_name for i in expected if i not in present]
    if missing:
        raise ValueError(f"missing chunks: {sorted(missing)}")
    if extra:
        names = sorted(path.name for path in extra)
        raise ValueError(f"extra same-pattern chunks: {names}")

    infos: list[ChunkInfo] = []
    for plan in plans:
        path = present[plan.index]
        size = path.stat().st_size
        if size != plan.byte_count:
            raise ValueError(
                f"chunk {plan.file_name} size {size} != expected {plan.byte_count}"
            )
        with path.open("rb") as handle:
            digest, count = _stream_cksum(handle)
        if count != plan.byte_count:
            raise ValueError(
                f"chunk {plan.file_name} size changed while hashing: "
                f"{count} != {plan.byte_count}"
            )
        infos.append(
            ChunkInfo(
                index=plan.index,
                path=path,
                file_name=plan.file_name,
                range_start=plan.range_start,
                byte_count=plan.byte_count,
                sha256=digest,
            )
        )
    return infos


def _verify_and_append(
    info: ChunkInfo,
    out_handle,
    assembled_hasher,
) -> int:
    """Re-verify one chunk against its scanned hash/size and append it."""
    digest = hashlib.sha256()
    count = 0
    with info.path.open("rb") as src:
        while True:
            block = src.read(_READ_BLOCK)
            if not block:
                break
            digest.update(block)
            assembled_hasher.update(block)
            out_handle.write(block)
            count += len(block)
    if count != info.byte_count:
        raise ValueError(
            f"chunk {info.file_name} size changed while assembling: "
            f"{count} != {info.byte_count}"
        )
    if digest.hexdigest() != info.sha256:
        raise ValueError(
            f"chunk {info.file_name} content changed while assembling"
        )
    return count


def build_manifest(
    *,
    output: Path,
    expected_total: int,
    chunk_bytes: int,
    plans: list[ChunkPlan],
    infos: list[ChunkInfo],
    assembled_bytes: int,
    assembled_sha: str,
) -> dict:
    return {
        "schema": SCHEMA,
        "parameters": {
            "expected_total": expected_total,
            "chunk_bytes": chunk_bytes,
            "chunk_count": len(plans),
            "suffix": SUFFIX,
        },
        "chunks": [
            {
                "index": info.index,
                "file": info.file_name,
                "range_start": info.range_start,
                "byte_count": info.byte_count,
                "sha256": info.sha256,
            }
            for info in infos
        ],
        "assembled": {
            "file": output.name,
            "byte_count": assembled_bytes,
            "sha256": assembled_sha,
        },
    }


def _replace(src: Path, dst: Path) -> None:
    os.replace(src, dst)


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def publish_manifest(manifest_dict: dict, manifest_path: Path) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(manifest_dict, indent=2, sort_keys=True, ensure_ascii=False)
        + "\n"
    ).encode("utf-8")
    fd, tmp_name = tempfile.mkstemp(
        dir=str(manifest_path.parent), prefix=".manifest-", suffix=".tmp"
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        _replace(tmp, manifest_path)
        tmp = None
        _fsync_dir(manifest_path.parent)
    finally:
        if tmp is not None and tmp.exists():
            tmp.unlink()


def _copy_backup(path: Path, output_dir: Path) -> Path:
    """Copy ``path`` into a fresh sibling temp file (copy + flush/fsync)."""
    fd, backup_name = tempfile.mkstemp(
        dir=str(output_dir), prefix=".backup-", suffix=".tmp"
    )
    backup = Path(backup_name)
    try:
        with os.fdopen(fd, "wb") as dst:
            with path.open("rb") as src:
                while True:
                    block = src.read(_READ_BLOCK)
                    if not block:
                        break
                    dst.write(block)
            dst.flush()
            os.fsync(dst.fileno())
        _fsync_dir(output_dir)
        return backup
    except BaseException:
        try:
            backup.unlink()
        except OSError:
            pass
        raise


def _abort_backup_prep(
    exc: BaseException,
    backup_output: Path | None,
    backup_manifest: Path | None,
) -> "NoReturn":
    """Best-effort cleanup after a force-backup preparation failure.

    Called from the backup-prep phase, which is fully separated from the
    publish transaction and its rollback. It never calls ``_rollback_one``
    and never modifies or deletes the original output/manifest. It only
    best-effort removes the backup copies that were already created,
    fsyncing each parent directory after a removal. A backup copy that
    cannot be removed is retained on disk and reported via a
    :class:`RollbackError`. The original backup-prep exception is always
    chained (as ``__cause__``) so the true failure is never lost.
    """
    retained: list[tuple[Path, Path, BaseException]] = []
    for backup in (backup_output, backup_manifest):
        if backup is None:
            continue
        try:
            backup.unlink()
            _fsync_dir(backup.parent)
        except BaseException as cleanup_error:
            if backup.exists():
                retained.append((backup, backup, cleanup_error))
    if retained:
        raise RollbackError(exc, retained) from exc
    raise exc


def assemble(
    *,
    chunk_dir: Path,
    expected_total: int,
    chunk_bytes: int,
    output: Path,
    manifest: Path,
    force: bool = False,
) -> dict:
    """Verify the chunk set and concatenate into ``output`` plus a manifest."""
    # Reject symlinked targets before resolving, since resolve() would follow
    # a symlink and hide it.
    if output.is_symlink():
        raise ValueError("output is a symlink; symlinks are not allowed")
    if manifest.is_symlink():
        raise ValueError("manifest is a symlink; symlinks are not allowed")
    if output.exists() and not output.is_file():
        raise ValueError("output exists and is not a regular file")
    if manifest.exists() and not manifest.is_file():
        raise ValueError("manifest exists and is not a regular file")

    chunk_dir = chunk_dir.resolve()
    output = output.resolve()
    manifest = manifest.resolve()

    if output == manifest:
        raise ValueError("output and manifest must resolve to different paths")

    plans = compute_ranges(expected_total, chunk_bytes)

    # output/manifest must not collide with any source chunk path.
    chunk_paths = {(chunk_dir / plan.file_name).resolve() for plan in plans}
    if output in chunk_paths:
        raise ValueError(
            f"output path conflicts with a source chunk: {output.name}"
        )
    if manifest in chunk_paths:
        raise ValueError(
            f"manifest path conflicts with a source chunk: {manifest.name}"
        )

    if (output.exists() or output.is_symlink()) and not force:
        raise FileExistsError(
            "refusing to overwrite existing output; pass --force to allow it"
        )
    if (manifest.exists() or manifest.is_symlink()) and not force:
        raise FileExistsError(
            "refusing to overwrite existing manifest; pass --force to allow it"
        )

    infos = scan_chunks(chunk_dir, plans)

    output.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)

    old_output = output.exists() or output.is_symlink()
    old_manifest = manifest.exists() or manifest.is_symlink()
    backup_output: Path | None = None
    backup_manifest: Path | None = None

    # ---- Force backup preparation (result / copy + fsync), fully separated
    # from the publish transaction and its rollback below. Every target that
    # existed before is backed up before any publish step. If the first or
    # second ``_copy_backup`` fails, we never call ``_rollback_one`` and never
    # modify or delete the original output/manifest; we only best-effort clean
    # up the backup copies already created (fsyncing each parent directory)
    # and re-raise.
    try:
        if old_output:
            backup_output = _copy_backup(output, output.parent)
        if old_manifest:
            backup_manifest = _copy_backup(manifest, manifest.parent)
    except BaseException as exc:
        _abort_backup_prep(exc, backup_output, backup_manifest)

    # Every existed-before target must have a ready backup before any publish
    # step can begin; the rollback below relies on those backups being present.
    assert (not old_output) or (
        backup_output is not None and backup_output.exists()
    ), "old output missing a ready backup before publish"
    assert (not old_manifest) or (
        backup_manifest is not None and backup_manifest.exists()
    ), "old manifest missing a ready backup before publish"

    try:
        assembled_hasher = hashlib.sha256()
        assembled_bytes = 0
        fd, tmp_name = tempfile.mkstemp(
            dir=str(output.parent), prefix=".assemble-", suffix=".tmp"
        )
        tmp_out = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                for info in infos:
                    assembled_bytes += _verify_and_append(
                        info, handle, assembled_hasher
                    )
                handle.flush()
                os.fsync(handle.fileno())
            if assembled_bytes != expected_total:
                raise ValueError(
                    f"assembled {assembled_bytes} bytes != expected_total "
                    f"{expected_total}"
                )
            assembled_sha = assembled_hasher.hexdigest()
            _replace(tmp_out, output)
            tmp_out = None
            _fsync_dir(output.parent)
        finally:
            if tmp_out is not None and tmp_out.exists():
                tmp_out.unlink()

        # Re-verify the published output on disk (size + sha) before the
        # manifest is published, so a torn write is caught in-transaction.
        with output.open("rb") as verify_handle:
            verify_digest, verify_size = _stream_cksum(verify_handle)
        if verify_size != assembled_bytes or verify_digest != assembled_sha:
            raise ValueError(
                "published output failed size/sha verification: "
                f"size {verify_size} != {assembled_bytes} or sha mismatch"
            )

        manifest_dict = build_manifest(
            output=output,
            expected_total=expected_total,
            chunk_bytes=chunk_bytes,
            plans=plans,
            infos=infos,
            assembled_bytes=assembled_bytes,
            assembled_sha=assembled_sha,
        )
        publish_manifest(manifest_dict, manifest)
    except BaseException as exc:
        # Roll back each of the two published targets best-effort and
        # independently: a failure restoring one does not block the other.
        failures: list[tuple[Path, Path | None, BaseException]] = []
        output_failure = _rollback_one(output, backup_output)
        if output_failure is not None:
            failures.append(output_failure)
        manifest_failure = _rollback_one(manifest, backup_manifest)
        if manifest_failure is not None:
            failures.append(manifest_failure)
        if failures:
            raise RollbackError(exc, failures) from exc
        raise

    # Success: remove the backups, then durable-delete by fsyncing the dir.
    for backup in (backup_output, backup_manifest):
        if backup is not None:
            backup.unlink()
            _fsync_dir(backup.parent)
    return manifest_dict


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify and concatenate chunk_{NNN}.resilient.bin ranges into an "
            "output file with a JSON manifest."
        )
    )
    parser.add_argument("--chunk-dir", type=Path, required=True)
    parser.add_argument("--expected-total", type=int, required=True)
    parser.add_argument("--chunk-bytes", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--force", action="store_true", help="allow overwriting existing files"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    assemble(
        chunk_dir=args.chunk_dir,
        expected_total=args.expected_total,
        chunk_bytes=args.chunk_bytes,
        output=args.output,
        manifest=args.manifest,
        force=args.force,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
