# Round 6 独立最终审阅：BDD100K-train v5 Metadata Gate

日期：2026-07-31  
审阅性质：冻结 analyzer 的一次性结果事后审阅；不重跑、不重算 candidate pool 或 hashes  
最终裁决：**正式结束 CEG mainline；RQ2-CEG 保持 UNANSWERED**

## 1. 冻结结果与工程缺陷

冻结 artifacts：

- metadata gate JSON  
  SHA256 `33DE06F02F5ED44C3BC8B371D5F02D625FA60B1A983339831DBF55C7FD15943B`
- candidate JSONL  
  SHA256 `85CCE62DED3B77BE1FB65651241EB32B25ABA57945AD29CEB8D3F8659089361F`
- frozen run log  
  SHA256 `D5107C37B97068F3E404BBCA889EDE39975055E45060DDD59511A3C1D85DD9FD`
- process exit：0

机器输出的冻结 decision 是：

```text
STOP_CEG_INDEPENDENCE
```

直接原因是 `missing_required_image_file_count=19961`。Analyzer 默认：

```text
data/raw/lastframe/<file_name>
```

而训练与评价实际图像根为：

```text
data/raw/lastframe/data/<file_name>
```

所以本次没有有效完成 image SHA256 independence gate。JSON 中：

- filename overlap = 0；
- clip-group overlap = 0；
- candidate hash overlap = 0；
- within-pool duplicate hash = 0；

其中前两项是实际集合检查结果；后两项的 0 不能解释为 hash independence 通过，因为大量图像根本没有被读到。正确说法是 **hash independence 未评估成功**，不是“已证明无 hash overlap”。

## 2. Root-path 修复能否改变 population 结论

不能。

Analyzer 的执行顺序是：

1. 读取冻结 manifests；
2. 只保留 keyframes；
3. 保留单一 red/green rationale；
4. 做 filename 与 clip-group exclusions；
5. 用 train-only official rows 做 traffic-light state matching；
6. 形成 `proposed_candidates`；
7. 之后才按 `image_root` 读取并 hash 图像。

因此 root path 只影响第 7 步：

- missing image；
- image hash overlap；
- within-pool duplicate hash；
- gate 1。

它不会新增 official annotation row、改变 rationale state、增加 state-matched proposal 或增加 clip group。

冻结的 pre-hash flow 是：

- BDD-OIA test：4,557；
- keyframes：2,233；
- single red/green rationale：1,138；
- exact filename excluded：237；
- clip group excluded：451；
- eligible after name/group exclusion：450；
- no train annotation row：129；
- state mismatch：red 128、green 106；
- proposed state-matched：87；
- red：50；
- green：37；
- proposed clip groups：87。

预注册 population gate：

- total ≥200；
- red ≥50；
- green ≥50；
- independent clip groups ≥30。

即使假设正确根目录下所有 87 个 proposals 均通过 hash independence：

- total 87 < 200；
- green 37 < 50。

后续 hash 检查只能保持 87 或使 gate 失败，不能把 87 增加到 200，也不能把 green 37 增加到 50。因此 87/50/37/87 是 population gate 的确定上界。

## 3. 正式 GO/STOP 判断

### 机器 gate

保持原记录：

```text
STOP_CEG_INDEPENDENCE
```

因为 frozen run 的 hash gate 由于错误路径没有完成。

### 科学 gate

追加独立审阅结论：

```text
STOP_CEG_POPULATION_NO_V6
```

原因不是把未执行的 `population_gate.evaluated=false` 改写成机器 PASS/FAIL，而是利用冻结代码的单调执行关系作逻辑判断：

```text
maximum possible post-hash candidate count <= pre-hash proposed count
```

pre-hash 上界已经低于 total 与 green 两项门槛。

所以不批准 root-path amendment 或第二次 analyzer run。修正路径只会得到一个更完整的 independence 诊断，却不可能改变最终 STOP；在已经看到 population flow 后再 rerun 也不再是原来的一次性结果前 gate。

## 4. 能声称什么

可以声称：

1. train-only official annotation metadata 与冻结 BDD-OIA evaluation population 的一次性交集已运行。
2. 在 filename/clip-group exclusions 与 official state matching 后，得到 87 个 **pre-hash proposed** samples：red 50、green 37、87 groups。
3. 该 pre-hash 上界不足以通过预注册 200/50/50/30 population gate。
4. 图像根配置错误使 hash independence 没有被有效确认。
5. 无论修正 image root 与否，population gate 均不可能通过。
6. 按 no-v6/no-horizontal-hunt 规则，BDD-OIA CEG mainline 正式结束。
7. Round 5 的 A/R/S/C1 五种子结论保持不变；RQ2-light 仍为 supported。

## 5. 不能声称什么

不能声称：

1. 87 个 proposals 已构成独立、可用于确认性 CEG 的 candidate pool。
2. hash overlap 或 duplicate hash 已证明为 0。
3. gate 1 若修复就一定通过。
4. red 50 / green 37 可以通过降低门槛、合并 validation、恢复旧 audit 文件或加入 temporal neighbors 补足。
5. 87 个 proposals 可以作为“探索性 v5”继续读取模型输出。
6. RQ2-light 可以替代 CEG 或证明 rationale supervision 使用了正确证据。
7. CEG mainline 的失败否定 A/R/S/C1 指标或五种子 RQ1。
8. v4、BDD100K validation、VLA4CoDrive 与本次失败后仍应继续寻找 v6 或另一数据集。

## 6. 对现有 artifacts 的处理

应保留：

- 原 gate JSON、candidate JSONL、log 及其 SHA256；
- 错误 `image_root` 的事实说明；
- 本独立审阅给出的“population 上界不可能过门”推理。

不应：

- 修改 frozen gate JSON 的原 machine decision；
- 重写 candidate manifest；
- 修正 root 后覆盖原结果；
- 对 87 个 proposals 生成 masks；
- 读取五种子在这些 proposals 上的 logits；
- 把这 87 个样本转成 v6 development pool。

## 7. 唯一下一项 ARSC-validity 实验

**五种子冻结 prediction caches 上的 ARSC 轴选择性干预 falsification suite。**

这是唯一推荐的下一实验。它：

- 不使用新数据；
- 不生成 mask；
- 不重训；
- 不寻找新数据集；
- 不尝试回答已关闭的 CEG；
- 直接检验 A/R/S/C1 作为测量轴是否对预期干预敏感、对无关干预保持不变。

### 7.1 研究问题

> 在固定 seeds 43–47 的已冻结 predictions 上，对 label relation、confidence ordering 和 clean/perturbed pairing 施加具有已知作用方向的离线干预时，A/R/S/C1 是否表现出预期的敏感性与轴间区分性？

### 7.2 固定干预

1. **A control**  
   固定 action logits，使用预注册 permutation 对 action target rows 或 class mapping 作破坏；Action Macro-F1 应明显下降。perfect-target control 必须为 1。

2. **R control**  
   固定 Joint rationale logits，对 rationale target rows/ontology columns 使用预注册 permutation；Rationale Macro-F1 应下降。perfect-target control 必须为 1。

3. **S control**  
   固定 thresholded action predictions 与 exact-set correctness，只改变用于 risk ranking 的 confidence：
   - oracle ordering；
   - original ordering；
   - fixed random permutations；
   - adversarial/reversed ordering。

   A 必须逐样本完全不变；AURC 应按预注册方向响应。该干预检验 S 是否测量排序信息而不只是重复 A。

4. **C1 control**  
   固定 clean 与三扰动 predictions：
   - identity self-pairing；
   - 正确 filename pairing；
   - 使用固定 permutation 的错误 filename pairing。

   identity 必须得到 action flip=0、rationale Jaccard=1；错误 pairing 应比正确 pairing 更不一致。clean A/R/S 必须不变。

### 7.3 GO gates

1. **Frozen input gate**  
   在任何新结果前冻结 seeds 43–47 cache hashes、sample order、threshold=0.5、permutation seeds/maps 与全部期望方向；禁止重新推理或训练。

2. **No-selection gate**  
   只允许一个预注册 control suite；不得看结果后更换 permutation、confidence control、阈值或 practical margin。

3. **Exact invariants gate**  
   perfect A/R=1；identity C1 flip=0/Jaccard=1；confidence-only intervention 下 action predictions 与 A 完全不变；pairing-only intervention 下 clean A/R/S 完全不变。任一失败即对应 metric implementation STOP。

4. **Hierarchical inference gate**  
   保持 seed、image、model、perturbation 配对，使用与 Round 5 一致的层级 bootstrap；报告 5 个 seed 原值，不能只池化图像。

5. **Bounded-claim gate**  
   该 suite 只验证 measurement sensitivity/discriminant behavior。无论通过与否，都不得恢复 CEG、宣称 causal faithfulness 或外部效度；失败时报告对应 ARSC axis 未通过 falsification，不调参救结果。

## 8. 最终结论

**CEG mainline：STOP，正式结束。**

工程上，frozen run 因错误 image root 未完成 hash independence；科学上，pre-hash population 上界 87、green 上界 37 已使 200/50/50/30 不可能通过。没有合理理由再做 root 修复、v6 或横向数据集搜索。

**唯一下一实验：五种子 frozen-cache ARSC 轴选择性干预 falsification。**

它是对现有 A/R/S/C1 度量有效性的内部反证测试，不是 CEG 替代品。
