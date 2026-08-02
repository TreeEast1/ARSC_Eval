# Round 11 DAAD-X 布局 Worker/Supervisor 第一闭环独立审阅备忘录

## 最终结论

最终决定为 **`GO_RUNNER_SUPERVISOR_IMPLEMENTATION_NOT_RUN`**。

该决定只适用于下列四个文件的精确字节版本，表示数据无关的布局 worker/supervisor 第一闭环及其合成测试已经满足进入后续 authority 复制、完整 formal runner 与 execution binding 集成审阅所需的实现条件。它不是正式运行授权，也不是任何研究结论。

## 精确版本绑定

| 文件 | 字节数 | SHA-256 |
|---|---:|---|
| `src/arsc_eval/round11_layout_worker.py` | 5740 | `E18CF25C52592EF25F4839FD6C2C33212C0C64ACBD5617C2AAFBD19298E38921` |
| `src/arsc_eval/round11_layout_runner.py` | 29191 | `01E413CDD54EF0E4EF510F2ECE02487D3BFDE7D7D071EC264E3DA1B3F3F89A8F` |
| `tests/test_round11_layout_worker.py` | 1462 | `40D548EDEAB2980308AD14FAC82F9F42A3DB05B344BC91B371B67BC8561ADFA8` |
| `tests/test_round11_layout_runner.py` | 12034 | `B47ABCCD6BC432F5761169B060CA27DE69A300E873614B5815FB7F2EE4CC40DF` |

任一文件的字节数或哈希发生变化都会使本决定失效，并要求重新独立审阅。

## 审阅边界

本轮只审阅 worker、supervisor 与合成测试，没有访问真实 receipt、manifest、archive、数据或其元数据路径，也没有生成正式实验产物。本决定明确不包含：

- authority 文件复制、authority 完整性闭合或正式 authority 集成；
- full formal runner、execution binding 或正式 attempt claim；
- 真实输入读取、正式布局清点运行或任何 run 授权；
- candidate selection、Phase-1、G0–G8、训练、推理或指标实验；
- publishable claim、研究结论或 ARSC 四项指标有效性、合理性与创新性结论。

因此，本决定严格保持 `no-real-input / no-authority-copy / no-full-formal-runner / no-binding / no-claim / no-run` 边界。

## 独立验证证据

最终精确候选的聚焦测试由独立审阅者直接运行：

```powershell
python -m pytest -q tests/test_round11_layout_worker.py tests/test_round11_layout_runner.py
```

结果为：`16 passed in 1.51s`。

Windows 句柄隔离、Job Object、阻塞、超时和失败路径窄集也由独立审阅者直接运行，结果为：`8 passed, 5 deselected in 1.11s`。其中 Windows 专项单独确认：

- Job Object 的 active-process limit 阻止 worker 创建后代进程；
- 父进程预置但未列入 `handle_list` 的 inheritable handle 对 worker 不可见；
- stdin、stdout/control 等授权管道仍可正常工作。

DeepSeek 辅助执行曾在审阅早期因传输端 `fetch failed` 而未执行，且没有文件写入；最终判断、源码复核和全部上述测试证据均由独立主审阅者直接完成。

## STOP_FIX 历史与关闭证据

### 第一轮 `STOP_FIX`：基础设施失败、阻塞 opener、线程收尾与最终 deadline 竞态

早期候选的 supervisor 失败闭合不足：日志/控制 drain 异常可能被降格为普通 observation；阻塞的 `archive_opener` 位于受控 feeder 之外，可能绕过 deadline；open/read/write 边界没有统一检查同一绝对 deadline；完成路径在 drain、fsync 和 supplied-hash 快照后没有最终 deadline 复核，存在“循环内未超时、最终返回 COMPLETE 时已超时”的竞态。

关闭证据：

- 日志文件在 spawn 前以 exclusive 方式打开并核验；
- `archive_opener` 移入收到 READY 后才启动的 feeder 线程；
- open、每次 read 和每次 write 前检查同一绝对 monotonic deadline；
- 日志/控制 drain 错误与线程无法终止均无条件成为 `LayoutRunnerError`，不能返回可误导的 observation；
- feeder、control、log 线程全部 join，额外控制消息检查、日志 flush/fsync 和 supplied-hash 快照完成后记录唯一 `finished_at`；
- 当 `finished_at > deadline` 且此前无更具体失败时，强制 `WORKER_TIMEOUT`；`complete` 仍要求 `failure_code is None`，`elapsed_seconds` 复用同一 `finished_at`；
- 阻塞 opener、feeder failure、timeout、log overflow 与 drain failure 合成回归均通过。

### 第二轮 `STOP_FIX`：Windows 非白名单可继承句柄泄漏

早期 Windows spawn 设置了 `STARTUPINFO.lpAttributeList = {"handle_list": ...}`，但没有在 `CreateProcess` flags 中加入 `EXTENDED_STARTUPINFO_PRESENT`。在 `bInheritHandles=True` 下，属性列表未生效，独立 probe 实际观察到未授权的 inheritable pipe handle 泄漏进 worker。这违反了精确句柄继承边界，构成正式阻断项。

关闭证据：

- runner 显式定义 `CREATE_SUSPENDED = 0x00000004` 与 `EXTENDED_STARTUPINFO_PRESENT = 0x00080000`；
- Windows 创建标志精确组合为 `CREATE_SUSPENDED | EXTENDED_STARTUPINFO_PRESENT | CREATE_NO_WINDOW`；
- 新增 Windows 实际回归：父进程预置一个不在 `handle_list` 的 inheritable pipe handle，worker 的 `GetHandleInformation` 必须失败；
- 该句柄隔离回归与授权控制管、Job Object 后代阻断回归同时通过。

## 最终实现判断

最终精确候选具备以下已核验性质：

- worker 使用固定、path-free 的 READY/COMPLETE/ERROR 控制协议，ERROR code 受固定 allowlist 约束；
- archive 仅在有效 READY 后打开，并由 deadline 受控 feeder 流式输送；
- 实际成功写入 worker stdin 的字节数与 SHA-256 独立累计，并与预期值及 COMPLETE summary 交叉验证；
- 控制流与日志有固定容量上限，异常、溢出、额外 terminal、无效 terminal、超时和线程失败均 fail-closed；
- Windows worker 在 suspended 状态下先进入带 `ACTIVE_PROCESS=1` 与 `KILL_ON_JOB_CLOSE` 的 Job Object，再恢复执行；
- 扩展启动属性的 handle allowlist 已实际生效，不再继承无关 inheritable handles；
- COMPLETE 判定覆盖全部线程收尾、日志持久化、hash 快照和最终 deadline 复核。

在本轮实现层边界内，没有发现剩余的 misleading COMPLETE、未受控 worker 后代、非白名单句柄泄漏或 deadline 绕过。

## Claim boundary

`GO_RUNNER_SUPERVISOR_IMPLEMENTATION_NOT_RUN` 只授权提交和集成上述精确 worker/supervisor 与合成测试，并进入另行审阅的 authority 复制、full formal runner 和 execution binding 阶段。它不授权访问真实 receipt、manifest、archive 或数据，不授权创建正式 claim，不授权正式运行，也不支持任何 publishable result 或关于 ARSC 指标有效性、合理性、创新性和 SCI 完备性的主张。
