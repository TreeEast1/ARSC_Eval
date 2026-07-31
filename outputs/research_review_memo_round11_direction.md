# Round 11 唯一方向最终裁决：先做 DAAD-X 结果盲完整性与来源泄漏预检

## 0. 最终裁决

**选择：`DAADX_PREFLIGHT_FIRST_THEN_CANDIDATE_A_IF_STOP`。**

Round 11 的唯一主任务应先是 DAAD-X 官方完整包的清单、媒体绑定、source-group 重建与近重复泄漏预检。原因是它是目前唯一仍可能提供独立外部总体的候选，而且该预检不需要训练、不读取 ARSC 模型输出，也不消费一次性的外部结果。直接进入候选 A 会放弃唯一尚未被否证的外部有效性机会，而 A 已明确只能产生同一 BDD-OIA/Round10 总体内的事后探索性增量。

该选择**不是 DAAD-X 训练 GO**。当前状态继续保持：

- external training：`STOP_ROUND11_EXTERNAL_TRAINING`；
- 唯一授权动作：`DAADX_DOWNLOAD_AND_GROUP_INTEGRITY_PREFLIGHT_ONLY`；
- 预检任一硬门失败或不可判定：`STOP_DAADX_EXTERNAL_LINE`，不得降低门槛、删掉不利样本或更换重复阈值，随后才可启动候选 A；
- 所有硬门通过：仅为 `GO_TO_SEPARATE_DAADX_PROTOCOL_FREEZE_REVIEW`，仍禁止训练、validation tuning、test inference 和 ARSC 成功主张。

下载已经开始只被视为 transport。18,585,647,156-byte 文件在完整下载、双读哈希、gzip/tar 与成员审计通过前，不被视为有效研究输入；下载期间不得读取视频内容并调整本协议。

## 1. 为什么不直接选择候选 A

Round7–9 已完成极端/分级 association-destruction 与 20-map 稳定性，Round10 已完成三类合成像素 corruption 的真实重新推理，并得到 3/12 严格门通过且全部属于 C1。候选 A 中仍有两个非同义反复的问题：clean uncertainty 对 incident failure 的预测，以及 C1 flip 的 harmful/beneficial/lateral 构成；但两者由已经看过的 Round10 结果生成，只能是 `post-result registered exploratory`。

DAAD-X 预检与它不同：预检回答“是否存在完整、来源可隔离且与 BDD-OIA 独立的外部总体”，这是发表层面更关键、当前证据尚未回答的问题。预检成本已因官方包下载开始而下降，且失败本身也是有结论的 feasibility evidence。因此顺序必须是：

1. 只做 DAAD-X preflight；
2. 若硬 STOP，永久关闭 DAAD-X 训练线；
3. 才按 `research_review_memo_round11_candidate_methods.md` 的边界做候选 A，不把 A 改称外部或确认性验证。

## 2. 已知风险与官方 loader 约束

截至冻结时，官方 HF split 并集为 1,566 个 UUID，而论文写 1,568；HF front view 只覆盖 1,427/1,566，缺 139 个，且缺失率随 maneuver 与稀有 explanation 类别变化，不能假设 MCAR。

官方代码 commit `932c463b10f2cad42d2d3854376b40a919f47d0a` 的 `models/utils/loader.py` 还存在两个会改变研究总体的行为：

- 初始化时只把 `road_path` 存在的 CSV 行加入 dataset，缺失视频会被静默排除；
- decoder 在每个时间区间使用 `random.randint` 选择帧；若解码为空，`__getitem__` 会移动到下一个 index，而不是为原 UUID 产生显式失败记录。

因此预检**不得实例化或复用官方 dataset loader**。必须从 tar member inventory 和冻结 CSV UUID 并集出发逐条检查；任何缺失、解码失败或替代 index 均以原 UUID 显式记录。所有抽帧只允许下面冻结的确定性时间点。

## 3. 结果盲防火墙

### 允许读取

- 官方 tar 的 HTTP receipt、压缩包字节、tar headers、成员路径/大小/mtime；
- 视频容器 metadata、codec、duration、fps、frame count、可解码状态；
- UUID、官方 split membership、路径/文件名中的 source/session token、`time.csv` 的非标签时间字段及多视图同步关系；
- 为完整性和近重复检测而确定性解码的像素；
- BDD-OIA 冻结图像输入，仅用于跨数据集近重复检查。

### 对 grouping 进程不可见

- maneuver、gaze 与 17 维 ego rationale 的值；
- 任意 BDD-OIA、Round10 或 DAAD-X 模型 logits、predictions、confidence、loss、metric；
- 任何 validation/test 模型输出；
- 根据 label prevalence 或模型效果生成的 subgroup。

CSV 可被独立的 sealing 步骤按原始字节哈希；grouping/split 程序只接收 UUID 与原始 split 名称。scout 已读取过聚合标签分布，因此本轮不能声称“标签从未被看过”；防火墙的可审计主张是**分组、媒体纳入和近重复阈值不读取标签值或模型结果**。

### 禁止的操作

- 模型训练、checkpoint 加载、validation tuning、test inference；
- 用官方 loader 生成一个经过静默删除或随机抽帧的总体；
- 人工看 pair 后删除 near-duplicate edge，或根据 cross-split pair 数调整阈值；
- 只下载/保留当前 HF 可用的 1,427 条 complete cases；
- 用 maneuver/rationale 平衡性修改 source groups 或重分 split；
- 对 driver-facing 视频做人脸识别、身份推断或发布生物特征；
- 发布视频、帧、可逆人脸/cabin fingerprint 或原始敏感 source identifiers。

## 4. 冻结总体与完整包清单

### 4.1 archive gate

官方输入固定为：

- URL：`https://cvit.iiit.ac.in/images/datasets/daadx/daadx.tar.gz`；
- 预期 Content-Length：`18,585,647,156` bytes；
- 数据源版本证据：官方代码 commit `932c463b10f2cad42d2d3854376b40a919f47d0a`、HF revision `35eddaa90667beffc5481e014df8fc6176ed0168`。

本地文件必须满足：精确字节数；两次独立顺序读取的 SHA-256 完全一致；gzip 完整性通过；tar 从头到尾可列举；canonical member path 不重复、不绝对、不含目录逃逸；成员 header checksum 有效。官方没有发布可核验 SHA-256 时，只能声称“本地下载已绑定并通过压缩/成员完整性检查”，不能声称与作者端 checksum 相等。

### 4.2 frozen eligible population

预检的目标总体固定为官方 `train.csv + val.csv + test.csv` 的 1,566 个唯一 UUID 并集，不用 `total.csv` 的 1,725 行或 `time.csv` 的 1,951 行替代，也不把包中额外媒体事后加入总体。论文的 1,568 与当前 split 的 1,566 差异必须记录，但未知两条不能自行补标。

每个 UUID 必须：

- 唯一绑定到恰好一个 front-view member；
- 可从首帧到尾帧完整解码，无空视频、截断、非法 duration/fps/frame count；
- member SHA-256、decoded-frame count、duration/fps/codec 与错误状态被显式保存；
- 其他视图只用于 source/session 证据与同步审计，不作为未来模型输入授权。

**硬门固定为 1,566/1,566 front-view 全覆盖且全解码通过。** 任一正式 UUID 缺失、重复绑定或不可完整解码即 STOP。鉴于 HF 缺失已经显示标签相关波动，本轮不允许再用“结果盲 complete-case population”补救。

## 5. source grouping 的结果盲重建

### 5.1 独立单元定义

独立单元是产生一个或多个 7–15 秒 clips 的最上游可审计 raw recording/capture session；clip UUID 不是独立单元。未来只用 front view 并不降低 source leakage 要求。

### 5.2 重建优先级

对全部 1,566 nodes 在叠加官方 split 之前构图，group 为无向图 connected component。边的优先级和来源固定为：

1. **作者/包内权威键**：相同 driver/session/raw-video/source ID 必须连边；同一 raw recording 的所有 clip intervals 必须同组。
2. **可审计 metadata 重建**：若无直接 session ID，只有在包内存在不依赖标签的 raw-recording token，或完整 acquisition timestamp + camera-rig/multiview synchronization identifier 时才允许重建；同一 raw token，或同一同步采集流的重叠/连续 interval，必须连边。
3. **内容证据只做保守合并**：exact media、decoded duplicate、near-overlap 与 boundary-continuity edge 只能把已有组进一步合并，不得用“没有检测到近重复”证明所有 singleton 真独立。

100% eligible clips 必须有权威键或第 2 类可审计 source/session provenance。若仅剩 UUID 和像素、无法证明 source/session 完备性，即使 near-duplicate graph 没有跨 split edge，也必须 STOP。人脸识别不被允许作为缺失 source key 的替代品。

公开产物只保存 salted source-group ID、group size 和 edge provenance；原始 driver/session/source identifiers 保留在不提交的本地受限映射中。

## 6. 近重复阈值：运行前固定，不按结果调整

### 6.1 确定性指纹

- 用固定 ffmpeg build 与单线程确定性解码；每个视频按完整 duration 以 2 Hz 取样，时间戳为 `0.25 + 0.5*j` 秒且严格小于 duration；不足一个采样间隔的视频直接失败。
- 每帧按长宽比 letterbox 到 256×144、转灰度；计算 64-bit DCT pHash（32×32 DCT，左上 8×8、排除 DC、按其余系数中位数二值化）和 normalized-frame SHA-256。
- 候选检索实现可使用 LSH，但最终 edge 只能由下面的完整 pair verification 决定；LSH 必须用 exhaustive audit subset 验证无漏检。

### 6.2 固定 edge 规则

以下任一成立即连边：

1. `BYTE_EXACT`：完整媒体 SHA-256 相同；
2. `DECODE_EXACT`：对齐采样帧的 normalized-frame SHA-256 序列相同；
3. `NEAR_OVERLAP_BROAD`：存在时间顺序一致、时间尺度斜率在 `[0.98, 1.02]` 的连续对齐窗口，长度至少 6 个 2-Hz frame pairs（至少 3.0 秒），其中每对 pHash Hamming distance ≤ 10、窗口 median ≤ 6，并且灰度 SSIM median ≥ 0.90；
4. `BOUNDARY_CONTINUATION_BROAD`：一个 clip 最后 1.5 秒与另一个 clip 最前 1.5 秒形成 3 个有序 frame pairs，pHash Hamming distance 均 ≤ 10、median ≤ 6 且 SSIM median ≥ 0.90，并且两者具有相同的非标签 camera-rig/multiview synchronization signature。

另行报告但不用于放松 broad graph 的 strict sensitivity view：3.0 秒窗口内每对 pHash ≤ 6、median ≤ 4、SSIM median ≥ 0.95。**正式 grouping 和泄漏门一律使用 broad edge**；strict/broad pair 数都要报告，结果出来后不能切换。

阈值由方法审查在 pair 列表生成前冻结。实现 QA 使用由 UUID SHA-256 选出的固定 50 个视频制作本地、不发布的确定性转码/resize/±5% brightness 正对照；broad rule 必须恢复全部来源关系。QA 失败只允许修复实现错误并由独立审阅重新冻结，不能根据真实 cross-split pair 调参。

### 6.3 检查范围

- DAAD-X 全部 1,566 clips 两两候选检索与验证；
- DAAD-X 与当前冻结 BDD-OIA 4,557 images 的跨数据集检查，BDD-OIA 图像视为单帧，匹配阈值仍使用 pHash ≤10 且 SSIM ≥0.90；单帧 cross-dataset match 只触发 quarantine/review，不用 3 秒条件；
- 所有 exact/near pairs 和距离均保存，不因 official split 相同而省略。

任何 DAAD-X source group 命中 BDD-OIA broad cross-dataset match 时，整个 DAAD-X group 按预先规则 quarantine；不是只删命中的 clip。quarantine 后重新计算完整性之外的 group/split 规模门。该过滤只基于输入相似性，不基于标签或模型效果。

## 7. split 叠加与冻结

group graph 完成并写入不可变 artifact 后，才允许叠加官方 train/val/test membership：

- 若每个 source group 只出现在一个官方 split，保留官方 split；
- 若任一 group 跨官方 splits，发布 split 被判为 leakage-fail，但不自动永久停止 DAAD-X；全部未 quarantine groups 用下面固定 hash rule 重分；
- canonical group ID 为其排序 UUID 列表的 SHA-256；`u` 为 SHA-256(`ARSC-DAADX-R11-GROUP-SPLIT-V1|canonical_group_id`) 前 64 bits 除以 `2^64`；`u<0.70` 为 train，`0.70≤u<0.90` 为 validation，`u≥0.90` 为 test；不按标签平衡或手工交换 group。

重分后必须 train/validation/test 各至少 30 个 source groups，test 至少 100 个 eligible clips，且任一 test group 不得占 test clips 的 10% 以上。任一规模门失败即 STOP；不得尝试新 salt。标签支持与 action/rationale protocol 不在本预检中判定，须在预检 GO 后另行结果盲冻结并审阅。

## 8. GO / STOP 门

全部门是 AND，不做多数表决：

| 门 | GO 条件 | STOP / INCONCLUSIVE 条件 |
|---|---|---|
| G0 transport/archive | 精确 18,585,647,156 bytes；双读 SHA 一致；gzip/tar/header/path 全通过 | 任一失败；一次官方断点重取后仍失败则永久 STOP |
| G1 frozen population | split UUID 唯一并集恰为 1,566，且 1,566/1,566 唯一 front binding | count/UUID 冲突、缺失、额外替换或多重绑定 |
| G2 decode | 1,566 个 front videos 全视频解码通过且 metadata 合法 | 任一空、截断、不可解码或 loader-style substitute |
| G3 source provenance | 100% clips 有权威或可审计 raw-source/session provenance | 仅 UUID/像素、provenance 不完整、需人脸识别才可补齐 |
| G4 grouping reproducibility | frozen broad graph 两次独立运行 byte-identical；QA 50/50 恢复 | 非确定、漏检、真实 pair 后调参或 edge 人工删改 |
| G5 cross-dataset independence | BDD-OIA match groups 整组 quarantine 后仍通过后续门 | 保留 matched group、仅删 clip，或 quarantine 后规模失败 |
| G6 split independence | 保留官方 split 或固定 one-salt grouped split 后 group intersections 全为 0 | 任一 group 跨 split，或使用标签/人工换组补救 |
| G7 cluster adequacy | 三 split 各 ≥30 groups；test ≥100 clips；最大 test group share ≤10% | 任一不满足 |
| G8 artifact closure | 清单、pair、group、split、日志与 index 全部 hash 闭合，无 staging/未解释异常 | 缺产物、hash 不符、日志无唯一成功退出或存在静默删样本 |

`G0–G8` 全通过的唯一结论是：`GO_TO_SEPARATE_DAADX_PROTOCOL_FREEZE_REVIEW_NOT_TRAINING`。任何门失败或信息不足的结论是：`STOP_DAADX_AND_SWITCH_TO_CANDIDATE_A_EXPLORATORY`。不得把 `INCONCLUSIVE` 当 GO。

## 9. 预检正式产物清单

实现前应固定到一个只增不改的 attempt 目录；最少产物为：

1. `round11_daadx_preflight_protocol.json`：本备忘的机器可执行镜像、依赖版本和 forbidden inputs；
2. `round11_daadx_download_receipt.json`：URL、HTTP headers、时间、预期/实得 bytes；
3. `round11_daadx_archive_hashes.json`：两次读取得到的 archive SHA-256 与 gzip/tar 状态；
4. `round11_daadx_tar_inventory.csv`：全部 canonical members、size、mtime、header status；
5. `round11_daadx_member_hashes.csv`：所有相关成员 SHA-256；
6. `round11_daadx_label_seal.json`：原始 CSV hashes、解析器版本、仅 UUID/split 可见声明；
7. `round11_daadx_uuid_media_binding.csv`：1,566 UUID 到 media 的一对一绑定及显式错误；
8. `round11_daadx_media_probe.csv`：codec、fps、duration、frames、全解码状态；
9. `round11_daadx_threshold_qa.json`：50 个 hash-selected 正对照的恢复率与固定阈值；
10. `round11_daadx_duplicate_edges.csv`：全部 exact/broad/strict edges、距离与证据类型；
11. `round11_daadx_cross_dataset_overlap.csv`：DAAD-X↔BDD-OIA pair 与 quarantine group；
12. `round11_daadx_source_groups.csv`：salted group IDs、members、provenance class、group size；
13. `round11_daadx_split_audit.csv`：official split overlap 与必要时的 one-salt grouped split；
14. `round11_daadx_preflight_results.json`：G0–G8 的逐项证据及唯一 verdict；
15. `round11_daadx_preflight.log`：命令、环境、异常和唯一 exit marker；
16. `round11_daadx_artifact_index.json`：前述正式产物的 path/bytes/SHA-256 闭包。

原始视频、帧、未脱敏 source IDs、生物特征或可逆 fingerprints 不进入 Git；只提交代码、协议、哈希、脱敏清单和派生统计。若底层 DAAD 媒体权利未进一步明确，任何媒体重分发继续禁止。

## 10. claim boundary

预检 GO 只允许表述：

> 在官方 DAAD-X 18,585,647,156-byte package 与当前 1,566-UUID split snapshot 上，front-view media completeness、可解码性、source-group provenance、近重复/跨数据集重叠及 grouped-split independence 已按冻结的结果盲规则通过审计。

它不支持：

- 任何 ARSC 指标有效、模型性能、外部泛化或道路安全主张；
- DAAD-X 与 BDD-OIA 构念完全等价；
- 7 类互斥 maneuver 等同 BDD-OIA 四项多标签动作；
- 原生 17 类 ego explanations 等同 BDD-OIA 21 类理由；
- 自然 weather severity 或自然 corruption dose-response；
- rationale grounding、faithfulness、因果解释；
- 未匹配到 near duplicate 就证明 driver 独立。

即使以后另行获批训练，DAAD-X 也只能是相邻构念的外部验证：U-turn 排除，Slow/Stop 构念歧义显式保留，R 使用原生 17 类，21 类 crosswalk 仅描述性；自然 severity 仍记为 `UNAVAILABLE`，brightness/blur/noise 只能称合成像素扰动的跨数据集复现。

若预检 STOP，允许的后续声明仅是“DAAD-X 当前发布物无法满足完整性/来源隔离的验证性门”；随后候选 A 仍按既有备忘作为同一 BDD-OIA 总体内的探索性补充，不能弥补外部有效性缺口。

## 11. 审阅终态

- 唯一当前方向：`DAADX_DOWNLOAD_AND_GROUP_INTEGRITY_PREFLIGHT_ONLY`；
- external model experiment：继续 STOP；
- candidate A：冻结为 DAAD-X STOP 后的唯一探索性 fallback；
- 预检代码/训练：本审阅未实现；
- Round7–10 protocol、outputs 与 verdict：不得修改。
