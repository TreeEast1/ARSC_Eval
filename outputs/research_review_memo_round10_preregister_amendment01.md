# Round 10 amendment01 outcome-blind 独立复审（IMPLEMENTATION-ONLY GO）

审阅对象严格固定为 commit
`2f08aedbd1ffa4508a1a0bc1666e8333ce705e4e`
（tree `e36730b216a7a0dc13596ea25eaef9a3804b95ff`）。开始审阅时
`main` 与 `origin/main` 均指向该 commit；审阅期间出现的后续 README-only
提交不属于被审状态，也未改变任何 Round 10 被审文件。

本次复审始终保持 outcome blind：没有加载 checkpoint tensor，没有构造或加载
模型，没有运行推理，没有读取或计算任何 Round 10 非零 severity prediction、
logit、confidence 或 metric outcome，也没有编写、启动或审阅正式 analyzer。

## 1. 二选一裁决

**`AUTHORIZE_OUTCOME_BLIND_FORMAL_IMPLEMENTATION_ONLY`**

amendment01 已逐项关闭 STOP01 的五个 blocker。现在只授权编写正式实现、合成
单元测试、atomic one-shot launcher 草案和新的 no-outcome preformal
preflight。**正式运行仍为 `NOT AUTHORIZED`**；在完整正式实现及其所有直接和
传递依赖被单独独立审计并签发 formal-run GO 前，不得加载模型、产生 corruption
prediction cache 或运行任何非零 severity inference。

## 2. 被审快照与完整性

- attempt02 preflight base commit：
  `a53cc0326e6ed21197630097d92e9f0bef78fbe8`。
- commit `2f08aed…` 的唯一变更是新增 attempt02 preflight JSON 与测试日志；
  amendment、operator、validators、semantic artifacts 和所有原 STOP01
  证据均来自其父状态且在 `2f08aed…` 中保持不变。
- attempt02 preflight SHA256：
  `22B6FBA3F2BEF4BFA4FA64F665E30A1499BD343F097F9CAD62DC394F260B9863`。
- attempt02 test log SHA256：
  `E41F700BDCB46BF359DB3C2D18C66F6E38F70D8F1650B5B7640152E4E1ADDD24`。
- 本 reviewer 独立重哈希了 preflight 中的 54 个逐文件绑定：18 个
  code/protocol/audit/review 文件、11 个保留的 STOP01 文件、5 个 config、
  10 个 checkpoint 和 10 个 calibration 文件；SHA256 与 byte size 全部匹配。
- 15 个 amendment01/attempt02 核心文件的 working bytes 与
  `2f08aed…:<path>` Git blobs 全部一致。
- 数据 manifest、源 JPEG 和 checkpoint 大文件不进入 Git，但都由 attempt02
  逐文件或有序 inventory SHA256 绑定；因此准确表述是“完整的代码、协议、
  审计和 preflight 状态已提交，外部大输入 bytes 已哈希冻结”，而不是声称
  Git 本身携带全部数据和 checkpoint。

## 3. STOP01 五个 blocker 的关闭情况

| STOP01 blocker | amendment01 修复 | 独立判断 |
|---|---|---|
| practical endpoint threshold 的统计层级不唯一 | 每个 component 先保留 5 个 per-seed endpoint effects，再取 seeds 43–47 的无权算术均值；只用 observed five-seed mean 与阈值作 `>=` 比较；bootstrap endpoint interval 仅描述，不进入 practical gate | **CLOSED** |
| noise operator 的直接依赖未绑定 | 新 `corruption_dose_response_v2.py` 内联完整 filename-SHA256、PCG RNG、float32/float64 addition、clip 和 uint8 cast 语义；AST 无任何本地 `arsc_eval` import | **CLOSED** |
| bootstrap tail quantile 与 edge cases 未冻结 | 固定 replicate family-axis mean-bottleneck、共享 seed/clip draws、5000 replicates、`numpy.quantile(method="linear")`、Bonferroni `0.05/12`、exact-zero/NaN/F1/Jaccard/duplicate/expanded-count 规则及 mandatory raw arrays | **CLOSED** |
| semantic label judgment 与 manifest provenance 不可审计 | 新增 immutable raw manifest、100-row full-vector/name sidecar、30 张 label-visible pages、exact row-key/page-map/sidecar/build bindings、独立 reviewed manifest 和 raw→reviewed transition；严格 JSON boolean 与 override validation | **CLOSED** |
| preflight 依赖 summary 且缺少负向验证 | attempt02 从 test manifest 重算 RNG sample、filename/labels、1200 grid、12×100 strata、parameters、review decisions、page hashes 和 raw→reviewed transition；加入 schema、dependency、override、page、grid、formal/staging/cache refusal tests | **CLOSED** |

## 4. practical gate 与 bootstrap 的可实现性复核

amendment01 已把原先会导致不同实现给出不同 PASS/FAIL 的自由度关闭：

- A：Action-Only 与 Joint 两个 component 的 `level0 - level4` per-seed
  effect 分别取五 seed 均值，每个都必须 `>= 0.01`。
- R：Joint rationale Macro-F1 的 `level0 - level4` per-seed effect
  五 seed 均值必须 `>= 0.01`。
- S：Action-Only 与 Joint exact-tie-averaged AURC 的
  `level4 - level0` per-seed effect 分别取五 seed 均值，每个都必须
  `>= 0.01`。
- C1：两个 action flip 的 `level4 - level0` 和一个 rationale Jaccard 的
  `level0 - level4` 分别取五 seed 均值，三个 component 都必须
  `>= 0.025`。
- practical 比较使用未舍入 float64、`>=`、无 tolerance；exact equality
  通过。上述阈值被明确限定为预注册 operational conventions，并非外部验证的
  minimal important differences。
- 每个 bootstrap replicate 只抽一个五位置 seed vector 和一个 3904 位置
  source-clip vector，二者跨全部 family、level、model、axis、component、
  endpoint 和 diagnostic 共享；重复 seed/clip occurrence 保留。
- clip occurrence 按 canonical manifest order 展开所有 member images；
  每个展开 image occurrence 权重为 1，因此 replicate image count 可变化。
- 12 个 fixed family×axis gates 使用同一组 5000 shared draws；Bonferroni
  lower bound 的输入是每 replicate 的 five-selected-position
  family-axis mean bottleneck，quantile 为
  `0.004166666666666667`，`method="linear"`，未舍入 lower bound 必须
  严格 `> 0`。
- 2.5%/97.5% intervals 与 endpoint bootstrap 均为 descriptive
  pointwise results，不能被称为 simultaneous familywise intervals。
- 必须保存 `[5000,12]` gate draws、`[5000,5]` seed positions、
  `[5000,3904]` clip positions、`[5000]` expanded counts、全部
  component endpoint draws 及逐 quantile diagnostics。

该合同已足以唯一指导正式实现；正式实现是否忠实满足它属于下一次 preformal
audit，而不属于本轮授权。

## 5. operator 独立重放

新 operator SHA256 为
`58CF72A2E9247AB7725B14B79FEBCCBBFC739B757E7AE0C12E472551536C51D2`。
独立 AST 检查确认其本地 ARSC 依赖数为 0，不再 import
`src/arsc_eval/data.py::deterministic_noise`。

本 reviewer 在不加载模型的情况下，对冻结 RNG 抽出的 100 张图独立重放全部
family×level pixel transforms：

- level 0 identity：全部精确；
- level 4 repeat determinism：全部精确；
- level 2 noise：用独立写出的 filename-SHA256/PCG 算法比较，
  100/100 pixel-exact；
- 三 family mean absolute RGB distance 与 build summary 逐 float 相等：
  - brightness：`[0, 3.483344976128472, 7.30561382740162, 14.447619896556713, 20.99476916232639]`
  - blur：`[0, 0.5821405635127315, 2.1063078486689815, 3.3623635814525463, 4.358784986255787]`
  - noise：`[0, 1.9974695167824075, 3.9269884946469906, 5.839060926649306, 7.727437525318287]`

三组距离均随 operator level 非降。该结果只验证冻结 pixel operator dose，
不能将其解释为自然世界 severity。

## 6. semantic audit 独立重算与视觉复核

在不 import 项目 semantic validator 的独立脚本中复算确认：

- test manifest 为 4,557 唯一 filenames，SHA256
  `89364A265FE4C2EDCA5125D34C4C25D47C96AFB46A5C4A8FE86B649785539004`；
- source-clip count 为 3,904；
- 4,557 张源 JPEG 总计 `159486737` bytes；
- ordered source-image inventory SHA256 为
  `8034D044D55973917D0719A1CC829EEA002582420D6F7E05BB18F9AFF8894901`；
- `numpy.random.default_rng(20260810)` 重算的 100 个 sorted indices
  与 build 完全一致，array SHA256 为
  `510DD4B56FC25E2AEE79ED9F34E12722254E163F200DE423F7FD9D7F90E8523E`；
- raw manifest 恰有 1,200 个按 canonical order 排列的唯一
  `(audit_index,family,level)` keys，12 strata 各 100 rows；
- row-key SHA256 为
  `5896BE2225E37C4A0A936C9CC086699D20CDA91498D8E52B703AF690BB2679CD`；
- sidecar 的 4-action/21-rationale vectors 与 test manifest 逐 row 相等，
  positive label names 也由 vectors 独立重建并逐项匹配；
- raw manifest 决策字段全部为空，reviewed manifest 的非决策字段逐 byte-field
  不变，raw before/after SHA256 同为
  `3746450D250194963A3CD14AB32E2D7A359772189F3FA63E22543F41E92D304D`；
- 30 张 page files、review decision 与 build page map 全部精确相等；
  canonical page-map SHA256 为
  `F91AE2704162718F075F639A205EE65E3BC0CF61977193D4F564E17DCBBD2458`。

本 reviewer 还逐张查看了全部 30 张 labelled contact sheets。每个 row 均显示
action 和 rationale positive label names；三类 operator 的 level 1–4
均未观察到改变这些标签适用性或场景语义的反例。现有 12 个 strata 的 labels、
scene 和 joint rates 均为 1.0，超过冻结的 0.95 阈值。

这仍是单 reviewer、100-image audit，不是总体语义保存率的 95% 置信保证。

## 7. tests 与 attempt02 preflight

提交的 test log 记录：

`75 passed in 16.36s`

这里的准确含义是 **75 个全仓测试**，不是“75 个全是负向测试”。新增
`test_round10_protocol_validation.py` 含 8 个 test functions，其中包含多个
负向 cases，覆盖：

- practical threshold 与 Bonferroni quantile method mutation；
- duplicate、out-of-grid、non-boolean 和 extra-field overrides；
- unbound local operator dependency；
- incorrect semantic sample/grid；
- review/actual page-hash mismatch；
- analyzer、launcher、formal output、prediction cache、implementation
  manifest 和 staging/tmp paths。

本 reviewer 在 `PYTHONDONTWRITEBYTECODE=1` 且禁用 pytest cache provider 的
条件下独立重跑全仓测试，结果为 `75 passed in 16.42s`。测试代码中不存在
`torch.load` 或 checkpoint model inference 路径。

attempt02 对 18 个新状态文件和 11 个 preserved STOP01 文件逐文件记录
SHA256/bytes；对 5 configs、10 checkpoints、10 calibrations 逐文件记录
SHA256/bytes；并在 tests 前后枚举文件系统。其 outcome-blinding flags 均为
false/未发生，checkpoint 仅按 bytes 哈希，未用 torch 加载。

独立 target-tree 文件名检查与源码路径检查确认 `2f08aed…` 中不存在 Round 10
formal analyzer、launcher、results、primitives、bootstrap draws、
point diagnostics、formal log、prediction cache、implementation/run manifest
或 staging/tmp artifact。

## 8. 实现阶段的硬边界与下一 gate

本裁决生效后只允许：

1. 编写正式 analyzer、纯合成/fixture tests、atomic one-shot output policy
   和 launcher 草案；
2. 将完整实现的所有直接及传递依赖纳入新 hash manifest，至少包括 model
   definition、data pipeline、metric/F1/tie-AURC/Jaccard/calibration、
   clip grouping、bootstrap、serialization 和 launcher；
3. 保证实现或测试阶段不读取 checkpoint tensor、不运行真实 BDD-OIA inference、
   不创建 prediction cache 或任何非零 severity outcome；
4. 生成新的 no-outcome implementation preflight，并保留本轮全部证据；
5. 请求独立 preformal audit。

独立 preformal audit 必须确认实现逐公式吻合、所有 mandatory arrays 和
diagnostics 完整、shared-draw 语义正确、formal output 使用 atomic staging
和唯一 one-shot attempt、运行前目录为空、tmux launcher 只能在单独 GO 后调用。

在该 audit 签发明确 formal-run GO 前：

**`formal_run_authorized = false`**

## 9. 剩余科学 claim boundaries

即使将来 12/12 gates 全部通过，也最多支持：在冻结的 BDD-OIA 4,557-image
test population、五个既有 ResNet-50 seeds、固定 threshold/calibration 与三套
预注册 synthetic pixel grids 下，A/R/S/C1 与模型输出呈现预注册的严格
dose-response，并在 source-clip 与 training-seed 条件重采样下通过
12-gate familywise-controlled lower-bound 判据。

它不支持：

- natural corruption prevalence 或自然 severity 标尺；
- darkening、motion blur、optical defocus、真实 sensor noise 或天气域；
- 其他数据集、模型、训练协议、threshold、metric 或真实道路 robustness；
- rationale grounding/faithfulness、CEG 或因果证据；
- calibration validity 或 safety guarantee；
- 所有 rationale ontology classes 均有效；
- 指标本身具有普遍、数学必然的单调性。

brightness 可能改善部分暗图，因此严格方向是可证伪 empirical hypothesis，
不是 metric theorem。某一 gate 失败只能说明当前
metric×model×operator×BDD-OIA construct-response 未获支持；不得换 severity、
删 family、加 seed 或将失败直接推广为 ARSC 指标全局无效。

## 10. 最终裁决

**`AUTHORIZE_OUTCOME_BLIND_FORMAL_IMPLEMENTATION_ONLY`**

STOP01 的五个 protocol/preflight blocker 已关闭，完整被审 preoutcome 状态已由
commit `2f08aed…`、attempt02 文件哈希和外部输入哈希共同绑定。正式运行仍未
授权，下一 gate 是“完整正式实现 + 独立 preformal audit + 单独 formal-run GO”。
