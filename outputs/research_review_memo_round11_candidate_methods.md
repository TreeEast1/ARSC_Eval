# Round 11 候选方法学备忘：冻结 Round10 输出的探索性增量分析（候选 A）

## 0. 文档状态与审查边界

- 状态：**候选方法审查，非最终方向裁决**。
- 本备忘只审查候选 A：只读使用 Round10 已冻结的 logits、targets、predictions、confidence、source-clip identity 与 corruption metadata，评估其是否还能产生非同义反复、可发表的信息增量。
- 本轮不实现分析、不修改既有协议、不重跑模型、不改写任何 Round7–10 结果。
- 候选 B（新外部数据验证）的可行性与优先级须等待 external scout 的独立报告；在收到该报告前，不做 A/B 最终选择。

## 1. 现有证据已经覆盖什么

| 轮次 | 已回答的问题 | 仍未回答的问题 |
|---|---|---|
| Round7 | 极端 association-destruction falsification；确认四指标在若干已知极端对照下并非完全失效 | 非极端梯度、映射稳定性、真实像素扰动和外部有效性 |
| Round8 | 同一冻结缓存上的 graded association-destruction；A/R/S/C1 的预注册单调门均通过 | 仍是合成标签—预测关联破坏，不是模型对视觉扰动的响应 |
| Round9 | 20 个前缀映射下四指标门均 20/20 通过，关闭 salt/map 偶然性疑问 | 没有新增模型行为或外部总体；不应再扩展同类 mapping 实验 |
| Round10 | 对 brightness/blur/noise 做真实重新推理；12 个门仅 C1 的 3 个通过，A/R/S 未通过完整单调门 | 为什么 C1 大幅变化而净性能/风险变化弱；clean 状态是否能预示 corruption 下的新增失败；外部泛化 |

因此，候选 A 只有在回答上述最后一行的两个“机制/预测”问题时才有信息增量。继续做指标间总体相关、更多映射或更换阈值，不构成新的有效性证据。

## 2. 候选 A 的非同义反复审计

### A1. clean uncertainty 对 corruption-induced incident failure 的预测

该问题可以是非同义反复的，但必须严格定义为“基线时刻的冻结预测量，预测之后扰动产生的新失败”：

- 预测量：Round10 已有定义的 clean action confidence，`max(sigmoid(action_logits / temperature))`；使用 `1 - confidence` 作为 clean uncertainty。不得在看过结果后从 entropy、margin、最小标签置信度等候选中择优。
- 风险集：仅纳入 clean 条件下 action exact-set correct 的图像。
- 结局：同一图像在预先指定的 level 4 corruption 下是否由 exact-set correct 变为 exact-set wrong。
- 主要判别量：clean uncertainty 区分 incident failure 与 retained correctness 的 tie-aware AUROC。

这与既有 S 不同：S 是同一条件内用 confidence 排序当前 error 的 risk–coverage 摘要；A1 是用 clean 时刻的冻结 uncertainty 预测随后 corruption 诱发的 incident failure。若混入 clean-wrong 图像，则“错误延续”会制造近乎平凡的可预测性；若改为 corrupted confidence 预测 corrupted error，则只是重算 S，必须禁止。

可发表的信息增量是有限但真实的：它检验现有 confidence 排序是否包含“未来脆弱性”信息，而不是再次证明 confidence 与同条件错误相关。

### A2. C1 与 accuracy/risk 变化为何可能不一致

以下命题本身是同义反复或机械关系，不能作为有效性发现：

- 在 clean-correct 风险集中，发生 action-set flip 必然意味着 corrupted exact-set wrong；因此用 C1 预测该 incident failure 是机械的。
- 在少量 seed × family 汇总点上计算 C1 与 A/S 的相关，样本依赖、点数很少，而且方向已从 Round10 结果可见。
- “C1 大而净 exact-set accuracy 变化小”可能仅由有害、获益及错误间横向转换互相抵消；会计恒等式本身不是新验证。

仍可增加的非平凡信息是**冻结的转换构成描述**：

1. 对每个 family × model 的 level 4 端点，将 action exact-set 状态转换分为：
   - harmful：clean correct → corrupted wrong；
   - beneficial：clean wrong → corrupted correct；
   - lateral：clean wrong → corrupted different-wrong 且 action set 发生变化；
   - stable：预测 action set 不变。
2. 报告 harmful、beneficial、lateral 的全样本发生率，以及 lateral / all-action-flips 的比例。该比例回答“高 C1 中有多少并未改变 exact-set correctness”。
3. 因 Round10 的 A 是四类 Macro-F1，而不是 exact-set accuracy，额外只允许报告所有四个 action 类的 TP/FP/FN 状态转换表，以精确重构 Macro-F1 端点。不得挑选响应最大的类别，也不得把非线性的 Macro-F1 变化伪装成可加的样本级归因。

该分析可说明 C1 是“输出不稳定性”而非“净性能损失”的直接量；它最多支持描述性互补，不能单独证明 C1 具有 psychometric 意义上的独立构念效度或增量效度。

### A3. 明确禁止的低信息增量分析

- corrupted confidence 预测同一 corrupted 条件的 error；
- clean-correct 子集上用 action flip 预测 corrupted error；
- 在 15/30 个高度依赖的汇总单元间做 C1–A/R/S 相关并称为构念效度；
- 根据已看过的 Round10 曲线选择 family、severity、model、action class 或阈值；
- 在同一批图像上训练高维 logits 分类器而没有真正未触碰的测试总体；
- 再做 association-map、salt、随机映射或更极端的同类标签关联破坏；
- 仅因某一事后 subgroup 有显著结果就把它升级为主结果。

## 3. 若候选 A 获批，应冻结的 estimand

### Estimand family E1：clean uncertainty 的前瞻判别力

固定 3 个 corruption families × 2 个 models，共 6 个主单元；severity 固定为 Round10 已预注册的 level 4 端点。

对单元 \(f,m\)：

- 风险集 \(D_{fm}=\{i: \hat{Y}_{i,m,clean}=Y_i\}\)，其中相等指四个 action 的 exact-set equality；
- 结局 \(Z_{ifm}=1\) 当且仅当 level 4 下 exact-set wrong；
- 预测量 \(U_{im}=1-\max_k \sigma(l_{imk,clean}/T_m)\)；
- 主 estimand：图像 occurrence 加权、ties 取平均秩的 AUROC\((U,Z)\)；
- 必须伴随报告：风险集大小、incident-failure prevalence、events/non-events 数目。

零假设可写为 AUROC = 0.5，但所有检验仍是 exploratory。不得另选更“好看”的 uncertainty 定义。若某主单元没有 event 或 non-event，则该单元不可估计，并按冻结失败规则报告，不能改结局或合并 family 补救。

若展示 level 1–3，只能作为完整 severity profile 的诊断附录，三个 level 必须全部展示，不得据其改换主端点。

### Estimand family E2：C1 flip 的转换构成

同样固定在 6 个 family × model 的 level 4 单元：

- harmful rate = correct → wrong 的图像数 / 全部图像数；
- beneficial rate = wrong → correct 的图像数 / 全部图像数；
- lateral rate = wrong → different-wrong 且 action set flip 的图像数 / 全部图像数；
- total action-flip rate = 任意 clean-to-corrupted action-set change / 全部图像数；
- 主描述量：lateral share = lateral flips / total action flips。

同时报告四个 action 类全部的 clean-to-level4 confusion-state transition counts，用于连接 Macro-F1 A。E2 不设置“通过/失败”门，不把恒等式包装成效度检验。

## 4. cluster unit 与推断总体

- 观测聚类单元固定为 **source clip**；3904 个有序 source-clip groups 是 bootstrap 的图像侧抽样单元，同一 clip 的成员帧与其所有 corruption 条件始终共同进出。
- 5 个 historical seeds 是配对的、固定训练 realization。可对 5 个 seed positions 做 paired resampling 以反映本实验内 seed 敏感性，但不得外推为“所有训练随机种子”的总体。
- 每次 bootstrap 使用同一组 seed-position draw 与 source-clip draw，跨两个模型、三个 families、全部 level 和全部 estimands 共享，以保留配对与协方差。
- 重复抽到的 seed position 或 clip 按 occurrence 保留；点估计也沿用图像 occurrence 权重，与 Round10 聚类约定一致。
- 三个 corruption families 是固定条件，不是从“所有自然分布偏移”随机抽出的 domain 样本。
- 建议冻结 5000 个确定性 bootstrap replicates 与独立于数据值生成的随机种子。任何 AUROC replicate 若缺少 event 或 non-event，不得静默删除或插补；须报告退化次数，该单元的区间结论标为 inconclusive。

## 5. multiplicity 与报告规则

事后冻结 multiplicity 不能恢复 confirmatory 身份，但可以限制选择性报告：

- E1 是唯一带零假设的主家族：6 个 AUROC > 0.5 检验使用 Holm family-wise correction；同时给出 6 个单元的 multiplicity-aware 95% simultaneous intervals。原始 p 值与调整后 p 值均完整报告。
- E2 为描述性家族：6 个 lateral-share 主估计给 simultaneous 95% intervals，不设显著性门；harmful/beneficial/lateral rates 与四类转换表完整报告。
- level 1–3、risk curves、uncertainty quantiles 等如保留，必须标为 unadjusted diagnostics，不能转化为主结论。
- 不允许把 E1 与 E2 中“成功的单元个数”另造一个 Round11 pass/fail gate。

## 6. controls 与失效判据

### 实现不变量

- level 0 identity：incident failure、harmful/beneficial/lateral 和 action flip 均应为 0。该项只检验 join、threshold 与配对实现，不是科学阴性对照。
- 主键唯一性、row count、source-clip membership、seed/model/family/level 完整性须与 Round10 frozen artifact 对齐；任何不一致均停止分析。

### 已知正对照

- 用 clean confidence 对 clean exact-set correctness 重构既有 S 的排序方向，仅作为实现桥接；不得作为 Round11 新发现。

### 阴性对照

- 在运行主分析前冻结一组 deterministic、outcome-blind 的 source-clip hash permutations，将 clean uncertainty 在 clip 层整体置换，并保持 clip 内帧与跨模型/seed 的配对结构；同一套置换用于全部 family。
- 该 empirical-null 仅检验 AUROC 管线是否会在破坏 predictor–outcome 对齐后系统地产生判别力。它不是新的 Round8/9 mapping 实验，也不得用最有利的 salt 作结论。
- 不使用“错误 seed 的 uncertainty”作严格阴性对照，因为不同 seed 对同一图像的难度可真实相关。

### 预先声明的分析失效

- 任一主键或 frozen metadata 无法无损对齐；
- 主 AUROC 单元缺少 event/non-event；
- 实现不变量非零；
- 结果生成后才改变 uncertainty、level、risk set、cluster unit 或 multiplicity family。

## 7. 结果已被看过后的证据等级

候选 A **只能是 post-result registered exploratory analysis**，不能称为 preregistered、confirmatory 或独立复现。原因不是代码是否提前写好，而是：

- Round10 的 C1-only 响应和 A/R/S 未过门已经被观察；
- A1/A2 的问题正是由这些已观察结果生成；
- 现在再切分同一冻结数据、冻结阈值或做 train/test split，都不能恢复一个未被观察的确认性总体。

因此，A 的适当角色是论文中的机制性/探索性补充：提供下一轮独立验证的明确假设与效应量，不得用来把 Round10 的 partial/fail 改判为 full pass。

## 8. claim boundary

允许的最强表述：

- 在同一 BDD-OIA 图像总体、两个既有 checkpoint、五个 historical seeds、三个固定合成 corruption operators 下，clean uncertainty 对某些 level 4 incident failures 显示（或不显示）探索性判别信息。
- C1 的变化可被 harmful、beneficial 与 lateral flips 的构成描述；这可解释输出不稳定性与净 exact-set correctness/Macro-F1 变化为何不同步。

禁止外推：

- 因果“脆弱性”、校准有效性、部署安全性或 failure prevention；
- 自然天气、真实传感器退化、未见 domain、未见架构或未见数据集；
- C1 已被证明为独立构念、充分风险指标，或比 A/R/S 更优；
- rationale faithfulness、grounding 或人类解释质量；
- 六个固定 family × model 单元之外的总体显著性。

## 9. 与候选 B 的暂定比较框架（不作裁决）

候选 B 若能提供真正独立、标签/任务兼容且可合法获取的数据，通常具有更高的外部有效性信息增益；但必须由 scout 回答：

- action 与 rationale target 是否与 BDD-OIA/ARSC estimand 可比，还是需要不可审计的标签映射；
- 是否有 source grouping、足够样本、可重建 logits/confidence 与明确 corruption/domain shift；
- 新数据是否真的是独立 population，而不是 BDD100K 派生重叠或同一测试分布的重包装；
- 许可、下载、算力与 checkpoint 适配是否可执行；
- 能否在接触 outcome 前冻结 endpoint、cluster unit、failure rule 与 multiplicity。

收到 scout 后的裁决原则应是：若 B 真正独立且 estimand 兼容，优先把 B 作为下一轮主验证；若 B 不兼容或不可执行，可将 A 作为边界清楚的探索性次级分析，但不得把 A 命名为“外部验证”或“confirmatory Round11”。这不是当前裁决。

## 10. 下一审查门

在 external scout 报告到达前：

- 不实现 A；
- 不打开新的阈值/uncertainty/level 搜索；
- 不修改 Round10 protocol、results 或已有 verdict；
- 保留 A1/E1 与 A2/E2 为唯一可接受的候选 A 范围。

下一次审查将只比较：A 的有限探索性信息增量，和 B 的实际独立性、可比性、执行风险。最终方向必须基于该比较，而不是因为 frozen logits 已经方便可用就默认选择 A。
