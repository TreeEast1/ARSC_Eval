# Independent result-blind Round 11 layout execution review

Date: 2026-08-09 (Asia/Shanghai)

Decision: `GO_RUN_LAYOUT_INVENTORY_ATTEMPT01_ONCE`

This is an independent, result-blind review of the frozen execution binding and contained launcher chain after correction of the canonical Windows `SYSTEMROOT` environment contract. The review was completed before any formal layout result existed. No DAAD-X archive, transport receipt, assembler manifest, or other formal input was opened, listed, statted, hashed, decompressed, or otherwise accessed. No old worktree binding or review was consulted. The formal launcher and formal data job were not run. The binding remains `NOT_RUN_BINDING_FROZEN_AWAIT_INDEPENDENT_GO_RUN` and does not self-authenticate.

## Frozen authority reviewed

- Binding head H1: `2187d323f80023f518f535c1e2a1308467b38559`
- Reviewed parent H0: `c34bcb118d9f89dc25160f39ca916fe061b6754c`
- H1 has exactly one parent, H0.
- H0-to-H1 contains exactly the seven reviewed code/test files plus `outputs/validity/round11_daadx_layout_inventory_execution_binding.json`.
- Binding identity: 12052 bytes; SHA-256 `B03D7238B8A451748A4BB08AEE46AAB1FA0ACE5779A4BEC4929149DB2465DA70`; Git blob `dd2dff72b7eb006d3f26dbebcaa9f436e4073083`; mode `100644`.
- All 24 bound artifact records match the H1 Git tree for path, mode, blob, and byte count. The seven changed code/test files also match their binding SHA-256 records byte-for-byte.

## Static execution-chain findings

- The binding is canonical JSON with schema `ARSC_ROUND11_DAADX_LAYOUT_EXECUTION_BINDING_V1`, decision `NOT_RUN_BINDING_FROZEN_AWAIT_INDEPENDENT_GO_RUN`, and `this_is_go_run=false`.
- The bound Python and real MinGit executables match their recorded paths, byte counts, SHA-256 values, link counts, versions, implementation, and Windows platform identity.
- Launcher and worker argv are exact and ordered, use `python -I -S -B`, and carry only the declared external anchors/control handle and exact archive byte/hash declarations.
- Launcher, worker, and Git subprocesses use the same exact four-key environment: `PYTHONDONTWRITEBYTECODE`, `PYTHONIOENCODING`, `PYTHONUTF8`, and canonical uppercase `SYSTEMROOT`. Missing, extra, wrong-case, and empty-root environments are rejected.
- The worker is created suspended, assigned to the one-process kill-on-close Windows Job, and receives only the explicit handle list before resume.
- Repository execution modules are loaded from leased, hash/tree-verified source bytes without ordinary repository import or bytecode loading. Failure paths roll back inserted modules and attached package attributes.
- The declared authorities, resource limits, artifact contract, one-shot attempt identity, claim/staging/final topology, and capability exclusions match the launcher enforcement code. Authority target contents were deliberately not inspected during this result-blind review.
- The claim boundary is `GO_RUN_LAYOUT_INVENTORY_ATTEMPT01_ONCE`; automatic retry, deletion, and recovery are forbidden.

## Test evidence

Command:

`D:\anaconda3\python.exe -m pytest -q -rs tests/test_round11_layout_worker.py tests/test_round11_layout_runner.py tests/test_round11_layout_formal_runner.py tests/test_create_round11_layout_execution_binding.py tests/test_run_round11_layout_inventory.py`

Result: 95 passed, 2 skipped, exit code 0. Both skips were limited to unavailable local symlink creation privileges:

- `tests/test_round11_layout_formal_runner.py:295`
- `tests/test_run_round11_layout_inventory.py:216`

SHA-256 of the captured subprocess stdout bytes: `79EC89BAF79205E45D94AFFFA0A6ABAF9DBC09180170EE459BE65E78B641B180`.

The positive generator tests simulate only the exact `git rev-parse HEAD` response required at generation time and delegate every other Git operation, including all `ls-tree H0` checks, to the real bound Git executable. The non-H0 negative test uses the real H1 checkout HEAD and proves regeneration is rejected. A real Windows `python -I -S -B` subprocess verifies the exact canonical four-key environment observed by CPython.

## Authorization boundary

This decision authorizes exactly one later invocation of the reviewed formal launcher for `layout_inventory_attempt01`, and only after a separate H2 commit contains exactly this review decision and this memo and the launcher is supplied out-of-band pins for that H2 HEAD and the review JSON SHA-256. It does not authorize direct/manual access to formal inputs, a retry, deletion, recovery, Phase 1, label or payload-semantic analysis, training, inference, or any claim of scientific completion.
