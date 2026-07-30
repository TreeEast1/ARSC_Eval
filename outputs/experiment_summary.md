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

## 9. 独立审阅裁决与唯一下一步

Round 5 独立审阅裁决为 **PASS with bounded claims**：

- Action equivalence：PASS；
- RQ2-light：SUPPORTED；
- RQ2-CEG：UNANSWERED；
- A/R/S/C1 已形成 BDD-OIA 内五种子重复性证据，但不形成因果、真实世界或跨数据集外部效度。

审阅者只批准一个后续方向：把固定版本的 BDD100K train 官方
traffic-light state boxes 与冻结的 BDD-OIA evaluation manifest 做元数据交集，
尝试建立一次性、完全未见的 v5 候选池。第一阶段不得生成 mask、读取五种子
logits 或训练模型。

候选池必须同时满足：总数不少于 200、red 不少于 50、green 不少于 50、
独立 video/scene groups 不少于 30，并且与模型 train/validation、v2–v4
generation/audit、同 scene 近邻帧均零重叠。任一条件不足即正式停止 CEG
主线，不降低门槛、不改做 v6。只有元数据 gate 通过后，才允许执行冻结的
一次性生成、模型输出盲审和最终五种子确认性 CEG。完整门控见
`outputs/research_review_memo_round5_multiseed.md`。
