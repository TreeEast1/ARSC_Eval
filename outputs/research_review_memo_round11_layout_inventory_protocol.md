# Round 11 DAAD-X layout-inventory protocol 独立结果盲冻结审阅备忘录

日期：2026-08-02  
裁决：`GO_FREEZE_COMMIT_LAYOUT_INVENTORY_PROTOCOL_NOT_RUN`

## 审阅边界

本次仅审阅以下 protocol 候选及其设计权威：

- `scripts/freeze_round11_daadx_layout_inventory_protocol.py`
- `tests/test_round11_daadx_layout_inventory_protocol.py`
- `outputs/validity/round11_daadx_layout_inventory_protocol.json`
- `outputs/research_review_memo_round11_layout_inventory_design.md`
- `outputs/validity/round11_layout_inventory_design_reviewer_decision.json`

审阅只读取候选和 Git 小型权威文件并运行纯合成测试。未读取 `data/`、真实 manifest、archive、chunks、标签或视频，未创建 layout/Phase1 claim，未运行 inventory、Phase1、G0–G8、训练或推理。DeepSeek worker 在执行前返回 `fetch failed`，未运行或写入；最终复现和裁决由主审阅者独立完成。

## Exact 候选字节

- generator：19850 bytes，SHA-256 `9F59962D14EBF81ED7B863F3059170A9E41D49B5AABEBCB3AE3FAE07A494AA42`
- tests：7372 bytes，SHA-256 `297F7A0832F337641D5785CD59C6DD9FDEB60C868316A98FC6FF1A8B0BD8450D`
- generated protocol：9720 bytes，SHA-256 `E2E16BDE936CDE68B2D305322C7B33422F5F0043B45D833858E1BFB7C90740C5`

Generator 从 exact authority bytes 重建的 canonical JSON 与候选 protocol byte-for-byte 一致。

## Authority 与非运行边界

Generator 精确核对 accepted transport receipt snapshot、receipt postgeneration decision、原 protocol、Phase1 amendment、amendment reviewer decision 和 layout design reviewer decision 的 SHA/schema；所有带 decision 的 authority 还要求 exact decision 值。它只读取这些小文件，不读取真实 manifest/archive/chunks。

Protocol 明确 `additive_only=true`、`result_blind=true`、`training_authorized=false`，不修改或覆盖原 protocol/Phase1 amendment，不产生 G0–G8 状态或 formal verdict。真实 archive/manifest 路径、bytes、SHA 只从 accepted receipt snapshot 声明中继承；protocol generation 不打开它们。

## Claim、路径与 closure

- layout claim 固定为 `outputs/validity/.round11_daadx_layout_inventory_attempt01.claim`；staging/final 使用独立 layout 路径，与 Phase1/formal 路径无重叠。
- 静态 HEAD-exact protocol/runner/tests/core/binding/reviewer identity 是 claim 前唯一允许的校验。
- claim 必须以 exclusive `xb` 创建并完成 file/strict parent-directory sync、open-handle/path identity 和关闭后 stable exact read，才允许任何 receipt/manifest/archive read、stat 或 hash。
- claim 在成功、STOP、普通异常、`KeyboardInterrupt` 或崩溃后永久保留；已有 claim/staging/final 只能 STOP 并转独立 attempt02。
- artifact allowlist 恰好 12 项，index 最后且 self-excluded；STOP 分支同样要求 exact hash closure、strict sync、atomic no-replace rename 和 post-publish rehash。

## Raw parser 与 payload firewall

Protocol 冻结单 gzip member、raw 512-byte tar/PAX state machine，禁止把 tarfile/libarchive 作为权威解析器。必须重算 compressed archive bytes/SHA，完整排空并验证 gzip header flags、可选 header CRC、CRC32、ISIZE 和 EOF，拒绝 concatenated/trailing compressed bytes。

Tar checksum 明确允许 stored octal 匹配 unsigned 或 signed standard sum 中任一个；禁止 base-256 numeric encoding。只允许 regular、directory、PAX `x/g`，拒绝 GNU longname/longlink、sparse、links、devices、FIFO 和未知类型；要求两个 zero end blocks，之后仅允许有界零 padding 至 gzip EOF。

PAX exact harmless allowlist 为 `path/size/mtime/atime/ctime/uid/gid/uname/gname/comment`。未知 key、GNU/sparse、SCHILY、link/linkpath、charset 等语义 key 全部拒绝；global `g` 禁止 path/size，只有 extended `x` 可覆盖 path/size；directory resolved size 必须为零。

Regular payload 唯一允许的物理行为是 1 MiB fixed buffer opaque drain/discard，以到达后续 header。禁止解析、保存、抽样、检查、内容 hash、日志或暴露给选择逻辑；只有有界 PAX metadata payload 可解析，payload retained bytes 为零。

## Bounds 与 OOM 防护

冻结：256 MiB dynamic memory cap、1 MiB compressed input/decompressed output/drain buffers、200000 logical members、400000 个固定 32-byte collision digests，以及 public inventory、restricted seal、structure summary 和 log 的独立输出上限。

Public inventory 与 restricted path seal 必须逐行直接写入 owned staging files；当前 member path 在行写入后释放，禁止在内存累计全量 raw/resolved path list。碰撞状态只能保存固定 32-byte digests。上述合同使 128 GiB uncompressed stream、16 GiB single regular member 等大数值只影响流式计数和运行时间，不触发等量内存分配。

## 选择与停止规则

- Public inventory 不含 raw paths；restricted seal 保留 raw/PAX/resolved path 的 hash-closed 映射且不得进入普通日志或 public Git。
- Annotation 必须分别找到唯一 train/val/test structural candidates。
- Front 必须形成唯一 full-match named-UUID regex，并绑定 selected path-hash set/count。
- Provenance 必须找到 exactly one structural candidate，但不得宣称 payload schema 有效。
- 缺失、重复或歧义一律 `STOP_LAYOUT_AMBIGUOUS_NO_PAYLOAD_DISAMBIGUATION`，禁止读取 payload 消歧。
- Runner outcome 恰好为 `LAYOUT_INVENTORY_COMPLETE_AWAIT_INDEPENDENT_SELECTION` 或 `STOP_LAYOUT_INTEGRITY_OR_POLICY_FAILURE`；均不是 Phase1/G0–G8 verdict。

## 测试证据与授权边界

命令：`python -m pytest -q tests/test_round11_daadx_layout_inventory_protocol.py`  
结果：`8 passed, 1 skipped in 0.16s`

唯一 skip 是当前 Windows 环境无法创建 symlink；generator 仍有显式 fail-closed 检查。测试覆盖 authority mutation、byte-exact generation、nonrun contract、claim-before-access、路径隔离、raw parser/PAX/payload boundary、bounds/memory streaming、12 artifacts、outcome/selection 和 no-overwrite 竞争者保留。

`GO_FREEZE_COMMIT_LAYOUT_INVENTORY_PROTOCOL_NOT_RUN` 仅授权提交上述 exact protocol generator/tests/generated JSON、设计权威和本次审阅证据。它不是 archive access 或 `GO_RUN`，不授权 claim、inventory、payload、Phase1、G0–G8、训练或推理。下一步只能实现 data-agnostic raw parser/runner/core 与纯合成微型 archive 测试，并再次接受独立代码安全审阅。
