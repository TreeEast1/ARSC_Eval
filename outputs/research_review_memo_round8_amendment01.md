# Round 8 Amendment 01 第二次 outcome-blind 合规审查

## 审查边界

本次只读取并核验了：

- 原 protocol：`outputs/validity/round8_graded_response_protocol.json`  
  SHA256 `B96AC789BA12DD0FE65AF2138C54248C2154C1E1489D911571422EDE94B65357`
- 第一次预注册审查：`outputs/research_review_memo_round8_preregister.md`  
  SHA256 `83C13D1112ABAF9CBA6504E26BBB0BDBBDD99C5D7A45DB27A840D0A695B65BF2`
- Amendment 01：`outputs/validity/round8_graded_response_protocol_amendment01.json`  
  SHA256 `D15E6F93FFEF686172F3887BAB609E6DA724ECE975BB125485A717688A020C8A`
- 冻结 association map、map manifest；
- 冻结 association-component NPZ、component manifest；
- component manifest 绑定的 builder、core、synthetic tests 与对应 commit。

我没有读取、运行或推导任何 q-response metric outcome，没有读取 target、logit、probability、prediction 或 confidence metric result，也没有查看未冻结的 `src/arsc_eval/graded_response.py` 或 `tests/test_graded_response.py`。未修改任何 protocol、map、component artifact 或代码。

## 结论

**GO**

Amendment 01 精确落实第一次审查要求的四类实质修订：

1. association-component bootstrap；
2. per-seed-first bottleneck 顺序；
3. q=0 stable-tie / tie-averaged bridge；
4. gated Macro/mean-three 与 diagnostics 的 claim 边界。

它没有更改 q、map、salt、input、metric、axis component 或 gate。新增的 component artifact 能从冻结 q=1 map 与 clip IDs 唯一复算，现有 outcome-blind component implementation 和 tests 足以作为正式分析实现的基础。

这个 GO 是对 Amendment 01 的合规批准。正式 q-response outcome 仍必须等待 Amendment 中已规定的 final analysis code/tests、one-shot script、pre-outcome implementation manifest 和 exact preflight 全部冻结并通过；这些是既有 GO 后硬前置条件，不构成新的 amendment。

## 1. Amendment 授权范围

### 1.1 唯一新增内容

Amendment 的 `amendment_01_changes` 只有：

- `association_component_bootstrap`
- `bootstrap_bottleneck_order`
- `q0_reproduction_boundary`
- `gate_and_claim_boundary`

另有 `implementation_freeze_before_formal_outcome`，只把上述修订转化为正式运行前的代码、测试、哈希和 preflight 条件，不新增科学 hypothesis。

这与第一次 memo 要求一一对应，没有加入新的 model、dataset、perturbation、threshold、q、map ensemble、alternative statistic 或 competing bootstrap。

### 1.2 明确保持不变

Amendment 明文禁止改变：

- q grid 与 active counts；
- pair/triplet cycle、cycle order、salt、source arrays；
- cache、calibration、threshold、五个 training seeds、model、perturbation、input population；
- tie-averaged AURC；
- within-axis minimum adjacent-step bottleneck；
- axis components、4-of-5 rule；
- 2,000 replicates、bootstrap seed `20260803`、95% percentile CI；
- 失败后换 endpoint slope、rank trend、q pair、model、perturbation 或 relaxed gate。

同时禁止保留 destination-clip bootstrap 作为竞争分析。因而不存在两套 inference 择优报告的自由度。

## 2. Component artifact 的唯一复算

### 2.1 冻结绑定

- map manifest SHA256：  
  `73B89C3438262BA272E0E90EDC2A6F9408B196CCBD4A30D9FA6FFFA798C273DC`
- map NPZ SHA256：  
  `8685E1A4605B5D6355A432BC6CA03CF61930BAB23D41D899478A5C1D8FC47ED1`
- component manifest SHA256：  
  `7E5EA6AB9E83A0CCE03FDBBBAC274AB01D1B7773CA43833348C77ED71127653F`
- component NPZ SHA256：  
  `F1DF45A526EEBE02C2CDA6EA2FB1FE8B034A3FDD3B1582B3598B602916CDD0E8`

component builder 只读取 map NPZ 中：

- `clip_group_ids`
- 五个冻结 q source maps

component graph 只用 `clip_group_ids` 与 q=1 source map；不读取 filename 以外的新输入，更不读取 targets 或任何模型量。

### 2.2 独立图复算

我没有调用 component builder 来生成正式 artifact，而是独立构造无向图：

- 3,904 个 clip nodes；
- 对每个 image `i` 加边  
  `clip(i) -- clip(q1_source[i])`；
- connected components 按其最小 clip ID 排序并连续编号。

独立结果与冻结 component NPZ 的六个数组逐元素完全一致：

- `component_id_by_clip`
- `component_id_by_image`
- `component_clip_offsets`
- `component_clip_ids`
- `component_image_offsets`
- `component_image_indices`

六个独立数组 SHA256 也全部与 component manifest 一致。

因此 component artifact 是冻结 map 的唯一确定函数，不存在额外 salt、随机种子、outcome 或手工选择。

### 2.3 精确 partition

独立复算得到：

- component count：**1,625**
- clip count：3,904
- image count：4,557
- clip-count histogram：  
  `{2:1191, 3:291, 4:101, 5:22, 6:7, 7:11, 8:2}`
- image-count histogram：  
  `{2:1191, 4:291, 6:101, 8:22, 10:7, 12:11, 13:1, 14:1}`
- maximum clips/component：8
- maximum images/component：14
- minimum clips/component：2
- minimum images/component：2

所有 3,904 clips 和 4,557 images 都恰好属于一个 component，无遗漏或重复。

### 2.4 五个 q 的 closure 与 restricted bijection

对 q=0、0.25、0.50、0.75、1.00 分别独立验证：

- global source map 是 4,557-index bijection；
- `component_id[source[i]] == component_id[i]` 对每张图成立；
- 每个 component 内的 source map restricted range 精确等于该 component 自身的 image-index set。

五个 q 均为：

- source closure：PASS
- restricted bijection：PASS

这保证 repeated component draw 中，每个 q 的 destination/source dyads 都留在被抽中的完整 component 内，且 target/confidence/perturbed-row multiset 在该 component 内保持。

## 3. Shared component bootstrap contract

绑定 core 的行为是：

1. 抽 `seed_count` 个 seed indices；
2. 只抽一份长度 1,625 的 component-index multiset；
3. 按每个 selected component 的冻结 packed slice 展开全部 image members；
4. component 重复出现时，完整 slice 按出现次数重复拼接；
5. 返回单一 `shared_images` vector，供正式分析的所有 seed、q、model、axis 和 perturbation 共用。

独立 outcome-blind 检查确认：

- component draw shape 为 `(1625,)`；
- `shared_images` 与对同一 component draw 独立调用 `expand_component_draw` 完全相等；
- 显式 draw `[component 0, component 1, component 0]` 得到  
  `[members(0), members(1), members(0)]`，完整成员和 multiplicity 均保持；
- 因 component 大小不同，每个 replicate 的 image 数允许变化；这属于标准完整 cluster resampling，不是丢失成员。

绑定的四个 component synthetic tests全部通过：

- deterministic dyadic closure；
- packed/repeated draw complete membership；
- one shared component draw；
- invalid non-bijection rejection。

这足以作为 component construction/bootstrap primitive 的 outcome 前基础。

## 4. Per-seed-first bottleneck 顺序

Amendment 已唯一规定 full-sample raw statistic：

> 每个 seed 内先计算所有 required q curves 和 expected-direction adjacent steps，再取该 seed 的 minimum。

也唯一规定每个 bootstrap replicate：

1. 构造一份 shared association-component image vector；
2. 对每个 selected seed 在该 vector 上重算所有 q curve points；
3. 在该 seed 内计算 adjacent steps 并取 minimum；
4. 对五个 selected seed bottlenecks 求均值，得到 replicate statistic。

这排除了以下不等价实现：

- 先对 seed 平均 curve，再取 min；
- 先对 step 做 bootstrap summary，再取 min；
- 对 component/model/step 选择性取最有利结果。

五-seed mean component curve 的 no-reversal check 被明确列为独立 deterministic check，不替代 bottleneck，也不生成新的可选 statistic。

因此顺序合规。正式 analysis tests 必须在 outcome 前用 synthetic curves 证明该顺序；Amendment 已将其列为 preflight 强制项。

## 5. q=0 stable/tie split

Amendment 已消除原 protocol 的歧义：

- A/R 与 correct-pair C1：q=0 必须逐 seed exact reproduce Round 7；
- S primitives：q=0 predictions、exact-set errors、confidence values 必须 exact reproduce；
- S Round 7 bridge：secondary canonical-stable AURC、UAR@90、correctness AUROC、ECE 必须 exact reproduce；
- S Round 8 primary：tie-averaged AURC 是新冻结 tie convention，通过独立 closed-form/brute-force synthetic tests，但有 confidence tie 时不要求等于 Round 7 stable-tie AURC。

这既保留 Round 7 provenance bridge，也没有把 tie-averaged primary 换回结果依赖的 stable order。ECE 继续是非方向 diagnostics，不进入 gate。

正式 analysis code 尚未冻结并不影响 Amendment 合规；在计算 outcome 前，preflight 必须实际完成上述 exact checks。

## 6. Gated component 与 claim 边界

Amendment 清楚冻结：

- A gate：两个 model 的 four-label Macro-F1；
- R gate：Joint 的 21-label Macro-F1；
- S gate：两个 model 的 tie-averaged AURC；
- C1 gate：两个 action mean-three flip 加一个 rationale mean-three Jaccard；
- full suite：四轴全部通过。

同时明确以下仅为 diagnostics：

- A/R Micro-F1 与 per-class curves；
- R coverage；
- S stable AURC、UAR@90、correctness AUROC、ECE、decile diagnostics；
- C1 individual perturbation curves。

允许的 claim 已改为 `association-component-cluster-conditional`，且明文禁止推及：

- A/R Micro-F1；
- 每个 R class；
- 每个 C1 perturbation；
- S diagnostics；
- construct、grounding、faithfulness、causal、安全、其他数据集/模型/阈值；
- simultaneous familywise 95% coverage。

四个 axis intervals 仍是 pointwise；没有新增 multiple-testing claim，也不允许 passing subset 冒充 full pass。

## 7. Outcome-blind implementation 与正式运行前条件

### 7.1 当前已冻结基础

component implementation 当前 SHA256 与 manifest 全部一致：

- builder：`D674C5A1A2B46F8025ED7BAF1D9735BA19273C2A0B132ED22C1D3D27D915DE63`
- core：`F8AA90F0756032ADCB283D111E5B29F03C9D93D96ABDA383E8F9E737B57CE6B5`
- tests：`918ABF1D6BC8EBB54F3872474AD484729E7F374DFDD4DA04C4F3F85ECFADF214`

三者与 commit  
`0f2673f1d4b2ea3bb32a2e7d5faea23dcc9e9861`  
中的文件内容也逐字节一致。

component implementation 对 partition、closure、restricted bijection、complete membership、multiplicity 与 single shared draw 提供了充分的结果前基础。

### 7.2 GO 后的强制前置条件

本审查没有查看尚未冻结的 formal analysis implementation。Amendment 已正确规定在正式 outcome 前必须：

1. 完成并冻结 final analysis core 与 synthetic tests；
2. 完成并冻结 formal one-shot script；
3. 生成 pre-outcome implementation/input hash manifest；
4. preflight 逐项绑定 protocol、Amendment、本 GO memo、map、component、code/tests、cache/calibration、Round 7 reference；
5. synthetic tests 覆盖 tie-averaged closed form、per-seed-first bottleneck、one shared component vector 和 q=0 split；
6. exact preflight 全部 PASS 后才允许一次正式 outcome run。

这些条件已经包含在 Amendment，不允许再另立 Amendment 02，也不允许在 outcome 后补做。

## 最终决定

**GO**

Round 8 Amendment 01 严格处于授权范围内；component artifact 可唯一复算，bootstrap primitive 正确保留 association component 的完整成员与 multiplicity，bottleneck 顺序、q=0 tie bridge 和 claim 边界均已唯一冻结。

正式 q-response outcome 当前仍未获立即执行许可；只有 Amendment 已列出的 final implementation freeze 与 exact preflight 全部完成并通过后，one-shot 才获许可。任何 hash、component、closure、shared-draw、bottleneck-order 或 q=0 split 失败均为 **STOP**，不得换 map、q、metric、gate 或 bootstrap。
