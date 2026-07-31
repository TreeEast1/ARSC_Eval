# Round 10 attempt01 预推理故障独立审阅

## 决定

**AUTHORIZE_OUTCOME_BLIND_ATTEMPT02_INFRASTRUCTURE_REPAIR_ONLY。**

本决定不授权 attempt02 正式运行。它只允许前瞻、透明、结果盲地实现一次基础设施限定修复，之后仍须生成新的 implementation commit、manifest、preflight，并取得新的独立 preformal GO。

本次 incident 审阅严格 outcome blind：未读取 checkpoint，未加载 checkpoint 张量，未构造或加载模型，未运行推理，也未读取或计算任何 Round 10 prediction、logit、confidence 或 metric outcome。

## attempt01 事实判定

提交 `7cc05537976d0fae1ebfb1aaa0618319a4cf69ca` 永久保存了：

- 原 GO decision SHA256：`913D580D31F41F1F0DE8F597D7439F241B6BFA5081DF35844ABF7CF5F97B6DFA`；
- attempt01 log SHA256：`BB6CCB81A6AF980C5BE35EED3D36DDE9D5E1DABADD2EDAF187011B1A8C22A3CC`；
- incident SHA256：`1DA010284B0E6F8311E3A76DDF0E2C0C1015891EE244D92B115C550273C5D712`；
- 唯一退出标记：`EXIT_CODE=1`。

日志只有 `formal analyzer requires the frozen tmux launcher contract` traceback，没有任何 seed、condition、checkpoint、inference、bootstrap 或结果输出。

独立 AST/执行顺序核验显示：

1. `formal_run` 第一条可执行语句在第 1304 行检查 tmux session 与环境哨兵；
2. `validate_formal_authorization` 在第 1309 行，尚未执行；
3. `STAGING_DIR.mkdir` 在第 1312 行，尚未执行；
4. 第一次 `run_seed_inference` 调用位于第 1320 行，尚未执行；
5. `torch`、`arsc_eval.engine`、`arsc_eval.models` 和相关工具只在 `run_seed_inference` 内第 840–844 行延迟导入；
6. 顶层没有 torch、engine 或 models import。

文件系统独立核验确认以下全部不存在：

- attempt01 staging、final 和 artifact index；
- 五个 seed logits；
- primitives；
- point diagnostics；
- bootstrap draws 和 bootstrap summary；
- results JSON。

因此 attempt01 没有进入正式模型网格，也没有产生任何可支持选择、调参、停止或重试的 outcome 信息。

## 根因

审阅的 launcher 明确传入 `--tmux-session arsc_round10_formal`，但把 `ARSC_ROUND10_LAUNCHED_BY_TMUX=1` 作为 WSL shell 的 inline 环境变量传给 Windows Python。analyzer 同时要求 CLI session 和该环境哨兵。失败位置与日志证明这个组合条件不成立；在冻结 launcher 已明确提供 CLI 参数的前提下，incident 对 WSL-to-Windows inline 环境变量未传播的归因与代码和日志一致。

GPU 是否空闲不是授权依据。决定只依赖失败发生在任何模型/结果代码之前。

## 与 formal_run_count=1 的关系

原协议冻结一次正式网格并规定结果产生后不得增加、筛选或重跑。attempt01 在正式授权复核、staging 和推理之前失败，不能被解释为已执行一次正式网格。允许一个前瞻修复后的 attempt02 不会重复抽样、重复检验或利用结果选择。

但 attempt01 仍是已消耗且不可覆盖的启动事件，必须永久标记为 pre-formal infrastructure failure。若后续发现任何 checkpoint/model/outcome 实际已经产生，本授权立即失效并转为 `PERMANENT_ROUND10_INCONCLUSIVE_STOP`。

## attempt02 允许的修复范围

唯一允许的实现变化是：

- 移除不可移植的 `ARSC_ROUND10_LAUNCHED_BY_TMUX` 环境变量条件；
- 保留并改为显式 CLI session `arsc_round10_formal_attempt02`；
- 使用全新的 log、staging、final 和 artifact index；
- analyzer 仍须要求新 log sentinel 已存在；
- launcher 和 analyzer 仍须共享严格 allowlist/guard；
- allowlist 必须精确允许并 hash-bind 已保存的 attempt01 log、incident 和本 incident reviewer decision。

建议冻结的新路径：

- session：`arsc_round10_formal_attempt02`
- log：`outputs/validity/round10_corruption_formal_attempt02.log`
- staging：`outputs/validity/round10_corruption_formal_attempt02.staging`
- final：`outputs/validity/round10_corruption_formal_attempt02`
- index：`outputs/validity/round10_corruption_artifact_index_attempt02.json`

不得删除、重命名、覆盖、截断或复用 attempt01 log/incident；不得再次使用 attempt01 session 或任一 attempt01 output path。

## 绝对冻结项

attempt02 修复不得改变 data、manifest、source-clip grouping、models、checkpoints、calibrations、operators、corruption families、levels、parameters、thresholds、metrics、diagnostics、seeds、bootstrap RNG/replicates/call order、quantiles、multiplicity、practical gates、decision rules 或 claim boundary。不得新增 cache/restart 机制。

## 必需授权序列

1. 仅实现上述 outcome-blind 基础设施修复；
2. 提交新的 implementation commit；
3. 生成全新 attempt02 implementation manifest 和 outcome-blind preflight；
4. 新 manifest 必须绑定全部直接/传递依赖、冻结输入、原 GO、attempt01 log、incident 和本 reviewer decision；
5. 用合成 fixture 验证新 session/log/path、strict allowlist、direct-run refusal、interruption permanence 和 exact finalizer contract；
6. 由独立 reviewer 再次 outcome-blind 审阅；
7. 只有新的 decision 明确签发 attempt02 formal GO 后才能启动；
8. attempt02 是唯一仍可能执行的正式模型网格；成功、科学失败或运行中断后均永久停止。
