from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("layout_binding_generator", ROOT / "scripts/create_round11_layout_execution_binding.py")
assert SPEC and SPEC.loader
generator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generator)
GIT = Path(r"D:\Tools\MinGit\mingw64\bin\git.exe")


def test_binding_is_nonrunning_exact_and_does_not_read_run_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    forbidden = {
        str(ROOT / "outputs/validity/round11_daadx_transport_receipt.json"),
        str(ROOT / "data/external/daadx_official/daadx_assembled_ranges_manifest.json"),
        str(ROOT / "data/external/daadx_official/daadx.assembled.tar.gz"),
    }
    touched: list[str] = []
    original_bytes = Path.read_bytes
    original_text = Path.read_text

    def read_bytes(path: Path) -> bytes:
        if str(path) in forbidden:
            touched.append(str(path))
            raise AssertionError("real input touched")
        return original_bytes(path)

    def read_text(path: Path, *args, **kwargs) -> str:
        if str(path) in forbidden:
            touched.append(str(path))
            raise AssertionError("real input touched")
        return original_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    monkeypatch.setattr(Path, "read_text", read_text)
    binding = generator.create_binding(python=Path(sys.executable), git=GIT)
    assert touched == []
    assert binding["decision"] == generator.DECISION
    assert binding["this_is_go_run"] is False
    assert binding["formal_run"]["timeout_seconds"] == 21600
    assert binding["formal_run"]["closure_reserve_seconds"] == 1800
    assert binding["authorities"]["manifest"]["bytes"] == 15792
    assert binding["authorities"]["archive"]["bytes"] == 18585647156
    assert binding["capabilities"]["label_values"] is False
    assert len({item["path"] for item in binding["artifacts"]}) == len(binding["artifacts"])


def test_publish_is_no_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "binding.json"
    generator.publish(target, b"first")
    with pytest.raises(FileExistsError):
        generator.publish(target, b"second")
    assert target.read_bytes() == b"first"


def test_binding_rejects_git_wrapper() -> None:
    with pytest.raises(RuntimeError, match="wrapper"):
        generator.create_binding(python=Path(sys.executable), git=Path(r"D:\Tools\MinGit\cmd\git.exe"))


def test_publish_zero_write_leaves_blocking_residue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "binding.json"

    def zero_write(fd: int, data: bytes) -> int:
        return 0

    monkeypatch.setattr(os, "write", zero_write)
    with pytest.raises(OSError):
        generator.publish(target, b"payload")
    # The exclusive leaf survives as blocking evidence and cannot be overwritten.
    assert target.exists()
    with pytest.raises(FileExistsError):
        generator.publish(target, b"second")
    assert target.read_bytes() == b""


def test_publish_short_write_completes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "binding.json"
    real_write = os.write

    def short_write(fd: int, data: bytes) -> int:
        if len(data) > 3:
            return real_write(fd, data[:3])
        return real_write(fd, data)

    monkeypatch.setattr(os, "write", short_write)
    generator.publish(target, b"hello world")
    assert target.read_bytes() == b"hello world"


def test_publish_fsync_failure_leaves_blocking_residue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "binding.json"

    def boom(fd: int) -> None:
        raise OSError("file fsync failed")

    monkeypatch.setattr(os, "fsync", boom)
    with pytest.raises(OSError):
        generator.publish(target, b"data")
    assert target.exists()
    with pytest.raises(FileExistsError):
        generator.publish(target, b"other")
    assert target.read_bytes() == b"data"


def test_publish_directory_sync_failure_leaves_blocking_residue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "binding.json"

    def boom(path: Path) -> None:
        raise OSError("directory sync failed")

    monkeypatch.setattr(generator, "sync_directory", boom)
    with pytest.raises(OSError):
        generator.publish(target, b"data")
    assert target.exists()
    with pytest.raises(FileExistsError):
        generator.publish(target, b"other")
    assert target.read_bytes() == b"data"


def test_publish_parent_identity_change_leaves_blocking_residue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "binding.json"
    calls = {"n": 0}

    def fake_identity(path: Path) -> tuple[object, object]:
        calls["n"] += 1
        # First call pins the parent; the post-sync recheck reports a swap.
        if calls["n"] == 1:
            return ("devA", "inoA")
        return ("devA", "inoB")

    monkeypatch.setattr(generator, "directory_identity", fake_identity)
    with pytest.raises(OSError):
        generator.publish(target, b"data")
    assert target.exists()
    with pytest.raises(FileExistsError):
        generator.publish(target, b"other")
    assert target.read_bytes() == b"data"


def test_publish_rejects_parent_reparse_point(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "binding.json"

    def fake(path: Path) -> bool:
        return path == target.parent

    monkeypatch.setattr(generator, "is_reparse_point", fake)
    with pytest.raises(OSError):
        generator.publish(target, b"data")
    assert not target.exists()


def test_publish_rejects_leaf_reparse_point(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "binding.json"
    real = generator.is_reparse_point

    def fake(path: Path) -> bool:
        return path == target or real(path)

    monkeypatch.setattr(generator, "is_reparse_point", fake)
    with pytest.raises(OSError):
        generator.publish(target, b"data")
    assert not target.exists()


def test_git_blob_matches_git_hash_object(tmp_path: Path) -> None:
    data = b"exact\x00bytes\n"
    result = __import__("subprocess").run(
        [str(GIT), "hash-object", "--stdin"], input=data, capture_output=True, check=True
    )
    assert generator.git_blob(data) == result.stdout.decode("ascii").strip()
