from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from arsc_eval.corruption_dose_response_v2 import (
    FAMILIES,
    PixelCorruptionV2,
)
from arsc_eval.data import deterministic_noise
from arsc_eval.round10_protocol_validation import (
    EXPECTED_PARAMETERS,
    expected_semantic_keys,
    forbidden_round10_paths,
    validate_amendment_schema,
    validate_bound_local_dependencies,
    validate_page_hash_binding,
    validate_review_decision,
    validate_semantic_raw_rows,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AMENDMENT_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round10_corruption_dose_response_protocol_amendment01.json"
)


def read_amendment() -> dict:
    return json.loads(AMENDMENT_PATH.read_text(encoding="utf-8"))


def valid_decision() -> dict:
    return {
        "schema_version": (
            "ARSC_ROUND10_SEMANTIC_REVIEW_DECISION_AMENDMENT01_V1"
        ),
        "reviewed_all_30_labelled_contact_sheets": True,
        "reviewed_all_1200_pairs_with_displayed_labels": True,
        "bindings": {
            "raw_manifest_sha256": "A",
            "label_sidecar_sha256": "B",
            "row_key_sha256": "C",
        },
        "default_decisions": {
            "action_and_rationale_labels_still_applicable": True,
            "scene_semantics_preserved": True,
        },
        "overrides": [],
    }


def test_v2_level_zero_exact_and_noise_bridge_pixel_exact() -> None:
    fixtures = (
        np.arange(17 * 19 * 3, dtype=np.uint8).reshape(17, 19, 3),
        np.stack(
            [
                np.zeros((13, 11), dtype=np.uint8),
                np.full((13, 11), 255, dtype=np.uint8),
                np.full((13, 11), 128, dtype=np.uint8),
            ],
            axis=-1,
        ),
    )
    for pixels in fixtures:
        image = Image.fromarray(pixels, mode="RGB")
        for family in FAMILIES:
            observed = np.asarray(
                PixelCorruptionV2(family, 0)(image, "identity.jpg")
            )
            assert np.array_equal(observed, pixels)
        for name in ("abc.jpg", "abc_1.jpg", "night-scene_3.jpg"):
            historical = np.asarray(
                deterministic_noise(image, name, 5.0, 20260731)
            )
            amended = np.asarray(
                PixelCorruptionV2("noise", 2)(image, name)
            )
            assert np.array_equal(amended, historical)


def test_v2_noise_is_deterministic_nested_and_seed_frozen() -> None:
    image = Image.fromarray(
        np.full((32, 32, 3), 128, dtype=np.uint8),
        mode="RGB",
    )
    level_one = np.asarray(
        PixelCorruptionV2("noise", 1)(image, "same.jpg"),
        dtype=np.int16,
    )
    level_two = np.asarray(
        PixelCorruptionV2("noise", 2)(image, "same.jpg"),
        dtype=np.int16,
    )
    repeated = np.asarray(
        PixelCorruptionV2("noise", 2)(image, "same.jpg"),
        dtype=np.int16,
    )
    assert np.array_equal(level_two, repeated)
    assert np.max(np.abs((level_two - 128) - 2 * (level_one - 128))) <= 1
    with pytest.raises(ValueError):
        PixelCorruptionV2("noise", 1, noise_seed=1)


def test_amendment_schema_accepts_only_frozen_gate_contract() -> None:
    amendment = read_amendment()
    validate_amendment_schema(amendment)

    bad_threshold = copy.deepcopy(amendment)
    bad_threshold["replacement_practical_endpoint_gates"]["A"][
        "primary_gate"
    ] = "mean must be >= 0.001"
    with pytest.raises(ValueError, match="practical threshold"):
        validate_amendment_schema(bad_threshold)

    bad_quantile = copy.deepcopy(amendment)
    bad_quantile["replacement_bootstrap_numeric_contract"][
        "bonferroni_primary_lower_bound"
    ]["numpy_method"] = "nearest"
    with pytest.raises(ValueError, match="quantile method"):
        validate_amendment_schema(bad_quantile)


def test_semantic_override_validation_rejects_bad_records() -> None:
    keys = expected_semantic_keys()
    bindings = {
        "raw_manifest_sha256": "A",
        "label_sidecar_sha256": "B",
        "row_key_sha256": "C",
    }
    validate_review_decision(valid_decision(), keys, bindings)

    duplicate = valid_decision()
    item = {
        "audit_index": 1,
        "family": "brightness",
        "level": 1,
        "action_and_rationale_labels_still_applicable": False,
        "scene_semantics_preserved": True,
        "review_notes": "counterexample",
    }
    duplicate["overrides"] = [item, copy.deepcopy(item)]
    with pytest.raises(ValueError, match="duplicate override"):
        validate_review_decision(duplicate, keys, bindings)

    out_of_grid = valid_decision()
    out_of_grid["overrides"] = [{**item, "level": 0}]
    with pytest.raises(ValueError, match="out of grid"):
        validate_review_decision(out_of_grid, keys, bindings)

    non_boolean = valid_decision()
    non_boolean["overrides"] = [
        {
            **item,
            "action_and_rationale_labels_still_applicable": "false",
        }
    ]
    with pytest.raises(ValueError, match="JSON boolean"):
        validate_review_decision(non_boolean, keys, bindings)

    extra_field = valid_decision()
    extra_field["overrides"] = [{**item, "unknown": 1}]
    with pytest.raises(ValueError, match="missing or extra"):
        validate_review_decision(extra_field, keys, bindings)


def test_unbound_transitive_operator_dependency_is_rejected() -> None:
    source = "from .data import deterministic_noise\n"
    with pytest.raises(ValueError, match="unbound local dependencies"):
        validate_bound_local_dependencies(
            source,
            {"src/arsc_eval/corruption_dose_response_v2.py"},
        )
    observed = validate_bound_local_dependencies(
        source,
        {
            "src/arsc_eval/corruption_dose_response_v2.py",
            "src/arsc_eval/data.py",
        },
    )
    assert observed == {"src/arsc_eval/data.py"}


def test_semantic_raw_grid_rejects_wrong_sample_and_grid() -> None:
    indices = list(range(100))
    records = [
        {
            "file_name": f"image_{index:03d}.jpg",
            "actions": [1, 0, 0, 0],
            "rationales": [0] * 21,
        }
        for index in indices
    ]
    rows = []
    for audit_index, family, level in expected_semantic_keys():
        rows.append(
            {
                "audit_index": str(audit_index),
                "dataset_index": str(indices[audit_index - 1]),
                "file_name": records[audit_index - 1]["file_name"],
                "family": family,
                "level": str(level),
                "parameter": str(
                    EXPECTED_PARAMETERS[family][level - 1]
                ),
                "action_and_rationale_labels_still_applicable": "",
                "scene_semantics_preserved": "",
                "review_notes": "",
            }
        )
    validate_semantic_raw_rows(rows, indices, records)

    wrong_sample = copy.deepcopy(rows)
    wrong_sample[0]["dataset_index"] = "999"
    with pytest.raises(ValueError, match="wrong dataset index"):
        validate_semantic_raw_rows(wrong_sample, indices, records)

    wrong_grid = copy.deepcopy(rows)
    wrong_grid[0]["family"] = "noise"
    with pytest.raises(ValueError, match="wrong key"):
        validate_semantic_raw_rows(wrong_grid, indices, records)


def test_page_hash_binding_rejects_review_and_file_mismatch() -> None:
    expected = {f"page_{index:02d}.png": "A" for index in range(30)}
    validate_page_hash_binding(expected, expected, expected)

    wrong_review = dict(expected)
    wrong_review["page_00.png"] = "B"
    with pytest.raises(ValueError, match="reviewed page hash"):
        validate_page_hash_binding(expected, wrong_review, expected)

    wrong_actual = dict(expected)
    wrong_actual["page_29.png"] = "B"
    with pytest.raises(ValueError, match="actual page hash"):
        validate_page_hash_binding(expected, expected, wrong_actual)


def test_formal_staging_and_cache_paths_are_rejected() -> None:
    forbidden = forbidden_round10_paths(
        [
            "scripts/analyze_round10_corruption.py",
            "scripts/launch_round10_corruption_tmux.sh",
            "outputs/validity/round10_corruption_formal.log",
            "outputs/validity/round10_corruption_results.json",
            "outputs/validity/round10_corruption_primitives.npz",
            "outputs/validity/round10_corruption_bootstrap_draws.npz",
            "outputs/validity/round10_corruption_prediction_cache/x.npz",
            (
                "outputs/validity/"
                "round10_corruption_formal_implementation_manifest.json"
            ),
            "outputs/validity/round10_corruption_formal_staging.tmp",
            "outputs/validity/round10_corruption_preflight_attempt02.json",
        ]
    )
    assert len(forbidden) == 9
    assert (
        "outputs/validity/round10_corruption_preflight_attempt02.json"
        not in forbidden
    )
