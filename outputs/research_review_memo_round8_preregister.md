# Round 8 严格结果前预注册审查

## 审查边界

本审查只读取：

- `outputs/validity/round8_graded_response_protocol.json`  
  SHA256 `B96AC789BA12DD0FE65AF2138C54248C2154C1E1489D911571422EDE94B65357`
- `outputs/validity/round8_graded_association_map_manifest.json`  
  SHA256 `73B89C3438262BA272E0E90EDC2A6F9408B196CCBD4A30D9FA6FFFA798C273DC`
- `outputs/validity/round8_graded_association_maps.npz`  
  SHA256 `8685E1A4605B5D6355A432BC6CA03CF61930BAB23D41D899478A5C1D8FC47ED1`
- 上述 manifest 明确绑定的 outcome-blind map builder/core/test。

我没有搜索、打开、运行或推导任何 q-response metric outcome，没有读取 target、logit、probability、prediction 或 confidence outcome 来预演方向，也没有修改 protocol、map 或代码。

## 裁决

**GO_WITH_AMENDMENT**

map、q grid、salt、输入与四轴 graded definition 均可冻结保留；tie-averaged AURC 与 bottleneck hypothesis 也具有明确科学含义。

但在正式 outcome 前必须只有一份 **Round 8 Amendment 01**，修复 seed × shared-clip bootstrap 遗留的 source-clip/dyadic clustering，并消除两个实现自由度：

1. tie-averaged AURC 与 Round 7 stable-tie AURC 的 q=0 reproduction 边界；
2. bootstrap replicate 内 bottleneck 的精确计算顺序。

在该 amendment 被哈希冻结、实现 synthetic tests 通过并再次做纯合规确认以前，**不得计算正式 q-response outcome**。

## 1. Outcome-blind map 审计

### 1.1 Provenance

- protocol、map manifest、map NPZ 的三个指定 SHA256 均匹配。
- builder 只读取 seed-43 cache 的 `test_file_names`。
- map manifest 不包含 targets、logits、probabilities 或 metric outcomes。
- construction commit `b24b91ec4a85ef03f77b3bef95ea4f9a9b5dd6f9` 中 builder/core/test 的文件 SHA256 与 manifest 三项记录全部匹配。

因此没有发现用 outcome 选择 salt、cycle、q 或 map 的证据。

### 1.2 Cycle partition 与 q 嵌套

独立从 NPZ 复核：

- 2,277 个 pair cycle 加一个 3-cycle，精确且不重复地覆盖索引 `0..4556`；
- pair 的两个成员均来自不同 clip，3-cycle 的三个成员也来自三个不同 clip；
- q=0、0.25、0.50、0.75、1.00 的 active image 数分别为  
  `0, 1140, 2278, 3418, 4557`；
- 每个 q 都是全局 source-index bijection；
- 每个 q 都没有 partial pair cycle；
- final triplet 仅在 q=1 激活；
- active set 严格嵌套，四个相邻增量分别为  
  `1140, 1138, 1140, 1139` 张图像；
- 每个 active mapping 都为 0 same-filename、0 same-clip；
- 五个 source array 的独立 SHA256 均与 protocol/manifest 一致。

这是一套 **clip-safe 的 image-level complete-cycle map**，而不是 whole-clip activation map。protocol 使用“被破坏样本比例”而非“被破坏 clip 比例”，因此该定义本身没有冲突。

### 1.3 多重集合保持

每个 q 的 map 都是全局置换，所以以下结论是精确的：

- action/rationale target row multiset 和逐类正例数保持；
- S confidence-value multiset 保持；
- C1 perturbed-prediction row multiset 保持；
- q=0 是 identity，q=1 为 0 fixed-point 的完整跨-clip mapping。

这里保持的是完整 4,557-image population 的 multiset。现行按 destination clip 抽样的 bootstrap replicate 不一定对 source map 闭合；这正是下面需要 amendment 的原因。

## 2. 四轴 graded definitions

### A

固定 clean action prediction，只把 scoring target 换成 `action_targets[source_map_q]`。这隔离了 sample-target association，并因全局 bijection 保持 target prevalence。两个模型的 Macro-F1 作为 gate component，定义清晰。

### R

与 A 同构，在 21-label rationale target 上评估 Joint prediction。Macro-F1 是 gate；Micro-F1、per-class F1 和 coverage 为必须报告的诊断。该设计不会自动保证下降，因此是可证伪的。

必须保持边界：R gate 只检验 Macro-F1 曲线，不等于 21 个类别都严格单调。

### S

predictions、exact-set errors 和 confidence values 全部不变，只改变 confidence value 与 sample/error 的关联：

`confidence_q[i] = original_confidence[source_map_q[i]]`

因此 S 检验的是 AURC 对逐步破坏 confidence-error association 的响应，不是重新校准，也不是改变模型 prediction。

### C1

clean prediction `i` 与 perturbed prediction `source_map_q[i]` 比较。q=0 为 correct pairing，q=1 为完全跨-clip pairing。mean-three action flip 预期上升，mean-three rationale Jaccard 预期下降。

它检验 sample correspondence destruction，不检验 brightness/blur/noise 的视觉 severity。单项 perturbation 只报告、不进入正式 gate。

四轴共用同一 outcome-blind nested map，有利于控制分析自由度；没有必要更换 map、salt、q 或 axis definition。

## 3. Tie-averaged AURC

### 3.1 数学合理性

protocol 的 tie rule：

> 在每个 equal-confidence block 内，对所有可能内部排列的 cumulative risk 取精确期望。

对于一个起始前已有 `E` 个累计错误、长度 `m`、含 `e` 个错误的 tie block，第 `k` 个 block 内位置的期望累计错误为：

`E + k * e / m`

将其除以全局 coverage position 并对所有位置求平均，正好得到所有 tie permutations 的期望 AURC。该规则：

- 不改变 score、error 或跨不同 score block 的次序；
- 无 tie 时与 canonical AURC 完全相同；
- 有 tie 时消除 filename/input order 作为隐含 tiebreak；
- 对所有 q、seed、model 一致使用，且在 outcome 前冻结。

因此它是 ARSC AURC 的合理 tie convention refinement，不是更换 S 构念或事后选择新 metric。

### 3.2 与 Round 7 的边界

Round 7 使用 canonical stable-tie AURC；Round 8 primary 使用 tie-averaged AURC。两者在存在 tie 时不要求数值相等。

所以 protocol 当前这条 exact stop：

> q=0 exactly reproduces Round 7 original A/R/S and correct-pair C1 point estimates

对 S primary 存在歧义，若解释为 tie-averaged AURC 必须等于 Round 7 stable-tie AURC，则是不可满足的。

Amendment 01 必须明确：

- q=0 的 A/R 与 correct-pair C1 point estimates 精确复现 Round 7；
- S 的 predictions、errors、confidence values 精确复现；
- Round 8 的 secondary canonical-stable AURC、UAR@90、correctness AUROC、ECE 在 q=0 精确复现 Round 7；
- tie-averaged AURC 是 Round 8 新冻结的 primary tie convention，只需通过独立 closed-form/brute-force synthetic audit，不得强制等于 Round 7 stable-tie 数值。

ECE 继续禁止进入 monotonic gate 或方向 claim；现有边界正确。

## 4. Bottleneck adjacent-step statistic

### 4.1 是否过严

该统计量是所有 required component curves、全部四个相邻 q-step 的最小 expected-direction change：

- A：8 个 step 的最小值；
- R：4 个 step 的最小值；
- S：8 个 step 的最小值；
- C1：12 个 step 的最小值。

它确实很严格。一个 seed 只要有一个 component 的一个相邻 step 持平或反向，该 seed statistic 就不为正。但这与本轮问题“是否在每一个相邻 severity step 都单调”完全一致。

它不是构造性必过：

- map 嵌套只保证激活集合嵌套，不保证 A/R Macro-F1 或 S AURC 单调；
- C1 的相邻 step 是新激活 cycle 的经验贡献，也不保证每一批 cycle 都有正确方向；
- R 的 zero-response classes 会降低 power，但不会机械地产生正结果。

因此不得因为它低 power 而放松成 endpoint slope、Spearman trend 或“多数 step 正”。若失败，只能解释为严格 adjacent-step monotonicity 未获支持，不能换统计量重跑。

### 4.2 复算顺序必须冻结

“bootstrap bottleneck”至少有两种不等价实现：先对 seed 求均值再取 min，或先在每个 seed 内取 min 再对 seed 求均值。当前 gate 文本使用“raw seed statistic”及“五-seed mean”，应唯一固定为后者。

Amendment 01 必须规定每个 replicate：

1. 生成一份 shared cluster image-index vector；
2. 对每个被抽中的 seed，重新计算该轴所有 q curve points；
3. 在该 seed 内计算所有 adjacent steps，并取 minimum，得到一个 seed bottleneck；
4. 对抽中的五个 seed bottleneck 求均值，作为 replicate statistic；
5. 对 2,000 个 replicate statistics 取 95% percentile CI。

完整样本的 raw seed statistic 使用同一顺序。另行检查的“五-seed mean component curves 无相邻反转”应从五个 seed 的 q-wise component mean 计算，不替代 bottleneck，也不生成新的选择性 gate。

## 5. Seed × shared-clip bootstrap 的 source-cluster 问题

### 5.1 现行设计解决了什么

它正确地：

- 抽训练 seed；
- 每 replicate 只抽一份 shared destination-clip multiset；
- clip 被抽中时保留其全部帧；
- 对所有 seed、q、model、axis、perturbation 使用同一 image vector。

这修复了 Round 7 的 frame-within-clip 相关性，也避免 seed × image 伪重复。

### 5.2 仍遗漏什么

q>0 时单个 metric primitive 同时依赖两个 cluster：

- destination/clean clip：`clip(i)`；
- source/target/confidence/perturbed clip：`clip(source_map_q[i])`。

map 是 image-level cross-clip cycle，不是 whole-clip cycle。独立 map 审计显示：

- q=1 时 **0/3904** 个 destination clip 对 source map 自闭合；
- 613 个多帧 source clip 的帧被分散到 2 或 3 个不同 destination clip；
- 只按 destination clip 抽样不会把共享同一 source clip 的所有 dyadic observations 共同重采样。

因此现行 bootstrap 仍可能低估 source-clip 引起的协方差。这个问题同时影响 A、R、S 和 C1，不是某一轴的特例。

### 5.3 唯一允许的修复

不要改 map。用冻结 q=1 map 构造 outcome-blind association graph：

- node：3,904 个 clip group；
- edge：对每个 image `i`，连接  
  `clip(i)` 与 `clip(q1_source_map[i])`；
- bootstrap cluster：该无向图的 connected component。

由于所有较低 q 的 edge 都是 q=1 edge 的子集，每个 q 的 source 都留在同一 connected component 内。当前冻结 map 唯一导出：

- **1,625 个 association components**；
- component clip-count histogram：  
  `{2:1191, 3:291, 4:101, 5:22, 6:7, 7:11, 8:2}`；
- 最大 8 个 clips、14 张 images；
- 每个 component 内，对每个 q 的 restricted source map 仍为 bijection。

Amendment 01 必须把 bootstrap 改为：

1. 有放回抽五个训练 seed；
2. 有放回抽 1,625 个 association-component indices；
3. 每次抽中 component 时包含其中所有 clips 的全部 images，并保留 component multiplicity；
4. 把同一 resulting image-index vector 用于所有 seed、q、model、axis、perturbation；
5. seed 仍为 `20260803`，replicates 仍为 `2000`，percentile 95% CI 不变。

应在 outcome 前生成只依赖 frozen clip IDs 和 q=1 map 的 component-ID artifact/hash，并 exact audit：

- 1,625-component partition；
- histogram 与 maximum size；
- 每个 q 的 source closure；
- 每个 q、每个 component 的 restricted bijection；
- replicate 只有一份 shared component draw；
- repeated component 保留完整成员与 multiplicity。

这不是换 map、q、salt、输入或 hypothesis，只是把 inference unit 从单端 clip 修正为 dyadic association component。

## 6. 四轴 gate 与 multiplicity

当前 gate 可以保留：

- 每轴五-seed mean bottleneck `> 0`；
- 至少 4/5 raw seed bottleneck `> 0`；
- 修订后的 seed × shared-association-component bootstrap pointwise 95% CI lower `> 0`；
- 五-seed mean component curves 无相邻方向反转；
- full pass 要求四轴全部通过。

统计解释：

- minimum statistic 是轴内的 union-intersection gate；要求它大于 0 等价于所有 required adjacent steps 同方向，不需要对轴内 4/8/12 个 step 再做挑选式显著性检验；
- full-suite claim 要求四轴全部通过，不允许把 passing subset 政名为全套 PASS；
- 四个轴 CI 仍是 pointwise，不是 simultaneous familywise 95% intervals；
- 若分别发表某一轴的显著性，必须说明未做四轴 simultaneous coverage；若只声称“四轴全部通过冻结 gate”，intersection gate 不产生挑选 passing axis 的问题。

不得新增 q-pairwise CI、换成 endpoint、挑选单个 model/perturbation 或在失败后改 gate。

## 7. Claim 边界

通过后允许的最强表述：

> 在 BDD-OIA 五个冻结训练 seed、一个 outcome-blind nested association map 与 association-component-cluster 条件推断下，A/R Macro-F1、S tie-averaged AURC 和 C1 mean-three correspondence metrics 在五个预注册 association-destruction 水平上满足严格 adjacent-step monotonic response gate。

必须明确不支持：

- construct、ontology、grounding、faithfulness、causal 或真实安全有效性；
- visual perturbation severity；
- R 的 21 个 per-class curves 都单调；
- A/R Micro-F1 单调；
- C1 每个 individual perturbation 都单调；
- S 的 UAR@90、AUROC 或 ECE 单调；
- 其他 map、salt、threshold、模型、训练协议、数据集或真实驾驶；
- simultaneous 95% familywise coverage。

claim 中的 `clip-cluster-conditional` 应在 amendment 后改为更准确的 `association-component-cluster-conditional`。

## 8. 唯一 Amendment 01 的范围

只允许一份 outcome-blind Amendment 01，且必须同时、唯一地完成：

1. 用冻结 q=1 map 导出的 1,625 个 association components 替代 destination-clip bootstrap unit；
2. 明确 bootstrap replicate 内“每 seed 先取 bottleneck，再对五个 selected seeds 求均值”的顺序；
3. 拆分 q=0 的 Round 7 stable-tie reproduction 与 Round 8 tie-averaged primary；
4. 增加 Macro/mean-three gate 与非 gated diagnostics/per-class claims 的边界；
5. 冻结 component artifact、最终 analysis code/tests、implementation manifest 和 reviewer memo 哈希。

明确禁止：

- 改 q grid、active counts、cycle order、pair/triplet、salt 或 source arrays；
- 改 cache、calibration、threshold、seed 或 model；
- 改 tie-averaged AURC、bottleneck statistic、axis components、4/5 rule、CI level 或 2,000 replicates；
- 读取任何 q-response outcome 后再修订；
- 维护 destination-clip 与 association-component 两套 inferential analyses并择优汇报。

## 最终决定

**GO_WITH_AMENDMENT**

map 与科学问题可以继续。正式 outcome 计算的唯一前置条件是上述 Amendment 01 全部冻结并通过独立合规确认。若 amendment 缺少 association-component bootstrap、q=0 S bridge 或 bottleneck 计算顺序中的任一项，则裁决自动转为 **STOP**。
