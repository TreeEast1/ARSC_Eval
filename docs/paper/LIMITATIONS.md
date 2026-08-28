# Limitations and protocol boundaries

This document states what the frozen BDD-OIA evidence does not establish. It is
written to be read alongside `docs/paper/ARSC_CLAIMS_AND_TERMINOLOGY.md`, which
lists the permitted and forbidden claims, and
`docs/paper/NUCLEAR_TRANSFER_CONDITIONS.md`, which states what a transfer to
nuclear decision support would require.

## 1. Scope of the empirical base

All results come from a single dataset (BDD-OIA), a single backbone family
(ResNet-50), two model variants (Action-Only and Joint Action-Rationale), and
five training seeds (43-47). The archival pilot seed 42 is excluded from the
primary analysis.

Consequences:

* This is a **case study of protocol mechanics**, not a survey of models. No
  claim is made that the observed profile generalises to other architectures,
  datasets, or task families.
* Five seeds is enough to demonstrate that heterogeneity exists and to report
  it, but not enough to characterise its distribution.
* The two models differ only in whether rationale supervision is present.
  Nothing here isolates *why* they differ on the non-A axes; the practical
  equivalence on A licenses describing the S and C differences as accompanying
  differences, not as effects causally attributed to rationale supervision.

## 2. Axis-specific boundaries

### A - Action Performance

Macro-F1 at a fixed 0.5 threshold on four action labels. It is not a safety
guarantee and is not sensitive to which individual samples change, which is
precisely the blind spot Round 10 exposes.

### R - Rationale-label Performance

R measures **label recovery only**. It is not a measure of reasoning
faithfulness, explanation quality, or evidence use. A rationale Macro-F1 of
about 0.274 with six of twenty-one classes at F1 = 0 across all five seeds
means *the label recovery coverage is incomplete and highly class-dependent* -
it does not mean the model's explanations are wrong, and it does not mean the
model does not reason.

Additional boundaries:

* The 21-class ontology is BDD-OIA's. Its completeness is not established, and
  Rounds 7-9 explicitly did not establish ontology completeness.
* The zero-F1 classes are the rarest classes in the split, so the Macro-F1 is
  dominated by class imbalance in the annotation, not only by model behaviour.
* The Macro/Micro gap is large (Macro about 0.274 vs Micro about 0.503).
  Reporting either alone is misleading.
* No rationale loss, class weighting, threshold, or training procedure was
  changed to improve these numbers. The coverage holes are reported, not
  repaired.

### S - Selective Risk & Calibration

* S must not be called "Safety". It is a selective-prediction operating
  characteristic.
* The three S metrics do not agree with each other. Under the frozen
  operationalisation only AURC resolves in Joint's favour; UAR@90 and ECE are
  inconclusive.
* **Known construct mismatch.** The error definition is exact-set (any of the
  four action bits wrong) while the frozen confidence is `max_i p_i`, a
  single-bit quantity. The audit in
  `outputs/paper/tables/s_confidence_audit.md` quantifies this: empirical
  exact-set accuracy is near 0.478, but mean `max(p)` confidence is about
  0.802, giving an ECE of about 0.324. An exact-set probability proxy has ECE
  near 0.099 on the same predictions.
* The audit is a **sensitivity check, not a replacement**. `S0` (`max(p)`)
  remains the frozen primary result. Exactly three pre-registered constructions
  were compared; no fourth was added, and no construction was promoted because
  it looked better.
* The audit's own conclusion is a disagreement, reported as such: the AURC
  direction is stable across constructions, but the UAR@90 verdict is not. The
  disagreement was not tuned away.
* Temperature scaling is a single scalar fitted on the official validation
  split over the four action logits only. It was not re-fitted from test
  results.

### C1 - Prediction Stability

* The perturbations are synthetic pixel operations (brightness scaling,
  Gaussian blur, deterministic Gaussian noise) applied in memory without JPEG
  re-encoding. They are **not** a model of real-world driving conditions:
  no weather, occlusion, sensor failure, motion blur from real motion, or
  domain shift.
* C1 is therefore **not real-road robustness**.
* C1 is also **not evidence faithfulness**. A model that flips less often is
  more stable; that says nothing about whether it uses correct evidence.
* Flip rate is computed on the thresholded action set, so it is threshold- and
  calibration-dependent by construction.
* The Round 5 C1 statistics are not clustered by source video clip. Round 10
  does use a seed-then-source-clip bootstrap.

## 3. CEG: a failed extension, not a validated axis

The Causal Evidence Gap was intended to test whether models are more sensitive
to critical than to matched non-critical evidence regions. It never reached a
confirmatory measurement and is reported as a measurement boundary.

The pre-registered mask audit gates were: critical-binding correct rate
>= 0.90, control critical-evidence contamination rate <= 0.05, and semantic
label unchanged rate >= 0.95, applied both overall and per light state.

The failure chain, all recorded in `outputs/validity/`:

* **Mask v2** (`mask_audit_v2/audit_summary.json`) failed the critical-binding
  gate outright: binding 0.4167 against the 0.90 minimum. Contamination was
  within limit at 0.0463. Retained only as a detector-localised
  occlusion-sensitivity diagnostic.
* **Mask v3** (`mask_audit_v3/audit_summary.json`) failed both gates:
  state-aware filtering raised binding to 0.7451, still below 0.90, and
  contamination rose to 0.0980, above 0.05.
* **Mask v4** (`mask_audit_v4/audit_summary.json`) used a filename-disjoint
  confirmatory population of 113 red/green pairs (46 red, 67 green) with all
  210 filenames seen during v2/v3 development excluded. It passed overall
  binding (0.9381) and the semantic gate (1.0) but failed the confirmatory gate
  on the state-specific and contamination criteria: red-stratum binding 0.8478
  (below 0.90), overall contamination 0.0531 and green contamination 0.0597
  (both above 0.05). Separately, the invariant check recorded two rendered
  patches whose critical and non-critical shapes differed by one pixel column
  (`masks_v4_invariants.json`, `all_invariants_passed: false`). The recorded
  decision is "Do not run confirmatory CEG with v4", and no confirmatory CEG
  was computed.
* **BDD100K official validation labels** yielded only 53 unseen, state-matched
  candidates (34 red, 19 green), below the pre-registered population gate.
* **The one-shot BDD100K-train v5 metadata intersection** yielded at most 87
  state-matched candidates (50 red, 37 green) before hashing, against frozen
  population gates of >= 200 total with per-state and per-group minima. That
  run also used the wrong image root, so hash independence could not be
  established; fixing the root cannot raise the count above 87.

Independent review formally closed the CEG line; no v6 was created and none
will be. **CEG has not been validated, and no CEG result is reported as
evidence.** Round 6 is retained in the appendix specifically as the population
insufficiency evidence for this closure.

## 4. What the Round 10 verdict does and does not mean

The pre-registered verdict is `ROUND10_PARTIAL_OR_FAIL` with 3 of 12
family-by-axis gates passed. This is unchanged and no threshold was adjusted.

* It **does** show that the axes respond differently to the same manipulation -
  discriminant, non-redundancy evidence.
* It **does not** show that all four axes are valid constructs. Nine gates
  failed.
* It **does not** license the expectation that every perturbation should move
  every axis. A perturbation that leaves aggregate A flat while moving C1 is
  informative about the *measurements*, not a failure of the protocol.
* The A gate failures were driven partly by local non-monotonicity rather than
  by an absence of any endpoint effect, so "A did not respond" should be read
  as "A did not satisfy the frozen strict monotonic dose-response gate".

## 5. Statistical limitations

* Round 5 uses 2000 hierarchical bootstrap replicates (resample seeds, then
  images within seed). Round 10 and Round 12 use 5000 replicates with a
  seed-then-source-clip scheme.
* Round 10's 12 gates are Bonferroni-corrected one-sided at p = 1/240. The
  Round 5 intervals are **not** corrected for multiplicity across the many
  metrics in the Profile Table, so individual "CI excludes 0" readings in that
  table should be treated as descriptive rather than as confirmatory tests.
* Intervals are percentile intervals; no bias correction is applied.
* With five seeds, the seed-level resampling component of the hierarchical
  bootstrap is coarse.

## 6. Excluded from the evidence base

The following exist in the repository but are **not** scientific evidence for
any paper claim, by explicit decision:

* **Round 11** - DAAD-X external validation transport and layout engineering.
  The external dataset line was stopped; VLA4CoDrive's frozen public release
  exposes only 9 standard scenarios (at most 2160 Action/Language pairing
  windows), which independent review judged insufficient.
* **Round 13** - synthetic MTMM protocol engineering, including the Win32
  containment work.

Neither is analysed further, and neither appears in the claim-to-evidence map.

## 7. Explicitly out of scope

* No external dataset was downloaded or opened for this analysis.
* DAAD-X was not continued.
* No CEG v6 was created.
* No further Round 7-9 style permutation/map sanity was run.
* No new complex metric was designed.
* No pre-registered threshold was modified.
* No epoch, threshold, temperature, or seed was re-selected on the basis of
  test results.
* No definition was adjusted to make the four axes all significant.
* No ARSC aggregate score was designed.

## 8. Optional future work, not executed here

One experiment would most directly test the durability of these findings:
**re-run the identical BDD-OIA ARSC protocol on a different backbone and check
whether the profile shape is preserved** - in particular whether A stays
practically equivalent, whether C remains the only axis with a strong
perturbation dose-response, and whether the seed-level reversals persist.

This was deliberately **not** executed. It is recorded here and in
`ARSC_FINAL_STATUS.md` as the single optional follow-up.
