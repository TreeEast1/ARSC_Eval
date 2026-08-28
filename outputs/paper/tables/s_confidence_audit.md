# S confidence-construct audit (Round 5 test set, seeds 43-47)

**Sensitivity / construct audit of the selective-risk operationalisation.** This is not a replacement primary result. `S0` remains the frozen primary S axis (conf = max_i p_i) exactly as published in `outputs/validity/rq1_multiseed_summary.json`.

Motivation: the frozen S axis scores an *exact-set* error (any of the four thresholded action bits wrong) using a *single-bit* confidence (`max_i p_i`). Those two constructs do not match. The audit measures how much that matters instead of arguing about it.

Nothing was retrained. The audit reuses the frozen test logits, the frozen temperature scaling, threshold 0.5, seeds 43, 44, 45, 46, 47, and the frozen hierarchical seed-then-image bootstrap (2000 replicates, seed 20260731). Because the threshold and the temperature are unchanged, the predicted action set -- and therefore the exact-set error vector -- is identical across all three constructions. Only the *ranking* of test images changes.

| Construction | Formula | Role |
| --- | --- | --- |
| `S0` max positive probability (frozen primary) | `conf = max_i p_i` | frozen primary |
| `S1` exact-set probability proxy | `conf = prod_i q_i, q_i = p_i if bit_i predicted else 1 - p_i` | construct audit alternative |
| `S2` weakest-bit certainty | `conf = min_i max(p_i, 1 - p_i)` | construct audit alternative |

`S0` reproduces the frozen published values to within 1e-09 on every checked field (18 checks, all passed = true), which is what licenses comparing `S1` and `S2` against it.

| Construction | Role | Metric | Action-Only | Joint | Joint - Action-Only | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| S0 | frozen primary | AURC | 0.388824<br>[+0.376467, +0.400637] | 0.372227<br>[+0.352407, +0.390232] | -0.016597<br>[-0.033558, -0.000400] | Joint better |
| S0 | frozen primary | UAR@90 | 0.490931<br>[+0.482301, +0.499954] | 0.479863<br>[+0.464205, +0.492346] | -0.011068<br>[-0.026036, +0.002000] | inconclusive |
| S0 | frozen primary | ECE | 0.324007<br>[+0.316790, +0.330847] | 0.324461<br>[+0.303098, +0.340577] | +0.000454<br>[-0.020440, +0.016291] | inconclusive |
| S1 | construct audit alternative | AURC | 0.339804<br>[+0.329759, +0.349436] | 0.318514<br>[+0.300615, +0.333249] | -0.021290<br>[-0.035928, -0.009964] | Joint better |
| S1 | construct audit alternative | UAR@90 | 0.488250<br>[+0.479131, +0.496977] | 0.477231<br>[+0.461432, +0.489469] | -0.011019<br>[-0.025160, +0.002097] | inconclusive |
| S1 | construct audit alternative | ECE | 0.098722<br>[+0.090703, +0.106820] | 0.095504<br>[+0.086803, +0.105860] | -0.003218<br>[-0.010496, +0.004816] | inconclusive |
| S2 | construct audit alternative | AURC | 0.344116<br>[+0.334278, +0.353691] | 0.321203<br>[+0.304285, +0.334873] | -0.022913<br>[-0.039379, -0.010254] | Joint better |
| S2 | construct audit alternative | UAR@90 | 0.494734<br>[+0.485761, +0.503414] | 0.480887<br>[+0.463918, +0.494442] | -0.013847<br>[-0.028571, -0.000779] | Joint better |
| S2 | construct audit alternative | ECE | 0.184908<br>[+0.177145, +0.192741] | 0.174949<br>[+0.164769, +0.186277] | -0.009960<br>[-0.020567, +0.001247] | inconclusive |

## Notes

- All three metrics are lower-is-better, so a wholly negative `Joint - Action-Only` interval means Joint is better.
- **Q1 - does the S conclusion depend on the confidence definition?** yes at least one metric changes verdict. The AURC direction is stable across constructions (stable = true), but the UAR@90 verdict is not (stable = false): it is inconclusive under S0 and S1 and resolves in Joint's favour only under S2. So the S conclusion is partly construct-dependent.
- **Q2 - do AURC, UAR@90 and ECE still disagree?** metrics disagree under at least one construction. The three metrics fail to agree within every construction (agreement by construction: S0 = false, S1 = false, S2 = false). Changing the confidence definition does not make the S metrics converge, so they must be reported separately.
- **Q3 - is `max(p)` mismatched with exact-set correctness?** Yes, measurably. The empirical exact-set error rate is 0.5220 for Action-Only and 0.5104 for Joint, i.e. exact-set accuracy near 0.478. Mean S0 confidence is 0.8020 -- far above that accuracy -- and the resulting S0 ECE is 0.3240. The exact-set proxy S1 has mean confidence 0.3795 and ECE 0.0987. `max(p)` is scoring a different event from the one the error definition counts.
- The constructions disagree and that disagreement is the reported finding. No further confidence definitions were tried, no construction was promoted to primary, and no threshold, temperature, seed or bootstrap setting was changed to reduce the disagreement.
- This audit varies only how test images are *ranked* for selective prediction. It does not measure safety, and it does not show that any construction is the correct one.
