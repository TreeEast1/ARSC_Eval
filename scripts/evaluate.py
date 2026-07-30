"""Compute exactly the requested Accuracy, Rationale, Safety, Consistency metrics."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.constants import ACTION_NAMES, RATIONALE_NAMES
from arsc_eval.engine import make_loader, predict, sigmoid_numpy
from arsc_eval.metrics import (
    action_flip_rate,
    multilabel_f1,
    rationale_jaccard,
    risk_coverage,
)
from arsc_eval.models import load_checkpoint_model
from arsc_eval.utils import (
    device_from_arg,
    json_safe,
    load_config,
    resolve_paths,
    write_json,
)


MODEL_ACTION = "Action-Only"
MODEL_JOINT = "Joint Action-Rationale"
MODEL_CALIBRATED = "Joint-Calibrated"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/experiment.yaml")
    parser.add_argument(
        "--action-checkpoint",
        default="checkpoints/action_only_best_action.pt",
    )
    parser.add_argument(
        "--joint-checkpoint", default="checkpoints/joint_best_action.pt"
    )
    parser.add_argument(
        "--calibration", default="outputs/calibration.json"
    )
    parser.add_argument("--device", default="auto")
    return parser.parse_args()


def rooted(path: str) -> Path:
    value = Path(path)
    return value if value.is_absolute() else PROJECT_ROOT / value


def make_eval_loader(
    config: dict,
    manifest: Path,
    image_root: Path,
    path_key: str = "file_name",
):
    return make_loader(
        manifest,
        image_root,
        int(config["image_size"]),
        int(config["training"]["batch_size"]),
        int(config["training"]["num_workers"]),
        shuffle=False,
        path_key=path_key,
    )


def correct_action_probability(
    targets: np.ndarray, probabilities: np.ndarray
) -> np.ndarray:
    positive = targets > 0.5
    counts = positive.sum(axis=1)
    if np.any(counts == 0):
        raise ValueError("Causal-evidence input has an empty action label.")
    return (probabilities * positive).sum(axis=1) / counts


def causal_gap(
    targets: np.ndarray,
    clean: np.ndarray,
    critical: np.ndarray,
    noncritical: np.ndarray,
) -> dict[str, Any]:
    clean_correct = correct_action_probability(targets, clean)
    critical_correct = correct_action_probability(targets, critical)
    noncritical_correct = correct_action_probability(targets, noncritical)
    delta_critical = clean_correct - critical_correct
    delta_noncritical = clean_correct - noncritical_correct
    gap = delta_critical - delta_noncritical
    return {
        "samples": len(targets),
        "mean_delta_critical": float(delta_critical.mean()),
        "mean_delta_noncritical": float(delta_noncritical.mean()),
        "mean_causal_evidence_gap": float(gap.mean()),
        "multiple_correct_action_policy": (
            "mean probability over all positive ground-truth actions"
        ),
    }


def compact_metric(metric: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in metric.items()
        if key != "risk_coverage_curve" and key != "ece_bins"
    }


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    paths = resolve_paths(config)
    device = device_from_arg(args.device)
    amp = bool(config["training"]["amp"])
    threshold = float(config["training"]["threshold"])
    output_dir = paths["output_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)

    action_model = load_checkpoint_model(
        str(rooted(args.action_checkpoint)), "action_only", device
    )
    joint_model = load_checkpoint_model(
        str(rooted(args.joint_checkpoint)), "joint", device
    )
    calibration = json.loads(
        rooted(args.calibration).read_text(encoding="utf-8")
    )
    temperature = float(calibration["temperature"])

    test_manifest = paths["processed_root"] / "test.jsonl"
    clean_loader = make_eval_loader(
        config, test_manifest, paths["dataset_root"] / "data"
    )
    clean_action = predict(action_model, clean_loader, device, amp=amp)
    clean_joint = predict(joint_model, clean_loader, device, amp=amp)
    action_targets = clean_action["action_targets"]
    rationale_targets = clean_joint["rationale_targets"]
    action_probabilities = sigmoid_numpy(clean_action["action_logits"])
    joint_action_probabilities = sigmoid_numpy(
        clean_joint["action_logits"]
    )
    calibrated_action_probabilities = sigmoid_numpy(
        clean_joint["action_logits"], temperature=temperature
    )
    joint_rationale_probabilities = sigmoid_numpy(
        clean_joint["rationale_logits"]
    )

    action_f1 = {
        MODEL_ACTION: multilabel_f1(
            action_targets,
            action_probabilities,
            ACTION_NAMES,
            threshold,
        ),
        MODEL_JOINT: multilabel_f1(
            action_targets,
            joint_action_probabilities,
            ACTION_NAMES,
            threshold,
        ),
        MODEL_CALIBRATED: multilabel_f1(
            action_targets,
            calibrated_action_probabilities,
            ACTION_NAMES,
            threshold,
        ),
    }
    rationale_f1 = {
        MODEL_JOINT: multilabel_f1(
            rationale_targets,
            joint_rationale_probabilities,
            RATIONALE_NAMES,
            threshold,
        ),
        MODEL_CALIBRATED: multilabel_f1(
            rationale_targets,
            joint_rationale_probabilities,
            RATIONALE_NAMES,
            threshold,
        ),
    }
    clean_metrics = {
        "split": "official test (valid four-action samples)",
        "samples": len(action_targets),
        "models": {
            name: {"action": metric}
            for name, metric in action_f1.items()
        },
    }
    write_json(output_dir / "clean_metrics.json", json_safe(clean_metrics))
    write_json(
        output_dir / "rationale_metrics.json",
        json_safe(
            {
                "split": "official test (valid four-action samples)",
                "samples": len(rationale_targets),
                "models": {
                    name: {"rationale": metric}
                    for name, metric in rationale_f1.items()
                },
            }
        ),
    )

    safety = {
        MODEL_ACTION: risk_coverage(
            action_targets, action_probabilities, threshold
        ),
        MODEL_JOINT: risk_coverage(
            action_targets, joint_action_probabilities, threshold
        ),
        MODEL_CALIBRATED: risk_coverage(
            action_targets, calibrated_action_probabilities, threshold
        ),
    }
    safety_metrics = {
        "split": "official test (valid four-action samples)",
        "samples": len(action_targets),
        "temperature": {
            MODEL_ACTION: 1.0,
            MODEL_JOINT: 1.0,
            MODEL_CALIBRATED: temperature,
        },
        "models": safety,
    }
    write_json(
        output_dir / "safety_metrics.json", json_safe(safety_metrics)
    )

    mask_manifest = paths["processed_root"] / "masks" / "manifest.jsonl"
    clean_mask_loader = make_eval_loader(
        config, mask_manifest, PROJECT_ROOT, "clean_path"
    )
    critical_loader = make_eval_loader(
        config, mask_manifest, PROJECT_ROOT, "critical_path"
    )
    noncritical_loader = make_eval_loader(
        config, mask_manifest, PROJECT_ROOT, "noncritical_path"
    )
    mask_clean = predict(joint_model, clean_mask_loader, device, amp=amp)
    mask_critical = predict(joint_model, critical_loader, device, amp=amp)
    mask_noncritical = predict(
        joint_model, noncritical_loader, device, amp=amp
    )
    mask_targets = mask_clean["action_targets"]
    mask_clean_joint = sigmoid_numpy(mask_clean["action_logits"])
    mask_critical_joint = sigmoid_numpy(mask_critical["action_logits"])
    mask_noncritical_joint = sigmoid_numpy(mask_noncritical["action_logits"])
    critical_metrics = {
        "mask_generation": json.loads(
            (output_dir / "critical_mask_generation.json").read_text(
                encoding="utf-8"
            )
        ),
        "models": {
            MODEL_JOINT: causal_gap(
                mask_targets,
                mask_clean_joint,
                mask_critical_joint,
                mask_noncritical_joint,
            ),
            MODEL_CALIBRATED: causal_gap(
                mask_targets,
                sigmoid_numpy(mask_clean["action_logits"], temperature),
                sigmoid_numpy(mask_critical["action_logits"], temperature),
                sigmoid_numpy(
                    mask_noncritical["action_logits"], temperature
                ),
            ),
        },
    }
    write_json(
        output_dir / "critical_mask_metrics.json",
        json_safe(critical_metrics),
    )

    perturbation_metrics: dict[str, dict[str, Any]] = {}
    for kind in ("brightness", "blur", "noise"):
        manifest = (
            paths["processed_root"] / "perturbations" / f"{kind}.jsonl"
        )
        loader = make_eval_loader(
            config, manifest, PROJECT_ROOT, "perturbed_path"
        )
        perturbed_action = predict(
            action_model, loader, device, amp=amp
        )
        perturbed_joint = predict(joint_model, loader, device, amp=amp)
        action_probs = sigmoid_numpy(perturbed_action["action_logits"])
        joint_action_probs = sigmoid_numpy(
            perturbed_joint["action_logits"]
        )
        calibrated_probs = sigmoid_numpy(
            perturbed_joint["action_logits"], temperature
        )
        rationale_probs = sigmoid_numpy(
            perturbed_joint["rationale_logits"]
        )
        perturbation_metrics[kind] = {
            MODEL_ACTION: {
                "action_flip_rate": action_flip_rate(
                    action_probabilities, action_probs, threshold
                ),
                "rationale_jaccard": None,
            },
            MODEL_JOINT: {
                "action_flip_rate": action_flip_rate(
                    joint_action_probabilities,
                    joint_action_probs,
                    threshold,
                ),
                "rationale_jaccard": rationale_jaccard(
                    joint_rationale_probabilities,
                    rationale_probs,
                    threshold,
                ),
            },
            MODEL_CALIBRATED: {
                "action_flip_rate": action_flip_rate(
                    calibrated_action_probabilities,
                    calibrated_probs,
                    threshold,
                ),
                "rationale_jaccard": rationale_jaccard(
                    joint_rationale_probabilities,
                    rationale_probs,
                    threshold,
                ),
            },
        }

    consistency_average = {}
    for model_name in (MODEL_ACTION, MODEL_JOINT, MODEL_CALIBRATED):
        flip_values = [
            perturbation_metrics[kind][model_name]["action_flip_rate"]
            for kind in ("brightness", "blur", "noise")
        ]
        jaccard_values = [
            perturbation_metrics[kind][model_name]["rationale_jaccard"]
            for kind in ("brightness", "blur", "noise")
            if perturbation_metrics[kind][model_name][
                "rationale_jaccard"
            ]
            is not None
        ]
        consistency_average[model_name] = {
            "action_flip_rate": float(np.mean(flip_values)),
            "rationale_jaccard": (
                float(np.mean(jaccard_values))
                if jaccard_values
                else None
            ),
        }
    consistency_metrics = {
        "samples_per_perturbation": len(action_targets),
        "threshold": threshold,
        "by_perturbation": perturbation_metrics,
        "mean_over_three_perturbations": consistency_average,
    }
    write_json(
        output_dir / "consistency_metrics.json",
        json_safe(consistency_metrics),
    )

    critical_by_model = critical_metrics["models"]
    rows = []
    for model_name in (MODEL_ACTION, MODEL_JOINT, MODEL_CALIBRATED):
        row = {
            "Model": model_name,
            "Action_Macro_F1": action_f1[model_name]["macro_f1"],
            "Rationale_Macro_F1": (
                rationale_f1[model_name]["macro_f1"]
                if model_name in rationale_f1
                else "N/A"
            ),
            "Causal_Evidence_Gap": (
                critical_by_model[model_name][
                    "mean_causal_evidence_gap"
                ]
                if model_name in critical_by_model
                else "N/A"
            ),
            "AURC": safety[model_name]["aurc"],
            "Unsafe_Acceptance_Rate_90": safety[model_name][
                "unsafe_acceptance_rate_90"
            ],
            "ECE": safety[model_name]["ece"],
            "Action_Flip_Rate": consistency_average[model_name][
                "action_flip_rate"
            ],
            "Rationale_Jaccard": (
                consistency_average[model_name]["rationale_jaccard"]
                if consistency_average[model_name]["rationale_jaccard"]
                is not None
                else "N/A"
            ),
        }
        rows.append(row)
    main_columns = [
        "Model",
        "Action_Macro_F1",
        "Rationale_Macro_F1",
        "Causal_Evidence_Gap",
        "AURC",
        "Unsafe_Acceptance_Rate_90",
        "ECE",
        "Action_Flip_Rate",
        "Rationale_Jaccard",
    ]
    with (output_dir / "main_results.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=main_columns)
        writer.writeheader()
        writer.writerows(rows)

    with (output_dir / "per_class_results.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        fieldnames = ["Model", "Dimension", "Class", "F1"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for model_name, metrics in action_f1.items():
            for class_name, value in metrics["per_class_f1"].items():
                writer.writerow(
                    {
                        "Model": model_name,
                        "Dimension": "Action",
                        "Class": class_name,
                        "F1": value,
                    }
                )
        for model_name, metrics in rationale_f1.items():
            for class_name, value in metrics["per_class_f1"].items():
                writer.writerow(
                    {
                        "Model": model_name,
                        "Dimension": "Rationale",
                        "Class": class_name,
                        "F1": value,
                    }
                )

    data_summary = json.loads(
        (output_dir / "data_summary.json").read_text(encoding="utf-8")
    )
    action_difference = abs(
        action_f1[MODEL_ACTION]["macro_f1"]
        - action_f1[MODEL_JOINT]["macro_f1"]
    )
    near_accuracy = action_difference <= 0.03
    flip_difference = (
        consistency_average[MODEL_JOINT]["action_flip_rate"]
        - consistency_average[MODEL_ACTION]["action_flip_rate"]
    )
    rq2_consistency = (
        "改善" if flip_difference < 0 else "未改善"
    )
    table_header = (
        "| Model | Action Macro-F1 | Rationale Macro-F1 | CEG | AURC | "
        "UAR@90 | ECE | Flip Rate | Rationale Jaccard |\n"
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|"
    )

    def cell(value: object) -> str:
        return f"{value:.6f}" if isinstance(value, float) else str(value)

    table_rows = "\n".join(
        "| " + " | ".join(cell(row[column]) for column in main_columns) + " |"
        for row in rows
    )
    summary_text = f"""# BDD-OIA 最小 ARSC-Eval 实验总结

## 1. 数据集获取

成功获取官方 last-frame 归档。SHA-256：`{data_summary["source_archive_sha256"]}`。

## 2. 实际样本数

- 官方：train={data_summary["splits"]["train"]["official_samples"]}，validation={data_summary["splits"]["val"]["official_samples"]}，test={data_summary["splits"]["test"]["official_samples"]}
- 四动作任务有效：train={data_summary["splits"]["train"]["valid_samples"]}，validation={data_summary["splits"]["val"]["valid_samples"]}，test={data_summary["splits"]["test"]["valid_samples"]}
- 缺失/损坏图像：{data_summary["totals"]["missing_images"]}/{data_summary["totals"]["corrupt_images"]}；四动作全空无效样本：{data_summary["totals"]["invalid_samples"]}
- Critical Mask 有效样本：{critical_metrics["mask_generation"]["valid_mask_pairs"]}

## 3. 两个训练模型配置

- Action-Only：ImageNet 预训练 ResNet-50，4 维动作 head，BCE，AdamW。
- Joint Action-Rationale：相同 ResNet-50，共享 backbone，4 维动作 head + 21 维理由 head，`Loss = Action Loss + Rationale Loss`。
- 统一：seed={config["seed"]}，image_size={config["image_size"]}，epochs={config["training"]["epochs"]}，batch_size={config["training"]["batch_size"]}，lr={config["training"]["learning_rate"]}，weight_decay={config["training"]["weight_decay"]}。
- Joint-Calibrated：Joint 最佳 Action-F1 checkpoint；validation 标量温度 T={temperature:.6f}。

## 4. 指标结果

{table_header}
{table_rows}

## 5. RQ1 / RQ2

- RQ1：两个训练模型 Action Macro-F1 差值为 {action_difference:.6f}，按预先用于总结的 0.03 “相近”判据，结果为{"相近" if near_accuracy else "不相近"}。Rationale、Safety、Consistency 的独立列显示了 Accuracy 本身不表达的信息；是否构成“相近准确率下的明显差异”应据上述原始指标判断。
- RQ2：Joint 相对 Action-Only 的平均 Action Flip Rate 差值为 {flip_difference:.6f}，因此轻微扰动稳定性在本次运行中{rq2_consistency}。按任务限制，Causal Evidence Gap 只对 Joint / Joint-Calibrated 计算，故关键证据依赖是否由联合监督“改善”不能与 Action-Only 做直接 CEG 因果对照；报告的是 Joint 的绝对 CEG。

## 6. 当前限制

- 单随机种子、5 epoch 的最小实验，不做超参数搜索。
- 四动作全空的官方 confuse/unknown 条目不进入四动作训练与评估，但在数据统计中保留。
- Critical Mask 使用固定 COCO YOLO11n；generic traffic sign 仅以 stop sign 定位，rider 以 bicycle/motorcycle 定位；无法可靠定位的样本被跳过。
- Benign 输入为固定轻微亮度、Gaussian blur 和 Gaussian noise；物化为 JPEG 会引入轻微重编码差异。
- Safety 的样本错误定义为四标签集合任一位不匹配；置信度严格取四个动作概率最大值。

## 7. 完整复现命令

```powershell
python scripts/download_data.py --data-root data
python scripts/prepare_data.py --config configs/experiment.yaml
python scripts/smoke_test.py --config configs/experiment.yaml --device cuda
python scripts/train_model.py --config configs/experiment.yaml --model action_only --device cuda
python scripts/train_model.py --config configs/experiment.yaml --model joint --device cuda
python scripts/calibrate.py --config configs/experiment.yaml --device cuda
python scripts/generate_masks.py --config configs/experiment.yaml --device 0
python scripts/generate_perturbations.py --config configs/experiment.yaml
python scripts/evaluate.py --config configs/experiment.yaml --device cuda
```
"""
    (output_dir / "experiment_summary.md").write_text(
        summary_text, encoding="utf-8"
    )
    print(json.dumps({"main_results": rows}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
