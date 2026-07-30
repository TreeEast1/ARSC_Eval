"""Create a deterministic stratified manual-audit pack for masks_v2."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.data import read_jsonl
from arsc_eval.utils import write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        default="data/processed/masks_v2/manifest.jsonl",
    )
    parser.add_argument(
        "--output-dir", default="outputs/validity/mask_audit_v2"
    )
    parser.add_argument("--fraction", type=float, default=0.10)
    parser.add_argument("--minimum-per-class", type=int, default=10)
    parser.add_argument("--rows-per-page", type=int, default=5)
    parser.add_argument(
        "--exclude-sample-manifest",
        action="append",
        default=[],
        help=(
            "Optional prior audit JSONL whose file names must not be sampled. "
            "Repeat the flag to exclude multiple independent audit rounds."
        ),
    )
    return parser.parse_args()


def rooted(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else PROJECT_ROOT / value


def evenly_spaced(records: list[dict], count: int) -> list[dict]:
    ordered = sorted(
        records,
        key=lambda record: (
            float(record["detector_confidence"]),
            record["file_name"],
        ),
    )
    if count >= len(ordered):
        return ordered
    indices = np.linspace(0, len(ordered) - 1, count)
    return [ordered[int(round(index))] for index in indices]


def stratified_sample(
    records: list[dict], fraction: float, minimum: int
) -> list[dict]:
    by_class: dict[str, list[dict]] = {}
    for record in records:
        by_class.setdefault(record["detected_class"], []).append(record)
    sampled = []
    for class_name in sorted(by_class):
        group = by_class[class_name]
        count = min(
            len(group),
            max(minimum, int(math.ceil(fraction * len(group)))),
        )
        sampled.extend(evenly_spaced(group, count))
    return sorted(
        sampled, key=lambda record: (record["detected_class"], record["file_name"])
    )


def draw_box(
    draw: ImageDraw.ImageDraw,
    box: list[int] | tuple[int, int, int, int],
    color: tuple[int, int, int],
    width: int = 5,
) -> None:
    draw.rectangle(tuple(box), outline=color, width=width)


def fit_panel(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    panel = Image.new("RGB", size, "white")
    copy = image.copy()
    copy.thumbnail(size, Image.Resampling.LANCZOS)
    left = (size[0] - copy.width) // 2
    top = (size[1] - copy.height) // 2
    panel.paste(copy, (left, top))
    return panel


def context_panel(
    image: Image.Image,
    box: list[int],
    color: tuple[int, int, int],
    size: tuple[int, int],
) -> Image.Image:
    left, top, right, bottom = box
    box_width = right - left
    box_height = bottom - top
    context_width = max(160, box_width * 5)
    context_height = max(120, box_height * 5)
    center_x = (left + right) / 2
    center_y = (top + bottom) / 2
    crop_left = max(0, int(round(center_x - context_width / 2)))
    crop_top = max(0, int(round(center_y - context_height / 2)))
    crop_right = min(image.width, crop_left + context_width)
    crop_bottom = min(image.height, crop_top + context_height)
    crop_left = max(0, crop_right - context_width)
    crop_top = max(0, crop_bottom - context_height)
    crop = image.crop((crop_left, crop_top, crop_right, crop_bottom))
    crop_draw = ImageDraw.Draw(crop)
    draw_box(
        crop_draw,
        [
            left - crop_left,
            top - crop_top,
            right - crop_left,
            bottom - crop_top,
        ],
        color,
        width=max(2, int(round(max(crop.width, crop.height) / 100))),
    )
    return fit_panel(crop, size)


def build_row(record: dict, width: int = 1160, height: int = 320) -> Image.Image:
    image = Image.open(rooted(record["clean_path"])).convert("RGB")
    full = image.copy()
    draw = ImageDraw.Draw(full)
    draw_box(draw, record["critical_box_xyxy"], (220, 30, 30))
    draw_box(draw, record["noncritical_box_xyxy"], (30, 80, 230))
    panels = (
        fit_panel(full, (520, 260)),
        context_panel(
            image, record["critical_box_xyxy"], (220, 30, 30), (300, 260)
        ),
        context_panel(
            image,
            record["noncritical_box_xyxy"],
            (30, 80, 230),
            (300, 260),
        ),
    )
    row = Image.new("RGB", (width, height), "white")
    x = 10
    for panel in panels:
        row.paste(panel, (x, 50))
        x += panel.width + 10
    title = (
        f"{record['file_name']} | class={record['detected_class']} | "
        f"rationale={','.join(record['localized_rationales'])} | "
        f"conf={record['detector_confidence']:.3f} | "
        f"offset={record['control_matching']['center_offset_norm']:.3f}"
    )
    ImageDraw.Draw(row).text((12, 12), title, fill="black")
    return row


def write_pages(
    sampled: list[dict], output_dir: Path, rows_per_page: int
) -> list[str]:
    pages_dir = output_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    page_paths = []
    for start in range(0, len(sampled), rows_per_page):
        rows = [
            build_row(record)
            for record in sampled[start : start + rows_per_page]
        ]
        page = Image.new("RGB", (1160, 320 * len(rows)), "white")
        for index, row in enumerate(rows):
            page.paste(row, (0, index * 320))
        page_path = pages_dir / f"page_{start // rows_per_page + 1:03d}.png"
        page.save(page_path)
        page_paths.append(str(page_path.relative_to(PROJECT_ROOT)))
    return page_paths


def main() -> int:
    args = parse_args()
    manifest = rooted(args.manifest)
    output_dir = rooted(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    records = read_jsonl(manifest)
    excluded_file_names: set[str] = set()
    if args.exclude_sample_manifest:
        for prior_manifest in args.exclude_sample_manifest:
            excluded_file_names.update(
                record["file_name"]
                for record in read_jsonl(rooted(prior_manifest))
            )
        records_for_sampling = [
            record
            for record in records
            if record["file_name"] not in excluded_file_names
        ]
    else:
        records_for_sampling = records
    sampled = stratified_sample(
        records_for_sampling,
        float(args.fraction),
        int(args.minimum_per_class),
    )

    sample_manifest = output_dir / "sample_manifest.jsonl"
    with sample_manifest.open("w", encoding="utf-8") as handle:
        for index, record in enumerate(sampled, start=1):
            handle.write(
                json.dumps(
                    {"audit_id": index, **record},
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            )

    review_path = output_dir / "manual_review.csv"
    with review_path.open("w", newline="", encoding="utf-8") as handle:
        columns = [
            "Audit_ID",
            "File_Name",
            "Detected_Class",
            "Localized_Rationales",
            "Critical_Binding_Correct",
            "Control_Free_Of_Critical_Evidence",
            "Semantic_Label_Unchanged",
            "Notes",
        ]
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for index, record in enumerate(sampled, start=1):
            writer.writerow(
                {
                    "Audit_ID": index,
                    "File_Name": record["file_name"],
                    "Detected_Class": record["detected_class"],
                    "Localized_Rationales": ";".join(
                        record["localized_rationales"]
                    ),
                    "Critical_Binding_Correct": "",
                    "Control_Free_Of_Critical_Evidence": "",
                    "Semantic_Label_Unchanged": "",
                    "Notes": "",
                }
            )

    page_paths = write_pages(sampled, output_dir, args.rows_per_page)
    class_population = Counter(
        record["detected_class"] for record in records
    )
    class_sample = Counter(record["detected_class"] for record in sampled)
    offsets = np.asarray(
        [
            record["control_matching"]["center_offset_norm"]
            for record in records
        ],
        dtype=np.float64,
    )
    y_offsets = np.asarray(
        [
            record["control_matching"]["y_center_offset_norm"]
            for record in records
        ],
        dtype=np.float64,
    )
    area_ratios = np.asarray(
        [record["control_matching"]["area_ratio"] for record in records],
        dtype=np.float64,
    )
    summary = {
        "manifest": str(manifest.relative_to(PROJECT_ROOT)),
        "population_pairs": len(records),
        "sample_pairs": len(sampled),
        "prior_audit_excluded_file_names": len(excluded_file_names),
        "sampling": (
            f"{100.0 * float(args.fraction):g}% per detected class with at "
            f"least {int(args.minimum_per_class)} when available; "
            "confidence-sorted evenly spaced selection after prior-audit "
            "filename exclusions"
        ),
        "population_by_class": dict(class_population),
        "sample_by_class": dict(class_sample),
        "automated_checks": {
            "exact_area_match_rate": float(
                np.isclose(area_ratios, 1.0).mean()
            ),
            "control_detector_overlap_rate": 0.0,
            "control_detector_overlap_basis": (
                "generator rejects any pixel intersection with all retained "
                "detector boxes"
            ),
            "center_offset_median": float(np.median(offsets)),
            "center_offset_p95": float(np.quantile(offsets, 0.95)),
            "vertical_offset_median": float(np.median(y_offsets)),
            "vertical_offset_p95": float(np.quantile(y_offsets, 0.95)),
        },
        "manual_review_file": str(review_path.relative_to(PROJECT_ROOT)),
        "pages": page_paths,
        "manual_status": "pending",
        "acceptance_thresholds": {
            "critical_binding_correct_rate_minimum": 0.90,
            "control_critical_evidence_contamination_rate_maximum": 0.05,
            "semantic_label_unchanged_rate_minimum": 0.95,
        },
    }
    write_json(output_dir / "audit_summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
