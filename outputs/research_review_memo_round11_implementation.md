# Round 11 DAAD-X preflight 实现独立审阅（最终）

## 0. 最终裁决

**`GO_FREEZE_PROTOCOL`。**

当前三个实现文件已经足以按既有方向裁决冻结 `round11_daadx_preflight_protocol.json`。该 GO 仅授权：把本次审阅的精确字节与 reviewer decision 一并提交到同一个 Git HEAD 后，运行一次 freeze script 生成不可覆盖的 protocol。

它**不授权**打开或列举 DAAD-X tar members、不授权视频解码或 formal preflight runner、不授权训练、validation tuning、test inference 或任何 ARSC 外部有效性主张。formal runner 及其 G0–G8 产物仍须另行独立审阅。

## 1. 结果盲范围

本审阅只读取并核对：

- `src/arsc_eval/daadx_preflight.py`；
- `tests/test_daadx_preflight.py`；
- `scripts/freeze_round11_daadx_preflight_protocol.py`；
- `outputs/research_review_memo_round11_direction.md`；
- `outputs/validity/round11_direction_reviewer_decision.json`。

未读取或列举大 tar、tar members、视频、DAAD-X 标签值或任何模型输出；未修改实现文件。

最终审阅 SHA-256：

| 文件 | SHA-256 |
|---|---|
| `src/arsc_eval/daadx_preflight.py` | `73639F1B85F84B2A27DC650E3DE1FC203A181561FA00306BCD5A5D2E76860E53` |
| `tests/test_daadx_preflight.py` | `20B79C7E2611AAC936C76F2516E0ACA7FE35C8F18D589C7D02CFD68A4D4D5DF2` |
| `scripts/freeze_round11_daadx_preflight_protocol.py` | `A1A182342B360F360E582E8F213315AE3B1043A55F5E629A7C73DA7E7B2E9B45` |
| `outputs/research_review_memo_round11_direction.md` | `47CE04714FF54085E11FD5D6D724BD690955F22C8E054F247170B1CEA3C6415A` |
| `outputs/validity/round11_direction_reviewer_decision.json` | `4C1683F83ED0921042FB30913743981D0153FA55D3C560C8DBBD5D946FA3B24C` |

审阅时三个实现文件尚未进入 HEAD `86530d1902ee272cc84d2981255a11453a73fb78`。这不是当前 GO 的例外条件：freeze script 会要求三个实现文件和本 reviewer decision 都存在于未来同一 HEAD，且 local bytes 与 `HEAD:path` blob hash 完全一致；未提交或提交后变化都会拒绝冻结。

## 2. 验证证据

- `PYTHONPATH=src python -m pytest tests/test_daadx_preflight.py -q`：`16 passed`；
- 三个目标文件 `py_compile` 通过；
- 8 个冻结前路径反例全部拒绝：多尾斜杠、ADS colon、segment trailing dot/space、`CON`、`NUL`、`COM1`、非 NFC 名称；
- case-insensitive collision 被拒绝；
- `[0,10,20,30,40,50]` 非连续六对不再匹配 broad near-overlap；
- pHash、normalized-frame SHA 与 SSIM 拒绝非 `(144,256) uint8` 正式输入；
- boundary API 显式接收并验证双方三个连续 0.5-second timestamps。

实现方报告全套 `110 passed`；本审阅机器的默认 Python 缺少旧测试所需 `cv2/ultralytics`，因此未独立复现该全套数值。本次授权依据是目标 16 项、反例、静态协议核对与编译通过；该环境差异不改变当前三个纯实现文件的审阅结论。

## 3. 阻断项关闭情况

### 3.1 冻结授权与版本绑定：关闭

freeze script 不再接受任意 implementation file 或任意 output：

- 固定绑定 freeze script、module、tests 三个文件；
- 结构化要求本 decision 的 schema 与顶层 `decision=GO_FREEZE_PROTOCOL`；
- 要求本 decision 的 `direction_decision_sha256` 与当前方向 decision 一致；
- 逐项核验 reviewer 记录的三个 SHA；
- 要求三个实现文件及 reviewer decision 的 local bytes 与同一 HEAD blobs 一致；
- 不再允许 `--output`；唯一正式输出固定为 `outputs/validity/round11_daadx_preflight_protocol.json`。

protocol、temporary、staging、final、log、artifact index 任一预存在都会拒绝冻结。写入使用 exclusive `xb` temporary、flush/fsync 和 `os.replace`；异常删除 temporary，不留下半正式 JSON。

### 3.2 路径与 archive 安全：关闭

路径 primitive 现拒绝绝对/drive/backslash/escape/repeated slash、ADS colon、控制字符、segment trailing dot/space、Windows device basenames、非 NFC 路径，并用 NFC+casefold collision key 拒绝大小写/Unicode alias。

机器 protocol 只允许 regular file 与 directory；symlink、hardlink、device、FIFO、socket、sparse/unknown 全部禁止；PAX 只能提供 metadata，不能绕过最终 canonical path 审计。后续 runner 必须逐 member 实现并接受独立复核，不能仅凭 protocol 文本把 G0 标 PASS。

### 3.3 near-duplicate、像素和 QA 合同：关闭

- aligned window 自身强制双方 0.5-second consecutive timestamps；六对、broad/strict 阈值与 `[0.98,1.02]` slope 保持不变；
- boundary 显式接收 tail/head times，并保留三对与相同非标签 rig signature 门；
- protocol 固定 RGB24 → BT.601 grayscale → half-pixel bilinear letterbox、目标 256×144、fill 0 与 rounding；
- pHash/frame SHA/SSIM 的正式输入必须为 144×256 uint8；SSIM 固定 data range 255、11×11 Gaussian window、sigma 1.5、reflect padding；
- QA 选择固定为 strict UTF-8 UUID SHA-256 排序及 UUID bytes tie-break；固定 50 个；
- transcode、resize、±5% brightness 的 codec、pixel format、CRF/preset/threads、尺寸/插值、公式、编码与处理顺序均已冻结，且每个 transform 要求 50/50 source recovery。

任何 QA 参数在看到真实 pair 或恢复率后都不得修改。

### 3.4 firewall、grouping、split 与门逻辑：关闭到 protocol-freeze 所需程度

- seal 返回对象只暴露 UUID/split 与原始 CSV SHA，不携带 individual labels；grouping/split 的标签值和模型结果继续禁止；
- 1,566 eligible UUID、1,566/1,566 front binding、禁止 complete-case deletion 均保留；
- G3 明确要求每个 clip 有 authoritative/auditable source provenance，absence of near duplicate 不能充当 provenance；content edges 只能进入保守 connected-components 合并；
- DAAD-X↔BDD-OIA 单帧阈值保持 pHash Hamming ≤10 且 SSIM ≥0.90，命中 quarantine 整个 DAAD-X source group；
- official split 仅在 group-disjoint 时保留，否则使用唯一 one-salt group split；
- canonical group ID 的 canonical UTF-8 JSON、uppercase SHA、namespace、first-64-bit big-endian integer boundaries 与 `val→validation` 已写入 protocol；
- G0–G8 仍为 AND-only；缺失或 INCONCLUSIVE 不能 GO；即使全 PASS，`training_authorized=False`。

完整 provenance validator、cross-dataset candidate generation、全视频 decoder、G7 计数和 G8 artifact closure 属于后续 formal runner，而不是当前 freeze primitive。当前 GO 不表示这些未来实现已经通过。

## 4. 必须保持不变的冻结边界

freeze 与后续 runner 不得修改：

- 1,566 eligible UUID 和 1,566/1,566 front hard gate；
- 2 Hz、first 0.25 s、step 0.5 s；
- broad：6 pairs、3.0-second window、pHash each ≤10、median ≤6、SSIM median ≥0.90；
- strict：pHash each ≤6、median ≤4、SSIM median ≥0.95；
- cross-dataset：pHash ≤10 AND SSIM ≥0.90，整组 quarantine；
- namespace `ARSC-DAADX-R11-GROUP-SPLIT-V1`、70/20/10 唯一 split、无第二 salt；
- 每 split ≥30 groups、test ≥100 clips、最大 test group share ≤10%；
- 16 项正式产物 allowlist；
- `GO_TO_SEPARATE_DAADX_PROTOCOL_FREEZE_REVIEW_NOT_TRAINING` 与 `STOP_DAADX_AND_SWITCH_TO_CANDIDATE_A_EXPLORATORY` 的语义。

## 5. 执行顺序

1. 将本 memo、最终 reviewer decision、三个实现文件及方向/scout 证据提交；不得在提交后修改被审字节。
2. 确认 protocol/staging/final/log/index/tmp 均不存在。
3. 运行 freeze script；由脚本自行核验本 decision、文件 SHA 与 HEAD blobs。
4. 保存 protocol SHA 并再次独立审阅未来 runner/preflight contract。
5. 只有后续 runner 获批才允许打开 tar members；当前不得提前用下载完成作为数据读取授权。

## 6. Claim boundary

`GO_FREEZE_PROTOCOL` 只说明当前纯 primitives、tests 与 freeze script 足以不可变地记录结果盲预检协议。它不说明 DAAD-X archive 完整、不说明 source groups 可重建、不说明近重复不存在、不说明 G0–G8 会通过，也不支持任何模型、ARSC、外部有效性或安全结论。
