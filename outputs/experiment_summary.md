# BDD-OIA ARSC-Eval 实验总结

更新时间：2026-07-31  
主实验：五个新配对随机种子 43–47  
历史 pilot：seed 42，仅保留，不并入主结果

## 1. 研究问题与边界

本项目检验四个互补维度是否比 Action Accuracy 单列更充分地描述驾驶模型：

- A（Accuracy）：四动作预测质量；
- R（Rationale）：21 类理由标签预测质量；
- S（Safety）：错误样本能否被置信度排序并在选择性预测中拒绝；
- C（Consistency）：轻微语义保持扰动下的动作/理由稳定性；
- CEG 是 RQ2 的独立 critical-evidence 子分支，不因 C1 通过而自动成立。

本轮可回答 RQ1 与 RQ2-light；RQ2-CEG 因 mask measurement gate 失败，保持
“未回答”，不报告确认性 CEG。

## 2. 数据、模型与冻结协议

- 官方样本：train=16,082，validation=2,270，test=4,572。
- 四动作任务有效样本：train=16,038，validation=2,258，test=4,557。
- 两模型共用 ImageNet 预训练 ResNet-50：
  - Action-Only：4 维 action head；
  - Joint Action-Rationale：共享 backbone，4 维 action head + 21 维
    rationale head，`Loss = Action BCE + Rationale BCE`。
- 每个 seed 内两个模型使用相同 backbone/action-head 初始化、数据顺序、
  split、增强、五轮训练预算和验证动作 F1 checkpoint 规则。
- 动作与理由阈值固定为 0.5；test 不用于调 epoch、seed、阈值、温度或
  checkpoint。
- 两个模型分别在 validation action logits 上拟合正标量温度。
- C1 在推理时使用无损内存变换：brightness=1.10、Gaussian blur
  radius=1.0、确定性 Gaussian noise=5/255。
- 单 seed 使用 2,000 次图像配对 bootstrap；五种子使用 2,000 次层级
  bootstrap：先重采样训练 seed，再在每个被选 seed 内重采样图像。

## 3. 五种子主结果

| 指标 | Action-Only | Joint | 差值定义与均值 | 层级 95% CI |
|---|---:|---:|---:|---:|
| Action Macro-F1 | 0.674050 | 0.685586 | Joint−Action = +0.011536 | [0.001590, 0.021807] |
| Rationale Macro-F1 | N/A | 0.273589 | N/A | [0.256071, 0.292872] |
| Rationale Micro-F1 | N/A | 0.503062 | N/A | [0.483546, 0.522462] |
| AURC（越低越好） | 0.388824 | 0.372227 | Joint−Action = −0.016597 | [−0.033558, −0.000400] |
| UAR@90（越低越好） | 0.490931 | 0.479863 | Joint−Action = −0.011068 | [−0.026036, 0.002000] |
| calibrated ECE（越低越好） | 0.324007 | 0.324461 | Joint−Action = +0.000454 | [−0.020440, 0.016291] |
| 三扰动平均 Action Flip | 0.118543 | 0.102436 | Action−Joint = +0.016107 | [0.001009, 0.032814] |
| Joint 三扰动 Rationale Jaccard | N/A | 0.916003 | N/A | [0.908090, 0.926552] |

### 3.1 每个 seed 的配对效应

| Seed | ΔAction F1（J−A） | ΔAURC（J−A） | ΔUAR@90（J−A） | ΔECE-cal（J−A） | Flip 优势（A−J） | Joint R Macro-F1 |
|---:|---:|---:|---:|---:|---:|---:|
| 43 | +0.020281 | −0.015472 | −0.015115 | +0.000296 | −0.005047 | 0.284311 |
| 44 | +0.025495 | −0.008114 | +0.000731 | +0.018920 | +0.003950 | 0.276922 |
| 45 | +0.015598 | +0.006354 | −0.010239 | +0.013784 | +0.027503 | 0.256838 |
| 46 | −0.001172 | −0.045048 | −0.036568 | −0.038861 | +0.045132 | 0.245824 |
| 47 | −0.002523 | −0.020704 | +0.005851 | +0.008130 | +0.008997 | 0.304051 |

上述表显示：

- Action F1 在 3/5 seed 为正、2/5 接近 0；跨 seed 平均为正；
- AURC 在 4/5 seed 改善且层级 CI 刚好排除 0；
- UAR@90 与 ECE 的 seed 方向不稳定，层级 CI 均跨 0；
- C1 在 4/5 seed 为正，但效应从 −0.0050 到 +0.0451，存在明显训练 seed
  异质性。

## 4. 预注册判定

### 4.1 RQ1：动作可比性通过

动作等价边界预先固定为 `[-0.03, +0.03]`。五种子
`ΔAction F1=+0.011536`，层级 95% CI 为 `[0.001590, 0.021807]`，完整落入
等价边界，因此 S/C1 的模型间比较满足冻结的动作可比前提。

CI 同时大于 0，说明当前训练协议下 Joint 的平均动作 F1 更高；但它仍属于
预先定义的“相近动作质量”范围。

### 4.2 RQ2-light：轻扰动子分支通过

冻结门槛：

1. `mean[Flip(Action)-Flip(Joint)] >= 0.01`；
2. 至少 4/5 seed 为正；
3. brightness/blur/noise 任一跨 seed 均值不得低于 −0.01。

观测结果：

- 五种子平均优势 = 0.016107；
- 4/5 seed 为正；
- brightness = 0.013562；
- blur = 0.009173；
- noise = 0.025587。

因此 RQ2-light 获得实践支持。其含义仅为 Joint 在冻结的三种轻扰动下平均
更少改变动作集合，不能解释为模型使用了正确因果证据。

### 4.3 RQ2-CEG：未回答

v4 独立 red/green-light mask 审计未通过冻结的总体/state-stratified
binding、contamination、artifact 门槛，并发现两个实际渲染 patch shape
不匹配。因此没有运行确认性 v4 CEG。v2/v3/v4 的任何探索性 CEG 均不得进入
主结果或作为 ARSC 有效性证据。

## 5. 四指标有效性与合理性

### A：动作指标

- perfect prediction=1；
- all-zero macro-F1=0；
- all-one macro-F1=0.4；
- seed42 冻结阈值网格 `{0.3,0.4,0.5,0.6,0.7}` 上，Joint−Action F1
  始终为正，没有方向反转；
- 五新种子把单 seed 差异升级为包含训练随机性的层级估计。

### R：理由指标

- 五种子 Rationale Macro-F1=0.273589，Micro-F1=0.503062；
- label permutation 将 seed42 Macro-F1 从 0.300991 降到 0.088577，
  说明指标能区分有信息预测与 prevalence/permutation 基线；
- 类别极不均衡：`car`、`person`、`left_lane`、`left_follow`、
  `no_left_lane`、`left_solid_line` 在五个 seed 均为 F1=0；因此不能只看
  micro-F1，也不能声称 21 类 ontology 被均匀学会；
- `rider`、`green_light`、`red_light` 等高支持类别明显较好，类别级结果
  已全部保存在 `rq1_multiseed_summary.json`。

### S：安全指标

- AURC 评估整个 risk-coverage 排序，五种子平均改善且 CI 刚好排除 0；
- UAR@90 是一个固定覆盖率切片，改善方向相同但 CI 跨 0；
- ECE 衡量 calibration，不等价于错误排序；两模型的平均 calibrated ECE
  基本相同；
- random/constant confidence reference、risk-coverage 端点和四种 confidence
  定义均已做 sanity/sensitivity；风险曲线存在 crossing，因此不能声称
  Joint 在所有 coverage 严格支配 Action-Only。

### C1：一致性指标

- identity transform 的 Action Flip=0、Rationale Jaccard=1；
- 100 张独立图像、300 个扰动 pair 的模型输出盲法语义审计全部判定语义
  不变，超过每扰动及总体 0.95 门槛；
- 变换在内存中执行，不发生 JPEG 重编码混杂；
- Rationale Jaccard 的空集—空集比例约 0.127–0.130；排除空并集后，
  brightness/blur/noise conditional Jaccard 仍分别为
  0.919816/0.887500/0.904568，说明高 Jaccard 不完全由空集记 1 造成；
- seed 与扰动分项效应异质，必须同时报告原始值、均值、SD 与层级 CI。

## 6. 负结果与科研停止规则

### Mask / CEG

- v2：critical binding 失败；
- v3：binding 与 contamination 失败；
- v4：独立 113-pair 总体/分层 gate 窄幅失败，且有两个实际 patch shape
  mismatch；
- BDD100K 官方 validation labels 只得到 53 个未见 state-matched 候选，低于
  v5 预注册 population gate。
- BDD100K-train v5 一次性元数据交集在 hash 前只得到 87 个 proposal：
  red 50、green 37、87 groups。冻结 analyzer 的 image root 少了一层
  `/data`，所以 hash independence 未有效完成，机器记录保持
  `STOP_CEG_INDEPENDENCE`；但 hash 只能删减、不能增加这 87 个候选，
  因此 total 87 < 200 且 green 37 < 50 已确定不可能通过 population gate。
  独立 reviewer 追加 `STOP_CEG_POPULATION_NO_V6`，禁止修 root 重跑、v6、
  mask 生成或读取这 87 个 proposal 的 logits。

这些结果不是“没有实验”，而是 measurement validity gate 正常阻止无效
CEG 进入论文结论。

### 外部数据

VLA4CoDrive 稀疏公开文件下载与 join 技术可行，但完整仓库索引只有：

- 9 个 canonical scenes；
- 最多 2,160 个 Action/Language paired windows；
- 540 个 weather path/filename 系统性 mismatch；
- 动作单位、理由 ontology、bbox relevance 尚未通过预注册审计。

独立 reviewer 正式裁决 STOP 外部训练；117 GB 全量下载不能补足 scene/window
硬门。PSI 仍需人工申请；BDD-X 与 BDD-OIA 同源且理由为自由文本，只能在新的
严格预注册后作为弱外部验证候选。

## 7. 工程修订与验证

首次五种子 tmux 运行在 seed43 评估前因 Windows worker 无法 pickle 局部
closure 而停止。失败时没有保存/查看 seed43 test cache 或指标。独立 reviewer
只批准：

- 把局部 closure 换成顶层 frozen dataclass callable；
- 参数、像素、噪声 seed、worker 数、数据顺序、分析口径全部不变；
- seed43 复用既有 checkpoint/calibration，只从 evaluation 重启。

修订通过逐像素等价、pickle roundtrip、真实 Windows
`num_workers=8`、32 样本 × 三扰动检查。成功日志保留为
`validity/tmux_rq1_multiseed_amendment01.log`，失败日志也原样保留。

最终工程验证：

- 实验环境 `pytest`: 29 passed；
- `compileall`: PASS；
- 原始 required outputs verifier: PASS；
- 环境、GPU、CUDA 与依赖版本：
  `outputs/environment_snapshot.json`。

## 8. 结论强度

可以声称：

1. 在固定 BDD-OIA、固定模型与五个新配对 seed 下，Joint 的平均动作 F1
   与 Action-Only 可比且更高；
2. ARSC 的 S 子指标没有给出同一个答案：AURC 改善，UAR/ECE 不确定；
3. R 指标揭示了整体可学习性和严重类别覆盖缺口；
4. 在通过语义审计的三种无损轻扰动下，Joint 的动作 flip 平均更低，并通过
   预注册 RQ2-light 门槛；
5. 四指标作为诊断分解比单独 Action F1 提供更多、非重复的信息。

不能声称：

1. 理由监督全面改善所有 ARSC 指标；
2. 高 Rationale Jaccard 等于理由正确或因果忠实；
3. C1 稳定性证明使用了正确视觉证据；
4. CEG 已被验证；
5. 结果已跨真实道路数据集外部验证；
6. 五个训练 seed 足以覆盖所有架构、超参数和数据分布不确定性。

全部主结果、原始 seed 值、审核与负结果索引见 `outputs/README.md`。

## 9. Round 5–6 独立审阅裁决

Round 5 独立审阅裁决为 **PASS with bounded claims**：

- Action equivalence：PASS；
- RQ2-light：SUPPORTED；
- RQ2-CEG：UNANSWERED；
- A/R/S/C1 已形成 BDD-OIA 内五种子重复性证据，但不形成因果、真实世界或跨数据集外部效度。

Round 5 只批准一个后续方向：把固定版本的 BDD100K train 官方
traffic-light state boxes 与冻结的 BDD-OIA evaluation manifest 做元数据交集，
尝试建立一次性、完全未见的 v5 候选池。第一阶段不得生成 mask、读取五种子
logits 或训练模型。

候选池必须同时满足：总数不少于 200、red 不少于 50、green 不少于 50、
独立 video/scene groups 不少于 30，并且与模型 train/validation、v2–v4
generation/audit、同 scene 近邻帧均零重叠。任一条件不足即正式停止 CEG
主线，不降低门槛、不改做 v6。只有元数据 gate 通过后，才允许执行冻结的
一次性生成、模型输出盲审和最终五种子确认性 CEG。完整门控见
`outputs/research_review_memo_round5_multiseed.md`。

Round 6 已执行该一次性交集。train-only transport 完整查询 2,233 个
keyframe ID，其中保留 original-train 1,744，排除 original-val 268，
API-no-row 221；前后镜像 revision 一致。冻结 gate 的 pre-hash proposal
上界为 87（red 50、green 37），已经不可能通过 200/50/50/30。虽然错误
image root 使 hash independence 未完成，但修复只能维持或删减 87，不能补足
total 与 green 缺口。因此：

- 机器裁决保持 `STOP_CEG_INDEPENDENCE`；
- 独立科学裁决为 `STOP_CEG_POPULATION_NO_V6`；
- CEG 主线正式关闭，RQ2-CEG 保持“未回答”；
- RQ2-light、A/R/S/C1 五种子内部结论不受该负结果推翻。

## 10. Round 7 冻结缓存轴选择性干预

Round 7 已按结果前协议和唯一 Amendment01 完成，不引入新数据、训练、mask
或重新推理：

1. A：破坏 action target row/class relation，perfect control 必须为 1，
   破坏后 Macro-F1 应下降；
2. R：破坏 rationale target row/ontology relation，perfect control 必须为 1，
   破坏后 Macro-F1 应下降；
3. S：固定 thresholded action predictions，只把 confidence ordering 改为
   oracle/original/random/adversarial；A 必须逐样本完全不变，AURC 应按方向响应；
4. C1：固定 clean/perturbed predictions，比 identity、正确 filename pairing
   与冻结错误 pairing；identity 必须 flip=0/Jaccard=1，错误 pairing应更不一致，
   clean A/R/S 必须完全不变。

结果前 exact audit 为 83/83 PASS，逐 seed 精确复现 Round 5。所有十个正式
方向对比均为 5/5 seeds 同方向，seed × shared-image crossed bootstrap 的
pointwise 95% CI 下界均大于 0：

| 对比 | 五-seed 均值 | 95% CI |
|---|---:|---:|
| A original−combined，Action-Only | 0.312962 | [0.299901, 0.326291] |
| A original−combined，Joint | 0.320033 | [0.305871, 0.335337] |
| R original−combined，Joint | 0.230389 | [0.213473, 0.247698] |
| S random−original AURC，Action-Only | 0.137671 | [0.119137, 0.156320] |
| S random−original AURC，Joint | 0.146539 | [0.128628, 0.165799] |
| C1 action wrong−correct，Action-Only | 0.669739 | [0.657245, 0.682235] |
| C1 action wrong−correct，Joint | 0.688713 | [0.675792, 0.700564] |
| C1 rationale correct−wrong，Joint | 0.782538 | [0.771974, 0.792558] |
| S adversarial−oracle AURC，Action-Only | 0.692018 | [0.690522, 0.692825] |
| S adversarial−oracle AURC，Joint | 0.692389 | [0.691325, 0.692871] |

独立 primitive-only verifier 对全部 raw seed 值、mean/SD 与 2,000 次
crossed-bootstrap CI 的最大绝对复现误差为 0。机器决策：

- `full_suite_measurement_pass = true`；
- `full_empirical_battery_pass = true`。

但独立科学总评保持 **PARTIAL**。A/R/C1 检验的是极端 association 或
sample correspondence 破坏，不是连续 severity；R 有 6 个类在 original
与 destroyed 下都保持 F1=0；S 的 original-vs-random 只相对于一份冻结
random reference，synthetic ECE 仅是数值诊断；C1 的巨大 wrong-pair 差异
不能解释为 brightness/blur/noise robustness。该实验不恢复 CEG，也不证明
construct validity、causal faithfulness、安全性或外部效度。

## 11. Round 8 唯一批准方向

下一轮仍不得换数据集或重训。只允许在同一 seeds 43–47 冻结 caches 上做
`q={0,0.25,0.50,0.75,1.00}` 的分级关联破坏响应曲线：

1. A/R：只对预冻结 q 比例样本做 prevalence-preserving row derangement；
2. S：只对 q 比例样本破坏 confidence-to-sample association，主分析只用
   AURC，不对 synthetic ECE 作方向解释；
3. C1：q 比例样本使用冻结 wrong pairing，其余保持 correct pairing；
4. bootstrap 每轮抽 training seeds，并只抽一份 shared clip multiset，
   入选 clip 的全部帧用于所有 seeds/conditions；
5. 每个轴只允许一个预注册单调趋势统计量和一个 gate，保留 R 全 21 类覆盖。

Round 8 通过后才允许把同一协议迁移第二数据集。完整结果边界、clip clustering
缺口与唯一下一步见 `outputs/research_review_memo_round7_final.md`。

## 12. Round 8 graded association-response result (authoritative update)

Round 8 completed the only experiment authorized by the Round 7 reviewer. It
used the frozen seed 43-47 BDD-OIA caches, one outcome-blind nested association
map, q levels `[0,.25,.50,.75,1]`, and 1,625 map-closed association components.
No data, training, inference, masks, model selection, threshold selection, or
post-result map selection was added.

The preregistered weakest-adjacent-step results were:

| Axis | Five-seed mean | SD | Association-component bootstrap 95% CI | Positive seeds |
|---|---:|---:|---:|---:|
| A | 0.068671 | 0.002259 | [0.059674, 0.072806] | 5/5 |
| R | 0.046416 | 0.003923 | [0.040571, 0.049523] | 5/5 |
| S | 0.026936 | 0.004363 | [0.018370, 0.030091] | 5/5 |
| C1 | 0.164889 | 0.002336 | [0.150002, 0.165152] | 5/5 |

All four formal gates passed and all five-seed mean component curves had no
adjacent reversal. The exact preflight passed 86/86 checks. A separate
implementation reproduced every point/detail/bottleneck and the full 2,000
replicate bootstrap. Its maximum point and bootstrap-summary absolute
differences were `1.8763e-14` and `2.4113e-15`; 7/7 independent audit checks
passed.

The final independent verdict is deliberately two-level:

- computational/formal: **PASS / VALID**;
- scientific/construct/external: **PARTIAL / BOUNDED INTERNAL EVIDENCE**.

The result supports internal graded responsiveness of A/R Macro-F1, S
tie-averaged AURC, and C1 mean-three correspondence metrics to the frozen
association destruction. It does not validate the complete rationale ontology,
rationale grounding or faithfulness, causal robustness, ECE/calibration,
real-driving safety, another architecture, or another dataset. Six rationale
classes (`car`, `person`, `left_lane`, `left_follow`, `no_left_lane`,
`left_solid_line`) have F1=0 at every q in every seed. C1 is a correspondence
metric, not a natural visual-severity or faithfulness metric.

The full evidence chain is in
`validity/round8_graded_response_artifact_index.json`; the final independent
review is `research_review_memo_round8_final.md`.

The only authorized next experiment is Round 9: 20 fixed outcome-blind
map/salt realizations (`map00`-`map19`, salts
`arsc-round9-map00`-`arsc-round9-map19`) on the same caches. Each axis must
have at least 18/20 positive map-specific bottlenecks, a positive grand mean,
a map x seed x component hierarchical bootstrap lower bound above zero, and
no grand-mean curve reversal. All maps must be reported; salts cannot be
replaced. VLA4CoDrive remains `STOP_EXTERNAL_TRAINING`.
# Addendum V0 (proposed): Rounds 9-13 evidence-level reconciliation

Date: 2026-08-09
Classification: DOCUMENTATION_ONLY; NOT_GO_RUN; NO_DATA_ACCESS;
                PROPOSED_AWAIT_INDEPENDENT_REVIEW

This addendum clarifies, for Rounds 9-13, the precise evidence weight of each
frozen protocol and its reviewer decision. It does not add or retract numeric
results. It forbids any claim of external validity, safety, rationale
grounding/faithfulness, or comprehensive four-axis validation.

See docs/design/rounds9_13_evidence_claim_reconciliation_addendum_v0_proposed.md
for the proposed, reviewable, non-authoritative evidence-claim matrix and its
cited tracked sources. The original tracked reviewer decisions and frozen
artifacts remain authoritative; this reference remains DOCUMENTATION_ONLY,
NOT_GO_RUN, and NO_DATA_ACCESS.
