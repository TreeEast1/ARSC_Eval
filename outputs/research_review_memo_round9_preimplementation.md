# Round 9 Multimap Robustness: Independent Preimplementation Review

## Review boundary and verdict

This review is strictly preimplementation and preoutcome. I inspected only
the frozen Round 9 protocol, outcome-blind map/component artifacts and
builders, the outcome-blind multimap helpers/tests, and the structural
independent audit named in the review request.

I did not read targets, predictions, probabilities, confidence values,
errors, or any new-map q>0 metric outcome. I did not inspect the still
unfrozen formal outcome implementation.

Verdict:

> **PASS TO COMPLETE AND FREEZE THE FORMAL IMPLEMENTATION.**
>
> **THE FORMAL ONE-SHOT RUN REMAINS STOP / NOT AUTHORIZED.**

This memo is not a formal-run GO. A second independent review is required
after the complete formal implementation, formal tests, exact preflight,
and launch manifest have been frozen.

## 1. Faithfulness to the sole-authorized Round 9 design

The protocol faithfully implements the only next experiment authorized by
the Round 8 final review:

- Dataset: the frozen 4,557-image BDD-OIA test population only.
- No download, training, model inference, new checkpoint, threshold
  selection, mask analysis, CEG analysis, or external dataset.
- Training seeds remain exactly 43, 44, 45, 46, and 47.
- Map IDs are exactly `map00` through `map19`.
- Salts are exactly `arsc-round9-map00` through
  `arsc-round9-map19`.
- Salt replacement and selective map removal are prohibited.
- The Round 8 map is a historical reference and is excluded from the
  Round 9 primary gate.
- q is exactly `[0, .25, .50, .75, 1]`.
- Active-image counts are exactly `[0, 1140, 2278, 3418, 4557]`.
- The action threshold remains 0.5.
- A, R, S, and C1 components, directions, tie rule, and per-seed-first
  bottleneck are unchanged from Round 8.
- R per-class/support/predicted-positive/all-zero diagnostics remain
  mandatory.
- S non-primary diagnostics remain diagnostic-only.
- C1 remains a correspondence metric, not a faithfulness or natural
  visual-severity metric.

The hierarchical bootstrap is also faithful:

1. Draw 20 map positions with replacement.
2. Draw one five-position training-seed vector and share it across all
   selected map occurrences.
3. For each map occurrence, draw that map's full association-component
   count with replacement.
4. Within an occurrence, share the component multiset across every seed,
   q, model, axis, and perturbation.
5. Compute the bottleneck inside each map occurrence and selected seed.
6. Average over selected seeds, then selected map occurrences.
7. Use 2,000 replicates, RNG seed `20260809`, and pointwise percentile
   95% intervals.

The per-axis gate is unchanged:

- at least 18/20 map-specific five-seed mean bottlenecks are strictly
  positive;
- the 20-map grand mean bottleneck is strictly positive;
- the hierarchical CI lower bound is strictly positive;
- the 20-map by five-seed grand mean component curves have no adjacent
  expected-direction reversal;
- all 20 maps and diagnostics are reported.

All four axes must pass for `ROUND9_FULL_PASS`. No post-outcome map
addition, salt replacement, threshold/metric/q/gate change, or passing-map
subset report is allowed.

## 2. Frozen artifact verification

Verified SHA256 values:

| Artifact | SHA256 |
|---|---|
| Protocol | `B8E180ECB3CDCE2F34EC987BDE33F9B8FEFE0D60509962C09D69811FD7D7F5F3` |
| Map NPZ | `9F540646ABF101800F5BC65AF272F4906C57EBFA94BEBB78B909DD52F1E627F4` |
| Map manifest | `1163E8AC6638FFD145167D0F3F5CFDEB6829A876FBAD7C4F06B14C3F0E37E7DB` |
| Component NPZ | `23C86D0B87C55287033531A66D0E78182263A2734A23C966D431B09DF0298272` |
| Component manifest | `AC7A688A1F0603DFA2D9CD3C9AE16FB000CB1B8B26427B589AD4DE24716CFBE9` |
| Map builder | `12540C081C37DD9002CBB89FD11D9EB9FCB1FAF3DA9B609557D158D7D88CD3AD` |
| Component builder | `30B4A2E278C12B0ED781DC745D675739F7D9DF654233807784F22B02143DF312` |
| Multimap helper | `7A044FA74B56B8EFD389ADC82F44B0C156951B3DA33A4B674FC52AFC5AD125EB` |
| Multimap tests | `BB31CC91C3C853C9FD467A731716AFC6166FE3DA96E697994EA80A86D973CCB4` |
| Structural verifier | `DF02D3F44D9FF0B6C7EB10F65FA296869AECE7115977455682CEA347F38EAF80` |
| Independent audit | `1E39F5F28591BE692B62204F79C2BB0CD1AFD0FFE954C7B232ABBCF3E63B8ADD` |
| Audit test log | `7CA4DB9B905ACB65BF55A6FD906C51D7D831826F1140DC3F5AE5EB4F6D9B2165` |

The Round 9 map builder reuses the exact Round 8
`graded_association.py` hash:

`529C0AB3364CA48AEFDD6FC91C7B1390D57110CFA221437B3F7FED4D709DD443`

The Round 9 component builder reuses the exact Round 8
`association_components.py` hash:

`F8AA90F0756032ADCB283D111E5B29F03C9D93D96ABDA383E8F9E737B57CE6B5`

The builders read filename/clip/source-index structure only. Their
manifests state that no target, prediction, logit/probability, confidence,
error, or metric outcome was read.

Structural evidence:

- Every map contains 2,277 pairs plus one final triplet that partitions
  all 4,557 images exactly.
- Every stored map stack equals the map stack reconstructed from its
  stored cycles.
- Every q map is a global bijection.
- Active sets are strictly nested and have the frozen counts.
- Active source/destination pairs are cross-clip.
- q=0 is identity and q=1 has zero fixed points.
- All 20 q1 maps are unique.
- A read-only replay using the frozen Round 8 builder and the 20 frozen
  salts matched all 20 stored map stacks.

Component evidence:

- Each map has its own q1-derived association-component partition.
- The independent verifier recomputed the partitions using a separate
  union/find implementation.
- Stored component labels, packed offsets, and members match the
  independent reconstruction.
- All 20 partitions are unique.
- Each current partition has 1,625 components.
- Minimum component size is two clips/two images.
- Maximum component size ranges from 7 to 12 clips and 12 to 22 images.
- Every q map is source-closed inside its own partition.
- Every component-restricted map remains a bijection.

The structural independent audit reports 13/13 PASS, 20 unique q1 maps,
20 unique component partitions, 61 passing tests, and no declared formal
result artifacts.

## 3. Statistical interpretation boundary

The 20 maps are not 20 datasets. They reuse the same 4,557 images,
targets, model outputs, and five training seeds. They vary only the
outcome-blind association realization.

Therefore, the future hierarchical interval may only be described as a
fixed-observed-population, map by seed by per-map-association-component
procedural interval. It is not:

- an external-population confidence interval;
- evidence from 20 independent scenes, domains, or datasets;
- evidence from 100 independent training runs;
- external validity, ontology completeness, faithfulness, calibration
  validity, causal validity, or a safety guarantee.

All maps have the same q=0 identity baseline. The 20 q=0 entries are not
20 independent baseline replications. Full-sample q=0 point values must be
identical across maps. Any q=0 bootstrap variation arises only from the
map-specific clustering procedure.

The four axis intervals remain pointwise, not simultaneous familywise 95%
intervals.

## 4. Governance gaps that block formal-run GO

The following issues do not invalidate the frozen protocol/maps/components,
but they must be resolved before a one-shot GO.

### 4.1 The current run manifest is structural, not final

The current preoutcome manifest does not bind a frozen formal analysis
core, one-shot script, formal-specific tests, output schema, q=0 bridge,
final reviewer GO memo, or launch manifest. It must be treated as a
phase-A structural manifest only.

### 4.2 Audit outputs lacked commit provenance at review time

At review time, HEAD/main/origin-main were
`7feb4b359be7d1c60115c61a17455797221b4911`, while the independent audit
JSON, preoutcome run manifest, and audit test log were untracked. They and
this memo must be committed and pushed before the formal implementation
freeze is reviewed.

### 4.3 The immutable test identity is not byte-stable

The raw test log contains wall-clock text such as
`Ran 61 tests in 0.082s`. The duration is nondeterministic, yet the current
manifest binds the raw log hash.

The final preflight must either exclude timing from the immutable identity
or normalize it with one fixed, tested rule. Two consecutive preflight
runs on the same commit/input state must produce byte-identical preflight
and candidate-manifest artifacts.

### 4.4 Formal-output absence checking is incomplete

The current verifier checks only four possible formal outputs. The
protocol also requires point/diagnostic tables, 80 map-specific axis
means, 400 map by seed bottlenecks, bootstrap summaries, and a formal tmux
log.

The final preflight must freeze the complete output schema and prove the
absence of every declared formal result, temporary result, partial result,
and formal log path before the run.

### 4.5 Independent salt binding is incomplete

The current independent verifier reconstructs source maps from stored
cycles, but it does not independently reconstruct the salted filename
order, triplet, first valid half rotation, and sorted pair cycles from each
frozen salt.

The current artifacts passed a reviewer replay, but the final verifier must
add salt-to-cycles reconstruction without importing the formal builder.
This is a verification repair, not a protocol or salt change.

### 4.6 Formal code must not assume a selectable component count

All current maps happen to have 1,625 components. The formal bootstrap
must nevertheless read the count and packed members from each frozen map
partition. It must not use component count as a rule for dropping or
replacing a salt, and it must never reuse one map's partition for another
map.

## 5. Required formal implementation behavior

Before the second independent review, the frozen implementation must:

1. Read only the protocol-declared map/component artifacts, Round 8
   primitives, Round 8 q=0 reference, and hash-bound code/metadata.
2. Use an exact allowlist for Round 8 primitive keys.
3. Perform no pixel loading, model loading, training, inference, or
   external-data access.
4. Prove q=0 identity and exact Round 8 A/R/S/C1 bridges before any q>0
   computation.
5. Prove all 20 full-sample q=0 rows are exactly identical.
6. Emit all 20 maps by five seeds by five q primary curves and required
   diagnostics.
7. Emit all 80 map-specific axis means and all 400 map by seed axis
   bottlenecks.
8. Take the minimum expected-direction adjacent step inside each map and
   seed before any seed or map averaging.
9. Expand a selected component with all of its image members and preserve
   multiplicity when a component repeats.
10. Use each selected map occurrence's own offsets/members.
11. Share one seed-position draw across all selected maps.
12. Share one component multiset within each occurrence across every
    seed, q, model, axis, and perturbation.
13. Keep independent component draws for separate selected map
    occurrences, including repeated occurrences of the same map ID.
14. Use exactly `np.random.default_rng(20260809)` and 2,000 replicates.
15. Produce exactly four finite draw arrays of shape `(2000,)`, ordered
    A, R, S, C1.
16. Freeze the percentile convention explicitly, including the
    interpolation/method.
17. Recompute summaries from stored draws and assert exact agreement.
18. Apply strict `> 0`, 18/20, CI-lower `> 0`, and zero reversal
    tolerance.
19. Require all four axes for full PASS.
20. Reject NaN/Inf and any missing map/seed/q/component/diagnostic row.
21. Refuse overwrites and publish formal artifacts only after all
    calculations and consistency checks complete.
22. Leave no formal-looking partial artifact if a pre-result assertion
    stops the run.

The formal script must not expose CLI overrides for map subset, salt, q,
threshold, metric, direction, gate, bootstrap seed, replicate count, or
interval method.

## 6. Required synthetic and preflight checks

Formal-specific synthetic tests must cover:

- salt-to-cycle/map reconstruction;
- per-map component expansion with different toy component counts;
- repeated component membership and multiplicity;
- repeated map occurrences with separate component draws;
- one shared seed vector across maps;
- one shared component draw within an occurrence;
- the counterexample distinguishing per-seed-first bottleneck from
  averaging curves before taking the minimum;
- C1 mixed directions;
- deterministic RNG draw prefix;
- 18/20 PASS versus 17/20 FAIL;
- zero map bottleneck is not positive;
- zero CI lower bound fails;
- zero grand mean fails;
- any reversal fails;
- any axis failure makes the full gate fail;
- NaN/Inf rejection;
- exact q=0 bridge and reduction order;
- deterministic output schemas and row counts.

The exact preflight must bind:

- the unchanged protocol, map, component, Round 8 primitive, and Round 8
  reference hashes;
- builders and reused Round 8 cores;
- the complete formal core, script, and tests;
- this preliminary memo;
- the exact Git commit;
- the complete output schema;
- the candidate manifest and subsequent independent GO memo.

It must record explicitly that no new-map q>0 metric outcome was computed.
Two consecutive preflight runs must be byte-identical and must prove the
complete absence of formal outputs.

## 7. Conditions for a later one-shot GO

A later reviewer may issue `GO_ONE_SHOT` only after all of the following:

- formal core/script/tests are committed, pushed, hash-bound, and clean;
- every formal-specific synthetic test passes;
- q=0 exact bridge passes without computing new-map q>0 outcomes;
- full output absence passes;
- two preflights and candidate manifests are byte-identical;
- timing is excluded from immutable identities;
- the candidate manifest binds the exact implementation/input commit;
- a second independent review inspects the frozen implementation, tests,
  preflight, and candidate manifest;
- the launch manifest binds the second reviewer's GO memo before any
  outcome computation;
- formal run count remains exactly one.

If the formal attempt stops before publishing results, its failure log
must be preserved, absence of result artifacts must be proven, and an
independent `GO_RERUN` review is required before any retry. No scientific
statistic may change after outcome exposure.

## Final preliminary decision

- **Protocol:** PASS; no scientific amendment is required.
- **Outcome-blind maps/components:** PASS.
- **Current structural audit:** PASS, with the governance repairs above
  required for the final preflight.
- **Permission:** implementation and freezing may continue.
- **Formal one-shot outcome run:** **STOP / NOT YET AUTHORIZED**.

