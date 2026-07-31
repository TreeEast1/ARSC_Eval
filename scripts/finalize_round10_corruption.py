"""Create the immutable Round 10 artifact index after tmux exits."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FINAL_DIR = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round10_corruption_formal_attempt01"
)
STAGING_DIR = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round10_corruption_formal_attempt01.staging"
)
LOG_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round10_corruption_formal_attempt01.log"
)
INDEX_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round10_corruption_artifact_index.json"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def relative(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def main() -> int:
    require(not INDEX_PATH.exists(), "artifact index already exists")
    require(not STAGING_DIR.exists(), "staging directory remains; run is inconclusive")
    require(FINAL_DIR.is_dir(), "formal final directory is absent")
    require(LOG_PATH.is_file(), "formal tmux log is absent")
    log = LOG_PATH.read_text(encoding="utf-8", errors="replace")
    exit_codes = [
        line.strip() for line in log.splitlines() if line.startswith("EXIT_CODE=")
    ]
    require(exit_codes == ["EXIT_CODE=0"], f"formal exit marker differs: {exit_codes}")
    result_path = FINAL_DIR / "round10_corruption_results.json"
    require(result_path.is_file(), "formal result JSON is absent")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    require(
        result["schema_version"] == "ARSC_ROUND10_CORRUPTION_RESULTS_V1"
        and result["status"] == "COMPLETE"
        and result["formal_run"] is True
        and result["attempt"] == "attempt01",
        "formal result completion contract differs",
    )
    files = sorted(path for path in FINAL_DIR.rglob("*") if path.is_file())
    require(len(files) == 10, f"formal artifact file count differs: {len(files)}")
    bindings = {
        relative(path): {
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
        for path in files
    }
    bindings[relative(LOG_PATH)] = {
        "sha256": sha256_file(LOG_PATH),
        "bytes": LOG_PATH.stat().st_size,
    }
    index: dict[str, Any] = {
        "schema_version": "ARSC_ROUND10_ARTIFACT_INDEX_V1",
        "generated_at_utc": utc_now(),
        "formal_run": True,
        "attempt": "attempt01",
        "status": "COMPLETE_HASH_BOUND",
        "result_verdict": result["verdict"],
        "file_count_including_log": len(bindings),
        "files": bindings,
        "result_json_written_last_before_atomic_rename": True,
        "tmux_exit_code": 0,
    }
    temporary = INDEX_PATH.with_name(INDEX_PATH.name + ".tmp")
    require(not temporary.exists(), "artifact-index temporary file already exists")
    temporary.write_text(
        json.dumps(index, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, INDEX_PATH)
    print(
        json.dumps(
            {
                "status": index["status"],
                "result_verdict": index["result_verdict"],
                "indexed_files": len(bindings),
                "index_sha256": sha256_file(INDEX_PATH),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
