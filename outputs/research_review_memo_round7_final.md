# Round 7 结果后独立科学审阅

## 审阅边界

- 审阅对象：BDD-OIA 五个冻结训练 seed 的 ARSC axis falsification one-shot。
- 正式结果：
  - `arsc_axis_falsification_results.json`  
    SHA256 `E0A1802EC426989B2F46FE5DED8F554A0CCAA63CFA5D1011A5F46808A56775EA`
  - `arsc_axis_falsification_point_estimates.csv`  
    SHA256 `E105F0D46980F2C3BF405D25D24D0A9B107B5085D0C73A840035A1D1C101DEAD`
  - `arsc_axis_falsification_bootstrap.csv`  
    SHA256 `06E56093815ABC28A7A6572E7D0E62475B23AB6A3ACF232171E93ACE180E84D0`
  - `arsc_axis_falsification_primitives.npz`  
    SHA256 `D832D136D482377EF013853CC8772A792EEC6EADE20FED627082BF72D2F4E2B7`
  - `tmux_arsc_axis_falsification.log`  
    SHA256 `5B2A9D551927F0E40B10A7224707D93F12AD6EC43EDB6618A446BFF09526D4A9`
- 我没有重跑 intervention、训练、推理或替换任何 control；只从冻结 primitives 做了只读独立复算。

## 总体裁决

**PARTIAL**

这里需要明确区分两个层面：

1. **冻结 protocol 的执行与全部正式 gate：PASS。**
2. **把本轮提升为“四个指标已经获得充分、一般性的科学有效性证明”：PARTIAL。**

第二层不能给 PASS 的原因不是结果弱或实现失败，而是本轮主要验证的是极端破坏下的内部敏感性和判别行为；同时，正式 image bootstrap 没有把同一视频 clip 内的帧作为 cluster。它足以支持有边界的内部 sanity/discriminant 结论，但还不足以支持构念、剂量响应、外部数据或真实安全有效性。

## 1. Artifact、exact audit 与独立复算

### 1.1 完整性

- 用户给出的五个正式 artifact SHA256 均与当前文件逐字节一致。
- immutable run manifest 中的 protocol、amendment、两份预审 memo、三份实现文件、五个 seed 的 cache/calibration/Round 5 reference 以及 preflight 共 **28/28** 个当前路径哈希一致。
- preflight 为 **83/83 PASS**，无失败项。
- Round 5 五个 seed 的 point estimates 和 aggregate mean/SD 均被 exact reproduction gate 覆盖。

### 1.2 结果文件互相一致

- point CSV 共 485 行，485 个唯一 `(seed, axis, model, control, metric)` 键，无非有限值；**485/485** 与结果 JSON 精确相等。
- bootstrap CSV 共 10 行；**10/10** 与结果 JSON 的 mean、SD、positive-seed count、CI 和 gate 精确相等。
- 从 primitives 独立复算五个 seed 的全部对比，最大绝对差为 **0.0**。
- 用 frozen seed `20260802` 独立复现 2,000 次 bootstrap 后，10 个对比的 mean、SD、positive-seed count 和 percentile CI 最大绝对差仍为 **0.0**。

因此没有发现结果搬运、CSV/JSON 分叉、结果后换 map、换 threshold 或换 bootstrap 的证据。

## 2. Crossed bootstrap 是否落实 amendment

**落实。**

每个 replicate 的实现顺序是：

1. 有放回抽取五个训练 seed；
2. 仅生成一份长度 4,557 的 canonical image multiset；
3. 对所有被抽中的 seed、model、control 和 contrast 使用同一份 image multiset；
4. 同一 seed 被重复抽中时，复用同一 frozen output 和同一 image multiset。

这正确避免了把“同一测试图像在五个训练 seed 下的五次预测”误当成五组独立图像。tmux 日志的 20 个进度节点也都记录 `shared_image_draw_per_replicate = 1`。

## 3. 正式 gates

所有正式方向 gate 都是 5/5 seed 为正，五 seed 均值为正，crossed-bootstrap 95% percentile CI 下界大于 0：

| 对比 | 五-seed 均值 | 95% CI | 正 seed |
|---|---:|---:|---:|
| A original − combined，Action-Only | 0.312962 | [0.299901, 0.326291] | 5/5 |
| A original − combined，Joint | 0.320033 | [0.305871, 0.335337] | 5/5 |
| R original − combined，Joint | 0.230389 | [0.213473, 0.247698] | 5/5 |
| S random AURC − original，Action-Only | 0.137671 | [0.119137, 0.156320] | 5/5 |
| S random AURC − original，Joint | 0.146539 | [0.128628, 0.165799] | 5/5 |
| C1 action wrong − correct，Action-Only | 0.669739 | [0.657245, 0.682235] | 5/5 |
| C1 action wrong − correct，Joint | 0.688713 | [0.675792, 0.700564] | 5/5 |
| C1 rationale correct − wrong，Joint | 0.782538 | [0.771974, 0.792558] | 5/5 |
| S adversarial AURC − oracle，Action-Only | 0.692018 | [0.690522, 0.692825] | 5/5 |
| S adversarial AURC − oracle，Joint | 0.692389 | [0.691325, 0.692871] | 5/5 |

另外，十个 `(seed, model)` 的 S ordering 均满足：

`oracle <= original/random <= adversarial`，且 `adversarial > oracle`。

因此：

- `full_suite_measurement_pass = true`：正确；
- `full_empirical_battery_pass = true`：正确；
- 两者的语义已按 amendment 分开，没有把 original-versus-random 偷塞进 measurement-validity gate。

## 4. A/R：intermediate controls 与 per-class 反例检查

### 4.1 支持结果

- A 的 row-only、class-only、combined 在两个 model、五个 seed 下都低于 original。
- R 的三个 destruction control 在五个 seed 下都低于 original。
- prevalence-preserving 的 row-only 已经产生稳定下降：
  - A：10 个 seed-model 单元的平均下降 0.311433，范围 `[0.294789, 0.333232]`；
  - R：五个 seed 的平均下降 0.197302，范围 `[0.178256, 0.221247]`。
- 独立检查还发现 target row map 为 0 个同文件、0 个同 clip 配对。
- A 的四个 class 在两个 model、五个 seed 下，original 相对 combined 都严格更高。
- R 的任一 per-class F1 都没有出现 destruction 高于 original 的方向反转。

这些结果说明主方向不是单由 combined control 的列 prevalence 变化造成；row-only control 已提供更干净的“样本—目标关联被破坏”证据。

### 4.2 必须保留的构造性限制

1. **combined 并不呈现“破坏越多、分数越低”的单调性。**  
   在全部 15 个 A/R seed-model 单元中，class-only 的 Macro-F1 都低于 combined。故不能把 combined 解释为比 row-only 或 class-only 更强的连续 severity，也不能声称已经观察到 dose-response。

2. **R 不是 21 类都提供了经验响应。**  
   `car`、`person`、`left_lane`、`left_follow`、`no_left_lane`、`left_solid_line` 六类在五个 seed 中均为 original F1 = destroyed F1 = 0；原因是模型在这些类没有正预测，而不是 target 无支持。`other_obstacle`、`left_green_light` 和 `left_obstacle` 也只在部分 seed 给出非零响应。

3. 因而 R 的 macro 方向证据真实存在，但不能改写成“21 个 rationale 类均验证有效”或“每一类都能感知关联破坏”。

## 5. S：measurement ordering 与 model-confidence informativeness

拆分是正确的。

### 5.1 Measurement-ordering

五 seed 平均 AURC：

| Model | Oracle | Original | Frozen random | Adversarial |
|---|---:|---:|---:|---:|
| Action-Only | 0.169258 | 0.388824 | 0.526495 | 0.861276 |
| Joint | 0.161004 | 0.372227 | 0.518766 | 0.853393 |

oracle/adversarial 是利用已知 error 构造出的极端排序，所以它们验证的是“AURC 实现能否响应已知排序”，不是独立的模型安全证据。该 gate 通过，但其角色应保持 implementation/measurement sanity check。

### 5.2 Frozen model confidence

original 的 max-action-probability 排序相对一份冻结 random 排序，在两个 model 上均为 5/5 seed 更低 AURC，且 CI 下界大于 0。允许的最强解释只是：

> 在这五个 seed 和这一份预注册 random reference 下，original confidence 对 exact-set correctness 的排序更有信息。

不能推及“优于随机排序分布”“已经校准良好”或“可作为安全保证”。

### 5.3 ECE 边界

结果文件正确地把 synthetic-ordering ECE 标为 numeric diagnostic，没有用它做方向 gate。这个边界非常必要：random ECE 的五-seed 均值反而低于 original：

- Action-Only：random 0.253448，original 0.324007；
- Joint：random 0.257486，original 0.324461。

这不是 random 排序更安全，而是 ECE 同时依赖 score 数值和 correctness，不是纯排序指标。任何“synthetic ECE 越低越好”的方向解释都应禁止。

### 5.4 Tie 实现风险

original confidence 有大量重复值；每个 seed-model 的 `N - unique(score)` 为 1,727–2,145。AURC 当前对同分样本使用 canonical input order 作为 stable tiebreak，而不是 tie-averaged AURC。

独立做同分块的 best/worst 排序边界后，完整样本 AURC 的最大摆幅为 0.000400，远小于最小的 random-minus-original 对比 0.124101，因此不改变本轮 gate。不过发表时应披露 deterministic stable-tie convention；下一版实现宜预注册 tie-averaged AURC 或唯一 tiebreak。

## 6. C1 巨大 wrong-pair 差异的有界解释

五 seed 均值：

- Action-Only action flip：correct 0.1185，wrong 0.7883；
- Joint action flip：correct 0.1024，wrong 0.7911；
- Joint rationale Jaccard：correct 0.9160，wrong 0.1335。

wrong map 是 bijection、0 fixed point、0 same-file、0 same-clip，并对所有 seed/model/perturbation 共用。因此巨大差异不是由重复抽样或偷偷选择不同 wrong map 造成。

但 wrong pairing 把当前 clean image 与另一无关 image 的 perturbed prediction 配对，本质上是极端 sample-correspondence destruction。它把 identity/content/prediction-set 差异同时引入，故只支持：

> C1 能区分正确配对与这一份冻结的、完全破坏的跨样本配对。

它不支持：

- wrong pairing 是更强的 brightness/blur/noise；
- C1 已验证 perturbation severity；
- C1 已验证语义、因果或真实世界一致性；
- 0.67–0.78 的差异可直接解释成模型 robustness 大小。

## 7. 伪重复、过度 claim 与实现风险

### 7.1 伪重复

- **没有发现 seed × image 的伪重复。** shared-image crossed bootstrap 正确处理了五个 seed 共用同一测试集。
- **仍有 clip-level cluster 风险。** 4,557 张图像按已冻结的 `_1/_3` clip 规则只对应 3,904 个 clip group；573 个 group 含 2 张图，40 个含 3 张图，共 1,266 张图像位于非 singleton group。正式 bootstrap 以 image 而不是 clip 为单位，所以其 CI 对 clip 内相关性是条件性的，可能偏窄。
- 五个训练 seed 仍然很少。5/5 同方向很有价值，但不能被表述为对任意训练随机性的充分总体推断。
- 十个 95% CI 是 pointwise intervals，不是 multiplicity-adjusted simultaneous intervals。由于 contrasts 全部预注册且全部通过，没有选择性汇报问题；但不能声称“联合 95% 覆盖”。

### 7.2 过度 claim

正式 JSON 自带的 `interpretation_boundaries` 是合规的，未发现 artifact 内部过度 claim。风险主要在后续论文表述：若省略“severe frozen destruction”“one fixed random reference”“one wrong map”“BDD-OIA five seeds”，就会超出证据。

### 7.3 实现与 provenance 风险

- 当前代码哈希与 pre-outcome manifest 一致，当前正式输出互相一致，没有发现会推翻结果的实现错误。
- one-shot existence guard 位于 `run_preflight()` 之后；误重跑会先重写 preflight/manifest，再因 result 已存在而停止。当前哈希链未显示结果污染，但未来应把 guard 前移。
- result JSON 内部绑定了 primitives 哈希，却没有绑定 point CSV、bootstrap CSV 和 tmux log 哈希。发表前的顶层 artifact index 应把这三项及本 memo 一并哈希固定。

## 8. 可发表的最强结论

> 在 BDD-OIA 固定的 4,557 张测试图像、五个冻结训练 seed、预注册映射与阈值下，ARSC 的 A/R Macro-F1 对严重的样本—目标关联破坏呈稳定下降，C1 action-flip/rationale-Jaccard 能稳定区分正确配对与一份完全破坏的跨样本配对；S 的 AURC 对 oracle/adversarial 排序按定义响应，并且冻结的 max-action-probability 排序在两个模型上均优于一份预注册 random reference。所有方向在 5/5 seed 一致，正式 crossed-bootstrap pointwise 95% CI 下界均大于 0。

这是一项强的 **BDD-OIA 内部敏感性、实现正确性与极端判别 control 证据**。

## 9. 不可声称

- 四个指标已经获得一般性的 construct validity、grounding、faithfulness 或 correctness 证明；
- R 的 21 个类别都已经验证；
- A/R/C1 对干预 severity 单调，或可定量比较 severity；
- S 已校准、可保证安全，或 original 优于“随机排序分布”；
- synthetic ECE 有任何统一方向含义；
- C1 wrong-pair 差异是模型对 brightness/blur/noise 的 robustness；
- 结论可外推到 CEG、其他数据集、其他架构、其他阈值、真实驾驶或因果效应；
- 当前十个 pointwise CI 是联合 95% 区间；
- image-level CI 已完整处理视频 clip 内相关性。

## 10. 唯一有意义且不发散的下一实验

**Round 8：同一 BDD-OIA frozen cache 上的预注册“分级关联破坏响应曲线”，并使用 seed × shared-clip crossed bootstrap。**

本轮先不要换数据集，也不要重新训练。唯一问题是：四个轴是否不仅能区分两个极端端点，而且会随着预先定义的关联破坏比例稳定、单调地响应。

建议只冻结一个统一 severity grid，例如 `q = {0, 0.25, 0.50, 0.75, 1.00}`：

- A/R：在 q 比例的预冻结样本子集内做 prevalence-preserving row derangement，其余样本保持 identity；
- S：保留 predictions/errors/confidence values，只在 q 比例样本上逐步打乱 confidence-to-sample association；主分析仍只用 AURC，不给 synthetic ECE 方向；
- C1：q 比例样本使用冻结 wrong pairing，其余保持 correct pairing；
- 所有轴共用预冻结的 clip 分组和 map，禁止看结果后换 map；
- bootstrap 每个 replicate 抽五个 seed，并只抽一份 shared clip multiset，再把入选 clip 的全部帧用于所有 seed/condition；
- 每个轴只预注册一个单调趋势统计量及一个 gate，避免对 q 的所有两两比较扩散；
- R 必须保留全部 21 类的 per-class/positive-prediction coverage，不得只汇报有响应的类；
- 在 outcome 前生成 protocol、实现哈希、synthetic unit tests 和独立 GO memo。

该实验直接修复本轮最重要的两个缺口：**只有极端端点**与**未按 clip 聚类的 inference**。只有它通过后，再把同一冻结协议原样迁移到第二数据集，才是有价值的外部 replication；现在直接找更多数据集只会复制尚未解决的内部构念问题。

## 最终决定

**Round 7 正式 one-shot：protocol PASS；独立科学总评：PARTIAL。**

结果应保留、可进入论文的内部有效性章节，但必须使用上述有界表述。下一轮只做 Round 8 分级响应曲线，不再并行扩展 CEG、训练、阈值、模型或数据集。
