# Round 8 正式结果后独立科研审阅

## 0. 审阅身份、范围与总裁决

本审阅以独立科研审阅者身份完成。审阅对象是已经冻结并完成 one-shot 运行的
Round 8 graded association-destruction experiment，以及随后由独立实现完成的结果复核。

本次允许的操作仅包括：

- 读取已经保存的 protocol、Amendment、preflight、manifest、正式结果与 audit；
- 对已保存 primitive 和 bootstrap draw 做只读复算；
- 检查 Git 历史、文件哈希、失败尝试留痕和结果治理链；
- 分析四个指标的可支持结论与不可支持结论；
- 给出且只给出一个下一步实验方向。

本次没有：

- 修改 Round 8 代码、输入、map、metric、threshold、seed、gate 或结果；
- 启动新实验；
- 下载新数据；
- 训练模型；
- 将探索性结果改写为预注册结果。

总裁决必须分为两层：

1. **计算与形式层：PASS / VALID。**  
   Round 8 的正式结果、独立复算、bootstrap、哈希绑定与运行治理相互一致，没有发现
   会推翻正式数值或 formal gate 的实现错误。
2. **科学、构念与外部层：PARTIAL / BOUNDED INTERNAL EVIDENCE。**  
   本轮证明的是四个预定义统计量对同一 BDD-OIA population 上、同一个 outcome-blind
   association-destruction construction 的 graded responsiveness。它不是四个构念的完整
   有效性证明，更不是跨数据集、跨模型、真实驾驶安全或 rationale faithfulness 的验证。

因此，本轮正式结论是：

> Round 8 的预注册计算命题通过；四轴在冻结的 BDD-OIA 五个训练 seed、一个 map/salt、
> 五个 q 水平以及 association-component-cluster 条件推断下，均满足严格相邻步响应 gate。
> 这构成较强的内部响应性证据，但只能作为 construct validity 与 external validity 的一部分。

---

## 1. 治理链与不可变性审计

### 1.1 关键正式产物

下列 SHA256 已复核：

| 产物 | SHA256 |
|---|---|
| `round8_graded_response_results.json` | `4CD0FCD16ED4A3BAE1D378FD10B3A44705F2433FDF3C3E15A26FBCE303AF6FD3` |
| `round8_graded_response_primitives.npz` | `6E51FB8842C6A6510364415C9D2D19C2307363024C34C8C7DE00DB57DCC7160C` |
| `round8_graded_response_independent_audit.json` | `8B0ACD210BEAA7629673732D86F79E35619C7D7106B11FEEB380CA4D1A0BBFDC` |
| `round8_graded_response_independent_bootstrap_draws.npz` | `BF5AB79EC55B1AA0FCFCAF7B7AC5EB9A6DA52EF37916374B7BD526847002190D` |

关键治理文件也保持一致：

| 产物 | SHA256 |
|---|---|
| protocol | `B96AC789BA12DD0FE65AF2138C54248C2154C1E1489D911571422EDE94B65357` |
| Amendment 01 | `D15E6F93FFEF686172F3887BAB609E6DA724ECE975BB125485A717688A020C8A` |
| 预注册审阅 memo | `83C13D1112ABAF9CBA6504E26BBB0BDBBDD99C5D7A45DB27A840D0A695B65BF2` |
| Amendment 01 GO memo | `CBF47293F5D983772C305B53E7C1DACD056D1609C7BA4F0A3B284BFAEEC9B66A` |
| attempt01 failure GO_RERUN memo | `9E051D174D3DC4117C6F4F9005EE03791CF297E0E5495E0C38953D6BA3ED54B8` |
| repaired preflight | `595D9E0A68124ADE294B90AD3891365C569AEE367CD576AC9C97F2D647CFBA0F` |
| pre-outcome run manifest | `85DC92712634C56B856409E3A58105205ABCCA504238A8B74EA3EC1F1F334ACD` |
| point CSV | `CDCBE0BAA0DD949B9F18F2545C76C4BC98328B3F48D301D018CF09D1B2AB7620` |
| bootstrap CSV | `A4042CEBB040CBC744BAF3D2BF6081CEC76AABA64C1F0962C0C15465A3276C41` |
| formal tmux log | `B09902A81C392F4FDBDEEF44A56DF93DEF15636480A6CCFB959785D9F2816351` |

### 1.2 结果前冻结与失败尝试

preflight 为 **86/86 PASS**，并明确记录：

- `q_greater_than_zero_metric_outcomes_computed = false`；
- `real_data_tie_averaged_primary_computed = false`；
- q=0 只执行预注册允许的 Round 7 bridge；
- 五个 seed 的 A、R、C1 correct-pair point estimate 与 Round 7 精确一致；
- S 的 prediction、error、confidence primitive 及 canonical-stable diagnostics 与 Round 7
  精确一致。

同一代码和输入状态下连续两次 preflight：

- preflight JSON byte-identical；
- run manifest byte-identical；
- 两次均为 86/86 PASS；
- q>0 outcome 均未计算；
- attempt01 的正式 result artifacts 均不存在。

attempt01 的浮点归约顺序错误在正式结果写盘前触发 STOP。失败日志被保留，独立审阅后只允许
outcome-independent 的 reduction-order 修正与 timing normalization。修复、测试、重新冻结和
byte-stability audit 均发生在 attempt02 之前。结果 provenance 同时绑定 protocol、Amendment、
两份 pre-outcome 审阅、失败日志、修复后代码、preflight 和 manifest。

这条链支持“受控实现失败后重跑”，不支持“看结果后改统计定义”的解释。没有发现 HARKing
证据。

### 1.3 Git 状态

正式结果和独立复核分别存在于清晰的提交历史中：

- `d9e7370 Record Round 8 graded response results`
- `b5a7f58 Add independent Round 8 result verifier`
- `ff127ed Independently reproduce Round 8 statistics`

正式审阅时 HEAD、`main` 与 `origin/main` 均指向 `ff127ed`。本 memo 不把后来出现的绘图文件
或其他未提交工作树内容视为 Round 8 formal evidence。

---

## 2. 独立数值复核

### 2.1 独立实现边界

independent verifier：

- 不 import `arsc_eval`；
- 不调用 formal one-shot script；
- A/R 从 component-level TP、FP、FN 重新构造；
- S 从 confidence-group sufficient statistics 与 harmonic tie expectation 重建；
- C1 从 component-level per-image event primitive 重建；
- 独立检查 CSV、primitive、map、component、bootstrap draw 与 formal result 的一致性。

独立 audit 为 **7/7 PASS**。

### 2.2 输入、map 与 component

复核得到：

- 样本数：4,557；
- 训练 seed：43、44、45、46、47；
- q：0、0.25、0.50、0.75、1.00；
- 87 个 primitive arrays；
- 五个 source map 均为 shape `(5, 4557)`；
- 所有 q map 均为全局 bijection；
- 所有 association component 对所有 q 都 source-closed；
- association component 数：1,625；
- component image size：2 至 14；
- 从 map 和 clip identity 独立重建的 component 与冻结 artifact 一致；
- primitive 中保存的 error 与从 prediction/target 独立重算的 error 一致。

这些检查证明 association-component bootstrap 的计算单位与冻结 map 是相容的。它不证明
这些 component 是自然世界中彼此独立的 1,625 个新场景或新数据集。

### 2.3 point estimate 一致性

正式 CSV 含 1,575 个 point rows，bootstrap CSV 含 4 个 axis rows。

独立复算与正式结果之间：

- primary/full point 最大绝对差：`1.8762769116165146e-14`；
- raw bottleneck 最大绝对差：`9.325873406851315e-15`；
- mean curve/SD 最大绝对差：`5.374173328576148e-15`；
- bootstrap summary 最大绝对差：`2.411265631607762e-15`。

这些差异完全处于浮点归约误差量级，没有改变任何方向、CI 或 gate。

### 2.4 bootstrap draw 一致性

独立 draw artifact 包含 `A`、`R`、`S`、`C1` 和 `_image_counts`：

- 每轴 2,000 个有限 draw；
- array 的 dtype、shape 与 bytes 哈希均匹配 audit；
- 用 `np.percentile` 对 draw 直接复算，A/R/C1 的 CI 与 formal 结果精确一致；
- S 唯一差异为 `2.411265631607762e-15`；
- 每个 replicate 使用一个共享 component draw；
- component 被抽中时保留全部成员及其 multiplicity；
- replicate image count 可变，最小 4,347，最大 4,858，均值 4,555.03；
- bootstrap statistic 为“每个抽中 seed 内先取最小 adjacent step，再对抽中 seed 求均值”。

因此正式 CI 与预注册 bootstrap contract 一致。

---

## 3. Formal gate 结果

正式状态为 `COMPLETED_ONE_SHOT`。每轴均满足：

- 五个 raw seed bottleneck 全部大于 0；
- 五 seed mean bottleneck 大于 0；
- association-component × seed bootstrap 的 pointwise 95% CI lower 大于 0；
- 五 seed mean component curves 没有相邻方向 reversal；
- 四轴 intersection gate 全部通过。

| Axis | 五 seed mean bottleneck | seed SD | 95% percentile CI |
|---|---:|---:|---:|
| A | 0.0686707912 | 0.0022588851 | [0.0596739496, 0.0728060780] |
| R | 0.0464163827 | 0.0039227677 | [0.0405713681, 0.0495232948] |
| S | 0.0269357067 | 0.0043626169 | [0.0183702976, 0.0300905967] |
| C1 | 0.1648891815 | 0.0023358015 | [0.1500024599, 0.1651522552] |

五个 raw seed bottleneck 为：

| Seed | A | R | S | C1 |
|---:|---:|---:|---:|---:|
| 43 | 0.06893865 | 0.04744095 | 0.03315547 | 0.16370419 |
| 44 | 0.06647921 | 0.04578337 | 0.02381009 | 0.16472826 |
| 45 | 0.06628000 | 0.04414212 | 0.02816155 | 0.16216809 |
| 46 | 0.07133405 | 0.04220229 | 0.02187391 | 0.16845878 |
| 47 | 0.07032205 | 0.05251319 | 0.02767752 | 0.16538658 |

formal 结论是稳健的：没有某一轴只靠单个训练 seed 勉强越过零线。

需要保留 multiplicity 边界：四个 interval 是 **pointwise** interval，不是四轴 simultaneous
familywise 95% interval。由于 full result 采用预注册的四轴 intersection gate，不能把它改写为
四个独立的、具有 simultaneous 95% coverage 的显著性声明。

---

## 4. 四轴科学解释

### 4.1 A：action agreement/accuracy responsiveness

五 seed mean primary curves：

| q | Action-only Macro-F1 | Joint Macro-F1 |
|---:|---:|---:|
| 0.00 | 0.674050 | 0.685586 |
| 0.25 | 0.595895 | 0.605172 |
| 0.50 | 0.522825 | 0.530171 |
| 0.75 | 0.454154 | 0.457291 |
| 1.00 | 0.375166 | 0.376541 |

支持的解释：

- 当 prediction 固定、action target prevalence 固定，而 sample–target association 被逐级破坏时，
  两个模型的 Macro-F1 都按预注册方向逐步下降；
- A 对这种 association destruction 有明确且跨五 seed 一致的响应。

不支持的解释：

- 不能据此证明 action ontology 完整；
- 不能证明 action prediction 在真实驾驶上安全或因果正确；
- 不能证明 threshold、其他模型、其他 action label space 或其他数据集同样成立。

### 4.2 R：rationale-label responsiveness

Joint 21-label Macro-F1 五 seed mean curve：

`0.273589 → 0.223890 → 0.177425 → 0.128330 → 0.078737`

macro gate 严格通过，但 per-class diagnostics 显示重要边界：

- 21 类中有 6 类在所有 q、所有五个 seed 上 F1 恒为 0；
- 这 6 类为 `car`、`person`、`left_lane`、`left_follow`、`no_left_lane`、
  `left_solid_line`；
- 对应 predicted positive count 为 0；
- 另有弱支持/平台型类别，例如 `other_obstacle`、`left_green_light`、
  `left_obstacle`。

所有 21 条五 seed mean per-class curves 没有向上 reversal，但这不等于 21 类都得到了有效的
graded validation：恒零曲线既不提供辨别力，也不能证明该类指标有效。

因此支持的结论只能是：

> R 的 **21-label Macro-F1 aggregate** 对冻结的 association destruction 呈严格响应。

禁止写成：

- 21 个 rationale 类均被验证；
- rationale ontology 被验证；
- 模型 rationale 是 grounded、faithful 或 causal；
- 模型实际“使用了”其 rationale。

### 4.3 S：selective prediction / confidence–error association

primary tie-averaged AURC：

| q | Action-only | Joint |
|---:|---:|---:|
| 0.00 | 0.388805 | 0.372213 |
| 0.25 | 0.418423 | 0.406262 |
| 0.50 | 0.455228 | 0.443546 |
| 0.75 | 0.488114 | 0.477935 |
| 1.00 | 0.527061 | 0.515420 |

其他诊断的五 seed mean 方向：

- canonical-stable AURC 与 tie-averaged AURC 同向上升；
- UAR@90 同向上升；
- correctness AUROC 从约 0.67 降至约 0.49；
- highest-confidence decile error 上升；
- lowest-confidence decile error 下降，最终高低 decile 接近；
- exact-set error rate 在 q 间保持常数；
- ECE 基本不变，只出现很小漂移。

这组“分化”不是矛盾，而是不同统计量测量对象不同：

- S construction 只置换 confidence 与 sample/error 的对应关系；
- prediction 与 error multiset 不变，所以总体 error rate 必然不变；
- confidence value multiset 也不变，固定 binning 的 ECE 对纯排序破坏可以近乎不敏感；
- AURC、UAR、AUROC 和 decile diagnostics 直接依赖 confidence–error ordering，因此方向一致。

支持的结论：

> tie-averaged AURC 能检测冻结 confidence values 与 exact-set errors 之间关联的逐级破坏；
> tie averaging 消除了 equal-confidence block 内输入顺序造成的隐藏 tiebreak。

不支持的结论：

- 不能宣称模型被重新校准；
- 不能宣称 ECE 已验证；
- 不能宣称总体预测更不安全；
- 不能把 selective-risk responsiveness 等同于真实世界 safety validity。

### 4.4 C1：clean–perturbed correspondence responsiveness

五 seed mean curves：

| q | Action-only flip | Joint flip | Rationale Jaccard |
|---:|---:|---:|---:|
| 0.00 | 0.118543 | 0.102436 | 0.916003 |
| 0.25 | 0.286285 | 0.274947 | 0.717869 |
| 0.50 | 0.452973 | 0.446449 | 0.521008 |
| 0.75 | 0.622749 | 0.620086 | 0.325175 |
| 1.00 | 0.791983 | 0.793782 | 0.127336 |

支持的解释：

- clean prediction 与正确对应的 perturbed prediction 被逐渐替换为跨 clip prediction 后，
  action flip 上升、rationale Jaccard 下降；
- mean-three correspondence metric 能灵敏检测 pairing destruction；
- 五 seed 的结果高度一致。

但其近似线性响应在很大程度上来自 graded mixture/cycle construction。它证明的是
**sample correspondence sensitivity**，不是：

- brightness、blur、noise 的自然视觉 severity 标尺；
- rationale semantic faithfulness；
- 因果鲁棒性；
- 任意扰动下的安全性。

C1 必须继续命名为 correspondence metric，不能升级为 faithfulness metric。

---

## 5. 关键设计限制

### 5.1 单一 map/salt

Round 8 只使用一个 outcome-blind nested map 和一个冻结 salt。该 map 没有 outcome selection
证据，但当前 CI 条件于这一个 map。association-component bootstrap 只对该 map 导出的
component 和当前 observed population 做重采样，不能估计“换一个合法随机 map 后”的变异。

这是本轮最直接、最可修复的剩余内部有效性缺口。

### 5.2 五个训练 seed

五 seed 均通过是强于只报告均值的证据，但五个 seed 仍是较小的模型训练重复数。seed bootstrap
不能创造额外的真实训练重复，也不能把结果外推到未观察的 architecture、training recipe 或
foundation model。

### 5.3 1,625 个 association components

component closure 修复了 destination clip 与 source clip 的 dyadic dependence，明显优于按单端
destination clip 抽样。但：

- 1,625 是同一 BDD-OIA test population 上由单一 map 推导出的 component 数；
- 它们不是 1,625 个独立数据集；
- 它们不增加 town、weather、camera、institution 或真实世界域的覆盖；
- bootstrap inference 仍然是 observed-population 和 map conditional。

### 5.4 R 的零预测类别

六个恒零类说明 Macro-F1 的下降由可响应类别驱动。R 通过不应掩盖类别覆盖不足。后续论文必须
同时报告 per-class support、predicted-positive coverage 和恒零类，不得只给 macro curve。

### 5.5 没有外部复制

当前没有：

- 第二数据集；
- 第二种 ontology；
- 第二类模型/architecture；
- 真实车载域；
- 人类判断的 rationale grounding/faithfulness 标注。

所以 external validity 当前为 **未建立**，而不是“失败”；construct validity 当前为
**部分支持**，而不是“全面证明”。

---

## 6. RQ 层面的可接受结论

如果核心 RQ 是“ARSC 四轴指标是否能对其各自预定义的关联破坏作出有方向、分级且跨训练 seed
一致的响应”，Round 8 给出肯定证据。

如果 RQ 被扩大为“ARSC 四轴是否完整、普适且真实地测量 action correctness、rationale
faithfulness、safety calibration 与 causal robustness”，Round 8 不能回答。

推荐论文中的最强合规措辞：

> 在 BDD-OIA 的五个冻结训练 seed、一个 outcome-blind nested association map，以及
> association-component-cluster 条件推断下，A/R Macro-F1、S tie-averaged AURC 和 C1
> mean-three correspondence metrics 在五个预注册 destruction levels 上均通过严格的
> adjacent-step response gate。结果支持这些统计量的内部 graded responsiveness；不构成
> ontology completeness、rationale faithfulness、真实安全性或跨域外部有效性的证明。

---

## 7. 外部候选 VLA4CoDrive 的当前裁决

现有只读 repository metadata audit 已经对 VLA4CoDrive 给出预注册硬门：

- 数据公开、非 gated，license 为 Apache-2.0；
- 总存储约 117.25 GB；
- Action/Language window metadata 可访问；
- GitHub 与 Hugging Face 的 4,320 个 window JSON path 一致；
- 但只有 1 个 town；
- 只有 9 个 canonical scenes；
- 低于冻结的至少 2 towns、至少 150 canonical scenes；
- weather 与 filename 不一致 540 次；
- 小样本 probe 的 technical gate 虽通过，但 action semantics 与 rationale ontology 均未确认；
- 既有正式 decision 为 `STOP_EXTERNAL_TRAINING`。

因此本审阅：

- 不授权完整下载；
- 不授权训练；
- 不授权把该数据集作为主 external result；
- 不授权因结果不理想而放松 town/scene/ontology 门槛。

这不是本 memo 选择的下一步方向。

---

## 8. 唯一授权的下一步：BDD-OIA 多 map/salt 稳健性实验

### 8.1 为什么只做这一项

Round 8 已经充分解决了当前 BDD-OIA 内的：

- graded q response；
- 五训练 seed 一致性；
- association-component dependence；
- tie handling；
- formal/independent implementation consistency。

最明显的剩余内部缺口是单一 map/salt。VLA4CoDrive 已触发既定 STOP，继续在该候选上扩大下载
或训练既不合规，也不能提供可信外部复制。因此唯一有必要、范围最小且不会发散的下一步是：

> **Round 9：冻结 20 个 outcome-blind 合法 map/salt，检验 Round 8 四轴响应是否对 map
> realization 稳健。**

这是 map-robustness confirmation，不是新的 metric search，也不是 external validation。

### 8.2 预注册单位与冻结内容

在读取任何新 map 的 q>0 metric outcome 之前，必须冻结：

1. 20 个 map ID：`map00` 至 `map19`；
2. 20 个明确的 UTF-8 salt 字符串：
   `arsc-round9-map00` 至 `arsc-round9-map19`；
3. 与 Round 8 完全相同的 map builder 算法；
4. 与 Round 8 完全相同的样本、五个训练 seed、模型 cache、calibration、threshold；
5. q 固定为 `[0, 0.25, 0.50, 0.75, 1.00]`；
6. active image count 固定为 `[0, 1140, 2278, 3418, 4557]`；
7. A/R/S/C1 metric、direction、per-seed-first bottleneck 和 diagnostics；
8. 每个 map 独立导出的 association-component artifact；
9. 2,000 个 hierarchical bootstrap replicates；
10. 全部代码、测试、protocol、map、component、input 和 reviewer GO memo 哈希。

Round 8 map 不进入 Round 9 的 20-map primary gate；它只作为历史 reference 报告。

### 8.3 outcome-blind map 合法性硬门

20 个 map 必须全部满足：

- q=0 identity；
- 每个 q 是全局 source-index bijection；
- active sets 严格 nested；
- cycle 只可完整激活，不得 partial activation；
- active destination 与 source 不得 same filename；
- active destination 与 source 不得 same clip；
- q=1 无 fixed point；
- target row multiset、confidence multiset 和 perturbed-prediction multiset 保持；
- 每个 map 的 association components 对所有 q source-closed；
- restricted map 在每个 component 内仍为 bijection；
- map builder 不读取 target、prediction、logit、probability、confidence、error 或 metric outcome。

任一预固定 salt 生成的 map 不满足硬门，则本轮 **STOP**。不得丢弃该 salt 再补一个“更好”的
salt。

### 8.4 唯一 primary statistic 与 hierarchical bootstrap

对每个 axis、每个 map、每个 training seed：

1. 计算所有 required component 的五点 q curve；
2. 将 adjacent steps 转为 expected-direction change；
3. 在该 seed 内取全部 required steps 的 minimum，得到 map-specific seed bottleneck；
4. 对五个 seed 求均值，得到 map-specific mean bottleneck。

每个 bootstrap replicate 必须：

1. 有放回抽取 20 个 map IDs；
2. 有放回抽取 5 个 training seed IDs，并将同一 seed draw 用于所有抽中的 map；
3. 对每个抽中的 map，从该 map 自己的 association components 有放回抽取完整 component；
4. 同一 map occurrence 内，所有 seed、q、model、axis 和 perturbation 共用同一 component draw；
5. 在每个 map × seed 内先取 bottleneck，再依次对 seed 和 map 求均值；
6. 以 2,000 个 replicate 的 pointwise percentile 形成每轴 95% CI。

不允许先平均 q curves 再取 minimum，也不允许对不同 axis 使用不同 map subset。

### 8.5 GO/PASS 与 STOP/FAIL 阈值

每一轴必须同时满足：

1. 20 个 map-specific mean bottleneck 中至少 **18/20 > 0**；
2. 20-map grand mean bottleneck `> 0`；
3. hierarchical bootstrap pointwise 95% CI lower `> 0`；
4. 20-map × 5-seed grand mean component curves没有相邻方向 reversal；
5. 所有 20 个 map 的结果完整报告，不隐藏失败 map。

四轴全部满足才可报告 `ROUND9_FULL_PASS`。

出现以下任一情况，结论为 `ROUND9_FAIL_OR_INCONCLUSIVE`：

- 任一轴少于 18/20 map positive；
- 任一轴 CI lower `<= 0`；
- 任一轴 grand mean curve 出现 reversal；
- map、component、input 或 code hash 不匹配；
- 在 freeze 前读取新 map 的 q>0 outcome；
- formal run 后修改统计定义。

失败时必须如实保存并报告，不得追加 salt、追加 map、换 threshold、换 metric、换 gate 或挑选
passing subset 重跑。

### 8.6 允许与禁止

允许：

- 复用冻结 cache 和 prediction；
- outcome-blind 生成 20 个 map/component artifacts；
- 增加只针对多-map aggregation、closure 和 hierarchical resampling 的 synthetic tests；
- 运行一次 preflight 和一次 formal experiment；
- 运行一个不 import formal implementation 的独立 verifier；
- 报告全部 map-specific diagnostics。

禁止：

- 下载其他数据集；
- 重新训练；
- 新增模型；
- 改变五个训练 seed；
- 改 q grid、threshold、axis definition、tie convention 或 bottleneck；
- 根据 outcome 删除或替换 salt；
- 把 20 maps 当成 20 个外部数据集；
- 把多-map PASS 写成 external validity、faithfulness 或 safety validity。

### 8.7 停止规则与 HARKing 防护

- 样本量固定为 20 个新 map，不做 sequential peek；
- bootstrap 固定为 2,000 replicates；
- formal outcome 只运行一次；
- 若实现错误在结果写盘前由预注册 assertion 截停，必须像 Round 8 一样保留失败日志并独立审阅；
- 若任何 outcome 已暴露，不得修改 scientific protocol；
- 不因 20-map 结果通过而继续追加 map 追求更窄 CI；
- 不因结果失败而追加 map 追求 PASS；
- Round 9 完成后，BDD-OIA map-realization 问题视为终止，不再做同类 salt 迭代。

Round 9 即使通过，也只是把结论从“单一 outcome-blind map 条件响应”提升为“在 20 个预固定
outcome-blind map realizations 上稳健响应”。它仍不解决跨数据集、跨模型、ontology、grounding、
faithfulness 或真实驾驶安全。

---

## 9. 最终正式裁决

### 计算与形式层

**PASS / VALID**

- 7/7 independent audit PASS；
- formal 与 independent point estimate、raw bottleneck、curves、bootstrap 在浮点误差内一致；
- 四轴均为 5/5 seed positive；
- 四轴 CI lower 均严格大于 0；
- q=0 bridge、map/component closure、one-shared-draw 和 per-seed-first bottleneck 均通过；
- governance chain 完整，attempt01 failure 被正确留痕并在结果前受控修复。

### 科学、构念与外部层

**PARTIAL / BOUNDED INTERNAL EVIDENCE**

- 已建立：四轴对预定义 graded association destruction 的内部响应性；
- 未建立：R 的全类别有效性、rationale faithfulness、视觉 severity、causal robustness、
  calibration validity、真实安全性和 external validity；
- 推断仍受单一 map/salt、五训练 seed、同一 BDD-OIA population 和无外部复制限制。

### 下一步

**只授权 Round 9 BDD-OIA 20-map/salt 稳健性实验。**

VLA4CoDrive 当前保持 `STOP_EXTERNAL_TRAINING`。在 Round 9 完成前，不授权其他数据集、训练或
新的主结果方向。
