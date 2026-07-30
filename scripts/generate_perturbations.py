"""Materialize the three permitted benign perturbations for the test split."""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.data import deterministic_noise, read_jsonl
from arsc_eval.utils import load_config, resolve_paths, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/experiment.yaml")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    paths = resolve_paths(config)
    settings = config["perturbations"]
    records = read_jsonl(paths["processed_root"] / "test.jsonl")
    image_root = paths["dataset_root"] / "data"
    perturbation_root = paths["processed_root"] / "perturbations"
    seed = int(config["seed"])
    jpeg_quality = int(settings["jpeg_quality"])

    def transform_one(kind: str, record: dict) -> dict:
        source_path = image_root / record["file_name"]
        destination = perturbation_root / kind / record["file_name"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        if args.force or not destination.exists():
            with Image.open(source_path) as source:
                image = source.convert("RGB")
            if kind == "brightness":
                image = ImageEnhance.Brightness(image).enhance(
                    float(settings["brightness_factor"])
                )
            elif kind == "blur":
                image = image.filter(
                    ImageFilter.GaussianBlur(
                        radius=float(settings["blur_radius"])
                    )
                )
            elif kind == "noise":
                image = deterministic_noise(
                    image,
                    record["file_name"],
                    float(settings["noise_std_255"]),
                    seed,
                )
            else:
                raise ValueError(kind)
            image.save(destination, quality=jpeg_quality, subsampling=0)
        output = dict(record)
        output["perturbed_path"] = str(destination.relative_to(PROJECT_ROOT))
        return output

    summary = {
        "split": "official test (valid four-action samples)",
        "samples_per_perturbation": len(records),
        "perturbations": {},
    }
    for kind in ("brightness", "blur", "noise"):
        with ThreadPoolExecutor(max_workers=int(settings["workers"])) as pool:
            transformed_records = list(
                pool.map(lambda item: transform_one(kind, item), records)
            )
        manifest = perturbation_root / f"{kind}.jsonl"
        with manifest.open("w", encoding="utf-8") as handle:
            for record in transformed_records:
                handle.write(
                    json.dumps(record, separators=(",", ":")) + "\n"
                )
        summary["perturbations"][kind] = {
            "manifest": str(manifest.relative_to(PROJECT_ROOT)),
            "count": len(transformed_records),
        }
    summary["parameters"] = {
        "brightness_factor": float(settings["brightness_factor"]),
        "gaussian_blur_radius": float(settings["blur_radius"]),
        "gaussian_noise_std_255": float(settings["noise_std_255"]),
        "noise_seed": seed,
        "jpeg_quality": jpeg_quality,
    }
    write_json(paths["output_dir"] / "perturbation_generation.json", summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

