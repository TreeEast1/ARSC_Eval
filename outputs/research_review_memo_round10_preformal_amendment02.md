# Round 10 attempt02 预正式运行独立盲审

## 决定

**GO_ROUND10_FORMAL_RUN_ATTEMPT02**

本决定授权一次且仅一次的 `attempt02` 正式科学网格。授权绑定实现 commit `0c10e078a27d67816041aedd31b0c3273177e30d`、preflight commit `7e11a31292b7f583828fcb4eaa6cf8a20fb60df5`、manifest SHA256 `D12886A702CB8B66D574D6A87879DCB3EF99B9D0F28507464A3541F6B06418EA` 和 preflight SHA256 `9DCC8E31CDE7AC8428BD297D9B433A23A48F785E1B4D75C70422E71A5A51DBF4`。

本次审阅严格 outcome blind：没有加载 checkpoint 张量，没有构造或加载模型，没有运行推理，没有读取或计算 Round 10 非零剂量 prediction、logit、confidence 或 metric outcome，也没有启动正式运行。checkpoint 文件仅以普通字节流重算 SHA256。

## attempt01 的永久历史与 attempt02 的唯一性

attempt01 被永久分类为 `PREFORMAL_INFRASTRUCTURE_FAILURE_ZERO_OUTCOME`。以下四项证据存在且哈希精确匹配：

- attempt01 log：`BB6CCB81A6AF980C5BE35EED3D36DDE9D5E1DABADD2EDAF187011B1A8C22A3CC`
- incident：`1DA010284B0E6F8311E3A76DDF0E2C0C1015891EE244D92B115C550273C5D712`
- incident reviewer decision：`93BAD702B0C6AB33187B05BCECCAF65946CAF6B3EAA542292187A81C2B4A93A0`
- incident review memo：`62CC1B1DF19FF68563E6152BA34080FB83925E34082E11C890F30D550C0063DC`

attempt01 的 staging、final 和 artifact index 仍全部不存在。该失败发生在授权复核、staging 创建、延迟的 torch/model import、推理和统计计算之前，因此不是一次已执行的正式模型网格，也没有产生可供选择、调参或停止使用的 outcome。它仍是不可删除、不可覆盖的历史启动事件。

attempt02 是唯一剩余且本决定唯一授权的正式科学网格。attempt02 成功、科学失败或运行中断后均不得再次启动、恢复或复用缓存。

## 科学实现零变化审计

从科学实现基线 `69a9b8fe8123efaa30272500546f4e3e2edb0615` 到修复实现 `0c10e078a27d67816041aedd31b0c3273177e30d`：

- configs、test manifest、models、checkpoints、calibrations、数据管线、corruption operator、`corruption_statistics`、A/R/S/C1、exact-tie AURC、source-clip occurrence weighting、shared bootstrap、quantile、multiplicity、thresholds、gates 和 decision rule 均未改变。
- 独立 byte diff 确认科学模块完全相同；独立 AST diff 确认 `seed_paths`、`load_temperature`、`run_seed_inference`、`save_seed_logits`、`prepare_all_seeds`、`compute_point_results`、`save_primitives` 和 `evaluate_gates` 全部完全相同。
- 仅修改 analyzer 的 attempt02 路径、授权链、会话标记和结果 attempt 元数据，以及 launcher、finalizer、attempt-aware GO contract/tests。

因此 infrastructure repair 没有改变任何研究设计、统计量或判定方向。

## attempt02 隔离与启动守卫

- 冻结 tmux session 精确为 `arsc_round10_formal_attempt02`。
- 新 log、staging、final、artifact index 与 attempt01 全部互斥且路径不重叠。
- launcher 在 `tmux new-session` 前执行同一 analyzer 的 `--guard-only`。
- Windows CLI `--tmux-session` 是唯一可移植启动标记；launcher 与 analyzer 均不存在 `ARSC_ROUND10_LAUNCHED_BY_TMUX` 环境变量哨兵。
- 正式 analyzer 先验证精确 attempt02 session，再要求 attempt02 log sentinel；工作树仅允许该 log 为 untracked，其他 tracked/untracked 变化均拒绝。
- strict Round 10 allowlist 拒绝未知 cache、tmp、staging、run artifact、logits 或日志。

独立负例重放确认拒绝：wrong/attempt01 session、缺失 attempt02 log、预先存在的 attempt02 产物、未知 prediction cache、未知 tmp，以及 attempt02 log 之外的未知 untracked 文件。attempt01 四项永久证据与所有 attempt02 写目标互斥，不能被覆盖。

## 完整性与测试

- manifest 的 77 个 `preformal_review_targets_sha256` 均已逐文件重算，77/77 精确一致，无 mismatch。
- 加入当前 manifest 与 preflight 后，reviewed path set 精确为 79 项；排序紧凑 JSON 的 canonical SHA256 为 `46964917CB08B8A1A371AA40CA2801D7F7697BF33AAAD9FA4F8292C9B52AB4F6`。
- 独立 AST 递归闭包从 8 个 root 得到精确 21 个文件，文件集合和完整 dependency graph 均与 manifest 相同，并包含 `graded_response`、`internal_validity`、`metric_validity`、`metrics` oracle chain。
- 独立全量测试结果：`94 passed in 16.25s`。
- finalizer 仅接受 `attempt02`、唯一 `EXIT_CODE=0`、不存在 staging、精确 10 个 final 文件；result 内部精确 9 个 pre-result 哈希必须使用 FINAL 路径并逐文件匹配。missing、same-count substitution、extra 和 hash mismatch 均被拒绝。

审阅完成前，attempt02 GO、log、staging、final 和 artifact index 均不存在；因此没有形式运行或 outcome 泄漏。

## 授权边界

必须使用已审 `scripts/launch_round10_corruption_tmux.sh`，必须先通过 `--guard-only`，必须使用 session `arsc_round10_formal_attempt02`，并保持本决定精确绑定的 79 个文件不变。不得复用 attempt01 或 attempt02 缓存，不得恢复中断运行，不得修改 seed、family、level、operator、metric、threshold、bootstrap、quantile、cluster unit、gate 或 claim boundary。

未来即使十二个 gate 全部通过，也只支持冻结 BDD-OIA population、五个历史 ResNet-50 seeds、固定 calibration/threshold、三种合成 pixel corruption grid 和预注册 seed/source-clip bootstrap 下的内部 joint metric-by-model-by-operator dose-response。它不支持自然腐蚀流行率或自然严重度、外部有效性、真实道路鲁棒性或安全保证、rationale grounding/faithfulness、因果结论或冻结用途之外的 calibration validity。
