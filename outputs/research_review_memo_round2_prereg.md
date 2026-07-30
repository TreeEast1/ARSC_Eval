# ARSC-Eval 独立科研预审备忘录（Round 2 / v4 Preregistration）

审阅对象：

- `outputs/research_review_memo_round1.md`
- `outputs/validity/mask_audit_v3/audit_summary.json`
- `scripts/generate_masks_v4.py`
- `tests/test_mask_v4.py`

本轮只做预审，未修改实现，也未查看任何 v4 审计图片或模型在 v4 mask 上的反事实输出。

## 一、总裁决

**结论：CONDITIONAL。**

v4 的科学方向合理回应了 Round 1 的主要 P0：它放弃无法可靠确认行为相关性的 car/person/rider 等通用检测框，只保留非方向性 red/green traffic-light rationale；显式绑定 rationale 到 action dimension；critical/non-critical 使用同尺寸、近位置、无损 PNG；control 排除低阈值检测框并增加信号颜色保护。

但当前版本还不能进入 confirmatory CEG：

1. 文件名独立性目前 **FAIL**；
2. 独立审计抽样与统计门槛尚未充分预注册；
3. 测试与运行依赖目前 **FAIL**；
4. CEG 的主分析人群、人工审核后纳排、分层和停止规则尚未冻结。

这些问题可在不查看 v4 模型输出的前提下修复，因此总裁决不是最终 FAIL，而是 CONDITIONAL。

## 二、v4 对 P0 的回应情况

### 2.1 已合理解决的部分：PASS

- 只处理 `green_light` 与 `red_light`，排除了 directional traffic-light rationale。
- 要求每张图只激活一个 red/green rationale，避免同图多状态竞争。
- 输出只保留一个 `localized_rationale`，并通过 `RATIONALE_TO_ACTION_INDEX` 映射到 Forward 或 Stop。
- 后续已有分析代码按 rationale-bound action 的真实二元状态计算概率，而不是无差别平均所有正动作。
- critical/control 宽高完全一致；当前 178 对的 area ratio 全为 1。
- control 在纵向优先匹配，当前中心偏移中位数 `0.0344`、P95 `0.0861`，纵向偏移 P95 为 0，明显修复 v1 “control 常落在底部角落”的系统偏差。
- exclusion detector threshold 从 0.35 降到 0.10，并对框扩张后要求零交叠，方向上合理。
- critical 与 non-critical 均保存为无损 PNG，消除了两类 mask 之间的 JPEG 重编码差异。
- mask 选择没有读取 Action-Only/Joint 的预测或 CEG；目前未发现 v4 prediction cache，因此尚可建立独立的 confirmatory 边界。

### 2.2 仍需审计、不能由代码规则自行保证的部分：CONDITIONAL

- HSV 状态匹配不能自行证明灯属于 ego lane，也不能排除尾灯、反射、招牌或其他交通方向的灯。
- control 的检测框与颜色 guard 不能排除 detector 漏检，也不能保证 control 没有遮住其他与 Forward/Stop 相关的重要证据。
- green 的纵向灯位与长宽比规则会排除水平信号灯，red 规则则没有对普通红色小物体施加同等强的形状约束。该取舍可以接受，但只能靠全新文件上的盲审证明精度。
- `strict_light_evidence` 的模块说明写了 “connected evidence”，实际实现使用的是所有阈值像素的总数和质心，没有 connected-component gate。预注册描述和实现必须一致；不能把当前结果称为连通证据过滤。

### 2.3 已明确缩小的外推范围：PASS，但必须写入结论

v4 不是通用 critical-evidence evaluator。当前产出为：

- 2,517 个 single-state eligible images；
- 178 个自动选中 mask pairs，产出率约 `7.07%`；
- green 106，red 72；
- 只覆盖高选择性的非方向红/绿交通灯子集。

即使独立审计通过，也不能外推到 car、person、rider、traffic sign、方向灯、全部 BDD-OIA 样本或一般驾驶证据。

## 三、开发集与独立审计边界

### 3.1 当前边界：FAIL

v2 与 v3 审计样本互不重叠，共 210 个文件名。这 210 个文件承担了 measurement development 的作用，尤其 v3 traffic-light 人工结果被 `analyze_v3_light_audit.py` 用来观察通过/失败样本的颜色、形状与灯位特征，并据此制定 v4 规则。

但是当前 v4 manifest 的 178 对中，有 **65 对出现在 v2/v3 审计样本中，占 36.52%**：

- prior-audit green：39；
- prior-audit red：26；
- 真正 filename-disjoint 的 v4 pairs 仅 113 对：green 67、red 46。

`generate_masks_v4.py` 的标题与 generation summary 称 “filename-disjoint”，但生成器并没有读取或排除 prior audit manifests。当前说法与实际 population 不一致。

### 3.2 必须冻结的三种角色

后续必须显式区分：

1. **Development filenames**：v2/v3 审计的 210 个文件。允许用于制定 v4，但不得进入 confirmatory CEG 主分析。
2. **Independent v4 validation filenames**：当前 v4 中其余 113 个从未用于 v2/v3 人工审计的文件。用于 v4 独立人工审核。
3. **Model outcomes**：Action-Only/Joint 在 v4 上的概率和 CEG。必须在规则、文件集合、审核 rubric 与统计方案冻结之后才可读取。

因为独立 population 只有 113 对，建议对这 113 对 **全量人工审核**，而不是继续用通用 `10% per detected class` 抽样器。全量审核同时解决以下问题：

- 只有一个 detected class 时，原 sampler 无法保证 red/green 分层；
- 10% 只会得到约 12 对，远低于 Round 1 的 100-pair 审核要求；
- confidence-sorted evenly-spaced sample 不是概率样本，用其点比例套 90%/5% 门槛缺乏清楚的统计含义；
- 113 对的全量审核工作量仍可控。

v4 审核与 confirmatory CEG 使用同一批 113 个文件并非 outcome leakage，前提是：

- 审核者看不到两个模型的输出、CEG、旧模型在这些文件上的错误或置信度；
- v4 规则在审核前冻结；
- 审核后无论 PASS/FAIL 都不改变 v4 规则；
- 若审核失败，当前 113 个文件立即转为 development，不得再用于修改后的 v5 独立验证。

更保守的做法是将审核与 CEG 再拆分，但在当前仅 113 对的条件下会使两边均严重欠样本。全量、模型输出盲法的 measurement audit 是更合理的折中。

## 四、预注册规则审阅

### 4.1 生成规则：CONDITIONAL PASS

当前具体阈值至少写进了代码和 generation JSON：

- detector selection confidence `0.35`；
- exclusion confidence `0.10`；
- maximum control center offset `0.35`；
- red/green HSV、像素数、质心和形状 gates；
- control detection expansion、信号色像素限制；
- PNG 与 mean-fill。

在 v4 审核结果揭盲之前，这些规则可以视为已冻结的候选预注册。必须同时冻结并记录：

- generator code SHA-256：`86EBF174693C582BE259C28354A32D7A72385AF99A0351F6B4A86E4598B89A54`
- 当前 manifest SHA-256：`0BC9E68CB5C911AB977DA418691CC8F1F5CA5F4FD58E5281FCEC6908263125E0`
- detector weights SHA-256、Ultralytics/OpenCV/Pillow 版本；
- 完整命令行参数；
- v2/v3 两份 prior audit sample manifests 的 SHA-256 与 210 个文件名的并集。

由于 confirmatory manifest 必须排除上述 210 个 development filenames，排除后应生成新 manifest 并重新记录 hash。该修正必须在审计前完成。

### 4.2 人工审核规则：当前 FAIL，必须先补齐

原字段 `Semantic_Label_Unchanged` 不适合直接用于 critical mask。critical mask 的目的正是移除决定性证据；若把它解释为“遮挡后正确驾驶标签仍应不变”，概念上与 intervention 目标冲突。应在审核前改成可观察的视觉完整性 rubric。

建议每对至少记录：

1. `State_Matches_Rationale`：框内确有对应 red/green 亮灯状态；
2. `Controls_Ego_Action`：该信号灯可合理判断为控制 ego 行驶方向，而非其他车道/方向；
3. `Critical_Box_Is_Tight`：框主要覆盖目标灯，不同时遮挡其他决定性区域；
4. `Control_Free_Of_Target_Signal`：control 不含同状态/其他状态交通信号；
5. `Control_Free_Of_Other_Action_Evidence`：control 不遮挡车辆、行人、标志、关键车道边界等明显 Forward/Stop 证据；
6. `Pair_Artifact_Comparable`：两个 patch 尺寸、填充与视觉伪影可比，除位置内容外无额外编码差异；
7. `Uncertain`：无法可靠判断时必须记为失败，不得默认为通过。

`critical_binding_correct` 应定义为 1–3 全部通过；`control_contaminated` 应定义为 4 或 5 任一失败。

审核页面应隐藏 detector confidence、selection score、HSV 像素数、旧 audit 结果和所有模型输出，避免锚定；只显示文件匿名 ID、目标 state/rationale、整图与两个局部框。建议由未参与阈值制定的 reviewer 完成，至少对所有失败项及 20% 通过项做第二人复核并记录一致性/裁决。

### 4.3 审核通过标准：须在揭盲前冻结

建议全量审核 113 个 disjoint pairs，并同时要求总体与两个 state 分层通过：

- critical binding correct rate `>= 0.90`；
- control contamination rate `<= 0.05`；
- pair artifact comparable rate `>= 0.95`。

只看总体会允许 green 的高比例掩盖 red 失败，或反之，因此 red 46 与 green 67 必须分别满足同样门槛。因为这是对有限 113-pair confirmatory population 的全量审核，可直接使用精确有限总体比例；若最终只抽样而非全审，则必须改用预注册的单侧置信界，而不是只比较点比例。

### 4.4 CEG 主分析规则：当前 FAIL，必须在推理前补齐

建议冻结为：

- Primary cohort：113 个 filename-disjoint v4 pairs 中，人工确认 `critical binding`、`control free` 与 `artifact comparable` 全部通过的 pairs。
- Sensitivity cohort：全部 113 个自动选择 pairs，不按人工结论过滤。
- Primary target：由唯一 localized rationale 绑定的 action dimension 的 ground-truth binary state。
- Per-sample CEG：

```text
P(correct action state | noncritical)
- P(correct action state | critical)
```

- Primary contrast：

```text
Delta_CEG
= mean(CEG_joint - CEG_action_only)
```

- Joint-Calibrated 不进入 CEG。
- 模型配对、mask 配对及 bootstrap 均以 filename 为单位。
- red/green 为预注册 secondary strata；总体为唯一 primary CEG。
- 不把 v2/v3 CEG 与 v4 CEG 合并。
- 不因 v4 CEG 的方向修改 gate、mask 阈值、纳排或 state 定义。
- 必须保存每个文件、模型、condition 的 action logits/probabilities、正确状态概率与 CEG。

如果要从“两个 checkpoint 的差异”升级到“联合理由监督的训练效应”，还必须在读取任何 seed-level 中间效果前固定完整 seed 列表、训练预算、checkpoint 规则与 seed 聚合方法，并完成至少 3、推荐 5 个 paired seeds。

## 五、测试与可复现性

### 当前状态：FAIL

`tests/test_mask_v4.py` 当前只有 3 个简单测试。使用工作区默认 `python` 执行时，测试在 import 阶段失败：

```text
ModuleNotFoundError: No module named 'cv2'
```

`requirements.txt` 未显式列出 OpenCV。即使某个 Ultralytics 环境间接安装了它，当前独立复现入口仍不完整。

现有测试还未证明：

- prior v2/v3 audit filenames 被排除；
- red/green rationale 唯一且 action mapping 正确；
- action target 的正/负状态被正确评分；
- low pixel count、错误灯位、错误 aspect、混合状态被拒绝；
- 所谓 connected evidence 是否真的连通；
- control 与 expanded exclusion boxes 零重叠；
- control exact size、maximum offset 和 signal-pixel limit；
- 当无合法 control 时可靠返回 `None`；
- selection 与 control 在重复运行中确定性一致；
- 输出 PNG 存在、尺寸一致、无文件名碰撞；
- manifest 不含重复文件、旧 audit 文件或 directional rationales。

另外，`test_control_avoids_signal_color` 只断言最终选中区域没有红色，并没有证明算法曾把一个更优但含红色的候选明确拒绝，因此对 color guard 的保护力较弱。

### 审核前必须新增的检查

1. 显式安装/锁定 OpenCV 依赖，并让测试在 README 指定环境中通过。
2. 加入 integration invariant test：v4 confirmatory manifest 与两份旧 audit sample manifests 的交集严格为 0。
3. 加入 state-stratified count 与唯一 rationale/action binding 检查。
4. 对 strict red/green gates 增加正例、边界值与主要负例测试。
5. 让实现或文档统一“connected evidence”：若保留该主张，就必须用 largest connected component 并测试 scattered pixels 被拒绝；否则删除该主张。
6. 完整测试 control 的面积、位置、expanded detection exclusion、signal guard、无候选行为。
7. 对最终 113-pair manifest 运行全量自动不变量审计，并保存 JSON：旧文件 overlap、框交叠、面积比、offset、signal pixels、重复文件、丢失 PNG 均为 0/合格。
8. 为生成脚本、detector 权重、manifest、审核文件和最终 gold cohort 保存 SHA-256。

只有上述检查通过，才允许生成独立审核页面。

## 六、独立审核通过后，CEG 能支持到什么强度

### 仅 audit PASS

可支持：

> v4 在 BDD-OIA test 中一个 filename-disjoint、自动筛选的非方向红/绿交通灯子集上，达到了预注册的人工定位与 control 质量门槛。

不能支持模型效应，也不能支持 ARSC 有效性。

### audit PASS + 单 seed paired CEG CI 排除 0

可支持：

> 对当前两个具体 checkpoint，在人工确认的红/绿灯子集上，Joint 与 Action-Only 对“遮挡目标灯”相对于“遮挡空间匹配 control”的正确动作状态概率响应存在配对差异。

更具体地，若 `Delta_CEG > 0` 且 95% CI 全大于 0，可称 Joint 在该子集上表现出更大的 **rationale-bound controlled occlusion sensitivity**。

仍不能称：

- 联合监督一般性地改善因果忠实性；
- 模型真正“推理使用”了正确证据；
- 结果适用于所有 BDD-OIA rationale 或全部测试图像；
- CEG 已被普遍验证为有效的 causal metric。

### audit PASS + 预注册多 seed 结果一致

若至少 3、推荐 5 个 paired seeds 中效应方向稳定，seed-level 汇总不确定性也支持 `Delta_CEG > 0`，可以将结论提升为：

> 在固定训练协议和 BDD-OIA 高精度非方向红/绿灯子集内，证据与“联合理由监督提高了 rationale-bound controlled occlusion sensitivity”一致。

“causal faithfulness”仍应避免。mask intervention 未随机生成真实世界反事实，检测条件选择率仅约 7%，且 occlusion response 仍可能受遮挡伪影、上下文冗余和模型脆弱性影响。

## 七、明确停止/继续门槛

### 立即 STOP，不得运行 confirmatory CEG，如果：

- confirmatory manifest 与 210 个 v2/v3 development filenames 有任何交集；
- OpenCV 依赖与新增不变量测试未通过；
- v4 规则、审核 rubric、primary cohort 和统计规则尚未冻结；
- 审核者已看到模型输出或旧 CEG 后才决定样本纳排；
- v4 审核样本不足且仍使用只按 detected class 的通用 10% sampler。

### 审核后 STOP，并将 v4 记为 measurement failure，如果：

- 总体或 red/green 任一分层未达到 binding `>=0.90`；
- 总体或 red/green 任一分层 control contamination `>0.05`；
- 总体或 red/green 任一分层 artifact comparable `<0.95`；
- 审核中发现 rubric 无法一致判定 ego-relevance 或 control contamination。

审核 FAIL 后，不得根据这 113 个文件修改规则并把同一批文件称为独立 v5 audit；后续改版必须使用新的未见文件或外部数据。失败版本仍可作为 exploratory measurement-development 记录。

### 继续到完整 CEG/多 seed，如果：

- 所有依赖、测试、hash 与 disjoint assertions 通过；
- 113 个 disjoint pairs 完成模型输出盲法人工审核；
- 总体和 red/green 三组均通过固定质量门槛；
- gold cohort 与 sensitivity cohort 已冻结；
- 全部 seed 列表与分析规则已冻结。

一旦进入多 seed，应完成预注册的全部 seeds，不因单 seed 或 interim CEG 方向提前停止。

### 最终结果停止规则

- `Delta_CEG` CI 包含 0：报告证据不足，不得在同一 test population 上继续调 mask 直至显著。
- red/green 方向不一致：总体效应只能称异质，不得写成统一 traffic-light 改善。
- image-level CI 支持但 seed-level 不稳定：只能作 checkpoint-level 结果，不能归因于联合监督。
- 两层不确定性和各 seed 方向均支持后，才允许使用上节限定范围内的“证据与改善一致”表述。

## 八、最终状态表

| 项目 | 状态 | 理由 |
|---|---|---|
| v4 科学方向 | PASS | 高精度、单 rationale/action、空间匹配、低阈值排除、PNG |
| 对 Round 1 P0 的完整回应 | CONDITIONAL | 仍依赖独立 ego/state/control 人工审核 |
| development/audit 文件独立 | FAIL | 当前 178 对中 65 对来自旧 audit |
| 生成规则可冻结性 | CONDITIONAL | 阈值明确，但缺权重/环境/hash 完整 provenance |
| 人工审核预注册 | FAIL | 样本量、state 分层、rubric、盲法尚未固化 |
| 单元/集成测试 | FAIL | 默认环境缺 cv2，关键不变量未覆盖 |
| 现在运行 confirmatory CEG | FAIL | 必须先通过本备忘录的前置门槛 |
| 修复前置问题后继续 v4 audit | PASS | 不需要扩大数据集或模型 |

**最终建议：保留 v4 的窄范围策略，但先把 65 个 development-overlap pairs 从 confirmatory manifest 排除，对剩余 113 对做模型输出盲法全量审计。只有审核和工程门槛同时通过，才进入 Action-Only/Joint CEG 与多 seed。**
