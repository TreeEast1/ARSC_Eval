# Round 7 独立结果前预注册审阅

日期：2026-07-31  
审阅对象：`outputs/validity/arsc_axis_falsification_protocol.json`  
对象 SHA256：`21504FD66E984E211C3E8C51AF013C7C30F8D6E14CFCE01A832FD53711482442`  
结果边界：未运行、请求或查看任何 intervention outcome  
最终裁决：**GO_WITH_AMENDMENT**

## 1. 总体判断

协议方向科学且严格受限：

- 只使用 seeds 43–47 已冻结 prediction caches；
- 不增加数据、训练、推理或 masks；
- 不恢复已经关闭的 CEG；
- 控制映射、threshold 和 random seeds 已冻结；
- 明确禁止 causal faithfulness、external validity 与 real-world safety 主张；
- 失败结果必须保留，禁止更换 permutation 或 threshold。

A/R 的 target destruction、S 的 ordering controls 和 C1 的 pairing controls 均可构成内部 measurement falsification。但当前版本仍有三个结果前必须修正的问题：

1. image 与 training seed 是 **crossed**，不是 image nested within seed；现 bootstrap 描述可能造成伪重复；
2. S 的 oracle/adversarial 是 metric implementation/ordering sanity，而 original-vs-one-random-order 测的是具体模型 confidence informativeness；二者被 `full_suite_pass` 混为一个 S validity gate；
3. exact invariants 尚未覆盖原 Round 5 结果复现、permutation bijection、wrong-pair clip identity 和原数组不可变性。

这些修订均不需要 outcome，并且不改变 frozen interventions，因此允许一次、仅一次 Amendment 01。修订完成并再次独立确认前不得运行分析。

## 2. A permutation 审查

### 2.1 合理性

A controls 包含：

- perfect；
- original；
- row-destroyed；
- class-destroyed；
- row-and-class-destroyed。

`(i+2281) mod 4557` 是无 fixed point 的 cyclic row permutation；`[1,2,3,0]` 是四 action columns 的循环置换。两者合用破坏：

- 预测与具体样本 target 的对应；
- Forward/Stop/Left/Right 的 class identity。

以：

```text
original Macro-F1 - row_and_class_destroyed Macro-F1
```

作为强 negative-control contrast 是合理的。它检验的是 Macro-F1 是否对已知错误的 sample/class association 敏感。

### 2.2 解释边界

即使通过，也只能声称：

> 冻结 A 实现会对严重破坏的 target association 作出预期响应。

不能声称：

- 四动作 ontology 本身获得构念效度；
- 模型 action predictions 正确；
- A 能检测所有类型的小错误；
- A 与 R/S/C 具有因果独立性。

row-and-class destruction 是强、复合 falsification；它不定位响应究竟来自 row 破坏还是 class 破坏。因此必须同时报告 original、row-only、class-only 和 combined control，不能只报告 primary combined contrast。

### 2.3 需要补充的 exact invariants

当前 A 未单列 `required_invariants`。Amendment 必须加入：

- row map 是 `0..4556` 的严格 bijection；
- row fixed points=0；
- class map 是 `0..3` 的严格 bijection；
- class fixed points=0；
- action probabilities/logits 在所有 A controls 中 bitwise unchanged；
- original action targets unchanged；
- row-only permutation 保持每个 action class 的 positive count 完全不变；
- R、S、C1 的输入和 point estimates 完全不变；
- original A point estimates 与冻结 Round 5 对应值逐 seed 精确复现。

## 3. R permutation 审查

### 3.1 合理性

R 采用相同 row permutation，并把 21 个 rationale columns 循环移动 7 位。该 class map：

- 是 bijection；
- 没有 fixed point；
- 不改变数组维度；
- 会破坏具体 ontology class identity。

对稀疏、类别不平衡的 rationale labels，combined row/class destruction 是合理的强 negative control。

### 3.2 主要限制

BDD-OIA Rationale Macro-F1 在 Round 5 已较低，且多个类别的模型 F1 为 0。破坏后的 Macro-F1 可能受以下因素影响：

- 类别 prevalence 差异；
- 全零预测；
- zero-division convention；
- 稀有类；
- class shift 后偶然的 prevalence 匹配。

所以必须报告：

- Macro-F1 与 Micro-F1；
- 每类 F1；
- 每类 target/predicted positive count；
- row-only、class-only、combined 三种结果；
- five seed raw contrasts。

通过只能证明 R metric 对冻结强破坏敏感，不能证明 rationale correctness、ontology quality、grounding 或 faithfulness。

### 3.3 需要补充的 exact invariants

除协议已有 action/A/S/C1 不变要求外，还应加入：

- 21-class map 是严格 bijection 且 fixed points=0；
- row-only 保持每个 rationale class positive count；
- combined mapping 不修改 rationale probabilities/logits；
- original rationale targets 未被 in-place 覆盖；
- perfect control 对所有有 positive support 的类为 1；
- 明确记录 zero-support class 的 F1 convention；
- original R point estimates与冻结 Round 5 逐 seed 精确复现。

如果某 rationale class 在 target 中没有 positive support，不能机械要求该类 perfect F1=1；必须按既有 metric convention 明确处理。整体 perfect Macro/Micro=1 的 gate 只有在所有类均有正例时才无歧义。

## 4. S ordering 审查

### 4.1 Oracle / adversarial ordering：严谨

S 固定：

- calibrated action probabilities；
- threshold=0.5；
- exact-set error；
- 只改变 confidence ordering。

正 temperature 不改变每个 logit 的符号，所以 thresholded predictions 与 raw logits 相同。只要 scores 无 ties：

- oracle 把所有 correct 放在所有 errors 前；
- adversarial 把所有 errors 放在所有 correct 前；
- oracle AURC 应为可实现下界；
- adversarial AURC 应为可实现上界。

协议要求每 seed、每 model 检查 extremal ordering，并要求 prediction/error/A invariants bitwise identical，这是严谨的 S metric implementation falsification。

### 4.2 Original vs random：不是纯 metric falsification

```text
random AURC - original AURC
```

检验的是冻结模型的 confidence ranking 是否比一个固定随机排列更有信息，而不是 AURC 是否会响应 ordering。若该 contrast 失败，可能因为：

- 模型 confidence 不提供有效排序；
- 单个 frozen random order 偶然较好；
- maximum-action-probability 与 exact-set error 构念不匹配。

它不意味着 oracle/adversarial 已通过的 AURC implementation 无效。

当前 protocol 的 partial policy 已隐约承认这一点，但 `full_suite_pass` 又要求全部八个 directional contrasts 通过，逻辑不一致。

### 4.3 必须修订的决策分类

Amendment 必须把 S 分成两个结果：

1. **S measurement-ordering gate**  
   由 exact invariants + oracle/adversarial extremal gate 决定。

2. **Frozen-model confidence-informativeness result**  
   由 original-vs-frozen-random contrast 决定，Action-only 与 Joint 分别报告。

`full_suite_measurement_pass` 不得因 original-vs-random 失败而把 S metric implementation 判为失败。可以另报：

```text
full_empirical_battery_pass
```

但必须明确它包含模型属性，不是纯 measurement validity。

### 4.4 Random 与次指标边界

一个 fixed random permutation 可以作为预注册 reference，但不能称为“随机排列分布”或“random expectation”。不得事后增加更多 random seeds。

ECE 依赖 confidence 数值而不仅是排序。oracle/random/adversarial 使用人为分配的 `[0,1]` unique scores，因而这些 controls 下的 ECE 高低取决于任意 score spacing。Amendment 必须规定：

- AURC、UAR@90、correctness AUROC 可用于 ordering controls；
- synthetic orderings 的 ECE 只作数值诊断，不能形成 directional validity claim；
- calibrated ECE 的科学解释仍仅限 original frozen confidence。

### 4.5 需要补充的 exact invariants

- 四种 orderings 的 thresholded predictions bitwise identical；
- exact-set error vector bitwise identical；
- A Macro/Micro-F1 bitwise identical；
- original calibrated probabilities bitwise unchanged；
- synthetic scores 全部有限、唯一、严格产生声明的 descending order；
- oracle 中 `max(score_error) < min(score_correct)`；
- adversarial 中 `max(score_correct) < min(score_error)`；
- original S point estimates与 Round 5 逐 seed 精确复现；
- R/C1 arrays 与 point estimates完全不变。

## 5. C1 wrong pairing 审查

### 5.1 合理性

identity、correct 和 wrong pairing 构成清晰的三层 control：

- identity：实现上界，flip=0、Jaccard=1；
- correct：真实同一 image 的 clean/perturbed pairing；
- wrong：clean image 与另一 image 的 perturbed prediction 配对。

wrong pairing 应提高 action flip、降低 rationale Jaccard。它检验 C1 是否依赖正确的 sample correspondence，而不是仅反映两组总体 prediction prevalence。

### 5.2 解释边界

wrong pairing 同时改变图像内容、action context 与 rationale content。它不是“更强扰动”，也不是自然鲁棒性 benchmark。

通过只能声称：

> C1 能区分正确配对与被破坏的文件对应。

不能声称：

- C1 已获得外部构念效度；
- wrong pairing 的差值量化真实 perturbation severity；
- C1 证明 rationale correctness 或 causal faithfulness。

### 5.3 需要补充的 exact invariants

`(i+997) mod 4557` 除 no fixed point 外还必须验证：

- 是 `0..4556` 的严格 bijection；
- five seeds/models/perturbations 使用完全相同 map；
- correct pairing 的 clean/perturbed file order完全一致；
- wrong pairing 中 source filename 与 clean filename 全部不同；
- wrong pairing 中 same clip-group pairs=0；
- pairing change 不修改任何 logits/probabilities，只修改索引关系；
- identity action flip逐样本全为0，而非只要求均值0；
- identity rationale Jaccard逐样本全为1；
- clean A/R/S arrays 与逐 seed point estimates精确复现 Round 5。

same clip-group 是纯 filename-derived input invariant，不涉及 intervention outcome。若当前 offset 997 违反该门，应 STOP 并重新审阅；本 amendment 不授权在检查后自行挑选另一 offset。

## 6. Bootstrap 与伪重复

### 6.1 当前问题

协议写：

> resample five training seeds, then resample 4557 canonical image indices within every selected seed

五个 training seeds 使用的是相同 4,557 images、相同 targets 与相同 filename order。image 与 seed 是 crossed factors，不是 image nested within seed。

若每个被抽到的 seed 独立抽一份 image indices，会破坏同一 test image 跨 seed 的配对，并把共享 test set 当成多组独立 image samples。这可能低估或扭曲图像层不确定性。

### 6.2 唯一允许的 bootstrap 修订

Amendment 必须改为 crossed paired bootstrap：

1. 每 replicate 从 5 个 training seeds 有放回抽 seed indices；
2. 每 replicate 从 4,557 个 canonical image indices **只抽一份**有放回 image multiset；
3. 将同一 image multiset 应用于该 replicate 中所有被抽 seed；
4. 对同一 seed/image，保留 model、original/destroyed target、confidence ordering、correct/wrong pairing、三种 perturbation 的完整配对；
5. seed 重复抽中时，保留该 seed 的同一输出，不重新生成独立 image draw；
6. 2,000 replicates、seed=20260802、percentile 95% interval 不变。

这项修订只改变 uncertainty resampling structure，不改变 point estimates、interventions 或 decision direction。

### 6.3 判定规则

“mean positive + 4/5 seeds positive + hierarchical CI lower>0”对强 falsification 是保守且可接受的。

八项 fixed contrasts 不作八次独立 discovery，因此无需用多重性校正来决定 `full_suite`；但：

- 每个 raw interval 必须报告；
- 失败不能隐去；
- 不得挑选通过的 contrasts 宣称整个 axis 通过；
- `full_suite_measurement_pass` 与包含 model-confidence 的 empirical battery 必须分开。

只有 5 seeds，CI 仍只能支持固定训练协议下的内部重复性，不能外推新 seeds population、架构或数据集。

## 7. Exact invariants 是否充分

当前 perfect A/R、identity C1、S prediction/error invariance 和 clean A/R/S invariance方向正确，但仍不足。Amendment 01 必须增加一个统一的 pre-analysis exact audit：

1. 所有 cache/calibration/input hashes匹配 protocol；
2. five seeds filename/target arrays bitwise identical；
3. filenames 唯一，targets binary且有限，logits有限；
4. 所有 row/class/pairing maps为合法 bijection；
5. 所有声明的 fixed points/counts经机器核验；
6. wrong pairing same filename=0、same clip-group=0；
7. perfect A/R按冻结 zero-support convention通过；
8. identity C1逐样本通过；
9. S scores/orderings满足严格 separation；
10. 每个 intervention 都不 in-place 修改 frozen arrays；
11. original A/R/S/C1 逐 seed point estimates与 Round 5 artifacts精确复现；
12. 任一 invariant 失败时，在 bootstrap 和 directional结果计算前 STOP。

该 audit 只能输出 pass/fail、hash 与 invariant diagnostics；不得用失败结果调整 permutation、offset、threshold 或 confidence definition。

## 8. 唯一允许的 Amendment 01

在不查看任何 intervention outcome 前，允许一次 amendment，且只能包含：

1. 把 bootstrap 改为第 6.2 节 crossed seed × shared-image paired bootstrap；
2. 把 S measurement-ordering validity 与 original-vs-random model-confidence informativeness 分成两个 decision；
3. 明确 synthetic-ordering ECE 不进入 directional validity claim；
4. 增加第 7 节 exact invariants；
5. 明确 A/R/C1 的 claim boundaries 与 intermediate controls 全量报告。

不得修改：

- cache inputs；
- seeds 43–47；
- threshold 0.5；
- row maps；
- class maps；
- wrong offset 997；
- random seed/order；
- intervention definitions；
- point-estimate contrasts；
- 4/5 direction rule；
- A/R/C1 directional CI rule；
- S oracle/adversarial extremal rule；
- bootstrap replicates/seed/confidence level；
- outcome-independent prohibited claims。

如果 wrong pairing same clip-group invariant不为0，或 perfect control因 zero-support definition无法按既有 metric无歧义计算，应 STOP 并再次独立审阅；不得在 Amendment 01 内选择新 offset、删除类别或改变 metric convention。

## 9. 最终裁决

**GO_WITH_AMENDMENT**

协议的 interventions 本身合理，且研究范围符合 Round 5/6 的边界。但在以下事项冻结并独立确认前不得运行：

- crossed bootstrap；
- S metric gate 与 model-confidence gate分离；
- synthetic ECE claim限制；
- expanded exact invariant audit。

Amendment 01 通过后，可运行一次 frozen falsification suite。通过结果只能支持：

> BDD-OIA、五个冻结训练 seeds 下，A/R/S/C1 对预定义强干预具有内部 measurement sensitivity 与部分 discriminant behavior。

它永远不能恢复 CEG、证明 causal faithfulness 或提供外部效度。
