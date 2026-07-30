# ARSC-Eval 独立科研审阅备忘录（Round 1）

审阅范围：当前 BDD-OIA 代码、全部 `outputs/` 结果及 RQ1/RQ2 结论。  
审阅角色：独立科研审阅，不参与本轮代码修改。  
总体判断：工程流水线已完成最小协议，但当前证据只能作为 descriptive pilot，尚不能证明四维指标“有效”，也不能证明联合理由监督改善关键证据依赖或扰动稳定性。

## 一、结论可证性

### RQ1

当前观察到：

- Joint 相对 Action-Only 的 Action Macro-F1 差值为 `+0.010480`。
- AURC 差值为 `-0.010331`，UAR@90 差值为 `-0.020234`，但未给出不确定性。
- 风险曲线并非全覆盖率占优：Joint 在 5% 与 10% coverage 的风险分别高约 `0.0395` 与 `0.0373`，曲线至少出现 6 次优劣方向切换。
- 平均 Flip Rate 仅改善 `0.002560`；分扰动看，brightness 改善 `0.001536`、noise 改善 `0.013167`，但 blur 恶化 `0.007022`。
- Action-Only 没有理由输出，故“Rationale 维度存在模型间差异”不能作为可比较的经验结论；目前只能说 Joint 提供了一个额外可评估输出。

因此，当前结果支持“ARSC 各列包含 Accuracy 之外的描述信息”，但不支持“存在显著差异”或“Joint 在 Safety/Consistency 上稳定更好”。`|ΔF1| <= 0.03` 只是点估计判据，不是等价性证明。

### RQ2

当前不能回答。关键原因：

1. CEG 只为 Joint 计算，而 CEG 本身只依赖动作概率，不要求 rationale head。缺少 Action-Only CEG 后，无法比较联合监督是否带来改善。
2. Joint CEG 为 `0.004461`，没有置信区间；数值很小，且 mask/control 设计存在系统偏差。
3. Joint-Calibrated 的 CEG 变为 `0.007685`，但它与 Joint 是同一模型。该变化只是概率温度变换造成，不能解释为证据依赖改变。温度缩放按原协议只应作用于 Safety。
4. Flip Rate 的改善很小且跨扰动方向不一致，单 seed 下无法归因于理由监督。

## 二、最高优先级问题（P0）

### P0-1：先修 CEG 对照，再跑多 seed

必须为 Action-Only 和 Joint 在完全相同的 mask pairs 上计算 CEG，并保存样本级：

- `p_clean`
- `p_critical`
- `p_noncritical`
- `delta_critical`
- `delta_noncritical`
- `CEG`
- 文件名、rationale、对应 action、检测类别、框、检测置信度

“Joint 的 CEG > 0”只能说明该模型在当前两种遮挡之间存在平均概率差；“联合监督改善关键证据依赖”要求直接检验：

```text
ΔCEG = CEG_joint - CEG_action_only
```

### P0-2：当前 mask/control 设计会使 CEG 比较失效

已核查的偏差：

- 3,798 个候选中仅 769 个有效，跳过 3,029 个，跳过率 `79.75%`。
- 769 个有效样本中 663 个是 traffic light，占 `86.22%`；traffic sign 仅 1 个。
- 350/769 样本含多个可定位 rationale，但实现先合并允许检测类，再选全局最高置信框，没有把“选中框—具体 rationale—对应 action”绑定。
- traffic-light detector 只识别通用交通灯，不能确认颜色或左右方向；因此可能把任意灯框绑定为 green/red/left/right green rationale。
- non-critical box 取离 critical box 最远的无重叠网格位置，只匹配面积、不匹配位置和内容。其归一化纵向中心中位数为 `0.962`，多数落在图像底边或角落；这与关键框的位置分布严重不同，也可能遮住道路、车道或其他关键目标。
- non-critical 只避开选中的 critical box，没有避开其他检测目标或其他被标注的关键证据。
- critical box 面积中位数仅占整图 `0.182%`，平均 `0.443%`，小效应容易被定位误差、插值及压缩噪声淹没。
- 从公式上，样本 CEG 等于 `P(noncritical)-P(critical)`，clean 项严格抵消；因此它本质上依赖两种 mask 是否真正构成受控配对。

在完成以下修正前，不应投入长时间多 seed 训练：

1. 选中检测框时记录并固定其具体 rationale，再映射到该 rationale 对应的动作；不要对样本所有正动作无差别求平均。
2. non-critical control 至少同时匹配面积和位置带，并排除所有相关检测框；推荐为每个 critical box 生成多个合格 control 后取均值。
3. 按 rationale/detected class 分层报告，不允许 86% traffic-light 样本代表全部关键证据。
4. 做分层人工定位审计；若不能确认灯色、方向和因果相关性，应将结果明确限定为 detector-localized occlusion sensitivity，而不是 causal faithfulness。

### P0-3：统计推断必须是配对且按图像聚类

下一轮至少 3 seeds，推荐 5 seeds。每个 seed 的两个模型必须使用相同：

- backbone/action-head 初始随机状态；
- 官方 split 与数据顺序；
- 训练预算和 checkpoint 选择规则；
- 图像、mask pair 与扰动实例。

统计要求：

- Macro-F1、AURC、UAR@90、Flip Rate、CEG 均报告模型间差值及 95% CI。
- image-level paired bootstrap 重采样时保留两个模型的配对。
- 三种扰动是同一图像的重复测量，bootstrap 应以 image 为 cluster，同时带走该图像的三种扰动；不得把它们当作 `3N` 个独立样本。
- 跨 seed 另报告 paired seed differences 与 mean ± SD；不能只合并所有预测后给一个窄 CI。
- 若要使用“动作准确率相近”作为 RQ1 前提，应在新结果产生前冻结等价界值。与当前协议一致可用 `±0.03 Macro-F1`，但通过条件应是差值 95% CI 完全位于该区间，而不是点估计落入区间。

## 三、指标级审阅（P1）

### Safety

实现遵守了原任务定义：confidence 为四个动作概率最大值，error 为四位动作集合任一位不匹配。但需要明确这是协议特定定义，不是天然适配 multi-label exact-set correctness 的置信度。

主要问题：

- `max(p_i)` 只反映最强正类，不反映其余位离 0.5 阈值的距离，却用来预测“整个四位集合完全正确”；置信度与 correctness 对象不完全匹配。
- 当前 full-coverage exact-set error 为 Action-Only `0.5330`、Joint `0.5150`，因此高 ECE 部分来自该定义错配，不能泛化称为模型整体“严重失准”。
- 标量温度 `T>0` 对 `max sigmoid(logit/T)` 保序，且不改变 0.5 二值决策，所以 Joint 与 Joint-Calibrated 的 AURC、UAR@90 完全一致是数学必然。校准当前只改善 ECE（`0.461689 → 0.337759`），不能声称改善选择性风险。
- Joint 风险曲线并非处处优于 Action-Only，单一 AURC 或 UAR@90 不应被写成全 coverage 的安全优势。

下一轮应保持原 Safety 主指标以便可比，同时把上述定义局限写清。若研究目标转为论证 Safety 指标本身的合理性，可做预注册的置信度定义敏感性分析，但不得事后挑选最有利定义替换主结果。

### Consistency

三种扰动强度表面上温和，但目前缺少语义保持核查，并存在统一 JPEG 重编码混杂：

- 原图与所有扰动图的差异同时包含 brightness/blur/noise 与 JPEG quality=95 的重编码。
- 应优先在推理时内存变换，或保存无损 PNG；若继续落盘 JPEG，至少需要 identity re-encode control 来量化编码本身造成的 flip。
- Action Flip Rate 是 0.5 附近的阈值事件，需保存样本级概率，并做阈值敏感性分析；主阈值仍固定为 0.5。
- Rationale Jaccard 把 clean 与 perturbed 均为空记为 1。当前 rationale Macro-F1 仅 `0.3010`，21 类中 7 类 F1=0，高达 `0.9025` 的 Jaccard 可能被 empty-empty 样本抬高。必须同时报告两边均空比例，以及 union 非空样本上的条件 Jaccard，作为诊断而非替换主指标。
- 仅一个 severity 点不能证明指标随扰动强度行为合理。若目标是验证 metric validity，可用少量预注册轻微强度等级做单调性检查，但不要做大规模搜索。

### Rationale

- Macro-F1 `0.3010`、Micro-F1 `0.5347`，且 car、person、left_lane、left_green_light、left_follow、no_left_lane、left_solid_line 共 7 类 F1=0。
- Action-Only 没有 rationale head，因此 R1 不能提供模型间“理由忠实性”对照。
- Rationale label correctness（R1）与 causal evidence use（R2）是不同性质；不能用较高的 label F1 代替 faithfulness，也不能用正 CEG 证明输出 rationale 正确。
- 后续应给 rare classes 的不确定性，并避免由高频类主导的总体叙述。

## 四、训练设计风险（P1）

- 单 seed 只能生成一次观察，不能区分辅助监督效应与优化随机性。
- 5 epochs 是原最小实验允许的资源折中，不是充分训练证据。Action-Only validation F1 持续上升；Joint validation Action F1 在第 2–5 epoch 明显波动，训练损失仍持续快速下降。
- 在多 seed 正式运行前，应只用 validation 决定固定训练上限、早停 patience 与 checkpoint 规则，再冻结。不得用 test 指标选择 epoch。
- 不做大规模超参搜索；两个模型必须保持同一训练预算。Joint 的 best-action checkpoint 用于所有 RQ 主比较，best-rationale checkpoint 仅作次要诊断，避免按不同指标选择对自身最有利的 checkpoint。

## 五、下一轮必须做

按顺序执行：

1. 冻结并存档当前 v0 pilot，不覆盖已有结果。
2. 修正 mask/control 配对并完成分层人工审计。
3. 用现有 checkpoints 同时计算 Action-Only 与 Joint CEG，保存所有样本级输出。
4. 为当前所有指标做 image-paired bootstrap，先判断效应量和不确定性。
5. 用 validation 确认固定训练预算/早停规则，然后运行至少 3、推荐 5 个 paired seeds。
6. 汇总 seed-level 与 image-level 不确定性；先回答 RQ1 的 accuracy equivalence，再检验 S/C 差异；RQ2 只用直接的 `ΔCEG` 与配对 stability 差值回答。
7. 内部效度通过后，才考虑增加数据集做外部效度验证。新增数据集不能修复当前 CEG 对照和 mask 偏差。

## 六、本轮不该做

- 不应立即扩展其他数据集、更多 backbone、VLM 或复杂模型。
- 不应在当前 mask 生成器不变的情况下直接烧 3–5 seeds。
- 不应把 Joint-Calibrated 当成独立训练模型，也不应解释其 CEG 变化。
- 不应把 `CEG > 0` 写成“因果忠实”或“联合监督改善”。
- 不应仅凭平均 Flip Rate 忽略 blur 的反向结果。
- 不应把三种扰动当独立样本扩大显著性。
- 不应根据 test 结果调整 mask 阈值、扰动强度、checkpoint 或“相近准确率”界值。
- 不应只报告 p-value；效应量、95% CI、方向一致性和实际量级必须同时给出。

## 七、建议通过标准

### 测量通过

- 分层人工审计至少覆盖 100 个 mask pairs，并覆盖所有有足够样本的检测类别。
- 建议 critical object/rationale/action 绑定正确率至少 90%，non-critical control 关键证据污染率不高于 5%；未达到时 CEG 不进入主结论。
- 各主要 rationale 分层有可报告样本量与 CI；样本极少的 traffic_sign 等只列为不可判定。
- 扰动图片无损或完成 identity re-encode control，且人工抽检确认语义标签不变。

### RQ1 通过

- `Δ Action Macro-F1` 的 95% CI 完全位于预注册等价区间（建议沿用 `[-0.03, +0.03]`）。
- 在此前提下，Safety/Consistency 的模型差值以配对 95% CI 报告；只有 CI 排除 0 且实际量级达到预注册阈值时，才称为明确差异。
- Safety 若只在部分 coverage 改善，应写成对应 coverage 的局部结论，不称整体支配。

### RQ2 通过

- `ΔCEG = CEG_joint - CEG_action_only` 的配对 95% CI 大于 0，并在多个有足够样本的 rationale 分层方向一致。
- 平均 Flip Rate 的 paired/clustered 95% CI 小于 0，且没有单一扰动出现超过预注册非劣界值的恶化。
- 至少 3（推荐 5）个 paired seeds 的效应方向基本一致；若 seed 间频繁反转，只能报告不稳定或证据不足。

### 校准通过

- 只把校准结论表述为 test ECE 改善。
- 明确说明 AURC/UAR 不变是正标量温度保持排序及 0.5 决策不变的必然结果，而非额外 Safety 增益。

## 八、最终审阅决策

当前版本：

- 工程完成度：通过。
- 最小协议符合度：基本通过。
- RQ1 强结论：不通过，只能作描述性观察。
- RQ2 结论：不通过。
- 四指标有效性/合理性验证：尚未通过。

下一次长实验的启动闸门是：先修 mask/control 与 action-rationale 绑定，完成分层人工审计，再运行 Action-Only CEG、paired bootstrap 和多 seed。其他数据集应排在这些内部效度修复之后。
