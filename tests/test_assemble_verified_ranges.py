from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/assemble_verified_ranges.py"
SPEC = importlib.util.spec_from_file_location("assemble_verified_ranges", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules["assemble_verified_ranges"] = MODULE
SPEC.loader.exec_module(MODULE)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_chunks(chunk_dir: Path, expected_total: int, chunk_bytes: int) -> list[bytes]:
    """Write synthetic chunk files and return their contents in order."""
    chunk_dir.mkdir(parents=True, exist_ok=True)
    contents: list[bytes] = []
    offset = 0
    index = 0
    while offset < expected_total:
        count = min(chunk_bytes, expected_total - offset)
        payload = bytes(
            (offset + pos) % 256 for pos in range(count)
        )
        path = chunk_dir / f"chunk_{index:03d}.resilient.bin"
        path.write_bytes(payload)
        contents.append(payload)
        offset += count
        index += 1
    return contents


def _run(chunk_dir: Path, tmp_path: Path, *, expected_total: int, chunk_bytes: int,
         output_name: str = "assembled.bin", manifest_name: str = "manifest.json",
         force: bool = False) -> dict:
    output = tmp_path / output_name
    manifest = tmp_path / manifest_name
    return MODULE.assemble(
        chunk_dir=chunk_dir,
        expected_total=expected_total,
        chunk_bytes=chunk_bytes,
        output=output,
        manifest=manifest,
        force=force,
    )


# ---------------------------------------------------------------- compute_ranges

def test_compute_ranges_exact_partition() -> None:
    plans = MODULE.compute_ranges(expected_total=10, chunk_bytes=5)
    assert [(p.index, p.range_start, p.byte_count, p.file_name) for p in plans] == [
        (0, 0, 5, "chunk_000.resilient.bin"),
        (1, 5, 5, "chunk_001.resilient.bin"),
    ]


def test_compute_ranges_remainder() -> None:
    plans = MODULE.compute_ranges(expected_total=13, chunk_bytes=5)
    assert [(p.index, p.range_start, p.byte_count) for p in plans] == [
        (0, 0, 5),
        (1, 5, 5),
        (2, 10, 3),
    ]
    assert plans[2].file_name == "chunk_002.resilient.bin"


def test_compute_ranges_single_smaller_chunk() -> None:
    plans = MODULE.compute_ranges(expected_total=4, chunk_bytes=16)
    assert [(p.index, p.range_start, p.byte_count) for p in plans] == [(0, 0, 4)]


def test_compute_ranges_empty() -> None:
    assert MODULE.compute_ranges(expected_total=0, chunk_bytes=4) == []


def test_compute_ranges_invalid_arguments() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        MODULE.compute_ranges(expected_total=-1, chunk_bytes=4)
    with pytest.raises(ValueError, match="positive"):
        MODULE.compute_ranges(expected_total=10, chunk_bytes=0)
    with pytest.raises(ValueError, match="positive"):
        MODULE.compute_ranges(expected_total=10, chunk_bytes=-2)


# ------------------------------------------------------------------- validation

def test_missing_chunk(tmp_path: Path) -> None:
    chunk_dir = tmp_path / "chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    # write only chunk_000 of a two-chunk set
    (chunk_dir / "chunk_000.resilient.bin").write_bytes(b"abcde")
    with pytest.raises(ValueError, match="missing"):
        _run(chunk_dir, tmp_path, expected_total=10, chunk_bytes=5)


def test_wrong_size_chunk(tmp_path: Path) -> None:
    chunk_dir = tmp_path / "chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    (chunk_dir / "chunk_000.resilient.bin").write_bytes(b"abcd")  # 4 not 5
    (chunk_dir / "chunk_001.resilient.bin").write_bytes(b"abcde")
    with pytest.raises(ValueError, match="size"):
        _run(chunk_dir, tmp_path, expected_total=10, chunk_bytes=5)


def test_extra_same_pattern_chunk(tmp_path: Path) -> None:
    chunk_dir = tmp_path / "chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    _write_chunks(chunk_dir, expected_total=10, chunk_bytes=5)
    (chunk_dir / "chunk_002.resilient.bin").write_bytes(b"extra00")
    with pytest.raises(ValueError, match="extra"):
        _run(chunk_dir, tmp_path, expected_total=10, chunk_bytes=5)


def test_unrelated_file_is_ignored(tmp_path: Path) -> None:
    chunk_dir = tmp_path / "chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    _write_chunks(chunk_dir, expected_total=10, chunk_bytes=5)
    (chunk_dir / "notes.txt").write_text("not a chunk\n")
    manifest = _run(chunk_dir, tmp_path, expected_total=10, chunk_bytes=5)
    assert manifest["parameters"]["chunk_count"] == 2


# --------------------------------------------------------- overwrite protection

def test_refuses_overwrite_without_force(tmp_path: Path) -> None:
    chunk_dir = tmp_path / "chunks"
    _write_chunks(chunk_dir, expected_total=10, chunk_bytes=5)
    output = tmp_path / "assembled.bin"
    manifest = tmp_path / "manifest.json"
    output.write_bytes(b"old output")
    manifest.write_text("{}")
    with pytest.raises(FileExistsError, match="output"):
        MODULE.assemble(
            chunk_dir=chunk_dir,
            expected_total=10,
            chunk_bytes=5,
            output=output,
            manifest=manifest,
            force=False,
        )


def test_force_allows_overwrite(tmp_path: Path) -> None:
    chunk_dir = tmp_path / "chunks"
    contents = _write_chunks(chunk_dir, expected_total=10, chunk_bytes=5)
    output = tmp_path / "assembled.bin"
    manifest = tmp_path / "manifest.json"
    output.write_bytes(b"old output")
    manifest.write_text("{}")
    mod = _run(
        chunk_dir, tmp_path, expected_total=10, chunk_bytes=5, force=True
    )
    assert output.read_bytes() == b"".join(contents)
    assert json.loads(manifest.read_text(encoding="utf-8")) == mod


# ------------------------------------------------------- mutation during assembly

def test_source_chunk_changes_between_scan_and_assembly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chunk_dir = tmp_path / "chunks"
    _write_chunks(chunk_dir, expected_total=10, chunk_bytes=5)
    original = MODULE.scan_chunks

    def mutate_scan(chunk_dir: Path, plans) -> None:
        infos = original(chunk_dir, plans)
        target = infos[1].path
        data = bytearray(target.read_bytes())
        data[0] ^= 0xFF
        target.write_bytes(bytes(data))
        return infos

    monkeypatch.setattr(MODULE, "scan_chunks", mutate_scan)
    with pytest.raises(ValueError, match="content changed"):
        _run(chunk_dir, tmp_path, expected_total=10, chunk_bytes=5)


# ---------------------------------------------------------- replace-failure cleanup

def _no_leftover_temps(path: Path) -> bool:
    return not any(p.suffix == ".tmp" for p in path.iterdir())


def test_output_replace_failure_cleans_temp(tmp_path: Path, monkeypatch) -> None:
    chunk_dir = tmp_path / "chunks"
    contents = _write_chunks(chunk_dir, expected_total=10, chunk_bytes=5)
    output = tmp_path / "assembled.bin"
    manifest = tmp_path / "manifest.json"

    real_replace = MODULE._replace

    def failing_replace(src: Path, dst: Path) -> None:
        if src.suffix == ".tmp" and dst == output:
            raise OSError("simulated replace failure")
        real_replace(src, dst)

    monkeypatch.setattr(MODULE, "_replace", failing_replace)
    with pytest.raises(OSError, match="simulated"):
        MODULE.assemble(
            chunk_dir=chunk_dir,
            expected_total=10,
            chunk_bytes=5,
            output=output,
            manifest=manifest,
            force=False,
        )
    assert not output.exists()
    assert not manifest.exists()
    assert _no_leftover_temps(tmp_path)
    # source chunks are untouched
    assert (chunk_dir / "chunk_000.resilient.bin").read_bytes() == contents[0]
    assert (chunk_dir / "chunk_001.resilient.bin").read_bytes() == contents[1]


def test_manifest_replace_failure_cleans_temp(tmp_path: Path, monkeypatch) -> None:
    chunk_dir = tmp_path / "chunks"
    contents = _write_chunks(chunk_dir, expected_total=10, chunk_bytes=5)
    output = tmp_path / "assembled.bin"
    manifest = tmp_path / "manifest.json"

    real_replace = MODULE._replace

    def failing_replace(src: Path, dst: Path) -> None:
        if dst == manifest and src.name.startswith(".manifest-"):
            raise OSError("simulated manifest replace failure")
        real_replace(src, dst)

    monkeypatch.setattr(MODULE, "_replace", failing_replace)
    with pytest.raises(OSError, match="simulated"):
        MODULE.assemble(
            chunk_dir=chunk_dir,
            expected_total=10,
            chunk_bytes=5,
            output=output,
            manifest=manifest,
            force=False,
        )
    # manifest published last must fail with no half products: the freshly
    # published output is rolled back too, leaving no output/manifest/temps.
    assert not output.exists()
    assert not manifest.exists()
    assert _no_leftover_temps(tmp_path)


# ---------------------------------------------- filename / symlink / conflicts

def test_non_canonical_digit_width_is_extra(tmp_path: Path) -> None:
    chunk_dir = tmp_path / "chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    _write_chunks(chunk_dir, expected_total=10, chunk_bytes=5)
    # two-digit variant of chunk index 0: same pattern, non-canonical width
    (chunk_dir / "chunk_00.resilient.bin").write_bytes(b"abcde")
    with pytest.raises(ValueError, match="extra"):
        _run(chunk_dir, tmp_path, expected_total=10, chunk_bytes=5)


def test_non_canonical_wider_digits_are_extra(tmp_path: Path) -> None:
    chunk_dir = tmp_path / "chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    _write_chunks(chunk_dir, expected_total=10, chunk_bytes=5)
    (chunk_dir / "chunk_0000.resilient.bin").write_bytes(b"abcde")
    with pytest.raises(ValueError, match="extra"):
        _run(chunk_dir, tmp_path, expected_total=10, chunk_bytes=5)


def test_pattern_symlink_is_rejected(tmp_path: Path, monkeypatch) -> None:
    chunk_dir = tmp_path / "chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    _write_chunks(chunk_dir, expected_total=10, chunk_bytes=5)
    # Simulate a pattern-matching symlink without needing OS symlink privileges
    # (which Windows shells generally lack). Force is_symlink() to report True
    # for the chunk_000 entry so scan_chunks must reject it.
    symlinked = (chunk_dir / "chunk_000.resilient.bin").resolve()
    real_is_symlink = Path.is_symlink

    def fake_is_symlink(self) -> bool:
        if str(self.resolve()) == str(symlinked):
            return True
        return real_is_symlink(self)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)
    with pytest.raises(ValueError, match="symlink"):
        _run(chunk_dir, tmp_path, expected_total=10, chunk_bytes=5)


def test_output_and_manifest_must_differ(tmp_path: Path) -> None:
    chunk_dir = tmp_path / "chunks"
    _write_chunks(chunk_dir, expected_total=10, chunk_bytes=5)
    with pytest.raises(ValueError, match="different"):
        MODULE.assemble(
            chunk_dir=chunk_dir,
            expected_total=10,
            chunk_bytes=5,
            output=tmp_path / "same.bin",
            manifest=tmp_path / "same.bin",
            force=False,
        )


def test_output_conflicting_with_source_chunk(tmp_path: Path) -> None:
    chunk_dir = tmp_path / "chunks"
    _write_chunks(chunk_dir, expected_total=10, chunk_bytes=5)
    with pytest.raises(ValueError, match="conflicts with a source chunk"):
        MODULE.assemble(
            chunk_dir=chunk_dir,
            expected_total=10,
            chunk_bytes=5,
            output=chunk_dir / "chunk_000.resilient.bin",
            manifest=tmp_path / "manifest.json",
            force=False,
        )


def test_manifest_conflicting_with_source_chunk(tmp_path: Path) -> None:
    chunk_dir = tmp_path / "chunks"
    _write_chunks(chunk_dir, expected_total=10, chunk_bytes=5)
    with pytest.raises(ValueError, match="conflicts with a source chunk"):
        MODULE.assemble(
            chunk_dir=chunk_dir,
            expected_total=10,
            chunk_bytes=5,
            output=tmp_path / "assembled.bin",
            manifest=chunk_dir / "chunk_001.resilient.bin",
            force=False,
        )


# ----------------------------------------- recoverable two-file transaction

def test_force_second_replace_failure_restores_both(tmp_path: Path, monkeypatch) -> None:
    chunk_dir = tmp_path / "chunks"
    contents = _write_chunks(chunk_dir, expected_total=10, chunk_bytes=5)
    output = tmp_path / "assembled.bin"
    manifest = tmp_path / "manifest.json"
    old_output = b"old output bytes"
    old_manifest = json.dumps({"old": True}).encode("utf-8")
    output.write_bytes(old_output)
    manifest.write_bytes(old_manifest)

    real_replace = MODULE._replace

    def failing_replace(src: Path, dst: Path) -> None:
        if dst == manifest and src.name.startswith(".manifest-"):
            raise OSError("simulated second replace failure")
        real_replace(src, dst)

    monkeypatch.setattr(MODULE, "_replace", failing_replace)
    with pytest.raises(OSError, match="simulated"):
        MODULE.assemble(
            chunk_dir=chunk_dir,
            expected_total=10,
            chunk_bytes=5,
            output=output,
            manifest=manifest,
            force=True,
        )
    # both originals are restored; no half-published output or backups remain
    assert output.read_bytes() == old_output
    assert manifest.read_bytes() == old_manifest
    assert _no_leftover_temps(tmp_path)
    assert (chunk_dir / "chunk_000.resilient.bin").read_bytes() == contents[0]


def test_force_post_verify_failure_rolls_back(tmp_path: Path, monkeypatch) -> None:
    chunk_dir = tmp_path / "chunks"
    contents = _write_chunks(chunk_dir, expected_total=10, chunk_bytes=5)
    output = tmp_path / "assembled.bin"
    manifest = tmp_path / "manifest.json"
    old_output = b"old output bytes"
    old_manifest = json.dumps({"old": True}).encode("utf-8")
    output.write_bytes(old_output)
    manifest.write_bytes(old_manifest)

    real_cksum = MODULE._stream_cksum

    def failing_cksum(handle):
        digest, size = real_cksum(handle)
        if getattr(handle, "name", "") == str(output):
            raise OSError("simulated post-verify failure")
        return digest, size

    monkeypatch.setattr(MODULE, "_stream_cksum", failing_cksum)
    with pytest.raises(OSError, match="post-verify"):
        MODULE.assemble(
            chunk_dir=chunk_dir,
            expected_total=10,
            chunk_bytes=5,
            output=output,
            manifest=manifest,
            force=True,
        )
    assert output.read_bytes() == old_output
    assert manifest.read_bytes() == old_manifest
    assert _no_leftover_temps(tmp_path)
    assert (chunk_dir / "chunk_000.resilient.bin").read_bytes() == contents[0]


def test_force_only_one_old_file_restores_it(tmp_path: Path, monkeypatch) -> None:
    chunk_dir = tmp_path / "chunks"
    _write_chunks(chunk_dir, expected_total=10, chunk_bytes=5)
    output = tmp_path / "assembled.bin"
    manifest = tmp_path / "manifest.json"
    # only the manifest exists beforehand; the output does not
    old_manifest = json.dumps({"old": True}).encode("utf-8")
    manifest.write_bytes(old_manifest)

    real_replace = MODULE._replace

    def failing_replace(src: Path, dst: Path) -> None:
        if dst == manifest and src.name.startswith(".manifest-"):
            raise OSError("simulated manifest replace failure")
        real_replace(src, dst)

    monkeypatch.setattr(MODULE, "_replace", failing_replace)
    with pytest.raises(OSError, match="simulated"):
        MODULE.assemble(
            chunk_dir=chunk_dir,
            expected_total=10,
            chunk_bytes=5,
            output=output,
            manifest=manifest,
            force=True,
        )
    # the pre-existing manifest is restored and the newly-published output is
    # removed (it never existed before this transaction)
    assert not output.exists()
    assert manifest.read_bytes() == old_manifest
    assert _no_leftover_temps(tmp_path)


def test_force_only_one_old_file_success(tmp_path: Path) -> None:
    chunk_dir = tmp_path / "chunks"
    contents = _write_chunks(chunk_dir, expected_total=10, chunk_bytes=5)
    output = tmp_path / "assembled.bin"
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}")  # only manifest exists, output does not
    mod = MODULE.assemble(
        chunk_dir=chunk_dir,
        expected_total=10,
        chunk_bytes=5,
        output=output,
        manifest=manifest,
        force=True,
    )
    assert output.read_bytes() == b"".join(contents)
    assert json.loads(manifest.read_text(encoding="utf-8")) == mod
    assert _no_leftover_temps(tmp_path)


# ------------------------------------------------- successful concatenation/EOF

def test_successful_concatenation_with_remainder(tmp_path: Path) -> None:
    chunk_dir = tmp_path / "chunks"
    contents = _write_chunks(chunk_dir, expected_total=101, chunk_bytes=30)
    output = tmp_path / "assembled.bin"
    manifest = tmp_path / "manifest.json"
    mod = MODULE.assemble(
        chunk_dir=chunk_dir,
        expected_total=101,
        chunk_bytes=30,
        output=output,
        manifest=manifest,
        force=False,
    )

    joint = b"".join(contents)
    assert len(joint) == 101
    assert output.read_bytes() == joint
    assert output.stat().st_size == 101

    assert mod["schema"] == MODULE.SCHEMA
    params = mod["parameters"]
    assert params["expected_total"] == 101
    assert params["chunk_bytes"] == 30
    assert params["chunk_count"] == 4
    assert params["suffix"] == "resilient.bin"

    assert [c["index"] for c in mod["chunks"]] == [0, 1, 2, 3]
    assert mod["chunks"][-1]["range_start"] == 90
    assert mod["chunks"][-1]["byte_count"] == 11
    expected_chunk_hashes = [_sha256_bytes(x) for x in contents]
    assert [c["sha256"] for c in mod["chunks"]] == expected_chunk_hashes

    assert mod["assembled"]["file"] == "assembled.bin"
    assert mod["assembled"]["byte_count"] == 101
    assert mod["assembled"]["sha256"] == _sha256_bytes(joint)

    # manifest on disk matches and is deterministic
    assert json.loads(manifest.read_text(encoding="utf-8")) == mod


def test_manifest_is_deterministic_and_mergeable(tmp_path: Path) -> None:
    chunk_dir = tmp_path / "chunks"
    _write_chunks(chunk_dir, expected_total=26, chunk_bytes=8)
    output = tmp_path / "assembled.bin"
    manifest = tmp_path / "manifest.json"
    mod_a = MODULE.assemble(
        chunk_dir=chunk_dir,
        expected_total=26,
        chunk_bytes=8,
        output=output,
        manifest=manifest,
        force=False,
    )
    manifest_a_text = manifest.read_text(encoding="utf-8")
    # force re-assembly into the same paths must reproduce identical bytes
    mod_b = MODULE.assemble(
        chunk_dir=chunk_dir,
        expected_total=26,
        chunk_bytes=8,
        output=output,
        manifest=manifest,
        force=True,
    )
    assert mod_b == mod_a
    assert manifest.read_text(encoding="utf-8") == manifest_a_text
    assert _no_leftover_temps(tmp_path)


# --------------------------------------------------------- >=1000 canonical names

def test_canonical_names_support_index_at_least_1000(tmp_path: Path) -> None:
    chunk_dir = tmp_path / "chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    chunk_bytes = 1
    expected_total = 1001  # chunks indexed 0..1000 inclusive
    for index in range(expected_total):
        (chunk_dir / f"chunk_{index:03d}.resilient.bin").write_bytes(b"x")

    plans = MODULE.compute_ranges(expected_total, chunk_bytes)
    assert plans[1000].file_name == "chunk_1000.resilient.bin"

    mod = _run(
        chunk_dir, tmp_path, expected_total=expected_total, chunk_bytes=chunk_bytes
    )
    indexes = [c["index"] for c in mod["chunks"]]
    assert indexes[-1] == 1000
    assert len(indexes) == expected_total
    assert (tmp_path / "assembled.bin").read_bytes() == b"x" * expected_total
    assert mod["parameters"]["chunk_count"] == expected_total
    # each parsed index carries exactly its canonical filename
    expected_files = {p.index: p.file_name for p in plans}
    assert all(c["file"] == expected_files[c["index"]] for c in mod["chunks"])


def test_non_canonical_width_of_high_index_is_extra(tmp_path: Path) -> None:
    chunk_dir = tmp_path / "chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    chunk_bytes = 1
    expected_total = 1001
    for index in range(expected_total):
        (chunk_dir / f"chunk_{index:03d}.resilient.bin").write_bytes(b"x")
    # index 1000 with extra leading zero pads: same index, wrong canonical name
    (chunk_dir / "chunk_01000.resilient.bin").write_bytes(b"x")
    with pytest.raises(ValueError, match="extra"):
        _run(chunk_dir, tmp_path, expected_total=expected_total, chunk_bytes=chunk_bytes)


# --------------------------------------------------- output/manifest symlink reject

def _symlink_fake(monkeypatch: pytest.MonkeyPatch, paths: set[str]) -> None:
    real_is_symlink = Path.is_symlink

    def fake_is_symlink(self) -> bool:
        if str(self.resolve()) in paths:
            return True
        return real_is_symlink(self)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)


def test_output_symlink_is_rejected(tmp_path: Path, monkeypatch) -> None:
    chunk_dir = tmp_path / "chunks"
    _write_chunks(chunk_dir, expected_total=10, chunk_bytes=5)
    output = tmp_path / "assembled.bin"
    manifest = tmp_path / "manifest.json"
    _symlink_fake(monkeypatch, {str(output.resolve())})
    with pytest.raises(ValueError, match="symlink"):
        MODULE.assemble(
            chunk_dir=chunk_dir,
            expected_total=10,
            chunk_bytes=5,
            output=output,
            manifest=manifest,
            force=False,
        )


def test_manifest_symlink_is_rejected(tmp_path: Path, monkeypatch) -> None:
    chunk_dir = tmp_path / "chunks"
    _write_chunks(chunk_dir, expected_total=10, chunk_bytes=5)
    output = tmp_path / "assembled.bin"
    manifest = tmp_path / "manifest.json"
    _symlink_fake(monkeypatch, {str(manifest.resolve())})
    with pytest.raises(ValueError, match="symlink"):
        MODULE.assemble(
            chunk_dir=chunk_dir,
            expected_total=10,
            chunk_bytes=5,
            output=output,
            manifest=manifest,
            force=False,
        )


def test_both_output_and_manifest_symlinks_rejected(tmp_path: Path, monkeypatch) -> None:
    chunk_dir = tmp_path / "chunks"
    _write_chunks(chunk_dir, expected_total=10, chunk_bytes=5)
    output = tmp_path / "assembled.bin"
    manifest = tmp_path / "manifest.json"
    _symlink_fake(monkeypatch, {str(output.resolve()), str(manifest.resolve())})
    with pytest.raises(ValueError, match="symlink"):
        MODULE.assemble(
            chunk_dir=chunk_dir,
            expected_total=10,
            chunk_bytes=5,
            output=output,
            manifest=manifest,
            force=False,
        )


# ------------------------------------------------ output/manifest directory reject

@pytest.mark.parametrize("force", [False, True])
def test_output_directory_is_rejected(tmp_path: Path, force: bool) -> None:
    chunk_dir = tmp_path / "chunks"
    _write_chunks(chunk_dir, expected_total=10, chunk_bytes=5)
    output = tmp_path / "assembled.bin"
    manifest = tmp_path / "manifest.json"
    output.mkdir()  # output exists but is a directory
    with pytest.raises(ValueError, match="not a regular file"):
        MODULE.assemble(
            chunk_dir=chunk_dir,
            expected_total=10,
            chunk_bytes=5,
            output=output,
            manifest=manifest,
            force=force,
        )
    # the existing directory must be left untouched
    assert output.is_dir()


@pytest.mark.parametrize("force", [False, True])
def test_manifest_directory_is_rejected(tmp_path: Path, force: bool) -> None:
    chunk_dir = tmp_path / "chunks"
    _write_chunks(chunk_dir, expected_total=10, chunk_bytes=5)
    output = tmp_path / "assembled.bin"
    manifest = tmp_path / "manifest.json"
    manifest.mkdir()  # manifest exists but is a directory
    with pytest.raises(ValueError, match="not a regular file"):
        MODULE.assemble(
            chunk_dir=chunk_dir,
            expected_total=10,
            chunk_bytes=5,
            output=output,
            manifest=manifest,
            force=force,
        )
    # the existing directory must be left untouched
    assert manifest.is_dir()


# ------------------------------------------ post-manifest dir-fsync failure cleanup

def test_manifest_dir_fsync_failure_leaves_no_half_products(
    tmp_path: Path, monkeypatch
) -> None:
    chunk_dir = tmp_path / "chunks"
    _write_chunks(chunk_dir, expected_total=10, chunk_bytes=5)
    output = tmp_path / "assembled.bin"
    manifest = tmp_path / "manifest.json"
    real_fsync_dir = MODULE._fsync_dir

    def failing_fsync_dir(path) -> None:
        # Fail only the fsync right after the manifest was replaced (both the
        # fresh output and manifest exist on disk by that point).
        if path == manifest.parent and manifest.exists() and output.exists():
            raise OSError("simulated manifest dir fsync failure")
        real_fsync_dir(path)

    monkeypatch.setattr(MODULE, "_fsync_dir", failing_fsync_dir)
    with pytest.raises(OSError, match="fsync"):
        MODULE.assemble(
            chunk_dir=chunk_dir,
            expected_total=10,
            chunk_bytes=5,
            output=output,
            manifest=manifest,
            force=False,
        )
    # the manifest replace had already succeeded, but rollback must remove it
    # and the freshly published output, leaving no half products.
    assert not output.exists()
    assert not manifest.exists()
    assert _no_leftover_temps(tmp_path)


# --------------------------- partial rollback failure keeps backup, recovers other

def test_one_rollback_failure_recovers_other_and_keeps_backup(
    tmp_path: Path, monkeypatch
) -> None:
    chunk_dir = tmp_path / "chunks"
    _write_chunks(chunk_dir, expected_total=10, chunk_bytes=5)
    output = tmp_path / "assembled.bin"
    manifest = tmp_path / "manifest.json"
    old_output = b"old output bytes"
    old_manifest = json.dumps({"old": True}).encode("utf-8")
    output.write_bytes(old_output)
    manifest.write_bytes(old_manifest)

    real_replace = MODULE._replace

    def failing_replace(src, dst) -> None:
        # Fail the manifest publish to trigger rollback, and also fail the
        # manifest *restore* (dst==manifest with a .backup- source) so that
        # target's rollback keeps its backup.
        if dst == manifest and src.name.startswith(".manifest-"):
            raise OSError("simulated manifest publish failure")
        if dst == manifest and src.name.startswith(".backup-"):
            raise OSError("simulated manifest restore failure")
        real_replace(src, dst)

    monkeypatch.setattr(MODULE, "_replace", failing_replace)
    with pytest.raises(MODULE.RollbackError) as exc_info:
        MODULE.assemble(
            chunk_dir=chunk_dir,
            expected_total=10,
            chunk_bytes=5,
            output=output,
            manifest=manifest,
            force=True,
        )
    err = exc_info.value
    # the original manifest publish failure is chained in
    assert isinstance(err.__cause__, OSError)
    assert "publish" in str(err.__cause__)
    # only the manifest restore failed
    assert len(err.failures) == 1
    fail_target, fail_backup, fail_error = err.failures[0]
    assert fail_target == manifest
    assert fail_backup is not None and fail_backup.exists()
    assert "restore" in str(fail_error)
    # message surfaces the failure with the retained backup path
    assert str(manifest) in str(err)
    assert str(fail_backup) in str(err)

    # the output target was still recovered despite the manifest failure
    assert output.read_bytes() == old_output
    # manifest was never replaced (publish failed), so only its backup remains
    assert manifest.read_bytes() == old_manifest
    # the retained manifest backup remains on disk; no other temps
    backups = [p for p in tmp_path.iterdir() if p.name.startswith(".backup-")]
    assert backups == [fail_backup]
    assert not any(
        p.name.startswith((".assemble-", ".manifest-")) for p in tmp_path.iterdir()
    )
    # source chunks are untouched
    assert (chunk_dir / "chunk_000.resilient.bin").read_bytes() == b"\x00\x01\x02\x03\x04"


def test_rollback_fsync_failure_reports_none_and_restores_both(
    tmp_path: Path, monkeypatch
) -> None:
    chunk_dir = tmp_path / "chunks"
    _write_chunks(chunk_dir, expected_total=10, chunk_bytes=5)
    output = tmp_path / "assembled.bin"
    manifest = tmp_path / "manifest.json"
    old_output = b"old output bytes"
    old_manifest = json.dumps({"old": True}).encode("utf-8")
    output.write_bytes(old_output)
    manifest.write_bytes(old_manifest)

    real_replace = MODULE._replace

    def failing_replace(src: Path, dst: Path) -> None:
        # Fail the manifest publish to trigger the rollback of both targets.
        if dst == manifest and src.name.startswith(".manifest-"):
            raise OSError("simulated manifest publish failure")
        real_replace(src, dst)

    real_fsync_dir = MODULE._fsync_dir
    fsync_calls = 0

    def failing_fsync_dir(path) -> None:
        nonlocal fsync_calls
        fsync_calls += 1
        # Dir-fsync call order here: two backup copies, the output publish,
        # then (in rollback) output restore, then manifest restore. The 4th
        # call is the fsync that follows the output backup being moved back;
        # fail it so the backup source is already consumed (it no longer
        # exists) by the time _rollback_one records the failure.
        if fsync_calls == 4:
            raise OSError("simulated rollback fsync failure")
        real_fsync_dir(path)

    monkeypatch.setattr(MODULE, "_replace", failing_replace)
    monkeypatch.setattr(MODULE, "_fsync_dir", failing_fsync_dir)
    with pytest.raises(MODULE.RollbackError) as exc_info:
        MODULE.assemble(
            chunk_dir=chunk_dir,
            expected_total=10,
            chunk_bytes=5,
            output=output,
            manifest=manifest,
            force=True,
        )
    err = exc_info.value
    # the original manifest publish failure is chained in
    assert isinstance(err.__cause__, OSError)
    assert "publish" in str(err.__cause__)
    # only the output rollback fsync failed, and its backup was already
    # consumed, so the reported backup must be None (not a stale path)
    assert len(err.failures) == 1
    fail_target, fail_backup, fail_error = err.failures[0]
    assert fail_target == output
    assert fail_backup is None
    assert "fsync" in str(fail_error)

    # although its fsync failed, the output's old content was already restored
    assert output.read_bytes() == old_output
    # the other target (manifest) also performed its restore
    assert manifest.read_bytes() == old_manifest
    assert _no_leftover_temps(tmp_path)
    # source chunks are untouched
    assert (chunk_dir / "chunk_000.resilient.bin").read_bytes() == b"\x00\x01\x02\x03\x04"


# --------------- force backup-prep failure never touches originals/rolls back

def _no_any_temps(path: Path) -> bool:
    return not any(
        p.name.startswith((".backup-", ".assemble-", ".manifest-"))
        for p in path.iterdir()
    )


def test_force_first_backup_failure_leaves_originals_untouched(
    tmp_path: Path, monkeypatch
) -> None:
    chunk_dir = tmp_path / "chunks"
    _write_chunks(chunk_dir, expected_total=10, chunk_bytes=5)
    output = tmp_path / "assembled.bin"
    manifest = tmp_path / "manifest.json"
    old_output = b"old output bytes"
    old_manifest = json.dumps({"old": True}).encode("utf-8")
    output.write_bytes(old_output)
    manifest.write_bytes(old_manifest)

    call_count = 0

    def failing_first_backup(path: Path, output_dir: Path):
        nonlocal call_count
        call_count += 1
        # The output backup is created first; fail it immediately.
        raise OSError("simulated first backup failure")

    monkeypatch.setattr(MODULE, "_copy_backup", failing_first_backup)
    with pytest.raises(OSError, match="first backup"):
        MODULE.assemble(
            chunk_dir=chunk_dir,
            expected_total=10,
            chunk_bytes=5,
            output=output,
            manifest=manifest,
            force=True,
        )
    # Neither original was modified nor deleted; only the failed backup prep
    # was attempted, and _rollback_one was never invoked.
    assert call_count == 1
    assert output.read_bytes() == old_output
    assert manifest.read_bytes() == old_manifest
    # no leftover backup/assemble/manifest temps
    assert _no_any_temps(tmp_path)
    # source chunks are untouched
    assert (chunk_dir / "chunk_000.resilient.bin").read_bytes() == b"\x00\x01\x02\x03\x04"


def test_force_second_backup_failure_cleans_first_backup_and_keeps_originals(
    tmp_path: Path, monkeypatch
) -> None:
    chunk_dir = tmp_path / "chunks"
    _write_chunks(chunk_dir, expected_total=10, chunk_bytes=5)
    output = tmp_path / "assembled.bin"
    manifest = tmp_path / "manifest.json"
    old_output = b"old output bytes"
    old_manifest = json.dumps({"old": True}).encode("utf-8")
    output.write_bytes(old_output)
    manifest.write_bytes(old_manifest)

    real_copy_backup = MODULE._copy_backup
    call_count = 0

    def failing_second_backup(path: Path, output_dir: Path):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Output backup succeeds (and is a real backup artifact on disk).
            return real_copy_backup(path, output_dir)
        # Manifest backup (second) fails.
        raise OSError("simulated second backup failure")

    monkeypatch.setattr(MODULE, "_copy_backup", failing_second_backup)
    with pytest.raises(OSError, match="second backup"):
        MODULE.assemble(
            chunk_dir=chunk_dir,
            expected_total=10,
            chunk_bytes=5,
            output=output,
            manifest=manifest,
            force=True,
        )
    # The output backup copy was created, then best-effort removed; neither
    # original target was modified or deleted.
    assert call_count == 2
    assert output.read_bytes() == old_output
    assert manifest.read_bytes() == old_manifest
    # the created backup was cleaned up; no leftover backup/assemble/manifest
    # temps at all (no publish step was ever reached)
    assert _no_any_temps(tmp_path)
    # source chunks are untouched
    assert (chunk_dir / "chunk_000.resilient.bin").read_bytes() == b"\x00\x01\x02\x03\x04"
