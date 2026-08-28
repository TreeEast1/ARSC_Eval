"""Regenerate every ARSC paper asset from the frozen artifacts, in order.

The stages are ordered by dependency: the S confidence audit and the Round 10 /
rationale / seed analyses read only `outputs/validity/`, while the profile and
decision-change tables and the final status document read those analyses'
outputs as well.

The S confidence audit runs the hierarchical bootstrap and takes a few minutes.
Pass ``--skip-audit`` to reuse the existing frozen audit JSON when only the
downstream tables and documents need rebuilding.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: ``(script, description, is_expensive)``
STAGES: tuple[tuple[str, str, bool], ...] = (
    (
        "run_s_confidence_audit.py",
        "S selective-risk construct audit (S0/S1/S2 + hierarchical bootstrap)",
        True,
    ),
    (
        "build_s_confidence_audit_table.py",
        "S confidence audit table",
        False,
    ),
    (
        "build_rationale_coverage.py",
        "Rationale per-class coverage figure and table",
        False,
    ),
    (
        "plot_round10_axis_separation.py",
        "Round 10 dose-response / axis-separation main figure and table",
        False,
    ),
    (
        "build_seed_heterogeneity.py",
        "Seed heterogeneity figure and table",
        False,
    ),
    (
        "build_arsc_profile_tables.py",
        "Main-result Profile Table and Decision Change Table",
        False,
    ),
    (
        "build_arsc_final_status.py",
        "ARSC_FINAL_STATUS.md claim-to-evidence map",
        False,
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-audit",
        action="store_true",
        help="reuse the existing S confidence audit JSON instead of "
        "re-running its bootstrap",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    stages = [
        stage
        for stage in STAGES
        if not (args.skip_audit and stage[2])
    ]
    print(f"regenerating {len(stages)} ARSC paper asset stage(s)\n")

    for index, (script, description, expensive) in enumerate(stages, start=1):
        marker = " (slow)" if expensive else ""
        print(f"[{index}/{len(stages)}] {description}{marker}")
        print(f"        scripts/{script}")
        started = time.monotonic()
        completed = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / script)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        elapsed = time.monotonic() - started
        if completed.returncode != 0:
            print(completed.stdout)
            print(completed.stderr, file=sys.stderr)
            print(f"        FAILED after {elapsed:.1f}s")
            return completed.returncode
        tail = [line for line in completed.stdout.splitlines() if line.strip()][-3:]
        for line in tail:
            print(f"        {line}")
        print(f"        ok in {elapsed:.1f}s\n")

    print("all ARSC paper assets regenerated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
