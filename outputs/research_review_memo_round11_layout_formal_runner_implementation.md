# Round 11 DAAD-X 布局 Formal Runner 实现独立审阅备忘录

## 最终结论

最终决定为 **`GO_FORMAL_RUNNER_IMPLEMENTATION_NOT_RUN`**。

该决定仅批准下列精确字节版本的数据无关 formal parent 编排实现及合成测试进入后续提交、execution binding 与另行独立运行审阅。它不是 `GO_RUN`，不创建或批准 execution binding，不授权获取真实 attempt claim，也不授权访问真实 DAAD-X receipt、manifest、archive、数据或其元数据。

## 精确版本绑定

| 文件 | 字节数 | SHA-256 |
|---|---:|---|
| `src/arsc_eval/round11_layout_formal_runner.py` | 25340 | `35A87AA2272CE9C86527943D6D20D14C39F45C34AFD0DBEB5D0F7DD55B3642D4` |
| `tests/test_round11_layout_formal_runner.py` | 13147 | `08C4078AE67B9FD41895617FD032E541472BA0ADE7E5E6C81C5E880A987182DA` |

任一文件的字节数或 SHA-256 变化都会使本决定失效，并要求重新进行独立审阅。

## 审阅边界

本轮仅只读审阅代码，并使用 pytest 临时目录中的合成微型输入执行测试。审阅期间：

- 未读取、stat、resolve、hash、列举或解压任何真实 DAAD-X receipt、manifest、archive、chunk、标签、视频或数据路径；
- 未执行正式布局清点，未创建真实 execution binding、正式 attempt claim、staging 或 final；
- 未创建 publishable result，未进行候选选择、Phase-1、G0–G8、训练或推理；
- 未形成关于 ARSC 四项指标有效性、合理性、创新性或 SCI 完备性的结论。

因此，本决定严格保持 `implementation-only / synthetic-only / no-real-input / no-binding / no-real-claim / no-run` 边界。

## 独立验证证据

最终精确候选的 focused suite 由独立审阅者直接运行：

```powershell
python -m pytest -q tests/test_round11_layout_formal_runner.py
```

结果为：`14 passed, 1 skipped in 4.74s`。

deadline、claim、link、supplied-prefix 与 archive-hash 相关窄集由独立审阅者直接运行，结果为：`7 passed, 1 skipped in 2.62s`。Windows symlink 用例因当前系统权限条件跳过，未冒充通过；receipt 与 archive 的 hardlink 非发布回归均实际通过。源码编译检查与 `git diff --check` 通过。

主代理在修复后的精确候选上报告全套结果为：`573 passed, 11 skipped`。该数字明确属于 **primary-run evidence**，不是本独立审阅者的全套复现。本独立审阅者尝试运行全套测试时，三个无关测试在 collection 阶段因当前解释器缺少 `cv2` 与 `ultralytics` 而失败，因此没有将主代理的全套数字冒充为独立证据。

按照工作区路由要求，曾尝试让 DeepSeek 仅执行只读的 focused 测试和初步覆盖映射；API 在执行前返回 `fetch failed`，没有运行测试，也没有写入文件。最终源码判断、反例构造和上述独立测试均由主审阅者直接完成。

## `STOP_FIX` 与关闭证据

### 最终 shared-deadline 逃逸

被阻断的候选仅在原子 rename 前检查 parent deadline。`control.finalize_and_publish` 在 rename 后仍需完成 final 绑定、父目录 fsync、final 身份检查和完整 12 项 post-publish streaming rehash，但 formal runner 在 finalizer 返回后没有再次检查 deadline，可能在绝对 deadline 之后仍返回 `LAYOUT_INVENTORY_COMPLETE`。

独立最小复现使用纯临时合成输入，让 post-publish closure verification 成功但模拟慢 I/O 跨过 deadline。旧候选实际返回：

- `outcome = LAYOUT_INVENTORY_COMPLETE_AWAIT_INDEPENDENT_SELECTION`；
- `completeness = LAYOUT_INVENTORY_COMPLETE`；
- elapsed `1.421s`，超过 `1.2s` deadline。

该行为违反了 receipt、manifest、worker、archive feed 与 closure 共用同一绝对 deadline 的冻结设计，因此给出 `STOP_FIX`。

关闭证据：

- `finalize_and_publish` 完成真实原子发布及 post-publish verification 后，formal runner 立即取得唯一 `finished_at = time.monotonic()`；
- 当 `finished_at >= deadline` 时抛出 `FormalRunnerInfrastructureError("attempt deadline expired before formal completion")`；
- 超时路径不构造、不返回 `FormalRunResult`，因而不能返回 misleading COMPLETE；
- 回归测试使用仅替换 formal 模块时钟的局部 fake clock，不污染 control 或 worker/supervisor 的计时；
- 回归确认异常后永久 claim 与 final 均保留、staging 不存在，符合 rename 后失败的阻断残留边界；
- 修复后的 focused 与窄集测试全部通过，原反例已关闭。

## 最终实现判断

最终精确候选已核验具备以下性质：

- preclaim 仅执行词法路径、可信缓存字节和冻结 expectations 校验，不触碰三项真实输入；
- durable claim 之后严格执行 receipt、manifest、worker READY、archive open/feed 顺序；receipt 失败跳过 manifest 与 archive，manifest 失败跳过 archive；
- receipt、manifest 与 archive 的正式文件描述符使用 `O_BINARY`，并执行 regular、non-symlink、single-link、句柄/路径身份及复制前后稳定性检查；
- authority 的完整、部分与空表示状态取自 staging 中实际稳定字节，不能用期望字节伪装观察结果；
- archive hashes 使用父进程实际成功写入 worker stdin 的 supplied bytes 与 SHA-256，准确区分 `NONE`、`SUPPLIED_PREFIX` 与 `COMPLETE_STREAM`；
- 完整字节但哈希不匹配时，首个失败归类为 `ARCHIVE_DIGEST_MISMATCH`，不能被 worker terminal 状态掩盖；
- parent deadline、worker budget、closure reserve、rename 前门和 formal completion 最终门共同闭合；
- pre-READY inventory residue、身份/link 异常、control/finalization 异常均不能发布伪 STOP；
- worker log 上限预留固定 parent append 预算，append 使用稳定身份检查、容量检查与 fsync；
- results、summary、archive hashes、artifact statuses 与 exact-byte index 由已审阅 control finalizer 交叉验证；
- staging 阶段基础设施异常保留 claim/staging 且不发布；rename 后异常或最终超时保留 claim/final 且不返回正式结果。

在本轮实现边界内，没有发现剩余的 misleading COMPLETE、misleading HASH_CLOSED_STOP、preclaim 真实输入越权访问或失败分类绕过。

## Claim boundary

`GO_FORMAL_RUNNER_IMPLEMENTATION_NOT_RUN` 只授权提交和集成上述精确 formal runner 与合成测试，并进入另行冻结、独立审阅的 execution binding 和运行授权阶段。它明确不是 `GO_RUN`，不授权访问真实 DAAD-X，不授权真实 claim，不授权正式运行、结果发布或任何研究主张。
