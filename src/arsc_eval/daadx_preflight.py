"""Pure, result-blind primitives for the frozen Round 11 DAAD-X preflight.

The functions in this module do not discover files, decode videos, inspect
labels, or write artifacts.  They implement only the deterministic contracts
needed by a later, separately reviewed preflight runner.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import math
import posixpath
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, BinaryIO, Iterable, Mapping, Sequence

import numpy as np


EXPECTED_GATE_IDS = tuple(f"G{index}" for index in range(9))
GROUP_SPLIT_NAMESPACE = "ARSC-DAADX-R11-GROUP-SPLIT-V1"
NORMALIZED_FRAME_SHAPE = (144, 256)
GO_VERDICT = "GO_TO_SEPARATE_DAADX_PROTOCOL_FREEZE_REVIEW_NOT_TRAINING"
STOP_VERDICT = "STOP_DAADX_AND_SWITCH_TO_CANDIDATE_A_EXPLORATORY"
WINDOWS_RESERVED_BASENAMES = {
    "CON", "PRN", "AUX", "NUL", "CLOCK$",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def sha256_bytes(value: bytes | bytearray | memoryview) -> str:
    """Return an uppercase SHA-256 hex digest for a byte-like value."""

    return hashlib.sha256(bytes(value)).hexdigest().upper()


def sha256_stream(stream: BinaryIO, chunk_size: int = 1024 * 1024) -> str:
    """Hash from the stream's current position without closing the stream."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    digest = hashlib.sha256()
    while True:
        chunk = stream.read(chunk_size)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest().upper()


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    """Sequentially hash one file."""

    with Path(path).open("rb") as handle:
        return sha256_stream(handle, chunk_size)


def double_read_sha256(path: str | Path) -> tuple[str, str, bool]:
    """Perform two independent sequential file reads and compare them."""

    first = sha256_file(path)
    second = sha256_file(path)
    return first, second, hmac.compare_digest(first, second)


def canonical_json_sha256(value: Any) -> str:
    """Hash a stable UTF-8 JSON representation."""

    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256_bytes(payload)


def canonical_tar_path(member_name: str) -> str:
    """Validate and return one safe canonical POSIX tar member path.

    A directory's optional trailing slash is removed.  Backslashes, absolute
    or drive-qualified names, empty/dot/dot-dot components, repeated slashes,
    control characters, and any name changed by POSIX normalization are
    rejected rather than repaired.
    """

    if not isinstance(member_name, str):
        raise TypeError("tar member path must be text")
    if not member_name or "\x00" in member_name or "\\" in member_name:
        raise ValueError("empty, NUL, or backslash tar path")
    if member_name.endswith("//") or ":" in member_name:
        raise ValueError("repeated trailing slash or alternate-data-stream tar path")
    if any(ord(character) < 32 or ord(character) == 127 for character in member_name):
        raise ValueError("control character in tar path")
    if member_name.startswith("/") or re.match(r"^[A-Za-z]:", member_name):
        raise ValueError("absolute or drive-qualified tar path")

    candidate = member_name.rstrip("/")
    if not candidate:
        raise ValueError("tar root is not a member path")
    parts = candidate.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("non-canonical or escaping tar path")
    for part in parts:
        if part.endswith((".", " ")):
            raise ValueError("Windows trailing-dot/space tar path segment")
        basename = part.split(".", 1)[0].upper()
        if basename in WINDOWS_RESERVED_BASENAMES:
            raise ValueError("Windows reserved-device tar path segment")
        if unicodedata.normalize("NFC", part) != part:
            raise ValueError("tar path segment must use NFC normalization")
    normalized = posixpath.normpath(candidate)
    if normalized != candidate or normalized.startswith("../"):
        raise ValueError("non-canonical or escaping tar path")
    return normalized


def validate_canonical_tar_paths(member_names: Iterable[str]) -> tuple[str, ...]:
    """Validate an inventory and reject duplicate canonical member paths."""

    canonical: list[str] = []
    seen: set[str] = set()
    seen_casefolded: dict[str, str] = {}
    for member_name in member_names:
        value = canonical_tar_path(member_name)
        if value in seen:
            raise ValueError(f"duplicate canonical tar member: {value}")
        folded = unicodedata.normalize("NFC", value).casefold()
        if folded in seen_casefolded:
            raise ValueError(
                "case-insensitive tar member collision: "
                f"{seen_casefolded[folded]!r} and {value!r}"
            )
        seen.add(value)
        seen_casefolded[folded] = value
        canonical.append(value)
    return tuple(canonical)


@dataclass(frozen=True)
class CsvUuidSplitSeal:
    """The complete label-blind output of split CSV sealing."""

    parser_version: str
    source_sha256: tuple[tuple[str, str], ...]
    uuid_split_rows: tuple[tuple[str, str], ...]

    @property
    def unique_uuid_count(self) -> int:
        return len(self.uuid_split_rows)


def _validate_uuid(value: str) -> str:
    if not value or value != value.strip():
        raise ValueError("UUID must be nonempty and have no surrounding whitespace")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("control character in UUID")
    return value


def parse_uuid_split_seal(
    split_csv_bytes: Mapping[str, bytes],
    *,
    uuid_column: str = "uuid",
    expected_splits: Sequence[str] = ("train", "val", "test"),
) -> CsvUuidSplitSeal:
    """Seal raw CSV bytes while exposing only UUID and source split.

    The parser locates the UUID column but never constructs dictionaries for,
    returns, logs, or hashes individual label values.  The SHA seals bind the
    complete original bytes, including columns hidden from grouping.
    """

    split_order = tuple(expected_splits)
    if not split_order or len(set(split_order)) != len(split_order):
        raise ValueError("expected_splits must be unique and nonempty")
    if set(split_csv_bytes) != set(split_order):
        raise ValueError("split CSV keys must exactly match expected_splits")

    hashes: list[tuple[str, str]] = []
    uuid_to_split: dict[str, str] = {}
    for split in split_order:
        raw = split_csv_bytes[split]
        if not isinstance(raw, bytes):
            raise TypeError("CSV sources must be raw bytes for exact sealing")
        hashes.append((split, sha256_bytes(raw)))
        text = raw.decode("utf-8-sig", errors="strict")
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        try:
            header = next(reader)
        except StopIteration as error:
            raise ValueError(f"empty CSV for split {split}") from error
        if header.count(uuid_column) != 1:
            raise ValueError(f"split {split} must contain one {uuid_column!r} column")
        uuid_index = header.index(uuid_column)
        for line_number, row in enumerate(reader, start=2):
            if not row or all(value == "" for value in row):
                continue
            if len(row) != len(header):
                raise ValueError(f"malformed CSV row {line_number} in split {split}")
            uuid = _validate_uuid(row[uuid_index])
            previous = uuid_to_split.get(uuid)
            if previous is not None:
                raise ValueError(
                    f"UUID {uuid!r} is duplicated in {previous!r}/{split!r}"
                )
            uuid_to_split[uuid] = split

    rows = tuple(sorted(uuid_to_split.items(), key=lambda item: item[0]))
    return CsvUuidSplitSeal(
        parser_version="ARSC_DAADX_UUID_SPLIT_SEAL_V1",
        source_sha256=tuple(hashes),
        uuid_split_rows=rows,
    )


def deterministic_frame_timestamps(
    duration_seconds: float,
    *,
    first_seconds: float = 0.25,
    interval_seconds: float = 0.5,
) -> tuple[float, ...]:
    """Return frozen 2-Hz timestamps ``0.25 + 0.5*j < duration``.

    Videos shorter than one full sampling interval fail even if 0.25 seconds
    happens to lie inside them, as required by the Round 11 protocol.
    Decimal string conversion prevents cumulative binary-float drift.
    """

    values = (duration_seconds, first_seconds, interval_seconds)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("timestamp inputs must be finite")
    duration = Decimal(str(duration_seconds))
    first = Decimal(str(first_seconds))
    interval = Decimal(str(interval_seconds))
    if duration < interval or first < 0 or interval <= 0:
        raise ValueError("video is shorter than one interval or schedule is invalid")
    timestamps: list[float] = []
    current = first
    while current < duration:
        timestamps.append(float(current))
        current += interval
    if not timestamps:
        raise ValueError("sampling schedule produces no frame")
    return tuple(timestamps)


def _as_grayscale(image: np.ndarray) -> np.ndarray:
    array = np.asarray(image)
    if array.ndim == 2:
        grayscale = array.astype(np.float64)
    elif array.ndim == 3 and array.shape[2] in (3, 4):
        rgb = array[..., :3].astype(np.float64)
        grayscale = (
            0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
        )
    else:
        raise ValueError("image must be HxW grayscale or HxWx3/4 RGB(A)")
    if not grayscale.size or not np.isfinite(grayscale).all():
        raise ValueError("image must be nonempty and finite")
    if grayscale.min() < 0 or grayscale.max() > 255:
        raise ValueError("image values must lie in [0, 255]")
    return grayscale


def _resize_bilinear(grayscale: np.ndarray, height: int, width: int) -> np.ndarray:
    source = np.asarray(grayscale, dtype=np.float64)
    source_height, source_width = source.shape
    if height <= 0 or width <= 0:
        raise ValueError("resize dimensions must be positive")
    if (source_height, source_width) == (height, width):
        return source.copy()

    y = (np.arange(height) + 0.5) * source_height / height - 0.5
    x = (np.arange(width) + 0.5) * source_width / width - 0.5
    y = np.clip(y, 0, source_height - 1)
    x = np.clip(x, 0, source_width - 1)
    y0 = np.floor(y).astype(np.int64)
    x0 = np.floor(x).astype(np.int64)
    y1 = np.minimum(y0 + 1, source_height - 1)
    x1 = np.minimum(x0 + 1, source_width - 1)
    wy = (y - y0)[:, None]
    wx = (x - x0)[None, :]
    top = source[y0[:, None], x0[None, :]] * (1.0 - wx) + source[
        y0[:, None], x1[None, :]
    ] * wx
    bottom = source[y1[:, None], x0[None, :]] * (1.0 - wx) + source[
        y1[:, None], x1[None, :]
    ] * wx
    return top * (1.0 - wy) + bottom * wy


def grayscale_letterbox(
    image: np.ndarray,
    *,
    target_width: int = 256,
    target_height: int = 144,
    fill_value: int = 0,
) -> np.ndarray:
    """Aspect-ratio-preserving RGB-to-gray bilinear letterbox."""

    if target_width <= 0 or target_height <= 0 or not 0 <= fill_value <= 255:
        raise ValueError("invalid letterbox dimensions or fill value")
    grayscale = _as_grayscale(image)
    source_height, source_width = grayscale.shape
    scale = min(target_width / source_width, target_height / source_height)
    resized_width = max(1, min(target_width, int(math.floor(source_width * scale + 0.5))))
    resized_height = max(
        1, min(target_height, int(math.floor(source_height * scale + 0.5)))
    )
    resized = np.clip(
        np.rint(_resize_bilinear(grayscale, resized_height, resized_width)),
        0,
        255,
    ).astype(np.uint8)
    result = np.full((target_height, target_width), fill_value, dtype=np.uint8)
    top = (target_height - resized_height) // 2
    left = (target_width - resized_width) // 2
    result[top : top + resized_height, left : left + resized_width] = resized
    return result


@lru_cache(maxsize=4)
def _orthonormal_dct_matrix(size: int) -> np.ndarray:
    indices = np.arange(size, dtype=np.float64)
    frequencies = indices[:, None]
    matrix = np.cos(math.pi * (2 * indices + 1) * frequencies / (2 * size))
    matrix[0] *= math.sqrt(1.0 / size)
    matrix[1:] *= math.sqrt(2.0 / size)
    matrix.setflags(write=False)
    return matrix


def dct_phash64(grayscale_frame: np.ndarray) -> int:
    """Return the frozen 64-bit DCT pHash as an unsigned Python integer.

    The input is resized to 32x32, an orthonormal 2-D DCT is computed, and the
    top-left 8x8 coefficients are packed row-major.  The DC bit is forced to
    zero; the other 63 bits use a strict comparison to their median.
    """

    frame = np.asarray(grayscale_frame)
    if frame.shape != NORMALIZED_FRAME_SHAPE or frame.dtype != np.uint8:
        raise ValueError("pHash input must be a normalized 144x256 uint8 frame")
    grayscale = _as_grayscale(frame)
    resized = _resize_bilinear(grayscale, 32, 32)
    dct = _orthonormal_dct_matrix(32)
    # Keep this tiny transform independent of process-global BLAS/OpenMP
    # state.  Some Windows scientific stacks load incompatible MKL runtimes
    # after PyTorch; explicit 32-element reductions are deterministic and
    # avoid a native-process abort without changing the DCT definition.
    row_transform = np.sum(
        dct[:, :, None] * resized[None, :, :], axis=1
    )
    coefficients = np.sum(
        row_transform[:, None, :] * dct[None, :, :], axis=2
    )
    low = coefficients[:8, :8].copy()
    tolerance = np.finfo(np.float64).eps * max(abs(low[0, 0]), 1.0) * 64
    low[np.abs(low) < tolerance] = 0.0
    flattened = low.ravel()
    median = float(np.median(flattened[1:]))
    bits = flattened > median
    bits[0] = False
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return value


def phash_hamming(left: int, right: int) -> int:
    """Hamming distance between two unsigned 64-bit hashes."""

    left_value, right_value = int(left), int(right)
    limit = 1 << 64
    if not 0 <= left_value < limit or not 0 <= right_value < limit:
        raise ValueError("pHash values must be unsigned 64-bit integers")
    return (left_value ^ right_value).bit_count()


def normalized_frame_sha256(grayscale_frame: np.ndarray) -> str:
    """Hash an exact uint8 normalized grayscale frame including its shape."""

    frame = np.asarray(grayscale_frame)
    if frame.shape != NORMALIZED_FRAME_SHAPE or frame.dtype != np.uint8:
        raise ValueError("normalized frame must be a 144x256 uint8 array")
    shape = f"{frame.shape[0]}x{frame.shape[1]}|uint8|".encode("ascii")
    return sha256_bytes(shape + np.ascontiguousarray(frame).tobytes())


def _gaussian_filter(image: np.ndarray, window_size: int, sigma: float) -> np.ndarray:
    radius = window_size // 2
    coordinates = np.arange(-radius, radius + 1, dtype=np.float64)
    kernel = np.exp(-(coordinates**2) / (2.0 * sigma**2))
    kernel /= kernel.sum()
    padded_y = np.pad(image, ((radius, radius), (0, 0)), mode="reflect")
    vertical = sum(
        kernel[index] * padded_y[index : index + image.shape[0], :]
        for index in range(window_size)
    )
    padded_x = np.pad(vertical, ((0, 0), (radius, radius)), mode="reflect")
    return sum(
        kernel[index] * padded_x[:, index : index + image.shape[1]]
        for index in range(window_size)
    )


def grayscale_ssim(
    left: np.ndarray,
    right: np.ndarray,
    *,
    data_range: float = 255.0,
    window_size: int = 11,
    sigma: float = 1.5,
) -> float:
    """Gaussian-window grayscale SSIM without scipy or skimage."""

    left_array = np.asarray(left)
    right_array = np.asarray(right)
    if (
        left_array.shape != NORMALIZED_FRAME_SHAPE
        or right_array.shape != NORMALIZED_FRAME_SHAPE
        or left_array.dtype != np.uint8
        or right_array.dtype != np.uint8
    ):
        raise ValueError("SSIM inputs must be normalized 144x256 uint8 frames")
    left_gray = _as_grayscale(left_array)
    right_gray = _as_grayscale(right_array)
    if left_gray.shape != right_gray.shape:
        raise ValueError("SSIM inputs must have identical shapes")
    if min(left_gray.shape) < 2:
        raise ValueError("SSIM inputs must be at least 2x2")
    if window_size < 3 or window_size % 2 == 0 or sigma <= 0 or data_range <= 0:
        raise ValueError("invalid SSIM window, sigma, or data range")

    mean_left = _gaussian_filter(left_gray, window_size, sigma)
    mean_right = _gaussian_filter(right_gray, window_size, sigma)
    variance_left = _gaussian_filter(left_gray * left_gray, window_size, sigma) - mean_left**2
    variance_right = (
        _gaussian_filter(right_gray * right_gray, window_size, sigma) - mean_right**2
    )
    covariance = _gaussian_filter(left_gray * right_gray, window_size, sigma) - mean_left * mean_right
    variance_left = np.maximum(variance_left, 0.0)
    variance_right = np.maximum(variance_right, 0.0)
    c1 = (0.01 * data_range) ** 2
    c2 = (0.03 * data_range) ** 2
    numerator = (2 * mean_left * mean_right + c1) * (2 * covariance + c2)
    denominator = (mean_left**2 + mean_right**2 + c1) * (
        variance_left + variance_right + c2
    )
    score = float(np.mean(numerator / denominator))
    return float(np.clip(score, -1.0, 1.0))


@dataclass(frozen=True)
class EdgeDecision:
    matched: bool
    rule: str
    start_pair: int | None = None
    end_pair_exclusive: int | None = None
    pair_count: int = 0
    time_scale_slope: float | None = None
    median_hamming: float | None = None
    median_ssim: float | None = None


def _aligned_inputs(
    times_a: Sequence[float],
    times_b: Sequence[float],
    hamming_distances: Sequence[int],
    ssim_values: Sequence[float],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    arrays = tuple(
        np.asarray(value)
        for value in (times_a, times_b, hamming_distances, ssim_values)
    )
    if any(array.ndim != 1 for array in arrays):
        raise ValueError("aligned-pair inputs must be one-dimensional")
    if len({len(array) for array in arrays}) != 1:
        raise ValueError("aligned-pair inputs must have equal lengths")
    a, b, hamming_values, ssim_scores = arrays
    if not all(np.isfinite(array.astype(np.float64)).all() for array in arrays):
        raise ValueError("aligned-pair inputs must be finite")
    if len(a) and (np.any(np.diff(a.astype(float)) <= 0) or np.any(np.diff(b.astype(float)) <= 0)):
        raise ValueError("aligned timestamps must be strictly increasing")
    if np.any(hamming_values < 0) or np.any(hamming_values > 64) or not np.equal(
        hamming_values, np.floor(hamming_values)
    ).all():
        raise ValueError("Hamming distances must be integers in [0, 64]")
    if np.any(ssim_scores < -1) or np.any(ssim_scores > 1):
        raise ValueError("SSIM values must lie in [-1, 1]")
    return a.astype(float), b.astype(float), hamming_values.astype(int), ssim_scores.astype(float)


def aligned_window_edge(
    times_a: Sequence[float],
    times_b: Sequence[float],
    hamming_distances: Sequence[int],
    ssim_values: Sequence[float],
    *,
    strict: bool = False,
) -> EdgeDecision:
    """Determine whether any ordered aligned window meets broad/strict rules.

    Supplied pairs are assumed to be consecutive candidates from the upstream
    aligner.  This function independently checks order, time-scale slope, all
    distance thresholds, and window medians.  It searches all windows of six
    or more pairs and reports the longest/best deterministic match.
    """

    a, b, hamming_values, ssim_scores = _aligned_inputs(
        times_a, times_b, hamming_distances, ssim_values
    )
    rule = "NEAR_OVERLAP_STRICT" if strict else "NEAR_OVERLAP_BROAD"
    each_limit = 6 if strict else 10
    median_limit = 4 if strict else 6
    ssim_minimum = 0.95 if strict else 0.90
    candidates: list[EdgeDecision] = []
    interval_tolerance = 1e-9
    for start in range(len(a)):
        for end in range(start + 6, len(a) + 1):
            distances = hamming_values[start:end]
            if np.any(distances > each_limit):
                break
            if (
                not np.allclose(np.diff(a[start:end]), 0.5, rtol=0.0, atol=interval_tolerance)
                or not np.allclose(
                    np.diff(b[start:end]), 0.5, rtol=0.0, atol=interval_tolerance
                )
            ):
                continue
            span_a = a[end - 1] - a[start]
            span_b = b[end - 1] - b[start]
            if span_a <= 0:
                continue
            slope = span_b / span_a
            if not 0.98 <= slope <= 1.02:
                continue
            median_hamming = float(np.median(distances))
            median_ssim = float(np.median(ssim_scores[start:end]))
            if median_hamming <= median_limit and median_ssim >= ssim_minimum:
                candidates.append(
                    EdgeDecision(
                        matched=True,
                        rule=rule,
                        start_pair=start,
                        end_pair_exclusive=end,
                        pair_count=end - start,
                        time_scale_slope=float(slope),
                        median_hamming=median_hamming,
                        median_ssim=median_ssim,
                    )
                )
    if not candidates:
        return EdgeDecision(matched=False, rule=rule)
    return min(
        candidates,
        key=lambda item: (
            -item.pair_count,
            item.median_hamming,
            -item.median_ssim,
            item.start_pair,
            item.end_pair_exclusive,
        ),
    )


def boundary_continuation_edge(
    tail_times: Sequence[float],
    head_times: Sequence[float],
    hamming_distances: Sequence[int],
    ssim_values: Sequence[float],
    *,
    tail_rig_signature: str,
    head_rig_signature: str,
) -> EdgeDecision:
    """Apply the frozen three-pair broad tail-to-head boundary rule."""

    tail = np.asarray(tail_times, dtype=float)
    head = np.asarray(head_times, dtype=float)
    hamming_values = np.asarray(hamming_distances)
    ssim_scores = np.asarray(ssim_values, dtype=float)
    rule = "BOUNDARY_CONTINUATION_BROAD"
    if (
        tail.ndim != 1
        or head.ndim != 1
        or hamming_values.ndim != 1
        or ssim_scores.ndim != 1
        or len(tail) != 3
        or len(head) != 3
        or len(hamming_values) != 3
        or len(ssim_scores) != 3
    ):
        raise ValueError("boundary rule requires exactly three ordered pairs")
    if (
        not np.isfinite(tail).all()
        or not np.isfinite(head).all()
        or not np.allclose(np.diff(tail), 0.5, rtol=0.0, atol=1e-9)
        or not np.allclose(np.diff(head), 0.5, rtol=0.0, atol=1e-9)
    ):
        raise ValueError("boundary pairs must be consecutive frozen 0.5-second samples")
    if np.any(hamming_values < 0) or np.any(hamming_values > 64) or not np.equal(
        hamming_values, np.floor(hamming_values)
    ).all():
        raise ValueError("Hamming distances must be integers in [0, 64]")
    if not np.isfinite(ssim_scores).all() or np.any(ssim_scores < -1) or np.any(ssim_scores > 1):
        raise ValueError("SSIM values must be finite and in [-1, 1]")
    same_signature = bool(tail_rig_signature) and hmac.compare_digest(
        tail_rig_signature, head_rig_signature
    )
    median_hamming = float(np.median(hamming_values))
    median_ssim = float(np.median(ssim_scores))
    matched = bool(
        same_signature
        and np.all(hamming_values <= 10)
        and median_hamming <= 6
        and median_ssim >= 0.90
    )
    return EdgeDecision(
        matched=matched,
        rule=rule,
        start_pair=0 if matched else None,
        end_pair_exclusive=3 if matched else None,
        pair_count=3 if matched else 0,
        median_hamming=median_hamming,
        median_ssim=median_ssim,
    )


def connected_components(
    nodes: Iterable[str], edges: Iterable[tuple[str, str]]
) -> tuple[tuple[str, ...], ...]:
    """Return deterministic undirected connected components, including singletons."""

    ordered_nodes = tuple(nodes)
    if len(set(ordered_nodes)) != len(ordered_nodes):
        raise ValueError("graph nodes must be unique")
    if any(not isinstance(node, str) or not node for node in ordered_nodes):
        raise ValueError("graph nodes must be nonempty strings")
    parent = {node: node for node in ordered_nodes}

    def find(node: str) -> str:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root == right_root:
            return
        if left_root < right_root:
            parent[right_root] = left_root
        else:
            parent[left_root] = right_root

    for edge in edges:
        if len(edge) != 2:
            raise ValueError("each edge must have exactly two endpoints")
        left, right = edge
        if left not in parent or right not in parent:
            raise ValueError("edge endpoint is absent from graph nodes")
        union(left, right)

    groups: dict[str, list[str]] = {}
    for node in ordered_nodes:
        groups.setdefault(find(node), []).append(node)
    components = [tuple(sorted(members)) for members in groups.values()]
    return tuple(sorted(components))


def canonical_group_id(members: Iterable[str]) -> str:
    """SHA-256 of the canonical JSON encoding of a sorted UUID list."""

    ordered = tuple(sorted(members))
    if not ordered or len(set(ordered)) != len(ordered):
        raise ValueError("group members must be nonempty and unique")
    if any(not isinstance(member, str) or not member for member in ordered):
        raise ValueError("group members must be nonempty strings")
    return canonical_json_sha256(list(ordered))


def salted_public_group_id(members: Iterable[str], secret_salt: bytes) -> str:
    """Create a non-reversible public ID using HMAC-SHA256 and a secret salt."""

    if not isinstance(secret_salt, bytes) or len(secret_salt) < 16:
        raise ValueError("secret_salt must contain at least 16 bytes")
    canonical = canonical_group_id(members).encode("ascii")
    digest = hmac.new(secret_salt, canonical, hashlib.sha256).hexdigest().upper()
    return f"DAADX-G-{digest}"


@dataclass(frozen=True)
class GroupSplitAssignment:
    canonical_group_id: str
    split: str
    hash_uniform: float
    group_size: int


def split_for_canonical_group_id(group_id: str) -> tuple[str, float]:
    """Apply the one frozen namespace and 70/20/10 group split."""

    if not re.fullmatch(r"[0-9A-Fa-f]{64}", group_id):
        raise ValueError("canonical group ID must be 64 hexadecimal characters")
    digest = hashlib.sha256(
        f"{GROUP_SPLIT_NAMESPACE}|{group_id.upper()}".encode("ascii")
    ).digest()
    value = int.from_bytes(digest[:8], byteorder="big", signed=False)
    denominator = 1 << 64
    if 10 * value < 7 * denominator:
        split = "train"
    elif 10 * value < 9 * denominator:
        split = "validation"
    else:
        split = "test"
    return split, value / denominator


def fixed_one_salt_group_split(
    groups: Iterable[Iterable[str]],
) -> tuple[GroupSplitAssignment, ...]:
    """Assign every disjoint group once; no alternate salt or swaps exist."""

    assignments: list[GroupSplitAssignment] = []
    seen_members: set[str] = set()
    for group in groups:
        members = tuple(group)
        overlap = seen_members.intersection(members)
        if overlap:
            raise ValueError("groups overlap on one or more UUIDs")
        seen_members.update(members)
        group_id = canonical_group_id(members)
        split, uniform = split_for_canonical_group_id(group_id)
        assignments.append(
            GroupSplitAssignment(group_id, split, uniform, len(members))
        )
    return tuple(sorted(assignments, key=lambda item: item.canonical_group_id))


class GateStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class GateVerdict:
    gate_statuses: tuple[tuple[str, str], ...]
    passed_gates: tuple[str, ...]
    failed_gates: tuple[str, ...]
    inconclusive_gates: tuple[str, ...]
    all_gates_passed: bool
    verdict: str
    training_authorized: bool = False


def aggregate_gate_verdicts(
    gate_statuses: Mapping[str, GateStatus | str],
) -> GateVerdict:
    """Aggregate G0-G8 with AND logic; missing information is inconclusive."""

    unexpected = set(gate_statuses) - set(EXPECTED_GATE_IDS)
    if unexpected:
        raise ValueError(f"unexpected gate IDs: {sorted(unexpected)}")
    normalized: list[tuple[str, str]] = []
    for gate_id in EXPECTED_GATE_IDS:
        raw_status = gate_statuses.get(gate_id, GateStatus.INCONCLUSIVE)
        try:
            status = raw_status if isinstance(raw_status, GateStatus) else GateStatus(str(raw_status).upper())
        except ValueError as error:
            raise ValueError(f"invalid status for {gate_id}: {raw_status!r}") from error
        normalized.append((gate_id, status.value))
    passed = tuple(gate for gate, status in normalized if status == GateStatus.PASS.value)
    failed = tuple(gate for gate, status in normalized if status == GateStatus.FAIL.value)
    inconclusive = tuple(
        gate for gate, status in normalized if status == GateStatus.INCONCLUSIVE.value
    )
    all_passed = len(passed) == len(EXPECTED_GATE_IDS)
    return GateVerdict(
        gate_statuses=tuple(normalized),
        passed_gates=passed,
        failed_gates=failed,
        inconclusive_gates=inconclusive,
        all_gates_passed=all_passed,
        verdict=GO_VERDICT if all_passed else STOP_VERDICT,
        training_authorized=False,
    )
