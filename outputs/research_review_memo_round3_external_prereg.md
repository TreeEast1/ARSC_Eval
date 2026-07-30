# Round 3 独立科研审阅备忘录：VLA4CoDrive 最小外部验证预注册

日期：2026-07-31  
角色：独立科研审阅者  
审阅范围：仅审阅研究设计、数据可获得性与停止门槛；不修改实验实现，不查看或追求“显著性”  
最终裁决：**CONDITIONAL GO（仅批准元数据/小样本可行性审计；尚不批准 118 GB 全量下载、训练或确认性结论）**

## 1. 一页结论

从 BDD-OIA v4 measurement gate 失败后转向 VLA4CoDrive，方向本身是科学的，原因不是当前结果“不够好”，而是：

1. v4 在盲审前已经固定了门槛，随后按门槛真实失败；
2. 官方 BDD100K validation 与 BDD-OIA 的可连接、未被先前审计使用的样本只有 53 个，其中 green 只有 19 个，未达到预先要求的总数 100、每状态 30；
3. 继续在同一 BDD-OIA test pool 上反复改 mask，会把 measurement development 与 confirmatory evaluation 混在一起；
4. VLA4CoDrive 提供独立的合成场景、动作、语言、2D/3D 标注以及跨天气帧对齐资源，能够用于检验 ARSC 度量框架是否可迁移，而不是继续优化同一个 BDD-OIA 测量工具。

但 VLA4CoDrive 不是 BDD-OIA 的直接复制。它是 CARLA 合成数据；动作是低层控制/未来轨迹，语言是窗口级自由文本，未见官方 train/validation/test split；官方示例中的 reasoning 也包含概括性、推测性表述，不是可直接使用的结构化 rationale ontology。因此本轮只能批准一个严格受限的 feasibility phase。只有动作离散化、语言本体、帧级对齐、scene-disjoint split、bbox 因果绑定和跨天气对齐均通过下面的冻结门槛，才可进入最小外部训练。

这项外部验证若通过，只能支持：

- ARSC 的计算定义和部分机制检验能否在一个受控合成驾驶域中工作；
- 在动作性能等价的条件下，Joint 与 Action-only 的安全排序、动作一致性及 CEG 是否出现有实践意义且跨种子同向的差异；
- Joint 模型的结构化 rationale 预测在经审计的 VLA4CoDrive 本体上是否有效。

它不能单独支持：

- ARSC 已获得真实道路跨域外部效度；
- VLA4CoDrive 的自由文本 reasoning 等同于 BDD-OIA 的 21 类 rationale；
- 天气重放等同于“语义不变的轻微扰动”；
- bbox 遮挡等同于真正的因果干预；
- Action-only 与 Joint 在 rationale 质量上存在直接优劣，因为 Action-only 没有 rationale 输出头。

## 2. 前序证据与转向合法性

### 2.1 BDD-OIA v4 必须停止

`outputs/validity/mask_audit_v4/audit_summary.json` 的盲审覆盖全部 113 对样本，得到：

- overall critical binding：106/113 = 0.9381，通过 0.90；
- overall control contamination：6/113 = 0.0531，超过 0.05，失败；
- green binding：67/67 = 1.0000，但 control contamination 为 4/67 = 0.0597，失败；
- red binding：39/46 = 0.8478，低于 0.90，失败；
- red control contamination：2/46 = 0.0435，通过；
- state-specific gates 未全部通过，最终 `overall_gate_passed=false`。

同时，`outputs/validity/masks_v4_invariants.json` 记录了 2 个 rendered patch shape mismatch，`all_invariants_passed=false`。这不是可以在确认性分析后忽略的小工程误差，因为 CEG 的可解释性要求 critical/control patch 在实际渲染后仍严格匹配。

因此，v4 不能用于确认性 CEG。这个决定与效应方向、大小或显著性无关。

### 2.2 BDD100K 官方 validation 不能提供足够的独立替代样本

`outputs/validity/bdd100k_validation_label_overlap.json` 显示：

- BDD100K 官方 validation 有 10,000 个样本；
- 与 BDD-OIA test 文件名重叠 268 个；
- rationale 与官方红/绿灯状态框匹配且未被任何既往 audit 使用的只有 red 34、green 19，共 53；
- 预注册门槛为总数至少 100、每状态至少 30，实际未通过。

所以“不再在 BDD-OIA 上继续磨 v5，而去独立数据源做外部验证”符合前序停止规则。不得把这次转向写成对 v4 的成功补救；v4 仍然是 measurement FAIL。

## 3. VLA4CoDrive 官方可获得性核验

核验来源限于官方仓库和由官方仓库链接的数据页：

- 官方 GitHub：<https://github.com/SayedPedramHaeri/VLA4CoDrive>
- 官方 Hugging Face 数据集：<https://huggingface.co/datasets/sayedpedramhaeri/VLA4CoDrive>

截至 2026-07-31 的只读核验结果：

| 项目 | 官方页面可见证据 | 审阅结论 |
|---|---|---|
| 公开性与许可 | GitHub 为公开仓库并标注 Apache-2.0；HF 数据页也标注 Apache-2.0 | 可用于可复现实验，但最终使用前仍应保存许可与 commit/revision |
| 数据规模 | HF 页面显示约 118 GB；README 声称约 10M vision、150K language、1M action、300–360 小时 | 数据真实存在，但不应先全量 snapshot |
| 模态 | 根目录可见 `Action`、`Language`、`Vision`、`Win`、`Metadata`；README 描述前后左右 RGB、LiDAR、动作与 30-step trajectory | 原理上覆盖 A/R/C 和外部场景信息 |
| 天气设计 | README 描述 8 towns × 8 weather，并称 weather replay frame-aligned | 有潜力做配对天气 stress test；必须先实测动作和帧键是否严格一致 |
| 语言结构 | 官方 JSON 示例含 `scene_id`、`window_id`、起止帧、采样帧、caption/context/description/reasoning | join key 和窗口边界可用 |
| reasoning 性质 | 官方示例为长自由文本，且出现对制动原因的推测，而非固定类别 | 不能直接计算 Rationale-F1；必须先做 ontology 与 temporal grounding audit |
| bbox | 官方仓库能看到 `Vision/.../Labels_2D` 及 3D/KITTI 目录 | 有 CEG 候选，但 bbox 类别、状态属性、实例跨帧一致性和因果相关性尚未证明 |
| 在线查看 | HF dataset viewer 当前提示尚不可用，但文件树和单文件页面可访问，并提供 `snapshot_download` | 可通过 `allow_patterns` 做小范围下载；viewer 不可用不是下载阻断 |
| 官方 split | 本次官方仓库/数据页核验未发现明确 train/val/test split | 必须自行构造并冻结 scene-disjoint split |

可获得性裁决是：**数据公开且可做小范围取样，不存在“数据集只是论文描述但无法访问”的阻断；但 schema 与跨模态对齐仍未达到可直接训练的程度。**

## 4. 外部验证的固定研究对象

### 4.1 最小输入与样本单位

主分析样本单位固定为一个 ego vehicle 的一个 30-frame window。为尽量保持与 BDD-OIA 单图协议的可比性，模型输入只使用：

- ego vehicle；
- front RGB；
- 该 window 的最后一个 `sampled_frame`；
- 不使用 rear/left/right、多车通信、LiDAR 或地图。

动作标签从与该最后帧同时间锚点的未来轨迹/低层控制构造。语言标签来自同一 window，但必须先通过“reasoning 对最后帧仍可见/可归因”的 temporal grounding audit。若这一门失败，不得临时改成中心帧或 8-frame clip 后仍称为同一确认性实验；中心帧、clip encoder 或多视角均属于后续探索性协议。

所有 Action-only 与 Joint 模型使用完全相同的图像、split、增强、backbone、训练预算、动作头和随机种子；Joint 仅增加 rationale 头与预注册的 loss 项。

### 4.2 独立场景键

严禁按 frame/window 随机划分。主键冻结为：

`canonical_scene_key = normalized_town_id + "::" + normalized_base_scene_id`

同一 `canonical_scene_key` 下的以下内容必须整体进入同一 split：

- 8 个天气版本；
- Vehicle_1/2/3；
- 所有 window；
- 所有 sampled frame；
- 所有传感器模态。

原因是官方说明天气版本为同一场景的 frame-aligned replay；不同车辆也可能看到同一交通事件。仅使用原始 `scene_id` 不安全，因为它可能在不同 town 中重复。

在 schema audit 后、模型训练前，对去重后的 canonical scene 列表按固定 seed `20260731` 哈希并按 town 分层为 60% train / 20% validation / 20% test。需要同时保存：

- 每个 scene key 到 split 的显式清单；
- 数据 revision；
- 生成脚本 SHA256；
- 每个 split 的 town、weather、action、rationale 分布；
- exact filename、内容 hash 和轨迹序列的跨 split 重叠审计。

任何 scene、天气副本、车辆副本、window 或相同轨迹序列跨 split，均为硬失败。允许在 train 内做类别采样；不允许用 test 分布调整 split 或阈值。

## 5. 四指标的可操作定义

### 5.1 A：Action Accuracy

#### 动作标签

从最后帧的 30-step future trajectory 在当前 ego 坐标系中计算：

- 纵向位移 `d_long`；
- 横向位移 `d_lat`；
- 终点速度 `v_end`；
- 未来窗口平均 brake（若字段存在）。

坐标轴正负、单位和采样周期必须用官方字段/小样本轨迹核验，不能凭文件名猜测。若轨迹为米制且 horizon 对所有样本一致，固定采用：

- `Stop = 1`：`v_end <= 0.5 m/s` 且 `d_long < 1.0 m`，或未来平均 `brake >= 0.20`；
- `Forward = 1`：`d_long >= 2.0 m` 且 `Stop = 0`；
- `Left = 1`：`d_lat >= 1.0 m`；
- `Right = 1`：`d_lat <= -1.0 m`。

`Forward` 可与 `Left` 或 `Right` 共现；`Left` 与 `Right` 不得共现。若坐标审计表明正负方向相反，只允许整体反转 `d_lat` 的符号，不允许按结果逐类调整。若官方单位并非米或 horizon 不恒定，必须先仅用 train scenes 确定物理等价阈值并形成带版本的 amendment；该 amendment 必须发生在任何模型训练和 validation/test 标签统计前。

动作离散化以未来轨迹为主，throttle/brake/steer 只用于一致性审计，不允许在看到类别不平衡后改用另一套标签源。近阈值样本不删除，不设事后灰区。出现 reverse、缺轨迹、NaN、时间锚点不一致的 window 按预定义 invalid reason 排除并计数。

动作映射必须经过至少 200 个、按 town/场景/动作分层的 window 审计；规则与轨迹/控制的语义一致率需至少 0.95，Left/Right 方向错误率必须为 0。

#### A 指标

- 主指标：4 类 multi-label Macro-F1，threshold 固定为 0.5；
- 次指标：Micro-F1、每类 F1；
- correctness：4-bit exact-set correctness；
- 不按 validation 为每类另调 threshold。

Action-only 与 Joint 的动作等价门槛冻结为：

`ΔA = Macro-F1(Joint) - Macro-F1(Action-only)`

其 scene-clustered 95% bootstrap CI 必须完全位于 `[-0.03, +0.03]`。这是实践等价边界，不是显著性追逐。如果不满足，RQ1 中对 S/C 的模型差异可能受动作能力差异混杂，只能描述，不作“rationale supervision 改善安全/一致性”的归因。

### 5.2 R：Rationale Fidelity

VLA4CoDrive 的 `reasoning` 是 window-level 自由文本，不能直接沿用 BDD-OIA 21 类标签。外部验证使用一个新的、冻结的、以可观察驾驶原因而不是动作复述为中心的 ontology。候选上位类仅包括：

1. traffic signal/sign；
2. lead or parked vehicle；
3. crossing/oncoming vehicle；
4. pedestrian/cyclist；
5. lane/road geometry or blockage；
6. junction/route/turn constraint；
7. visibility/weather hazard。

这只是候选集合。最终可纳入确认性 R 指标的类别必须同时满足：

- 能由 reasoning 文本以冻结词典/规则稳定映射；
- 不是“车辆正在刹车/转向/前进”这类动作标签的同义复述；
- 对选择的最后帧可见或可由同时间锚点的标注支持；
- train ≥200 positives、validation ≥50 positives、test ≥50 positives；
- 至少保留 4 个合格类别，否则不构成充分的 multi-label R 外部验证。

ontology 与映射规则只能在 train scenes 的语言样本上开发。之后在至少 200 个未用于词典开发、按 town 和类别分层的 validation windows 上盲审；其中至少 100 个由两名独立审阅者复核。通过门槛：

- 映射 precision ≥0.90；
- 对人工确认的可用原因 coverage/recall ≥0.85；
- 最后帧 temporal/visual grounding rate ≥0.90；
- unsupported/ambiguous rate ≤0.10；
- 双人多标签一致性（类别平均 Cohen's κ 或等价 chance-corrected agreement）≥0.75；
- 纯动作词汇泄漏率 ≤0.10。

任一门槛失败，不得继续训练 Joint 后再重写词典。此时 R、rationale Jaccard 和 rationale-bound CEG 均停止；只可把 A/S/动作一致性作为探索性可行性结果，不能称为四维 ARSC 外部验证。

R 指标固定为：

- 主指标：ontology classes 的 Macro-F1，threshold 0.5；
- 次指标：Micro-F1、每类 F1；
- 不使用 BLEU/ROUGE 等自由生成文本相似度；
- Action-only 没有 rationale 头，故 R 只用于评价 Joint，不能声称 Joint 的 R “优于” Action-only。

### 5.3 S：Safety-Aware Evaluation

为了与现有 ARSC 协议保持可比，主定义固定为：

- 错误事件：4-bit action set 不完全正确；
- confidence：四个 action 概率的最大值；
- 主指标：AURC、UAR@90；
- 次指标：ECE。

温度缩放只在 validation 上拟合一个正标量，并分别应用于两模型。由于正温度不改变样本的 confidence 排序，校准前后的 AURC/UAR@90 不应被包装成新增安全收益；ECE 是校准敏感量。

所有 risk-coverage、bootstrap 与 CI 的重采样单位是 `canonical_scene_key`，不是 frame/window。每个模型还需报告：

- overall exact-set error；
- 90% coverage 实际保留的 scenes/windows；
- 每个 action 的错误构成；
- constant-confidence 和随机排序 sanity reference。

“最大正类概率”未必是 multi-label 决策风险的最佳置信度。诸如最小决策边界距离、每标签置信度乘积等替代定义，只能列为探索性 sensitivity analysis，不得替换预注册主指标。

### 5.4 C：Consistency 与 CEG

#### C1：轻微图像扰动

在 clearNoon test 基准图上固定三类轻微扰动：brightness、Gaussian blur、Gaussian noise。具体参数必须在查看模型输出前写入 manifest。每种变换应：

- 在内存或无损格式中生成，避免 JPEG 重编码混杂；
- 与原图保持尺寸、crop 和标签完全一致；
- 先抽取至少 100 张、按 scene 分层、模型输出盲化的图像做语义不变审计；
- overall 及每扰动的 semantic-label-unchanged rate 均 ≥0.95。

指标：

- Action Flip Rate：原图与扰动图 4-bit action 是否发生任一变化；
- Rationale Jaccard：Joint 原图与扰动图的 thresholded rationale set Jaccard；
- identity transform 必须得到 Flip Rate=0、Rationale Jaccard=1，否则实现无效。

Action Flip Rate 可比较 Action-only 与 Joint；Rationale Jaccard 只评价 Joint。

#### C2：frame-aligned weather replay

天气变化不是普通“无害扰动”，因此必须与 C1 分开报告，不能和 brightness/blur/noise 平均成一个 C 分数。

基准 weather 固定为 `clearNoon`。训练与模型选择只使用 train/validation scenes 的 clearNoon；其他 weather 不进入训练。test scenes 上将 clearNoon 与同一 town/scene/vehicle/window/frame 的其他 7 个天气配对，前提是：

- join key 完全一致；
- 未来轨迹和离散 action label 一致率 ≥0.99；
- window 边界、采样帧和车辆身份一致率 =1.00；
- 至少每个 weather contrast 有 500 个有效 window、30 个 canonical test scenes；
- 人工语义审计 ≥100 对，场景事件保持率 ≥0.95。

通过后，天气 Action Flip Rate 和 Joint Rationale Jaccard 可作为**预注册的受控合成 stress test**。它支持“同一模拟事件跨渲染条件的稳定性”，不支持真实世界天气鲁棒性。如果动作/交通状态不是严格重放，整个天气分析降为探索性或停止，不能把不配对样本当作 consistency。

#### C3：bbox-controlled CEG

官方 2D bbox 只证明物体位置，不证明它是 reasoning 的原因。确认性 CEG 仅允许对同时满足以下条件的样本构造：

- rationale ontology 类与官方 bbox 类存在事先冻结的一对一或明确多对一映射；
- critical bbox 在选择帧中可见且确为该 rationale/action 的关键证据；
- control patch 与所有被标注的关键实例及其他同类证据无交叠；
- critical/control 在实际渲染后 width、height、pixel count、blur/noise 参数完全一致；
- 两个遮挡都不改变动作语义；
- traffic-light state、lead-vehicle relevance 等无法由 bbox 属性确认的类别不得仅凭类别名强行纳入。

最小池：

- ≥200 个有效 critical/control pairs；
- ≥30 个 canonical test scenes；
- 每个纳入的 evidence stratum ≥50 pairs；
- 独立模型输出盲审至少 100 pairs；若候选少于 100 则全审。

确认性门槛：

- critical binding correct ≥0.90 overall 且每 stratum ≥0.90；
- control critical-evidence contamination ≤0.05 overall 且每 stratum ≤0.05；
- semantic-label-unchanged ≥0.95；
- rendered patch shape mismatch =0；
- train/validation/audit/test scene overlap =0。

主量：

`CEG = drop(action-state probability | critical occlusion) - drop(action-state probability | matched control occlusion)`

每个模型先算 CEG，再报告：

`ΔCEG = CEG(Joint) - CEG(Action-only)`

CEG 不做温度缩放。只有 evidence stratum 通过全部门槛，结论才限定到该 stratum。bbox audit 若失败，不允许像 BDD-OIA v2-v4 一样在同一确认池继续迭代 mask；RQ2 的 CEG 分支记为未回答。

## 6. RQ1 / RQ2 的可回答范围与决策规则

### RQ1

冻结表述：

> 在 VLA4CoDrive 的 scene-disjoint、clearNoon 最小外部验证中，当 Joint 与 Action-only 的动作 Macro-F1 满足 ±0.03 实践等价时，Joint 的结构化 rationale fidelity 如何，以及两模型的 safety ranking 和 action consistency 是否存在稳定、有实践意义的差异？

RQ1 可以回答：

- Joint 的 Rationale Macro/Micro/per-class F1；
- 两模型的 AURC、UAR@90、ECE；
- 两模型在轻微扰动和配对天气下的 Action Flip Rate；
- Joint 自身的 Rationale Jaccard。

RQ1 不能回答 Action-only 与 Joint 谁的 rationale 更好。若动作等价门未通过，S/C 的模型差异仅描述为伴随差异，不归因于 rationale supervision。

### RQ2

冻结表述：

> 在 ontology、bbox 和天气配对审计均通过后，rationale supervision 是否带来更强的 rationale-bound evidence sensitivity，以及更低的动作翻转？

确认性支持规则不使用 p-value：

- CEG 分支：`mean ΔCEG ≥ 0.02`，且 3/3 个配对种子方向为正；
- 轻微扰动分支：`mean[FlipRate(Action-only)-FlipRate(Joint)] ≥ 0.01`，且 3/3 种子方向为正；
- 天气分支单独报告；若同样达到 0.01 且 3/3 同向，可支持“受控合成天气 stress 下”的子结论；
- scene-clustered 95% CI 必须完整报告，但不以反复调设置使其排除 0 为目标。

如果只通过其中一个分支，只支持对应机制，不得写成“RQ2 整体得到支持”。效应低于实践阈值或种子方向不稳，结论为未获得预注册支持，不再追加 backbone、seed 或阈值追逐结论。

## 7. 最小样本、训练和停止门槛

### 7.1 Feasibility phase：现在唯一获批的阶段

只允许按路径下载少量文件，不允许下载 118 GB 全量 snapshot。建议用官方 HF revision 和 `allow_patterns` 锁定：

- 2 个 town；
- clearNoon 加 1 个非 clear weather；
- 2–3 个 vehicle；
- 至少 200 个 windows 的 Language、Action、Metadata、Labels_2D；
- 仅为对齐/视觉审计下载不超过 200 个 front RGB frames。

此阶段不训练，不计算模型效果，也不根据预期效应挑 town/weather。

### 7.2 进入训练前的硬门

同时满足才可 GO：

1. **可获取性与完整性**：官方 revision 可固定；所选模态 join completeness overall 及每 town ≥0.95；Action/Language/image 的时间锚点错误率为 0；
2. **独立 scene**：至少 150 个完整 canonical scenes，使固定 60/20/20 split 的 test 至少 30 scenes；
3. **有效 windows**：全体 ≥5,000，test ≥1,000；
4. **四动作支持度**：每类 train positives ≥500、validation ≥100、test ≥100，且每类出现在至少 10 个 test scenes；
5. **动作语义**：200-window audit 一致率 ≥0.95，Left/Right 方向错误为 0；
6. **rationale ontology**：至少 4 个类别达到第 5.2 节全部质量与样本门槛；
7. **扰动语义**：三种轻微扰动各自 label-unchanged rate ≥0.95；
8. **训练/评估泄漏**：scene、weather replay、vehicle、window、hash、轨迹序列跨 split 无重叠。

1–6 任一失败：**STOP 四维外部验证**。不得通过放宽 ontology、降低最小 positives、合并 Left/Right、改阈值或换代表帧来救确认性实验；这些只能形成带新版本的新预注册。

天气 gate 失败：保留 C1，取消确认性天气 C2。  
bbox gate 失败：保留 A/R/S/C1，取消确认性 CEG 和 RQ2-CEG 分支。  
这两种局部失败必须明确写成“对应 RQ 未回答”，不能隐去。

### 7.3 最小训练协议

- 模型：同一 backbone 的 Action-only 与 Joint；
- 固定配对 seeds：`42, 43, 44`；
- 相同初始化策略、epoch/batch/optimizer/early-stopping budget；
- early stopping 只看 validation；test 每 seed 只做一次冻结评估；
- primary point estimate 为 3 seeds 均值；
- uncertainty 使用以 canonical scene 为 cluster 的 bootstrap，并同时展示三个 seed 的原始结果；
- 不因方向不一致继续补 seed；
- 不因 test 结果调整 action threshold、ontology、confidence、mask 或 perturbation severity。

## 8. 度量本身的最小 falsification / sanity checks

为了验证的是指标而不只是训练出一个模型，以下检查必须先于结果解释：

- A：标签与预测完全一致时四类 F1=1；全零/全一预测的边界行为保存；
- R：ontology label 随机置换后 F1 应降至类别 prevalence 对应基线；这只做离线 metric sanity，不重新训练；
- S：identity ordering 与 constant/random confidence reference 正确；scene-cluster 与 frame-level bootstrap 的差异同时保存，但主结论仅用 scene-cluster；
- C1：identity transform 的 flip=0、Jaccard=1；
- CEG：critical/control 互换时 CEG 符号相反；零面积或形状不等 pair 必须被 invariants 拒绝；
- C2：同一键的 action/trajectory 若不相等，系统必须停止配对，而不是静默计算天气 flip。

这些是实现与构念有效性的反证检查，不是为产生更好结果服务。

## 9. 明确标记为探索性的内容

以下结果即使后续计算，也不能进入确认性主结论：

- alternative action thresholds、dead-zone、由 steer/brake 直接定义动作；
- 在看到 validation/test 后修改 ontology 词典或合并类别；
- 中心帧、8-frame clip、rear/side/multi-view、多车协作、LiDAR；
- 其他 backbone、更多种子、不同 loss weight 的事后搜索；
- 把 7 个天气结果与三种轻微扰动平均成单一 C；
- 未通过严格轨迹配对的跨天气比较；
- alternative confidence definitions、classwise threshold、校准后 CEG；
- town-held-out、跨 town 泛化、severity curve；
- 连续控制误差、trajectory ADE/FDE；
- 自由文本生成指标；
- 与 BDD-OIA 的数值高低直接横向排名；
- 在 bbox gate 失败后于同一 test scenes 上继续开发 v2/v3 mask；
- 任何在 test 结果出现后才提出的 subgroup 或解释。

## 10. 主要威胁与报告措辞

1. **合成域威胁**：VLA4CoDrive 的受控性有利于机制验证，但不能替代真实道路外部效度。
2. **语言构念威胁**：reasoning 可能是概括或推测，甚至只是动作复述；不通过 ontology/grounding audit 就没有 R。
3. **时间错配威胁**：window-level language 与单个最后帧可能不一致；这是硬门而非可忽略噪声。
4. **动作构念威胁**：低层控制/轨迹不是 BDD-OIA 的人工驾驶建议。只能声称验证四动作接口的可迁移实现，不能声称标签语义完全等价。
5. **非独立样本威胁**：weather、vehicle、window、frame 高度相关；scene grouping 与 cluster bootstrap 是必要条件。
6. **bbox 因果威胁**：目标框相关不等于原因；CEG 结论必须限定到通过人工因果绑定审计的类别。
7. **训练分布威胁**：为保持天气 stress 的解释，其他 weather 不得进入训练；否则只能解释为多天气训练后的稳定性。

推荐的最终措辞是：

> “本实验是 ARSC 在一个公开、受控、合成驾驶数据集上的预注册最小外部机制验证。它检验度量管线能否在独立数据结构下保持可操作性，并不单独建立真实世界泛化。”

## 11. 最终裁决

**CONDITIONAL GO**

批准：

- 固定官方 GitHub/HF revision；
- 按 `allow_patterns` 获取小规模 Metadata/Action/Language/Labels_2D 与至多 200 张 front RGB；
- 完成 scene key、动作、ontology、时间对齐、bbox 和天气配对的盲化 feasibility audit；
- 按本备忘录保存全部 pass/fail 记录。

暂不批准：

- 118 GB 全量下载；
- 任何模型训练；
- 任何 test 结果；
- 将 VLA4CoDrive 称为已经完成的 ARSC 外部验证。

下一次 GO/STOP 只依据第 7.2 节门槛。若核心门通过，可进入三种子最小训练；若核心门失败，应如实终止四维验证，而不是继续寻找能产生理想结果的标签、阈值、帧或数据子集。
