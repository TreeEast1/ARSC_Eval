# Round 9 独立事后科研审阅：20-map 条件稳健性

审阅对象：BDD-OIA Round 9 `attempt01` 正式结果、正式代码、冻结协议、完整独立复算、日志，以及 Round 8/RQ1/RQ2 的既有结论。

## 1. 最终裁决

**计算与形式层：PASS。冻结的 Round 9 条件门槛确实为 `ROUND9_FULL_PASS`。**

**科学与构念层：BOUNDED CONDITIONAL PASS。** Round 9 建立的是：在同一批 4,557 张 BDD-OIA 测试图像、五个训练 seed、20 个预先固定且 outcome-blind 的合法 association map，以及冻结的 map×seed×association-component 重采样程序下，A、R、S、C1 四条 graded-response 门槛对 map realization 稳健。它不是外部有效性、完整构念有效性、rationale faithfulness、因果证据或真实道路安全性的证明。

Round 8 留下的单 map/salt 缺口已经按预注册方式关闭。按照既定停止规则，**BDD-OIA salt/map 主线到此终止，不再增加 salt、map、q 网格或 bootstrap 次数。**

## 2. 正式结果与独立复算

正式结果为：

| Axis | positive maps | point grand mean bottleneck | 预注册 pointwise percentile interval | gate |
|---|---:|---:|---:|---|
| A | 20/20 | 0.068647584 | [0.064261314, 0.067624000] | PASS |
| R | 20/20 | 0.045433441 | [0.040588555, 0.047385435] | PASS |
| S | 20/20 | 0.027079873 | [0.021644456, 0.026685809] | PASS |
| C1 | 20/20 | 0.163593739 | [0.155702463, 0.160482023] | PASS |

每一轴同时满足：至少 18/20 map 为正、20-map point grand mean 为正、bootstrap interval 下界为正、grand-mean component curve 无相邻方向反转。实际观察到的是更强的有限集合结果：四轴均为 20/20 map 正向。

独立 verifier 明确不 import 正式分析脚本或 `arsc_eval` 实现模块，而是复用独立 Round 8 sufficient-statistic 实现后重新构造全部 20-map 统计量。独立审计结果为 **8/8 checks PASS**：

- 20 maps × 5 seeds × 5 q 的所有 primary curves、完整 diagnostics 与 bottlenecks 均重新计算；
- point/diagnostic 最大绝对差为 `2.2315482794965646e-14`，低于冻结容差 `5e-13`；
- map×seed bottleneck 最大差为 `1.4765966227514582e-14`，map mean bottleneck 最大差为 `4.784367346744034e-15`；
- 2,000 次 bootstrap 的 map positions、共享 seed positions、每次 map occurrence 的 component 抽样、expanded image counts 以及 A/R/S/C1 四轴数值全部逐元素精确一致，最大数值差为 `0.0`；
- 正式与独立 bootstrap NPZ 的文件 SHA256 完全相同：`C31AF6BFB6015FC499CDA7A2D7FB875C07BB61E2829EB39F3801CB24E71BCD43`；
- 独立 gate 与正式 gate 均为 `A=true, R=true, S=true, C1=true`；
- Round 8 q=0 bridge 最大差为 `0.0`。

因此，正式/独立实现的一致性足以确认冻结门槛；这里没有发现能推翻 `ROUND9_FULL_PASS` 的计算错误。

## 3. 20 maps 与区间应如何解释

20 个 map 不是 20 个数据集，也不是 20 个独立道路域。它们全部重用同一批 4,557 张图像、同一组 target/prediction/confidence 和同五个训练 seed，只改变 outcome-blind association realization。因此：

1. `20/20 positive` 是对预固定有限 map 集合的强稳健性证据；
2. map 层重采样反映的是这 20 个算法性 realization 的变异，不增加 town、weather、camera、institution、model family 或 ontology 覆盖；
3. 跨 map 共享一次 seed draw 是必要的，因为每个 map 观察到的是同五个训练 seed；把每个 map 的 seed 当作新独立训练会伪增样本量；
4. 每个 map occurrence 使用自身 source-closed association components，并在该 occurrence 内对所有 seed/q/model/axis/perturbation 共享 component draw，符合冻结依赖结构；
5. 这些区间只能命名为冻结程序下的 **map×seed×per-map-component 条件 percentile intervals**。它们不是对新数据集、真实道路总体或所有合法 salt 的总体置信区间。

四个区间是逐轴 pointwise intervals，不具有 simultaneous familywise 95% coverage。`ROUND9_FULL_PASS` 是四个预注册门槛的交集，不应改写成“四指标联合具有 95% 置信度”。

还需透明报告一点：bootstrap 分布均值为 A=`0.065979041`、R=`0.043905897`、S=`0.024034196`、C1=`0.158119425`，低于相应 point grand mean；A、S、C1 的 point estimate 甚至高于其 percentile interval 上界。这与“对非线性最弱相邻步 bottleneck 在 component 重采样后重新取 minimum”的有限样本 bootstrap 偏移相容，且正式与独立实现逐元素相同，所以不构成协议执行错误，也不改变所有 interval lower > 0 的冻结判定。但论文必须同时给出 point statistic 与程序性 interval，不能把该 interval 误画成必然以 point estimate 为中心的常规误差条。

20-map point bottleneck 的离散程度较小但不是零：

| Axis | map mean 的 sample SD | map min | map max |
|---|---:|---:|---:|
| A | 0.001725005 | 0.065054745 | 0.071225596 |
| R | 0.000973499 | 0.043672888 | 0.047276210 |
| S | 0.001342486 | 0.024005238 | 0.029421482 |
| C1 | 0.001940356 | 0.160617365 | 0.167668788 |

这支持“结果没有依赖某一个特殊 salt”，但不支持“map 变异已经覆盖外部域变异”。

## 4. Rationale 的六个恒零类别

正式 primitive 中没有 zero-target-support rationale class。以下六类在所有 20 maps × 5 seeds × 5 q 中 target support 固定为正、predicted-positive count 恒为 0、F1 恒为 0：

| class | target positives | predicted positives |
|---|---:|---:|
| `car` | 39 | 0 |
| `person` | 34 | 0 |
| `left_lane` | 29 | 0 |
| `left_follow` | 68 | 0 |
| `no_left_lane` | 23 | 0 |
| `left_solid_line` | 69 | 0 |

这不是“类别在测试集缺失”，而是冻结 0.5 阈值下的模型覆盖失败。由于这些类别的 prediction 恒为零，target association 怎样重排都不能让它们产生 q 响应；R Macro-F1 的正向 graded response 由其余 15 个有响应类别驱动，并被六个恒零项稀释。

所以 R gate PASS 支持的是“当前 21-class Macro-F1 aggregate 对 score-bearing 类别的 association destruction 有方向性响应”，不支持：

- 21 类 ontology 均被模型学会；
- 六个恒零类已得到类别级构念验证；
- macro 或 micro 汇总可以替代 per-class support、predicted-positive coverage 和 per-class F1 报告；
- rationale label correctness 等同于 explanation faithfulness 或 grounding。

## 5. 对 RQ1 / RQ2 的影响

### RQ1

RQ1 关心动作准确率相近的模型是否在 rationale、safety 或 stability 上存在差异。模型间动作等价、R/S/C1 差异与五 seed 方向性已经由 Round 5 的冻结比较回答。Round 9 不新增模型间效应量，也不应改写为“rationale supervision 的因果收益”；它只增强了 A/R/S/C1 这些既有统计量对 association-map realization 的内部稳健性。

### RQ2

RQ2-light 仍只支持：在冻结 brightness/blur/noise 轻扰动下，Joint 平均 action flip 少于 Action-only。Round 9 进一步表明 C1 的 clean–perturbed correspondence statistic 会随配对关系破坏而分级响应，但没有建立自然视觉 severity 标尺。

RQ2-CEG 继续保持 **UNANSWERED / CLOSED**。Round 9 不恢复失败的 mask measurement gate，也不能把 C1 correspondence sensitivity 写成“模型依赖正确关键证据”。

## 6. 合规 claim boundary

可以声称：

> 在冻结的 BDD-OIA 4,557-image population、五训练 seed、20 个预固定 outcome-blind 合法 association maps，以及 map×seed×association-component 条件推断下，A/R/S/C1 四条 graded association-response gate 均通过；四轴均为 20/20 map 正向，正式结果由独立实现完整复算。

不可以声称：

- 20 maps 是 20 个独立数据集、域或真实重复；
- 四个 pointwise intervals 提供四轴 simultaneous 95% coverage；
- ARSC 已具有跨数据集、跨 architecture 或真实道路外部有效性；
- R 已验证 ontology completeness、rationale grounding 或 faithfulness；
- S 的 tie-AURC 响应等于 calibration validity 或安全保证；
- C1 已验证自然 corruption severity、因果鲁棒性或关键证据依赖；
- RQ2-CEG 已回答；
- Round 9 是新模型训练、新数据推理或外部 replication。

## 7. 下一轮唯一优先方向

候选方向的信息价值排序为：

1. **BDD-OIA 真实输入像素 corruption 的多 severity dose-response 构念验证**；
2. 通过独立 ontology/population feasibility gate 后的外部数据 replication；
3. 新的人类 rationale grounding/faithfulness 标注研究。

本裁决只授权第 1 项进入 **outcome-blind 预注册与 preflight**，不同时启动第 2、3 项。原因是：

- Round 9 已经终止 salt/map 不确定性，继续同类 map 几乎不增加构念信息；
- 第 1 项直接补上 Round 8/9 明确未回答的“视觉 corruption severity”缺口，并与 RQ2-light 原有 brightness/blur/noise 分支同源；
- 它可在同一 BDD-OIA population、现有五个冻结 checkpoint 和原四指标内执行，不需要搜索新 metric、模型或数据集；
- 它使用真正经过像素变换后重新推理的模型输出，而不是将已有 prediction/target association 重排；
- 已审查的 VLA4CoDrive 仍不满足 town/scene/ontology gate；此时横向寻找并训练新数据集会把“构念验证”变成数据集搜索。

建议冻结为一个窄的 Round 10：

1. 只用既有三类变换：brightness、Gaussian blur、Gaussian noise；
2. 每类预先固定 identity 加四个非零 severity，参数依据图像统计与语义不变审计确定，不得查看模型 metric 后调级；
3. 固定 BDD-OIA 4,557 张测试图像、训练 seeds 43–47、现有 Action-only/Joint checkpoints、0.5 阈值、A/R/S/C1 定义；
4. 对每个 severity 做真实的 paired image inference；禁止 prediction reassignment、association map 或新 salt；
5. 在读任何新 severity outcome 前完成每个 corruption×severity stratum 的 label/scene-semantic audit；失败的 stratum 按预注册规则整体 STOP，不换一个更容易通过的 severity；
6. 主要检验冻结 expected direction：severity 增大时 A/R 不升、tie-AURC 不降、action flip 不降、rationale Jaccard 不升；具体 bottleneck、实用阈值、multiplicity 与失败规则必须在 outcome-blind protocol 中冻结；
7. 以原始 clip/source 为 cluster，对同一 resample 同时评估所有 severity、model、axis 和 corruption family；三个 corruption family 必须分别完整报告，不能只选择或汇总 passing family；
8. 正式运行仍只允许一次，结果无论 PASS/FAIL/INCONCLUSIVE 都终止该 severity grid，不追加 seed、severity、corruption 或阈值追逐结论。

该实验若通过，只能称为“对三种预固定像素 corruption severity 的 BDD-OIA 内部构念响应”；它仍不是自然发生 corruption 的流行率估计或外部道路安全验证。

## 8. 独立 audit 日志的空 `EXIT_CODE`

正式日志以 `EXIT_CODE=0` 结束；独立 audit 日志末尾为 `EXIT_CODE=` 空值。独立 audit JSON 已原子化完整写出，状态为 PASS，8/8 checks 完整，独立 draw artifact 完整，且其 NPZ 与正式 NPZ 文件哈希相同。日志也包含 2,000/2,000 bootstrap 完成与完整 JSON 输出。

因此该空值是 **tmux/bash launcher 的 shell exit-code observability defect**，不是统计计算失败，也不降低上述独立复算证据。后续若复用 launcher，应先用非科研 smoke command 修复并验证 exit marker；不应为了填补这一日志字段而重跑 Round 9 或改变其正式结果。

## 9. 停止与禁止事项

- 不再运行任何 BDD-OIA salt/map robustness 实验；
- 不因 CI 想更窄而增加 map、bootstrap replicate 或 seed；
- 不重跑 Round 9 来修复独立 launcher 的空 exit marker；
- 不把六个恒零 rationale class 隐藏在 aggregate 指标后；
- 不恢复 CEG/mask 主线；
- 不绕过既有 VLA4CoDrive population/ontology STOP；
- 不在查看新 corruption outcomes 后修改 severity、metric、gate、cluster unit 或 passing subset；
- 不在 Round 10 outcome-blind protocol 与独立 GO 之前运行正式新 severity 推理。

## 10. Reviewer decision

**CONFIRM_ROUND9_FULL_PASS_WITH_BOUNDED_CONDITIONAL_CLAIM**

下一动作：**仅为 Round 10 BDD-OIA pixel-space corruption dose-response construct validation 编写 outcome-blind protocol 与 preflight；BDD salt/map 线永久关闭。**
