# Round 6 Protocol Amendment 01 独立审阅

日期：2026-07-31  
对象：BDD100K-train v5 metadata gate 的 transport split 过滤  
审阅边界：未读取 BDD-OIA 候选交集，未计算 red/green state-match counts  
裁决：**GO 实施有界 amendment；gate 重启为 CONDITIONAL GO**

## 1. 事件边界

冻结协议为：

- preregistration commit：`1611eb4`
- protocol：`outputs/validity/bdd100k_train_v5_metadata_protocol.json`
- protocol SHA256：`F9B8843FB16F4DD6C61C883DB4F82347FAC009062EF78C99CFFA1ED66B8C7DB9`
- mirror revision：`d82c5188d392714ba8091d68014f7b9838ceadf2`
- semantic population：BDD100K Detection 2020 **train**
- population gates：total ≥200、red ≥50、green ≥50、independent clip groups ≥30。

第一次 metadata gate 在 `analyze_bdd100k_train_v5_gate.py` 的 row-level split 检查处中止：

```text
RuntimeError: non-train row found in train annotation result
```

只读核验确认该检查发生在：

- 读取 BDD-OIA test/train/validation manifests 之前；
- filename/clip-group intersection 之前；
- 图像 SHA256 计算之前；
- official state matching 和候选计数之前；
- candidate manifest 或 gate summary 写出之前。

当前不存在：

- `outputs/validity/bdd100k_train_v5_metadata_gate.json`
- `outputs/validity/bdd100k_train_v5_candidates.jsonl`

失败日志已保存，SHA256：

`E86353B27A2E722983157BDCACBD28DB13624899BBE3E197A7124784065F038E`

因此该问题仍处于 **pre-result engineering boundary**，没有 red/green 候选结果可用于适配协议。

## 2. transport split 的解释

HF Dataset Viewer API 参数中的 `split=train` 是镜像的 transport table 名称；返回 row 内的 `split` 字段保留 BDD100K 原始 train/val 身份。已获准的 split-only inspection 显示：

- row-level train：1,744；
- row-level val：268；
- 总 retained transport rows：2,012。

预注册的语义对象从始至终是 BDD100K Detection 2020 train。因此按：

```python
str(row["split"]).casefold() == "train"
```

保留 row，并排除原始 validation row，是在恢复冻结 estimand，不是根据候选数量或 state 分布改变 eligibility。

## 3. 允许的 amendment

允许仅修改 `scripts/download_bdd100k_enriched_annotations.py`：

1. 新 API response 中，只把 row-level split 为 train 的记录加入 retained rows；
2. resume 时，对现有 checkpoint rows 应用相同过滤；
3. BDD-OIA 2,233 个 keyframe IDs、batching、API endpoint、固定 revision、KEEP_FIELDS、超时/重试保持不变；
4. `analyze_bdd100k_train_v5_gate.py`、所有 eligibility/exclusion/hash 规则及 200/50/50/30 gates 保持不变；
5. 不生成 mask、不读取 checkpoint/logits、不运行训练；
6. amendment 冻结前后不得查看或计算 candidate/state-match counts。

该修改不授权：

- 同时查询 HF transport `validation` table；
- 合并 row-level val；
- 降低 population gates；
- 修改 sole-rationale、state normalization 或 traffic-light box 规则；
- 修改 filename、clip-group 或 image-hash exclusions；
- 修改 BDD-OIA evaluation population；
- 在结果出现后再次改变 split 解释。

## 4. 必须补充的工程修正

### 4.1 complete/resume 必须与“有意排除的行”兼容

现实现用：

```python
set(rows_by_id) == set(requested_ids)
```

判断 complete checkpoint 是否可直接复用。过滤非-train rows 后，该条件原则上不可能成立，因为 row-level val 和 API 无匹配 ID 都不会进入 `rows_by_id`。

必须把“查询已完成”与“train row 被保留”分开。允许两种方式：

- 首选：记录所有已完成的 requested IDs/batches，并用其判断 resume/complete；
- 或为本次一次性 rerun 归档旧 artifact 后从空 checkpoint 开始，并仍修正后续 checkpoint 的 complete 语义。

不得通过把 val rows 留在 checkpoint 中来满足 complete 条件。

### 4.2 val exclusion 与 API no-match 必须分别记录

新 artifact 至少单独记录：

- requested IDs；
- queried/completed IDs 或 batch count；
- retained original-train rows；
- excluded original-val rows；
- API no-row IDs；
- pre/post repository revision；
- retained fields only、no image bytes、no embeddings。

不能把 268 个已返回但因原始 split=val 排除的 IDs 全部误报为普通 “unmatched”。这不影响候选 gate 公式，但影响数据流可追溯性。

### 4.3 过滤必须在每次写 checkpoint 前发生

不能先把 val rows 写入 checkpoint、最后完成时才清理。每个 `write_checkpoint` 前的 `rows_by_id` 都必须已经是 row-level train only；resume 时也必须再次验证：

```text
all(retained row split casefold == "train")
```

缺失、null 或未知 split 一律不保留，并按独立原因计数。

## 5. 必须保存的 provenance

在 rerun 前写出 amendment record，至少包含：

- amendment ID 与时间；
- preregistration commit `1611eb4`；
- protocol path/hash；
- fixed mirror revision；
- 原 downloader：
  - bytes 9,951
  - SHA256 `3F1D0059412C0A50FE1952EC370C5771B43DBA1A63749723A0089E0D216FBE2E`
- 原 analyzer：
  - bytes 17,489
  - SHA256 `68EA66B7B24043AE38AB0682528B30D87E4F285EF5A506FC909F2C538283D095`
- 原 combined metadata artifact：
  - bytes 11,593,262
  - SHA256 `045945848E9BACFA063F758D940598F9080945D72952F63499FA1F1964F44481`
- 原 metadata log：
  - SHA256 `5225D8FE16F633776A9AAD10BBF723FF78C7C35EA01E79FA6BAA2BA5B44E4C8D`
- 原 failed gate log：
  - SHA256 `E86353B27A2E722983157BDCACBD28DB13624899BBE3E197A7124784065F038E`
- 只允许的 split inspection：1,744 train / 268 val；
- 明确声明 candidate/state counts 未计算、未查看；
- amended downloader 的 path/bytes/SHA256；
- exact diff；
- train-only/filter/resume tests 的日志 hash；
- 新 metadata artifact 的 bytes/SHA256 与 split-flow counts。

原 combined artifact 与失败日志必须归档或至少以不可混淆的 hash 记录保存，不能无痕覆盖。

## 6. 重启前 GO gates

以下全部通过才允许重启 metadata gate：

1. **Outcome-blind gate**  
   candidate manifest 与 gate summary 仍不存在；没有人运行其他脚本计算 state-match counts。

2. **Revision gate**  
   pre/post mirror revision 均严格等于 `d82c5188d392714ba8091d68014f7b9838ceadf2`。

3. **Split gate**  
   新 artifact 中 retained rows 的 original split 全部 case-insensitive 等于 train；val、missing、unknown 均为 0 retained。

4. **Completeness/provenance gate**  
   2,233 requested IDs 的查询完成状态可证明；original-val exclusions 与 API no-match 分开；checkpoint interruption/resume 测试通过。

5. **Frozen-analysis gate**  
   analyzer SHA256、protocol、BDD-OIA manifests、eligibility、hash exclusions 和 200/50/50/30 thresholds 均不变。

任一失败：**STOP，不运行 candidate gate。**

## 7. 重启边界

Gate 1–5 全过后：

1. 只重跑同一个 metadata gate；
2. analyzer 使用 train-only metadata artifact；
3. 允许 gate 首次读取冻结 BDD-OIA manifests、执行 hashes 并计算 candidate/state counts；
4. gate 结果无论 GO/STOP 都必须保存；
5. population gate 失败时执行原决策：

```text
STOP_CEG_POPULATION_NO_V6
```

不得再修改 split、eligibility 或样本门槛。

## 8. 最终裁决

### Amendment 实施

**GO**

把 combined transport table 按原始 row split 过滤为 train-only，属于恢复预注册语义的结果前工程修复。

### Metadata gate 重启

**CONDITIONAL GO**

只有完成 provenance、修正 complete/resume、区分 val exclusion 与 API no-match，并通过上述五项门槛后，才可重跑一次原 metadata gate。

### 自动 STOP

如果需要纳入 row-level val、修改候选规则、降低 200/50/50/30、发现已经计算过 candidate/state counts，或无法证明全部 2,233 IDs 在固定 revision 下完成查询，则本 amendment 失效并 STOP。
