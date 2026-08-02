"""Build a strict, deterministic transport receipt for the DAAD-X archive.

This tool never opens gzip/tar content.  It validates the byte-range assembler
manifest, re-hashes the opaque assembled file, and binds both plus the exact
transport implementation/test bytes into one no-overwrite JSON receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "ARSC_ROUND11_DAADX_TRANSPORT_RECEIPT_V1"
MANIFEST_SCHEMA = "ARSC_ASSEMBLED_RANGES_MANIFEST_V1"
ORIGINAL_URL = "https://cvit.iiit.ac.in/images/datasets/daadx/daadx.tar.gz"
CDN_URL = "https://cdn.iiit.ac.in/cdn/cvit.iiit.ac.in/images/datasets/daadx/daadx.tar.gz"
EXPECTED_ETAG = '"68089dd7-453ca7834"'
EXPECTED_TOTAL = 18_585_647_156
CHUNK_BYTES = 268_435_456
SUFFIX = "resilient.bin"

IMPLEMENTATION_PATHS: tuple[tuple[str, Path], ...] = (
    ("assembler", ROOT / "scripts/assemble_verified_ranges.py"),
    ("assembler-tests", ROOT / "tests/test_assemble_verified_ranges.py"),
    ("receipt-builder", Path(__file__).resolve()),
    ("receipt-tests", ROOT / "tests/test_build_round11_daadx_transport_receipt.py"),
)
IMPLEMENTATION_ROLES: tuple[str, ...] = tuple(role for role, _ in IMPLEMENTATION_PATHS)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def require_regular(path: Path) -> None:
    require(not path.is_symlink(), f"path must not be a symlink: {path}")
    require(path.is_file(), f"regular file missing: {path}")


def sha256_file(path: Path) -> str:
    require_regular(path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def relative(path: Path, *, root: Path) -> str:
    resolved_root = root.resolve()
    resolved = path.resolve()
    return resolved.relative_to(resolved_root).as_posix()


def require_sha256(value: Any, label: str) -> str:
    require(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdefABCDEF" for character in value),
        f"{label} must be 64 hexadecimal characters",
    )
    return value.upper()


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def scan_archive_ranges(
    archive_path: Path, *, expected_total: int, chunk_bytes: int
) -> tuple[str, list[str]]:
    """Opaque-stream one archive pass, hashing the whole file and each range."""
    require_regular(archive_path)
    whole = hashlib.sha256()
    range_hashes: list[str] = []
    consumed = 0
    with archive_path.open("rb") as stream:
        while consumed < expected_total:
            needed = min(chunk_bytes, expected_total - consumed)
            part = hashlib.sha256()
            remaining = needed
            while remaining:
                block = stream.read(min(8 * 1024 * 1024, remaining))
                require(bool(block), "archive ended before expected total")
                whole.update(block)
                part.update(block)
                consumed += len(block)
                remaining -= len(block)
            range_hashes.append(part.hexdigest().upper())
        require(stream.read(1) == b"", "archive exceeds expected total")
    require(consumed == expected_total, "archive byte count differs")
    return whole.hexdigest().upper(), range_hashes


def validate_manifest(
    manifest: Mapping[str, Any],
    *,
    expected_total: int,
    chunk_bytes: int,
    suffix: str = SUFFIX,
) -> dict[str, Any]:
    """Validate the assembler manifest and return normalized transport facts."""
    require(
        set(manifest) == {"schema", "parameters", "chunks", "assembled"},
        "assembler manifest top-level fields differ",
    )
    require(manifest["schema"] == MANIFEST_SCHEMA, "assembler manifest schema differs")
    parameters = manifest["parameters"]
    require(isinstance(parameters, Mapping), "manifest parameters must be an object")
    require(
        set(parameters) == {"expected_total", "chunk_bytes", "chunk_count", "suffix"},
        "manifest parameter fields differ",
    )
    require(expected_total > 0 and chunk_bytes > 0, "expected_total/chunk_bytes must be positive")
    count = (expected_total + chunk_bytes - 1) // chunk_bytes
    require(parameters["expected_total"] == expected_total, "manifest total differs")
    require(parameters["chunk_bytes"] == chunk_bytes, "manifest chunk size differs")
    require(parameters["chunk_count"] == count, "manifest chunk count differs")
    require(parameters["suffix"] == suffix, "manifest suffix differs")

    chunks = manifest["chunks"]
    require(isinstance(chunks, list) and len(chunks) == count, "manifest chunks differ")
    normalized_chunks: list[dict[str, Any]] = []
    for index, item in enumerate(chunks):
        require(isinstance(item, Mapping), f"chunk {index} must be an object")
        require(
            set(item) == {"index", "file", "range_start", "byte_count", "sha256"},
            f"chunk {index} fields differ",
        )
        start = index * chunk_bytes
        byte_count = min(chunk_bytes, expected_total - start)
        expected_file = f"chunk_{index:03d}.{suffix}"
        require(item["index"] == index, f"chunk {index} index/order differs")
        require(item["file"] == expected_file, f"chunk {index} filename differs")
        require(item["range_start"] == start, f"chunk {index} range start differs")
        require(item["byte_count"] == byte_count, f"chunk {index} byte count differs")
        normalized_chunks.append(
            {
                "index": index,
                "file": expected_file,
                "range_start": start,
                "byte_count": byte_count,
                "sha256": require_sha256(item["sha256"], f"chunk {index} sha256"),
            }
        )

    assembled = manifest["assembled"]
    require(isinstance(assembled, Mapping), "manifest assembled must be an object")
    require(
        set(assembled) == {"file", "byte_count", "sha256"},
        "manifest assembled fields differ",
    )
    require(
        isinstance(assembled["file"], str)
        and bool(assembled["file"])
        and Path(assembled["file"]).name == assembled["file"],
        "assembled file must be one basename",
    )
    require(assembled["byte_count"] == expected_total, "assembled byte count differs")
    return {
        "chunk_count": count,
        "chunks": normalized_chunks,
        "assembled_file": assembled["file"],
        "assembled_sha256": require_sha256(assembled["sha256"], "assembled sha256"),
    }


def build_receipt(
    *,
    manifest_path: Path,
    archive_path: Path,
    implementation_paths: Sequence[tuple[str, Path]],
    root: Path,
    expected_total: int,
    chunk_bytes: int,
    original_url: str = ORIGINAL_URL,
    cdn_url: str = CDN_URL,
    expected_etag: str = EXPECTED_ETAG,
) -> dict[str, Any]:
    require_regular(manifest_path)
    require_regular(archive_path)
    require(manifest_path.resolve() != archive_path.resolve(), "manifest/archive alias")
    require(original_url == ORIGINAL_URL, "original URL differs from formal constant")
    require(cdn_url == CDN_URL, "CDN URL differs from formal constant")
    require(expected_etag == EXPECTED_ETAG, "ETag differs from formal quoted constant")
    manifest_bytes = manifest_path.read_bytes()
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest().upper()
    raw_manifest = json.loads(manifest_bytes.decode("utf-8"))
    require(isinstance(raw_manifest, dict), "assembler manifest must be a JSON object")
    facts = validate_manifest(
        raw_manifest, expected_total=expected_total, chunk_bytes=chunk_bytes
    )
    require(archive_path.name == facts["assembled_file"], "archive basename differs from manifest")
    require(archive_path.stat().st_size == expected_total, "archive size differs")
    archive_sha, range_hashes = scan_archive_ranges(
        archive_path, expected_total=expected_total, chunk_bytes=chunk_bytes
    )
    require(archive_sha == facts["assembled_sha256"], "archive SHA differs from manifest")
    require(
        range_hashes == [item["sha256"] for item in facts["chunks"]],
        "archive range SHA differs from manifest chunk SHA",
    )

    require(
        tuple(role for role, _ in implementation_paths) == IMPLEMENTATION_ROLES,
        "implementation roles/order differ from formal contract",
    )
    roles: set[str] = set()
    identity_paths: list[Path] = []
    implementation: list[dict[str, Any]] = []
    for role, path in implementation_paths:
        require(isinstance(role, str) and bool(role), "implementation role is invalid")
        require(role not in roles, f"duplicate implementation role: {role}")
        roles.add(role)
        require_regular(path)
        require(
            not any(os.path.samefile(path, previous) for previous in identity_paths),
            "implementation paths must be distinct",
        )
        identity_paths.append(path)
        implementation.append(
            {"role": role, "path": relative(path, root=root), "sha256": sha256_file(path)}
        )
    chunk_chain = canonical_json_bytes(facts["chunks"])
    require_regular(manifest_path)
    require(manifest_path.read_bytes() == manifest_bytes, "manifest changed during archive scan")
    return {
        "schema_version": SCHEMA,
        "transport_only": True,
        "official": {
            "original_url": original_url,
            "resolved_cdn_url": cdn_url,
            "expected_etag": expected_etag,
            "expected_content_length_bytes": expected_total,
        },
        "assembler_manifest": {
            "path": relative(manifest_path, root=root),
            "schema_version": MANIFEST_SCHEMA,
            "sha256": manifest_sha,
        },
        "assembled_archive": {
            "path": relative(archive_path, root=root),
            "byte_count": expected_total,
            "sha256": archive_sha,
        },
        "chunk_plan": {
            "chunk_bytes": chunk_bytes,
            "chunk_count": facts["chunk_count"],
            "suffix": SUFFIX,
            "coverage_start": 0,
            "coverage_end_exclusive": expected_total,
            "chunk_records_sha256": hashlib.sha256(chunk_chain).hexdigest().upper(),
        },
        "implementation": implementation,
    }


def publish_receipt(
    receipt: Mapping[str, Any], output: Path, *, link_func: Any = os.link
) -> None:
    require(not output.exists() and not output.is_symlink(), "receipt output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    require(not output.parent.is_symlink(), "receipt parent must not be a symlink")
    temporary = output.with_name(output.name + ".tmp")
    require(not temporary.exists() and not temporary.is_symlink(), "receipt temp already exists")
    owned = False
    try:
        with temporary.open("xb") as stream:
            owned = True
            stream.write(canonical_json_bytes(receipt))
            stream.flush()
            os.fsync(stream.fileno())
        link_func(temporary, output)
        temporary.unlink()
        owned = False
        fsync_directory(output.parent)
    finally:
        if owned and (temporary.exists() or temporary.is_symlink()):
            temporary.unlink()
            fsync_directory(output.parent)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    manifest = Path(os.path.abspath(args.manifest))
    archive = Path(os.path.abspath(args.archive))
    output = Path(os.path.abspath(args.output))
    require_regular(manifest)
    require_regular(archive)
    require(output.resolve() != manifest.resolve(), "receipt/manifest alias")
    require(output.resolve() != archive.resolve(), "receipt/archive alias")
    receipt = build_receipt(
        manifest_path=manifest,
        archive_path=archive,
        implementation_paths=IMPLEMENTATION_PATHS,
        root=ROOT,
        expected_total=EXPECTED_TOTAL,
        chunk_bytes=CHUNK_BYTES,
    )
    publish_receipt(receipt, output)
    print(f"WROTE {relative(output, root=ROOT)}")
    print(f"SHA256 {sha256_file(output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
