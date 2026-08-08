"""Stage-1 read-only Round 13 preflight CLI (writes nothing).

Runs :func:`arsc_eval.round13_preflight.run_preflight` and prints a compact
stdout JSON summary with the ``PREFLIGHT_STAGE1_PASS`` status.

Constraints honored here:

* No output path and no formal-execution argument is accepted.  The parser
  defines no positional parameter and no option; any unexpected argument
  (including ``--output`` or a formal-execution flag) is rejected by argparse
  with exit code 2.
* Nothing is written: no artifact, log, or index is created, modified, or
  removed.
* ``PREFLIGHT_STAGE1_PASS`` is an infrastructure stage-1 status only.  It is
  neither ``GO_RUN`` nor a scientific verdict; no GO/verdict is self-issued.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from arsc_eval.round13_preflight import run_preflight  # noqa: E402


def main() -> int:
    # No positional parameters and no options: any output or formal-execution
    # argument is rejected before any verification runs.
    parser = argparse.ArgumentParser(
        description=(
            "Stage-1 read-only Round 13 preflight. Rejects any output or "
            "formal-execution argument and writes nothing."
        )
    )
    parser.parse_args()

    summary = run_preflight(ROOT)
    # Compact single-line JSON summary to stdout.
    sys.stdout.write(json.dumps(summary, ensure_ascii=False, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as error:
        sys.stderr.write(f"PREFLIGHT_STAGE1_FAIL: {error}\n")
        raise SystemExit(1) from error
