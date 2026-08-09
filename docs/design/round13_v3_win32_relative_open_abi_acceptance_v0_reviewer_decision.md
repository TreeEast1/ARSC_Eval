# Round 13 - V3 Win32 Relative-Open ABI Acceptance V0 Reviewer Decision

Status: FROZEN_REVIEW_DECISION_PROPOSED_FOR_COMMIT

Decision: ACCEPT_ABI_DESIGN_FOR_FUTURE_SYNTHETIC_PRIMITIVE_ONLY

Authorization: NOT_GO_RUN

Implementation activation: NOT_ACTIVE_UNTIL_THIS_RECORD_IS_COMMITTED_AND_INDEPENDENTLY_HASH_VERIFIED

## 1. Reviewed object

This independent design-review decision binds exactly the following committed
object and no substitute:

- Git commit: `ae9c824424d527e5f01c141153ac2a3849ce580b`
- Design path:
  `docs/design/round13_v3_win32_relative_open_abi_acceptance_v0_proposed.md`
- Design SHA-256:
  `ADC2F05B6829E7F3EDCAA6126970D57C7EB173ECB074ECF2538FCFE5EDB7C33B`
- Design byte count: `19272`
- Design line count: `360`
- Design encoding constraint: ASCII

Any change to the commit, path, digest, byte count, line count, or bytes voids
this decision and requires a new independent review. A working-tree draft,
successor document, copied document, or semantically similar document is not
covered by this decision.

## 2. Review conclusion

The bound proposal is accepted as a design-level ABI contract for a future,
data-agnostic Win32 relative-open primitive and synthetic fake-DLL/fake-HANDLE
tests only. The review accepts the bound document's pinned Windows x64 ABI,
handle-relative `NtCreateFile` strategy, access/share/disposition/options,
same-HANDLE identity and metadata checks, directory lease graph, fixed claim
creation semantics, bounded same-HANDLE write/flush/readback, independent
relative reopen, closed failure mapping, and permanent-consumption policy.

This conclusion is a design acceptance only. It is not evidence that an
implementation exists, is correct, or is authorized to access real inputs.

## 3. Maximum future implementation scope

After this reviewer-decision record itself is committed and independently
hash-verified, a separate later gate may authorize no more than:

- one data-agnostic Win32 ABI/relative-open primitive;
- one synthetic fake-DLL/fake-HANDLE test slice for that primitive;
- in-memory buffers, fake handles, injected fault statuses, and synthetic path
  components only;
- ABI size/offset, option, identity, reparse, delete-pending, link-count,
  byte-cap, error-mapping, concurrency, and lifetime assertions described in
  the bound design.

This record does not itself authorize that implementation. It only establishes
the reviewed design basis on which a later, separately bounded implementation
gate may be requested.

## 4. Explicit non-authorizations

This decision is `NOT_GO_RUN`. It does not authorize, approve, imply, or create
any of the following:

- a DAAD-X, Round 13, formal, scientific, metric, model, training, inference,
  evaluation, or data run;
- any claim creation, attempt consumption, replay-store update, used-writer,
  result, verdict, artifact-index, staging, recovery, retry, rewrite, delete, or
  formal-output mutation;
- any real `CreateFileW`, `NtCreateFile`, `NtQueryDirectoryFile`, `WriteFile`,
  `FlushFileBuffers`, or other Win32 filesystem execution against the workspace
  or any real filesystem target;
- any runner, launcher, protocol, schema, envelope, verifier, replay store,
  authority loader, or formal pipeline wiring;
- any parseable GO, authorization-envelope, approval, decision, claim, nonce,
  signature, credential, or execution instance;
- any production, deployment, external side effect, or credential handling;
- any statement that the SCI objective or DAAD-X evaluation is complete.

No draft, proposal, memo, test fixture, fake object, status token, or this
reviewer decision may be interpreted as `GO_RUN`.

## 5. Closed data and filesystem boundary

The following remain closed and outside the authority of this decision:

- `data/external/**`;
- every official DAAD-X tar/archive and every range/chunk/assembled archive;
- every DAAD-X receipt, assembler manifest, transport manifest, binding JSON,
  inventory, extracted member, and archive metadata;
- quarantined and untracked data or code files;
- formal paths under `outputs/validity/**`;
- any operation that reads, lists, stats, opens, hashes, verifies, copies,
  decompresses, extracts, inventories, or otherwise touches those objects.

No synthetic test authorized by a later gate may substitute a real workspace
path, real official input, or real formal-output path for an in-memory fake.

## 6. Repository boundary

This reviewer decision authorizes only its own creation and later exact-byte
review. It does not authorize changes to:

- `src/arsc_eval/round13_v3_runner.py`;
- any current runner or launcher;
- any protocol, schema, generator, binding, envelope, or formal artifact;
- any existing tests;
- Git history other than a later separately approved commit containing this
  exact reviewer-decision file.

No staging, commit, push, merge, branch change, or tag is authorized by the
creation of this record. Those actions require a separate gate.

## 7. Activation and revocation

This decision remains inactive while uncommitted. The next permitted action is
an independent exact-byte review of this file followed, only if that review
passes, by a separately authorized docs-only commit.

Even after such a commit, the design remains `NOT_GO_RUN`. Any future primitive
implementation requires a new bounded gate that names its exact allowed paths,
requires synthetic-only tests, forbids real Win32 filesystem execution, and
preserves all closed data and formal-output boundaries above.

Final reviewer token: `ACCEPT_ABI_DESIGN_FOR_FUTURE_SYNTHETIC_PRIMITIVE_ONLY`

