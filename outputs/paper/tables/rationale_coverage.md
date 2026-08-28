# R axis: per-class rationale-label coverage

Frozen Round 5 study, seeds 43, 44, 45, 46, 47, threshold 0.5, n = 4557 test images, Joint model only.

R Macro-F1 = 0.273589 (95% hierarchical CI [0.256071, 0.292872]); R Micro-F1 = 0.503062 (95% hierarchical CI [0.483546, 0.522462]).

**6 of 21 classes score F1 = 0 in all five seeds** and are marked ZERO. Rows are sorted by 5-seed mean F1.

| Rationale class | Support | Support rate | Mean F1 | SD | Min-Max | Mean precision | Mean recall | Mean predicted positives | Flag |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| car | 39 | 0.0086 | 0.0000 | 0.0000 | 0.0000-0.0000 | 0.0000 | 0.0000 | 0.0 | ZERO |
| person | 34 | 0.0075 | 0.0000 | 0.0000 | 0.0000-0.0000 | 0.0000 | 0.0000 | 0.0 | ZERO |
| left_lane | 29 | 0.0064 | 0.0000 | 0.0000 | 0.0000-0.0000 | 0.0000 | 0.0000 | 0.0 | ZERO |
| left_follow | 68 | 0.0149 | 0.0000 | 0.0000 | 0.0000-0.0000 | 0.0000 | 0.0000 | 0.0 | ZERO |
| no_left_lane | 23 | 0.0050 | 0.0000 | 0.0000 | 0.0000-0.0000 | 0.0000 | 0.0000 | 0.0 | ZERO |
| left_solid_line | 69 | 0.0151 | 0.0000 | 0.0000 | 0.0000-0.0000 | 0.0000 | 0.0000 | 0.0 | ZERO |
| left_green_light | 136 | 0.0298 | 0.0056 | 0.0125 | 0.0000-0.0280 | 0.0571 | 0.0029 | 1.4 |  |
| other_obstacle | 89 | 0.0195 | 0.0087 | 0.0194 | 0.0000-0.0435 | 0.1333 | 0.0045 | 0.6 |  |
| left_obstacle | 175 | 0.0384 | 0.0384 | 0.0567 | 0.0000-0.1366 | 0.3790 | 0.0217 | 7.8 |  |
| right_obstacle | 826 | 0.1813 | 0.2765 | 0.0815 | 0.1644-0.3907 | 0.6253 | 0.1821 | 240.8 |  |
| right_solid_line | 403 | 0.0884 | 0.2926 | 0.0702 | 0.2311-0.4040 | 0.5965 | 0.1970 | 132.4 |  |
| right_green_light | 897 | 0.1968 | 0.3867 | 0.0438 | 0.3279-0.4474 | 0.6093 | 0.2854 | 420.4 |  |
| road_clear | 941 | 0.2065 | 0.3884 | 0.0554 | 0.2946-0.4413 | 0.5271 | 0.3171 | 577.6 |  |
| right_follow | 713 | 0.1565 | 0.3908 | 0.0750 | 0.2773-0.4816 | 0.6211 | 0.2914 | 335.8 |  |
| traffic_sign | 302 | 0.0663 | 0.4389 | 0.0301 | 0.4010-0.4812 | 0.7291 | 0.3152 | 131.0 |  |
| follow | 667 | 0.1464 | 0.4782 | 0.0271 | 0.4577-0.5104 | 0.5622 | 0.4198 | 500.6 |  |
| right_lane | 860 | 0.1887 | 0.4906 | 0.0549 | 0.4217-0.5469 | 0.6843 | 0.3870 | 488.2 |  |
| no_right_lane | 1182 | 0.2594 | 0.5723 | 0.0500 | 0.4888-0.6171 | 0.7123 | 0.4843 | 808.0 |  |
| red_light | 1083 | 0.2377 | 0.6012 | 0.0328 | 0.5448-0.6304 | 0.7385 | 0.5117 | 755.4 |  |
| green_light | 1574 | 0.3454 | 0.6423 | 0.0242 | 0.6064-0.6703 | 0.6731 | 0.6205 | 1460.4 |  |
| rider | 1037 | 0.2276 | 0.7342 | 0.0232 | 0.7047-0.7541 | 0.8341 | 0.6575 | 818.6 |  |

## Notes

- Support is identical across seeds because the frozen test split is shared; the script asserts this.
- A class flagged ZERO is a rationale-label recovery hole at the frozen threshold. It is not evidence about reasoning quality.
- The ZERO classes have a mean predicted-positive count of 0 in every seed: the model never emits these labels at all, so the hole is missing predictions rather than wrong predictions.
- The ZERO classes are exactly the six rarest classes (support 23-69 of 4557), so prevalence explains much of the pattern; the point of the table is that the aggregate Macro-F1 does not reveal it.
- All six left/right rationale pairs are asymmetric: the rarer left-side label is recovered far worse than its right-side counterpart (see the lateral_asymmetry block of the JSON).
- The Macro/Micro gap (0.2736 vs 0.5031) is what a single Macro number hides: Micro is carried by the recovered high-support classes.
