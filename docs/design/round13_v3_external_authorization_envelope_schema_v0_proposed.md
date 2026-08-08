# Round 13 - V3 External Authorization Envelope Schema V0 (Proposed, Non-Authoritative)

Status: PROPOSED

Review: AWAIT_INDEPENDENT_REVIEW

Authorization: NOT_GO_RUN

> **Non-authoritative, design-only.** This document and its twin canonical JSON
> Schema (`round13_v3_external_authorization_envelope_schema_v0_proposed.json`)
> are working proposals. They are **not** in any formal artifact allowlist and
> they create - and must not be read as creating - any approval, claim, attempt,
> consumption, run, or data access. Nothing in this package authorizes a run,
> and no concrete authorization instance is ever produced here.
>
> **Every instance is rejected.** The V0 schema root deliberately carries the
> unsatisfiable sentinel keyword `"not": {}`, so under JSON Schema Draft-07
> **all** values - including an otherwise structurally conforming envelope - are
> rejected. Only a separate, future authoritative schema (never mutation of this
> V0 document) may remove that sentinel.

---

## 1. Purpose and insufficiency

The committed neutral runner (`src/arsc_eval/round13_v3_runner.py`) emits only
the authority-absent `AWAIT_EXTERNAL_AUTHORIZATION_V3` preclaim evidence body and
contains no envelope builder, no GO loader, and no claim/decision/approval
fields. The preceding Win32 traceability proposal
(`docs/design/round13_v3_win32_one_shot_traceability_proposed.md`, sect. 4)
records that a **separate** authorization-envelope schema is required and is out
of scope for that Win32 document.

This package is that separate envelope schema **proposal**. It is offered for
review but remains **insufficient on its own**:

- It is **PROPOSED / NOT_GO_RUN** and non-authoritative. It must not be treated
  as a frozen or reviewed contract.
- It is **not independently reviewed**, **not frozen**, and **not referenced by
  any runner**.
- It provides **no verifier**, **no instance builder/parser/loader**, and **no
  replay store or used-writer**; a conforming envelope cannot be constructed or
  consumed from this package.
- The **independent authority authentication metadata is deliberately left as a
  required future field shape only** (its object's property set is intentionally
  empty). Concrete nonce, signature, and envelope-id bindings are deferred to a
  further separately frozen and independently reviewed authoritative schema.
- The schema root carries the **unsatisfiable sentinel** `"not": {}`, so under
  Draft-07 **every instance is rejected**. This is a deliberate invariant of V0:
  the sentinel may be removed only by a separate future authoritative schema,
  never by mutating this V0 document.
- It therefore **cannot authorize anything** today. It only proposes the future
  structural binding categories, and it rejects every instance until a separate
  authoritative schema supersedes it.

## 2. What the proposed schema structurally requires

The canonical JSON Schema at
`docs/design/round13_v3_external_authorization_envelope_schema_v0_proposed.json`
is a deterministic, fully closed (`additionalProperties: false` at every object)
JSON Schema document that structurally requires the following future binding
categories on any *future* envelope instance:

> **Unsatisfiable sentinel.** The document root also carries the JSON Schema
> keyword `"not": {}`. Under Draft-07 an empty schema matches every value, so
> `not: {}` rejects **every** instance. The structural categories below are
> therefore never satisfiable by V0 itself: they document the intended future
> shape, and V0 continues to reject everything until a separate authoritative
> schema removes the sentinel.

| Category | Structural requirement | Notes |
|---|---|---|
| Package status | `package_status` is `const` `PROPOSED_NOT_GO_RUN` | Non-authoritative marker, encoded in the schema itself. |
| Envelope schema identity | `envelope_schema` is `const` `ARSC_ROUND13_V3_EXTERNAL_AUTHORIZATION_ENVELOPE_V0_PROPOSED` | Self-describes this proposed schema (a schema id, not a concrete envelope instance). |
| Decision constraint | `decision` is `const` `GO_RUN_V3` | **Only** `GO_RUN_V3` is permitted, expressed as a JSON Schema `const`. |
| Attempt | `attempt` is `const` `round13_attempt03` | Exact one-shot attempt. |
| Protocol binding | `protocol` object: `schema` is `const` `arsc-round13-synthetic-mtmm-protocol-v3`; `sha256` is a 64-hex string | Binds the committed V3 protocol schema and digest. |
| Implementation & runtime identities | `implementation_identity` object: `runner` (`path` + `sha256`) and `runtime` (`version` + `executable_sha256`), both 64-hex where a digest is required | Pins the neutral runner implementation and runtime. |
| Neutral evidence | `neutral_evidence` object: `schema` is `const` `ARSC_ROUND13_SYNTHETIC_MTMM_PREFLIGHT_EVIDENCE_V3`; `digest` is a 64-hex string | Binds the preclaim evidence schema and digest. |
| Independent authority authentication | `independent_authority_authentication` is a **required** object with an **empty closed property set** | Required as a *future field shape only*; concrete nonce/signature/envelope-id values are intentionally absent and deferred. |
| Single-use / replay-refusal semantics | `single_use` object: `replay_refusal` is `const` `true`; `max_uses` is `const` `1` | Expresses permanent one-shot / replay-refusal semantics without any concrete instance. |

## 3. Deliberate exclusions

To keep this package **non-authoritative and free of any parseable instance**:

- The schema root carries the **unsatisfiable sentinel** `"not": {}`, so Draft-07
  rejects **every** instance. This sentinel is part of V0 and may be removed
  only by a separate future authoritative schema - never by mutating V0.
- No `examples`, `example`, `default`, or `enum` keys appear anywhere in the
  schema.
- No concrete `nonce`, `signature`, or `envelope-id` **value** appears. The
  authority-authentication field is a required **empty** closed shape only.
- No top-level or nested `instance`, `claim`, `approval`, or `authorization`
  payload is defined; nothing here is loadable as a go/claim payload.
- The generator exposes no instance builder/parser/loader/verifier, no replay
  store, no `used` writer, no claim/writer, no Win32 API, no data access, and no
  metric API, and it accepts no envelope payload.

## 4. Generator / reproducibility

`scripts/generate_round13_v3_external_authorization_envelope_schema_v0_proposed.py`
only **builds, canonicalizes, checks, and writes** the proposed canonical schema
document at the fixed docs path. Canonical bytes are deterministic
`json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=True)` plus one
trailing LF. No time, random, environment, workspace read, or network input is
consulted, so the `docs` JSON can be byte-for-byte reproduced by any compliant
copy of the generator. The generator is never imported or consumed by the
committed neutral runner.

## 5. Future review checklist (before any authoritative use)

A future authoritative envelope schema - **separate and frozen** - must, after
independent review, additionally:

- [ ] Be marked frozen and authoritative (never PROPOSED / NOT_GO_RUN).
- [ ] Complete the `independent_authority_authentication` field shape with
      concrete nonce/signature/envelope-id **value** definitions and a verifier.
- [ ] Define a replay store / used-writer and enforce single-use/replay refusal
      at claim time, not only as schema shape.
- [ ] Be wired into the neutral runner (or a separate, reviewed claim pipeline)
      and independently reviewed before it may gate a `GO_RUN_V3` attempt.
- [ ] Remain fully closed (`additionalProperties: false` at every object),
      deterministic, and byte-reproducible.

Until all of the above holds, this package authorizes nothing and remains
**PROPOSED / NOT_GO_RUN**.
