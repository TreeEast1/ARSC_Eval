# Round 10 formal attempt02 独立 postresult SCI 审阅

## 最终决定

**ACCEPT_ROUND10_PARTIAL_OR_FAIL_AS_VALID_FINAL_OUTCOME**

Round 10 attempt02 是一个完整、可重构、与预注册判据逐值一致的正式结果。正式 verdict `ROUND10_PARTIAL_OR_FAIL` 应按原样接受：12 个 family×axis 门控通过 3 个，三个通过项全部是 C1（brightness、blur、noise）；A、R、S 在三个 operator 上均未通过完整的五条件门控。

这不是实现失败或结果无效。相反，它是强预注册假设被部分支持、部分反证的有效最终结果。不得补跑模型、调阈值、改变 severity、删 family、挑 seed 或追加结果追随实验来“修复”3/12。

本次审阅允许读取正式 logits、primitives、bootstrap draws 与结果，但没有重跑模型、加载 checkpoint、改变任何原始产物/协议/代码、重拟合 calibration、调整阈值或选择子集。

## 1. 提交与完整性

- 保存提交：`d6ad61830fa8a54445d9bd9aa4687f9b325b9f8f`，tree `3c83e8931156e0cb08451cf7f3b6418264192b99`；审阅开始时 `HEAD == origin/main`。
- artifact index SHA256：`83E67C4F7F56F97769B7E0CDE0E8CECEEAD542358B994147AB3DE284F845DB5A`。
- index 中 10 个 final 文件加 formal log，共 11 项；11/11 SHA256 与字节数均已独立重算且精确匹配。
- final 目录恰好包含冻结合同规定的 10 个文件；result 内 9 个 pre-result 哈希全部是 FINAL 路径且逐文件匹配。
- log 只有一个退出标记 `EXIT_CODE=0`；attempt02 staging 不存在。
- result 绑定实现 commit `0c10e078a27d67816041aedd31b0c3273177e30d` 和 GO SHA256 `2D98F77990E444934B9376AC28758CC3A06C602E0E7F0972A58C52E3AF8F73B8`。
- 冻结实现先写完九个 pre-result 文件，最后写 result JSON，再以同卷 `os.replace(staging, final)` 原子重命名；result、index 和 staging 缺失状态相互印证该合同。
- attempt01 log、incident、incident reviewer decision 与 memo 的四个永久哈希仍精确匹配；attempt01 staging、final、index 仍不存在。

## 2. 五个 seed logits 与 primitives

五个 `seed_43`–`seed_47` archive 均为 `ARSC_ROUND10_SEED_LOGITS_V1`，字段集合完全一致：

- `file_names`: `(4557,)`；
- `action_targets`: `(4557,4)` float32；
- `rationale_targets`: `(4557,21)` float32；
- `action_only_logits`, `joint_action_logits`: `(3,5,4557,4)` float32；
- `joint_rationale_logits`: `(3,5,4557,21)` float32。

所有数值数组 finite，targets 为二值；五个 seed 的 filename order、action targets 和 rationale targets 逐位相同。每个 seed 的三个 family 在 level 0 上，三套 action-only、joint-action、joint-rationale logits 均逐位相同，符合“一次 clean inference 后跨 family 复制”的合同。

独立代码从 filename 重新生成 3,904 个 source-clip IDs/keys/sizes，从 raw logits、五组冻结温度、0.5 阈值重新生成 predictions/confidence/errors，并重新聚合 A/R/C1 clip primitives 与 S confidence tie groups。以下全部逐位相同：

- predictions、targets、confidence、errors、group IDs/counts；
- A 的 TP/FP/FN、R 的 TP/FP/FN；
- C1 action flip clip sums 与 rationale Jaccard clip sums；
- 四条 seed×family×component×level curves；
- 逐类 F1、target/predicted-positive counts 和八项 S diagnostics；
- 60 个 family-axis bottlenecks 与 120 个 endpoint effects。

采用冻结的 `einsum` 累加顺序后，`round10_corruption_point_diagnostics.csv` 的 3,975 行（600 primary curves、600 action-class、1,575 rationale-class、1,200 safety diagnostics）达到 0 mismatch。独立派生数组 reconstruction SHA256 为 `5E6845C6D5AE943B6A778CDD26D28A6A5B83991960777C69FB2EE334A5BDB926`。用直接 `sum` 的独立实现曾出现最大 `1.33e-15` 的加法顺序差异；改用冻结累加顺序后为精确零，不构成科学或实现差异。

因此 primitives 足以在不重新推理的情况下完整重构所有点估计、逐类计数和 S 诊断。

## 3. Bootstrap 与门控重构

`ARSC_ROUND10_BOOTSTRAP_DRAWS_V1` 的数组 shape、dtype、finite 与 range 均符合合同：

- gate draws `(5000,12)` float64；endpoint draws `(5000,24)` float64；
- seed selections `(5000,5)` uint8，范围 0–4；
- clip selections `(5000,3904)` uint16，范围 0–3903；
- expanded counts `(5000,)` int32，范围 4,473–4,647。

从空 RNG 状态独立运行 `numpy.random.default_rng(20260810)`，按冻结调用顺序生成全部 5,000 组 seed 和 clip selections，逐位 mismatch 均为 0；全部 5,000 个 expanded counts 也为 0 mismatch。前三个 replicate 使用同一 seed/clip draw 从 clip primitives 重新计算全部 12 gate draws 与 24 endpoint draws，逐位 mismatch 为 0，验证了 shared-draw 合同。

selection/draw 数组审计哈希：

- seed selections：`D4F9BA46BADFB0585798D1929DB0E7293AA8E64519A11CCB07310886FA10FEFB`
- clip selections：`295B04588E51E8723C57BEF94C27F1034999DA842202572DE2045DD0BE0DFD36`
- expanded counts：`150F0B7CB591721D1385BDDB5C18BE3FBFED3AC7E6889B47B5F103343E59ED18`
- 12 gate draws：`D3BB47501D1D6AD1FD229B2EFC83E1CD78F13BDF1B992CCED9C417D088938DD1`
- 24 endpoint draws：`FF002713762B50AF5DB872DDBD61F1B50F22A1DC5B320CFB6E3F380E022BCEA2`

独立重算 12 个 gate input vectors 的 2.5%、97.5%、1/240 quantiles，以及 24 个 endpoint input vectors 的 2.5%、97.5% quantiles，共 84 个 `method="linear"` 数值，0 mismatch；所有 quantile input hashes 也为 0 mismatch。seed-positive counts、五 seed 均值、grand-mean no-reversal、24 个 practical threshold comparisons、全部五条件布尔值、3/12 和 `all_twelve=false` 均与 result 相同。bootstrap summary 36 行为 0 mismatch。

## 4. 十二个 family×axis 门控

五个条件依次为：①至少 4/5 seed bottleneck 严格为正；②五 seed 均值严格为正；③Bonferroni lower 严格为正；④grand-mean component curves 无反转；⑤该轴所有 practical endpoints 通过。

| Family | Axis | 正 seed | mean bottleneck | Bonferroni lower | ① | ② | ③ | ④ | ⑤ | Gate |
|---|---:|---:|---:|---:|:---:|:---:|:---:|:---:|:---:|:---:|
| brightness | A | 0 | -0.002446 | -0.006327 | ✗ | ✗ | ✗ | ✗ | ✗ | FAIL |
| brightness | R | 2 | -0.000367 | -0.002990 | ✗ | ✗ | ✗ | ✗ | ✗ | FAIL |
| brightness | S | 0 | -0.003572 | -0.009939 | ✗ | ✗ | ✗ | ✗ | ✗ | FAIL |
| brightness | C1 | 5 | 0.024167 | 0.017411 | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| blur | A | 0 | -0.001337 | -0.004892 | ✗ | ✗ | ✗ | ✗ | ✓ | FAIL |
| blur | R | 1 | -0.000504 | -0.002173 | ✗ | ✗ | ✗ | ✗ | ✗ | FAIL |
| blur | S | 0 | -0.004632 | -0.013750 | ✗ | ✗ | ✗ | ✗ | ✗ | FAIL |
| blur | C1 | 5 | 0.031688 | 0.024812 | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| noise | A | 0 | -0.002174 | -0.005194 | ✗ | ✗ | ✗ | ✗ | ✗ | FAIL |
| noise | R | 2 | -0.000287 | -0.002238 | ✗ | ✗ | ✗ | ✓ | ✗ | FAIL |
| noise | S | 0 | -0.007420 | -0.013780 | ✗ | ✗ | ✗ | ✗ | ✗ | FAIL |
| noise | C1 | 5 | 0.024354 | 0.017204 | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |

失败原因不是单一的统计功效不足。A/R/S 的 seed bottleneck 数、均值和 Bonferroni lower 均失败；除 noise-R 外，grand-mean curve 也有至少一次反转。blur-A 的两个 practical endpoints 虽然都通过，但严格逐级单调与 bootstrap criteria 失败；noise-R 虽无 grand-mean 反转，但效应大小、seed consistency 和 uncertainty criteria 均失败。

## 5. 二十四个 practical endpoints

| Family | Component | 五 seed mean effect | Threshold | Pass |
|---|---|---:|---:|:---:|
| brightness | A::action_only | 0.003186 | 0.010 | ✗ |
| brightness | A::joint | 0.001751 | 0.010 | ✗ |
| brightness | R::joint_rationale | 0.004391 | 0.010 | ✗ |
| brightness | S::action_only | 0.005789 | 0.010 | ✗ |
| brightness | S::joint | 0.003624 | 0.010 | ✗ |
| brightness | C1::action_only_flip | 0.193241 | 0.025 | ✓ |
| brightness | C1::joint_flip | 0.170770 | 0.025 | ✓ |
| brightness | C1::joint_rationale_jaccard | 0.145944 | 0.025 | ✓ |
| blur | A::action_only | 0.014165 | 0.010 | ✓ |
| blur | A::joint | 0.012241 | 0.010 | ✓ |
| blur | R::joint_rationale | 0.005900 | 0.010 | ✗ |
| blur | S::action_only | 0.005615 | 0.010 | ✗ |
| blur | S::joint | 0.002127 | 0.010 | ✗ |
| blur | C1::action_only_flip | 0.265043 | 0.025 | ✓ |
| blur | C1::joint_flip | 0.232390 | 0.025 | ✓ |
| blur | C1::joint_rationale_jaccard | 0.224183 | 0.025 | ✓ |
| noise | A::action_only | 0.013365 | 0.010 | ✓ |
| noise | A::joint | -0.000646 | 0.010 | ✗ |
| noise | R::joint_rationale | 0.004911 | 0.010 | ✗ |
| noise | S::action_only | -0.006718 | 0.010 | ✗ |
| noise | S::joint | -0.006556 | 0.010 | ✗ |
| noise | C1::action_only_flip | 0.196884 | 0.025 | ✓ |
| noise | C1::joint_flip | 0.160325 | 0.025 | ✓ |
| noise | C1::joint_rationale_jaccard | 0.142494 | 0.025 | ✓ |

## 6. 对四指标有效性与 RQ 的解释

本实验同时回答了计算有效性和一个严格、条件化的 construct-response 问题：

- **C1：得到最强且跨 operator 的支持。** 三类 corruption 的全部五条件门控与 9/9 practical endpoints 均通过。随着冻结 severity 增加，动作翻转率上升、理由集合 Jaccard 下降，说明 C1 能稳定追踪输出不一致性。它证明的是扰动敏感性，不是模型更安全、理由更忠实或 C1 具有因果含义。
- **A：只有 endpoint 层面的局部支持，没有普遍 dose-response 支持。** blur 的 action-only/joint、noise 的 action-only endpoint 达到 0.01，但三类 A gate 全失败，说明终点性能变化并不形成跨 seed、逐相邻级别稳定的单调曲线。
- **R：当前网格下反应弱。** 三个 R endpoints 均低于 0.01，三个 R gates 全失败；noise-R 的 grand mean 虽无反转，仍缺少 seed consistency、正均值 lower bound 和 practical magnitude。当前证据不支持 R 在这些 operator/severity 下是灵敏的 dose-response 指标。
- **S：当前网格下未显示预期的选择性风险退化。** 三个 S gates 全失败；brightness/blur 的效应低于 0.01，noise 甚至为负。冻结 tie-averaged AURC 的计算本身已完全重构，因此这是科学上的不敏感/反向响应结果，不是实现错误。

对 RQ 最稳妥的回答是：**ARSC 四轴确实提供可分离的诊断信息；在 BDD-OIA 五 seed 和三种冻结合成像素 corruption 下，C1 对 severity 呈稳定且有实际幅度的跨 operator 响应，而 A 仅有部分终点敏感性，R 与 S 未获得预注册的普遍单调 dose-response 支持。**

`PARTIAL_OR_FAIL` 不能等同于“ARSC 全局无效”，也不能被改写为“所有四指标均有效”。它支持“多轴分解揭示单一准确率会遗漏的行为”，同时反证“四轴都会在所有这些 corruption 上稳定单调响应”的强版本。

## 7. 下一步是否需要新实验

**接受 Round 10 本身不需要任何补实验或重跑。** 若研究目标只是在冻结 BDD-OIA synthetic grid 上报告这个预注册检验，当前证据已经完整。

若要主张外部有效性或自然道路条件下的合理性，则需要一个新的、结果独立预注册的外部验证，而不是对 Round 10 做结果追随式迭代。最有信息量的有界方向是：

1. 在查看模型输出前固定一个独立驾驶数据 population、一个由元数据/物理定义而非当前结果选择的自然或真实采集 severity axis，以及唯一的 label crosswalk；
2. 预先冻结样本、四动作与 21 理由标注/适用性审计、五 seed、calibration、threshold、四轴定义、12-gate 规则和 one-shot stopping；
3. 保留 A/R/S/C1 全部轴，不因本轮 C1 通过而只验证 C1，也不因 A/R/S 失败而选择更强 corruption；
4. 若外部数据没有兼容理由标签，只能声明为 A/S/C1 或 S/C1 的部分外部验证，不能包装成完整 ARSC 外部验证。

该新研究是外部主张的必要条件，但不是当前结论成立的必要条件。

## 8. Claim boundaries 与文档措辞

结果仅适用于冻结的 BDD-OIA 4,557-image population、3,904 source clips、五个历史 ResNet-50 seeds、固定 validation temperatures/0.5 thresholds、brightness/blur/noise 三套合成 pixel grids 和预注册 seed/source-clip bootstrap。

它不支持自然 corruption prevalence/severity、跨数据集外部有效性、真实道路鲁棒性或安全保证、rationale grounding/faithfulness、因果证据，亦不验证 0.01/0.025 是外部最小重要差异。

README/report 应与最终审阅对齐并至少采用如下措辞：

> Round 10 是完整且可重构的预注册 partial/fail 结果：12 个严格 family×axis 门控通过 3 个，且全部属于 C1。三类冻结合成像素 corruption 下，C1 获得跨 operator 的单调与实际幅度支持；A 仅出现部分 endpoint 敏感性，R 与 S 未获得普遍单调 dose-response 支持。这说明四轴能区分不同模型行为，但不证明 ARSC 全局有效或无效，也不支持安全、因果、理由忠实性或外部有效性主张。

若现有 README/report 已准确包含 3/12、C1-only、A/R/S 边界和 synthetic/internal 限定，则不需要更改数值结论；仍应加入 postresult reviewer decision/memo 与 index 哈希作为最终证据入口。术语“真实像素扰动”应明确写成“对原图实际重推理的**合成**像素扰动”，避免被误解为自然道路 corruption。
