# Round 11 DAAD-X 布局清点正式运行器集成设计独立审阅

## 结论

审阅决定为 **`GO_DESIGN_RUNNER_INTEGRATION_NOT_RUN`**。

该决定只冻结正式布局运行器的父子进程架构、claim 顺序、失败分类和产物生命周期，授权后续进行无真实数据的实现及合成测试。它不是 execution binding，不授权创建 claim，不授权访问或检查真实 receipt、manifest、archive 及其元数据，也不授权正式运行、候选选择、Phase-1、G0–G8、训练、推理或研究主张。

## 精确依据

审阅仓库 HEAD：`150248e675a579b931afb181355f30080ad7e464`。

| 角色 | 路径 | 字节数 | SHA-256 |
|---|---|---:|---|
| 冻结布局协议 | `outputs/validity/round11_daadx_layout_inventory_protocol.json` | 9720 | `E2E16BDE936CDE68B2D305322C7B33422F5F0043B45D833858E1BFB7C90740C5` |
| 协议审阅授权 | `outputs/validity/round11_layout_inventory_protocol_reviewer_decision.json` | 8977 | `ED67D48A629FF3B7D8827E4BC0D8CE170B88C483EEE62FAFDCBDE96647E16E03` |
| 流式 parser/sink | `src/arsc_eval/round11_layout_inventory.py` | 38198 | `3D3AA0CD07DBFBFEBE874FBC80DD7ABF7AD658D0FFB90551F5267D4CD7D6CD4B` |
| watchdog | `src/arsc_eval/round11_layout_watchdog.py` | 6275 | `3B44D8E1C044150EB8B418CB0E44D5FBDB4DEF49D06068698895F52C2C2FB379` |
| parser/watchdog 实现审阅授权 | `outputs/validity/round11_layout_inventory_implementation_reviewer_decision.json` | 3522 | `5CE4BE73044217A3E9893406AE30C90CFE2E8B0DA86C23431A4A39C365584A72` |
| 已审阅控制原语 | `src/arsc_eval/round11_phase1_control.py` | 15944 | `89AEA0B774D20E0D79126F9A521A1E5514A3DED54E73910EC8DFF12A99BAEA1E` |
| 控制原语审阅授权 | `outputs/validity/round11_phase1_control_reviewer_decision.json` | 6516 | `1F4FD48A3D978DC4957DFB81105135F0AFD2DF86E2D3E35725AB5F1086666D3F` |

任一绑定字节变化都要求重新审阅。本轮没有读取、stat、hash 或列举真实 receipt、manifest、archive、chunk 或数据路径。

## 父进程与 worker 的精确职责

### 受信任父进程

父进程是唯一控制面，独占以下职责：

1. 验证 HEAD、协议、runner、worker、tests、parser、watchdog、control、execution binding 和 execution reviewer decision 的精确身份；
2. 创建并永久保留 attempt claim；
3. 创建 staging，执行 receipt/manifest 的稳定读取、验证和流式复制；
4. 稳定打开 archive，以不超过 1 MiB 的块向 worker stdin 供给压缩字节，同时在父进程中记录“已供给压缩前缀”的实际字节数和 SHA-256；
5. 执行硬截止时间、日志上限、worker 终止和无后代进程控制；
6. 生成 archive hashes、structure summary、results 和 artifact index；
7. 对全部产物执行稳定流式哈希、文件与目录同步、原子无覆盖发布以及发布后重哈希。

父进程不得解析 tar/PAX 路径，也不得解释或保存解压后的普通成员 payload。

### 受限 worker

worker 必须是 execution binding 中绑定的精确提交字节。启动要求为：

- 使用绝对 Python executable、精确 argv、`shell=False`、关闭无关句柄、isolated/no-bytecode 模式；
- 使用精确最小环境 allowlist，不继承无关环境或秘密；
- cwd 必须是本 attempt 独占的精确 staging 目录；
- stdin 只接收父进程供给的压缩流；stdout/stderr 只进入受限日志；
- 独立的有界控制 pipe 只允许一个固定 `READY` 和一个固定 terminal canonical message，禁止携带原始路径；
- worker 只允许直接创建并流式写入 public inventory 与 restricted path seal；其他正式产物均由父进程生成；
- `READY` 只能在两个 sink 文件均已 `xb` 创建并完成句柄/路径身份检查后发送。

archive 只能在父进程收到合法 `READY` 后打开。worker 中的 parser 必须对收到的同一压缩流再次独立计算压缩字节数和 SHA-256。

## 无后代进程与 watchdog

正式 Windows 运行必须先以 suspended 状态创建 worker，将其加入同时启用 `ACTIVE_PROCESS_LIMIT=1` 与 `KILL_ON_JOB_CLOSE` 的独占 Job Object，成功后才恢复执行。Job 创建、分配或限制配置失败时，不得打开 archive。不得在没有等价、另行审阅的 containment 层时宣称支持其他平台。

watchdog 集成必须扩展为同时管理 stdin feeder、控制 pipe、stdout/stderr drain 和 Job Object；当前只终止精确子进程且 `stdin=DEVNULL` 的 helper 不能直接视为正式运行器。

使用一个单调绝对 deadline。建议从 claim 完成持久化时开始计时，receipt/manifest 处理、worker、archive feeder 和闭合步骤共享同一 deadline，任何阶段只能使用剩余时间。日志总量不得超过冻结上限；必须预留固定父日志预算，其余预算交给 worker drain。超时或日志溢出时关闭 stdin、终止整个 Job、结束 feeder/control/log 线程，只有在全部线程和句柄稳定后才允许尝试 STOP 闭合。

## claim 前后允许动作

### claim 前允许

仅允许：

1. 从已跟踪的受信任 Git 字节验证协议、runner、worker、tests、parser、watchdog、control、binding 和 reviewer decision；
2. 验证 reviewer 的精确 GO、schema、HEAD、toolchain、Python executable、argv、环境 allowlist、cwd 字符串、Job 配置和冻结上限；
3. 只检查精确 claim/staging/final 控制路径及其父目录，不得枚举包含真实输入的目录；
4. 生成密码学随机 token；
5. 从协议或 binding 读取声明性的真实输入路径字符串及期望哈希，但不得触碰对应真实文件。

claim 前禁止对真实 receipt、manifest、archive 或 chunk 执行 open、read、list、stat、resolve、hash 或 schema 检查。

### claim 获取

claim 必须使用精确路径 `xb` 创建。先持久化零字节阻断目录项并同步父目录，再写入包含 schema、phase、attempt、execution-binding SHA-256 和随机 token 的 canonical JSON；每一步都执行打开句柄/路径身份检查、文件同步、目录同步和关闭后的稳定重读。claim 在成功、STOP、异常、中断、超时或崩溃后均不得删除。已有 claim、staging 或 final 必须停止并要求另行审阅 attempt02，不得清理、恢复或复用。

### claim 后允许

claim 持久化完成后才可：

1. `xb` 创建 mode 0700 的 staging 并同步父目录；
2. 以 no-follow、regular、single-link、稳定身份方式读取、验证和流式复制 receipt；
3. receipt 合格后同样处理 manifest；
4. receipt 与 manifest 均合格且 worker 已 `READY` 后，稳定打开 archive 并进行唯一一次有界供给/解析扫描；
5. 生成并关闭 STOP 或 COMPLETE 的 11 项 payload，最后生成 index 并尝试发布。

receipt 或 manifest 失败后不得打开 archive。

## 12 项产物生命周期

正式目录必须只包含协议冻结的 12 个精确文件。artifact index 最后创建且自排除，记录前 11 个文件的精确字节数和 SHA-256。

- 协议、binding 和 execution reviewer decision 使用 claim 前已验证并缓存的精确字节，在 claim 后写入 staging；
- receipt 与 manifest 只在 claim 后流式复制，读取与写入均进行稳定身份检查；
- worker 直接流式写 public inventory 和 restricted seal，不在内存累计路径列表；
- 父进程根据供给状态生成 archive hashes，根据 worker terminal message 或缺失状态生成 structure summary；
- 父进程最后生成 results、完成日志、稳定读取前 11 项并创建 index。

所有正式文件必须 `xb`、write-all、有界、regular/non-symlink/single-link、写前后检查句柄/路径身份、flush/fsync。staging 目录随后同步，以真正的 no-replace 原语原子重命名为 final，再同步父目录，并对 final 的精确 12 项执行流式重哈希。

restricted seal 允许达到 2 GiB，新的布局控制代码必须以不超过 1 MiB 的缓冲区流式计算哈希和发布后重哈希。不得直接复用会把完整文件聚合到 Python `bytes` 的 `round11_phase1_control.read_regular_stable` 或基于全 payload mapping 的 index 路径。

## 精确失败分类

### 1. publishable `HASH_CLOSED_STOP`

仅当控制面、文件身份和持久化能力仍健康时，下列失败可以发布正式哈希闭合 STOP：

- receipt/manifest 缺失、不可读、非 canonical、schema 错误、哈希或字节数不匹配、稳定性失败；
- archive 缺失、打开失败、期望哈希/大小不匹配；
- gzip、tar、PAX、路径、类型、checksum、完整性、资源上限或隐私策略失败；
- parser 异常、worker 非零退出、worker 控制协议错误；
- 能被完整 containment 并稳定收尾的超时或日志溢出。

任何已产生的 public/restricted 字节必须原样保留，禁止截断、覆盖或伪装成完整输出。若 worker 没有产生两项输出，父进程只能创建协议冻结的空表示：public 为 header-only，restricted 为零字节，并在 results 中标记 `GENERATED_EMPTY_NO_WORKER_OUTPUT`，不能称为已观察 inventory。

archive hashes 必须区分：

- `NONE`：未读取，observed SHA-256 为 `null`，observed bytes 为 0；
- `SUPPLIED_PREFIX`：记录父进程实际供给前缀的真实 SHA-256 与字节数；
- `COMPLETE_STREAM`：只有完整扫描完成时才记录完整观察哈希和字节数。

不得把期望完整 SHA-256 写入 observed 字段。structure summary 未完成的计数必须为 `null`/`INCONCLUSIVE`，不能用 0 冒充观察结果。results 必须逐项记录 `OBSERVED_COMPLETE`、`OBSERVED_PARTIAL` 或 `ABSENT_REPRESENTED_EMPTY`，并记录首个 failure stage/code、`layout_complete=false`、`completeness=HASH_CLOSED_STOP` 和 `STOP_LAYOUT_INTEGRITY_OR_POLICY_FAILURE`。index 对实际存在的完整、部分或空表示字节进行真实哈希。

### 2. `NONPUBLISHABLE_RESIDUE`

下列控制面或持久化失败不得伪装为正式 STOP：

- claim 无法完成持久化；已有 claim/staging/final；
- 路径身份、symlink、hardlink 或并发替换异常；
- 文件/目录 fsync 失败；sink 字节无法稳定读取；
- feeder、控制或日志线程不能终止；worker/Job 无法终止；
- 必需 STOP 元数据无法按上限独占写入；
- index 创建或同步失败；no-replace rename 失败；
- 父进程崩溃、断电或其他无法确认闭合的异常。

此时永久保留 claim 和所有 staging 残留，不删除、不覆盖、不复用；必须通过另行冻结并审阅的 attempt02 继续。它不是 12 项哈希闭合 STOP。

### 3. `BLOCKING_FINAL_UNVERIFIED`

若 staging 已重命名为 final，但父目录同步、精确 12 项验证或发布后流式重哈希失败，则保留 final 与 claim，禁止回滚或再次发布，并将其视为 `BLOCKING_FINAL_UNVERIFIED`。在另一次结果盲闭合审阅确认精确字节前，它既不是通过结果，也不是可接受的 `HASH_CLOSED_STOP`。

## 正式 execution binding 条件

任何运行前必须先创建并独立审阅一个 HEAD-exact、非运行 binding。binding 至少绑定：

1. runner、worker、tests、parser、watchdog、新布局 control、冻结协议和全部审阅授权文件的路径、字节数、SHA-256 与同一 HEAD blob；
2. Python executable 的绝对路径、版本与哈希，精确 Windows 平台和 Job Object 策略；
3. 完整 argv、最小环境键值、cwd、claim/staging/final 路径；
4. deadline、块大小、内存、日志和各输出上限；
5. 12 项精确文件名、empty/partial/status schema 和三类失败分类；
6. receipt、manifest、archive 的声明路径和期望字节数/SHA-256，但 binding 生成和审阅阶段仍不得触碰真实文件；
7. 唯一 attempt01 execution reviewer decision 的 schema、决策值及互相绑定哈希。

正式父进程在 claim 前只能验证该 binding 和 reviewer authority 的静态身份；真实输入只能在 claim 持久化后验证。

受信任且已绑定的模块代码在进程内遭任意类级 monkeypatch，不属于对象输入威胁边界。正式运行必须以 isolated 模式从绑定的提交字节启动，不能以此边界允许未绑定代码注入。

## Claim boundary

`GO_DESIGN_RUNNER_INTEGRATION_NOT_RUN` 只授权实现和合成测试上述设计。它不授权访问真实 receipt、manifest、archive 或其元数据，不授权创建 attempt claim 或 executable binding，不授权布局清点、候选选择、Phase-1、G0–G8、训练、推理或任何 ARSC 指标有效性与 SCI 级结论。
