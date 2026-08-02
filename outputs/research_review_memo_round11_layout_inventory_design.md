# Round 11 DAAD-X archive-layout inventory 最小方法设计审阅备忘录

日期：2026-08-02  
裁决：`GO_DESIGN_LAYOUT_INVENTORY_PROTOCOL_NOT_RUN`

## 审阅结论与边界

Round11 必须在 final Phase1 runner integration 和 execution binding 之前增加一个独立、result-blind、additive-only 的 archive-layout inventory 门。否则 annotation train/val/test exact members、front regex 和 provenance candidate 只能靠猜测。ffprobe 的静态路径、SHA、版本和能力绑定可以与 layout 工作并行，但不能替代该门。

本裁决只允许实现和冻结 layout-inventory protocol、runner、纯合成测试及非运行 binding 模板。它不是 archive access、inventory run、claim acquisition、Phase1 或 `GO_RUN` 权限。本次审阅未访问 archive、manifest 或 data 下源 receipt，未修改代码、原协议、Phase1 amendment 或数据。

## 当前静态权威绑定

- accepted receipt snapshot：`outputs/validity/round11_daadx_transport_receipt.json`，1629 bytes，SHA-256 `D738E21E5DC1976C192CFA3982E2CA2941FF3D2AF8A811BA432D51778A6B1C7F`
- receipt postgeneration decision：`outputs/validity/round11_transport_receipt_postgeneration_reviewer_decision.json`，6933 bytes，SHA-256 `050680A0014D489F68652DEFF87767A4BA92B0B087DE3DF400E8A6C25369F758`
- original protocol：`outputs/validity/round11_daadx_preflight_protocol.json`，9478 bytes，SHA-256 `01642976FAE14A43A25BDD65CA8D007E3C944D2B91771907ABE1B59553FAE880`
- Phase1 amendment：`outputs/validity/round11_daadx_phase1_diagnostic_amendment.json`，3916 bytes，SHA-256 `4B760550C75CF17B9EF32A9F203F1A63EB8428D90FEB4755C74B7A120D7430D9`
- amendment reviewer decision：`outputs/validity/round11_phase1_amendment_reviewer_decision.json`，5604 bytes，SHA-256 `3C27C0CAD8C39968329FA2BD322EB6B16CD6B2D2D5B0D23684369E58E77920F9`

所有这些文件在审阅 HEAD `6057f2134d760e7ed2b1c77b630da0800405a2a0` 中 tracked 且 byte-exact。

## Protocol 与 claim 顺序

新增独立 schema，例如 `ARSC_ROUND11_DAADX_LAYOUT_INVENTORY_PROTOCOL_V1`，明确：

- additive-only，不修改或覆盖原 protocol/Phase1 amendment；
- `result_blind=true`、`training_authorized=false`；
- 不产生 G0–G8 状态、formal verdict 或科学结论；
- attempt 固定为 `layout_inventory_attempt01`；
- claim 固定为 `outputs/validity/.round11_daadx_layout_inventory_attempt01.claim`；
- staging/final 固定为 `outputs/validity/round11_daadx_layout_inventory_attempt01.staging` 和 `outputs/validity/round11_daadx_layout_inventory_attempt01`，与 Phase1/formal 路径不重叠。

执行顺序必须是：

1. 只校验 HEAD-exact 静态 protocol、runner、tests、core、binding schema 和 reviewer identity；不得读取 receipt、manifest 或 archive 内容。
2. 使用 exclusive `xb` 原子创建 claim，写入 phase/attempt/binding SHA/random token，file fsync、strict parent-directory sync，并校验 path/inode。
3. claim 从创建瞬间起永久保留；成功、STOP、异常、`KeyboardInterrupt` 或崩溃均不得删除、复用或自动恢复。
4. claim 持久化完成后，才读取并核对 accepted receipt snapshot、真实 manifest 和 archive path/bytes/SHA。
5. 任何已有/stale/symlink claim、staging 或 final 都 STOP；恢复只能建立独立审阅的 attempt02。

## Raw gzip/tar/PAX 边界

禁止把 `tarfile`、libarchive 或其他会规范化路径的库作为权威解析器。必须实现 raw streaming state machine：

- 同一 opaque compressed scan 重算 archive bytes/SHA，与 accepted receipt 完全一致；
- 严格解析 gzip header/trailer，完整排空至 EOF，验证 CRC32 和 ISIZE；建议冻结为单 gzip member，拒绝 concatenated member 和 trailing compressed bytes；
- 逐块读取原始 512-byte tar header，自行验证 checksum、typeflag、size、name/prefix；
- 只允许 regular、directory、PAX `x/g`；拒绝 GNU `L/K`、links、devices、FIFO、sparse 和未知危险类型；
- 严格解析有界 PAX `<length> key=value\n` 记录，唯一 key、UTF-8，并正确应用 global/next-member `path`、`size`；
- 路径必须 UTF-8、NFC、相对 POSIX canonical，拒绝空组件、`.`/`..`、反斜杠、控制字符、Windows device/ADS、大小写或 Unicode collision、重复 resolved path；
- 要求两个连续 tar zero blocks；其后只允许有界全零 padding，随后必须到 gzip EOF；
- protocol 必须冻结 compressed bytes、uncompressed stream、member/header count、单 member size、累计 PAX bytes、path bytes 和 elapsed-time 上限。

顺序 tar 无法在物理上完全不读取 regular payload 的同时到达后续 header。因此唯一允许的 payload 行为是：固定小缓冲区 opaque drain/discard，以到达下一个 header。regular payload bytes 禁止解析、保存、抽样、日志、内容哈希或暴露给选择逻辑。PAX metadata payload 是唯一允许解析的 payload。若实现无法保证该隔离，应 STOP。

## 两阶段路径 seal 与选择规则

公开 inventory 不保留 raw path，只记录 ordinal、raw/resolved path SHA、type、size 和 PAX flags。另生成 restricted、hash-closed path seal，记录 raw header path、PAX path、resolved canonical path 及对应 SHA。`sealed` 表示不可自适应修改，不表示加密；该文件不得写入普通日志，只提供给独立 layout selector。

Selector 只能依据 path、type、extension、size、cardinality 和目录结构：

- 选择三个唯一 annotation candidates 并映射 train/val/test；
- 冻结一个带命名 `uuid` group 的 front full-match regex，并记录它选择的 path-hash 集合和数量；
- 选择最多一个 provenance candidate member，但不得宣称其 payload 已满足 provenance schema。

禁止读取 annotation/provenance payload、标签列或视频帧做消歧。候选缺失或不唯一时必须 `STOP_LAYOUT_AMBIGUOUS_NO_PAYLOAD_DISAMBIGUATION`。annotation UUID、front UUID 对应关系和 provenance schema 分别留给后续 G1/G3 验证。

## 建议 exact 12-artifact closure

1. `round11_daadx_layout_inventory_protocol.json`
2. `round11_daadx_layout_inventory_execution_binding.json`
3. `round11_daadx_layout_inventory_execution_reviewer_decision.json`
4. `round11_daadx_transport_receipt.json`
5. `round11_daadx_assembler_manifest.json`
6. `round11_daadx_layout_archive_hashes.json`
7. `round11_daadx_layout_structure_summary.json`
8. `round11_daadx_layout_public_inventory.csv`
9. `round11_daadx_layout_restricted_path_seal.jsonl`
10. `round11_daadx_layout_inventory_results.json`
11. `round11_daadx_layout_inventory.log`
12. `round11_daadx_layout_inventory_artifact_index.json`

Index 必须最后生成且 self-excluded，记录前 11 项 bytes/SHA。所有文件必须 regular、non-symlink、single-link，逐文件 fsync、目录 strict sync、atomic no-replace rename、post-publish rehash。运行失败也形成 exact closure；崩溃保留 staging 和永久 claim。

Runner 只允许两个 outcome：

- `LAYOUT_INVENTORY_COMPLETE_AWAIT_INDEPENDENT_SELECTION`
- `STOP_LAYOUT_INTEGRITY_OR_POLICY_FAILURE`

独立 selector 后续只能作出 `ACCEPT_LAYOUT_AND_FREEZE_CANDIDATES` 或 `STOP_LAYOUT_AMBIGUOUS_NO_PAYLOAD_DISAMBIGUATION`，不能签发 Phase1 `GO_RUN`。

## 最安全实施顺序

1. 实现 protocol generator/schema 与纯合成反例测试。
2. 独立结果盲冻结审阅并提交 protocol。
3. 实现 raw gzip/tar/PAX parser、claim、两阶段 seal 和 12-artifact publisher，只用微型合成 archives 测试。
4. 独立代码安全审阅并提交 exact runner/tests/core。
5. 生成 HEAD-exact layout execution binding。
6. 独立 execution reviewer 才可能另行签发一次 layout-inventory 运行权限。
7. 一次性运行 inventory 并进行独立 closure/selection review。
8. 并行固定 ffprobe absolute path/SHA/version/capabilities。
9. 只有 accepted layout selection 和 ffprobe binding 都完成后，才能集成 final Phase1 runner/binding。
10. Phase1 仍需新的独立 execution review；本裁决不能替代。
