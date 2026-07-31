# Round 10 outcome-blind 预注册 / preflight 独立审阅（STOP01）

审阅范围：Round 10 corruption dose-response 协议、像素算子、语义审计、preflight、测试日志和 Round 9 授权决定。审阅期间没有加载模型、没有运行推理、没有读取或计算任何 Round 10 非零严重度 prediction、logit、confidence 或 metric outcome，也没有编写或启动正式分析。

## 1. 二选一裁决

**A）`STOP/REPAIR_PROTOCOL_PREFLIGHT`**

当前不授权正式实现，也不授权正式运行。

研究方向、三类 operator、五级 severity、family×axis 结构和共享 seed+clip bootstrap 的总体思路合理；但当前冻结协议仍有无法唯一实现的 practical-threshold 规则，preflight 没有绑定 noise operator 的直接代码依赖，semantic gate 的 label-applicability 判断缺少可见 label 证据，且所谓“新 operator/preflight tests”实际只有四个 operator tests。上述问题均发生在任何新 severity 模型 outcome 产生之前，可以进行 outcome-blind 修复，但必须保留本次 STOP 痕迹并重新接受独立审阅。

## 2. 已独立确认通过的内容

### 2.1 没有结果泄漏

源码检查显示：

- `src/arsc_eval/corruption_dose_response.py` 只定义像素变换，没有模型或 metric 代码；
- semantic-audit builder 只读取冻结 test manifest 与源图像并生成 contact sheets；
- preflight 不 import `torch` 加载 checkpoint，只对 checkpoint bytes 做 SHA256；
- 当前没有 Round 10 formal analyzer、launcher、prediction cache、result、primitive、bootstrap draw、diagnostic CSV 或 formal log；
- preflight 记录的七个 formal artifact/cache absence 项在独立复查时全部仍为 true；
- `outcome_blinding` 中四项非零严重度 outcome 标志均为 false，与源码可达路径一致。

所以当前协议仍保持 outcome blind，允许修订，不涉及看到结果后改门槛。

### 2.2 冻结输入绑定可复算

独立只读复算确认：

- test manifest 为 4,557 个唯一 filename；
- source clip 规则得到 3,904 clips；
- 4,557 张源图像总大小为 `159486737` bytes；
- ordered source-image inventory SHA256 为  
  `8034D044D55973917D0719A1CC829EEA002582420D6F7E05BB18F9AFF8894901`，与 preflight 完全一致；
- 五个 config、十个 checkpoint、十个 calibration file 的文件大小与 SHA256 全部匹配 preflight；
- Round 9 授权决定 SHA256 为  
  `7D362D283493440A2365149BADE802F6CA3B56FCED9824A7B5A5056571F387B3`；
- protocol、semantic artifacts、operator code、scripts、test 与 test log 的现有 hash 均匹配 preflight，没有发现静默替换。

`preflight_base_commit=debf928daefd573e4ebf893a91d235cb6e14c1e7` 本身不包含当前未跟踪的 Round 10 文件，但 preflight 的逐文件 content hashes 可以识别其实际状态。后续进入 implementation-only GO 前应把完整 preoutcome 状态提交，不能只引用该 base commit。

### 2.3 operator / construct

冻结 grid 与代码一致：

| family | level 0–4 |
|---|---|
| brightness | 1.00, 1.05, 1.10, 1.20, 1.30 |
| Gaussian blur radius | 0.0, 0.5, 1.0, 1.5, 2.0 |
| Gaussian noise std/255 | 0.0, 2.5, 5.0, 7.5, 10.0 |

level 2 参数与历史 RQ2-light 设置一致；level 0 的 synthetic identity test 通过；noise 使用 filename-specific deterministic field 并随 level 缩放。100-image audit sample 上三类变换的 mean absolute RGB change 均随 level 非降，level 0 identity 与 level 4 repeat determinism 均通过。

科学上必须把 operator 命名限制得更窄：

- brightness grid 只验证“全局增亮”，不验证暗化、曝光变化全域或低光；
- blur 是 Gaussian blur，不是运动模糊或真实镜头失焦；
- noise 是 JPEG decode 后加入的 deterministic iid Gaussian RGB noise，不是真实传感器噪声；
- 参数/像素距离是预固定 operator dose，不是自然世界 severity 标尺。

严格的 A/R 下降、AURC 上升、flip 上升、Jaccard 下降是可证伪的模型×数据×operator 假设，不是这些 metric 的数学必然性质。尤其全局增亮可能改善某些暗图；若将来出现 reversal，必须如实报告当前 construct gate 未通过，不能直接写成“该 metric 无效”。

### 2.4 family×axis bottleneck、12-gate multiplicity 与共享 bootstrap

以下设计是清楚且原则上合理的：

- 每个 family×axis×seed 先对全部 required components 和四个 adjacent severity steps 取 expected-direction minimum；
- 每个 family×axis 报告五个 seed bottleneck、其算术均值和至少 4/5 seed strictly positive；
- family 不参与 primary pooling，固定为 3 families × 4 axes = 12 gates；
- 每个 bootstrap replicate 只抽一次五 seed positions 和一次 3,904 clip positions，并把二者共享给全部 family、severity、model、axis 与 diagnostics；
- clip 被抽中后扩展其全部 member images，metric 与 seed-level bottleneck 在每个 replicate 内重新计算；
- Bonferroni one-sided lower quantile 使用 `0.05/12 = 0.004166666666666667`，这一公式正确；
- ordinary 2.5%–97.5% intervals 只能称为 descriptive pointwise intervals；只有 12 个 Bonferroni lower-bound gate 的交集才能称 familywise controlled。

但低尾 quantile 的具体 interpolation/method 尚未冻结，见阻断项 3。

### 2.5 100-image × 12-stratum semantic audit 的实际结构

独立结构复算确认：

- seed `20260810` 重新抽样得到的 100 个 sorted dataset indices 与 build summary 完全一致；
- manifest 恰为 1,200 个唯一 `(audit_index, family, level)` keys；
- 每个 nonzero family×level stratum 恰有 100 rows；
- filename 与 dataset index、operator parameter、family 和 level 均与冻结 manifest/grid 精确对应；
- 当前 reviewed manifest 中 2,400 个布尔决定全部为 true；
- 30 张 contact sheets 的文件 hash 全部匹配 build summary 和 review decision；
- 30-page canonical path→SHA256 map 的聚合 SHA256 为  
  `F751992D96E386F54CE23F2F1945615B2662DC28D171E90B6270810E0FE2E778`。

本 reviewer 还独立查看了全部 30 张 contact sheets。按 contact-sheet 可见信息，三类 level 1–4 变换均未造成明显场景语义改变，level 4 仍保持可识别道路、车辆、行人、灯和车道结构。因此 **scene-semantics-preserved 部分没有观察到实质反例**。

但 contact sheets 只显示 filename 与五级图像，不显示每张图的 action/rationale labels；当前 review decision 又用 `default_decisions=true`、空 overrides 将全部 1,200 rows 自动展开为 true。因此“原 action/rationale labels 仍适用”没有与可见 label evidence 一一绑定，不能把机器生成的 2,400 true 直接等同于 2,400 个可审计人工判断。该问题必须修复。

## 3. 阻断项与必须修复

### 阻断 1：practical endpoint thresholds 的统计层级不明确

协议给出 A/R/S 的 `0.01` 和 C1 的 `0.025` 阈值，但没有规定它们应用于：

- 每个 seed；
- 五 seed endpoint effects 的算术均值；
- bootstrap distribution 的 point estimate；
- pointwise lower bound；
- Bonferroni lower bound；
- 或全部 seed 同时。

`family_axis_pass` 又要求“all required practical endpoint thresholds pass”，所以不同实现会对同一数据产生不同 PASS/FAIL。正式实现目前不可唯一识别。

**修复要求：** 在 outcome-blind amendment 中逐 component 写出公式、seed 聚合顺序、比较运算符和是否使用 uncertainty bound。推荐保持与其余设计一致：先计算每 seed endpoint effect，完整保存；primary practical gate 使用五 seed effects 的算术均值与固定阈值比较；bootstrap endpoint distribution 作描述性报告，不另增未预注册的 CI-threshold gate。若选择其他规则，也必须现在明确冻结。还应声明这些阈值是预注册 operational conventions，不是经过外部验证的 minimal clinically/practically important differences。

### 阻断 2：noise operator 的直接代码依赖没有 hash 绑定

`corruption_dose_response.py` 从 `src/arsc_eval/data.py` import `deterministic_noise`。后者包含 filename hash、RNG、float32、normal sampling、clipping 与 uint8 cast 的真正 noise 实现，当前 SHA256 为：

`B46F21C217240CF23D017310D35D44E414B75BC2A9CE568EE42E86521D372004`

但它不在 `CODE_AND_PROTOCOL_FILES`，也没有出现在 preflight hash inventory 中。只绑定 caller 并不能冻结 noise operator。

**修复要求：**

1. 将 exact noise implementation 内联到 Round 10 bound module，或把 `src/arsc_eval/data.py` 纳入 preflight/reviewer hash contract；
2. 增加 level-2 pixel-exact historical bridge test，而不是只比较三个参数；
3. 绑定所有正式实现将直接调用的 metric、data pipeline、model-definition 和 tie-AURC 依赖；这部分可在 implementation-only 阶段完成，但 operator 的当前直接依赖必须先补。

### 阻断 3：bootstrap quantile 与 endpoint gate 仍有实现自由度

5000 draws 下 `alpha/12` 对应约第 21 个低尾 order statistic，不同 quantile interpolation 会给出不同 lower bound。协议没有冻结 NumPy quantile `method`，也没有明确 lower bound 对 family-axis **mean bottleneck** 而非其他统计量计算。

**修复要求：**

- 明确 Bonferroni lower bound 的输入就是每个 replicate 的 five-selected-seed family-axis mean bottleneck；
- 冻结 `numpy.quantile` method（建议沿用 `method="linear"`）；
- 同时冻结 ordinary 2.5/97.5 percentile 的 method；
- 冻结 exact-zero、strict positivity、NaN、undefined F1/empty class、duplicate seed 和 variable expanded-image-count 处理；
- 要求保存 12×5000 raw gate draws、seed selections、clip selections、expanded image counts 和 quantile diagnostics，以供独立逐 draw 复算。

### 阻断 4：semantic gate 的 label judgment 与 manifest provenance 不充分

当前 semantic contact sheets 没有 action/rationale label 内容；summarizer 默认所有决定为 true，只记录异常 overrides。它还原地覆盖 blank manifest：build summary 绑定的 pre-review manifest hash 为
`3746450D250194963A3CD14AB32E2D7A359772189F3FA63E22543F41E92D304D`，
当前 reviewed manifest hash则为
`94D30755D6E8BD48288ACF9690C828F201B41E3863349D5A2143D65AE15C7CF8`。
原始模板没有被保留为独立 artifact。

**修复要求：**

1. 给每个 selected image 绑定 action/rationale label vector 或 label names，使 label-applicability 决定可审计；若认为 scene preservation 逻辑上已足够，应删除冗余的第二个决定并相应修改 protocol，而不能继续声称两个独立决定都经过观察；
2. review decision 必须绑定 exact 1,200 row-key hash 和 label sidecar/manifest hash；
3. 若使用 default-true batch attestation，必须明确声明 reviewer 已检查全部 1,200 pairs 与其 labels，并把例外列表的全集/唯一性验证写入机器规则；
4. summarizer 必须拒绝 duplicate、out-of-grid、missing 或非-JSON-boolean override；不能使用会把字符串 `"false"` 转成 true 的宽松 `bool(...)`；
5. 保留 immutable raw manifest，并写入新的 reviewed manifest；或至少用可复算的 before/after hash transition，不再原地覆盖唯一副本。

现有 30 pages 可保留，不得改变 severity；若补充 label sidecar 且图像/row keys 不变，不需要因本 STOP 重跑模型或修改 operator。

### 阻断 5：preflight 没有真正执行它宣称的 semantic/preflight 结构验证

当前 preflight 信任 audit summary 的 counts/booleans，没有自行复算：

- `rng(20260810)` 选出的 100 indices；
- selected index 到 filename 的映射；
- 1,200 unique row-key 完整 grid；
- 每 stratum 100 rows；
- parameter 与 protocol grid；
- manifest decision 的严格布尔类型；
- raw→reviewed manifest provenance。

本 reviewer 的只读复算显示当前 artifacts 恰好都正确，但 preflight 代码本身无法阻止将来错误 artifact 通过。

另外测试日志的 `67 passed` 实际由既有 63 tests 加四个 operator tests 构成；`tests/test_corruption_dose_response.py` 没有 preflight 或 semantic-validator negative tests。因此协议中的“new operator/preflight tests pass”尚未真实满足。

**修复要求：**

- 把上述独立结构复算写入 preflight hard assertions；
- 增加不运行模型的 negative tests，至少覆盖错误 sample/grid、重复或越界 override、page/hash mismatch、未绑定 transitive operator dependency、错误 practical-threshold schema、错误 Bonferroni quantile method，以及 formal/staging artifact refusal；
- preflight 除 final formal names 外还要拒绝所有冻结 staging/`.tmp` paths、prediction-cache staging 和已存在的 formal implementation/run manifests；
- 新 preflight 必须写新 artifact，保留本次 STOP01 preflight，不得静默覆盖。

## 4. 对 protocol 科学边界的补充

即使未来 12/12 gates 全部通过，也只支持：

> 在 BDD-OIA 冻结 4,557-image population、五个既有 ResNet-50 training seeds、固定 0.5 threshold、clean-validation temperature，以及三套预固定 synthetic pixel-operator grids 下，A/R/S/C1 的观察量与模型输出呈现预注册的严格方向性 dose-response，并在 source-clip 与 training-seed 条件重采样下通过 12-gate familywise-controlled lower-bound 判据。

它不支持：

- natural corruption prevalence 或自然 severity 标尺；
- 暗化、运动模糊、镜头失焦、真实传感器 noise 或天气域；
- 外部数据、其他模型或真实道路 robustness；
- rationale grounding/faithfulness、CEG 或因果证据；
- calibration validity 或 safety guarantee；
- “指标本身普遍有效”。当前结果始终是 metric×model×operator×BDD-OIA 的联合行为；
- 六个历史恒零 rationale 类已被验证；
- 100-image 单 reviewer semantic audit 等于总体语义不变率的 95% 置信保证。

若某 gate 失败，只能写为当前 operator-grid 的预注册 construct-response 未获支持；不得据此直接否定整个 ARSC 指标，也不得换 severity、丢 family 或追加 seed。

## 5. 允许的修复路径

本 STOP 只允许 outcome-blind protocol/preflight 修复：

1. 保留本 memo、machine STOP decision、当前 protocol/preflight/audit artifacts；
2. 创建 amendment 或新版本 protocol，关闭上述五个阻断项；
3. 不运行模型，不创建非零 severity cache，不实现 formal analyzer；
4. 生成新的 outcome-blind preflight 与测试日志；
5. 请求独立 re-review。

全部修复通过后，下一次 reviewer 最多可以签发：

`AUTHORIZE_OUTCOME_BLIND_FORMAL_IMPLEMENTATION_ONLY`

即使届时签发，formal run 仍为 `NOT AUTHORIZED`。完整正式实现、synthetic tests、atomic one-shot policy、全部 transitive hashes 和一个不 import 正式实现的独立 preformal audit 还必须再次审阅并获得单独 GO。

## 6. 最终决定

**`STOP/REPAIR_PROTOCOL_PREFLIGHT`**

当前结果盲性保持完好，修复窗口仍然有效；但在 practical threshold、operator dependency、semantic label evidence、quantile method 和 preflight negative validation 被唯一冻结前，不得开始正式实现。
