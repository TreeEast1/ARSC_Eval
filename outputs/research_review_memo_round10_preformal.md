# Round 10 预正式运行独立审阅备忘录

## 决定

**STOP_REPAIR_ROUND10_FORMAL_IMPLEMENTATION。不得启动 attempt01。**

本次审阅严格保持 outcome blind。未调用 `torch.load`，未加载 checkpoint 张量，未构造或加载模型，未运行模型推理，也未读取或计算任何 Round 10 非零剂量 prediction、logit、confidence 或 metric outcome。审阅快照为实现 commit `c8191120ce6387ea65269a57480651f5ae697670`，implementation/preflight 提交为 `81b3cd52397ed1862e1b7e349a30278125e45150`。

## 阻断缺陷

### R10_PREFORMAL_B1：one-shot 守卫不是全域拒绝

正式 analyzer 的授权路径只对 staging、final 和 artifact-index 三个标准路径调用 `require_paths_absent`；官方 tmux launcher 只检查 GO、标准 final/staging/log/index。二者都没有扫描并拒绝任意额外的 Round 10 cache、prediction cache、临时文件、非标准 staging、run manifest 或散落的正式产物。直接运行 analyzer 还可以绕过 launcher 的标准 log 不存在检查。

因此，诸如 `outputs/validity/round10_corruption_prediction_cache/`、非标准 `round10*.tmp`、额外 run manifest 或其他 Round 10 正式缓存可以存在而正式运行仍被接受。这不满足 amendment01 和先前 implementation-only authorization 中“任何 formal/cache/staging/temporary/run artifact 已存在即永久 STOP、不得复用或重启”的约束。

### R10_PREFORMAL_B2：GO contract 未封闭 outcome-blind 状态

`validate_preformal_go` 只检查 `checkpoint_tensors_loaded`、`model_inference_run`、非零剂量 predictions 和 metric outcomes 四个 false 字段。它不检查 `model_constructed_or_loaded`、非零剂量 logits、非零剂量 confidences，也不要求 `review_mode` 是精确且无额外字段的 schema。

纯合成反例已确认：分别加入

- `"model_constructed_or_loaded": true`
- `"round10_nonzero_severity_logits_read_or_computed": true`
- `"round10_nonzero_severity_confidences_read_or_computed": true`

时，当前 validator 均接受该 GO。故一个明确声明违反 outcome-blind 的 reviewer decision 仍可解锁 checkpoint 加载与正式运行。

### R10_PREFORMAL_B3：60 项哈希集合不是传递依赖闭包

被绑定的 `tests/test_corruption_statistics.py` 直接导入 `arsc_eval.graded_response.tie_averaged_aurc` 作为 tie-AURC 测试 oracle，但 `src/arsc_eval/graded_response.py` 不在 `preformal_review_targets_sha256` 中。所有 `arsc_eval.*` 导入还会执行包文件 `src/arsc_eval/__init__.py`，该文件同样未绑定。

这使“87 tests passed”的关键 oracle/导入执行语义可在不触发 60 项哈希校验的情况下改变，不满足全部 direct/transitive files 必须 hash-bind 的预正式审阅条件。

### R10_PREFORMAL_B4：finalizer 只验证数量，不验证必需产物集合与内部哈希

finalizer 仅要求 final 目录下存在 10 个文件，然后对当前任意 10 个文件建立索引。它没有要求精确的五个 seed logits、primitives、point diagnostics、bootstrap draws、bootstrap summary 和 result 文件名集合，也没有把 result JSON 中 `artifact_sha256_before_result_json` 的九项路径/哈希与磁盘重新核对。

因此，缺失一个必需产物但由任意其他文件补足到 10 个时，finalizer 仍可输出 `COMPLETE_HASH_BOUND`。这不足以证明正式输出合同完整。

## 已通过的独立核验

- 独立重哈希 manifest 的 60 个目标，60/60 与记录完全一致；再加当前 manifest 与 preflight 共核验 62 项。
- implementation manifest SHA256：`79483B9C6F23B7B1DC720FAAAC8D53174FE1D850F6C72B24F5EEAD3B1314E34A`。
- formal preflight SHA256：`9AB8959D9E09EE89662F277F487CF6DE8E7AE36850FD13107A429473E008089D`。
- 独立全量测试：`87 passed in 16.33s`，使用 `-B`、`PYTHONDONTWRITEBYTECODE=1` 和 `-p no:cacheprovider`。
- 纯合成 operator-before-resize fixture 与数据管线逐值一致，并与 resize-before-operator 结果不同。
- 纯合成 A、R、S、C1 独立逐图/逐类复算与实现一致，最大绝对差分别为 `0`、`0`、`1.11e-16`、`1.11e-16`；source-clip 重复抽样按展开后的每个 image occurrence 单位加权。
- exact-tie AURC 对 120 个组内排列穷举：实现值 `0.6111111111111112`，独立穷举均值 `0.6111111111111110`。
- 纯合成 5000-replicate replay 精确复现 seed draw、clip draw、expanded counts、12-gate family-then-axis flatten order 和 24-endpoint family-then-component flatten order。
- 静态审计确认：level 0 只推理一次后跨三 family 复制；A/R/S/C1 方向与 component 定义、4/5、五 seed mean、Bonferroni raw `>0`、no-reversal、practical endpoint raw `>=`、`method="linear"` quantile 和非有限值停止规则均按冻结协议实现。
- 当前审阅时标准 final、staging、log、artifact index 与 preformal GO 均不存在。

这些通过项不抵消上述授权、one-shot、哈希闭包和输出完整性缺陷。

## 最小修复与再审条件

1. 用统一、可测试的全域枚举函数拒绝所有已有 Round 10 formal/cache/prediction/staging/tmp/run artifacts；launcher 与 analyzer 必须共享同一语义，并消除直接调用绕过 log 哨兵的路径。
2. 将 GO `review_mode` 定义为精确 schema，至少强制模型构造/加载、checkpoint 张量、推理、非零剂量 predictions/logits/confidences/metric outcomes 全部为 false，并为每个 true、缺失和额外字段添加负测试。
3. 将 `src/arsc_eval/graded_response.py`、`src/arsc_eval/__init__.py` 及重新枚举出的全部本地传递依赖纳入 manifest；重新生成 outcome-blind preflight。
4. finalizer 必须检查精确必需文件名集合、精确数量、result 内部九项哈希映射与磁盘一致，再创建 artifact index；添加缺失、替换、额外文件和哈希不一致的负测试。
5. 修复必须形成新的 implementation commit、新 manifest 和新 preflight，并接受另一轮独立 outcome-blind preformal review。现有 attempt01 未获授权。
