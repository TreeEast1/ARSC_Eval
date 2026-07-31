from __future__ import annotations

from dataclasses import asdict

import numpy as np
import pytest

from arsc_eval.daadx_preflight import (
    EXPECTED_GATE_IDS,
    GO_VERDICT,
    STOP_VERDICT,
    GateStatus,
    aggregate_gate_verdicts,
    aligned_window_edge,
    boundary_continuation_edge,
    canonical_group_id,
    canonical_json_sha256,
    canonical_tar_path,
    connected_components,
    dct_phash64,
    deterministic_frame_timestamps,
    double_read_sha256,
    fixed_one_salt_group_split,
    grayscale_letterbox,
    grayscale_ssim,
    normalized_frame_sha256,
    parse_uuid_split_seal,
    phash_hamming,
    salted_public_group_id,
    sha256_bytes,
    sha256_file,
    split_for_canonical_group_id,
    validate_canonical_tar_paths,
)


def test_canonical_tar_paths_reject_escape_absolute_and_aliases() -> None:
    assert canonical_tar_path("daadx/front/a.mp4") == "daadx/front/a.mp4"
    assert canonical_tar_path("daadx/front/") == "daadx/front"
    for unsafe in (
        "../escape",
        "a/../escape",
        "/absolute",
        "C:/drive",
        "a\\windows",
        "a//b",
        "daadx/front///",
        "a.mp4:secret",
        "front/name. ",
        "front/name.",
        "front/CON",
        "front/nul.mp4",
        "front/COM1.txt",
        "front/e\u0301.mp4",
        "./a",
        "a/./b",
        "",
        "a\x00b",
    ):
        with pytest.raises(ValueError):
            canonical_tar_path(unsafe)
    with pytest.raises(ValueError, match="duplicate"):
        validate_canonical_tar_paths(["a/b/", "a/b"])
    with pytest.raises(ValueError, match="case-insensitive"):
        validate_canonical_tar_paths(["front/A.mp4", "front/a.mp4"])


def test_uuid_split_seal_exposes_no_label_values() -> None:
    sources = {
        "train": b"uuid,maneuver,rationale\r\nu2,TURN,SECRET_A\r\n",
        "val": b"uuid,maneuver,rationale\r\nu1,STOP,SECRET_B\r\n",
        "test": b"uuid,maneuver,rationale\r\nu3,SLOW,SECRET_C\r\n",
    }
    seal = parse_uuid_split_seal(sources)
    assert seal.uuid_split_rows == (("u1", "val"), ("u2", "train"), ("u3", "test"))
    assert seal.unique_uuid_count == 3
    serialized = repr(asdict(seal))
    assert "SECRET" not in serialized
    assert "maneuver" not in serialized
    assert seal.source_sha256[0][1] == sha256_bytes(sources["train"])


def test_uuid_split_seal_rejects_cross_split_duplicates_and_wrong_sources() -> None:
    duplicate = {
        "train": b"uuid,label\nu1,x\n",
        "val": b"uuid,label\nu1,y\n",
        "test": b"uuid,label\nu2,z\n",
    }
    with pytest.raises(ValueError, match="duplicated"):
        parse_uuid_split_seal(duplicate)
    with pytest.raises(ValueError, match="exactly match"):
        parse_uuid_split_seal({"train": b"uuid\nu1\n"})


def test_deterministic_timestamps_are_strictly_below_duration() -> None:
    assert deterministic_frame_timestamps(2.0) == (0.25, 0.75, 1.25, 1.75)
    assert deterministic_frame_timestamps(0.5) == (0.25,)
    with pytest.raises(ValueError, match="shorter"):
        deterministic_frame_timestamps(0.49)


def test_grayscale_letterbox_preserves_aspect_and_is_deterministic() -> None:
    red_wide = np.zeros((10, 20, 3), dtype=np.uint8)
    red_wide[..., 0] = 255
    normalized = grayscale_letterbox(red_wide, target_width=20, target_height=20)
    assert normalized.shape == (20, 20)
    assert normalized.dtype == np.uint8
    assert np.all(normalized[:5] == 0)
    assert np.all(normalized[15:] == 0)
    assert np.all(normalized[5:15] == 76)
    np.testing.assert_array_equal(normalized, grayscale_letterbox(red_wide, target_width=20, target_height=20))


def test_dct_phash_is_64_bit_deterministic_and_hamming_is_exact() -> None:
    constant = np.full((144, 256), 80, dtype=np.uint8)
    gradient = np.tile(np.arange(256, dtype=np.uint8), (144, 1))
    first = dct_phash64(constant)
    second = dct_phash64(constant.copy())
    changed = dct_phash64(gradient)
    assert 0 <= first < 2**64
    assert first == second == 0
    assert phash_hamming(first, second) == 0
    assert phash_hamming(first, changed) == changed.bit_count()
    with pytest.raises(ValueError):
        phash_hamming(-1, 0)


def test_normalized_frame_hash_binds_shape_and_bytes() -> None:
    frame = np.zeros((144, 256), dtype=np.uint8)
    changed = frame.copy()
    changed[0, 0] = 1
    assert normalized_frame_sha256(frame) != normalized_frame_sha256(changed)
    with pytest.raises(ValueError, match="144x256"):
        normalized_frame_sha256(np.zeros((256, 144), dtype=np.uint8))


def test_grayscale_ssim_identity_brightness_and_shape_checks() -> None:
    image = np.tile(np.arange(256, dtype=np.uint8), (144, 1))
    brighter = np.clip(image.astype(int) + 20, 0, 255).astype(np.uint8)
    assert grayscale_ssim(image, image) == pytest.approx(1.0, abs=1e-12)
    assert grayscale_ssim(image, brighter) < 1.0
    assert grayscale_ssim(image, brighter) == pytest.approx(
        grayscale_ssim(brighter, image), abs=1e-12
    )
    with pytest.raises(ValueError, match="normalized"):
        grayscale_ssim(image, brighter[:, :-1])


def test_broad_and_strict_aligned_windows_are_distinct() -> None:
    times = np.arange(6, dtype=float) * 0.5
    broad_only = aligned_window_edge(
        times,
        times + 4.0,
        [6, 6, 6, 6, 6, 6],
        [0.91] * 6,
    )
    strict = aligned_window_edge(
        times,
        times + 4.0,
        [4, 4, 4, 4, 4, 4],
        [0.96] * 6,
        strict=True,
    )
    assert broad_only.matched and broad_only.rule == "NEAR_OVERLAP_BROAD"
    assert not aligned_window_edge(
        times, times + 4.0, [6] * 6, [0.91] * 6, strict=True
    ).matched
    assert strict.matched and strict.rule == "NEAR_OVERLAP_STRICT"


def test_aligned_window_rejects_bad_slope_each_distance_and_median() -> None:
    times = np.arange(6, dtype=float) * 0.5
    assert not aligned_window_edge(times, times * 1.03, [1] * 6, [0.99] * 6).matched
    assert not aligned_window_edge(times, times, [1, 1, 1, 1, 1, 11], [0.99] * 6).matched
    assert not aligned_window_edge(times, times, [7] * 6, [0.99] * 6).matched
    assert not aligned_window_edge(times, times, [1] * 6, [0.89] * 6).matched
    sparse = np.arange(6, dtype=float) * 10.0
    assert not aligned_window_edge(sparse, sparse, [1] * 6, [0.99] * 6).matched


def test_boundary_rule_requires_three_pairs_and_same_nonlabel_signature() -> None:
    matched = boundary_continuation_edge(
        [8.25, 8.75, 9.25],
        [0.25, 0.75, 1.25],
        [6, 6, 6],
        [0.90, 0.91, 0.92],
        tail_rig_signature="rig-sync-1",
        head_rig_signature="rig-sync-1",
    )
    assert matched.matched
    assert not boundary_continuation_edge(
        [8.25, 8.75, 9.25],
        [0.25, 0.75, 1.25],
        [6, 6, 6],
        [0.90, 0.91, 0.92],
        tail_rig_signature="rig-sync-1",
        head_rig_signature="rig-sync-2",
    ).matched
    with pytest.raises(ValueError, match="exactly three"):
        boundary_continuation_edge(
            [0.25, 0.75],
            [0.25, 0.75],
            [1, 1],
            [0.99, 0.99],
            tail_rig_signature="x",
            head_rig_signature="x",
        )


def test_connected_components_are_deterministic_and_include_singletons() -> None:
    expected = (("a", "b", "c"), ("d",))
    assert connected_components(["d", "c", "b", "a"], [("b", "c"), ("a", "b")]) == expected
    assert connected_components(["a", "b", "c", "d"], [("c", "b"), ("b", "a")]) == expected
    with pytest.raises(ValueError, match="absent"):
        connected_components(["a"], [("a", "missing")])


def test_salted_public_ids_hide_canonical_and_change_with_salt() -> None:
    members = ["uuid-b", "uuid-a"]
    canonical = canonical_group_id(members)
    public_a = salted_public_group_id(members, b"0123456789abcdef")
    public_b = salted_public_group_id(members, b"fedcba9876543210")
    assert public_a == salted_public_group_id(reversed(members), b"0123456789abcdef")
    assert public_a != public_b
    assert canonical not in public_a
    assert "uuid" not in public_a


def test_fixed_one_salt_split_is_order_invariant_and_disjoint() -> None:
    groups = [("c",), ("a", "b"), ("d", "e")]
    first = fixed_one_salt_group_split(groups)
    second = fixed_one_salt_group_split(reversed(groups))
    assert first == second
    for assignment in first:
        split, uniform = split_for_canonical_group_id(assignment.canonical_group_id)
        assert assignment.split == split
        assert assignment.hash_uniform == uniform
        assert split in {"train", "validation", "test"}
        assert 0.0 <= uniform < 1.0
    with pytest.raises(ValueError, match="overlap"):
        fixed_one_salt_group_split([("a", "b"), ("b", "c")])


def test_gate_aggregation_is_and_only_and_never_authorizes_training() -> None:
    passed = aggregate_gate_verdicts({gate: GateStatus.PASS for gate in EXPECTED_GATE_IDS})
    assert passed.all_gates_passed
    assert passed.verdict == GO_VERDICT
    assert passed.training_authorized is False

    failed = aggregate_gate_verdicts(
        {**{gate: "PASS" for gate in EXPECTED_GATE_IDS}, "G5": "FAIL"}
    )
    assert failed.verdict == STOP_VERDICT
    assert failed.failed_gates == ("G5",)

    missing = aggregate_gate_verdicts({"G0": "PASS"})
    assert missing.verdict == STOP_VERDICT
    assert missing.inconclusive_gates == EXPECTED_GATE_IDS[1:]
    with pytest.raises(ValueError, match="unexpected"):
        aggregate_gate_verdicts({"G9": "PASS"})


def test_sha_helpers_are_consistent(tmp_path) -> None:
    path = tmp_path / "small.bin"
    payload = b"DAAD-X preflight test\x00"
    path.write_bytes(payload)
    expected = sha256_bytes(payload)
    assert sha256_file(path, chunk_size=3) == expected
    first, second, equal = double_read_sha256(path)
    assert first == second == expected
    assert equal
    assert canonical_json_sha256({"b": 2, "a": 1}) == canonical_json_sha256(
        {"a": 1, "b": 2}
    )
