# ARSC 中文论文写作总交接文档

**文件角色：** 唯一论文作者交接包。阅读本文件后应能直接撰写中文会议论文，无需再翻仓库。  
**目标投稿：** 核电安全技术与装备全国重点实验室 2026 年度学术年会。  
**仓库：** `ARSC_space/BDD-OIA_space`（GitHub：`https://github.com/TreeEast1/ARSC_Eval.git`）。  
**整理日期：** 2026-08-29。  
**整理原则：** 只读取、核验、汇总已冻结实验结果；不训练、不加 seed、不改阈值、不设计 ARSC 总分、不启动 Round 14。  
**数字规则：** 正文表格默认保留 6 位小数（与 `outputs/paper/tables/` 一致）；需要核对全精度时以冻结 JSON 为准。禁止猜数字。若某量无法从现有 artifact 得到，明确写「当前无该结果」。

**本文件与仓库其它文档的关系：** `ARSC_FINAL_STATUS.md`、`docs/paper/ARSC_CLAIMS_AND_TERMINOLOGY.md`、`docs/paper/LIMITATIONS.md`、`docs/paper/NUCLEAR_TRANSFER_CONDITIONS.md` 以及 `outputs/paper/` 下的表/图是本交接的来源。论文作者以**本文件**为准；路径仅用于追溯。

---

# 0. 这篇论文到底在讲什么

面向安全关键人工智能决策，仅报告任务准确率不足以完整描述模型行为。本文构建一个多维、可审计的评价协议（ARSC），从决策任务性能、理由标签性能、选择性风险与校准、以及受控扰动下预测稳定性等不同侧面描述模型，并利用公开代理任务 BDD-OIA 验证这些评价维度能够提供非冗余信息。

**ARSC 是什么：** 面向决策模型的可审计多维评价协议。它不是 Safety Score，不是排行榜，也不是认证程序。四个评价轴不可通约，Round 10 还表明它们不对同一种扰动作出机械同步响应，因此禁止合成单一总分。

**ARSC 不是什么：**

- 不是训练一个更好的自动驾驶模型；
- 不是证明 rationale supervision 全面提升安全性；
- 不是已经验证核电 AI 安全。

**BDD-OIA 的角色：** proxy benchmark / 代理试场。只用于：

1. 验证协议能否计算；
2. 验证多维评价是否能改变单纯 Accuracy 导出的判断；
3. 验证不同评价轴是否具有非冗余响应。

**核电的角色：** 研究动机、目标应用域和未来迁移对象。当前工作没有核电数据、没有核电实验、没有核安全有效性结论。

**Punchline（中文候选）：**

> 任务准确率给出排序；多维评价给出行为剖面。

英文冻结表述：`Action Performance produces a ranking. ARSC produces a profile.`

**Action-Only vs Joint 的论文角色：** 受控评价案例（controlled evaluation case study），用来展示「当任务性能相近时，多维评价会改变判断」。它不是本文的核心方法贡献。

---

# 1. 两个主研究问题

## RQ1

**当两个模型的 Action Performance 相近时，多维评价是否能够揭示单一任务性能指标遗漏的信息，并改变模型判断？**

主证据：Round 5，Action-Only vs Joint，配对 seeds 43–47。

## RQ2

**在受控的 synthetic semantics-preserving pixel perturbations 下，不同评价轴是否呈现非冗余响应？**

主证据：Round 10。12 个 family × axis gate 最终只通过 **3 / 12**，并且**恰好全部是 C1 / Prediction Stability**。冻结形式裁决：`ROUND10_PARTIAL_OR_FAIL`。独立审阅接受为最终结局：`ACCEPT_ROUND10_PARTIAL_OR_FAIL_AS_VALID_FINAL_OUTCOME`。

不要把 3/12 直接解释为「ARSC 四轴效度失败」。科学解释应是：大量 sample-level action-set prediction 可以发生变化，而 aggregate Action Macro-F1、Rationale Macro-F1 和 Selective Risk 指标只发生很小变化，因此 Prediction Stability 捕获了 Action Performance 无法直接反映的信息，形成 axis separation / non-redundancy evidence。这**不**等于四个轴都完成 construct validation。

Round 12 是次级支持结果，不是主实验。

---

# 2. 实验设置（可直接写入论文「实验设置」）

## 2.1 数据集：BDD-OIA（公开代理任务，不是核电数据）

| 项目 | 冻结记录 | 来源 |
| --- | --- | --- |
| 数据名称 | BDD-OIA official last-frame release | `outputs/data_summary.json` |
| Google Drive file id | `1WFiwRi_sMA_McZnkbEjh8Rnl-Im7_9Mk` | 同上 |
| 归档大小 / SHA-256 | 778 443 955 bytes / `015c3b6494a5bd1d5b672b1d90cc4795da36647492836f0112a1578f5ff670fc` | 同上 |
| 输入 | 官方 last-frame JPEG；resize 到 224×224；ImageNet 均值/方差归一化 | `configs/experiment.yaml`；`src/arsc_eval/data.py` |
| Split | **严格使用官方 train / val / test**（`official_split_preserved: true`） | `outputs/data_summary.json` |
| 无效样本定义 | 缺失/损坏图像、畸形标签，或四个动作全空 | 同上 |
| 空 rationale | 若四动作有效则保留 | 同上 |
| 第五动作字段 | 仅记录、忽略；模型只预测 Forward/Stop/Left/Right | 同上 |

**过滤动作全空后的有效数量：**

| Split | 官方样本 | 有效样本 | 无效（四动作全空） |
| --- | ---: | ---: | ---: |
| train | 16082 | **16038** | 44 |
| val | 2270 | **2258** | 12 |
| test | 4572 | **4557** | 15 |
| 合计 | 22924 | 22853 | 71 |

**最终 test = 4557。** Round 10 source clips = **3904**（由文件名去掉末端 `_1` 或 `_3` 得到；`expected_source_clip_count: 3904`）。

**4 个动作名称：** `Forward`, `Stop`, `Left`, `Right`。

**Test 动作正例（官方 processed manifest）：** Forward 2484，Stop 2103，Left 1225，Right 1339。  
**Train 动作正例：** Forward 8770，Stop 7315，Left 4113，Right 4534。

**21 个 rationale label（仓库准确名称，顺序即 class index 0–20）：**

`green_light`, `follow`, `road_clear`, `red_light`, `traffic_sign`, `car`, `person`, `rider`, `other_obstacle`, `left_lane`, `left_green_light`, `left_follow`, `no_left_lane`, `left_obstacle`, `left_solid_line`, `right_lane`, `right_green_light`, `right_follow`, `no_right_lane`, `right_obstacle`, `right_solid_line`.

**Test support 有两套不要混用的计数：**

1. 官方 processed manifest：`outputs/data_summary.json` → `splits.test.rationale_positive_counts`。
2. 评价用 prediction-cache 标签：`outputs/paper/rationale_coverage.json`（Round 5 逐类 F1 表必须用这一套）。

二者在若干类别上相差 1–3（例如 `follow` 668 vs 667，`red_light` 1084 vs 1083，`car` 40 vs 39）。**论文逐类 F1 表一律用评价 cache。** 官方 manifest 只用于描述数据集规模。

冻结状态：dataset summary 已写入仓库；test manifest SHA-256 = `89364A265FE4C2EDCA5125D34C4C25D47C96AFB46A5C4A8FE86B649785539004`（Round 10 / v5 gate 交叉引用）。

## 2.2 模型

两模型均为 ImageNet pretrained ResNet-50（`torchvision.models.ResNet50_Weights.DEFAULT`），输入 224×224。

| | Action-Only | Joint Action-Rationale |
| --- | --- | --- |
| Backbone | ResNet-50，`fc` 替换为 Identity | 相同 |
| Action head | 4-dim linear | 4-dim linear |
| Rationale head | **无** | 21-dim linear |
| Loss | Action BCEWithLogits | Action BCE + Rationale BCE，权重 1:1 |
| 同 seed 配对 | 共享 backbone / action-head 初始化与 data order | 仅额外增加 rationale head/loss |

配对设计检查（seed 43 示例，五 seed 均 `gate_passed: true`）：

- `common_initialization_exact_match: true`
- Joint 独有参数仅 `rationale_head.weight` / `rationale_head.bias`
- `training_order_exact_match_after_global_rng_consumption: true`

来源：`outputs/validity/rq1_seed_{43–47}/paired_design_check.json`；协议：`outputs/validity/rq1_multiseed_frozen_protocol.json`。

**因此 Rationale Performance 不能作为 Action-Only vs Joint 的直接两模型比较指标。** Action-Only 没有 rationale head，R 是 Joint 的单模型轴。

## 2.3 训练、校准与推理协议

来源：`configs/rq1_seed43.yaml`–`rq1_seed47.yaml`、`configs/experiment.yaml`、`scripts/train_model.py`、`outputs/environment_snapshot.json`、`outputs/paper/s_confidence_audit.json`（温度）。

| 项目 | 冻结值 |
| --- | --- |
| Optimizer | AdamW |
| lr | 1e-4 |
| weight decay | 1e-4 |
| batch | 128 |
| AMP | true（fp16 autocast） |
| epochs | 5 |
| threshold | 0.5（action 与 rationale 均固定；test 不参与选择） |
| Checkpoint | 只按 validation **Action Macro-F1** 选择 `*_best_action.pt` |
| Temperature scaling | 标量，只拟合官方 validation 的 **四维 action logits**；test 不参与 |
| 主 seeds | 43–47 |
| Seed 42 | pilot / archived，排除出主分析 |
| 硬件 | NVIDIA GeForce RTX 5090（32607 MiB），driver 581.29 |
| Python | 3.11.13 |
| CUDA（PyTorch 报告） | 13.0 |
| torch / torchvision | `2.10.0.dev20251012+cu130` / `0.25.0.dev20251012+cu130` |
| 捕获时间 | 2026-07-31T02:52:20+08:00 |
| OS | Windows with WSL2 tmux orchestration |

**各 seed 冻结 temperature（validation 拟合，用于 test 校准）：**

| Seed | Action-Only | Joint |
| ---: | ---: | ---: |
| 43 | 2.586428 | 2.569311 |
| 44 | 2.906062 | 2.317606 |
| 45 | 2.879532 | 2.026177 |
| 46 | 2.506124 | 1.239887 |
| 47 | 2.912066 | 2.845759 |

Joint seed 46 的 temperature（1.24）明显低于其它 seed，这是已记录的校准异质性，不要事后重拟合。

Test 不参与：epoch 选择、threshold、temperature、seed 选择。

Round 5 C1 轻扰动参数（与 Round 10 **level 2** 对齐）：brightness factor 1.10，Gaussian blur radius 1.0，Gaussian noise std 5/255；in-memory，不 JPEG 重编码；noise seed 20260731。

## 2.4 统计

### Round 5 / RQ1

- 单 seed：2000 次 image-paired bootstrap（历史单 seed 分析仍存在于 `rq1_seed_*/rq1_metrics.json`）。
- 五 seed 主推断：**hierarchical paired bootstrap**，2000 replicates，RNG seed `20260731`，95% percentile CI。
- 层级：先有放回抽训练 seed，再在被抽中的 seed 内抽图像；模型与扰动配对保持。
- Practical-equivalence：Δ Action Macro-F1 = Joint − Action-Only 的 95% CI **完全位于 ±0.03**。冻结结果：CI [0.001590, 0.021807]，`passed = true`。
- Round 5 的「CI 不含 0」**未做**跨指标多重校正，应作描述性读取，不要写成 confirmatory familywise 检验。

来源：`outputs/validity/rq1_multiseed_summary.json`（SHA-256 `ECA8D453…5680000`）。审阅：`outputs/research_review_memo_round5_multiseed.md`（RQ1 等价 PASS；RQ2-light SUPPORTED；CEG unanswered）。

### Round 10 / Round 12

- 5000 replicates；先抽 5 个训练 seed 位置，再抽 3904 个 source clips，再展开为成员图像。
- Round 10：12 个 family×axis gate，Bonferroni 单侧 familywise α=0.05，每门 quantile = 0.05/12 = **0.004166666666666667**。
- Round 12：四轴 conjunction，Bonferroni `q=0.0125`（0.05/4）单侧下界。

---

# 3. 四个评价维度真正在算什么

论文统一采用下列操作化名称。禁止把旧工程名 Safety / Consistency 写进正文。

## A：Action Performance（动作性能）

**实际计算：** 4 个动作各自做 binary F1（threshold=0.5），再 Macro-F1。同时可报告 Micro-F1。

**可以表示：** 当前代理任务中的动作集合预测性能。

**不能解释成：** 真实驾驶能力；核安全水平；安全保证。

## R：Rationale-label Performance（理由标签性能）

**实际计算：** 21 个 rationale 标签的 Macro-F1、Micro-F1、per-class F1（threshold=0.5）。

**可以表示：** 理由标签恢复能力 / coverage。

**不能写：** reasoning faithfulness；模型真的基于这些理由决策；内部推理正确。

## S：Selective Risk and Calibration（选择性风险与校准）

三个量必须分开报告，禁止合成「Safety」：

| 量 | 含义 | 方向 |
| --- | --- | --- |
| AURC | 风险–覆盖曲线下面积（exact-set error） | 越低越好 |
| UAR@90 | 90% coverage 处的 unsafe acceptance rate | 越低越好 |
| ECE | 15-bin ECE，校准后概率 | 越低越好 |

**当前 error 定义：** 四位 action prediction 中任一 bit 错误，则整个 action set 记为 incorrect（exact-set error）。

**当前冻结 confidence（S0）：** `conf = max(action probability)`，即 `max_i p_i`。

S 不是 Safety。AURC / UAR / ECE 在当前实验中没有给出完全一致的 Joint vs Action-Only 排序，必须分开报告。

**Confidence sensitivity audit 已存在**（不是新实验，是对冻结 logits 的再统计）：`outputs/paper/s_confidence_audit.json`。三种定义：

| 代号 | 公式 | 角色 |
| --- | --- | --- |
| S0 | `max_i p_i` | 冻结主结果 |
| S1 | exact-set 概率代理 `∏_i q_i`，预测为正则 `q_i=p_i` 否则 `1-p_i` | 构念审计 |
| S2 | weakest-bit certainty `min_i max(p_i, 1-p_i)` | 构念审计 |

S0 复现 Round 5 发表值，18 项检查全部 `within_tolerance`（1e-9）。**S0 不被替换。**

## C：Prediction Stability under Synthetic Semantics-Preserving Pixel Perturbations（合成语义保持像素扰动下的预测稳定性）

代码与结果文件写为 **C1**。

**实际计算：** clean vs perturbed，thresholded action set 是否变化。核心指标：action-set flip rate。Joint 另有 rationale-set Jaccard（空–空定义为 1）。

**Perturbation：** brightness、Gaussian blur、Gaussian noise。必须写 **synthetic pixel perturbation**。

**不能写：** real-world sensor noise；real perturbation；overall robustness；evidence faithfulness；correct evidence usage。

CEG 不是第四或第五个已验证轴。它是失败的 evidence-sensitivity 扩展，只作为测量边界报告。

---

# 4. Round 5 主结果（RQ1）

**冻结 artifact：** `outputs/validity/rq1_multiseed_summary.json`  
SHA-256：`ECA8D453E9DB67CB933CAF2217DAFC62BD054709734C857AF8A5BE9665680000`  
**Paper 表：** `outputs/paper/tables/arsc_profile.md`  
**审阅：** `outputs/research_review_memo_round5_multiseed.md`（frozen / independently reviewed）

表中 *Joint advantage* 一律定向为「正 = Joint 更好」。AURC / UAR / ECE / flip rate 均为越低越好，因此 advantage 对差值做了相应取负。Difference 列对 A 使用 Joint−Action-Only；对 S/C1 使用「Joint 更好为正」。

## 4.1 可直接复制的主表

| Metric | Action-Only | Joint | Difference（Joint 更好为正） | 95% CI | Interpretation |
| --- | ---: | ---: | ---: | --- | --- |
| Action Macro-F1 | 0.674050 | 0.685586 | +0.011536 | [+0.001590, +0.021807] | 实践等价带内；Joint 均值略高；3/5 seed 同向 |
| Action Micro-F1 | 0.709682 | 0.718783 | n/a（无冻结配对区间） | Action-Only [0.704031, 0.715616]；Joint [0.713687, 0.724029] | 仅完整性报告 |
| Rationale Macro-F1 | n/a | 0.273589 | n/a | [0.256071, 0.292872] | Action-Only 无 R head |
| Rationale Micro-F1 | n/a | 0.503062 | n/a | [0.483546, 0.522462] | 高频类拉高 Micro |
| AURC | 0.388824 | 0.372227 | +0.016597 | [+0.000400, +0.033558] | Joint 小优势；4/5 seed 同向 |
| UAR@90 | 0.490931 | 0.479863 | +0.011068 | [−0.002000, +0.026036] | 不确定（CI 含 0）；3/5 seed 同向 |
| ECE-cal | 0.324007 | 0.324461 | −0.000454 | [−0.016291, +0.020440] | 本质持平；1/5 seed 利 Joint |
| C1 flip（三 family 均值） | 0.118543 | 0.102436 | +0.016107 | [+0.001009, +0.032814] | Joint 平均更稳；4/5 seed 同向 |
| C1 flip brightness | 0.101119 | 0.087558 | +0.013562 | [−0.003557, +0.031995] | 不确定 |
| C1 flip blur | 0.126882 | 0.117709 | +0.009173 | [−0.008428, +0.028224] | 不确定 |
| C1 flip noise | 0.127628 | 0.102041 | +0.025587 | [+0.011322, +0.039590] | 唯一 5/5 seed 同向的配对比较 |
| Joint rationale Jaccard（三扰动均值） | n/a | 0.916003 | n/a | [0.908090, 0.926552] | 轻扰动下 rationale 集合相对稳定；≠ faithfulness |

全精度要点：

- Action-Only Macro-F1 = `0.6740501115284726`
- Joint Macro-F1 = `0.6855859853354236`
- ΔA = `0.01153587380695098`
- AURC Δ（Joint−Action，越低越好故原始差分为负）= `−0.016596842367294407`；定向优势 `+0.016596842367294407`
- C1 advantage = `0.016107087996488918`
- Jaccard mean-three = `0.9160032184916976`

## 4.2 如何解释，不要写成模型比赛

### Action

两者落在预注册 ±0.03 practical-equivalence 范围内（`passed=true`）。Joint 均值略高约 1.15 个百分点，且 95% CI 不含 0，但 **不要把论文写成 SOTA 比赛**。等价与小幅正差异可以同时成立。Action 优势也不是 5/5 同向（seeds 46、47 反号）。

### S

AURC 有小优势。UAR@90 / ECE 没有稳定优势。所以不能说「Joint uncertainty / safety 全面更好」。未校准 ECE 曾对 Joint 有利（Δ = −0.038578，CI 不含 0），但校准后差异消失；正文以校准后 ECE 为准。

### C / RQ2-light

Joint 平均 flip rate 较低。原 RQ2-light gate（结果前冻结）：

1. mean advantage ≥ 0.01；
2. 至少 4/5 seed 为正；
3. 任一单扰动平均 advantage ≥ −0.01。

实际：mean = 0.016107；4/5 为正；brightness +0.013562，blur +0.009173，noise +0.025587。三项均满足，`supported=true`。

正文建议写成：当前 controlled case study 中观察到 Joint 平均预测稳定性更高。不要扩大成「rationale supervision universally improves robustness」。seed 43 反向；brightness/blur 的单扰动 CI 含 0。

---

# 5. Seed heterogeneity（必须单独成节，禁止藏反号）

**冻结：** `outputs/paper/seed_heterogeneity.json`（SHA-256 `831BF174…3EF21A`）  
表中 AURC/UAR/ECE 已定向为「正 = Joint 更好」（即对 Joint−Action 的越低越好指标取负）。C1 为 Action−Joint flip advantage。

| Seed | Δ Action F1 | Δ AURC（Joint更好为正） | Δ UAR@90 | Δ ECE | C1 advantage | Joint R Macro |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 43 | +0.020281 | +0.015472 | +0.015115 | −0.000296 | **−0.005047** | 0.284311 |
| 44 | +0.025495 | +0.008114 | **−0.000731** | −0.018920 | +0.003950 | 0.276922 |
| 45 | +0.015598 | **−0.006354** | +0.010239 | −0.013784 | +0.027503 | 0.256838 |
| 46 | **−0.001172** | +0.045048 | +0.036568 | **+0.038861** | +0.045132 | 0.245824 |
| 47 | **−0.002523** | +0.020704 | **−0.005851** | −0.008130 | +0.008997 | 0.304051 |
| Mean | +0.011536 | +0.016597 | +0.011068 | −0.000454 | +0.016107 | 0.273589 |

必须明确标记：

- **seed 43：C1 方向反转**（Round 5 与 Round 12 再次反转，Round 12 D_C1 = −0.001884）；
- **seed 45：AURC 方向反转**；
- **Action advantage 并非 5/5 同向**（46、47 反号）；
- UAR 在 44、47 反号；ECE 均值接近 0，seed 46 是唯一明显利 Joint 的 ECE seed。

**总结句：** training seed heterogeneity 是当前评价 profile 的真实组成部分，五 seed mean 不能替代 seed-level reporting。禁止为了叙事整齐隐藏反号。冻结结论：`no_comparison_is_unanimous = true`。

---

# 6. Rationale coverage（21 类）

**冻结：** `outputs/paper/rationale_coverage.json`（SHA-256 `3CC99E26…1C271A`）  
Support / F1 来自五 seed prediction cache，n=4557。Action-Only 无此表。

| Label | Test support | Seed43 F1 | Seed44 | Seed45 | Seed46 | Seed47 | Mean | All-zero? |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| green_light | 1574 | 0.646 | 0.670 | 0.655 | 0.633 | 0.606 | 0.642 | no |
| follow | 667 | 0.505 | 0.458 | 0.460 | 0.458 | 0.510 | 0.478 | no |
| road_clear | 941 | 0.394 | 0.441 | 0.402 | 0.295 | 0.410 | 0.388 | no |
| red_light | 1083 | 0.613 | 0.611 | 0.545 | 0.607 | 0.630 | 0.601 | no |
| traffic_sign | 302 | 0.481 | 0.452 | 0.401 | 0.434 | 0.426 | 0.439 | no |
| **car** | **39** | **0** | **0** | **0** | **0** | **0** | **0** | **yes** |
| **person** | **34** | **0** | **0** | **0** | **0** | **0** | **0** | **yes** |
| rider | 1037 | 0.747 | 0.751 | 0.705 | 0.714 | 0.754 | 0.734 | no |
| other_obstacle | 89 | 0 | 0 | 0 | 0 | 0.043 | 0.009 | no（4/5 为零） |
| **left_lane** | **29** | **0** | **0** | **0** | **0** | **0** | **0** | **yes** |
| left_green_light | 136 | 0 | 0 | 0 | 0 | 0.028 | 0.006 | no（4/5 为零） |
| **left_follow** | **68** | **0** | **0** | **0** | **0** | **0** | **0** | **yes** |
| **no_left_lane** | **23** | **0** | **0** | **0** | **0** | **0** | **0** | **yes** |
| left_obstacle | 175 | 0.023 | 0.033 | 0 | 0 | 0.137 | 0.038 | no |
| **left_solid_line** | **69** | **0** | **0** | **0** | **0** | **0** | **0** | **yes** |
| right_lane | 860 | 0.547 | 0.514 | 0.443 | 0.422 | 0.527 | 0.491 | no |
| right_green_light | 897 | 0.385 | 0.403 | 0.370 | 0.328 | 0.447 | 0.387 | no |
| right_follow | 713 | 0.423 | 0.398 | 0.374 | 0.277 | 0.482 | 0.391 | no |
| no_right_lane | 1182 | 0.617 | 0.567 | 0.489 | 0.599 | 0.589 | 0.572 | no |
| right_obstacle | 826 | 0.272 | 0.256 | 0.300 | 0.164 | 0.391 | 0.276 | no |
| right_solid_line | 403 | 0.318 | 0.261 | 0.250 | 0.231 | 0.404 | 0.293 | no |

长期 5 seed F1=0 且 **从未预测为正** 的六类：`car`, `person`, `left_lane`, `left_follow`, `no_left_lane`, `left_solid_line`。它们恰好是最稀有的六类（support 23–69）。覆盖空洞是「缺预测」而不是「大量错预测」。

解释要点：

- R Macro ≈ 0.27，R Micro ≈ 0.50，差距 +0.229；
- 高频类别（rider、green_light、red_light）拉高 Micro；
- 六类完全没有被恢复；
- 左右不对称：六个 left/right 对中，左侧支持更少、恢复更差（例如 `no_left_lane` 23 vs `no_right_lane` 1182，F1 0 vs 0.572）；
- 因此单一 Macro/Micro 都不足以描述 coverage。

**Round 7 之前的 metric-validity permutation（seed 42 pilot，不是主 seeds）：**  
`outputs/validity/metric_validity_frozen_grid.json` → `rationale_label_permutation`：observed Macro-F1 `0.300991` → permuted `0.088577`。  
只能说明：metric 对明显错误匹配有区分能力。不能说明所有类别已被学会，也不能说明 rationale 是 faithful explanation。

---

# 7. Round 10（RQ2；结果部分应给最大篇幅）

## 7.1 实验设计

| 项目 | 冻结值 |
| --- | --- |
| 图像 | 4557 official valid four-action test |
| source clips | 3904 |
| Families | brightness / blur / noise |
| Levels | 0（identity）+ 1,2,3,4 |
| brightness factor | 1.0, 1.05, 1.1, 1.2, **1.3** |
| blur radius | 0.0, 0.5, 1.0, 1.5, **2.0** |
| noise std（/255） | 0.0, 2.5, 5.0, 7.5, **10.0** |
| noise | filename-deterministic Gaussian，seed 20260731，同一标准正态场按 level 缩放 |
| Level 2 | 精确复现 RQ2-light：1.10 / 1.0 / 5 |
| 推理 | **真实重新推理**，不是缓存篡改；原 JPEG 打开一次，RGB 转换后内存扰动，再 224 resize + ImageNet norm；不保存/重载变换 JPEG |
| Calibration | 复用 clean-validation 温度，不在扰动图像上重拟合 |
| Checkpoints | 历史 `*_best_action.pt`，seeds 43–47 |
| Formal run | attempt02；attempt01 incident 保留且不得覆盖 |
| 生成时间 | 2026-07-31T10:12:59Z |
| 形式裁决 | `ROUND10_PARTIAL_OR_FAIL` |
| 独立审阅 | `ACCEPT_ROUND10_PARTIAL_OR_FAIL_AS_VALID_FINAL_OUTCOME` |

**Semantic blind audit：** 100 张图 × 12 个非零 family×level strata = 1200 pairs、2400 决策；模型输出盲。每层 `labels_still_applicable_rate=1.0`、`scene_semantics_preserved_rate=1.0`、`joint_pass_rate=1.0`。技术门：level 0 精确恒等；level 4 重复变换字节级一致；三 family 的 mean absolute RGB change 随 level 非降。`complete_grid_passed: true`。  
来源：`outputs/validity/round10_corruption_semantic_audit/audit_summary.json`。

**权威结果：** `outputs/validity/round10_corruption_formal_attempt02/round10_corruption_results.json`  
SHA-256：`9AE834DD81D4A397BA966917245AAA581007A0BFBF5B08CA773D7515756242C4`

## 7.2 预注册规则（3/12 怎么判）

协议：`outputs/validity/round10_corruption_dose_response_protocol.json`  
Amendment 01（结果盲，只改 practical endpoint 的统计层）：`round10_corruption_dose_response_protocol_amendment01.json`

**每个 family×axis 的五个 pass conditions（必须同时成立）：**

1. 至少 4/5 seed bottlenecks 严格为正；
2. 五 seed 未加权 mean bottleneck 严格为正；
3. Bonferroni 单侧 bootstrap 下界严格为正（quantile 0.004166666666666667）；
4. 该轴全部所需 grand-mean component curve 无相邻反转；
5. 该轴全部 practical endpoint 通过。

**Bottleneck 定义：** 在一个 family、一个轴、一个 seed 内，对所有所需 component 与四组相邻 severity 步，取期望方向上的最小相邻步。

**Practical endpoint thresholds（五 seed 未加权均值，≥，不四舍五入）：**

| 轴 | 阈值 | 效应定义 |
| --- | ---: | --- |
| A | 0.01 | 每个模型：level0 Macro-F1 − level4 Macro-F1 |
| R | 0.01 | Joint：level0 − level4 rationale Macro-F1 |
| S | 0.01 | 每个模型：level4 AURC − level0 AURC |
| C1 | 0.025 | 每个模型 level4 flip（level0 必须恰为 0）；以及 Joint rationale Jaccard 的 level0−level4（level0 必须恰为 1） |

**Round 10 整体：**

- Full construct pass：12 个门全过。
- 任一 family-axis 失败 → 报告 `ROUND10_PARTIAL_OR_FAIL`，列出每一门，禁止事后改阈值、丢 family、或只报告通过子集。

## 7.3 12 个 gate 的结果

最终只有 **3 个 PASS**，且全部 **C1 PASS**。

| Perturbation family | A | R | S | C1 |
| --- | --- | --- | --- | --- |
| brightness | FAIL | FAIL | FAIL | **PASS** |
| blur | FAIL | FAIL | FAIL | **PASS** |
| noise | FAIL | FAIL | FAIL | **PASS** |

更细的条件分解（`passed` 列是五条件合取）：

| Gate | 正 seed 数 | mean bottleneck | Bonferroni 下界 | 无反转 | endpoint | 门结果 |
| --- | ---: | ---: | ---: | --- | --- | --- |
| brightness·A | 0/5 | −0.002446 | −0.006327 | no | no | FAIL |
| brightness·R | 2/5 | −0.000367 | −0.002990 | no | no | FAIL |
| brightness·S | 0/5 | −0.003572 | −0.009939 | no | no | FAIL |
| brightness·C1 | 5/5 | +0.024167 | +0.017411 | yes | yes | PASS |
| blur·A | 0/5 | −0.001337 | −0.004892 | no | **yes** | FAIL |
| blur·R | 1/5 | −0.000504 | −0.002173 | no | no | FAIL |
| blur·S | 0/5 | −0.004632 | −0.013750 | no | no | FAIL |
| blur·C1 | 5/5 | +0.031688 | +0.024812 | yes | yes | PASS |
| noise·A | 0/5 | −0.002174 | −0.005194 | no | no | FAIL |
| noise·R | 2/5 | −0.000287 | −0.002238 | **yes** | no | FAIL |
| noise·S | 0/5 | −0.007420 | −0.013780 | no | no | FAIL |
| noise·C1 | 5/5 | +0.024354 | +0.017204 | yes | yes | PASS |

注意：blur 的 A **endpoint 达到了 0.01**（Action-Only 0.014165，Joint 0.012241），但仍因单调 dose-response / bottleneck 条件失败。论文应写「A 未满足冻结的严格单调剂量门」，不要写成「A 对扰动完全无响应」。

**Frozen verdict：** `ROUND10_PARTIAL_OR_FAIL`。保留原样。

## 7.4 Dose-response 关键数字（最高 severity = level 4）

来源：`outputs/paper/round10_axis_separation.json` 与 Round 10 `practical_endpoints`。

**Action-set flip @ max severity**

| Family | Action-Only | Joint |
| --- | ---: | ---: |
| brightness | 0.193241 | 0.170770 |
| blur | 0.265043 | 0.232390 |
| noise | 0.196884 | 0.160325 |

约 0.193 / 0.265 / 0.197 vs 0.171 / 0.232 / 0.160。

**Aggregate A/R/S 在同一 endpoint 的变化（正 = 按期望方向变差）**

| Family | A Action-Only | A Joint | R Joint | S Action-Only | S Joint |
| --- | ---: | ---: | ---: | ---: | ---: |
| brightness | +0.003186 | +0.001751 | +0.004391 | +0.005789 | +0.003624 |
| blur | +0.014165 | +0.012241 | +0.005900 | +0.005615 | +0.002127 |
| noise | +0.013365 | **−0.000646** | +0.004911 | **−0.006718** | **−0.006556** |

R endpoint 仅下降约 0.004–0.006，未达到预注册 0.01。S 在 noise 出现反向（AURC 下降 = 变好）。最大 C1 劣化 0.2650，最大 |A| 劣化 0.0142，比值约 **18.7×**。最大 |R| 劣化 0.0059。

**真实现象：** prediction-set flip 可达约 16%–27%，但 aggregate A/R/S 变化明显更小。C1 与 A 不是同一测量。

## 7.5 应如何解释

### Formal gate interpretation

3/12。Frozen formal verdict：`PARTIAL_OR_FAIL`。不能篡改，不能事后改阈值把 3/12 救成 PASS。

### Evaluation-paper interpretation

Round 10 对当前论文最重要的价值是：不同评价轴没有对相同 perturbation manipulation 产生机械同步响应。尤其：C1 可以明显恶化，而 aggregate Action Macro-F1 基本不变。因此 C 与 A 捕获不同的信息。这支持 axis separation / non-redundancy。

禁止写：四个 axis 都完成 construct validation。  
禁止写：synthetic perturbation 对应真实传感器异常。

---

# 8. Round 12（次级支持，不是主实验）

必须同时写两层，不能只写「Round 12 PASS」。

| 层 | 冻结值 |
| --- | --- |
| Formal gate verdict | `PASS` |
| Independent reviewer disposition | `ACCEPT_PASS_WITH_LIMITATIONS` |

**冻结：** `outputs/validity/round12_existing_outputs_results.json`  
SHA-256：`A4012EB3EC164674648E67507956B5870E7E321F8F844FF9709A3093BB33F00B`  
审阅：`outputs/validity/round12_existing_outputs_postresult_reviewer_decision.json`  
SHA-256：`43FE4528DD2BEDD6233D13F58EEA6947B6B746E8815F6A28CF9B6F67ADA7DFC3`

Round 12 **没有新推理**：在 Round 10 已有 dose grid 上做 Joint vs Action-Only 的 dose-aggregated interaction。CEG 状态在审阅中仍为 `UNANSWERED_CLOSED`。

| 量 | 点估计 | Bonferroni 单侧下界 q=0.0125 | 门含义 |
| --- | ---: | ---: | --- |
| D_C1 | +0.020017 | +0.001826 | 主效应：flip 优势点估计 ≥0.01 且下界 >0 |
| D_A | +0.003826 | +0.000220 | 仅 −0.01 非劣 |
| D_R | −0.001956 | −0.003641 | 仅 −0.01 非劣 |
| D_S | +0.000796 | −0.005292 | 仅 −0.01 非劣 |

三 family D_C1：brightness 0.016820，blur 0.016765，noise 0.026465。  
5 seed D_C1：4/5 为正；**seed 43 = −0.001884**。

A/R/S 只是满足 −0.01 non-inferiority guardrail，**不是 improvement**。Round 12 不是三轴全面改善。

审阅核心边界（必须引用）：

> not an every-seed or every-cell guarantee.

论文角色：secondary supporting result。不是主实验。禁止写成无条件 PASS。

---

# 9. CEG 失败链（closed and unanswered）

CEG 原意：检验模型对 critical evidence region 是否比 matched non-critical region 更敏感。预注册 mask audit gates：

- critical-binding correct rate ≥ 0.90
- control critical-evidence contamination rate ≤ 0.05
- semantic label unchanged rate ≥ 0.95  
并同时应用于 overall 与按灯态分层。

## v2

来源：`outputs/validity/mask_audit_v2/audit_summary.json`（SHA-256 `C6213463…A55CCA`）

- 审阅 108 pairs。
- **binding = 0.4167**（45/108 = 0.4166666666666667）→ FAIL（<0.90）。
- contamination = 0.0463 → PASS（≤0.05）。
- semantic = 1.0 → PASS。
- `overall_gate_passed: false`。
- 决策：FAIL for causal-faithfulness claims；仅保留为 detector-localised occlusion-sensitivity diagnostic。

## v3

来源：`outputs/validity/mask_audit_v3/audit_summary.json`（SHA-256 `32C56F2A…1B196A`）

- 审阅 102 pairs；排除先前 108 个文件名。
- **binding = 0.7451**（76/102 = 0.7450980392156863）→ 仍 FAIL。
- **contamination = 0.0980**（10/102 = 0.09803921568627451）→ FAIL（>0.05）。
- semantic = 1.0 → PASS。
- 对应失败：binding gate 与 contamination gate。

## v4（必须特别写：不是 population gate 失败）

来源：`outputs/validity/mask_audit_v4/audit_summary.json`（SHA-256 `908B15FF…2DB9FF`）；人口：`masks_v4_confirmatory_population.json`；不变量：`masks_v4_invariants.json`。

**Confirmatory population：113 filename-disjoint pairs**（red 46，green 67）。排除 v2/v3 开发审计中见过的 210 个文件名。这本身不是问题，也不是 population 失败。

v4 实际 audit（100% 审阅这 113 pairs，模型输出盲）：

| Gate | 数值 | 阈值 | 结果 |
| --- | ---: | ---: | --- |
| overall binding | 0.9381（106/113） | ≥0.90 | **PASS** |
| semantic | 1.0 | ≥0.95 | **PASS** |
| red-stratum binding | 0.8478（39/46） | ≥0.90 | **FAIL** |
| overall contamination | 0.0531（6/113） | ≤0.05 | **FAIL** |
| green contamination | 0.0597（4/67） | ≤0.05 | **FAIL** |
| red contamination | 0.0435（2/46） | ≤0.05 | PASS |

另有 **two one-pixel patch shape mismatches**（`all_invariants_passed: false`）：

- `b279bc06-3c8aeb90_1.jpg`：critical 94×30 vs noncritical 94×31
- `661a6487-c5df650e_3.jpg`：critical 79×32 vs noncritical 79×33

记录决策：`Do not run confirmatory CEG with v4`。没有计算 confirmatory CEG 指标。

因此：**mask v4 failed the audit gates。不要写 failed population/state gate。**

## Population insufficiency 是后面的事情

**BDD100K official validation：** `outputs/validity/bdd100k_validation_label_overlap.json`  
未见过、state-matched candidates = **53**（red 34，green 19）。门槛：total ≥100 且每态 ≥30。green 19 < 30，**failed population gate**。这是 validation 交集，不是 v4。

**BDD100K-train v5 metadata intersection：** `outputs/validity/bdd100k_train_v5_metadata_gate.json`  
SHA-256：`33DE06F0…FD15943B`

Pre-hash proposed：**87** candidates（red **50**，green **37**，87 clip groups）。  
冻结 population requirement（`bdd100k_train_v5_metadata_protocol.json`）：total ≥200，red ≥50，green ≥50，independent clip groups ≥30。green 37 < 50 且 total 87 < 200，上界不可能过门。

机器运行因错误图像根（`data/raw/lastframe` 而非 `data/raw/lastframe/data`）给出 `STOP_CEG_INDEPENDENCE`（`missing_required_image_file_count=19961`），hash independence **未评估成功**。修 root 不能把 87 增加到 200。独立审阅因此追加：

**`STOP_CEG_POPULATION_NO_V6`**

未生成 v5/v6 mask，未读取提案 logits。CEG 状态：**closed and unanswered**。

绝对不能写：CEG validated；model failed CEG；evidence reliance failed；evidence faithfulness 已验证。

**方法学意义：** 对安全关键评价而言，评价干预本身也必须先接受审计。当 intervention 无法满足 binding、contamination、semantic 或 population 要求时，合理结果是「不回答该问题」，而不是降低门槛强行计算指标。

---

# 10. Round 7–9 及其它负结果（只简要，勿抢正文）

## Round 7

极端 sanity control，不是 construct validity。在冻结 prediction cache 上做 permutation / ordering / pairing 等 10 个 directional controls。正式 10 门 5/5 seed 为正；独立复算 reproduction error = 0。科学审阅：**PARTIAL**（执行 PASS，但不能升级为四轴一般效度证明）。  
来源：`outputs/research_review_memo_round7_final.md`；`outputs/validity/arsc_axis_falsification_results.json`。

## Round 8–9

- Round 8：graded q，单一 map/salt；四轴方向门通过；科学层 PARTIAL。
- Round 9：20 maps；形式 `ROUND9_FULL_PASS`（四轴 20/20 map 为正）。**20 maps ≠ 20 datasets**——同一 4557 图、同一五 seed，只换 association realization。
- 六类 rationale 仍长期 F1=0。
- 该 salt/map 线永久关闭，不再增加 map/q。

## VLA4CoDrive

Round 4 独立审阅：**STOP VLA4CoDrive training** / `STOP_EXTERNAL_TRAINING`。公开仓库实际只有 9 个 canonical scene、最多 2160 个 Action/Language pairing windows，低于预注册 5000 windows / 150 scenes。10-window probe 只证明读取链路可工作。不要当外部验证。  
来源：`outputs/research_review_memo_round4_vla_feasibility.md`；`outputs/validity/vla4codrive_probe_feasibility.json`。

## DAAD-X

18 585 647 156 bytes ≈ **18.6 GB**；**70/70** chunks；assembled archive SHA-256 `98E6DD4D068004B090A5D62C648A727AF902EBF3B176BCE2CE044EABDE91E965`。`transport_only: true`。审阅明确禁止读取 labels/video、训练、推理。所以：**无 scientific result**，不是 external validation。  
来源：`outputs/validity/round11_daadx_transport_receipt.json`。

## Round 13

protocol / ABI / synthetic MTMM / Win32 containment 工程。无 scientific result memo。不能作为 scientific evidence。

---

# 11. Decision Change Table（如果只看 Accuracy，结论怎么变）

可直接改写入正文。来源：`outputs/paper/tables/decision_change.md`。

| Evaluation view | Evidence | Naive conclusion | ARSC interpretation |
| --- | --- | --- | --- |
| 只看 A | Action-Only 0.674050 vs Joint 0.685586；Δ=+0.011536，CI 在 ±0.03 内 | 两模型表现相近，Joint 略高；不必再评 | 正因为 A 实践等价，A 无法裁决模型；差异必须到其它轴找。且 A 优势仅 3/5 seed |
| 加入 R | Joint Macro 0.273589，Micro 0.503062；六类五 seed F1=0 | Joint 有理由输出，所以更「可解释」 | 有输出但 coverage 明显不完整；R ≠ faithfulness |
| 加入 S | AURC 略好；UAR/ECE 无统一方向 | Joint uncertainty 更好 | 不能给出「整体 uncertainty 更好」的单一结论 |
| 加入 C | Joint 平均 flip 更低；seed 43 反向；Round 12 同向但非每 seed | Joint 更稳健，可部署 | 平均稳定性存在差异，但不是每个训练 seed 都成立；C1 ≠ 真实鲁棒 / evidence |
| Round 10 | 大量 sample flips，A Macro-F1 几乎不动；3/12 全是 C1 | 四轴验证失败，额外轴没价值 | Aggregate task performance 无法替代 prediction stability；这是非冗余证据 |
| S 构念审计 | S0 ECE≈0.324 vs S1 ECE≈0.099；UAR 裁决随定义改变 | 应改用「更好看」的 S1 | S0 仍是冻结主结果；S 必须按指标和 confidence 定义分报 |

**最终 punchline：** Accuracy produces a ranking; multidimensional evaluation produces a behavioral profile.  
中文：任务准确率给出排序；多维评价给出行为剖面。

---

# 12. 核电迁移逻辑（条件陈述，不是结果）

> BDD-OIA 验证的是评价协议的可计算性、诊断价值和不同评价维度的非冗余性，而不是核电安全有效性。

| 当前 BDD-OIA 评价维度 | 当前操作化 | 核电对应对象 | 真正迁移前必须解决的问题 |
| --- | --- | --- | --- |
| A Action Performance | 4-action Macro-F1 @0.5 | 异常检测、故障识别、事故诊断、操作建议、状态分类等离散决策 | 重新定义核任务标签集、多标签/单标签结构、类别平衡、阈值与实践等价带宽。当前未验证任何核任务 |
| R Rationale-label Performance | 21 个驾驶 rationale labels | 关键测点、工艺参数、时间趋势、EOP 条目、诊断依据、操作逻辑 | **必须重建 ontology**。当前不存在完整核领域对应 ontology。R 仍只测量标签恢复，不是 faithfulness |
| S Selective Risk & Calibration | exact-set error + max(p)；AURC/UAR@90/ECE | 弃权 / 移交操纵员 | 必须重定义 correctness（宜为 episode 而非单帧）、confidence、coverage 工作点、代价不对称。UAR@90 无核安全含义 |
| C Prediction Stability | brightness / blur / Gaussian noise | 测量噪声、传感器漂移、通道缺失/dropout、时滞、标定误差、量化 | **不能直接照搬**像素扰动。必须依据真实 measurement / instrumentation assumptions。当前工作没有验证这些扰动 |
| CEG / Evidence intervention | 交通灯等检测框遮挡 | 关键测点干预 | 关键测点定义、干预语义合理性、binding、contamination、population、领域专家审计。当前 CEG unanswered |

跨轴还需要：seed/run 分布报告、领域论证的预注册阈值、监管语境下 ARSC 不是 V&V / 安全论证、以及人–机系统而不是单独模型。

---

# 13. Limitations（正文必须覆盖）

1. BDD-OIA 是 proxy domain。  
2. 没有真实核电实验。  
3. 单一 ResNet-50 backbone。  
4. Rationale-label Performance ≠ reasoning faithfulness。  
5. 21 rationale 类别存在 coverage holes（六类五 seed F1=0）。  
6. S 依赖 confidence operationalization（exact-set error vs max(p) 不匹配）。  
7. AURC/UAR/ECE 不提供统一结论。  
8. C1 仅为 synthetic pixel perturbation stability。  
9. C1 ≠ evidence reliance。  
10. seed heterogeneity 明显；五 seed 不足以刻画分布。  
11. CEG unanswered。  
12. 无真正跨数据集 external validation。  
13. DAAD-X 没有产生科学结果。  
14. ARSC 当前不应该合成为单一 Safety Score。  
15. BDD-OIA 中的 perturbation 不应直接类比核电传感器扰动。  
16. Round 5 多指标 CI 未做多重校正。  
17. Round 12 不是 every-seed / every-cell / 三轴改善。  
18. Round 10 的 3/12 不是四轴构念全部成立。

---

# 14. 推荐的中文论文结构

面向「核电安全技术与装备全国重点实验室 2026 年度学术年会」的篇幅：方法与迁移讨论应清楚，实验以 RQ1+RQ2 为主，负结果放附录或局限性。

## 0 引言

- 安全关键 AI 不能只报告 Accuracy；
- 核电运行辅助、大模型辅助决策、自主控制等需求；
- 当前缺乏多维、可审计评价；
- 核领域公开结构化数据不足；
- 使用 BDD-OIA proxy 验证协议可计算性与诊断价值；
- 贡献点建议三条：  
  1. 提出并操作化 A/R/S/C 四轴可审计评价协议（不做总分）；  
  2. 在动作性能相近的受控案例中展示多维剖面如何改变判断；  
  3. 用合成语义保持扰动证明轴间非冗余，并如实报告 CEG 停止。

## 1 面向安全关键人工智能决策的多维评价协议

1.1 评价目标  
1.2 Action Performance  
1.3 Rationale-label Performance  
1.4 Selective Risk and Calibration  
1.5 Prediction Stability  
1.6 审计与停止机制（含 CEG 作为「不回答」先例）

## 2 实验设计

2.1 BDD-OIA 代理任务  
2.2 Action-Only 与 Joint 模型（案例，非方法主体）  
2.3 训练与统计  
2.4 synthetic perturbation protocol

## 3 结果与分析

3.1 动作性能相近模型的多维 profile（Round 5）  
3.2 受控扰动下评价轴的非冗余响应（Round 10）  
3.3 理由类别覆盖与 seed heterogeneity  
3.4 CEG 的测量边界和停止决策  
Round 12 可作为 3.2 的辅助一句，不要单列成「主实验 3」。

## 4 面向核电智能决策的迁移讨论

明确哪些可以迁（报告纪律、弃权机制的形式），哪些必须重新定义（ontology、扰动物理、正确性事件）。

## 5 局限性

## 6 结论

回到：协议可计算、剖面改变判断、C 与 A 非冗余、核电尚未验证。

---

# 15. 建议主图和主表

现在不要生成新图；仓库已有 `outputs/paper/figures/`。

## Figure 1 — 协议概念图（需新绘）

画这些模块与箭头：

- 输入：决策模型 + 任务样本（此处为 BDD-OIA last-frame）；
- 四个并行评价轴 A/R/S/C，各标注操作化指标与「不测量什么」；
- 审计/停止闸门（binding / contamination / population → 不回答）；
- 输出：behavioral profile（四个数并列表），明确 **没有** 合成 Safety Score；
- 侧注：核电 = 动机与未来迁移，不是当前数据。

## Table 1 — 四轴定义

component / operational metric / interpretation / limitation。直接用本文件第 3 节。

## Table 2 — Round 5 主表

本文件第 4.1 节。

## Figure 2 — Round 10 dose-response / axis separation（已有）

路径：`outputs/paper/figures/round10_axis_separation.png`（及 `.svg`）。  
**x：** perturbation severity（0–4）。  
**y：** A/R/S/C 各自变化（正 = 变差）。  
重点不是曲线都变化，而是 **C 明显变化但 A/R/S 不同步**（noise 上 S 甚至反向）。

## Figure 3 — 主文用 seed heterogeneity

**推荐主文：seed heterogeneity**（`outputs/paper/figures/seed_heterogeneity.png`）。  
理由：没有任何 headline 比较在 5 seed 上同号；若只放均值，读者会读成「Joint 全面更好」。这与 RQ1「剖面而非排序」直接相关。

**建议附录：** rationale per-class coverage 图（`outputs/paper/figures/rationale_coverage.png`）+ 本文件第 6 节全表。正文用一小段或一个「六类为零」摘录即可。

## Table 3 — Decision Change Table

本文件第 11 节。

---

# 16. 参考文献需求

本交接**不编造 citation**。仓库内没有 `.bib`。下列「已核验」仅表示仓库文档里已有官方 URL；作者投稿前仍应打开核对题录。其余一律 `NEEDS_EXTERNAL_VERIFICATION`。

## 16.1 论文至少需要的文献类别

- BDD-OIA original paper  
- ResNet  
- temperature scaling  
- selective prediction / risk-coverage  
- calibration / ECE  
- explainable / rationale-based decision models  
- safety-critical AI evaluation  
- nuclear AI / nuclear fault diagnosis / nuclear operation support  
- NPPAD 或类似公开核数据  
- AI safety / trustworthy AI 在核能场景中的研究  

## 16.2 仓库已有真实文献入口（推荐位置）

| 工作 | 仓库中的出处 | 作者/venue/year/DOI | 建议位置 |
| --- | --- | --- | --- |
| DAAD-X | `outputs/dataset_scout_round11_external_validity.md` | ICCV 2025 论文 PDF：https://openaccess.thecvf.com/content/ICCV2025/papers/Karuppasamy_Towards_Safer_and_Understandable_Driver_Intention_Prediction_ICCV_2025_paper.pdf ；项目页 https://mukil07.github.io/VCBM.github.io/ | 相关工作 / 为何未做外部验证。**不能当本文实验文献。** |
| VLA4CoDrive | `outputs/dataset_scout_round1.md` | WACV 2026 workshop HTML：https://openaccess.thecvf.com/content/WACV2026W/LLVM-AD/html/Boroujeni_VLA4CoDrive_Vision-Language-Action_Dataset_for_Cooperative_Autonomous_Driving_WACVW_2026_paper.html ；GitHub https://github.com/SayedPedramHaeri/VLA4CoDrive | 相关工作 / STOP 外部训练。**不能当外部验证。** |
| BDD-X | 同上 Round 11 scout | GitHub https://github.com/JinkyuKimUCB/BDD-X-dataset ；标注为 ECCV 2018 传统来源但 **年份/题录未在本仓库逐字段核验** | 相关工作。标记 `NEEDS_EXTERNAL_VERIFICATION`（完整题录） |
| PSI | 同上 | NeurIPS 2025 abstract：https://papers.neurips.cc/paper_files/paper/2025/hash/436fb0fa57c75e0d2063b5bc19a21da1-Abstract-Datasets_and_Benchmarks_Track.html | 相关工作。访问门失败，无实验 |

## 16.3 当前无仓库内核验题录（全部 `NEEDS_EXTERNAL_VERIFICATION`）

- BDD-OIA 原始论文（作者、venue、年、DOI）  
- He et al., ResNet  
- Guo et al., On Calibration of Modern Neural Networks / temperature scaling  
- Geifman & El-Yaniv 或同等 selective risk / AURC  
- ECE 原始定义文献  
- NPPAD 及核电故障诊断公开数据  
- 核电运行支持 / 核安全 AI 评价文献  

严禁把未核验条目写成已核验。

---

# 17. 术语中文翻译

| English | 推荐译法 | 备选 / 不要用 |
| --- | --- | --- |
| Action Performance | 动作性能 | 不要译成「驾驶能力」「安全性」 |
| Rationale-label Performance | 理由标签性能 | 备选「理由标签恢复性能」。不要「推理忠实性」 |
| Selective Risk | 选择性风险 | 不要「安全风险」 |
| Calibration | 校准 | — |
| Prediction Stability | 预测稳定性 | 不要「鲁棒性」「证据忠实性」 |
| Semantics-preserving perturbation | 语义保持扰动 | 强调正确答案不变 |
| Synthetic pixel perturbation | 合成像素扰动 | 不要「真实扰动」「传感器噪声」 |
| Action-set flip rate | 动作集合翻转率 | 备选「动作集翻转率」 |
| Practical equivalence | 实践等价 | 不是「完全相同」 |
| Hierarchical paired bootstrap | 分层配对自助法 | 先抽训练 seed，再抽图像/clip |
| Coverage | 覆盖率 | R 中指类别恢复覆盖；S 中指选择性预测覆盖，二者不要混用 |
| Binding | 绑定（干预是否落在声明的关键证据上） | 不要望文生义成「约束优化」 |
| Contamination | 污染（对照区是否碰到关键证据） | — |
| Evidence intervention | 证据干预 | CEG 语境 |
| Proxy benchmark | 代理基准 / 代理试场 | 不要「核电基准」 |
| Non-redundancy | 非冗余 | — |
| Axis separation | 评价轴分离 | 与 non-redundancy 近义，Round 10 主解释 |
| Behavioral / evaluation profile | 行为剖面 / 评价剖面 | 对应「不是单一分数」 |
| Exact-set error | 精确集合错误 | 四位动作任一错误即错 |
| Abstention | 弃权 | 核电语境可作「移交操纵员」 |

旧名 **Safety**（指 S 轴）、**Consistency**（指 C1）已废止，正文不要用。

---

# 18. 论文可以写什么 / 不能写什么

## Allowed claims

- Action-Only 与 Joint 在冻结 practical-equivalence（±0.03）范围内具有相近 Action Performance；Joint 均值略高但不是模型竞赛结论。  
- 多维评价揭示了 Accuracy 遗漏的信息，并把「排序」变成「剖面」。  
- Rationale Performance 存在明显类别 coverage holes（六类五 seed F1=0）。  
- Selective-risk 子指标没有统一给出同一结论；仅 AURC 在 S0 下对 Joint 有小优势。  
- Joint 在当前案例上具有平均 C1 advantage，但不是 every-seed guarantee（seed 43 反向）。  
- Round 10 提供了 axis non-redundancy evidence；形式裁决仍是 `ROUND10_PARTIAL_OR_FAIL`（3/12，全为 C1）。  
- CEG unanswered；评价干预本身未过审计时应当停止而非降门槛。  
- BDD-OIA 仅为 proxy validation。  
- ARSC 适合报告 behavioral/evaluation profile，而不是单一 Safety Score。  
- Round 12 可写为次级、带 limitations 的 C1 剂量汇总支持，A/R/S 仅为非劣。  

## Forbidden claims

- Joint 全面更安全。  
- Joint 全面改善 A/R/S/C。  
- rationale supervision universally improves robustness。  
- Rationale F1 = explanation faithfulness。  
- C1 = evidence faithfulness / evidence reliance。  
- C1 = real-world robustness。  
- synthetic noise = nuclear sensor noise。  
- CEG validated。  
- CEG proved model did not use evidence。  
- BDD-OIA validated nuclear safety。  
- DAAD-X external validation。  
- 20 maps = 20 datasets。  
- Round 13 有 scientific result。  
- Round 12 是三轴 improvement 或无条件 PASS。  
- 四轴都完成 construct validation。  
- 把 AURC/UAR/ECE 合称为 Safety。  

---

# 19. Key Numbers Cheat Sheet

路径相对于仓库根 `BDD-OIA_space/`。冻结状态见各 SHA-256。

### Dataset

| 量 | 值 | Source |
| --- | --- | --- |
| train / val / test 官方 | 16082 / 2270 / 4572 | `outputs/data_summary.json` |
| 有效 | 16038 / 2258 / **4557** | 同上 |
| source clips | **3904** | Round 10 `data.source_clip_count` |
| 动作 | Forward, Stop, Left, Right | 同上 |
| rationale 类数 | 21 | 同上 |

### Round 5（seeds 43–47，2000 hierarchical bootstrap）

| 量 | Action-Only | Joint | Δ 或备注 |
| --- | ---: | ---: | --- |
| A Macro-F1 | 0.674050 | 0.685586 | +0.011536；CI [0.001590, 0.021807]；等价 PASS |
| Joint R Macro / Micro | — | 0.273589 / 0.503062 | Macro CI [0.256071, 0.292872] |
| AURC | 0.388824 | 0.372227 | 定向优势 +0.016597；CI [0.000400, 0.033558] |
| UAR@90 | 0.490931 | 0.479863 | 定向 +0.011068；CI 含 0 |
| ECE-cal | 0.324007 | 0.324461 | 定向 −0.000454；CI 含 0 |
| C1 mean-three flip | 0.118543 | 0.102436 | advantage +0.016107；CI [0.001009, 0.032814] |
| Joint Jaccard mean-three | — | 0.916003 | CI [0.908090, 0.926552] |

Source：`outputs/validity/rq1_multiseed_summary.json`。Reviewer：Round 5 memo。

### Seed heterogeneity（反号）

- A 反号：46、47  
- AURC 反号：45  
- C1 反号：43  
- UAR 反号：44、47  

### Round 10

- 3/12；三个 C1 PASS（brightness/blur/noise）  
- 形式 `ROUND10_PARTIAL_OR_FAIL`  
- practical thresholds：A/R/S ≥0.01，C1 ≥0.025  
- 最高 severity flip：AO 0.193 / 0.265 / 0.197；Joint 0.171 / 0.232 / 0.160  
- 最大 |A| 变化 0.0142；最大 |R| 0.0059；S noise 反向  

### Round 12

- D_C1 = +0.020017；lower bound +0.001826  
- 4/5 seeds；seed 43 = −0.001884  
- 形式 PASS + 审阅 `ACCEPT_PASS_WITH_LIMITATIONS`  

### CEG

| 量 | 值 |
| --- | --- |
| v2 binding | 0.4167 |
| v3 binding / contamination | 0.7451 / 0.0980 |
| v4 pairs | 113（red 46 / green 67） |
| v4 overall binding | 0.9381 PASS |
| v4 red binding | 0.8478 FAIL |
| v4 overall / green contamination | 0.0531 / 0.0597 FAIL |
| BDD100K val unseen | 53（34/19） |
| train v5 proposed | 87（50/37） |
| 科学停止 | `STOP_CEG_POPULATION_NO_V6` |

### S 审计（S0 为主）

- exact-set error：AO 0.5220，Joint 0.5104 → accuracy ≈0.48  
- mean S0 confidence：AO 0.8020  
- S0 ECE AO 0.3240 vs S1 ECE AO 0.0987  
- AURC 方向跨 S0/S1/S2 稳定；UAR@90 不稳定  

### 环境

RTX 5090；Python 3.11.13；CUDA 13.0；torch `2.10.0.dev20251012+cu130`。

---

# 20. 冻结 provenance 速查

| Artifact | SHA-256 | 角色 |
| --- | --- | --- |
| `outputs/validity/rq1_multiseed_summary.json` | `ECA8D453E9DB67CB933CAF2217DAFC62BD054709734C857AF8A5BE9665680000` | Round 5 |
| `outputs/validity/rq1_multiseed_frozen_protocol.json` | `CC5FE969EA90EFB1181F67AB5D18CE67C05DE9207F903C7F14EBD964AC07EE0C` | Round 5 预注册 |
| `outputs/validity/round10_corruption_formal_attempt02/round10_corruption_results.json` | `9AE834DD81D4A397BA966917245AAA581007A0BFBF5B08CA773D7515756242C4` | Round 10 |
| `outputs/validity/round10_corruption_dose_response_protocol.json` | `E3F54B24A50D847636FA644355BF78DB1AB2432CF74543E8AEF11A005D17029D` | Round 10 门规则 |
| `outputs/validity/round12_existing_outputs_results.json` | `A4012EB3EC164674648E67507956B5870E7E321F8F844FF9709A3093BB33F00B` | Round 12 形式结果 |
| `outputs/validity/round12_existing_outputs_postresult_reviewer_decision.json` | `43FE4528DD2BEDD6233D13F58EEA6947B6B746E8815F6A28CF9B6F67ADA7DFC3` | Round 12 审阅 |
| `outputs/paper/s_confidence_audit.json` | `4C430D73C8427D72DDB6A8D5C0A9A05D822635E803F47A5B6EDABD3EBB3D9778` | S 审计 |
| `outputs/paper/rationale_coverage.json` | `3CC99E26152ABDD3A05AEABB5EB5F2DEF67A63A74BDD501FB5BE21D38A1C271A` | 21 类 F1 |
| `outputs/paper/round10_axis_separation.json` | `EA66D71776E256326896A44B9A5D0BAB91BEE42C69E359ADB227E6EC5E21BC71` | Round 10 论文视图 |
| `outputs/paper/arsc_profile.json` | `96EBFE68BD912C8B170940CCE6C6AFAAF34D8CDFDBE6ABC9472CC4A07BB4FEBE` | RQ1 profile |
| `outputs/paper/seed_heterogeneity.json` | `831BF174BA1203BABA353A08F2A8DB19EF74A22BBEC0B418D0304C61F03EF21A` | seed 表 |
| `outputs/validity/mask_audit_v2/audit_summary.json` | `C62134637AEB38AC034E1EA61E4095A1AB4426F1D912C2E2A9904D6414A55CCA` | CEG v2 |
| `outputs/validity/mask_audit_v3/audit_summary.json` | `32C56F2AF8503BBA2027AAC0245C66C976110917B271655479282F4BCC1B196A` | CEG v3 |
| `outputs/validity/mask_audit_v4/audit_summary.json` | `908B15FF25BE9B2A0F21B18B8E442F8B903DA8AFF68A9A9583391364372DB9FF` | CEG v4 |
| `outputs/validity/bdd100k_train_v5_metadata_gate.json` | `33DE06F02F5ED44C3BC8B371D5F02D625FA60B1A983339831DBF55C7FD15943B` | CEG v5 停止 |
| `outputs/validity/round11_daadx_transport_receipt.json` | `D738E21E5DC1976C192CFA3982E2CA2941FF3D2AF8A811BA432D51778A6B1C7F` | DAAD-X 仅运输 |
| `outputs/data_summary.json` | `52FF75ED5BB5FA1E65EA6565C05992CB3D66A08BCBE319974ACAB5D36CF61898` | 数据集计数 |
| `outputs/environment_snapshot.json` | `9404CADB8B2A3651B5B3B4409C76AA62C7F310E335C6A0D628B718C98647D641` | 硬件/软件 |

审阅状态摘要：Round 5 / 10 / 12 均有独立事后审阅；Round 10 与 Round 12 的形式裁决与审阅 disposition 必须成对引用。

---

# 21. 作者写作时不要混淆的数值边界

1. **Round 5 AURC 与 Round 10 level-0 AURC 不是 bit-identical。** Round 5 Action-Only AURC = 0.388824；Round 10 clean = 0.388805。RQ1 表用 Round 5，剂量曲线用 Round 10，不要互相「修正」。  
2. **官方 manifest 与评价 cache 的 rationale support 相差 1–3。** 逐类 F1 用 cache。  
3. **Jaccard 0.916 是 Round 5 轻扰动 mean-three**，不是 Round 10 level-4 Jaccard 下降量（后者 endpoint 约 0.146 / 0.224 / 0.142）。  
4. **CEG 机器码 `STOP_CEG_INDEPENDENCE` 与科学码 `STOP_CEG_POPULATION_NO_V6` 并存。** 论文应写清两层，不要只留一个。  
5. **旧字段名** `safety_and_consistency_attribution_allowed` 出现在 Round 5 JSON 的 interpretation 块中；后续纸面文件已明确禁止把 S/C 差异因果归因于 rationale supervision。以纸面 claim boundary 为准。  

---

# Final Consistency Audit

- [x] 所有关键数字均可追溯至 artifact（上表 SHA-256 已于 2026-08-29 对文件字节重算，与 `ARSC_FINAL_STATUS.md` 中 Round 5/10/12/S/R/profile/seed 哈希一致）
- [x] Round 5 数字一致（profile JSON / summary JSON / 论文表三方对齐到 1e-9 量级）
- [x] Round 10 3/12 准确且全为 C1
- [x] Round 10 thresholds 已写出（A/R/S 0.01，C1 0.025，以及五条合取条件）
- [x] Round 12 没有被写成 unconditional PASS（形式 PASS + `ACCEPT_PASS_WITH_LIMITATIONS`）
- [x] v4 没有被错误写成 population failure（113 pairs 是 confirmatory audit；population 失败是后续 53 与 87）
- [x] CEG = closed and unanswered
- [x] DAAD-X 没被称为 external validation
- [x] Round 13 没被称为 scientific result
- [x] Rationale F1 没被解释为 faithfulness
- [x] C1 没被解释为 evidence reliance
- [x] synthetic perturbation 没被写成 real-world perturbation
- [x] BDD-OIA 没被写成 nuclear validation
- [x] seed-level negative directions 被保留（43 C1，45 AURC，46/47 Action，44/47 UAR）
- [x] AURC/UAR/ECE 没被强行统一成一个结论
- [x] 所有旧 “Safety / Consistency” 命名在论文推荐表述中已经纠偏

**已记录、不掩盖的非阻塞备注：**

1. `data_summary.json` 与 `rationale_coverage.json` 的 test rationale support 存在 1–3 的差；本文件已指定 F1 用后者。  
2. Round 5 与 Round 10 clean AURC 差约 2e-5；已要求分表使用。  
3. CEG 机器判定与科学判定代码不同，已并列写出。  
4. BDD-OIA / ResNet / temperature scaling / NPPAD 等核心引用题录在仓库中 **未核验**，必须 `NEEDS_EXTERNAL_VERIFICATION`，未编造。  
5. 当前无「核电实验数字」——正确状态是「当前无该结果」。

`PAPER_HANDOFF_READY`
