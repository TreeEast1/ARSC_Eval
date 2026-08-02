# Round 11 DAAD-X 布局控制层实现独立审阅备忘录

## 最终结论

最终决定为 **`GO_CONTROL_IMPLEMENTATION_NOT_RUN`**。

该决定仅适用于下列两个文件的精确字节版本，表示数据无关的布局控制原语及合成测试已达到后续提交和正式 runner 集成所需的实现安全条件。它不是 execution binding，不授权读取真实输入，不授权获取正式 attempt claim，也不授权布局清点运行、候选选择、Phase-1、G0–G8、训练、推理或研究结论。

## 精确版本绑定

| 文件 | 字节数 | SHA-256 |
|---|---:|---|
| `src/arsc_eval/round11_layout_control.py` | 57960 | `7209EAAC75184D0C25F73FEC964900688310B7B6434608D6FE3DDCE7F57E2DA4` |
| `tests/test_round11_layout_control.py` | 34734 | `F587BE8CA087D1DB0A91FD40BDDD6B035A5408CADEA5EACAA83DAB0FCB999EF5` |

任一文件的字节或哈希变化都会使本决定失效，并要求重新独立审阅。

## 审阅边界

本审阅只使用实现代码、合成测试和临时目录中的合成微型产物。审阅期间：

- 未读取、列举、stat、resolve 或 hash 任何真实 receipt、manifest、archive、chunk、标签、视频或其他数据路径；
- 未创建 execution binding；
- 未创建或获取正式 `layout_inventory_attempt01` claim；测试中创建的 claim、staging 和 final 全部位于合成临时目录，仅用于控制原语验证；
- 未执行正式布局清点；
- 未形成数据质量、候选选择、指标有效性、外部有效性或训练授权主张；
- 未修改 control 候选、测试、README 或真实数据。

因此，本决定严格保持 `no-real-input / no-binding / no-formal-claim / no-run` 边界。

## 独立验证证据

独立运行命令：

```powershell
$env:PYTHONPATH='src'; python -m pytest -q tests/test_round11_layout_control.py
```

最终精确版本结果：`53 passed, 1 skipped in 4.09s`。

主任务报告全量回归为 `543 passed, 10 skipped`，并报告 `py_compile` 与 diff-check 通过。该全量数字明确属于 **primary-run evidence**；本独立审阅没有重新运行全套测试，不能将其表述为独立复现。

受限 DeepSeek 辅助端在最终轮次只读取两个候选文件并运行同一聚焦命令，报告 `53 passed, 1 skipped` 且无文件写入。该结果仅作辅助佐证；最终安全判断、代码审计和反例重放均由独立主审阅者直接完成。

## STOP_FIX 历史与关闭证据

### 第一轮 `STOP_FIX`：生命周期、authority 与 STOP 语义

第一版控制候选存在五项阻断问题：

1. `create_exclusive_staging` 与 finalizer 之间未绑定目录身份；创建后可整体替换 staging，替代树仍被发布并验证为有效；
2. archive hashes、structure summary、public/restricted 输出与 results 状态没有严格交叉验证，矛盾 STOP 仍可发布；
3. protocol、binding、reviewer 等 authority 只校验文件名，不校验期望字节数和 SHA-256；
4. claim 与输出父目录身份未贯穿整个 attempt，替换父目录后可在相同字符串路径获得第二个 claim；
5. `staging == final` 未在创建前拒绝，会提前物化 final 路径。

关闭证据：最终实现引入密封 `AttemptLease`，持有父目录、claim、staging 和 final 的生命周期身份；Windows 正式路径使用拒绝 delete/rename sharing 的句柄；每个 claim 边界重新流式哈希 claim 字节。staging 身份在创建后持有，在 no-replace rename 前才释放，rename 后要求 final 身份等于原 staging 身份。alias 在 `mkdir` 前拒绝。`ClosureExpectations` 精确绑定前五项 authority 的字节数与 SHA-256。closure 对 archive hashes、summary、results、authority、inventory 和 index 执行 canonical/schema/关系验证，并在哈希前后重复检查精确 allowlist。

### 中间反例：Python `bool` 冒充整数

在第二轮复核过程中，曾复现 canonical JSON 中的 `true/false` 通过 `isinstance(value, int)` 冒充 archive bytes、summary counts 或 restricted ordinal/size，并被发布为有效 closure。

关闭证据：最终实现对所有外部数值字段使用 `type(value) is int`，并加入 archive byte count、restricted numeric field 和畸形外部类型回归。验证 API 对外部畸形类型、Unicode 和数值错误统一失败关闭，同时不吞没内部 `AssertionError` 等程序错误。

### 第二轮 `STOP_FIX`：partial 尾片与 COMPLETE 资源一致性

修正后的实现仍有两项阻断问题：

1. `OBSERVED_PARTIAL` 强制 terminal newline 和 public/restricted 行数相等，无法在不篡改证据的情况下闭合 worker 硬终止留下的 restricted JSON 尾片或 public 领先一行；
2. COMPLETE closure 没有把 inventory 中的成员大小、类型与累计 payload 重新约束到 `DEFAULT_LIMITS`，也没有与 summary 聚合值交叉校验。曾复现超过冻结单 regular member 上限 1 字节的 COMPLETE 仍被发布。

关闭证据：最终 partial scanner 原样保留有界尾片；允许符合 sink 写入顺序的 public 领先不超过一行，并分别绑定 summary 的 public/restricted 完整行数。尾片本身由 artifact index 的精确字节数和 SHA-256 闭合。独立重放中，截断 restricted 尾部 5 字节、将 summary 更新为 public=1/restricted=0 后，STOP 成功发布、closure 验证通过且截断字节逐字节保留；若 summary 仍声称 restricted=1，则交叉验证拒绝。

COMPLETE 路径现在流式累计 regular/directory 数量与 regular payload 总量，逐成员执行冻结大小和逻辑成员上限，并与 summary 的 logical/type/total 字段逐项一致。summary 还受 raw-header、uncompressed tar stream、post-end padding 和结构字节关系约束。独立重放中，单 regular member 上限加 1 被 `regular-member size cap exceeded` 拒绝。

### 第三轮 `STOP_FIX`：resolved-path 去重和 Unicode 碰撞

前一候选没有在 closure 验证中重建 parser 的 resolved-path 碰撞状态。曾复现两行 COMPLETE 使用相同 resolved path/hash 时仍能成功发布并通过验证；Unicode casefold 等价而原字节不同的路径也存在同类风险。

关闭证据：最终实现对每个完整 public/restricted 配对行维护：

- `set[bytes]` 形式的 32 字节 resolved digest；
- `dict[bytes, bytes]` 形式的 NFC(casefold) digest 到 resolved digest 映射；
- 与 parser 相同的“加入前 `+2`”碰撞条目上限检查。

实现不累计原始或 resolved 路径。独立最终重放结果：

- 第二行与第一行 resolved path 完全相同：拒绝 `duplicate resolved path`；
- 第二行 `PRIVATE/...` 与第一行 `private/...`：拒绝 `casefold Unicode path collision`。

`max_logical_members=200000` 与 `max_collision_digest_entries=400000` 精确对应：第 200000 个完整配对行达到 400000 个固定摘要条目，更高 ordinal 已先被逻辑成员上限拒绝。

### PAX flags 规范顺序

最终 validator 要求 flags 与 parser 发射顺序完全一致：`PATH_OVERRIDE`、`SIZE_OVERRIDE`、排序后的 `GLOBAL_KEY_SHA256:*`、排序后的 `EXTENDED_KEY_SHA256:*`，并拒绝重复 flags。独立重放确认排序的 GLOBAL flags 被接受，逆序被 `public PAX flag order differs from parser output` 拒绝。

## 最终实现判断

最终 control 实现具备以下已核验性质：

- durable、exclusive、永久阻断的正式 claim 设计与生命周期身份复核；
- exact 12-artifact allowlist、index-last/self-excluded 和严格 canonical JSON；
- `HASH_CLOSED_STOP`、`NONPUBLISHABLE_RESIDUE`、`BLOCKING_FINAL_UNVERIFIED` 的失败关闭边界；
- exact authority bytes/SHA binding；
- public/restricted 流式配对、隐私字段、路径/hash/关系、partial 尾片和统计一致性验证；
- gzip/tar 布局 COMPLETE 的资源上限和结构聚合闭合；
- symlink、hardlink、fd/path TOCTOU、整目录替换和并发 extra-entry 防护；
- strict file/directory fsync、atomic no-replace rename、发布后流式重哈希和 crash residue 保留；
- restricted seal 最多 2 GiB 时仍以不超过 1 MiB 的缓冲区流式哈希，不整体物化大型 payload。

没有发现剩余的 impossible COMPLETE 或误导性 publishable STOP 绕过。

## Claim boundary

`GO_CONTROL_IMPLEMENTATION_NOT_RUN` 只授权提交当前精确 control/tests，并进入另行审阅的正式 runner 集成。它不授权读取真实 receipt、manifest、archive 或数据元信息，不授权创建 execution binding 或正式 claim，不授权正式布局运行、候选选择、Phase-1、G0–G8、训练、推理，也不证明 ARSC 四项指标有效、合理、创新或达到 SCI 结论标准。
