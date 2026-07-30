"""Download and extract the official BDD-OIA last-frame archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

import requests


OFFICIAL_FILE_ID = "1WFiwRi_sMA_McZnkbEjh8Rnl-Im7_9Mk"
OFFICIAL_URL = (
    "https://drive.usercontent.google.com/download"
    f"?id={OFFICIAL_FILE_ID}&export=download&confirm=t"
)
EXPECTED_BYTES = 778_443_955


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--url", default=OFFICIAL_URL)
    parser.add_argument("--chunk-mib", type=int, default=8)
    parser.add_argument("--no-extract", action="store_true")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path, chunk_size: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    existing = destination.stat().st_size if destination.exists() else 0
    headers = {"Range": f"bytes={existing}-"} if existing else {}
    with requests.get(url, headers=headers, stream=True, timeout=(30, 120)) as response:
        response.raise_for_status()
        if existing and response.status_code != 206:
            existing = 0
            mode = "wb"
        else:
            mode = "ab" if existing else "wb"
        total = int(response.headers.get("content-length", 0)) + existing
        downloaded = existing
        with destination.open(mode) as handle:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if not chunk:
                    continue
                handle.write(chunk)
                downloaded += len(chunk)
                print(
                    f"\rDownloaded {downloaded / 2**20:.1f} / "
                    f"{total / 2**20:.1f} MiB",
                    end="",
                    flush=True,
                )
    print()


def safe_extract(archive: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    target_resolved = target.resolve()
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            member_target = (target / member.filename).resolve()
            if target_resolved not in member_target.parents and member_target != target_resolved:
                raise RuntimeError(f"Unsafe archive member: {member.filename}")
        bundle.extractall(target)


def main() -> int:
    args = parse_args()
    root = args.data_root.resolve()
    archive = root / "raw" / "lastframe.zip"
    extract_root = root / "raw" / "lastframe"
    metadata_path = root / "raw" / "download_metadata.json"

    if not archive.exists() or archive.stat().st_size != EXPECTED_BYTES:
        download(args.url, archive, args.chunk_mib * 1024 * 1024)
    if archive.stat().st_size != EXPECTED_BYTES:
        raise RuntimeError(
            f"Unexpected archive size: {archive.stat().st_size}; "
            f"expected {EXPECTED_BYTES}"
        )

    archive_sha256 = sha256(archive)
    metadata = {
        "source": args.url,
        "google_drive_file_id": OFFICIAL_FILE_ID,
        "archive": str(archive),
        "bytes": archive.stat().st_size,
        "sha256": archive_sha256,
    }
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    if not args.no_extract:
        if extract_root.exists():
            sentinel = extract_root / ".extracted.json"
            if sentinel.exists():
                print(f"Already extracted: {extract_root}")
                return 0
            shutil.rmtree(extract_root)
        safe_extract(archive, extract_root)
        (extract_root / ".extracted.json").write_text(
            json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
