"""Freeze the result-blind Round 11 DAAD-X integrity preflight protocol.

This command never opens the DAAD-X archive.  It binds the independently
reviewed transport, population, media, provenance, grouping, and split rules
before the formal preflight is allowed to inspect the downloaded package.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "outputs/validity/round11_daadx_preflight_protocol.json"
REVIEW_MEMO = ROOT / "outputs/research_review_memo_round11_direction.md"
REVIEW_DECISION = (
    ROOT / "outputs/validity/round11_direction_reviewer_decision.json"
)
IMPLEMENTATION_REVIEW_DECISION = (
    ROOT / "outputs/validity/round11_implementation_reviewer_decision.json"
)
SCOUT_DECISION = (
    ROOT / "outputs/validity/round11_external_dataset_feasibility.json"
)
IMPLEMENTATION_FILES = (
    ROOT / "scripts/freeze_round11_daadx_preflight_protocol.py",
    ROOT / "src/arsc_eval/daadx_preflight.py",
    ROOT / "tests/test_daadx_preflight.py",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def git_value(*args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(ROOT), *args], text=True
    ).strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    return parser.parse_args()


def rooted(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def require_head_matches(path: Path) -> None:
    relative = path.relative_to(ROOT).as_posix()
    try:
        committed = subprocess.check_output(
            ["git", "-C", str(ROOT), "show", f"HEAD:{relative}"]
        )
    except subprocess.CalledProcessError as error:
        raise ValueError(f"required file is not present in HEAD: {relative}") from error
    if sha256(path) != hashlib.sha256(committed).hexdigest().upper():
        raise ValueError(f"working file differs from HEAD: {relative}")


def main() -> int:
    parse_args()
    output = DEFAULT_OUTPUT
    protected_outputs = (
        output,
        ROOT / "outputs/validity/round11_daadx_preflight_attempt01.staging",
        ROOT / "outputs/validity/round11_daadx_preflight_attempt01",
        ROOT / "outputs/validity/round11_daadx_preflight_attempt01.log",
        ROOT / "outputs/validity/round11_daadx_artifact_index.json",
        output.with_suffix(output.suffix + ".tmp"),
    )
    existing_outputs = [str(path) for path in protected_outputs if path.exists()]
    if existing_outputs:
        raise FileExistsError(
            f"refusing freeze because formal output already exists: {existing_outputs}"
        )

    required = [
        REVIEW_MEMO,
        REVIEW_DECISION,
        IMPLEMENTATION_REVIEW_DECISION,
        SCOUT_DECISION,
        *IMPLEMENTATION_FILES,
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing reviewed direction inputs: {missing}")

    decision = json.loads(REVIEW_DECISION.read_text(encoding="utf-8"))
    if decision.get("schema_version") != "ARSC_ROUND11_DIRECTION_REVIEWER_DECISION_V1":
        raise ValueError("unexpected direction reviewer schema")
    direction = decision.get("direction_decision", {})
    if direction.get("decision") != "DAADX_PREFLIGHT_FIRST_THEN_CANDIDATE_A_IF_STOP":
        raise ValueError("reviewer decision does not authorize DAAD-X preflight")
    if direction.get("round11_unique_current_task") != "DAADX_DOWNLOAD_AND_GROUP_INTEGRITY_PREFLIGHT_ONLY":
        raise ValueError("reviewer decision lacks the preflight-only boundary")

    implementation_review = json.loads(
        IMPLEMENTATION_REVIEW_DECISION.read_text(encoding="utf-8")
    )
    if implementation_review.get("schema_version") != "ARSC_ROUND11_IMPLEMENTATION_REVIEWER_DECISION_V1":
        raise ValueError("unexpected implementation reviewer schema")
    if implementation_review.get("decision") != "GO_FREEZE_PROTOCOL":
        raise ValueError("implementation reviewer did not authorize freezing")
    if implementation_review.get("direction_decision_sha256") != sha256(REVIEW_DECISION):
        raise ValueError("implementation review is not bound to this direction decision")
    reviewed_hashes = {
        item["path"]: item["sha256"]
        for item in implementation_review.get("reviewed_files", [])
    }
    implementation_hashes: dict[str, str] = {}
    for path in IMPLEMENTATION_FILES:
        relative = path.relative_to(ROOT).as_posix()
        current_hash = sha256(path)
        if reviewed_hashes.get(relative) != current_hash:
            raise ValueError(f"implementation review hash mismatch: {relative}")
        require_head_matches(path)
        implementation_hashes[relative] = current_hash
    require_head_matches(IMPLEMENTATION_REVIEW_DECISION)

    protocol = {
        "schema_version": "ARSC_ROUND11_DAADX_PREFLIGHT_PROTOCOL_V1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "formal_run": False,
        "result_blind": True,
        "attempt": "attempt01",
        "direction": "DAADX_PREFLIGHT_FIRST_THEN_CANDIDATE_A_IF_STOP",
        "authorization": "DAADX_DOWNLOAD_AND_GROUP_INTEGRITY_PREFLIGHT_ONLY",
        "training_authorized": False,
        "repository": {
            "head": git_value("rev-parse", "HEAD"),
            "tree": git_value("rev-parse", "HEAD^{tree}"),
            "branch": git_value("branch", "--show-current"),
            "implementation_sha256": implementation_hashes,
        },
        "independent_review": {
            "memo": REVIEW_MEMO.relative_to(ROOT).as_posix(),
            "memo_sha256": sha256(REVIEW_MEMO),
            "decision": REVIEW_DECISION.relative_to(ROOT).as_posix(),
            "decision_sha256": sha256(REVIEW_DECISION),
            "implementation_decision": IMPLEMENTATION_REVIEW_DECISION.relative_to(ROOT).as_posix(),
            "implementation_decision_sha256": sha256(IMPLEMENTATION_REVIEW_DECISION),
            "scout_decision": SCOUT_DECISION.relative_to(ROOT).as_posix(),
            "scout_decision_sha256": sha256(SCOUT_DECISION),
        },
        "official_input": {
            "url": "https://cvit.iiit.ac.in/images/datasets/daadx/daadx.tar.gz",
            "expected_content_length_bytes": 18_585_647_156,
            "official_code_commit": (
                "932c463b10f2cad42d2d3854376b40a919f47d0a"
            ),
            "official_hf_revision": (
                "35eddaa90667beffc5481e014df8fc6176ed0168"
            ),
            "eligible_split_names": ["train", "val", "test"],
            "expected_unique_uuid_count": 1566,
            "expected_front_binding_count": 1566,
            "complete_case_deletion_allowed": False,
        },
        "label_firewall": {
            "grouping_visible_fields": ["uuid", "official_split"],
            "sealed_fields": ["maneuver", "gaze_eX", "ego_eX"],
            "forbidden_inputs": [
                "any_model_logits",
                "any_model_predictions",
                "any_model_confidence",
                "any_model_loss_or_metric",
                "label_values_in_grouping_or_split_code",
                "face_identity_or_biometric_features",
            ],
        },
        "media": {
            "future_model_view": "front_view_only",
            "decode_requirement": "full_video_first_frame_through_last_frame",
            "sampling_hz_for_duplicate_audit": 2.0,
            "first_timestamp_seconds": 0.25,
            "timestamp_step_seconds": 0.5,
            "normalized_width": 256,
            "normalized_height": 144,
            "letterbox_fill_uint8": 0,
            "resize_rounding": "floor(source_dimension*scale+0.5)",
            "resize_interpolation": "half_pixel_bilinear_then_round_to_nearest_even_uint8",
            "decoder_pixel_format": "RGB24",
            "normalization": "RGB_to_BT601_grayscale_then_aspect_preserving_bilinear_letterbox",
            "phash": {
                "dct_size": 32,
                "hash_size": 8,
                "exclude_dc_from_median": True,
                "bits": 64,
            },
            "ssim": {
                "data_range": 255.0,
                "window_size": 11,
                "gaussian_sigma": 1.5,
                "padding": "reflect",
            },
        },
        "duplicate_edges": {
            "byte_exact": True,
            "decode_exact": True,
            "broad": {
                "minimum_aligned_pairs": 6,
                "minimum_seconds": 3.0,
                "time_scale_slope_min": 0.98,
                "time_scale_slope_max": 1.02,
                "phash_each_max": 10,
                "phash_median_max": 6,
                "ssim_median_min": 0.90,
            },
            "strict_sensitivity": {
                "minimum_aligned_pairs": 6,
                "phash_each_max": 6,
                "phash_median_max": 4,
                "ssim_median_min": 0.95,
            },
            "boundary": {
                "seconds_each_side": 1.5,
                "ordered_pairs": 3,
                "phash_each_max": 10,
                "phash_median_max": 6,
                "ssim_median_min": 0.90,
                "requires_same_camera_rig_signature": True,
            },
            "cross_dataset_scan": {
                "reference_population": "frozen_BDD_OIA_4557_images",
                "single_frame_phash_hamming_max": 10,
                "single_frame_ssim_min": 0.90,
                "action": "quarantine_entire_DAADX_source_group",
            },
            "qa": {
                "selection": {
                    "digest": "SHA256(uuid encoded as strict UTF-8 bytes)",
                    "order": "ascending digest bytes then ascending UUID UTF-8 bytes",
                    "count": 50,
                },
                "positive_transforms": ["transcode", "resize", "brightness_pm5pct"],
                "transform_input": "original eligible front-view video",
                "transform_then_measurement_order": "transform_video_then_decode_RGB24_then_sample_then_grayscale_letterbox",
                "transcode": {
                    "ffmpeg_version": "7.1",
                    "video_codec": "libx264",
                    "pixel_format": "yuv420p",
                    "crf": 23,
                    "preset": "medium",
                    "threads": 1,
                    "audio": "dropped",
                },
                "resize": {
                    "width": 320,
                    "height": 180,
                    "interpolation": "ffmpeg_scale_bicubic",
                    "encode_as": "same_as_transcode",
                },
                "brightness_pm5pct": {
                    "factors": [0.95, 1.05],
                    "domain": "decoded_RGB24_uint8",
                    "formula": "clip(floor(pixel*factor+0.5),0,255)",
                    "encoding": "ffv1_lossless_rgb24_threads1_no_audio",
                },
                "required_recovery": "50/50_source_relations_for_each_transform",
            },
        },
        "source_grouping": {
            "unit": "upstream_raw_recording_or_capture_session",
            "all_clips_require_authoritative_or_auditable_provenance": True,
            "absence_of_near_duplicate_is_not_provenance": True,
            "group_algorithm": "connected_components_of_authoritative_metadata_and_broad_content_edges",
            "public_group_ids": "salted_nonreversible",
        },
        "group_split": {
            "salt": "ARSC-DAADX-R11-GROUP-SPLIT-V1",
            "train_upper": 0.70,
            "validation_upper": 0.90,
            "minimum_groups_each_split": 30,
            "minimum_test_clips": 100,
            "maximum_test_group_share": 0.10,
            "label_balancing_allowed": False,
            "second_salt_allowed": False,
            "official_split_policy": "retain_only_if_source_group_disjoint_else_discard_and_apply_exactly_one_salt",
            "canonical_group_id": "uppercase_SHA256(canonical_UTF8_JSON_of_sorted_UUID_array; ensure_ascii=false; separators=comma_colon)",
            "hash_input": "ASCII(namespace + vertical_bar + uppercase_canonical_group_id)",
            "hash_uniform": "first_64_SHA256_bits_as_unsigned_big_endian_integer_divided_by_2^64",
            "integer_boundaries": {
                "train": "10*value < 7*2^64",
                "validation": "7*2^64 <= 10*value < 9*2^64",
                "test": "9*2^64 <= 10*value",
            },
            "split_name_normalization": {"val": "validation"},
        },
        "gates": {
            "G0": "transport_archive_exact_bytes_double_sha_gzip_tar_header_path_and_member_type",
            "G1": "1566_unique_split_uuids_and_1566_unique_front_bindings",
            "G2": "all_1566_front_videos_fully_decode_with_valid_metadata",
            "G3": "100_percent_authoritative_or_auditable_source_provenance",
            "G4": "broad_graph_byte_identical_rerun_and_qa_50_of_50",
            "G5": "cross_dataset_match_groups_quarantined_and_later_gates_hold",
            "G6": "zero_group_intersection_after_official_or_one_salt_split",
            "G7": "cluster_adequacy_thresholds_all_hold",
            "G8": "complete_hash_closed_artifact_set_and_unique_exit_marker",
        },
        "verdict_rule": {
            "all_G0_through_G8_pass": (
                "GO_TO_SEPARATE_DAADX_PROTOCOL_FREEZE_REVIEW_NOT_TRAINING"
            ),
            "any_fail_or_inconclusive": (
                "STOP_DAADX_AND_SWITCH_TO_CANDIDATE_A_EXPLORATORY"
            ),
        },
        "formal_output": {
            "staging": "outputs/validity/round11_daadx_preflight_attempt01.staging",
            "final": "outputs/validity/round11_daadx_preflight_attempt01",
            "log": "outputs/validity/round11_daadx_preflight_attempt01.log",
            "artifact_index": "outputs/validity/round11_daadx_artifact_index.json",
            "required_artifacts": [
                "round11_daadx_preflight_protocol.json",
                "round11_daadx_download_receipt.json",
                "round11_daadx_archive_hashes.json",
                "round11_daadx_tar_inventory.csv",
                "round11_daadx_member_hashes.csv",
                "round11_daadx_label_seal.json",
                "round11_daadx_uuid_media_binding.csv",
                "round11_daadx_media_probe.csv",
                "round11_daadx_threshold_qa.json",
                "round11_daadx_duplicate_edges.csv",
                "round11_daadx_cross_dataset_overlap.csv",
                "round11_daadx_source_groups.csv",
                "round11_daadx_split_audit.csv",
                "round11_daadx_preflight_results.json",
                "round11_daadx_preflight.log",
                "round11_daadx_artifact_index.json",
            ],
        },
        "archive_safety": {
            "allowed_tar_member_types": ["regular_file", "directory"],
            "forbidden_tar_member_types": [
                "symlink", "hardlink", "character_device", "block_device",
                "fifo", "socket", "sparse_or_unknown"
            ],
            "link_targets": "all_links_forbidden_so_no_target_is_followed",
            "pax_headers": "parsed_metadata_only_and_never_allowed_to_override_canonical_path_safety",
            "case_insensitive_path_collisions_allowed": False,
            "windows_alternate_data_stream_names_allowed": False,
            "windows_reserved_devices_allowed": False,
            "segment_trailing_dot_or_space_allowed": False,
            "unicode_normalization": "every_segment_must_be_NFC_and_collision_key_is_NFC_casefold",
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    payload = (json.dumps(protocol, indent=2, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    print(f"WROTE {output.relative_to(ROOT)}")
    print(f"SHA256 {sha256(output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
