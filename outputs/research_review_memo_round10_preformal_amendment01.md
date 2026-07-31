# Round 10 预正式运行 Amendment 01 独立复审

## 决定

**GO_ROUND10_FORMAL_RUN_ATTEMPT01。**

修复实现 commit 为 `69a9b8fe8123efaa30272500546f4e3e2edb0615`，修复预飞 commit 为 `19cf3b7ddc434922649a4284d6bd1a7ae8d241e7`。先前 decision `A109F38F4EB347B855090D17AE76417B2BD7753DE0968D6FAF65BEC669B260B9` 的 B1–B4 已全部独立关闭。

本次复审严格 outcome blind：未调用 `torch.load`，未加载 checkpoint 张量，未构造或加载模型，未运行模型推理，未读取或计算任何 Round 10 非零剂量 prediction、logit、confidence 或 metric outcome，也未启动正式实验。

## B1–B4 关闭证据

### B1：one-shot 与 tmux/log 守卫——CLOSED

- 用临时合成 output tree 注入 prediction cache、tmp、非标准 staging、run manifest、logits 和 formal log 六类未知文件；严格 allowlist 全部拒绝，同时保留冻结 protocol/semantic evidence。
- launcher 在 `tmux new-session` 之前调用同一 analyzer `--guard-only`。
- 正式 analyzer 要求冻结 session 参数和 launcher 环境哨兵，并要求标准 formal log 已存在。
- 正式阶段工作树只允许该标准 log 为唯一 untracked 路径；标准 staging/final/index 以及任意额外 Round 10 output 仍被拒绝。

### B2：GO review_mode 精确 schema——CLOSED

- review_mode 精确为 10 个字段，字段集合、JSON boolean 类型和值均被校验。
- 独立负例确认 missing、extra、mistyped，以及 `model_constructed_or_loaded`、非零剂量 logits、非零剂量 confidences 为 true 时均拒绝。

### B3：本地传递依赖闭包——CLOSED

- 不调用实现内 closure 函数，独立用 AST 从八个冻结 root 递归枚举本地 `arsc_eval` import。
- 独立闭包与 manifest 的 21 个文件及完整 dependency graph 精确一致。
- 闭包包括 `src/arsc_eval/__init__.py`、`graded_response.py`、`internal_validity.py`、`metric_validity.py` 和 `metrics.py`。

### B4：finalizer 完整性合同——CLOSED

- 合成 final tree 的精确文件集合为五个 seed logits、primitives、point diagnostics、bootstrap draws、bootstrap summary 和 result，共 10 个。
- result 内部九项 pre-result 路径全部使用 FINAL 目录，不含 `.staging`，并逐文件重算 SHA256。
- missing、等数量 substitution、extra 和 hash mismatch 四类独立负例均拒绝。

## 其他核验

- 独立重哈希 `preformal_review_targets_sha256`：69/69 完全一致，无 mismatch。
- 加入当前 amendment01 manifest 和 preflight 后，审阅集合严格为 71 项。
- manifest SHA256：`5783C9FE25A593DFE4FFDA3CAA594079D955C5C33DBF32D966717412A474A101`。
- preflight SHA256：`42B06C21EF585780C18EE644AB00C324A2BD6EB8576CD2915091594EB968BCE2`。
- 独立全量测试：`94 passed in 16.39s`，使用 `-B`、`PYTHONDONTWRITEBYTECODE=1` 与 `-p no:cacheprovider`。
- 原统计实现、operator、数据管线及冻结协议哈希未变化；先前通过的纯合成 A/R/S/C1、exact-tie AURC、source-clip occurrence weighting 与 5000 shared-bootstrap 审计继续由本次精确哈希集合绑定。
- 复审完成时 amendment01 GO、标准 staging、final、formal log 和 artifact index 均不存在。

## 授权边界

本决定只授权一次冻结的 `attempt01` 正式运行。必须使用已审 launcher、tmux session、同一 guard、同一 71 项绑定和 one-shot 输出路径。不得复用缓存、重启中断运行、改变 seed/family/level/threshold/metric/bootstrap/quantile/cluster unit，也不得把未来结果外推为自然腐败、真实道路安全、外部有效性、grounding、faithfulness 或因果证据。
