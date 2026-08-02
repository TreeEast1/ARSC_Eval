# Round 11 DAAD-X 布局清点实现独立审阅备忘录

## 结论

最终决定为 **`GO_IMPLEMENTATION_NOT_RUN`**。

该决定仅表示下列四个候选文件在当前精确字节版本上，通过了结果盲、无真实数据的实现审阅，可以进入受约束的正式运行器集成阶段。它不表示已经运行 DAAD-X 布局清点，不表示任何数据门、统计门或研究结论成立，也不授权训练、模型推理、标签读取、视频解码或 ARSC 有效性声明。

## 精确版本绑定

| 文件 | 字节数 | SHA-256 |
|---|---:|---|
| `src/arsc_eval/round11_layout_inventory.py` | 38198 | `3D3AA0CD07DBFBFEBE874FBC80DD7ABF7AD658D0FFB90551F5267D4CD7D6CD4B` |
| `src/arsc_eval/round11_layout_watchdog.py` | 6275 | `3B44D8E1C044150EB8B418CB0E44D5FBDB4DEF49D06068698895F52C2C2FB379` |
| `tests/test_round11_layout_inventory.py` | 21874 | `B03128FC4AC810B3CED5F710573DDD32A9415BE93D9986B1B1BD049294E558E5` |
| `tests/test_round11_layout_watchdog.py` | 3477 | `B0FAB96C0F47608150BB62ACE55D9E1875CD1CC4228B0C6C3D0B0DC363CE8ABE` |

所依据协议文件为 `outputs/validity/round11_daadx_layout_inventory_protocol.json`，字节数 9720，SHA-256 为 `E2E16BDE936CDE68B2D305322C7B33422F5F0043B45D833858E1BFB7C90740C5`。

本决定只适用于以上精确字节。任一候选文件或协议文件发生变化后，本决定失效，必须重新独立审阅。

## 审阅范围与禁止事项

本轮只审阅上述四个候选文件及其协议绑定。审阅者没有打开、列举或解析任何真实归档及其成员，没有读取真实标签、视频或模型输出，没有执行正式布局清点，也没有修改实现或测试。

因此，本轮明确保持以下边界：

- `no-real-data`：未访问真实数据；
- `no-claim`：未形成数据质量、指标有效性或研究有效性主张；
- `no-binding`：未把任何真实数据、运行结果或研究结论绑定进协议；
- `no-run`：未执行正式布局清点运行。

## 审阅迭代记录

### 第一次 `STOP_FIX`

第一次候选审阅发现三类阻断问题：

1. tar 格式识别未严格固定为精确 POSIX USTAR magic/version，存在错误格式进入后续路径解释的风险；
2. 资源与输出上限不完整，无法对内存、输出和相关累计量形成完整的失败关闭约束；
3. 任意回调 sink 可以保留 `MemberRecord` 中的原始路径，违反只允许受控流式落盘的隐私边界。

这些问题在后续候选中通过精确 USTAR 校验、冻结上限、具体受控 sink、流式输出和相关回归测试关闭。

### 第二次 `STOP_FIX`

修正后的候选仍存在三个可复现阻断问题：

1. watchdog 只在子进程仍存活时检查截止时间；子进程在截止时间后、下一次轮询前退出时可被错误接受。实测 `sleep 0.07`、`timeout 0.05`、`poll 0.2` 返回成功，记录耗时约 0.209 秒；
2. 即使要求 sink 为精确类型，实例仍有可写状态，调用方可覆盖 `_emit` 并保留完整原始路径；
3. `ResourceLimits` 可被子类覆盖 `validate()`，从而接受高于冻结最大值的资源上限。

最终候选改为按剩余截止时间 `wait` 并在退出后再次检查时限；`ResourceLimits` 禁止子类化、要求精确类型并采用非虚验证；`OwnedStagingSink` 使用 slots 和封印赋值，解析器以类限定方式调用 `_emit` 与 `close`。

### 最终独立重放

聚焦命令：

```powershell
$env:PYTHONPATH='src'; python -m pytest -q tests/test_round11_layout_inventory.py tests/test_round11_layout_watchdog.py
```

独立结果：`92 passed in 0.72s`。

既有三个反例的最终重放结果：

- watchdog 的 `sleep 0.07 / timeout 0.05 / poll 0.2` 案例在约 0.066 秒时以 `LayoutWatchdogError` 失败关闭；
- 对精确 `OwnedStagingSink` 实例赋值 `_emit` 被封印拒绝，解析完成后外部保留列表仍为 0，公开清单中不存在 `private/raw/path.bin`；
- `ResourceLimits` 子类定义被 `TypeError` 拒绝，精确类型但提高 `max_in_memory_bytes` 的实例也被非虚验证拒绝。

静态核验同时确认：精确写入循环、逐行写入前后的打开句柄/路径身份检查、输出上限、类限定 sink 调用、剩余截止时间等待以及退出后的截止时间检查均存在于所绑定候选中。

主任务报告的全套测试证据为 `490 passed, 9 skipped`。该数字明确标记为 **primary-run evidence**，本独立审阅没有重新运行全套测试，不能把它表述为独立复现结果。

## 委派工具记录

早期一次 DeepSeek 只读委派在取回阶段出现 `fetch failed`，没有形成可用实现证据。最终重放阶段的委派曾违反“不创建文件”的约束，短暂创建 `scratch_bypass_probe.py`，随后已删除；独立检查确认没有残留，工作区状态只显示四个预期的候选/测试文件。该委派输出不作为本决定的实现证据，最终判断以主审阅者直接读取的候选字节、独立聚焦测试及反例重放为依据。

## 正式集成必须满足的条件

后续正式运行器必须：

1. 绑定精确 worker 与完整 argv，不接受调用端自由替换；
2. 使用明确、最小且受控的环境变量集合，不继承与任务无关的环境或秘密；
3. 绑定并独占受控 staging cwd，保持输出路径、父目录和所有权假设；
4. 从结构上禁止 worker 创建后代进程；若未来允许派生，则必须先加入 Windows Job Object 或 POSIX process-group 级的整组终止控制并重新审阅；
5. 在运行前重新核验本备忘录绑定的四个候选文件和协议文件的 SHA-256 与字节数。

本审阅将“受信任模块代码在进程内被任意类级 monkeypatch”排除在对象输入威胁边界之外。允许攻击者任意改写 `ResourceLimits.validate` 或其他受信任类方法，等同于允许其修改正在执行的实现代码，不能作为当前对象协议的输入绕过；正式运行仍必须从受控、已绑定的代码版本启动。

## Claim boundary

`GO_IMPLEMENTATION_NOT_RUN` 只确认当前精确候选实现具备进入受控集成的条件。它不证明真实 DAAD-X 归档完整，不证明布局清点会通过，不证明数据可用于训练，不证明四项 ARSC 指标有效、合理、创新或具备外部有效性，也不构成任何 SCI 级研究结论。
