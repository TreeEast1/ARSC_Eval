"""Pre-result amendment check for Windows multi-worker perturbation loading."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.data import make_benign_perturbation
from arsc_eval.engine import make_loader
from arsc_eval.utils import load_config, resolve_paths, write_json


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def main() -> int:
    config = load_config(PROJECT_ROOT / "configs" / "rq1_seed43.yaml")
    paths = resolve_paths(config)
    settings = config["perturbations"]
    results = {}
    for kind in ("brightness", "blur", "noise"):
        transform = make_benign_perturbation(
            kind,
            float(settings["brightness_factor"]),
            float(settings["blur_radius"]),
            float(settings["noise_std_255"]),
            int(settings["noise_seed"]),
        )
        loader = make_loader(
            paths["processed_root"] / "test.jsonl",
            paths["dataset_root"] / "data",
            int(config["image_size"]),
            16,
            8,
            shuffle=False,
            limit=32,
            pil_transform=transform,
        )
        batches = list(loader)
        images = np.concatenate(
            [batch["image"].numpy() for batch in batches], axis=0
        )
        names = [
            str(name) for batch in batches for name in batch["file_name"]
        ]
        results[kind] = {
            "samples": len(names),
            "file_names": names,
            "tensor_shape": list(images.shape),
            "tensor_sha256": sha256_bytes(images.tobytes()),
            "finite": bool(np.isfinite(images).all()),
        }
    result = {
        "status": "pre_result_engineering_amendment_check",
        "platform": "Windows spawn DataLoader",
        "num_workers": 8,
        "all_conditions_passed": all(
            value["samples"] == 32 and value["finite"]
            for value in results.values()
        ),
        "conditions": results,
    }
    output = (
        PROJECT_ROOT
        / "outputs"
        / "validity"
        / "rq1_amendment01_worker_check.json"
    )
    write_json(output, result)
    print(json.dumps(result, indent=2))
    return 0 if result["all_conditions_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
