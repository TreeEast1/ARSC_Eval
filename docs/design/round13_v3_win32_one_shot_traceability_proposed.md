# Round 13 - V3 Win32 One-Shot Traceability (Proposed)

Status: PROPOSED

Review: AWAIT_INDEPENDENT_REVIEW

Authorization: NOT_GO_RUN

> **Non-authoritative, design-only.** This document is a working proposal: it is design-only, it is **not** in a formal artifact allowlist, and it creates - and must not be read as creating - any approval, claim, attempt, consumption, or data access. Nothing in this document authorizes a run.

---

## 1. Basis and scope

This proposal is scoped strictly to the committed V3 protocol and the neutral runner. It proposes a Win32-specific, one-shot traceability contract for the claim pipeline. Where the committed V3 protocol or the neutral runner does not yet pin the contracts called out below, the "Missing design contract" column records that gap; nothing here silently assumes committed behavior that is not present.

**Existing committed evidence** is present in this workspace and is used in the matrix below:

- `outputs/validity/round13_synthetic_mtmm_v3_frozen_protocol.json` (committed frozen V3 protocol).
- `src/arsc_eval/round13_v3_runner.py` (committed neutral runner source).
- `tests/test_round13_v3_runner.py` (committed neutral runner tests).

These files are the fixed, tracked, clean-under-HEAD inputs the neutral runner binds in its preclaim evidence closure. The matrix distinguishes what is already committed and what this proposal still requires as a Win32-specific contract.

## 2. Auditable traceability matrix

Columns:

- **Existing committed evidence** - committed, reviewable evidence already present in this workspace for the row.
- **Missing design contract** - the gap this proposal must fill before a run may be considered.
- **P0 acceptance tests** - the minimum tests that must pass before authorization is even considered.
- **Failure semantics** - what must happen (never silent) when the contract is violated.

All nine core rows below are graded **P0**.

| # | Traceability item | Existing committed evidence | Missing design contract | P0 acceptance tests | Failure semantics |
|---|---|---|---|---|---|
| 1 | External authorization envelope | None. The neutral runner emits an authority-absent `AWAIT_EXTERNAL_AUTHORIZATION_V3` preclaim body; it contains no envelope builder, no GO loader, and no claim/decision/approval fields. | A separate future frozen/reviewed envelope schema must bind protocol SHA, attempt, implementation/environment, evidence digest, and replay/used refusal; see sect. 4. Not provided here. | Missing, malformed, wrong-binding, expired (if expiry is adopted), already-used, and replayed envelopes are refused before claim creation. A conforming envelope can reach claim creation only after its separate schema and verifier are frozen and independently approved. | Refusal is explicitly returned as an in-memory, caller-visible fixed enumerated code with zero writes; it creates or modifies no formal or status file. No forwarding or "best effort" downgrade is allowed, and no claim is created under an unauthorized or unverified envelope. |
| 2 | Claim-time hash-closure binding recomputation | Neutral runner recomputes the protocol digest and binds the fixed tracked files (protocol, runner, tests, manifests) under the actual Git HEAD at evidence-collection time; it does not trust stored flags. | Claims must recompute their binding at claim time from recomputed protocol/value closures and must not trust stored "authorized" flags. | Test that a stale or forged digest, commit, or value cannot pass (forged commit / runner path / runner sha / executable path / executable version all fail). | Recompute failure aborts; fail closed; no partial or best-effort commit is permitted. |
| 3 | Root/input and outputs/validity Win32 directory-handle leases | Neutral runner's stable-read helpers are leaf-stable and fail closed on symlink/reparse, hard-link, and identity drift, but do not hold Win32 directory leases and do not guarantee tree atomicity. | Exact lease scopes below (sect. 3); all formal children opened relative to held directory handles with identity/reparse/share-mode checks, never by string re-resolution. | Test that any path leaving the leased roots/handles is refused; that children are opened relative to held handles. | Before claim creation, a lease violation aborts with zero writes. Once any claim object exists, every later lease or identity violation is a consumed postclaim failure: return only a fixed enumerated infrastructure code and never delete, recover, or retry the claim. No string path re-resolution is permitted. |
| 4 | Fixed-path `CREATE_NEW` claim artifact | Neutral runner performs zero writes and refuses if any V3 formal artifact or legacy V1/V2 formal artifact, staging, partial, or temp file already exists (existing-artifact refusal). | Claim/winner artifact created only via fixed-path `CREATE_NEW`; never overwrite. Successful creation creates the named claim object and immediately and permanently consumes the attempt. Durability is established only by Row 5, and failure to establish durability never permits retry. | Test that an existing target fails cleanly (no overwrite), and any existing formal artifact is refused before writes. | Overwrite must never occur; conflict surfaces as explicit error, never a silent replace. |
| 5 | Same-handle write / `FlushFileBuffers` / readback | Neutral runner reads leaf files through an open descriptor with no-follow and identity drift checks; it has no writer and no `FlushFileBuffers`/claim readback. | The claim artifact is written, flushed, and read back through the same open handle with verification; a durable same-handle claim readback is required. | Test that the readback equals the written claim bytes; test that absence of flush/readback fails. | Mismatched readback or flush failure is a postclaim failure. Even if durability is unconfirmed, the existence of any 0/partial/corrupt claim object permanently consumes the attempt; it is never deleted, recovered, or retried, and only a fixed enumerated infrastructure code is returned. |
| 6 | Permanent one-shot no-retry claim | Committed protocol declares the V3 attempt (`round13_attempt03`) as a permanent formal claim with `retry_allowed: false`; neutral runner provides `authority_absent`/`not_run` and no replay. | A permanent claim is never retried, recovered, or re-run on a later run for the same attempt/input; DELETE/RECOVER/REWRITE are not supported. | Test that a replayed or already-claimed attempt is refused; that no retry/delete/recover/rewrite path exists. | Replaying a permanent claim is refused explicitly; duplication is never silently tolerated; prior claim is never deleted. |
| 7 | Result-blind / preclaim-vs-postclaim failure non-leakage | Neutral runner is result-blind: preclaim evidence carries no approval/claim/decision values and is emitted with zero writes. | Preclaim (before any claim) must fail with zero writes; postclaim (after any claim object exists) is permanently consumed. Externally visible failure uses only fixed enumerated infrastructure codes, never exception text/results. | Test that preclaim failure produces zero writes; test that postclaim failure never publishes uncodified exception text/results; test no cleanup language that deletes the claim. | Failures before claim leave zero writes; once any claim object exists the attempt is permanently consumed even if 0/partial/corrupt, and the claim is never deleted/recovered/retried; external failure includes only enumerated infrastructure codes. |
| 8 | Claim-first; results+verdict+index-last closure with independent reread | The committed protocol pins formal claim/results/verdict/index identities and hash-closure semantics; the neutral runner declares `not_run`/`authority_absent` and writes none of them. Win32 `CREATE_NEW` behavior is not committed evidence. | Closure order is fixed: claim first, then results, then verdict, then index last; a final independent handle reopens and rereads the claimed state before any success report. | Test that observable readers can never see index/results before claim; test independent reread detects divergence of every formal artifact. | Divergence between claimed state and what an independent reader sees aborts and reports, never self-corrects; prior claim is never removed. |
| 9 | Core crash/reparse/partial-claim semantics | Neutral runner fails closed on reparse/symlink/dangling-link and refuses staging/partial/temp files; it has no writer, so no partial-claim artifacts can be produced by it. | Define crash states precisely (pre-claim, mid-write 0/partial/corrupt, post-claim) with no claim of cross-file atomicity; a claim object is created only via `CREATE_NEW` and once present is permanent. | Kill-mid-write crash-state definition; concurrent claimants; reparse/junction handling; partial-claim detection. | Any crash/postclaim state produces a deterministic, auditable outcome; a once-created claim object exists and is never deleted/recovered/retried; no silently "successful" partial artifact is claimed as whole. |

## 3. Exact lease scopes (Win32)

- **Root / input chain lease.** From anchor verification and binding recomputation (protocol digest, fixed tracked files, Git HEAD closure) until a durable same-handle claim readback, every root and input artifact is accessed only through an acquired Win32 directory handle anchored at the verified root/input path-chain handle. Formal children are opened **relative to the held directory handle**.
- **Outputs / validity handle lease.** Held continuously from the **absence scan** through `CREATE_NEW`, the computation, results/verdict, index-last, and the **final independent reopen/read closure**; every output and validity artifact is accessed only through the outputs/validity directory handle acquired at absence-scan start.
- **No string path re-resolution.** Within either lease, no path is resolved again by recomposing strings; all opens are relative to an already-held directory handle. Re-resolving is a contract violation.
- **Formal children.** Any formal child is opened relative to the held directory handle with identity, reparse, and share-mode checks; a child may never be located again by a fresh string path.
- **No disjoint/release-ordering claim.** This document does not claim that the root/input lease and the outputs/validity lease are disjoint by directory, and it does not specify an unsupported lease release ordering. Both scopes are defined independently above; release discipline must be pinned in the separate Win32 design review, not assumed here.

## 4. Future authorization-envelope schema (separate; not implemented here)

A separate, future, frozen/reviewed authorization-envelope schema is required and is **explicitly out of scope** for this document. That schema must bind: a protocol SHA, the attempt identifier, the implementation/environment identity, and an evidence digest; and it must provide replay/used refusal on reuse of a consumed envelope. It must be a separate schema that is itself frozen and independently reviewed before it may be used.

This document does **not** contain, and must not be extended to imply, any example payload, nonce, signature, or parseable authorization instance. Nothing here may be later interpreted as a valid authorization instance, and no envelope builder or instance may be constructed within this proposal.

## 5. P1 (post-P0, non-blocking) coverage

Limited to platform, stress, fuzz, and performance concerns that do **not** gate authorization:

- **Platform breadth:** a broader OS/filesystem matrix, including additional Windows SKU/version variations and checks that the lease semantics hold across supported Win32 environments.
- **Stress:** high concurrency with many overlapping claimant processes; large artifact counts under a single lease.
- **Fuzz:** broader fuzz breadth over malformed inputs, path shapes, and reparse-name tricks against the lease boundaries and `CREATE_NEW` fixed-path code.
- **Performance:** lease acquisition/release overhead, `FlushFileBuffers`/readback latency, and index-last closure wall-clock - measured, not optimized at P0.

## 6. Scope of this proposal

This proposal itself grants no authority whatsoever. In particular:

- It gives no implementation authority: it is design-only and creates nothing.
- It gives no run authority: nothing here authorizes any run, execution, attempt, claim, or consumption.
- It gives no claim authority and no data arrangement: the neutral runner remains `authority_absent`/`not_run`, and the formal claim pipeline remains not-run until a separately frozen/reviewed authorization path exists.
- It gives no data access: `data/external`, quarantined data, and all other inputs remain closed under this proposal.

The separate authorization mechanism, when it exists, must itself state all enforcements; no blanket prohibition on ordinary docs commit/push is made here. This document only records that this proposal confers no implementation/run/claim/data authority. No claim object may be deleted, recovered, or rewritten under this design.

## 7. Next-review checklist

The independent review must confirm and record:

- [ ] The design matrix and lease scopes are reviewed against the committed V3 protocol and the neutral runner only.
- [ ] All nine core rows are P0 and accurately state one-shot `attempt03`, permanent claim, no retry/delete/recover/rewrite, preclaim-vs-postclaim failure, and hash-closure semantics.
- [ ] The neutral runner evidence is correctly described as `authority_absent`/`not_run`, double Git/runtime binding closure, raw HEAD/index/worktree closure, and zero-writer/existing-artifact refusal.
- [ ] Neither the protocol nor the neutral runner provides external envelope authentication or a Win32 writer/lease.
- [ ] Lease scopes (sect. 3) match the stated anchors and closure ordering; no string re-resolution and no disjoint/release-order-unsupported claim exists.
- [ ] Crash states are defined precisely without claiming cross-file atomicity, and postclaim objects are never deleted/recovered/retried.
- [ ] Failure semantics keep externally visible failure to fixed enumerated infrastructure codes only, never exception text/results; no cleanup language suggests claim deletion.
- [ ] The separate future envelope schema (sect. 4) is a distinct frozen/reviewed binding with protocol SHA, attempt, implementation/environment, evidence digest, and replay/used refusal, carrying no example payload/nonce/signature/parseable instance.
- [ ] P1 items are genuinely non-blocking and limited to OS/filesystem breadth, stress/fuzz breadth, and performance/diagnostics.
- [ ] This review is of the **design only**; it does not claim that code or tests already implement any Win32 writer/lease/envelope behavior beyond the committed neutral runner evidence closure.
- [ ] This document remains non-authoritative, design-only, not in the artifact allowlist, and confers no approval/claim/attempt/consumption/data access.
