# Seed-level heterogeneity of the ARSC profile

Frozen Round 5 five-seed study. Each model comparison is oriented so that **positive means Joint is better**; AURC, UAR@90 and ECE are lower-is-better and are negated accordingly (the frozen metric key for every row is in `outputs/paper/seed_heterogeneity.csv`).

**Every model comparison in the profile has at least one seed that reverses the sign of the five-seed mean.**

| Axis | Quantity | seed 43 | seed 44 | seed 45 | seed 46 | seed 47 | Mean | SD | 95% hierarchical CI | Seeds agreeing | Reversed seeds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | A: Action Macro-F1 | +0.020281 | +0.025495 | +0.015598 | -0.001172 | -0.002523 | +0.011536 | 0.012718 | [+0.001590, +0.021807] | 3/5 | 46, 47 |
| S | S: AURC | +0.015472 | +0.008114 | -0.006354 | +0.045048 | +0.020704 | +0.016597 | 0.018883 | [+0.000400, +0.033558] | 4/5 | 45 |
| S | S: UAR@90 | +0.015115 | -0.000731 | +0.010239 | +0.036568 | -0.005851 | +0.011068 | 0.016528 | [-0.002000, +0.026036] | 3/5 | 44, 47 |
| S | S: ECE (calibrated) | -0.000296 | -0.018920 | -0.013784 | +0.038861 | -0.008130 | -0.000454 | 0.023040 | [-0.016291, +0.020440] | 4/5 | 46 |
| C1 | C1: action-set flip rate | -0.005047 | +0.003950 | +0.027503 | +0.045132 | +0.008997 | +0.016107 | 0.020113 | [+0.001009, +0.032814] | 4/5 | 43 |
| R | R: Joint rationale Macro-F1 | +0.284311 | +0.276922 | +0.256838 | +0.245824 | +0.304051 | +0.273589 | 0.022943 | [+0.256071, +0.292872] | n/a | - |

## Notes

- The confidence intervals are the frozen hierarchical bootstrap intervals (2000 replicates, seed resampling then image resampling), reoriented to match the sign convention.
- Seed 43 reverses C1, seed 45 reverses AURC, and seeds 46 and 47 reverse the Action Macro-F1 advantage.
- The Joint rationale Macro-F1 is not a model comparison because the Action-Only model has no rationale head; its across-seed range is reported instead.
- No seed is dropped, reweighted or explained away.
