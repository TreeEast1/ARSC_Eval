# Round 4 独立事后审阅：VLA4CoDrive feasibility 与下一步优先级

日期：2026-07-31  
角色：独立科研审阅者  
审阅性质：严格按 Round 3 预注册作事后裁决；只读审阅既有结果与脚本，不下载、不训练、不查看模型效应  
最终裁决：**STOP VLA4CoDrive training**

## 1. 执行摘要

VLA4CoDrive 的 10-window probe 证明了一件有限但有价值的事：该公开数据不是空仓库，稀疏下载、Action/Language join、JSON schema、视频解码和至少一个 COCO 文件均能工作。

它没有证明该数据可以进入 ARSC 四维训练。相反，完整仓库索引已经给出不可由“继续下载”解决的硬失败：

- Hugging Face revision `872d0898a5663b1028584d80de94d7a284f0d196` 共 117,246,701,986 bytes、99,715 paths；
- GitHub 与 Hugging Face 的 4,320 个 Action/Language window JSON 路径完全相同，说明不是 GitHub 少列了另一批语言/动作样本；
- 4,320 路径由 2,160 个 Action 与 2,160 个 Language JSON 构成，理论最大 paired windows 只有 2,160，低于预注册的 5,000；
- 全部 window 仅来自 `Town10HD`，只有 9 个 `canonical_scene_key`，远低于 150；按 60/20/20 分组最多约为 5/2/2 个独立 scene，更不可能得到至少 30 个 test scenes；
- 540 个 path-weather 与 filename-weather 不一致，全部表现为 `hardFogNoon` 目录对应 `WeathercustomWeather` 文件名；这可能是系统性别名而非 540 个损坏文件，但在完成语义别名核验前不能满足严格天气配对；
- probe 的动作坐标、单位、终点速度与未来 brake 语义尚未锁定，`pre_registered_action_mapping_ready=false`；
- 10/10 reasoning 都触发宽口径动作词 regex，文本声明的 braking-event 数与真实 brake rising edge 仅 1/10 匹配；
- COCO 文件虽有 57,076 个标注，但唯一类别为 `car`，仅证明存在车框，不能支持 traffic light、pedestrian、road geometry 等多类 reasoning，也不能单凭 car bbox 证明“关键前车”因果绑定。

因此，Round 3 的核心门 2、3、5、6 已明确未通过；门 1、7、8 也尚未完成。根据预注册：“1–6 任一失败即 STOP 四维外部验证”。本次必须停止 VLA4CoDrive 训练，不得降低 scene/window 数、把 weather/vehicle/window 当独立 scene、把动作词出现率改名为 rationale ontology，或用全量 117 GB 下载来绕过裁决。

后续路线首选：**D）先完成不依赖 mask 的 BDD-OIA 五个新配对种子 RQ1 与四指标 falsification**。  
优先级：**D > A > B > C**。

这是对执行顺序而不是证据等级的调整：D 能最快回答现有单 seed 不足，且 CEG measurement FAIL 不会传染到 clean A、Joint 的 R、S 或轻扰动 C1。A 仍是解决 RQ2-CEG 的唯一首选后续路线，但应在 D 的低成本 measurement sanity gate 与五种子 RQ1 冻结后推进。B 只在 A 元数据门失败或完成后仍需要真实道路外部验证时启动；PSI 在访问状态不变时停止投入。

## 2. 审阅材料与可追溯性

本轮审阅：

- `outputs/research_review_memo_round3_external_prereg.md`
- `outputs/validity/vla4codrive_probe_feasibility.json`
- `outputs/validity/vla4codrive_repository_index.json`
- `scripts/analyze_vla4codrive_feasibility.py`
- `scripts/analyze_vla4codrive_repository_index.py`
- `scripts/download_vla4codrive_probe.ps1`
- `scripts/download_vla4codrive_probe.sh`
- `tests/test_vla4codrive_feasibility.py`

没有把 README 声称的数据规模替代实际仓库索引；没有读取模型输出；没有基于效应方向决定是否继续。

## 3. 技术 gate 通过与科学 hard gate 通过不是一回事

### 3.1 10-window probe 真正证明了什么

`vla4codrive_probe_feasibility.json` 的小样本来自：

- one town：Town10HD；
- one canonical scene：scene001；
- one weather：clearNight；
- one vehicle：Vehicle_1；
- 10 个连续 windows。

在这个极窄切片上：

- Action 10、Language 10，paired 10；
- cross-modal join completeness = 1.0；
- Action 与 Language schema valid rate = 1.0；
- 10 个视频均可打开，30 frames、1280×1080、10 fps；
- 30-frame action windows 和每帧 30-point trajectory 结构存在；
- 一个 clearNight COCO 文件可读且有非零 annotation。

所以 `technical_gate.passed=true` 是正确的工程判断：下载方式和最基本读取链路可行。

### 3.2 它没有证明什么

同一结果文件已经显式写出：

- `minimum_200_window_feasibility_audit=false`
- `minimum_150_canonical_scenes=false`
- `minimum_5000_valid_windows=false`
- `action_semantics_audited=false`
- `rationale_ontology_audited=false`
- `split_frozen=false`
- `bbox_ceg_audited=false`
- `weather_pairing_audited=false`
- `go_to_training=false`

10 个相邻 windows 不能估计跨 scene 的类别支持度、ontology precision/coverage、天气对齐或 bbox 因果绑定。它们也不是 10 个独立实验单位，而是同一 scene、同一 vehicle 的时间相关切片。

故 `technical_gate.passed=true` 与 `training_authorized=false` 不矛盾。前者是文件可读性，后者才是科研立项闸门。

## 4. Round 3 逐项硬门裁决

### 4.1 可获取性与 join：局部通过，全局未完成

积极证据：

- HF 数据公开、非 gated、Apache-2.0；
- HF/GitHub window JSON 路径全集相同；
- 10-window Action/Language join 为 1.0；
- revision/commit 和 probe 文件 hash 已保存。

未通过点：

- probe 只覆盖一个 scene/vehicle/weather，不能代表全库 join completeness；
- `analyze_vla4codrive_feasibility.py` 的 `parse_window_identity` 要求目录 weather 与文件名 weather 完全相同；若把 `hardFogNoon/...WeathercustomWeather...` 纳入，会直接抛错，当前 clearNight probe 没有触及该分支；
- 540 个 mismatch 可能只是官方命名别名，但必须由元数据/视觉/轨迹配对证明，不能静默改名；
- COCO 的示例 image name 与 window video 的逐帧 join 尚未审计。

裁决：**仅局部工程通过，不足以通过 Round 3 gate 1。**

### 4.2 独立 scene ≥150：确定失败

完整 HF 与 GitHub 索引都只有：

- towns：`["Town10HD"]`
- canonical scenes：scene001–scene009，共 9 个。

天气 × vehicle × window 产生大量文件，但它们属于相同底层事件，Round 3 已要求整体 group。将 8 weather、3 vehicle 或 10 window 当成独立 scene 会构成伪重复并低估不确定性。

按冻结 60/20/20 split，9 个 scene 只能形成约 5/2/2；test 不可能达到 30 scenes。

裁决：**硬失败，且继续下载 117 GB 不能改变仓库索引中的 scene 数。**

### 4.3 有效 windows ≥5,000：确定失败

完整索引包含：

- Action window JSON：2,160；
- Language window JSON：2,160；
- 二者路径集合按 modality 对应，最大 paired window 数为 2,160。

即使所有 JSON 都有效并能一一 join，仍低于 5,000。若以 clearNoon 为唯一训练/验证主天气，可用 window 还会更少。

裁决：**硬失败。**

### 4.4 四动作支持度：未建立

probe 中：

- `pre_registered_action_mapping_ready=false`；
- future trajectory 的两个坐标轴正负与物理含义未确认；
- 最后一帧没有被证明提供 Round 3 定义所需的 future terminal speed/future brake；
- `aEgo` 出现最大约 6457.66 的异常量级，进一步说明字段单位/语义不能想当然；
- 仅 10 个同场景 windows，无法检查每类 train/validation/test positives 或 scene coverage。

裁决：**未通过。不得先根据最终类别数量调 Left/Right/Stop 阈值。**

### 4.5 动作语义 200-window audit：未完成

Round 3 要求至少 200 个分层 windows、动作规则一致率 ≥0.95、Left/Right 方向错误为 0。当前只做了结构统计，没有人工/轨迹语义审计。

文本中声明的 braking-event count 与 `brakePressed` rising edges 仅 1/10 相同。这可能由事件定义不同、文本模板错误或 probe 过小造成；它不能证明全部 language 都错误，但足以否定“语言计数可直接替代 telemetry ground truth”。

裁决：**硬门未通过。**

### 4.6 rationale ontology：未通过

当前 regex 是筛查而非 ontology 标注：

- 10/10 reasoning 至少出现一个 brake/stop/accelerate/turn/drive/moving/speed 等动作词；
- exploratory reason lexicon 只在 10 个样本中触发 traffic signal/sign、lead vehicle、junction/route、weather/visibility 四个候选上位类；
- precision、coverage、temporal grounding、unsupported rate、κ 均未测；
- `ontology_confirmed=false`。

需要特别区分：脚本的 `reasoning_action_word_rate=1.0` 是“任何动作词出现”的宽口径指标，不完全等同于 Round 3 的“纯动作复述泄漏率”。因此不能仅凭 1.0 宣称人工审计后的 pure-action leakage 必然为 100%。但在没有 200-window 独立审计的情况下，它是强烈风险信号，绝不是 ontology 已通过的证据。

裁决：**硬门未通过。**

### 4.7 轻微扰动语义：未完成

未见 brightness/blur/noise 的冻结 manifest 或 100-image、每扰动 ≥0.95 语义不变审计。

裁决：**未通过，但它不是当前最先阻断项。**

### 4.8 split 与泄漏：在 9 scenes 条件下无法形成合格 split

canonical key 的解析 `town + scene` 与 Round 3 一致，测试也覆盖了关键路径解析，这是优点。但只有 9 个 groups，无法形成预注册规模的 train/validation/test，也未完成轨迹/hash 去重。

裁决：**未通过。**

## 5. 天气与 bbox 子门

### 5.1 540 个 weather mismatch 应如何解释

索引显示 540 个 mismatch 正好来自 Action 与 Language 两个 modality 下的 `hardFogNoon` 目录，而 filename 写 `WeathercustomWeather`。这更像一个系统性 alias，而不是 540 个彼此独立的随机损坏。

因此：

- 不应夸大为“540 个数据内容错误”；
- 也不应在未核验时直接把 `customWeather` 当成 hardFogNoon；
- 必须对同一 scene/vehicle/window 的帧、轨迹、action、窗口边界作实际配对；
- 即使 alias 最终可解决，也无法补足 9 scenes 和 2,160 windows。

`analyze_vla4codrive_repository_index.py` 把 `weather_filename_mismatch_count_zero` 和“至少两个 town”加入 `pre_registered_hard_gate`。前者和后者是合理的保守 screening，但不是 Round 3 第 7.2 节逐字列出的两个独立核心阈值。停止结论不依赖这两个附加条件；Round 3 明确写出的 150 scenes、5,000 windows、动作语义和 ontology 已足以 STOP。

### 5.2 COCO 只有 car 的含义

`coco_labels_present=true` 只说明 COCO 文件存在且非空。其唯一 category 为 `car`：

- 可以成为“车辆证据”stratum 的候选；
- 不能区分 lead、parked、crossing、oncoming 或无关车辆；
- 不能承载 traffic-light state、pedestrian/cyclist、lane/road geometry；
- COCO 中 8,530 个 image records 与具体 window/frame 的准确 join 尚未验证；
- 在完成模型输出盲化的 relevance/contamination audit 前，不满足 CEG。

Round 3 的四类 ontology 门和 CEG bbox 门是两个不同要求。理论上 CEG 可以只对一个通过审计的 vehicle stratum 作限定结论，但当前既没有合格四类 R ontology，也没有 200-pair/30-scene bbox pool；而整个仓库总共只有 9 scenes。

裁决：**bbox CEG 未通过，且 scene 门使其不能达到预注册确认规模。**

## 6. 对 VLA4CoDrive 的正式裁决

### 6.1 必须 STOP training

Round 3 已写明：

> 核心门 1–6 任一失败，即 STOP 四维外部验证；不得通过放宽 ontology、降低 positives、合并动作、改阈值或换帧来救确认性实验。

本次至少有以下确定失败：

- 9 < 150 canonical scenes；
- 最大 2,160 < 5,000 paired windows。

另有以下未完成：

- action mapping；
- 200-window action semantic audit；
- rationale ontology；
- weather pairing；
- bbox CEG audit；
- split freeze；
- perturbation semantic audit。

所以裁决不是 PAUSE，也不是“有条件继续下载”，而是：

**STOP_EXTERNAL_TRAINING**

### 6.2 允许保留什么结论

可以保存并报告：

- 官方数据可公开访问；
- HF/GitHub window JSON 索引一致；
- 小样本文件读取与 join 管道可行；
- 当前官方 revision 不满足预注册 ARSC 外部验证规模与标注门槛；
- feasibility 的负结果避免了约 117 GB 的无效下载与训练。

不能报告：

- VLA4CoDrive 已验证或否定 ARSC；
- reasoning ontology 无效；
- 100% 文本是动作泄漏；
- weather replay 不一致；
- car bbox 无任何研究价值；
- 模型在 VLA4CoDrive 上表现如何。

### 6.3 唯一重新开放条件

仅当官方发布新的可固定 revision，且元数据索引在不下载大 blob 的条件下同时证明：

- ≥150 canonical scenes；
- ≥5,000 paired Action/Language windows；
- 有足够多 town/scene groups 可得到 ≥30 test scenes；
- Action/Language/Vision 时间键可解析；

才可重新提交新的 feasibility 预注册。不能把当前 revision 的 8 weather × 3 vehicle × 10 windows 重新计数为更多 scenes。

### 6.4 CEG 失败是否阻止 A/R/S/C1：不阻止，但结论必须拆开

**允许独立推进 A、R、S、C1。**

理由是 v4 失败针对 critical/control mask 的 measurement validity：

- A 使用 clean action labels 与 clean predictions；
- R 使用 BDD-OIA 已有 21 类 rationale labels，只评价 Joint 的预测质量；
- S 使用 clean action correctness、confidence 与 risk-coverage；
- C1 使用 clean/brightness/blur/noise 配对，不使用 critical/non-critical mask；
- 只有 CEG/C3 依赖 v4 mask。

因此不存在“一个 CEG gate 失败，四指标全部作废”的逻辑。正确的 RQ 状态是：

- RQ1 的 A 等价、Joint R、S 和 C1 可以由五配对种子继续回答；
- RQ2 的 CEG/evidence-sensitivity 分支保持 **STOP / unanswered**；
- RQ2 的轻扰动 Action Flip 分支可以独立检验，但不能替代 CEG 分支，也不能把“flip 更低”写成“使用了正确证据”。

仍有两个前置限制：

1. 原扰动落盘为 JPEG quality=95，包含重编码混杂；C1 若不增加 identity re-encode control 或改用冻结的内存/无损变换，只能作为探索性结果。
2. seed=42 的 pilot 已看过，不能把包含它的事后扩展包装成完全未见结果的原始确认性研究。更稳妥的 primary replication 使用五个新配对 seeds `43,44,45,46,47`，seed 42 单独保留为 archival pilot。

## 7. 后续路线优先级

## 7.1 第一优先：D）BDD-OIA 五个新配对种子 RQ1 与无新 mask falsification

### 为什么现在先做 D

D 与当前 RQ1 直接对应，也回应 Round 1 最明确的缺口——单 seed 无法区分辅助监督效应与优化随机性。它：

- 不需要新数据集或自由文本 ontology；
- 不使用已失败的 v4 mask；
- 不要求先解决 BDD100K train 标签访问；
- 复用冻结的 BDD-OIA split、动作/理由标签、模型结构和训练预算；
- 可以在不追逐 test 结果的前提下给出 seed-level 稳定性；
- 先验证 metric 行为，再决定是否值得为 RQ2-CEG 获取新框。

Round 1 曾写“不应在当前 mask 生成器不变时直接烧 3–5 seeds”。该警告适用于把长训练用于尚未通过 measurement gate 的 CEG/RQ2。现在的批准明确排除 CEG，只针对不依赖 mask 的 RQ1 A/R/S/C1；所以不构成对 v4 gate 的绕过。

### D0：训练前冻结

在任何新 seed 的 test 推理前冻结：

- primary new seeds：`43,44,45,46,47`；
- seed 42：只作为既往 pilot，不能并入 primary 五种子均值；
- Action-only 与 Joint 每个 seed 使用相同 backbone/action-head 初始状态、数据顺序、split、增强和预算；
- 原固定 5 epochs 与 best validation Action-F1 checkpoint 规则不变；
- Joint 所有 RQ 主比较使用同一个 best-action checkpoint；
- action threshold=0.5、rationale threshold=0.5；
- 动作等价界 `[-0.03,+0.03]`；
- test 不用于 epoch、loss weight、checkpoint、阈值或 seed 选择；
- CEG、v2/v3/v4 mask outputs 不进入本轮 primary table。

若无法保证两个模型的配对初始化、相同数据顺序或固定 checkpoint 规则：**STOP 五种子训练，先修复复现性，但不看 test。**

### D1：先做低成本 metric falsification

不依赖训练效果的检查先运行：

- A：perfect prediction 得 1；all-zero/all-one 与空标签行为符合冻结定义；
- R：固定 label permutation 后降至 prevalence 对应基线；每类支持度与 7 个既往零 F1 类显式报告；
- S：constant/random confidence reference；risk-coverage 端点正确；正温度不改变 AURC/UAR 排序；
- C1：identity transform flip=0、Jaccard=1；
- Rationale Jaccard 同时报告 empty-empty 比例与 union-nonempty conditional Jaccard；
- threshold sensitivity grid 预先固定为 `{0.3,0.4,0.5,0.6,0.7}`，0.5 始终为 primary，不挑选最佳阈值。

C1 还必须二选一：

1. 在推理时使用参数冻结的内存/无损 brightness、blur、noise；或
2. 保留既有 JPEG perturbations，同时增加 identity JPEG re-encode control，单独量化重编码 flip。

并对每类扰动抽检语义不变；overall 及每扰动均需 ≥0.95，才允许把 C1 放入主 RQ1。未通过时 A/R/S 仍可继续，C1 降为 exploratory。

### D2：五种子 RQ1 判定

每个 seed 单独报告，再报告配对 seed difference：

- `ΔA = Macro-F1(Joint)-Macro-F1(Action-only)`；
- AURC、UAR@90、ECE 的模型间差；
- overall 与 brightness/blur/noise 的 Action Flip 差；
- Joint 的 Rationale Macro/Micro/per-class F1 与 Rationale Jaccard；
- image-clustered bootstrap 保持两个模型配对，三扰动随同一 image 整体重采样；
- 跨 seed 报 mean、SD、五个原始差值和方向，不只池化所有图像。

RQ1 的动作可比前提只在 `ΔA` 的 95% CI 完全落入 `[-0.03,+0.03]` 时成立。若不成立，S/C1 差异只能描述为伴随差异。

RQ2 的扰动子分支若要称获得实践支持，事先固定为：

- `mean[FlipRate(Action-only)-FlipRate(Joint)] ≥0.01`；
- 至少 4/5 个新 seeds 方向为正；
- 三种扰动中不得有一种平均恶化超过 0.01。

不满足就报告未获得支持，不追加 seed 或改 severity。无论 flip 结果如何，RQ2-CEG 仍为未回答。

### D 的结论边界

五种子 D 可以把“单 checkpoint 描述”提升为固定 BDD-OIA 训练协议下的重复性证据；但它是看过 seed-42 pilot 后的预注册 replication，不是完全未受先验结果影响的首次确认。它不能修复 v4、不能建立外部效度，也不能证明 causal faithfulness。

## 7.2 第二优先：A）BDD100K train 官方框驱动的全新 v5

### 为什么 A 仍是 RQ2-CEG 的首选路线

这一路线与现有四指标/RQ 最近：

- 保持 BDD-OIA 已有四动作与 21 类 rationale，不重新发明外部 ontology；
- 保持已有 Action-only/Joint 模型与 A/R/S/C 主协议，不需要新训练；
- 官方 traffic-light state bbox 能直接针对当前最关键的 measurement failure：rationale-bound CEG；
- 可以用全新、从未进入 v2–v4 development/audit 的文件形成真正的 sequential holdout；
- 若失败，失败点仍是清晰的 CEG measurement gate，不会扩散成另一个完整数据集工程。

它不是“继续在同一 113 张图上做 v5”。只有在全新官方标签交集足够、文件/scene 与所有既往开发和审计严格隔离时，才有科学资格称为 v5。

### A0：先做元数据候选门，不生成 mask、不看模型输出

先取得并固定 BDD100K train 官方标签 revision，只做 filename/scene/state/rationale 的索引连接。必须排除：

- v2、v3、v4 audit/sample/confirmatory manifests 中全部文件；
- 所有既往 mask generation manifests 中全部文件，而不仅是人工审过的文件；
- 用于 mask 参数开发、可视化检查或错误分析的全部文件；
- 与上述文件属于同一视频/scene group 的近邻帧；
- 任何不在冻结 BDD-OIA evaluation split 的样本；
- 任何模型训练/validation 文件。

在生成任何 v5 图像或读取模型输出前，candidate pool 必须同时满足：

- total unseen state-matched candidates ≥200；
- red ≥50，green ≥50；
- ≥30 个独立 video/scene groups；
- rationale state 与官方 bbox state 一致率 =1.00；
- 文件/scene/hash 与所有既往 audit/dev/train/validation overlap =0。

若任一项失败：**STOP A，不做 v5，也不降低到 100 或继续找 v6。**

### A1：冻结一次性 generator

在旧的 v2–v4 development 图上完成全部工程修正并冻结 generator、控制框搜索规则、offset、尺寸规则与 hash。不得用 A0 的新候选图调参数。

新 pool 只运行一次。关键规则：

- 仅用官方 state bbox 绑定 red/green rationale，不再用 detector 代替 state label；
- control 对所有官方关键框零像素相交；
- critical/control 实际渲染后的 width、height、pixel count 完全相同；
- 边界 clipping 后形状不等的 pair 自动丢弃并计数；
- 每个 scene 只保留预注册上限，避免单场景主导；
- 模型输出在 audit gate 冻结前不可读取。

### A2：盲审确认门

有效池仍需：

- pairs ≥200；
- red/green 各 ≥50；
- independent scene groups ≥30。

模型输出盲审至少 100 pairs；若池小于 100 则全审。通过条件沿用既有门槛，不另发明宽松标准：

- critical binding ≥0.90 overall 且 red/green 各 ≥0.90；
- control contamination ≤0.05 overall 且 red/green 各 ≤0.05；
- semantic-label-unchanged ≥0.95；
- rendered patch shape mismatch =0；
- 所有跨 split/既往 pool invariants 通过。

任一失败：**STOP CEG，不在同一 holdout 上开发 v6。**

### A3：唯一获准的确认性计算

只有 A0–A2 全过，才对冻结的既有 Action-only/Joint checkpoint 做一次 CEG 计算，不重新训练。

解释 RQ2 前还必须满足原有动作等价条件：

- `ΔA` 的 scene-clustered 95% CI 完全落入 `[-0.03,+0.03]`。

若动作不等价，v5 CEG 只能描述，不能归因于 rationale supervision。若等价，沿用预注册：

- `mean ΔCEG ≥0.02`；
- 3/3 配对 seeds 方向为正；
- 完整报告 scene-clustered CI，不追加 seed 追结果。

这就是本轮给 A 的明确 GO/STOP 门。

## 7.3 第三优先：B）BDD-X 可获取性、去重与自由文本 ontology feasibility

### 为什么不是现在的首选

BDD-X 是真实道路语言解释的潜在外部来源，与 R 相关；但它可能与 BDD/BDD-OIA 共享视频或近邻帧，且自由文本 ontology 会重现 VLA4CoDrive 已暴露的动作复述、时间 grounding 和类别映射风险。它还未证明能提供 state-aware bbox CEG。

因此只允许元数据 feasibility，不应直接下载视频或训练。

### B 的进入门

在任何训练前必须证明：

- 官方、稳定、许可清晰的 image/video、action 与 explanation 均可获取；
- 以原始 video ID、frame ID、时间邻近和 perceptual hash 对 BDD-OIA 全部 train/validation/test 及所有 mask/audit pool 去重；
- 去重后 ≥150 independent scenes、≥5,000 paired samples、test ≥30 scenes；
- 四动作能无事后阈值搜索映射，每类 train ≥500、validation/test ≥100；
- 至少 4 个 rationale 类满足 precision ≥0.90、coverage ≥0.85、grounding ≥0.90、κ ≥0.75、pure-action leakage ≤0.10；
- 若要做 CEG，另需官方 bbox 与 ≥200 pairs/≥30 scenes 的独立门。

任一核心门失败：停止 BDD-X 训练。不得因其是“真实数据”而降低 Round 3 标准。

B 只有在 A 的元数据候选门失败，或 A 完成后仍确需独立真实道路外部验证时，才上升为主线。

## 7.4 第四优先：C）PSI

当前是访问阻断，不是科研设计问题。重复尝试不会增加四指标证据，只会消耗时间。

处理原则：

- 保存官方访问请求、许可和错误状态；
- 不用非官方镜像或来源不明拷贝；
- 在授权/链接状态发生可验证变化前保持 STOP；
- 访问恢复后也必须重新走 scene、action、ontology、bbox 和去重 feasibility gate，不能直接训练。

## 8. 建议的非发散执行顺序

1. **立即关闭 VLA4CoDrive 当前 revision 的训练路线**，保留 feasibility 负结果；
2. **冻结 D0，先做 D1 metric falsification 与 C1 measurement gate**；
3. D1 不阻断 A/R/S 后，运行五个新配对 seeds `43–47`，只回答 RQ1 与 RQ2 的轻扰动子分支；
4. **再做 A0 元数据交集与独立性计数**，不生成 mask、不看 logits；
5. A0 通过后按 A1/A2 一次性 v5；A0 失败则明确停止，不做 v6；
6. 只有 A 停止或完成后仍存在明确外部效度缺口，才启动 BDD-X 元数据 feasibility；
7. PSI 等访问状态变化，不主动投入。

这个顺序围绕现有 RQ 的核心缺口——CEG measurement validity——推进，而不是继续搜集更多看似相关但构念不同的数据集。

## 9. 最终审阅意见

**VLA4CoDrive：STOP training。**

这是一次有意义的负 feasibility 结果：小样本工程通路可行，但完整官方 revision 的独立 scene 与 paired window 总量在预注册层面不够，且动作、ontology、weather、bbox 门均未完成。继续下载或训练会违反 Round 3。

**下一步首选：D）先做不依赖 mask 的 BDD-OIA 五个新配对种子 RQ1 与四指标 falsification。**

CEG gate 失败时，A、Joint R、S、C1 可以独立推进；其中 C1 必须先解决 JPEG identity/无损变换与语义不变 gate。primary seeds 固定为 `43–47`，seed 42 只作既往 pilot。动作等价 CI 未完全落入 ±0.03 时，S/C1 只描述、不归因；RQ2-CEG 始终保持 STOP。

随后第二优先才是 A。A 的唯一 GO 条件是：在任何新 mask 或模型输出前，得到至少 200 个完全未见的官方 state-matched candidates，red/green 各至少 50、至少 30 个独立 scene/video groups、与全部既往 pool/train/validation 零重叠；随后盲审 binding ≥0.90、control contamination ≤0.05（overall 与各状态）、semantic unchanged ≥0.95、render mismatch=0。任一门失败即 STOP，不在同一 holdout 上继续 v6。

优先级固定为：

**D > A > B > C**

这既优先修复单 seed 与指标行为证据，也保留 A 对 RQ2-CEG 的窄范围后续，不会因 VLA 失败而发散到新的大规模训练工程。
