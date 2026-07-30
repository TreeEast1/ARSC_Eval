# Round 8 formal attempt01 独立失败审查

## 审查边界

本审查只读取：

- 冻结 Round 8 protocol；
- 冻结 Amendment 01；
- Amendment 01 outcome-blind GO memo；
- 已提交的 preflight 与 run manifest；
- `outputs/validity/round8_graded_response_formal_attempt01_failed.log`；
- 当前已提交的 `scripts/analyze_round8_graded_response.py`；
- 当前已提交的 `src/arsc_eval/graded_response.py`。

我没有读取或推导任何 q-response metric outcome，没有读取 results、point CSV、bootstrap CSV 或 primitives，也没有读取 target、logit、probability、prediction 或 confidence 数值。

## 裁决

**GO_RERUN**

允许且只允许实施已提出的唯一最小修复，完成提交、重新冻结和独立 preflight 后，启动一次 formal attempt02。

这属于 **outcome-sealed implementation correction**，不是 Amendment 02，也不是科学 protocol 变更。理由是：

1. attempt01 由预先存在的 exact consistency assertion 自动 STOP；
2. failure log 只暴露断言名称，没有暴露任何 q curve、方向、bottleneck、CI 或 gate；
3. `point_outcomes()` 未返回，正式 point CSV、primitives、bootstrap CSV 与 results 的写入均尚未开始；
4. C1 两条路径在实数算术中定义完全相同，只因浮点归约顺序不同而可能产生约 `1e-16` 的 bit-level 差异；
5. 修复方向由 Round 7 point convention 与冻结 q=0 exact reproduction 唯一决定，不需要也不允许参考 outcome；
6. preflight/manifest 的变化只有 pytest wall-clock timing，不影响任何科学 check。

## 1. 冻结对象与失败证据

### 1.1 治理链

- protocol SHA256：  
  `B96AC789BA12DD0FE65AF2138C54248C2154C1E1489D911571422EDE94B65357`
- Amendment 01 SHA256：  
  `D15E6F93FFEF686172F3887BAB609E6DA724ECE975BB125485A717688A020C8A`
- Amendment 01 GO memo SHA256：  
  `CBF47293F5D983772C305B53E7C1DACD056D1609C7BA4F0A3B284BFAEEC9B66A`
- attempt01 failed log SHA256：  
  `E3D3D58FF47663F7031AA85963D3AA81702BA4CA21F35C60DA77DEEA10E95296`

failed log 的唯一异常为：

`RuntimeError: C1 action point/curve implementation mismatch`

没有打印任何 metric value。

### 1.2 attempt01 使用的已提交实现

已提交 run manifest 绑定：

- analysis script SHA256：  
  `68AD821605D807F3A00ABBDBC386B6208FC1EFED9DB2691F99318494C247CE23`
- graded-response core SHA256：  
  `598CA3FC8EFEA920310E60F1B91149C2F98CCCAE7649B0466E91340492DC8A71`
- implementation last commit：  
  `e0ab35121baa4bf1bbb5cc9b88e24f1e510c8f8d`

当前 script/core 仍与该 manifest 哈希一致；未发现 attempt01 后对正式实现做未提交试探性修改。

## 2. STOP 是否发生在正式结果写入前

formal `main()` 的顺序是：

1. 重复运行 preflight；
2. 检查正式 result 不存在；
3. 调用 `point_outcomes()`；
4. `point_outcomes()` 成功返回后才写 point CSV；
5. 随后才写 primitives、运行 bootstrap、写 bootstrap CSV 和最终 results。

attempt01 在 `point_outcomes()` 内部的 C1 action exact assertion 抛出异常，函数没有返回。因此：

- point CSV 未进入写入；
- primitives 未进入写入；
- bootstrap 未启动；
- bootstrap CSV 未进入写入；
- results JSON 未进入写入。

需要诚实区分：程序进入了 `point_outcomes()`，所以内存中已瞬时计算部分 curves；但这些数值没有被日志披露、没有被持久化，也没有用于选择修复方向。治理意义上，这是 outcome-sealed 的实现失败，而不是已查看结果后的分析重设计。

## 3. C1 mismatch 的技术性质

令 `x[p, i]` 为 perturbation `p`、sample `i` 的 action-flip 或 rationale-Jaccard primitive，三个 perturbation 数为 3，sample 数为 `n`。

### point/detail 路径

当前 `c1_point_detail()` 先对每个 perturbation 求 sample mean，再求三者 mean：

`(1/3) * Σ_p [(1/n) * Σ_i x[p,i]]`

### curve 路径

当前 `graded_axis_curves()` 先对每个 sample 求三 perturbation mean，再求 sample mean：

`(1/n) * Σ_i [(1/3) * Σ_p x[p,i]]`

两式在实数算术中严格相等，使用相同：

- sample；
- q source map；
- clean/perturbed prediction；
- threshold；
- action-flip / rationale-Jaccard primitive；
- mean-three metric。

NumPy 浮点归约的加法顺序不同，可导致最后一位出现约 `1e-16` 差异。当前 assertion 使用严格 `!=`，所以会把纯舍入差异视为 implementation mismatch。

这不是：

- metric definition 差异；
- q、map 或样本差异；
- threshold 或 prediction 差异；
- gate 或方向差异；
- 结果不符合 hypothesis。

## 4. 唯一允许的 C1 修复

允许修改 `graded_axis_curves()` 中 action 与 rationale 两个 C1 mean-three 路径，使其都采用：

1. 每个 perturbation 的 per-sample primitive；
2. 对 selected samples 求该 perturbation 的 scalar mean；
3. 对 brightness、blur、noise 三个 scalar means 求 mean-three。

这与：

- `c1_point_detail()`；
- Round 7 point convention；
- q=0 exact reproduction boundary

完全一致。

必须同时覆盖 action 与 rationale，避免 action 修复后在下一个 strict assertion 被同类 rationale 舍入差异再次中止。

不得采用以下替代方案：

- 给 strict assertion 加 tolerance；
- 删除 assertion；
- 只修触发失败的某个 seed、q、model 或 action 分支；
- 改用不同 metric、dtype、threshold、source map 或样本；
- 查看具体 curve 后选择更有利的归约路径。

修复后 exact equality assertion 应保留。统一归约顺序后，它继续承担 bit-level implementation consistency gate。

## 5. Preflight timing 非确定性

已提交 preflight：

- SHA256  
  `C706717B1C4C44FEEE95848CDAFB63E17C7D1A4D30F0E42741CD9878B46A01EE`
- status：PASS
- checks：86/86
- pytest stdout 尾部：`15 passed in 0.13s`

attempt01 重复 preflight 后，working-tree preflight：

- SHA256  
  `4F00BA1AA34E552FCF877921E8089333BA30BCBD6E35CD7BAA1536A377E28618`
- status：PASS
- checks：86/86
- 唯一内容差异：`15 passed in 0.15s`

run manifest 的唯一差异是引用的 preflight SHA 从已提交值变为新值：

- committed run manifest SHA256：  
  `8E4386C55CB5B25A1566171AEDC93B78006B78000685FE9ACCA6C5C4DF18D0B9`
- attempt01 后 working-tree run manifest SHA256：  
  `6238C0FDA3006A4E986608C9D884121432E41B4DD2BD13A0B6372CB1891DC11A`

因此 preflight 不具备 byte stability 的原因已唯一定位为 wall-clock timing，而不是 input、code、check 或 outcome 变化。

## 6. 唯一允许的 preflight 修复

synthetic-test detail 不得再持久化 pytest 的易变 wall-clock duration。

允许：

- 只记录 return code、固定 suite identity/hash 和确定性 pass summary；
- 或对 stdout 做唯一固定的 duration normalization。

优先采用前者，因为它没有依赖 pytest 文本格式的正则自由度。失败时仍应让 preflight STOP；完整原始 stdout/stderr 可以只写入独立失败日志，不进入 immutable audit hash。

修复后必须：

1. 在同一 code/input state 连续运行 preflight-only 两次；
2. 两次 preflight JSON SHA256 完全相同；
3. 两次 run manifest SHA256 完全相同；
4. 两次均为 86/86 PASS；
5. synthetic suite 的新增 regression test 被确定性 summary 覆盖。

## 7. 必须新增的 synthetic regression

只新增与此次失败直接对应的 outcome-blind synthetic regression：

- 对 action 的两个 model，验证 curve mean-three 与 point/detail 的“先 perturbation scalar mean、再三者 mean”逐 bit 相等；
- 对 rationale 分支做同一验证；
- 覆盖至少一个会让旧两种归约顺序产生末位差异的 deterministic synthetic array；
- assertion 仍为 exact equality；
- 不读取 BDD-OIA target、prediction 或任何 formal q-response output。

可以同时为 preflight detail normalization 增加 byte-stability unit test，但不得借此次修复更改其他统计逻辑。

## 8. 为什么不是 Amendment 02

科学 protocol 冻结的对象是：

- C1 mean-three；
- 三个固定 perturbations；
- q map；
- per-seed-first bottleneck；
- direction/gate/bootstrap。

拟议修复没有改变其中任何一项。它只选择两个代数等价实现中的一个固定浮点归约顺序，并消除 audit 中非科学的运行耗时。

选择“先每 perturbation sample mean、再三者 mean”也不是事后择优，因为：

- Round 7 point convention 已先验存在；
- attempt01 的 point/detail path 已这样实现；
- Amendment 要求 q=0 exact bridge；
- 修复不需要查看 curve 的大小或方向。

所以应记录为 `Round 8 attempt01 implementation failure and authorized repair`，而不是 protocol amendment。不得创建 Amendment 02。

## 9. attempt02 的强制启动条件

只有全部满足后才允许 formal attempt02：

1. 只实施上述 C1 action+rationale reduction-order 修复；
2. 只实施 pytest timing normalization；
3. 新增相应 exact synthetic regression；
4. 修复代码和 tests 提交到一个明确 commit；
5. 保留 attempt01 failed log，且绑定其 SHA256；
6. 保留本失败审查 memo，且在新 manifest 中绑定其 SHA256；
7. 新 preflight 为 86/86 PASS；
8. preflight-only 连续两次产生 byte-identical preflight 与 run manifest；
9. 新 manifest 绑定修复后的全部 code/tests、protocol、Amendment、两份 reviewer memo、map/component、cache/calibration 与 Round 7 references；
10. 确认不存在 attempt01 遗留的 results、point CSV、bootstrap CSV 或 primitives；
11. attempt02 继续使用同一 q、map、salt、threshold、seeds、models、metric、gate、association-component bootstrap、2,000 replicates 和 seed `20260803`；
12. attempt02 只运行一次；若再触发 implementation STOP，保留失败并重新独立审查，不得自行迭代参数。

已被 attempt01 改写的 working-tree preflight/run manifest 不能直接作为 attempt02 freeze；它们必须由修复后提交的确定性实现重新生成并冻结。

## 最终决定

**GO_RERUN**

attempt01 是在正式结果落盘前被 exact implementation gate 正确截停的受控失败。拟议三项修复是唯一、最小、outcome-independent 的实现修正，不改变任何科学协议内容。

在第 9 节全部条件完成以前，attempt02 仍为 **STOP**；完成后允许一次 formal rerun。
