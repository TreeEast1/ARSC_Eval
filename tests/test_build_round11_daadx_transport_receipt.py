from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_round11_daadx_transport_receipt.py"
SPEC = importlib.util.spec_from_file_location("round11_receipt", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _fixture(tmp_path: Path, *, total: int = 10, chunk_bytes: int = 4):
    archive = tmp_path / "daadx.tar.gz"
    payload = bytes(range(total))
    archive.write_bytes(payload)
    count = (total + chunk_bytes - 1) // chunk_bytes
    chunks = []
    for index in range(count):
        start = index * chunk_bytes
        part = payload[start : start + chunk_bytes]
        chunks.append(
            {
                "index": index,
                "file": f"chunk_{index:03d}.resilient.bin",
                "range_start": start,
                "byte_count": len(part),
                "sha256": _sha(part),
            }
        )
    manifest = {
        "schema": MODULE.MANIFEST_SCHEMA,
        "parameters": {
            "expected_total": total,
            "chunk_bytes": chunk_bytes,
            "chunk_count": count,
            "suffix": "resilient.bin",
        },
        "chunks": chunks,
        "assembled": {
            "file": archive.name,
            "byte_count": total,
            "sha256": _sha(payload),
        },
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    implementations = []
    for role in ("assembler", "assembler-tests", "receipt-builder", "receipt-tests"):
        path = tmp_path / f"{role}.py"
        path.write_text(role, encoding="utf-8")
        implementations.append((role, path))
    return archive, manifest_path, manifest, implementations


def _build(tmp_path: Path, *, total: int = 10, chunk_bytes: int = 4):
    archive, manifest_path, manifest, implementations = _fixture(
        tmp_path, total=total, chunk_bytes=chunk_bytes
    )
    receipt = MODULE.build_receipt(
        manifest_path=manifest_path,
        archive_path=archive,
        implementation_paths=implementations,
        root=tmp_path,
        expected_total=total,
        chunk_bytes=chunk_bytes,
    )
    return receipt, archive, manifest_path, manifest, implementations


def test_formal_constants_and_chunk_count() -> None:
    assert MODULE.EXPECTED_TOTAL == 18_585_647_156
    assert MODULE.CHUNK_BYTES == 268_435_456
    assert (MODULE.EXPECTED_TOTAL + MODULE.CHUNK_BYTES - 1) // MODULE.CHUNK_BYTES == 70
    assert MODULE.EXPECTED_ETAG == '"68089dd7-453ca7834"'


def test_receipt_exact_structure_bindings_and_determinism(tmp_path: Path) -> None:
    receipt, archive, manifest_path, manifest, implementations = _build(tmp_path)
    assert set(receipt) == {
        "schema_version", "transport_only", "official", "assembler_manifest",
        "assembled_archive", "chunk_plan", "implementation",
    }
    assert receipt["schema_version"] == MODULE.SCHEMA
    assert receipt["transport_only"] is True
    assert receipt["assembled_archive"] == {
        "path": archive.name,
        "byte_count": 10,
        "sha256": _sha(archive.read_bytes()).upper(),
    }
    assert receipt["assembler_manifest"]["path"] == manifest_path.name
    assert receipt["assembler_manifest"]["sha256"] == MODULE.sha256_file(manifest_path)
    assert receipt["chunk_plan"]["chunk_count"] == 3
    assert receipt["chunk_plan"]["coverage_end_exclusive"] == 10
    assert [item["role"] for item in receipt["implementation"]] == [r for r, _ in implementations]
    assert receipt == MODULE.build_receipt(
        manifest_path=manifest_path,
        archive_path=archive,
        implementation_paths=implementations,
        root=tmp_path,
        expected_total=10,
        chunk_bytes=4,
    )
    assert MODULE.canonical_json_bytes(receipt).endswith(b"\n")


@pytest.mark.parametrize(
    "mutate,message",
    [
        (lambda m: m.__setitem__("extra", 1), "top-level"),
        (lambda m: m.__setitem__("schema", "WRONG"), "schema"),
        (lambda m: m["parameters"].__setitem__("extra", 1), "parameter fields"),
        (lambda m: m["parameters"].__setitem__("chunk_count", 9), "chunk count"),
        (lambda m: m["chunks"][0].__setitem__("extra", 1), "fields differ"),
        (lambda m: m["chunks"][0].__setitem__("index", 1), "index/order"),
        (lambda m: m["chunks"][1].__setitem__("range_start", 5), "range start"),
        (lambda m: m["chunks"][-1].__setitem__("byte_count", 4), "byte count"),
        (lambda m: m["chunks"][0].__setitem__("file", "chunk_00.resilient.bin"), "filename"),
        (lambda m: m["chunks"][0].__setitem__("sha256", "bad"), "sha256"),
        (lambda m: m["assembled"].__setitem__("extra", 1), "assembled fields"),
    ],
)
def test_manifest_structural_failures(tmp_path: Path, mutate, message: str) -> None:
    _archive, _path, manifest, _impl = _fixture(tmp_path)
    mutate(manifest)
    with pytest.raises(ValueError, match=message):
        MODULE.validate_manifest(manifest, expected_total=10, chunk_bytes=4)


def test_archive_size_and_hash_must_match_manifest(tmp_path: Path) -> None:
    archive, manifest_path, _manifest, implementations = _fixture(tmp_path)
    archive.write_bytes(b"short")
    with pytest.raises(ValueError, match="archive size"):
        MODULE.build_receipt(
            manifest_path=manifest_path, archive_path=archive,
            implementation_paths=implementations, root=tmp_path,
            expected_total=10, chunk_bytes=4,
        )
    archive.write_bytes(b"x" * 10)
    with pytest.raises(ValueError, match="archive SHA"):
        MODULE.build_receipt(
            manifest_path=manifest_path, archive_path=archive,
            implementation_paths=implementations, root=tmp_path,
            expected_total=10, chunk_bytes=4,
        )


def test_valid_hex_but_wrong_chunk_sha_is_rejected(tmp_path: Path) -> None:
    archive, manifest_path, manifest, implementations = _fixture(tmp_path)
    manifest["chunks"][1]["sha256"] = "A" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="range SHA"):
        MODULE.build_receipt(
            manifest_path=manifest_path, archive_path=archive,
            implementation_paths=implementations, root=tmp_path,
            expected_total=10, chunk_bytes=4,
        )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"original_url": "https://wrong"}, "original URL"),
        ({"cdn_url": "https://wrong"}, "CDN URL"),
        ({"expected_etag": "68089dd7-453ca7834"}, "ETag"),
        ({"expected_etag": '"DIFFERENT"'}, "ETag"),
    ],
)
def test_transport_constants_are_not_injectable(
    tmp_path: Path, kwargs: dict, message: str
) -> None:
    archive, manifest_path, _manifest, implementations = _fixture(tmp_path)
    with pytest.raises(ValueError, match=message):
        MODULE.build_receipt(
            manifest_path=manifest_path, archive_path=archive,
            implementation_paths=implementations, root=tmp_path,
            expected_total=10, chunk_bytes=4, **kwargs,
        )


def test_manifest_toctou_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive, manifest_path, manifest, implementations = _fixture(tmp_path)
    original_scan = MODULE.scan_archive_ranges

    def mutating_scan(*args, **kwargs):
        result = original_scan(*args, **kwargs)
        manifest["assembled"]["file"] = "changed.tar.gz"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return result

    monkeypatch.setattr(MODULE, "scan_archive_ranges", mutating_scan)
    with pytest.raises(ValueError, match="manifest changed"):
        MODULE.build_receipt(
            manifest_path=manifest_path, archive_path=archive,
            implementation_paths=implementations, root=tmp_path,
            expected_total=10, chunk_bytes=4,
        )


def test_symlink_archive_rejected_when_supported(tmp_path: Path) -> None:
    archive, manifest_path, _manifest, implementations = _fixture(tmp_path)
    link = tmp_path / "archive-link"
    try:
        link.symlink_to(archive)
    except (OSError, NotImplementedError):
        pytest.skip("symlink unavailable")
    with pytest.raises(ValueError, match="symlink"):
        MODULE.build_receipt(
            manifest_path=manifest_path, archive_path=link,
            implementation_paths=implementations, root=tmp_path,
            expected_total=10, chunk_bytes=4,
        )


def test_publish_is_no_overwrite_and_cleans_owned_temp(tmp_path: Path) -> None:
    receipt, *_ = _build(tmp_path)
    output = tmp_path / "receipt.json"
    MODULE.publish_receipt(receipt, output)
    first = output.read_bytes()
    assert json.loads(first)["schema_version"] == MODULE.SCHEMA
    assert not output.with_name(output.name + ".tmp").exists()
    with pytest.raises(ValueError, match="already exists"):
        MODULE.publish_receipt(receipt, output)
    assert output.read_bytes() == first


def test_publish_link_failure_cleans_only_owned_temp(tmp_path: Path) -> None:
    receipt, *_ = _build(tmp_path)
    output = tmp_path / "receipt.json"

    def fail_link(source: Path, target: Path) -> None:
        raise OSError("injected link failure")

    with pytest.raises(OSError, match="injected link failure"):
        MODULE.publish_receipt(receipt, output, link_func=fail_link)
    assert not output.exists()
    assert not output.with_name(output.name + ".tmp").exists()


def test_publish_competitor_output_and_temp_are_preserved(tmp_path: Path) -> None:
    receipt, *_ = _build(tmp_path)
    output = tmp_path / "receipt.json"

    def competitor_link(source: Path, target: Path) -> None:
        target.write_bytes(b"competitor")
        raise FileExistsError("competitor won")

    with pytest.raises(FileExistsError, match="competitor won"):
        MODULE.publish_receipt(receipt, output, link_func=competitor_link)
    assert output.read_bytes() == b"competitor"
    assert not output.with_name(output.name + ".tmp").exists()

    other_output = tmp_path / "other.json"
    other_temp = other_output.with_name(other_output.name + ".tmp")
    other_temp.write_bytes(b"other owner")
    with pytest.raises(ValueError, match="temp already exists"):
        MODULE.publish_receipt(receipt, other_output)
    assert other_temp.read_bytes() == b"other owner"


def test_duplicate_implementation_role_and_outside_root_rejected(tmp_path: Path) -> None:
    archive, manifest_path, _manifest, implementations = _fixture(tmp_path)
    duplicate = [implementations[0], (implementations[0][0], implementations[1][1])]
    with pytest.raises(ValueError, match="roles/order"):
        MODULE.build_receipt(
            manifest_path=manifest_path, archive_path=archive,
            implementation_paths=duplicate, root=tmp_path,
            expected_total=10, chunk_bytes=4,
        )


def test_implementation_roles_order_and_hardlink_alias_rejected(tmp_path: Path) -> None:
    archive, manifest_path, _manifest, implementations = _fixture(tmp_path)
    with pytest.raises(ValueError, match="roles/order"):
        MODULE.build_receipt(
            manifest_path=manifest_path, archive_path=archive,
            implementation_paths=list(reversed(implementations)), root=tmp_path,
            expected_total=10, chunk_bytes=4,
        )
    alias = tmp_path / "hardlink-alias.py"
    try:
        alias.hardlink_to(implementations[0][1])
    except (OSError, NotImplementedError):
        pytest.skip("hardlink unavailable")
    aliased = list(implementations)
    aliased[1] = (aliased[1][0], alias)
    with pytest.raises(ValueError, match="paths must be distinct"):
        MODULE.build_receipt(
            manifest_path=manifest_path, archive_path=archive,
            implementation_paths=aliased, root=tmp_path,
            expected_total=10, chunk_bytes=4,
        )


@pytest.mark.parametrize("link_which", ["manifest", "archive"])
def test_cli_rejects_symlink_before_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, link_which: str
) -> None:
    archive, manifest_path, _manifest, implementations = _fixture(tmp_path)
    target = manifest_path if link_which == "manifest" else archive
    link = tmp_path / f"{link_which}-link"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink unavailable")
    monkeypatch.setattr(MODULE, "EXPECTED_TOTAL", 10)
    monkeypatch.setattr(MODULE, "CHUNK_BYTES", 4)
    monkeypatch.setattr(MODULE, "ROOT", tmp_path)
    monkeypatch.setattr(MODULE, "IMPLEMENTATION_PATHS", tuple(implementations))
    manifest_arg = link if link_which == "manifest" else manifest_path
    archive_arg = link if link_which == "archive" else archive
    with pytest.raises(ValueError, match="symlink"):
        MODULE.main([
            "--manifest", str(manifest_arg), "--archive", str(archive_arg),
            "--output", str(tmp_path / "receipt.json"),
        ])
