"""Reliably cache the fixed pretrained weights used by this experiment."""

from __future__ import annotations

import argparse
import hashlib
import time
from pathlib import Path

import requests


ARTIFACTS = {
    "resnet50": {
        "url": "https://download.pytorch.org/models/resnet50-11ad3fa6.pth",
        "file_name": "resnet50-11ad3fa6.pth",
        "bytes": 102_540_417,
        "sha256_prefix": "11ad3fa6",
    }
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", choices=ARTIFACTS, default="resnet50")
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path.home() / ".cache" / "torch" / "hub" / "checkpoints",
    )
    parser.add_argument("--max-attempts", type=int, default=30)
    return parser.parse_args()


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> int:
    args = parse_args()
    artifact = ARTIFACTS[args.artifact]
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    destination = args.cache_dir / artifact["file_name"]
    partial = destination.with_suffix(destination.suffix + ".part")
    if (
        destination.exists()
        and destination.stat().st_size == artifact["bytes"]
        and digest(destination).startswith(artifact["sha256_prefix"])
    ):
        print(f"Verified cached weight: {destination}")
        return 0

    for attempt in range(1, args.max_attempts + 1):
        existing = partial.stat().st_size if partial.exists() else 0
        if existing > artifact["bytes"]:
            partial.unlink()
            existing = 0
        headers = {"Range": f"bytes={existing}-"} if existing else {}
        try:
            with requests.get(
                artifact["url"],
                headers=headers,
                stream=True,
                timeout=(30, 120),
            ) as response:
                response.raise_for_status()
                if existing and response.status_code != 206:
                    partial.unlink(missing_ok=True)
                    existing = 0
                    mode = "wb"
                else:
                    mode = "ab" if existing else "wb"
                with partial.open(mode) as handle:
                    for chunk in response.iter_content(1024 * 1024):
                        if chunk:
                            handle.write(chunk)
                            existing += len(chunk)
                            print(
                                f"\r{existing / 2**20:.1f} / "
                                f"{artifact['bytes'] / 2**20:.1f} MiB",
                                end="",
                                flush=True,
                            )
            print()
        except requests.RequestException as error:
            print(f"\nAttempt {attempt} interrupted: {error}")
        if partial.exists() and partial.stat().st_size == artifact["bytes"]:
            actual_digest = digest(partial)
            if not actual_digest.startswith(artifact["sha256_prefix"]):
                raise RuntimeError(
                    f"Weight hash mismatch: {actual_digest}; expected prefix "
                    f"{artifact['sha256_prefix']}"
                )
            partial.replace(destination)
            print(f"Verified and cached: {destination}")
            return 0
        time.sleep(min(attempt, 5))
    raise RuntimeError("Unable to complete pretrained weight download.")


if __name__ == "__main__":
    raise SystemExit(main())
