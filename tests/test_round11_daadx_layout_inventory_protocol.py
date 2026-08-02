from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/freeze_round11_daadx_layout_inventory_protocol.py"
SPEC = importlib.util.spec_from_file_location("layout_protocol", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _build():
    return MODULE.build_protocol(MODULE.load_authority_bytes())


def test_exact_authorities_and_generated_protocol() -> None:
    authorities = MODULE.load_authority_bytes()
    for path, _schema, digest, _decision in MODULE.AUTHORITY_SPECS:
        assert MODULE.sha256_bytes(authorities[path]) == digest
    protocol = _build()
    generated = ROOT / MODULE.OUTPUT_PATH
    if generated.exists():
        assert generated.read_bytes() == MODULE.canonical_json_bytes(protocol)


def test_top_level_contract_is_exact_and_nonrunning() -> None:
    protocol = _build()
    assert set(protocol) == {
        "schema_version", "generated_at_utc", "additive_only", "result_blind",
        "phase", "attempt", "training_authorized", "authorities", "input_contract",
        "authorization", "execution_control", "parser_contract", "resource_bounds",
        "artifact_contract", "output_privacy", "outcomes", "selection_contract",
        "prohibited_effects", "next_required_action",
    }
    assert protocol["schema_version"] == MODULE.SCHEMA
    assert protocol["additive_only"] is True
    assert protocol["result_blind"] is True
    assert protocol["training_authorized"] is False
    assert protocol["next_required_action"].endswith("NOT_RUN")
    assert protocol["authorization"]["phase1_or_g0_g8_execution"] is False


def test_claim_before_access_and_paths_are_disjoint() -> None:
    protocol = _build()
    control = protocol["execution_control"]
    assert "BEFORE_ANY_RECEIPT_MANIFEST_ARCHIVE" in control["claim_creation"]
    assert control["claim_persists_on_every_exit_exception_interrupt_or_crash"] is True
    assert control["automatic_delete_reuse_or_recovery_allowed"] is False
    assert len({control["claim_path"], control["staging_path"], control["final_path"]}) == 3
    assert "phase1_attempt01" not in "|".join(
        [control["claim_path"], control["staging_path"], control["final_path"]]
    )


def test_raw_parser_and_payload_boundary_are_frozen() -> None:
    parser = _build()["parser_contract"]
    assert parser["authoritative_parser"] == "CUSTOM_RAW_GZIP_TAR_PAX_STATE_MACHINE_ONLY"
    assert parser["tarfile_or_libarchive_authority_allowed"] is False
    assert parser["gzip"]["member_count"] == 1
    assert parser["gzip"]["crc32_isize_and_eof_required"] is True
    assert parser["tar"]["raw_header_bytes"] == 512
    assert "EITHER_UNSIGNED_OR_SIGNED" in parser["tar"]["checksum"]
    assert set(parser["tar"]["allowed_types"]) == {"REGULAR", "DIRECTORY", "PAX_EXTENDED_X", "PAX_GLOBAL_G"}
    payload = parser["regular_payload"]
    assert payload["physical_access"].startswith("FIXED_BUFFER_OPAQUE_DRAIN")
    assert payload["parse_save_extract_sample_inspect_hash_log_or_expose_allowed"] is False
    assert payload["bytes_retained_in_python_object_or_output"] == 0
    pax = parser["pax"]
    assert set(pax["exact_allowed_keys"]) == {
        "path", "size", "mtime", "atime", "ctime", "uid", "gid",
        "uname", "gname", "comment",
    }
    assert pax["global_g_path_or_size_allowed"] is False
    assert pax["sparse_link_linkpath_charset_schily_gnu_or_unknown_keys_allowed"] is False
    assert pax["directory_resolved_size_must_be_zero"] is True


def test_resource_bounds_are_positive_and_coherent() -> None:
    bounds = _build()["resource_bounds"]
    assert all(isinstance(value, int) and value > 0 for value in bounds.values())
    assert bounds["compressed_archive_bytes_exact"] == 18_585_647_156
    assert bounds["max_single_pax_payload_bytes"] <= bounds["max_cumulative_pax_payload_bytes"]
    assert bounds["regular_payload_drain_buffer_bytes"] <= bounds["max_single_regular_member_bytes"]
    assert bounds["max_single_regular_member_bytes"] <= bounds["max_uncompressed_tar_stream_bytes"]
    assert bounds["max_compressed_input_buffer_bytes"] <= bounds["max_in_memory_bytes"]
    assert bounds["max_decompressed_output_buffer_bytes"] <= bounds["max_in_memory_bytes"]
    assert bounds["max_collision_digest_entries"] == 2 * bounds["max_logical_members"]


def test_artifacts_outcomes_and_selection_match_design_decision() -> None:
    protocol = _build()
    design = json.loads(
        (ROOT / "outputs/validity/round11_layout_inventory_design_reviewer_decision.json").read_text(encoding="utf-8")
    )
    assert protocol["artifact_contract"]["exact_files"] == design["exact_artifacts"] == list(MODULE.ARTIFACTS)
    assert protocol["artifact_contract"]["artifact_index"] == MODULE.ARTIFACTS[-1]
    assert set(protocol["outcomes"]) == set(design["outcomes"])
    assert all(not value["is_phase1_or_g0_g8_verdict"] for value in protocol["outcomes"].values())
    selection = protocol["selection_contract"]
    assert selection["payload_disambiguation_allowed"] is False
    assert selection["selector_may_issue_phase1_go_run"] is False
    assert protocol["output_privacy"]["public_inventory_contains_raw_paths"] is False
    assert protocol["output_privacy"]["sealed_means_hash_closed_not_encrypted"] is True
    privacy = protocol["output_privacy"]
    assert privacy["public_inventory_and_restricted_seal_write_mode"].startswith("STREAM_")
    assert privacy["full_raw_or_resolved_path_lists_may_accumulate_in_memory"] is False
    assert "FIXED_32_BYTE" in privacy["collision_state"]
    assert selection["provenance_candidate"].startswith("EXACTLY_ONE_")


def test_mutated_authority_fails_closed() -> None:
    authorities = MODULE.load_authority_bytes()
    path = MODULE.AUTHORITY_SPECS[0][0]
    authorities[path] += b" "
    with pytest.raises(ValueError, match="SHA differs"):
        MODULE.build_protocol(authorities)


def test_atomic_no_overwrite_and_competitor_preserved(tmp_path: Path) -> None:
    output = tmp_path / "protocol.json"
    protocol = _build()
    MODULE.publish_no_overwrite(protocol, output)
    expected = output.read_bytes()
    assert expected == MODULE.canonical_json_bytes(protocol)
    with pytest.raises(ValueError, match="already exists"):
        MODULE.publish_no_overwrite(protocol, output)
    assert output.read_bytes() == expected

    competitor = tmp_path / "competitor.json"
    def competitor_link(_source: Path, target: Path) -> None:
        target.write_bytes(b"competitor")
        raise FileExistsError("competitor won")

    with pytest.raises(FileExistsError, match="competitor won"):
        MODULE.publish_no_overwrite(protocol, competitor, link_func=competitor_link)
    assert competitor.read_bytes() == b"competitor"
    assert not competitor.with_name(competitor.name + ".tmp").exists()


def test_symlink_output_rejected_when_supported(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_bytes(b"target")
    output = tmp_path / "protocol.json"
    try:
        output.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink unavailable")
    with pytest.raises(ValueError, match="already exists"):
        MODULE.publish_no_overwrite(_build(), output)
