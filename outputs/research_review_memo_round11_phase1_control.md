# Round 11 DAAD-X Phase1 control primitives 独立结果盲审阅备忘录

日期：2026-08-02  
裁决：`GO_COMMIT_PHASE1_CONTROL_PRIMITIVES`

## 审阅边界

本次仅审阅以下两个未跟踪候选：

- `src/arsc_eval/round11_phase1_control.py`
- `tests/test_round11_phase1_control.py`

审阅只使用临时目录和合成字节，未访问 `data/`、DAAD-X archive、下载 chunks、transport receipt、assembler manifest、标签、视频或模型输出；未运行 Phase1、G0–G8、训练或推理；未修改候选。DeepSeek worker 在执行前连续返回 `fetch failed`，未运行测试或写入文件，最终测试和安全判断均由主审阅者独立完成。

## 裁决依据

候选已解决前两轮全部 STOP_FIX 阻塞，可提交为独立控制原语，但尚未获准集成 runner 或执行。

### 永久一次性 claim

- 使用 exclusive `xb` 创建固定 claim，已有 regular、stale 或 symlink 路径均阻断；两进程竞争恰好一个成功。
- 初始空文件先 file fsync，再 strict parent-directory sync，完成 fd/path identity 与 `nlink==1` 校验后才允许 hook。
- Windows 使用 `CreateFileW` 的 `GENERIC_WRITE | BACKUP_SEMANTICS | WRITE_THROUGH` 目录句柄及 `FlushFileBuffers`；POSIX 使用 directory fd 与 `fsync`。所有 open、flush、close 或 fsync 错误均传播，不存在 best-effort 成功。
- 普通异常、`KeyboardInterrupt`、第一轮或第二轮 file/directory sync 失败均保留阻断 claim，不执行自动删除或恢复。
- 写入 payload 并 file fsync 后，最终 parent-directory sync 在 claim fd 仍打开时执行，随后再次比较 fd/path identity；关闭后再用 stable no-follow read 比较 exact payload。
- 上轮尾部 TOCTOU 已复现关闭：本机 Windows 在第二次目录 sync 回调中阻止 `os.replace`，最终 claim 与返回 payload 精确一致；POSIX 若允许替换，随后的 fd/path identity 校验必须抛出 `Phase1ControlError`，替换路径仍保持阻断。

### 精确结果与 hash-closed publication

- artifact allowlist 与冻结 amendment 恰好一致：15 个 payload 加最后创建且 self-excluded 的 artifact index，共 16 个文件。
- results 只允许精确字段集、G0–G3 的 `PASS/FAIL/INCONCLUSIVE`、G4–G7 的 `DEFERRED_NOT_RUN_PHASE1`，并根据四门状态映射到两个且仅两个 outcome；禁止 G8 字段、formal G0–G8 verdict 和训练权限。
- results 和 index 均使用 duplicate-key-safe JSON 解析，并要求 raw bytes 与 canonical JSON 完全一致。最终目录中的 15 个 payload 被重新 stable-read、重算 bytes/SHA，并要求重建的 canonical index 与实际 index byte-for-byte 相同。
- 所有文件必须是 regular、non-symlink、`nlink==1`；stable read 使用 `O_NOFOLLOW`（平台支持时）、打开句柄与当前路径 identity 校验，以及读取前后 size/mtime/ctime 校验。
- 每个 payload 和 index 均 file fsync，staging 目录、共同父目录和 rename 后父目录均 strict sync。
- Windows `os.rename` 对已有 target 实测为 no-replace；Linux 仅使用 `renameat2(RENAME_NOREPLACE)`，符号或内核支持缺失时 fail closed，不使用可覆盖 fallback。
- rename 失败或竞争者 final 出现时保留完整 staging，且不删除或覆盖竞争者；post-rehash 失败时保留 blocking final，不执行危险 rollback。

## 测试证据

命令：`python -m pytest -q tests/test_round11_phase1_control.py`  
结果：`28 passed, 1 skipped in 0.68s`

唯一 skip 是当前 Windows 环境无法创建 symlink。普通/中断异常、两轮同步失败、两进程 claim 竞争、claim 两个替换窗口、duplicate/noncanonical results/index、artifact open 后替换、rename 失败、竞争者 final、篡改/额外文件和 post-rehash blocking final 均有纯合成反例覆盖。

独立补充复现确认：

- 最终目录 sync 期间替换：Windows 返回 replacement prevented，claim exact 为 true；
- 对已存在 target 调用真实 no-replace rename：抛出 `FileExistsError`，source 保留，竞争者 target 内容不变。

## 授权边界

`GO_COMMIT_PHASE1_CONTROL_PRIMITIVES` 仅授权提交上述两个 exact 候选及本审阅证据。它不授权 runner integration、不授权创建真实 attempt claim、不授权读取或 hash receipt/manifest/archive/chunks、不授权 Phase1 或 formal preflight、不构成 `GO_RUN`、G0–G8 证据、训练、推理或外部有效性结论。后续仍须完成 runner 集成测试、HEAD-exact execution binding 和独立 execution reviewer decision。
