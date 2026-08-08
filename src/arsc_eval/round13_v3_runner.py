"""Neutral, read-only, preclaim evidence collector for Round 13 V3.

This module collects deterministic, canonical-neutral *preclaim evidence* only.
It exists so a future claim moment can prove that, at evidence-collection time,
the fixed committed V3 protocol, the fixed runner/tests sources, and the fixed
dependency manifests were all present, tracked, and clean under the actual Git
HEAD commit, and that no formal artifact already existed.  It deliberately has
no launcher, no GO approval semantics, no claim construction, no formal
results/verdict/index publication, no metric computation, and no writer of any
kind.

The single public entry point is ``collect_preclaim_evidence(root)``.  It takes
no GO input and performs zero writes, returning a canonical, result-blind dict
that declares the run "not run" and claims no authority.  Because this is
preclaim evidence and not a claim, the returned dict contains no approval,
claim, or decision fields.

Naming / public API policy:

* ``GOExpected``, ``RuntimeBinding``, and ``FileSnapshot`` are removed from the
  public API.  The internal snapshot and binding records are private
  (``_FileSnapshot``, ``_RuntimeBinding``).
* ``validate_go_payload``, ``build_claim_payload``, and
  ``validate_preclaim(go_path/go_bytes)`` are removed.  No GO approval or claim
  construction semantics, and no arbitrary GO path, remain.
* ``__all__`` exposes only neutral evidence/canonical/read helpers and
  constants.  No injectable binding, GO validator, or claim builder is
  exported.

Read-safety note: the stable-read helpers are *leaf-stable* — they read one
regular single-link leaf file with no-follow and identity drift checks — but
they do not and cannot guarantee directory-tree atomicity on a hostile or
mutating filesystem.  In particular, ``collect_preclaim_evidence`` is not
TOCTOU-proof against a concurrent writer.  Evidence must therefore be
recomputed at the future claim moment (ideally under a Win32 directory lease)
rather than replayed from an earlier collection.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

# ---------------------------------------------------------------------------
# (A) Frozen V3 protocol / evidence constants (from the committed V3 draft).
# ---------------------------------------------------------------------------
PROTOCOL_REL = "outputs/validity/round13_synthetic_mtmm_v3_frozen_protocol.json"
PROTOCOL_SHA256 = (
    "EC1A453172C729A3780BC894C9B09317121547E17FBFA4C616FE73F7C86CF18F"
)
PROTOCOL_SCHEMA = "arsc-round13-synthetic-mtmm-protocol-v3"
FORMAL_ATTEMPT = "round13_attempt03"

# Neutral preclaim evidence schema.  This evidence is not a claim: the run is
# declared not-run and no authority is claimed.  The schema bytes never contain
# approval/claim/decision/go fields.
EVIDENCE_SCHEMA = "ARSC_ROUND13_SYNTHETIC_MTMM_PREFLIGHT_EVIDENCE_V3"
EVIDENCE_STATUS = "AWAIT_EXTERNAL_AUTHORIZATION_V3"

# Fixed implementation scope for the evidence: the runner/tests source
# snapshots and the dependency manifests are derived from these constants.
RUNNER_REL = "src/arsc_eval/round13_v3_runner.py"
TESTS_REL = "tests/test_round13_v3_runner.py"
REQUIREMENTS_REL = "requirements.txt"
REQUIREMENTS_DEV_REL = "requirements-dev.txt"

# Fixed files that must be tracked and clean under the actual Git HEAD for the
# evidence to be valid.  Used by the read-only git closure checks.
FIXED_TRACKED_FILES = (
    PROTOCOL_REL,
    RUNNER_REL,
    TESTS_REL,
    REQUIREMENTS_REL,
    REQUIREMENTS_DEV_REL,
)

# Fixed one-shot constants from the frozen V3 protocol used only for protocol
# validation (never emitted into the evidence schema).
CLAIM_SCHEMA = "ARSC_ROUND13_SYNTHETIC_MTMM_CLAIM_V3"
FORMAL_CLAIM_NAME = "round13_synthetic_mtmm_v3_formal_claim.json"
FORMAL_RESULTS_NAME = "round13_synthetic_mtmm_v3_results.json"
FORMAL_VERDICT_NAME = "round13_synthetic_mtmm_v3_verdict.json"
FORMAL_INDEX_NAME = "round13_synthetic_mtmm_v3_artifact_index.json"
CLAIM_PATH_REL = Path("outputs/validity") / FORMAL_CLAIM_NAME

# Legacy V1/V2 formal artifacts that must all be absent before V3 evidence can
# be collected.
V1_LEGACY_FORMAL_NAMES = (
    "round13_synthetic_mtmm_formal_claim.json",
    "round13_synthetic_mtmm_results.json",
    "round13_synthetic_mtmm_verdict.json",
    "round13_synthetic_mtmm_artifact_index.json",
)
V2_LEGACY_FORMAL_NAMES = (
    "round13_synthetic_mtmm_v2_formal_claim.json",
    "round13_synthetic_mtmm_v2_results.json",
    "round13_synthetic_mtmm_v2_verdict.json",
    "round13_synthetic_mtmm_v2_artifact_index.json",
)

# Permanent V3 formal artifact names (see (A)).
V3_FORMAL_NAMES = (
    FORMAL_CLAIM_NAME,
    FORMAL_RESULTS_NAME,
    FORMAL_VERDICT_NAME,
    FORMAL_INDEX_NAME,
)

# V3 candidate / staging / temp suffixes that must never exist at evidence
# collection.
V3_TEMP_SUFFIXES = (".candidate.tmp", ".candidate", ".staging", ".partial", ".tmp")


class V3RunnerError(RuntimeError):
    """Any fail-closed V3 preclaim invariant violation."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise V3RunnerError(message)


# ---------------------------------------------------------------------------
# Canonical / digest helpers (compact canonical JSON, sort_keys, separators).
# ---------------------------------------------------------------------------
def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def normalize_hex256(value: str, label: str) -> str:
    require(
        isinstance(value, str) and len(value) == 64,
        f"{label} must be 64 hexadecimal characters",
    )
    try:
        int(value, 16)
    except (TypeError, ValueError):
        raise V3RunnerError(f"{label} is not hexadecimal") from None
    return value.upper()


def normalize_commit(value: str, label: str) -> str:
    """Require a 40-character hexadecimal Git object id and normalize case."""
    require(
        isinstance(value, str) and len(value) == 40,
        f"{label} must be a 40-character hexadecimal Git object id",
    )
    try:
        int(value, 16)
    except (TypeError, ValueError):
        raise V3RunnerError(f"{label} is not a hexadecimal Git object id") from None
    return value.lower()


# ---------------------------------------------------------------------------
# (B) Lexical (never OS-resolved) path helpers.  These reject symlink/reparse
#     and non-directory ancestors and never follow symlinks.
# ---------------------------------------------------------------------------
_REPARSE_ATTRIBUTE = 0x400  # Windows FILE_ATTRIBUTE_REPARSE_POINT


def _require_absolute(path: Path, label: str) -> None:
    require(isinstance(path, Path), f"{label} must be a Path")
    require(path.is_absolute(), f"{label} must be an absolute path")


def _is_reparse(path: Path) -> bool:
    """Report a Windows reparse point (symlink, junction, etc.) without
    following it.  On non-Windows always False; POSIX symlinks are handled
    separately via ``lstat`` ``S_ISLNK``."""
    if os.name != "nt":
        return False
    try:
        current = os.lstat(path)
        if getattr(current, "st_file_attributes", 0) & _REPARSE_ATTRIBUTE:
            return True
    except OSError:
        return False
    try:
        import ctypes

        attributes = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        return bool(attributes != -1 and (attributes & _REPARSE_ATTRIBUTE))
    except (ImportError, AttributeError, OSError):
        return False


def _require_real_dir(path: Path, label: str) -> None:
    """Require a real directory: non-symlink, non-reparse, not a file."""
    try:
        current = os.lstat(path)
    except OSError as error:
        raise V3RunnerError(f"{label} directory cannot be stat'd: {path}") from error
    require(not stat.S_ISLNK(current.st_mode), f"{label} must not be a symlink: {path}")
    require(stat.S_ISDIR(current.st_mode), f"{label} is not a directory: {path}")
    require(not _is_reparse(path), f"{label} must not be a reparse point: {path}")


def lexical_path(root: Path, rel: str, *, label: str) -> Path:
    """Return the lexical (never OS-resolved) absolute ``root/rel`` path.

    Requires an absolute ``root`` and a clean relative ``rel`` and rejects any
    ``..``/absolute/over-long component.  ``root`` and every intermediate
    directory component must be a real (non-symlink, non-reparse) directory,
    and the final target must not be a symlink or reparse point.
    """
    _require_absolute(root, "root")
    require(isinstance(rel, str) and rel, f"{label} path must be a non-empty string")
    normalized = rel.replace("\\", "/")
    require(not normalized.startswith("/"), f"{label} path must be relative")
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    require(parts and not normalized.endswith("/"), f"{label} path is malformed")
    require(all(part != ".." for part in parts), f"{label} path escapes root")

    _require_real_dir(root, "root")
    current = root
    for component in parts[:-1]:
        current = current / component
        _require_real_dir(current, label)
    target = current / parts[-1]
    try:
        result = os.lstat(target)
        require(
            not stat.S_ISLNK(result.st_mode),
            f"{label} target must not be a symlink: {target}",
        )
        require(not _is_reparse(target), f"{label} target must not be a reparse point: {target}")
    except FileNotFoundError:
        pass
    except OSError as error:
        raise V3RunnerError(f"{label} target cannot be stat'd: {target}") from error
    return target


# ---------------------------------------------------------------------------
# (B) Pure no-follow stable-read helpers (fail closed, TOCTOU-safe).
# ---------------------------------------------------------------------------
def _identity(metadata: os.stat_result) -> tuple[int, int, int]:
    return metadata.st_dev, metadata.st_ino, metadata.st_nlink


def _require_regular_no_follow(path: Path, label: str) -> None:
    """Reject symlink/reparse, non-regular, or hard-linked paths."""
    try:
        current = os.lstat(path)
    except OSError as error:
        raise V3RunnerError(f"{label} path cannot be stat'd: {path}") from error
    require(not stat.S_ISLNK(current.st_mode), f"{label} must not be a symlink")
    require(
        stat.S_ISREG(current.st_mode),
        f"{label} is not a regular file: {path}",
    )
    require(current.st_nlink == 1, f"{label} must not be hard-linked")
    require(not _is_reparse(path), f"{label} must not be a reparse point")


def _require_open_identity(descriptor: int, path: Path, label: str) -> None:
    opened = os.fstat(descriptor)
    try:
        current = os.lstat(path)
    except OSError as error:
        raise V3RunnerError(f"{label} path disappeared or changed") from error
    require(stat.S_ISREG(opened.st_mode), f"{label} open handle is not regular")
    require(
        stat.S_ISREG(current.st_mode) and not stat.S_ISLNK(current.st_mode),
        f"{label} path is not a regular file",
    )
    require(_identity(opened) == _identity(current), f"{label} path/inode changed")
    require(opened.st_nlink == 1, f"{label} must not be hard-linked")
    require(not _is_reparse(path), f"{label} must not be a reparse point")


def _stable_read_descriptor(
    descriptor: int, path: Path, *, expected_size: int | None
) -> tuple[bytes, int, str]:
    """Read a single, stable, regular, single-link descriptor.

    When ``expected_size`` is provided the total byte count must match it;
    otherwise the actual count is returned.  In both cases identity drift and
    mid-read mutation are rejected and the returned (bytes, size, sha256) are
    the canonical result.
    """
    before = os.fstat(descriptor)
    _require_open_identity(descriptor, path, "stable read")
    require(
        expected_size is None or before.st_size == expected_size,
        "stable file size drift",
    )
    digest = hashlib.sha256()
    chunks: list[bytes] = []
    count = 0
    while True:
        block = os.read(descriptor, 1_048_576)
        if not block:
            break
        count += len(block)
        require(
            expected_size is None or count <= expected_size,
            "stable file exceeds declared size",
        )
        chunks.append(block)
        digest.update(block)
    require(
        expected_size is None or count == expected_size,
        "stable file byte count drift",
    )
    after = os.fstat(descriptor)
    _require_open_identity(descriptor, path, "stable read")
    require(
        (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        == (after.st_size, after.st_mtime_ns, after.st_ctime_ns),
        "stable file changed while being read",
    )
    return b"".join(chunks), count, digest.hexdigest().upper()


def stable_read_bytes_actual(path: Path) -> tuple[bytes, int, str]:
    """Read an exact, stable, regular, single-link file and return its raw
    bytes, byte count, and upper-hex SHA-256.  Fails closed on symlink/reparse,
    non-regular, hard-link, or identity drift.  No expected digest required."""
    _require_regular_no_follow(path, "stable read")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags)
    try:
        return _stable_read_descriptor(descriptor, path, expected_size=None)
    finally:
        os.close(descriptor)


def stable_read_bytes(
    path: Path,
    *,
    expected_size: int,
    expected_sha256: str,
) -> bytes:
    """Read an exact, stable, regular, single-link file that matches the
    declared size + SHA-256.  Fails closed on symlink/reparse, non-regular,
    hard-link, identity drift, size/hash drift, or mid-read mutation."""
    require(isinstance(expected_size, int) and expected_size >= 0, "expected size is invalid")
    require(
        isinstance(expected_sha256, str) and len(expected_sha256) == 64,
        "expected SHA-256 is invalid",
    )
    _require_regular_no_follow(path, "stable read")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags)
    try:
        raw, count, digest = _stable_read_descriptor(
            descriptor, path, expected_size=expected_size
        )
        require(
            digest == normalize_hex256(expected_sha256, "expected SHA"),
            "stable file hash drift",
        )
        return raw
    finally:
        os.close(descriptor)


def verify_canonical_json_object(raw: bytes, label: str) -> Mapping[str, Any]:
    """Require that ``raw`` is a canonical, compact JSON object.

    Fails closed on type drift (non-object), duplicate keys, non-canonical
    encoding, and NaN/Infinity.
    """

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            require(key not in result, f"{label} contains duplicate JSON key: {key}")
            result[key] = item
        return result

    try:
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise V3RunnerError(f"{label} is not valid JSON") from error
    require(isinstance(parsed, Mapping), f"{label} must be a JSON object")
    require(raw == canonical_json_bytes(parsed), f"{label} JSON is not canonical")
    return parsed


# ---------------------------------------------------------------------------
# (C) Read-only git closure + evidence binding derived from the repository and
#     the running interpreter.  All records here are private; nothing injectable
#     is exposed via ``__all__``.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class _FileSnapshot:
    path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class _RuntimeBinding:
    protocol_path: str
    protocol_sha256: str
    protocol_size: int
    implementation_commit: str
    runner: _FileSnapshot
    tests: _FileSnapshot
    requirements: _FileSnapshot
    requirements_dev: _FileSnapshot
    python_executable: _FileSnapshot
    python_version: str
    installed_distributions_sha: str
    git_executable: _FileSnapshot


@dataclass(frozen=True)
class _GitExec:
    """Resolved, real, non-reparse absolute git executable and its stable
    no-follow snapshot for evidence."""

    path: Path
    snapshot: _FileSnapshot


def _null_device() -> str:
    """The OS null device path used for core.hooksPath / GIT_CONFIG_GLOBAL."""
    return "NUL" if os.name == "nt" else "/dev/null"


def _require_no_ambient_git_vars() -> None:
    """Fail closed if any ambient environment variable name starts with ``GIT_``
    (case-insensitive).  Called before any git subprocess so a caller-controlled
    ``GIT_DIR`` / ``GIT_WORK_TREE`` / hook pointer can never leak in."""
    offenders = [name for name in os.environ if name.upper().startswith("GIT_")]
    require(
        not offenders,
        f"ambient GIT_ environment variable present: {', '.join(sorted(offenders))}",
    )


def _minimal_git_env() -> dict[str, str]:
    """Build the minimal whitelist environment for read-only git calls."""
    allowed = {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "TEMP",
        "TMP",
    }
    env: dict[str, str] = {}
    for name in allowed:
        if name in os.environ:
            env[name] = os.environ[name]
    env["LC_ALL"] = "C"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = _null_device()
    env["GIT_NO_REPLACE_OBJECTS"] = "1"
    env["GIT_NO_LAZY_FETCH"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _resolve_git_executable() -> _GitExec:
    """Resolve ``git`` once via ``shutil.which`` on PATH.  The result must be an
    absolute, regular, non-reparse (non-symlink) file; it is then stable-read
    with a no-follow snapshot for neutral evidence."""
    resolved = shutil.which("git")
    require(isinstance(resolved, str) and resolved, "git executable not found on PATH")
    git_path = Path(os.path.abspath(resolved))
    _require_regular_no_follow(git_path, "git executable")
    _raw, size, sha = stable_read_bytes_actual(git_path)
    return _GitExec(
        path=git_path,
        snapshot=_FileSnapshot(path=str(git_path), size=size, sha256=sha),
    )


def _git_cmd(root: Path, git: _GitExec, args: Sequence[str]) -> list[str]:
    """Read-only git argv with the absolute executable, no-pager / no-locks, the
    lexical ``--git-dir`` / ``--work-tree``, and all hostile features disabled."""
    git_dir = os.path.join(str(root), ".git")
    hooks = _null_device()
    return [
        str(git.path),
        "--no-pager",
        "--no-optional-locks",
        f"--git-dir={git_dir}",
        f"--work-tree={str(root)}",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.untrackedCache=false",
        "-c",
        f"core.hooksPath={hooks}",
        "-c",
        "diff.external=",
        "-c",
        "pager.status=false",
        "-c",
        "pager.diff=false",
        *args,
    ]


def _installed_distributions_manifest() -> Sequence[tuple[str, str]]:
    """Return installed distributions as ``(name, version)`` pairs, sorted by
    casefold ``name`` then ``version``.  Isolated behind a module function so
    tests can substitute a deterministic provider."""
    import importlib.metadata as metadata

    pairs: list[tuple[str, str]] = []
    for distribution in metadata.distributions():
        meta = distribution.metadata or {}
        name = (meta.get("Name") or "").strip()
        version = (distribution.version or "").strip()
        pairs.append((name, version))
    pairs.sort(key=lambda item: (item[0].casefold(), item[1].casefold()))
    return pairs


def installed_distributions_sha() -> str:
    """Deterministic SHA-256 of the installed-distributions manifest."""
    lines = [f"{name}=={version}" for name, version in _installed_distributions_manifest()]
    return sha256_bytes("\n".join(lines).encode("utf-8"))


# ---------------------------------------------------------------------------
# Read-only git closure.  All git commands run as read-only subprocesses with a
# fixed working directory equal to ``root``.  Nothing is written or mutated.
# ---------------------------------------------------------------------------
def _require_empty_replace_refs(root: Path) -> None:
    """Fail closed unless ``root/.git/refs/replace`` is absent or an empty,
    real, non-reparse (non-symlink) directory.

    Any git ``refs/replace`` entry rewrites object lookups (e.g. ``HEAD``)
    under the hood, so even though the subprocess env sets
    ``GIT_NO_REPLACE_OBJECTS=1`` the lexical replacement-refs tree is inspected
    before any git subprocess and must be empty.  A non-directory, a symlink, a
    reparse point, or any entry fails closed.
    """
    label = ".git/refs/replace"
    replace = lexical_path(root, label, label=label)
    if not os.path.lexists(replace):
        return
    _require_real_dir(replace, label)
    entries = sorted(os.listdir(replace))
    require(
        not entries,
        f"{label} must be empty but contains replacement refs: {', '.join(entries)}",
    )


def _git_run(
    root: Path, git: _GitExec, args: Sequence[str]
) -> subprocess.CompletedProcess[str]:
    _require_no_ambient_git_vars()
    _require_empty_replace_refs(root)
    env = _minimal_git_env()
    return subprocess.run(
        _git_cmd(root, git, args),
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _git_run_bytes(
    root: Path, git: _GitExec, args: Sequence[str]
) -> subprocess.CompletedProcess[bytes]:
    """Read-only git subprocess with binary stdout/stderr (no text conversion)
    for plumbing commands whose output is opaque bytes (e.g. ``cat-file blob``).
    Env hardening and replace-ref refusal are identical to ``_git_run``."""
    _require_no_ambient_git_vars()
    _require_empty_replace_refs(root)
    env = _minimal_git_env()
    return subprocess.run(
        _git_cmd(root, git, args),
        cwd=str(root),
        capture_output=True,
        text=False,
        check=False,
        env=env,
    )


def _git_rev_parse_commit(root: Path, git: _GitExec) -> str:
    """Return the exact 40-hex commit at ``HEAD`` or fail closed."""
    result = _git_run(root, git, ["rev-parse", "--verify", "HEAD^{commit}"])
    if result.returncode != 0:
        raise V3RunnerError(
            f"git rev-parse failed for {root}: {result.stderr.strip()}"
        )
    return normalize_commit(result.stdout.strip(), "git HEAD commit")


def _git_show_toplevel(root: Path, git: _GitExec) -> str:
    """Return the normalized absolute top-level work-tree path, or fail closed."""
    result = _git_run(root, git, ["rev-parse", "--show-toplevel"])
    if result.returncode != 0:
        raise V3RunnerError(
            f"git rev-parse --show-toplevel failed for {root}: {result.stderr.strip()}"
        )
    toplevel = result.stdout.strip()
    if not toplevel:
        raise V3RunnerError(f"git rev-parse --show-toplevel returned empty for {root}")
    return os.path.normcase(os.path.normpath(toplevel))


def _git_cat_file_type(root: Path, git: _GitExec, commit: str) -> str:
    result = _git_run(root, git, ["cat-file", "-t", commit])
    if result.returncode != 0:
        raise V3RunnerError(f"git cat-file failed for {root}: {result.stderr.strip()}")
    return result.stdout.strip()


def _git_cat_file_blob(root: Path, git: _GitExec, rev: str) -> bytes:
    """Read a single blob object's raw bytes via ``git cat-file blob`` with the
    hardened argv/env and binary stdout (no text conversion, no filter).  Fails
    closed on a nonzero exit."""
    result = _git_run_bytes(root, git, ["cat-file", "blob", rev])
    if result.returncode != 0:
        error = result.stderr.decode("utf-8", "replace").strip()
        raise V3RunnerError(f"git cat-file blob failed for {root}: {error}")
    return result.stdout


def _git_ls_files_error_unmatch(root: Path, git: _GitExec) -> None:
    result = _git_run(root, git, ["ls-files", "--error-unmatch", *FIXED_TRACKED_FILES])
    if result.returncode != 0:
        raise V3RunnerError(
            "a fixed protocol/runner/tests/requirements file is not tracked by git"
        )


def _decode_path_record(record: bytes, cmd_label: str) -> str:
    """Decode a plumbing record's trailing path strictly as fixed UTF-8.

    The records of ``git ls-tree -z`` and ``git ls-files -z -s`` are NUL-
    delimited; everything except the terminal path element is ASCII and must
    stay loss-less.  The path element itself must be valid fixed UTF-8 (no
    surrogate-pass-through, never replaced).  Any byte sequence that is not
    valid UTF-8 fails closed instead of being silently replaced."""
    try:
        return record.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise V3RunnerError(
            f"{cmd_label} emitted an undecodable path record"
        ) from error


def _decode_ascii_exact(value: bytes, label: str) -> str:
    """Decode a plumbing record's ASCII field strictly, failing closed with
    ``V3RunnerError`` instead of a raw ``UnicodeDecodeError``."""
    try:
        return value.decode("ascii")
    except UnicodeDecodeError as error:
        raise V3RunnerError(f"{label} is not strict ASCII") from error


def _parse_ls_tree_zero(root: Path, git: _GitExec, commit: str) -> dict[str, tuple[str, str]]:
    """Run ``git ls-tree -z <commit> -- <all fixed paths>`` filter-free and
    return {rel: (mode, oid)} for exactly the fixed tracked files, each of which
    must resolve to a single ``blob`` entry whose mode is exactly 6 octal digits
    and whose OID is exactly 40 lowercase hex.  Fail closed on malformed,
    duplicate, missing, or unexpected entries and on any entry lacking NUL
    termination or strict fixed-UTF-8 path.  ``-z`` (with the explicit ``--``
    path boundary) means the mode/type/oid are ASCII and each record ends at its
    NUL, so parsing never depends on lossy text conversion or filters."""
    expected = set(FIXED_TRACKED_FILES)
    result = _git_run_bytes(
        root, git, ["ls-tree", "-z", commit, "--", *FIXED_TRACKED_FILES]
    )
    if result.returncode != 0:
        raise V3RunnerError(
            f"git ls-tree failed for {root}: "
            f"{result.stderr.decode('utf-8', 'replace').strip()}"
        )
    raw = result.stdout
    require(raw.endswith(b"\x00"), "git ls-tree records are not NUL-terminated")
    records = raw[:-1].split(b"\x00")
    seen: dict[str, tuple[str, str]] = {}
    for record in records:
        require(bool(record), "git ls-tree emitted an empty NUL-delimited record")
        fields, sep, raw_path = record.partition(b"\t")
        require(bool(sep), "git ls-tree record has no path/metadata separator")
        require(bool(fields), "git ls-tree record has empty metadata")
        parts = fields.split(b" ")
        require(
            len(parts) == 3,
            "git ls-tree emitted a malformed entry (expected mode type oid)",
        )
        mode, sp_type, raw_oid = parts
        require(
            len(mode) == 6 and all(c in b"01234567" for c in mode),
            "git ls-tree emitted a malformed mode (expected 6 octal digits)",
        )
        require(sp_type == b"blob", "git ls-tree emitted a non-blob fixed-tree entry")
        require(
            len(raw_oid) == 40 and all(c in b"0123456789abcdef" for c in raw_oid),
            "git ls-tree emitted a malformed blob OID",
        )
        oid = _decode_ascii_exact(raw_oid, "git ls-tree OID")
        mode_text = _decode_ascii_exact(mode, "git ls-tree mode")
        rel = _decode_path_record(raw_path, "git ls-tree")
        require(rel in expected, f"git ls-tree emitted an unexpected path: {rel}")
        require(rel not in seen, f"git ls-tree emitted a duplicate output entry: {rel}")
        seen[rel] = (mode_text, oid)
    missing = expected - set(seen)
    require(
        not missing,
        f"git ls-tree tree is missing fixed tracked file(s): {', '.join(sorted(missing))}",
    )
    return seen


def _parse_ls_files_s_zero(root: Path, git: _GitExec) -> dict[str, tuple[str, str]]:
    """Run ``git ls-files -s -z -- <all fixed paths>`` filter-free and return
    {rel: (mode, oid)} for exactly the fixed tracked files, each of which must
    have exactly one index entry with stage exactly 0, a mode of exactly 6 octal
    digits, and an OID of exactly 40 lowercase hex.  Fail closed on malformed,
    missing, or unexpected entries, on any entry lacking NUL termination or
    strict fixed-UTF-8 path, and on any nonzero-stage entry (an unmerged /
    conflict entry would otherwise leave the stage nonzero)."""
    expected = set(FIXED_TRACKED_FILES)
    result = _git_run_bytes(
        root, git, ["ls-files", "-s", "-z", "--", *FIXED_TRACKED_FILES]
    )
    if result.returncode != 0:
        raise V3RunnerError(
            f"git ls-files -s failed for {root}: "
            f"{result.stderr.decode('utf-8', 'replace').strip()}"
        )
    raw = result.stdout
    require(raw.endswith(b"\x00"), "git ls-files records are not NUL-terminated")
    records = raw[:-1].split(b"\x00")
    seen: dict[str, tuple[str, str]] = {}
    for record in records:
        require(bool(record), "git ls-files emitted an empty NUL-delimited record")
        fields, sep, raw_path = record.partition(b"\t")
        require(bool(sep), "git ls-files record has no path/metadata separator")
        require(bool(fields), "git ls-files record has empty metadata")
        parts = fields.split(b" ")
        require(
            len(parts) == 3,
            "git ls-files emitted a malformed index record (expected mode oid stage)",
        )
        mode, raw_oid, stage = parts
        require(
            len(mode) == 6 and all(c in b"01234567" for c in mode),
            "git ls-files emitted a malformed mode (expected 6 octal digits)",
        )
        require(stage == b"0", "a fixed tracked index entry is not at stage 0")
        require(
            len(raw_oid) == 40 and all(c in b"0123456789abcdef" for c in raw_oid),
            "git ls-files emitted a malformed index blob OID",
        )
        oid = _decode_ascii_exact(raw_oid, "git ls-files OID")
        mode_text = _decode_ascii_exact(mode, "git ls-files mode")
        rel = _decode_path_record(raw_path, "git ls-files -s")
        require(rel in expected, f"git ls-files emitted an unexpected path: {rel}")
        require(rel not in seen, f"git ls-files emitted a duplicate output entry: {rel}")
        seen[rel] = (mode_text, oid)
    missing = expected - set(seen)
    require(
        not missing,
        f"git index is missing fixed tracked file(s): {', '.join(sorted(missing))}",
    )
    return seen


def _verify_git_index_vs_head(root: Path, git: _GitExec, commit: str) -> None:
    """Filter-free binary Git index-vs-HEAD closure over every fixed tracked
    file.

    Uses a single ``git ls-tree -z`` run and a single ``git ls-files -s -z``
    run, each parsed into {rel: (mode, oid)}.  Requires the committed HEAD tree
    entry (via ``git ls-tree -z``) to be a single ``blob`` per path and the Git
    index (via ``git ls-files -s -z``) to hold exactly one stage-0 entry per
    path.  The index (mode, oid) tuple must equal the HEAD (mode, oid) tuple
    exactly for every path.  This closes the gap that a staged (but
    worktree-restored) tamper could otherwise leave unnoticed, without any
    filter, status, diff, or text conversion.
    """
    head_entries = _parse_ls_tree_zero(root, git, commit)
    index_entries = _parse_ls_files_s_zero(root, git)
    require(
        set(head_entries) == set(index_entries) == set(FIXED_TRACKED_FILES),
        "git index-vs-HEAD path sets differ",
    )
    for rel in FIXED_TRACKED_FILES:
        require(
            index_entries[rel] == head_entries[rel],
            f"fixed file index (mode, oid) differs from its committed HEAD entry: {rel}",
        )


def _verify_fixed_files_blob_bytes(root: Path, git: _GitExec, commit: str) -> None:
    """For every fixed tracked file, require the raw bytes of the committed
    ``HEAD:<path>`` blob (read via read-only, filter-free ``cat-file blob`` with
    binary stdout) to equal the raw lexical worktree file bytes.  No diff,
    status, textconv, or clean filter is ever invoked."""
    for rel in FIXED_TRACKED_FILES:
        blob = _git_cat_file_blob(root, git, f"{commit}:{rel}")
        target = lexical_path(root, rel, label="fixed file")
        worktree_bytes, _size, _sha = stable_read_bytes_actual(target)
        require(
            blob == worktree_bytes,
            f"fixed file differs from its committed HEAD blob: {rel}",
        )


def _verify_git_root(root: Path, git: _GitExec) -> None:
    """Verify ``root`` is the repository top-level before any other closure
    check, comparing the normalized absolute work-tree string to ``root``."""
    expected = os.path.normcase(os.path.normpath(os.path.abspath(str(root))))
    actual = _git_show_toplevel(root, git)
    require(
        actual == expected,
        f"git top-level {actual!r} does not match root {expected!r}",
    )


def _verify_git_closure(root: Path, git: _GitExec) -> str:
    """Verify the actual commit object and that every fixed file is tracked,
    byte-for-byte equal to its committed HEAD blob, and that the Git index
    matches HEAD exactly (mode and blob OID) via the filter-free binary plumbing
    closure.  Returns the normalized 40-hex commit."""
    _verify_git_root(root, git)
    commit = _git_rev_parse_commit(root, git)
    obj_type = _git_cat_file_type(root, git, commit)
    require(obj_type.lower() == "commit", "git HEAD commit is not a commit object")
    _git_ls_files_error_unmatch(root, git)
    _verify_git_index_vs_head(root, git, commit)
    _verify_fixed_files_blob_bytes(root, git, commit)
    return commit


def _require_abs_root(root: Path) -> Path:
    _require_absolute(root, "root")
    return root


def _derive_runtime_binding(
    root: Path, expected_commit: str, git: _GitExec
) -> _RuntimeBinding:
    """Derive the private, read-only evidence binding from the repository and the
    running interpreter.  The commit is fixed by the caller's read-only git
    closure check; no caller value is ever injectable."""
    root_abs = _require_abs_root(root)

    protocol_path = lexical_path(root, PROTOCOL_REL, label="protocol")
    protocol_raw, protocol_size, protocol_sha = stable_read_bytes_actual(protocol_path)
    require(
        protocol_sha == normalize_hex256(PROTOCOL_SHA256, "protocol SHA"),
        "protocol bytes do not match the fixed frozen digest",
    )

    def _snapshot(rel: str, label: str) -> _FileSnapshot:
        target = lexical_path(root, rel, label=label)
        raw, size, digest = stable_read_bytes_actual(target)
        return _FileSnapshot(path=rel, size=size, sha256=digest)

    runner = _snapshot(RUNNER_REL, "runner source")
    tests = _snapshot(TESTS_REL, "tests source")
    requirements = _snapshot(REQUIREMENTS_REL, "requirements manifest")
    requirements_dev = _snapshot(REQUIREMENTS_DEV_REL, "requirements-dev manifest")

    # Absolute interpreter snapshot: the running executable and exact version.
    executable = Path(os.path.abspath(sys.executable))
    require(executable.is_absolute(), "sys.executable must resolve to an absolute path")
    exec_raw, exec_size, exec_sha = stable_read_bytes_actual(executable)
    python_executable = _FileSnapshot(
        path=str(executable), size=exec_size, sha256=exec_sha
    )
    python_version = str(sys.version)

    installed_sha = installed_distributions_sha()

    return _RuntimeBinding(
        protocol_path=PROTOCOL_REL,
        protocol_sha256=protocol_sha,
        protocol_size=protocol_size,
        implementation_commit=expected_commit,
        runner=runner,
        tests=tests,
        requirements=requirements,
        requirements_dev=requirements_dev,
        python_executable=python_executable,
        python_version=python_version,
        installed_distributions_sha=installed_sha,
        git_executable=git.snapshot,
    )


# ---------------------------------------------------------------------------
# (B) Preflight: read-only protocol + no-existing-artifacts validation.
# ---------------------------------------------------------------------------
def _outputs_validity(root: Path) -> Path:
    """Lexical, non-following path to ``root/outputs/validity`` that requires a
    real (non-symlink, non-reparse, non-file) directory and never OS-resolves
    any component.  outputs/validity must already exist; no mkdir is done here."""
    return lexical_path(root, "outputs/validity", label="outputs/validity")


def _verify_protocol_bytes(
    root: Path, binding: _RuntimeBinding
) -> Mapping[str, Any]:
    """Validate the exact frozen protocol bytes at the fixed lexical path:
    awaited digest, canonical compact JSON, schema, result-blind, and the
    formal one-shot fields.  Read-only."""
    protocol_path = lexical_path(root, binding.protocol_path, label="protocol")
    raw = stable_read_bytes(
        protocol_path,
        expected_size=binding.protocol_size,
        expected_sha256=binding.protocol_sha256,
    )
    require(
        sha256_bytes(raw) == normalize_hex256(binding.protocol_sha256, "protocol SHA"),
        "protocol bytes do not match the derived digest",
    )
    require(
        raw.endswith(b"\n") and b"\n" not in raw[:-1],
        "protocol is not the compact canonical single-line encoding",
    )
    protocol = verify_canonical_json_object(raw, "protocol")
    require(
        protocol.get("schema_version") == PROTOCOL_SCHEMA,
        "protocol schema differs",
    )
    require(protocol.get("result_blind") is True, "protocol must remain result-blind")
    _verify_formal_one_shot(protocol.get("formal_execution"))
    return protocol


def _verify_formal_one_shot(formal_execution: Any) -> None:
    require(
        isinstance(formal_execution, Mapping) and "one_shot" in formal_execution,
        "protocol formal_execution.one_shot is missing",
    )
    one_shot = formal_execution["one_shot"]
    require(isinstance(one_shot, Mapping), "protocol one_shot must be an object")
    require(
        one_shot.get("attempt") == FORMAL_ATTEMPT,
        "protocol one_shot.attempt differs",
    )
    require(
        one_shot.get("claim_schema") == CLAIM_SCHEMA,
        "protocol one_shot.claim_schema differs",
    )
    require(
        one_shot.get("claim_path", CLAIM_PATH_REL.as_posix())
        == CLAIM_PATH_REL.as_posix(),
        "protocol one_shot.claim_path differs",
    )
    require(
        one_shot.get("formal_claim_is_permanent") is True,
        "protocol must keep the permanent claim",
    )
    require(
        one_shot.get("retry_allowed") is False,
        "protocol one_shot.retry_allowed must be False",
    )
    status = one_shot.get("infrastructure_status")
    require(
        isinstance(status, Mapping)
        and status.get("value") == "IMPLEMENTATION_FAILURE",
        "protocol one_shot.infrastructure_status.value must be IMPLEMENTATION_FAILURE",
    )


def _refuse_existing_artifacts(root: Path) -> None:
    """Refuse any existing V3 formal artifact, legacy V1/V2 formal artifact, or
    any V3 candidate/staging/temp name under outputs/validity.  No writes."""
    validity = _outputs_validity(root)
    for expected_name in (*V3_FORMAL_NAMES, *V1_LEGACY_FORMAL_NAMES, *V2_LEGACY_FORMAL_NAMES):
        candidate = validity / expected_name
        if os.path.lexists(candidate):
            raise V3RunnerError(f"existing formal artifact refuses V3 run: {expected_name}")
    for child in validity.iterdir():
        if _is_v3_candidate_or_temp(child.name):
            raise V3RunnerError(f"existing V3 candidate/staging/temp artifact: {child.name}")


def _is_v3_candidate_or_temp(name: str) -> bool:
    name_lower = name.lower()
    if not name_lower.startswith("round13_synthetic_mtmm_v3") and not name_lower.startswith(
        ".round13_synthetic_mtmm_v3"
    ):
        return False
    if name in V3_FORMAL_NAMES:
        return False
    return any(name_lower.endswith(suffix) for suffix in V3_TEMP_SUFFIXES)


# ---------------------------------------------------------------------------
# (D) Neutral preclaim evidence collection (read-only, zero writes).
# ---------------------------------------------------------------------------
def collect_preclaim_evidence(root: Path) -> dict[str, Any]:
    """Collect deterministic, read-only preclaim evidence for the V3 protocol.

    Verifies ``root`` is absolute, runs the full tracked-clean git closure to
    obtain the actual HEAD commit, derives the private runtime binding,
    preflights the fixed frozen protocol and refuses any existing formal
    artifact, then re-runs the git closure and re-derives the binding to
    require the commit and the byte-for-byte binding are stable.  Performs zero
    writes and returns a canonical, result-blind, authority-free dict with
    exactly the neutral evidence keys; it never emits approval, claim,
    decision, or authority fields.
    """
    require(isinstance(root, Path), "root must be a Path")
    require(root.is_absolute(), "root must be an absolute path")

    # 0) Resolve the real, non-reparse absolute git executable once and fail
    #    closed on any ambient GIT_ environment variable before any subprocess.
    _require_no_ambient_git_vars()
    git = _resolve_git_executable()

    # 1) First git closure: actual HEAD commit + full tracked-clean check.
    commit1 = _verify_git_closure(root, git)

    # 2) Derive the fixed-source runtime binding for that commit.
    binding1 = _derive_runtime_binding(root, commit1, git)

    # 3) Preflight: frozen protocol bytes + refusal of existing formal artifacts.
    _verify_protocol_bytes(root, binding1)
    _refuse_existing_artifacts(root)

    # 4) Re-run the git closure: HEAD and tracked-clean must be unchanged.
    commit2 = _verify_git_closure(root, git)
    require(commit2 == commit1, "git HEAD changed between git closures")

    # 5) Re-derive the binding and require byte-for-byte stability.
    binding2 = _derive_runtime_binding(root, commit2, git)
    require(binding1 == binding2, "runtime binding drifted between verifications")

    # 6) Re-read the resolved real git executable and require its size and
    #    SHA-256 equal the original snapshot, so the closure evidence is bound
    #    to the same stable executable that ran the whole collection.
    re_read_git_bytes, re_read_git_size, re_read_git_sha = stable_read_bytes_actual(
        git.path
    )
    require(
        re_read_git_size == git.snapshot.size,
        "git executable size changed during collection",
    )
    require(
        re_read_git_sha == normalize_hex256(git.snapshot.sha256, "git executable SHA"),
        "git executable hash changed during collection",
    )

    def snapshot_node(snapshot: _FileSnapshot) -> dict[str, Any]:
        return {
            "path": snapshot.path,
            "sha256": snapshot.sha256,
            "size": snapshot.size,
        }

    return {
        "schema_version": EVIDENCE_SCHEMA,
        "status": EVIDENCE_STATUS,
        "formal_attempt": FORMAL_ATTEMPT,
        "not_run": True,
        "authority_absent": True,
        "protocol": {
            "path": binding1.protocol_path,
            "sha256": binding1.protocol_sha256,
            "size": binding1.protocol_size,
        },
        "implementation": commit1,
        "bound_sources": {
            "runner": snapshot_node(binding1.runner),
            "tests": snapshot_node(binding1.tests),
            "requirements": snapshot_node(binding1.requirements),
            "requirements_dev": snapshot_node(binding1.requirements_dev),
        },
        "environment": {
            "python_executable": {
                **snapshot_node(binding1.python_executable),
                "version": binding1.python_version,
            },
            "git_executable": snapshot_node(binding1.git_executable),
            "installed_distributions": {
                "sha256": binding1.installed_distributions_sha
            },
        },
    }


__all__ = [
    "EVIDENCE_SCHEMA",
    "EVIDENCE_STATUS",
    "FIXED_TRACKED_FILES",
    "FORMAL_ATTEMPT",
    "FORMAL_CLAIM_NAME",
    "FORMAL_INDEX_NAME",
    "FORMAL_RESULTS_NAME",
    "FORMAL_VERDICT_NAME",
    "PROTOCOL_REL",
    "PROTOCOL_SCHEMA",
    "PROTOCOL_SHA256",
    "REQUIREMENTS_DEV_REL",
    "REQUIREMENTS_REL",
    "RUNNER_REL",
    "TESTS_REL",
    "V1_LEGACY_FORMAL_NAMES",
    "V2_LEGACY_FORMAL_NAMES",
    "V3RunnerError",
    "V3_FORMAL_NAMES",
    "canonical_json_bytes",
    "collect_preclaim_evidence",
    "installed_distributions_sha",
    "lexical_path",
    "normalize_commit",
    "normalize_hex256",
    "require",
    "sha256_bytes",
    "stable_read_bytes",
    "stable_read_bytes_actual",
    "verify_canonical_json_object",
]
