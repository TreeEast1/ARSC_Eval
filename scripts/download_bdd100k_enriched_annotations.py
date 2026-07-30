"""Fetch only BDD100K annotations needed by the BDD-OIA test manifest.

The public ``lance-format/BDD100K-enriched`` mirror exposes BDD100K train and
validation labels through the Hugging Face Dataset Viewer API.  Querying by
``image_id`` avoids downloading image bytes, embeddings, or unrelated rows.
The saved artifact contains annotation metadata only.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_URL = "https://datasets-server.huggingface.co/filter"
HUB_API_URL = "https://huggingface.co/api/datasets"
DATASET = "lance-format/BDD100K-enriched"
CONFIG = "default"
SPLIT = "train"
EXPECTED_DATASET_REVISION = "d82c5188d392714ba8091d68014f7b9838ceadf2"
KEEP_FIELDS = (
    "image_id",
    "split",
    "width",
    "height",
    "ann_categories",
    "ann_bboxes",
    "ann_occluded",
    "ann_truncated",
    "ann_traffic_light_colors",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bdd-oia-manifest", default="data/processed/test.jsonl"
    )
    parser.add_argument(
        "--output",
        default=(
            "data/external/bdd100k/"
            "bdd100k_enriched_annotations_for_bdd_oia.json"
        ),
    )
    parser.add_argument("--batch-size", type=int, default=40)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--retries", type=int, default=8)
    parser.add_argument(
        "--expected-dataset-revision",
        default=EXPECTED_DATASET_REVISION,
        help=(
            "Abort unless the public metadata mirror resolves to this exact "
            "Git revision before and after the download."
        ),
    )
    return parser.parse_args()


def rooted(path: str) -> Path:
    value = Path(path)
    return value if value.is_absolute() else PROJECT_ROOT / value


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def keyframe_ids(records: list[dict]) -> list[str]:
    """Return unique BDD100K keyframe IDs, excluding BDD-OIA _1/_3 frames."""
    ids = []
    for record in records:
        stem = Path(record["file_name"]).stem
        if stem.endswith(("_1", "_3")):
            continue
        ids.append(stem)
    return sorted(set(ids))


def filter_url(image_ids: list[str]) -> str:
    if not image_ids:
        raise ValueError("image_ids cannot be empty")
    if any("'" in image_id for image_id in image_ids):
        raise ValueError("unexpected quote in image ID")
    predicate = " OR ".join(
        f'"image_id" = \'{image_id}\'' for image_id in image_ids
    )
    parameters = {
        "dataset": DATASET,
        "config": CONFIG,
        "split": SPLIT,
        "where": predicate,
        "offset": 0,
        "length": 100,
    }
    return f"{API_URL}?{urllib.parse.urlencode(parameters)}"


def resolve_dataset_revision(timeout: float) -> str:
    url = f"{HUB_API_URL}/{DATASET}/revision/main"
    request = urllib.request.Request(
        url, headers={"User-Agent": "ARSC-Eval/1.0"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    revision = str(payload.get("sha", ""))
    if len(revision) != 40:
        raise RuntimeError("dataset mirror returned an invalid Git revision")
    return revision


def fetch_batch(
    image_ids: list[str], timeout: float, retries: int
) -> list[dict]:
    url = filter_url(image_ids)
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "ARSC-Eval/1.0"}
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.load(response)
            if payload.get("num_rows_total", 0) > 100:
                raise RuntimeError("filter returned more than 100 rows")
            rows = []
            for item in payload.get("rows", []):
                row = item["row"]
                rows.append({field: row[field] for field in KEEP_FIELDS})
            return rows
        except Exception as error:  # network/API errors are transient
            last_error = error
            if attempt + 1 < retries:
                time.sleep(min(2**attempt, 30))
    raise RuntimeError(f"failed to fetch batch after {retries} attempts") from last_error


def write_checkpoint(
    output_path: Path,
    requested_ids: list[str],
    rows_by_id: dict[str, dict],
    completed_batches: int,
    resolved_revision: str,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": {
            "dataset": DATASET,
            "config": CONFIG,
            "api_split": SPLIT,
            "api_endpoint": API_URL,
            "official_annotation_release": (
                "BDD100K Detection 2020 train annotations"
            ),
            "official_format_documentation": (
                "https://github.com/bdd100k/bdd100k/blob/master/"
                "doc/format.md"
            ),
            "repository": (
                "https://huggingface.co/datasets/"
                "lance-format/BDD100K-enriched"
            ),
            "resolved_repository_revision": resolved_revision,
            "access_note": (
                "The public mirror is used only as a metadata transport for "
                "BDD100K object annotations; no image bytes or embeddings are "
                "retained."
            ),
        },
        "requested_keyframe_ids": len(requested_ids),
        "matched_rows": len(rows_by_id),
        "completed_batches": completed_batches,
        "complete": False,
        "rows": [rows_by_id[key] for key in sorted(rows_by_id)],
    }
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(output_path)


def main() -> int:
    args = parse_args()
    if not 1 <= args.batch_size <= 100:
        raise ValueError("batch size must be between 1 and 100")
    records = read_jsonl(rooted(args.bdd_oia_manifest))
    requested_ids = keyframe_ids(records)
    if args.limit is not None:
        requested_ids = requested_ids[: args.limit]

    output_path = rooted(args.output)
    resolved_revision = resolve_dataset_revision(args.timeout)
    if resolved_revision != args.expected_dataset_revision:
        raise RuntimeError(
            "dataset mirror revision mismatch before download: "
            f"expected {args.expected_dataset_revision}, "
            f"observed {resolved_revision}"
        )
    rows_by_id: dict[str, dict] = {}
    completed_batches = 0
    if output_path.exists():
        existing = json.loads(output_path.read_text(encoding="utf-8"))
        existing_revision = existing.get("source", {}).get(
            "resolved_repository_revision"
        )
        if existing.get("rows") and existing_revision != resolved_revision:
            raise RuntimeError(
                "existing checkpoint was produced from a different or "
                "unrecorded dataset revision"
            )
        rows_by_id = {
            row["image_id"]: row for row in existing.get("rows", [])
        }
        if existing.get("complete") and set(rows_by_id) == set(requested_ids):
            print(json.dumps(existing, indent=2, ensure_ascii=False))
            return 0

    total_batches = (
        len(requested_ids) + args.batch_size - 1
    ) // args.batch_size
    for start in range(0, len(requested_ids), args.batch_size):
        batch = requested_ids[start : start + args.batch_size]
        if all(image_id in rows_by_id for image_id in batch):
            completed_batches += 1
            continue
        rows = fetch_batch(batch, args.timeout, args.retries)
        for row in rows:
            rows_by_id[row["image_id"]] = row
        completed_batches += 1
        write_checkpoint(
            output_path,
            requested_ids,
            rows_by_id,
            completed_batches,
            resolved_revision,
        )
        print(
            json.dumps(
                {
                    "batch": completed_batches,
                    "total_batches": total_batches,
                    "queried": min(start + len(batch), len(requested_ids)),
                    "matched": len(rows_by_id),
                }
            ),
            flush=True,
        )

    final_revision = resolve_dataset_revision(args.timeout)
    if final_revision != resolved_revision:
        raise RuntimeError(
            "dataset mirror revision changed during download: "
            f"{resolved_revision} -> {final_revision}"
        )
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    payload["complete"] = True
    payload["completed_batches"] = total_batches
    payload["source"]["post_download_repository_revision"] = final_revision
    payload["unmatched_keyframe_ids"] = sorted(
        set(requested_ids).difference(rows_by_id)
    )
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(output_path)
    print(
        json.dumps(
            {
                "requested_keyframe_ids": len(requested_ids),
                "matched_rows": len(rows_by_id),
                "unmatched": len(payload["unmatched_keyframe_ids"]),
                "output": str(output_path),
                "complete": True,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
