# ARSC main-result Profile Table (Round 5, BDD-OIA, seeds 43-47)

The four ARSC axes reported **separately**. There is no combined score: the axes are not commensurable, and Round 10 shows they do not respond to the same manipulation.

Cells give the frozen five-seed mean above the 95% hierarchical bootstrap interval (resample seeds, then images within seed; 2000 replicates). The *Joint advantage* column is oriented so that **positive always means Joint is better**, including for the lower-is-better metrics.

| Axis | Reads as | Explicitly does *not* measure |
| --- | --- | --- |
| A = Action Performance | 4-action Macro-F1 @ 0.5 | not a safety guarantee |
| R = Rationale-label Performance | 21-class rationale Macro-F1 @ 0.5 | not reasoning faithfulness |
| S = Selective Risk & Calibration | AURC / UAR@90 / ECE (exact-set error, calibrated) | not 'Safety'; a selective-prediction operating characteristic |
| C1 = Prediction Stability | clean vs perturbed action-set flip rate @ 0.5 | not real-road robustness, not evidence faithfulness |

| Axis | Metric | Better | Action-Only | Joint | Joint advantage | Seeds favouring Joint | Verdict at frozen criteria |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | Action Macro-F1 | higher | 0.674050<br>[+0.666304, +0.681934] | 0.685586<br>[+0.679124, +0.692179] | +0.011536<br>[+0.001590, +0.021807] | 3/5 | Joint better (95% CI excludes 0) |
| A | Action Micro-F1 | higher | 0.709682<br>[+0.704031, +0.715616] | 0.718783<br>[+0.713687, +0.724029] | n/a | n/a | reported for completeness; no frozen paired interval |
| R | Rationale Macro-F1 (21 classes) | higher | n/a | 0.273589<br>[+0.256071, +0.292872] | n/a | n/a | single-model axis (Action-Only has no R head) |
| R | Rationale Micro-F1 (21 classes) | higher | n/a | 0.503062<br>[+0.483546, +0.522462] | n/a | n/a | single-model axis (Action-Only has no R head) |
| S | AURC (exact-set error, calibrated) | lower | 0.388824<br>[+0.376467, +0.400637] | 0.372227<br>[+0.352407, +0.390232] | +0.016597<br>[+0.000400, +0.033558] | 4/5 | Joint better (95% CI excludes 0) |
| S | UAR@90 (risk at 90% coverage) | lower | 0.490931<br>[+0.482301, +0.499954] | 0.479863<br>[+0.464205, +0.492346] | +0.011068<br>[-0.002000, +0.026036] | 3/5 | inconclusive (95% CI includes 0) |
| S | ECE (calibrated) | lower | 0.324007<br>[+0.316790, +0.330847] | 0.324461<br>[+0.303098, +0.340577] | -0.000454<br>[-0.016291, +0.020440] | 1/5 | inconclusive (95% CI includes 0) |
| C1 | Action-set flip rate (mean of 3 families) | lower | 0.118543<br>[+0.112881, +0.124263] | 0.102436<br>[+0.083374, +0.116436] | +0.016107<br>[+0.001009, +0.032814] | 4/5 | Joint better (95% CI excludes 0) |
| C1 | Action-set flip rate (brightness) | lower | 0.101119<br>[+0.095677, +0.106737] | 0.087558<br>[+0.067408, +0.104280] | +0.013562<br>[-0.003557, +0.031995] | 3/5 | inconclusive (95% CI includes 0) |
| C1 | Action-set flip rate (blur) | lower | 0.126882<br>[+0.118147, +0.135046] | 0.117709<br>[+0.097738, +0.131534] | +0.009173<br>[-0.008428, +0.028224] | 3/5 | inconclusive (95% CI includes 0) |
| C1 | Action-set flip rate (noise) | lower | 0.127628<br>[+0.119596, +0.135485] | 0.102041<br>[+0.083649, +0.116788] | +0.025587<br>[+0.011322, +0.039590] | 5/5 | Joint better (95% CI excludes 0) |

## Notes

- **Action Performance produces a ranking. ARSC produces a profile.** The profile is the result; collapsing it back to one number would discard exactly the information the protocol exists to expose.
- Action Performance is practically equivalent under the pre-registered +/-0.03 margin (passed = true), which is what makes the other three axes the only place a difference can be found.
- The R axis has no Action-Only column because the Action-Only model has no rationale head. R measures rationale-label recovery only; it is not evidence about reasoning faithfulness.
- S is a selective-prediction operating characteristic computed with the frozen confidence definition conf = max_i p_i against an exact-set error. See `outputs/paper/tables/s_confidence_audit.md` for the construct-sensitivity audit; it does not replace these numbers.
- C1 is clean-vs-perturbed action-set flip rate under brightness/blur/noise on BDD-OIA images. It is not real-road robustness and not evidence faithfulness.
- Per-seed values for every comparison are in `outputs/paper/seed_heterogeneity.csv`. Of the 8 paired comparisons in this table, only 1 (Action-set flip rate (noise)) favours Joint on all five seeds; every headline comparison (A, AURC, UAR@90, ECE, C1 mean-of-three) has at least one seed that reverses the sign of its mean.
