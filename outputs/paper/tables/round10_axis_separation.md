# Round 10: axis response to perturbation severity

Frozen Round 10 formal run (attempt02): 4557 test images from 3904 source clips, 5 seeds, three corruption families, clean level plus four severity levels, real re-inference.

Pre-registered verdict, unchanged: **ROUND10_PARTIAL_OR_FAIL**, 3 of 12 family-by-axis gates passed. The three that passed are the three C1 gates.

Degradation is signed so that positive always means worse: -dMacro-F1 for A and R, +dAURC for S, +d(flip rate) for C1.

| Family | Axis | Model | Clean | Max severity | Degradation | SD across seeds | Gate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| brightness | A | Action-Only | 0.6741 | 0.6709 | +0.0032 | 0.0017 | fail |
| brightness | A | Joint Action-Rationale | 0.6856 | 0.6838 | +0.0018 | 0.0021 | fail |
| brightness | R | Joint Action-Rationale | 0.2736 | 0.2692 | +0.0044 | 0.0014 | fail |
| brightness | S | Action-Only | 0.3888 | 0.3946 | +0.0058 | 0.0058 | fail |
| brightness | S | Joint Action-Rationale | 0.3722 | 0.3758 | +0.0036 | 0.0027 | fail |
| brightness | C1 | Action-Only | 0.0000 | 0.1932 | +0.1932 | 0.0081 | PASS |
| brightness | C1 | Joint Action-Rationale | 0.0000 | 0.1708 | +0.1708 | 0.0335 | PASS |
| blur | A | Action-Only | 0.6741 | 0.6599 | +0.0142 | 0.0065 | fail |
| blur | A | Joint Action-Rationale | 0.6856 | 0.6733 | +0.0122 | 0.0083 | fail |
| blur | R | Joint Action-Rationale | 0.2736 | 0.2677 | +0.0059 | 0.0041 | fail |
| blur | S | Action-Only | 0.3888 | 0.3944 | +0.0056 | 0.0081 | fail |
| blur | S | Joint Action-Rationale | 0.3722 | 0.3743 | +0.0021 | 0.0133 | fail |
| blur | C1 | Action-Only | 0.0000 | 0.2650 | +0.2650 | 0.0158 | PASS |
| blur | C1 | Joint Action-Rationale | 0.0000 | 0.2324 | +0.2324 | 0.0346 | PASS |
| noise | A | Action-Only | 0.6741 | 0.6607 | +0.0134 | 0.0066 | fail |
| noise | A | Joint Action-Rationale | 0.6856 | 0.6862 | -0.0006 | 0.0034 | fail |
| noise | R | Joint Action-Rationale | 0.2736 | 0.2687 | +0.0049 | 0.0029 | fail |
| noise | S | Action-Only | 0.3888 | 0.3821 | -0.0067 | 0.0037 | fail |
| noise | S | Joint Action-Rationale | 0.3722 | 0.3657 | -0.0066 | 0.0051 | fail |
| noise | C1 | Action-Only | 0.0000 | 0.1969 | +0.1969 | 0.0127 | PASS |
| noise | C1 | Joint Action-Rationale | 0.0000 | 0.1603 | +0.1603 | 0.0308 | PASS |

## Notes

- Largest C1 degradation at maximum severity: 0.2650. Largest absolute A degradation over the same range: 0.0142 (18.7x smaller).
- Largest absolute R degradation: 0.0059.
- S does not even agree with itself across families: AURC gets worse under brightness and blur but better under noise, which is why no S gate passed.
- C1 measures thresholded prediction-set stability under synthetic image corruption. It is not real-road robustness and not evidence about what the model attends to.
