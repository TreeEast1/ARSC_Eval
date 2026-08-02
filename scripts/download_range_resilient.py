"""Append-only HTTP Range downloader for an unstable official dataset host.

Every response is bound to an exact Content-Range, total size, and ETag before
any bytes are appended.  A truncated TLS response keeps its verified prefix;
the next request starts at the new local size.  Existing bytes are never
truncated or overwritten.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


CONTENT_RANGE_RE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")


def parse_content_range(value: str) -> tuple[int, int, int]:
    match = CONTENT_RANGE_RE.fullmatch(value.strip())
    if match is None:
        raise ValueError(f"invalid Content-Range: {value!r}")
    start, end, total = (int(part) for part in match.groups())
    if start < 0 or end < start or total <= end:
        raise ValueError(f"inconsistent Content-Range: {value!r}")
    return start, end, total


def validate_response_headers(
    response: requests.Response,
    *,
    requested_start: int,
    requested_end: int,
    expected_total: int,
    expected_etag: str,
) -> None:
    if response.status_code in {408, 425, 429} or 500 <= response.status_code <= 599:
        raise requests.HTTPError(f"retryable HTTP status {response.status_code}")
    if response.status_code != 206:
        raise ValueError(f"expected HTTP 206, received {response.status_code}")
    start, end, total = parse_content_range(response.headers.get("Content-Range", ""))
    if (start, end, total) != (requested_start, requested_end, expected_total):
        raise ValueError(
            "response range mismatch: "
            f"observed={(start, end, total)} expected="
            f"{(requested_start, requested_end, expected_total)}"
        )
    expected_etag_header = (
        expected_etag
        if expected_etag.startswith('"') and expected_etag.endswith('"')
        else f'"{expected_etag}"'
    )
    if response.headers.get("ETag") != expected_etag_header:
        raise ValueError("response ETag differs from the frozen official object")
    content_length = int(response.headers.get("Content-Length", "-1"))
    if content_length != requested_end - requested_start + 1:
        raise ValueError("response Content-Length differs from requested range")


def event(kind: str, **fields: object) -> None:
    print(
        json.dumps(
            {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "event": kind,
                **fields,
            },
            sort_keys=True,
        ),
        flush=True,
    )


def download(
    *,
    url: str,
    output: Path,
    expected_total: int,
    expected_etag: str,
    range_end: int,
    base_offset: int,
    max_attempts: int,
    read_timeout_seconds: int,
    request_window_bytes: int,
) -> int:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    expected_output_bytes = range_end - base_offset + 1
    if base_offset < 0 or range_end < base_offset or range_end >= expected_total:
        raise ValueError("invalid frozen output range")
    if request_window_bytes <= 0:
        raise ValueError("request_window_bytes must be positive")
    if output.exists() and not output.is_file():
        raise ValueError("output exists but is not a regular file")
    current_output_bytes = output.stat().st_size if output.exists() else 0
    if current_output_bytes > expected_output_bytes:
        raise ValueError("existing output is longer than the frozen range")
    if current_output_bytes == expected_output_bytes:
        event("already_complete", output=str(output), bytes=current_output_bytes)
        return 0

    session = requests.Session()
    session.headers.update(
        {
            "Accept-Encoding": "identity",
            "User-Agent": "ARSC-Eval-result-blind-range-downloader/1",
        }
    )
    attempts = 0
    while current_output_bytes < expected_output_bytes:
        if max_attempts and attempts >= max_attempts:
            event("attempt_limit", attempts=attempts, bytes=current_output_bytes)
            return 2
        attempts += 1
        requested_start = base_offset + current_output_bytes
        requested_end = min(
            range_end, requested_start + request_window_bytes - 1
        )
        before_size = output.stat().st_size if output.exists() else 0
        if before_size != current_output_bytes:
            raise RuntimeError("output size changed outside this downloader")
        event(
            "request",
            attempt=attempts,
            start=requested_start,
            end=requested_end,
            retained_bytes=current_output_bytes,
        )
        response: requests.Response | None = None
        appended = 0
        try:
            response = session.get(
                url,
                headers={"Range": f"bytes={requested_start}-{requested_end}"},
                stream=True,
                timeout=(30, read_timeout_seconds),
                allow_redirects=False,
            )
            validate_response_headers(
                response,
                requested_start=requested_start,
                requested_end=requested_end,
                expected_total=expected_total,
                expected_etag=expected_etag,
            )
            with output.open("ab", buffering=0) as handle:
                since_sync = 0
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    remaining = expected_output_bytes - (current_output_bytes + appended)
                    if len(chunk) > remaining:
                        raise RuntimeError("server delivered bytes beyond frozen range")
                    handle.write(chunk)
                    appended += len(chunk)
                    since_sync += len(chunk)
                    if since_sync >= 16 * 1024 * 1024:
                        os.fsync(handle.fileno())
                        since_sync = 0
                os.fsync(handle.fileno())
        except (requests.RequestException, OSError) as error:
            event(
                "retryable_error",
                attempt=attempts,
                error=type(error).__name__,
                appended_bytes=appended,
            )
        finally:
            if response is not None:
                response.close()

        observed_size = output.stat().st_size if output.exists() else 0
        expected_size = current_output_bytes + appended
        if observed_size != expected_size:
            raise RuntimeError("output size does not equal verified appended bytes")
        current_output_bytes = observed_size
        event(
            "attempt_closed",
            attempt=attempts,
            retained_bytes=current_output_bytes,
            expected_output_bytes=expected_output_bytes,
        )
        if appended == 0:
            time.sleep(min(60, 5 + attempts))

    event("complete", attempts=attempts, bytes=current_output_bytes)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-total", type=int, required=True)
    parser.add_argument("--expected-etag", required=True)
    parser.add_argument("--base-offset", type=int, default=0)
    parser.add_argument("--range-end", type=int, required=True)
    parser.add_argument("--max-attempts", type=int, default=0)
    parser.add_argument("--read-timeout-seconds", type=int, default=300)
    parser.add_argument("--request-window-bytes", type=int, default=16 * 1024 * 1024)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return download(
        url=args.url,
        output=args.output,
        expected_total=args.expected_total,
        expected_etag=args.expected_etag,
        range_end=args.range_end,
        base_offset=args.base_offset,
        max_attempts=args.max_attempts,
        read_timeout_seconds=args.read_timeout_seconds,
        request_window_bytes=args.request_window_bytes,
    )


if __name__ == "__main__":
    raise SystemExit(main())
