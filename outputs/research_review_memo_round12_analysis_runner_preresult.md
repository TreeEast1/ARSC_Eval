# Round 12 existing-outputs formal runner: independent result-blind pre-result review

Date: 2026-08-02

Verdict: `GO_RUN_ROUND12_FORMAL_ATTEMPT01`

## Review boundary

This was a result-blind review of the frozen Round 12 protocol, direction and protocol-prereview decisions, statistics core, canonical metric implementation, deterministic serializers, formal runner, and synthetic tests. I did not run the formal runner, decode or inspect values from either real Round 10 NPZ archive, compute any Round 12 effect or bootstrap result, inspect a formal Round 12 output, access DAAD-X, load a model/checkpoint, run inference, or train a model.

## Scientific contract

The implementation preserves the frozen four effects and their favorable directions: `D_A`, `D_R`, `D_S`, and `D_C1`; equal weighting over all 12 family-by-nonzero-level cells and five seed positions; exact family level-0 equality; shared seed-position and source-clip-position draws; metric recomputation from expanded clip samples; 5000 paired bootstrap replicates; linear float64 q=0.0125 one-sided Bonferroni lower bounds; and the exact PASS/PARTIAL/FAIL comparisons. The R component remains a within-joint retention guardrail and cannot establish a between-model rationale benefit.

The core reuses the bound canonical `f1_from_counts`, `harmonic_numbers`, and `weighted_tie_averaged_aurc` functions. It accepts only the frozen raw primitive inputs and the exact saved shared draws, rejects aggregate outcome inputs, validates metadata/order/ranges/finiteness/binary constraints/source-clip mapping, and performs exhaustive raw clean equality before effects.

## Execution and output controls

Authorization is checked before outcome-bearing imports or payload access and requires the exact result-blind decision, exact one-attempt execution scope, all twelve canonical path/hash bindings, frozen idle protocol state, direction/prereview decisions, and protocol-bound archive hashes. After authorization, NPY member names, shapes, and dtypes are checked from headers before selective `numpy.load`. Reviewed bytes are reauthorized after computation and before serialization/publication.

The fixed claim `outputs/validity/.round12_existing_outputs_attempt01.claim` is created atomically with exclusive `xb`, written/fsynced before any formal NPY-header or payload access, and retained after success or failure. Concurrent and stale claims fail closed; there is no automatic stale-claim recovery. The claim is a non-outcome execution-control sentinel, not a sixth scientific result. The five reserved formal outputs remain exactly:

- `outputs/validity/round12_existing_outputs_results.json`
- `outputs/validity/round12_existing_outputs_point_diagnostics.csv`
- `outputs/validity/round12_existing_outputs_component_draws.npz`
- `outputs/validity/round12_existing_outputs_artifact_index.json`
- `outputs/validity/round12_existing_outputs_protocol.log`

Serialization is deterministic and rejects nonfinite JSON and wrong bootstrap array dtypes/shapes. Component NPZ member order and timestamps are fixed. CSV gate booleans occupy the declared `passed` column. The artifact index hashes all four non-index payloads and is published last. Publishing uses token-unique, exclusively created, fsynced staging files; the default hard-link publication refuses overwrite; rollback is restricted to confirmed published targets and owned staging paths.

## Verification

- Reviewer-local synthetic suite: `89 passed, 2 skipped in 2.04s`.
- Owner-reported full suite: `325 passed, 3 skipped`.
- Reviewer-local `py_compile` passed for runner, core, and serializer.
- Skips are Windows symlink-privilege cases; the non-symlink behavior is covered.
- All five formal outputs, the claim, and the GO decision were absent before this decision was written.
- Whole-file hashes of the real NPZ archives were used only as opaque identity checks and match the frozen protocol. NPZ payload values were not decoded or inspected.

## Residual limitations and required interpretation

- Five training seeds limit inferential precision; the crossed bootstrap does not create additional independent training runs.
- Existing BDD-OIA outputs cannot establish causality, safety, explanation faithfulness, or external validity.
- `D_R` is a within-joint retention guardrail only.
- Directory fsync is best-effort on Windows. A process termination or power loss may leave the persistent claim, owned staging files, or non-index partial outputs. This intentionally fails closed and requires human audit; it must not be cleared automatically or followed by an automatic rerun.
- Multi-file publication uses artifact-index-last commit semantics rather than an impossible filesystem-wide atomic rename of five flat files. Absence of the index means the attempt is incomplete and not a valid formal result.
- A privileged external process could still alter files despite the controls. The reviewed workflow assumes ordinary single-workspace operation, while concurrent runner invocations are blocked by the exclusive claim.

## Authorization boundary

This review authorizes exactly one execution of `attempt01` by the canonical no-argument runner against the exact twelve bound files. It does not authorize a retry, claim removal, a second analysis, protocol/implementation changes, new inference, training, DAAD-X access, or any scientific claim before independent post-result review. Any hash mismatch, pre-existing claim/output/staging file, execution error, incomplete publication, or post-compute reauthorization failure requires stop and human review.
