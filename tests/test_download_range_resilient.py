from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/download_range_resilient.py"
SPEC = importlib.util.spec_from_file_location("download_range_resilient", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FakeResponse:
    def __init__(self, status_code: int, headers: dict[str, str]) -> None:
        self.status_code = status_code
        self.headers = headers


def test_parse_content_range_is_exact() -> None:
    assert MODULE.parse_content_range("bytes 10-19/100") == (10, 19, 100)
    for invalid in ("10-19/100", "bytes 20-19/100", "bytes 0-100/100"):
        with pytest.raises(ValueError):
            MODULE.parse_content_range(invalid)


def test_header_validation_binds_range_length_total_and_etag() -> None:
    response = FakeResponse(
        206,
        {
            "Content-Range": "bytes 10-19/100",
            "Content-Length": "10",
            "ETag": '"official"',
        },
    )
    MODULE.validate_response_headers(
        response,
        requested_start=10,
        requested_end=19,
        expected_total=100,
        expected_etag='"official"',
    )
    MODULE.validate_response_headers(
        response,
        requested_start=10,
        requested_end=19,
        expected_total=100,
        expected_etag="official",
    )
    response.headers["ETag"] = '"wrong"'
    with pytest.raises(ValueError, match="ETag"):
        MODULE.validate_response_headers(
            response,
            requested_start=10,
            requested_end=19,
            expected_total=100,
            expected_etag='"official"',
        )


def test_retryable_server_status_raises_request_error() -> None:
    response = FakeResponse(504, {})
    with pytest.raises(MODULE.requests.HTTPError, match="retryable"):
        MODULE.validate_response_headers(
            response,
            requested_start=0,
            requested_end=9,
            expected_total=100,
            expected_etag="official",
        )
