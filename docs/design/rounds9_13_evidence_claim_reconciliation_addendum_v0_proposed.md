# Rounds 9-13 Evidence / Claim Reconciliation - Proposed Addendum V0

Status: PROPOSED
Documentation-only: DOCUMENTATION_ONLY
Run authorization: NOT_GO_RUN
Data access: NO_DATA_ACCESS
Review: PROPOSED_AWAIT_INDEPENDENT_REVIEW
Proposed date: 2026-08-09

> **Documentation-only proposal. This file makes no claim, grants no
> authorization, and proposes no data access.** It is a future-addendum design
> that suggests how `outputs/experiment_summary.md` *could* be extended to make
> the evidence-level reach of Rounds 9-13 explicit. It is **not** an edit of
> `outputs/experiment_summary.md`, an authorization envelope, a claim instance,
> or a member of any formal allowlist. Nothing here authorizes a run
> (`NOT_GO_RUN`), grants access to any input or artifact
> (`NO_DATA_ACCESS`), or supersedes any tracked reviewer decision.

---

## 1. Purpose, scope, and non-authoritative boundary

This proposal collates the committed reviewer decisions and frozen artifacts for
Rounds 9-13 into a single reconciliation that a future addendum of
`outputs/experiment_summary.md` could incorporate. The addendum exists **only**
to record what each round may and may not legitimately claim; it is
**documentation-only** and carries no scientific, safety, grounding, or
external-validity assertion.

The proposal is based exclusively on tracked committed repository documents
(counterpart memo `.md` text, `experiment_summary.md`, and the round reviewers)
and the reviewer decisions cited below. No archive, chunk, receipt, or manifest
contents were inspected; no new experiment or metric recomputation was run; no
external-validity claim is made. The Rounds 9-13 conclusions below are a
faithful synthesis and paraphrase; quoted numeric and token values are copied
from tracked artifacts, and the original tracked sources control on conflict.

The future addendum is proposed for **later independent review**. It is marked
`PROPOSED_AWAIT_INDEPENDENT_REVIEW` and strictly `NOT_GO_RUN`.

## 2. The proposed future addendum (text blueprint for experiment_summary.md)

Below is the *proposed* text the future addendum would append to
`outputs/experiment_summary.md`. It is proposed blueprint text, **not a current
edit**. A reviewer must independently decide whether any of it may be
incorporated, and no change to `outputs/experiment_summary.md` is made by this
document.

```
# Addendum V0 (proposed): Rounds 9-13 evidence-level reconciliation

Date: 2026-08-09
Classification: DOCUMENTATION_ONLY; NOT_GO_RUN; NO_DATA_ACCESS;
                PROPOSED_AWAIT_INDEPENDENT_REVIEW

This addendum clarifies, for Rounds 9-13, the precise evidence weight of each
frozen protocol and its reviewer decision. It does not add or retract numeric
results. It forbids any claim of external validity, safety, rationale
grounding/faithfulness, or comprehensive four-axis validation.

See docs/design/rounds9_13_evidence_claim_reconciliation_addendum_v0_proposed.md
for the proposed, reviewable, non-authoritative evidence-claim matrix and its
cited tracked sources. The original tracked reviewer decisions and frozen
artifacts remain authoritative; this reference remains DOCUMENTATION_ONLY,
NOT_GO_RUN, and NO_DATA_ACCESS.
```

## 3. Evidence-claim matrix (four separated axes)

The reconciliation separates evidence along four axes. Rows cite tracked
artifact paths and, where readily available, commit hashes. Every row's "allowed
claim" is limited to the frozen scope below; anything beyond it is forbidden.

| Round | Axis: computational integrity | Axis: within-BDD construct sensitivity | Axis: between-model interaction | Axis: external validity |
|---|:---|:---|:---|:---|
| Round 9 (20-map association robustness) | **PASS** formal/computational: `ROUND9_FULL_PASS`; independent 8/8 checks; bootstraps byte-identical; artifact `outputs/validity/round9_multimap_artifact_index.json`; memo `outputs/research_review_memo_round9_postresult.md`. Go memo reviewed HEAD `2eeda1d784c322adf2fa123b9d5c39ad0457d48f`. | **BOUNDED CONDITIONAL PASS**: response is robust across 20 prefix map realization; 20/20 maps positive on A/R/S/C1. Not a monotone-dose or ontology-level validation. Six rationale classes tie at F1=0 in all maps/seeds/q. | Round 9 adds no model-vs-model effect size; preserves RQ1/RQ2 conclusion only. | Not 20 datasets; no cross-domain/external effect. |
| Round 10 (synthetic pixel corruption dose-response) | **PASS** / formal `ROUND10_PARTIAL_OR_FAIL` accepted as valid final outcome; independent replay of 3,975 diagnostics at 0 mismatch; memo `outputs/research_review_memo_round10_postresult.md`; bound decision SHA `795FCECE213B78C03FD820274D67338FED0F57426E2A33AEF6F281F762266A89`. | **C1 only** obtains monotone, practical-magnitude, cross-operator support (3/3 C1 gates). A is endpoint-local only (blur action-only/joint, noise action-only reach 0.01). R and S lack universal monotone construct validation (0/3 R, 0/3 S gates). | None asserted from this round alone; interaction handled by Rounds 7/8/12. | No natural-corruption prevalence, real-road safety, or dataset transfer. |
| Round 11 (DAAD-X transport) | **PASS** transport completeness only: 70/70 chunks; 18,585,647,156 bytes; expected ETag `"68089dd7-453ca7834"`; assembled SHA-256 `98E6DD4D068004B090A5D62C648A727AF902EBF3B176BCE2CE044EABDE91E965`; opaque assembled-transport review `outputs/research_review_memo_round11_assembled_transport.md`; receipt post-generation review `outputs/research_review_memo_round11_transport_receipt_postgeneration.md`; tracked snapshot `outputs/validity/round11_daadx_transport_receipt.json`. | No construct-sensitivity evidence. | No model interaction. | Transport-only. No archive interpretation, label access, or scientific evidence. Does not establish external validity. |
| Round 12 (paired multi-axis supervision x dose) | **PASS** structured; artifact `outputs/validity/round12_existing_outputs_results.json`; index `round12_existing_outputs_artifact_index.json`; memo `outputs/research_review_memo_round12_existing_outputs_postresult.md`; one-shot claim `outputs/validity/.round12_existing_outputs_attempt01.claim` (must be permanently preserved). | **PASS_WITH_LIMITATIONS**. D_C1 = +0.020017, Bonferroni q=0.0125 one-sided lower bound +0.001826; 3/3 corruption families positive; 4/5 seeds positive (seed 43 = -0.001884). D_A/D_R/D_S pass -0.01 non-inferiority guardrails only. Does not establish every family x dose cell or every seed positive. D_R is a Joint-internal retention guardrail only. | Between-model axis: the preregistered equal-weight aggregate across the 12 non-zero family-by-dose cells is positive for Joint-vs-Action-Only C1 action flips, with A/R/S non-inferiority. This does not establish that every individual cell is positive. | No external validity, safety, faithfulness, or causal attribution. |
| Round 13 V3 (synthetic MTMM V3) | Frozen/proposed/not run. Protocol `outputs/validity/round13_synthetic_mtmm_v3_frozen_protocol.json` (commit `4c8f7bf`); neutral runner `src/arsc_eval/round13_v3_runner.py` (commit `8f5588a`); Win32 ABI design `docs/design/round13_v3_win32_relative_open_abi_acceptance_v0_proposed.md` (commit `ae9c824424d527e5f01c141153ac2a3849ce580b`); ABI-scope review record `docs/design/round13_v3_win32_relative_open_abi_acceptance_v0_reviewer_decision.md` (commit `30921418e4e2fd191616441626a417705854ea80`; review record only, not GO_RUN, claim authority, or data-access authority). | No claim; no result. | No model interaction. | No claim; no `GO_RUN`; no data access. |

**Consolidated evidence-level conclusions (to be preserved verbatim in the
addendum):**

- **C1 has the strongest support** across Rounds 9, 10, and 12; it remains a
  sample-correspondence / action-flip diagnostic, not a faithfulness or safety
  claim.
- **A is limited and endpoint-local** (best supported claim is per-endpoint
  sensitivity; no universal dose-response).
- **R and S lack universal monotone construct validation** (R: 6 classes
  F1=0; S: synthetic tie-averaged AURC response only; no universal monotone
  support).
- **Round 12 is PASS_WITH_LIMITATIONS** and cannot establish every cell or
  external validity.
- **Round 11 proves transport completeness only** (70/70 chunks;
  18,585,647,156 bytes; expected ETag `"68089dd7-453ca7834"`; assembled
  SHA-256 `98E6DD4D068004B090A5D62C648A727AF902EBF3B176BCE2CE044EABDE91E965`).
  It includes **no archive interpretation or scientific evidence**.
- **Round 13 V3 is frozen/proposed/not run**, with **no claim and no GO_RUN**.

## 4. Explicitly forbidden claims

The proposed addendum must explicitly forbid any of the following, in any of
the cited rounds:

1. **External validity** - no real-road, cross-dataset, natural-corruption, or
   deployment generalization claim is supported by Rounds 9-13.
2. **Safety** - no real-driving safety, calibration-as-safety, or operational
   guarantee.
3. **Grounding / faithfulness** - no rationale grounding, causal evidence, or
   claim that C1 or R verifies critical-evidence dependence (RQ2-CEG remains
   UNANSWERED/closed; Round 10/12 memos affirm CEG is not restored).
4. **Comprehensive four-axis validation** - no claim that A/R/S/C1 jointly
   constitutes complete ARSC validation; Round 10 explicitly passed only
   C1-family gates (3/12) and Round 12 explicitly limits A/R/S to
   non-inferiority guardrails.

## 5. Trusted tracked artifact and decision index (sources for the addendum)

- `outputs/experiment_summary.md` (target of the future addendum; not edited
  here).
- `outputs/README.md` (master artifact index; authoritative path/SHA ledger).
- `outputs/research_review_memo_round9_postresult.md` (Round 9).
- `outputs/research_review_memo_round10_postresult.md` (Round 10).
- `outputs/research_review_memo_round11_assembled_transport.md`,
  `outputs/research_review_memo_round11_transport_receipt_postgeneration.md`,
  `outputs/validity/round11_daadx_transport_receipt.json` (Round 11).
- `outputs/research_review_memo_round12_existing_outputs_direction.md`,
  `outputs/research_review_memo_round12_existing_outputs_postresult.md`,
  `outputs/validity/.round12_existing_outputs_attempt01.claim`,
  `outputs/validity/round12_existing_outputs_artifact_index.json` (Round 12).
- `outputs/validity/round13_synthetic_mtmm_v3_frozen_protocol.json`,
  `src/arsc_eval/round13_v3_runner.py`,
  `docs/design/round13_v3_external_authorization_envelope_schema_v0_proposed.md`,
  `docs/design/round13_v3_win32_one_shot_traceability_proposed.md`,
  `docs/design/round13_v3_win32_relative_open_abi_acceptance_v0_proposed.md`,
  `docs/design/round13_v3_win32_relative_open_abi_acceptance_v0_reviewer_decision.md`
  (Round 13 V3; the last item is an ABI-scope review record only, not GO_RUN,
  claim authority, or data-access authority).

Commit hashes (readily available in this workspace):
- Round 9 Go memo reviewed HEAD: `2eeda1d784c322adf2fa123b9d5c39ad0457d48f`.
- Round 10 result implementation binding: `0c10e078a27d67816041aedd31b0c3273177e30d`; result
  commit `d6ad618`.
- Round 11 DAAD-X transport evidence release: `6057f21`.
- Round 12 frozen protocol: `0d7c64d`; Round 12 formal results + review: `f8170b3`.
- Round 13 V3 protocol freeze: `4c8f7bf`; V3 neutral runner evidence: `8f5588a`;
  V3 ABI design: `ae9c824424d527e5f01c141153ac2a3849ce580b`; ABI-scope
  review record only: `30921418e4e2fd191616441626a417705854ea80` (not GO_RUN,
  claim authority, or data-access authority).

## 6. Quarantine and non-inspection guarantee

This proposal was authored with **no access** to, and intentionally refrained
from reading or inspecting:

- `data/external/**`;
- any archive, chunk, receipt, or manifest contents;
- `outputs/validity/round11_daadx_layout_inventory_execution_binding.json`;
- `src/arsc_eval/round13_execution.py`.

The proposal neither creates nor implies a parseable authorization envelope,
claim instance, nonce, signature, or formal allowlist. In particular, mirroring
the Round 13 V3 authorization-schema design, the proposed addendum must not be
parsed as any authorization, claim, or GO/decision payload, and no
`GO_RUN_V3` or any other `GO_RUN` decision is created, implied, or authorized by
this file.

## 7. Independent-review request metadata (proposed; not a reviewer decision)

- Status: `PROPOSED_AWAIT_INDEPENDENT_REVIEW`.
- Authorization: `NOT_GO_RUN`.
- Data access: `NO_DATA_ACCESS`.
- Documentation delta: only this file is new; no existing file is modified.
- Next required action (by an independent reviewer, not by this proposal):
  review the reconciliation above against the cited tracked artifacts and
  decide whether to approve documentation-only incorporation of the addendum
  text into `outputs/experiment_summary.md`. Such approval cannot authorize a
  run or data access, create or consume a claim, or supersede any existing
  reviewer decision.
