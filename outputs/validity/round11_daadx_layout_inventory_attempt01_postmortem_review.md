# Round 11 DAAD-X layout attempt01: independent postmortem review

Review date: 2026-08-09 (Asia/Shanghai)

Scope: read-only review of the published attempt result, its claim, and the
relevant control code. This review did not read, enumerate, stat, decompress,
or otherwise access any official archive/input/data path. It did not launch,
retry, delete, recover, or modify `layout_inventory_attempt01`.

## Disposition

`layout_inventory_attempt01` is consumed and must not be retried. Its durable
claim exists and binds execution binding SHA-256
`B03D7238B8A451748A4BB08AEE46AAB1FA0ACE5779A4BEC4929149DB2465DA70`.
The final result directory exists as a normal directory, and neither candidate
staging path exists. The reviewed execution authority says
`GO_RUN_LAYOUT_INVENTORY_ATTEMPT01_ONCE`, `one_shot.retry=false`, and
`formal_run.automatic_retry_delete_recovery=false`. The control implementation
creates the claim exclusively and durably, retains it on every failure, rejects
an existing claim, refuses to replace an existing final directory, and publishes
staging to final without replacement. Therefore a policy-conforming re-entry
cannot reacquire attempt01.

The result is a valid fail-closed execution record:

- outcome: `STOP_LAYOUT_INTEGRITY_OR_POLICY_FAILURE`
- completeness: `HASH_CLOSED_STOP`
- first failure: `MANIFEST/AUTHORITY_CANONICAL_FAILURE`
- archive observation: `NONE`, 0 bytes, no observed SHA-256
- layout status: incomplete/inconclusive
- external validity: not established
- Phase 1 or G0--G8 verdict: false
- training authority: false

This is a terminal safety/governance outcome, not a positive or negative
scientific result about DAAD-X.

## Evidence verification

The result directory contains the 11 indexed payload artifacts plus the
self-excluded artifact index (12 files, 50,625 bytes total). Every indexed
file's byte count and SHA-256 matches
`round11_daadx_layout_inventory_artifact_index.json`. The index itself is 1,731
bytes with SHA-256
`077294EFAEDA36722AFC592D8A6A2DD8293FEB66647318020473D6408D415FB0`.
The claim is 329 bytes with SHA-256
`8423CCF76F11430DAEFD8E671F4997C592EA688A5CC6A48880BFC2ECE64B36C8`.

The copied manifest is complete relative to the frozen authority declaration:
15,792 bytes and SHA-256
`FDBCC19DD726F8CA5C93A8189C47A5ACBEA5E6D1EC131679B4302E7493A835DC`.
It is valid JSON, but it is not byte-for-byte canonical under the formal
runner's canonical encoding. Re-encoding the parsed value using that encoding
would produce 12,224 bytes, including its required trailing newline, rather
than the observed 15,792 bytes. Its top-level keys are `assembled`, `chunks`,
`parameters`, and `schema`; it has
`schema="ARSC_ASSEMBLED_RANGES_MANIFEST_V1"` and no `schema_version` field.
The runner tests strict canonicality before testing `schema_version`, so the
recorded first failure code is exactly the expected first failing predicate.
This diagnoses an authority representation/schema-contract mismatch; it does
not diagnose archive corruption.

## Claim boundaries

The evidence supports these safety claims:

1. The independent one-shot authorization was bound into the claim and result.
2. Authority bytes were copied and hash-checked before acceptance.
3. The manifest was rejected fail-closed at the canonicality gate.
4. The archive-opening branch was not reached; the published record represents
   zero archive bytes as observed.
5. The STOP record was closure-validated, indexed, durably published, and is
   internally hash-consistent.

It does not support claims about archive integrity, archive layout, member
counts or paths, semantic content, privacy properties of members, DAAD-X
construct validity, external validity, model performance, Phase 1/G0--G8, or
training authorization. The copied manifest matching its declared byte digest
only establishes identity with the frozen manifest authority; it does not make
that authority canonical or schema-conformant and says nothing about the
unopened archive.

## Narrow next research direction

Freeze a dataset-agnostic ARSC construct/measurement protocol, then evaluate it
on a separately governed, openly accessible benchmark already permitted for
research (for example, BDD-OIA/BDD100K annotations only after their license,
acquisition, and schema are independently reviewed). Start with synthetic
fixtures and public metadata/labels to assess content validity, annotation
reliability, intervention sensitivity, and measurement invariance. Treat this
DAAD-X attempt as missing-by-policy/censored for scientific analysis, never as
a zero or adverse scientific observation. Do not use this recommendation as
authority to touch or retry the DAAD-X archive.

## H3 recommendation

Yes: record the exact claim and the complete 12-file attempt01 directory in H3
as immutable adverse-execution, safety, provenance, and reproducibility
evidence. Include this postmortem as interpretation, but do not edit any claim
or attempt artifact and do not include official input/data files. H3 must label
the record `HASH_CLOSED_STOP`, state that attempt01 is consumed, and explicitly
deny scientific/external-validity conclusions. This is evidence that the
guardrails worked; it is not evidence that the SCI objective is complete.
