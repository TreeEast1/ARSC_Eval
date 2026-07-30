"""Build a model-output-blind visual audit for lossless C1 perturbations."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.data import make_benign_perturbation, read_jsonl
from arsc_eval.utils import load_config, resolve_paths, write_json


KINDS = ("brightness", "blur", "noise")
AUDIT_SEED = 20260731
PERTURBATION_SEED = 20260731


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/experiment.yaml")
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--rows-per-page", type=int, default=5)
    parser.add_argument(
        "--output-dir",
        default="outputs/validity/perturbation_semantic_audit",
    )
    return parser.parse_args()


def rooted(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def fit_thumbnail(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    canvas = Image.new("RGB", size, "black")
    copy = image.copy()
    copy.thumbnail(size, Image.Resampling.LANCZOS)
    left = (size[0] - copy.width) // 2
    top = (size[1] - copy.height) // 2
    canvas.paste(copy, (left, top))
    return canvas


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    paths = resolve_paths(config)
    records = read_jsonl(paths["processed_root"] / "test.jsonl")
    if args.samples > len(records):
        raise ValueError("requested more audit samples than available")
    rng = np.random.default_rng(AUDIT_SEED)
    selected_indices = sorted(
        int(value)
        for value in rng.choice(
            len(records), size=args.samples, replace=False
        )
    )
    selected = [records[index] for index in selected_indices]
    output_dir = rooted(args.output_dir)
    page_dir = output_dir / "pages"
    page_dir.mkdir(parents=True, exist_ok=True)
    settings = config["perturbations"]
    transforms = {
        kind: make_benign_perturbation(
            kind,
            float(settings["brightness_factor"]),
            float(settings["blur_radius"]),
            float(settings["noise_std_255"]),
            PERTURBATION_SEED,
        )
        for kind in KINDS
    }

    manifest_path = output_dir / "audit_manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "audit_index",
                "dataset_index",
                "file_name",
                "brightness_semantic_unchanged",
                "blur_semantic_unchanged",
                "noise_semantic_unchanged",
                "review_notes",
            ],
        )
        writer.writeheader()
        for audit_index, (dataset_index, record) in enumerate(
            zip(selected_indices, selected),
            start=1,
        ):
            writer.writerow(
                {
                    "audit_index": audit_index,
                    "dataset_index": dataset_index,
                    "file_name": record["file_name"],
                    "brightness_semantic_unchanged": "",
                    "blur_semantic_unchanged": "",
                    "noise_semantic_unchanged": "",
                    "review_notes": "",
                }
            )

    thumb_size = (320, 180)
    label_height = 24
    columns = ("original", *KINDS)
    image_root = paths["dataset_root"] / "data"
    page_records = []
    for page_start in range(0, len(selected), args.rows_per_page):
        page_number = page_start // args.rows_per_page + 1
        current = selected[page_start : page_start + args.rows_per_page]
        width = len(columns) * thumb_size[0]
        height = label_height + len(current) * (
            thumb_size[1] + label_height
        )
        page = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(page)
        font = ImageFont.load_default()
        for column, name in enumerate(columns):
            draw.text(
                (column * thumb_size[0] + 6, 6),
                name,
                fill="black",
                font=font,
            )
        for row, record in enumerate(current):
            with Image.open(image_root / record["file_name"]) as source:
                original = source.convert("RGB")
            variants = [original]
            variants.extend(
                transforms[kind](original, record["file_name"])
                for kind in KINDS
            )
            y = label_height + row * (thumb_size[1] + label_height)
            for column, variant in enumerate(variants):
                page.paste(
                    fit_thumbnail(variant, thumb_size),
                    (column * thumb_size[0], y),
                )
            audit_index = page_start + row + 1
            label = f"{audit_index:03d} {record['file_name']}"
            draw.text(
                (6, y + thumb_size[1] + 5),
                label,
                fill="black",
                font=font,
            )
        page_path = page_dir / f"page_{page_number:02d}.png"
        page.save(page_path, format="PNG")
        page_records.append(
            {
                "page": page_number,
                "path": str(page_path.relative_to(PROJECT_ROOT)),
                "sha256": sha256_file(page_path),
                "first_audit_index": page_start + 1,
                "last_audit_index": page_start + len(current),
            }
        )

    result = {
        "status": "awaiting_model_output_blind_visual_review",
        "sample_seed": AUDIT_SEED,
        "perturbation_seed": PERTURBATION_SEED,
        "samples": len(selected),
        "same_images_for_each_perturbation": True,
        "in_memory_transform_no_jpeg_reencoding": True,
        "parameters": {
            "brightness_factor": float(settings["brightness_factor"]),
            "gaussian_blur_radius": float(settings["blur_radius"]),
            "gaussian_noise_std_255": float(settings["noise_std_255"]),
        },
        "manifest": str(manifest_path.relative_to(PROJECT_ROOT)),
        "manifest_sha256": sha256_file(manifest_path),
        "pages": page_records,
        "gate": {
            "minimum_samples": 100,
            "minimum_semantic_unchanged_rate_overall_and_each": 0.95,
        },
    }
    write_json(output_dir / "build_summary.json", result)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
