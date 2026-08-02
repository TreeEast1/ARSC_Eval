# 结果制品索引

本目录保存成功结果、负向测量审计、失败运行的来源记录和独立审阅备忘录。文件在此建立索引而不移动，从而保证审阅备忘录引用的哈希和路径持续有效。

## BDD-OIA 五种子主结果

主复现实验使用新的配对种子 43–47。种子 42 作为归档先导实验，不纳入主结果。

- `validity/rq1_multiseed_summary.json`：完整的分层 bootstrap 汇总、原始种子指标、逐类别 F1 和冻结判定。
- `validity/rq1_multiseed_seed_metrics.csv`：长表格式的原始种子估计值。
- `validity/rq1_multiseed_metric_summary.csv`：每项指标的均值、SD 和分层 95% 区间。
- `validity/rq1_seed_43` 至 `validity/rq1_seed_47`：各种子的训练日志、校准结果、无损预测缓存、配对设计检查和配对图像 bootstrap 指标。
- `validity/tmux_rq1_multiseed_amendment01.log`：完整且成功的 tmux 运行日志。
- `validity/rq1_multiseed_frozen_protocol.json`：结果产生前冻结的协议。
- `validity/rq1_protocol_amendment01.json`：经独立授权、仅涉及序列化的修订及重启边界。
- `research_review_memo_round4_amendment01.md`：重启前独立审阅。
- `research_review_memo_round5_multiseed.md`：结果产生后的独立审阅。

主要判定：

| 判定 | 结果 |
|---|---|
| 动作可比性 | PASS：Joint−Action macro-F1 = 0.011536，分层 95% CI [0.001590, 0.021807]，位于 ±0.03 内 |
| RQ2-light 扰动分支 | SUPPORTED：Action−Joint flip = 0.016107，5 个种子中 4 个为正 |
| RQ2 CEG 分支 | UNANSWERED 并关闭：v2–v5 测量/总体门均失败 |

## 指标证伪与 C1 测量有效性

- `validity/metric_validity_frozen_grid.json` 和 `.csv`：冻结的 `{0.3,0.4,0.5,0.6,0.7}` 阈值网格。
- `validity/metric_validity_sensitivity.json` 和 `metric_validity_thresholds.csv`：探索性置信度定义、风险曲线交点、边界案例和实现健全性检查。
- `validity/perturbation_semantic_audit/audit_summary.json`：对 100 张独立图像及 300 对变换图像进行的模型输出盲审；三种扰动均通过 ≥0.95 语义不变性门。
- `validity/perturbation_semantic_audit/audit_manifest.csv`：已审阅样本及判定。
- `validity/rq1_amendment01_tests.log` 和 `rq1_amendment01_worker_check.json`：序列化修订的像素等价性检查和真实 Windows `num_workers=8` 检查。

## Round 7 冻结缓存 ARSC 轴证伪实验

- `validity/arsc_axis_falsification_protocol.json`：不可变的原始预注册。
- `research_review_memo_round7_preregister.md`、`validity/arsc_axis_falsification_protocol_amendment01.json` 和 `research_review_memo_round7_amendment01.md`：结果盲审、唯一获准的交叉 bootstrap 修订和最终 GO。
- `validity/arsc_axis_falsification_preflight.json` 和 `arsc_axis_falsification_run_manifest.json`：干预结果产生前的 83/83 项精确检查及冻结代码/输入哈希。
- `validity/arsc_axis_falsification_results.json`、`arsc_axis_falsification_point_estimates.csv` 和 `arsc_axis_falsification_bootstrap.csv`：完整的五种子对照及 2,000 次“种子 × 共享图像”交叉 bootstrap 结果。
- `validity/arsc_axis_falsification_primitives.npz`：紧凑、无损的二值、置信度、映射和逐图像 C1 原始量。
- `validity/tmux_arsc_axis_falsification.log`：正式单次运行日志，`EXIT_CODE=0`。
- `scripts/verify_axis_falsification_outputs.py`、`validity/arsc_axis_falsification_reproduction_audit.json` 及其日志：仅依赖原始量的重建；十项检查全部通过，所有原始/聚合/bootstrap 结果的最大差异为 0。
- `research_review_memo_round7_final.md`：结果产生后的独立科学审阅。
- `validity/arsc_axis_falsification_artifact_index.json`：完整证据链的顶层 SHA256 绑定。

正式协议和门均通过，但独立科学结论为 **PARTIAL**。十项对比在 5/5 个种子上均为正，逐点 95% 区间全部高于零。结果支持指标对严重关联或对应关系破坏具有内部敏感性，但不能建立严重度单调性、构念/因果/外部有效性、校准或安全性。原始条件与破坏条件中均有六个解释类别的 F1=0；正式区间还以图像而非视频片段作为聚类单位。

可视化审计联系表保留在各 `pages/` 目录本地。由于其中包含重新分发的数据集像素，这些文件被有意排除在公开 Git 仓库之外；清单、判定、汇总和生成代码均受版本控制。

## Round 8 分级关联响应确认

- `validity/round8_graded_response_protocol.json`、`research_review_memo_round8_preregister.md`、`validity/round8_graded_response_protocol_amendment01.json` 和 `research_review_memo_round8_amendment01.md`：结果盲协议、独立审阅、关联分量修订和结果产生前的最终 GO。
- `validity/round8_graded_association_maps.npz` 及其清单：唯一的结果盲嵌套 q 映射，有效图像数为 `0/1140/2278/3418/4557`。
- `validity/round8_association_components.npz` 及其清单：1,625 个映射闭合分量，每个分量包含 2–14 张图像，并用作推断单位。
- `validity/round8_graded_response_formal_attempt01_failed.log` 和 `research_review_memo_round8_attempt01_failure.md`：保留的结果产生前归约顺序断言失败记录，以及经独立授权的有界重跑说明。
- `validity/round8_graded_response_preflight.json`、`round8_graded_response_preflight_stability.json` 和 `round8_graded_response_run_manifest.json`：86/86 项精确预检，以及逐字节一致的重复结果产生前冻结。
- `validity/round8_graded_response_results.json`、`round8_graded_response_point_estimates.csv`、`round8_graded_response_bootstrap.csv` 和 `round8_graded_response_primitives.npz`：完整的五种子点结果、诊断、关联分量 bootstrap 汇总和紧凑无损原始量。
- `scripts/verify_round8_graded_response_outputs.py`、`validity/round8_graded_response_independent_audit.json`、`round8_graded_response_independent_bootstrap_draws.npz` 及审计 tmux 日志：独立实现及全部 2,000 次抽样；7/7 项检查通过。
- `validity/round8_graded_response_curves.png` 和 `.svg`：展示每个种子及五种子均值的描述性曲线；未绘制无效的逐点置信带。
- `research_review_memo_round8_final.md`：最终的结果后计算与科学审阅。
- `validity/round8_graded_response_artifact_index.json`：完整 Round 8 证据链的顶层 SHA256 绑定。

正式轴结果：

| 轴 | 最弱相邻步均值 | 关联分量 95% CI | 正值种子数 |
|---|---:|---:|---:|
| A | 0.068671 | [0.059674, 0.072806] | 5/5 |
| R | 0.046416 | [0.040571, 0.049523] | 5/5 |
| S | 0.026936 | [0.018370, 0.030091] | 5/5 |
| C1 | 0.164889 | [0.150002, 0.165152] | 5/5 |

四个正式门全部通过。独立重建对点估计和 bootstrap 汇总的复现误差分别为 `1.88e-14` 和 `2.42e-15`。最终计算结论为 **PASS / VALID**；科学结论为 **PARTIAL / BOUNDED INTERNAL EVIDENCE**。它验证了指标对冻结关联构造的分级响应，而非所有解释类别、本体、定位、忠实性、因果稳健性、校准、现实世界安全性或其他数据集。六个解释类别仍恒为零。C1 必须表述为样本对应关系敏感性。

Round 9 已完成当时唯一获准的后续实验，并永久关闭 BDD-OIA salt/map 路线。VLA4CoDrive 仍为 `STOP_EXTERNAL_TRAINING`。

## Round 9 的 20 映射关联响应稳健性实验

- `validity/round9_multimap_protocol.json`：不可变的 20 映射协议和单次停止规则。
- `validity/round9_multimap_maps.npz`、其清单和独立 salt 重放审计：20 个带前缀、结果盲且合法的映射实例。
- `validity/round9_multimap_components.npz` 及其清单：每个映射对应一个由 1,625 个分量构成的来源闭合划分。
- `validity/round9_multimap_preoutcome_independent_audit.json`、预检、实现清单、预注册审阅和机器 GO：q>0 结果产生前完成的结果盲绑定。
- `validity/round9_multimap_results.json`、`round9_multimap_primitives.npz`、两个 CSV 文件和正式日志：完整的 `attempt01` 单次结果及诊断。
- `scripts/verify_round9_multimap_outputs.py`、`validity/round9_multimap_independent_audit.json`、`round9_multimap_independent_bootstrap_draws.npz` 及审计日志：对每个点估计及全部 2,000 次抽样进行的独立原始数组实现。
- `validity/round9_multimap_curves.png` 和 `.svg`：不含无效逐点 q 置信带的描述性 20 映射响应曲线。
- `research_review_memo_round9_postresult.md` 和 `validity/round9_postresult_reviewer_decision.json`：结果产生后的独立计算与科学裁定。
- `validity/round9_multimap_artifact_index.json`：由 41 项制品组成的证据链的顶层 SHA-256 绑定。

正式轴结果：

| 轴 | 20 映射总均值瓶颈 | 分层逐点 95% 区间 | 正值映射数 |
|---|---:|---:|---:|
| A | 0.068648 | [0.064261, 0.067624] | 20/20 |
| R | 0.045433 | [0.040589, 0.047385] | 20/20 |
| S | 0.027080 | [0.021644, 0.026686] | 20/20 |
| C1 | 0.163594 | [0.155702, 0.160482] | 20/20 |

冻结的正式判定为 `ROUND9_FULL_PASS`；独立复现通过 8/8 项检查。点估计/诊断的最大差异为 `2.23e-14`，所有 bootstrap 数组完全一致。科学结论为 **BOUNDED CONDITIONAL PASS**：结果在 20 个带前缀的映射间稳健，但这些映射并非 20 个独立数据集，也不能证明外部有效性。四个区间是逐点区间，并非族内同时区间。六个解释类别有正目标支持，但预测正例和 F1 始终为零。

不允许继续迭代 BDD-OIA salt/map 路线。其唯一获准的后续工作 Round 10 已按结果盲协议完成：对真实像素空间的亮度/模糊/噪声进行多严重度推理。

## Round 10 合成像素扰动剂量响应实验

- `validity/round10_corruption_dose_response_protocol.json`、`validity/round10_corruption_dose_response_protocol_amendment01.json`、`research_review_memo_round10_preregister.md` 和 `research_review_memo_round10_preregister_amendment01.md`：冻结协议、修订及独立预注册审阅。
- `validity/round10_corruption_preflight.json`、`validity/round10_corruption_preflight_attempt02.json`、`validity/round10_corruption_formal_preflight_amendment02.json` 和 `validity/round10_corruption_formal_implementation_manifest_amendment02.json`：预检、`attempt02` 冻结预检和正式实现绑定。
- `research_review_memo_round10_preformal.md`、`research_review_memo_round10_preformal_amendment01.md`、`research_review_memo_round10_preformal_amendment02.md` 和 `validity/round10_preformal_reviewer_decision_amendment02.json`：结果产生前的独立审阅及正式 `GO_ROUND10_FORMAL_RUN_ATTEMPT02`。
- `validity/round10_corruption_formal_attempt01.log`、`validity/round10_formal_attempt01_incident.json`、`research_review_memo_round10_attempt01_incident.md` 和 `validity/round10_attempt01_incident_reviewer_decision.json`：保留的 `attempt01` 预推理基础设施失败、事件记录和独立裁定。该次失败发生在正式网格启动、模型构建/加载、检查点张量加载及任何非零严重度推理之前，状态为 `ROUND10_ATTEMPT01_PREFLIGHT_INFRASTRUCTURE_FAILURE_STOP`。
- `validity/round10_corruption_formal_attempt02/round10_corruption_results.json`：正式结果；覆盖 5 个种子、4557 张图像、3904 个来源片段及 5000 次分层 bootstrap，冻结判定为 `ROUND10_PARTIAL_OR_FAIL`。
- `validity/round10_corruption_formal_attempt02/round10_corruption_point_diagnostics.csv`、`validity/round10_corruption_formal_attempt02/round10_corruption_bootstrap_summary.csv`、`validity/round10_corruption_formal_attempt02/round10_corruption_bootstrap_draws.npz` 和 `validity/round10_corruption_formal_attempt02/round10_corruption_primitives.npz`：正式点诊断、bootstrap 汇总、全部抽样和无损紧凑原始量。
- `validity/round10_corruption_formal_attempt02/seed_43_logits.npz` 至 `validity/round10_corruption_formal_attempt02/seed_47_logits.npz`：五个种子的无损正式 logits。
- `validity/round10_corruption_formal_attempt02.log`：完整正式运行日志，`EXIT_CODE=0`。
- `validity/round10_corruption_artifact_index_attempt02.json`：包含正式结果与日志在内的 11 项制品的 SHA256 绑定，状态为 `COMPLETE_HASH_BOUND`。
- `research_review_memo_round10_postresult.md` 和 `validity/round10_postresult_reviewer_decision.json`：已完成的独立结果后科学审阅及机器判定；最终接受 `ROUND10_PARTIAL_OR_FAIL` 为有效的预注册最终结果，审阅结论为 `ACCEPT_ROUND10_PARTIAL_OR_FAIL_AS_VALID_FINAL_OUTCOME`。

正式设计使用亮度、模糊和噪声三类合成像素算子，并对每张原图实际重新推理；每类包含严重度 `0/1/2/3/4`，固定 12 个“算子族 × ARSC 轴”门。最终仅 3/12 个门通过，且三者全部为 C1：brightness、blur 和 noise 的 C1 门分别通过；A、R、S 的 9 个门均未通过。因此该轮不是四轴全面确认，正式判定保持 `ROUND10_PARTIAL_OR_FAIL`。结果仅界定于冻结的 BDD-OIA 总体、五个历史 ResNet-50 种子、固定阈值/校准和三组合成扰动网格；C1 仍只能解释为样本对应关系敏感性，不能外推为构念、因果、外部或现实安全有效性。独立审阅重建了 3,975 行诊断并逐位重放全部 5,000 组 seed/clip 选择；制品哈希、诊断、抽样、84 个分位数和 36 行 bootstrap 汇总均为 0 mismatch。

## Round 11 DAAD-X 外部验证准备

- `validity/round11_daadx_transport_receipt.json`：官方 70 段组装归档的 exact 1,629-byte transport receipt 快照；绑定归档 `18,585,647,156` bytes、SHA-256 `98E6DD4D...E91E965`、manifest、range-chain 和四个实现文件。
- `research_review_memo_round11_assembled_transport.md` 与 `validity/round11_assembled_transport_reviewer_decision.json`：70/70 段实际 SHA、顺序拼接和组装归档的独立 opaque 复核。
- `research_review_memo_round11_transport_receipt_postgeneration.md` 与 `validity/round11_transport_receipt_postgeneration_reviewer_decision.json`：一次性 receipt 的结果后独立复核，裁决为 `ACCEPT_ROUND11_TRANSPORT_RECEIPT`。
- `validity/round11_daadx_phase1_diagnostic_amendment.json`：只增不改的 G0–G3 Phase 1 诊断补充协议；全通过与早停都必须生成哈希闭合证据，G4–G7 保持 `DEFERRED_NOT_RUN_PHASE1`，禁止 G8 或正式结论。
- `src/arsc_eval/round11_phase1_control.py` 及审阅证据：永久 attempt claim、严格 fsync、双进程竞争、canonical index 和原子 no-replace 发布控制。

大归档、range 分块和本地组装 manifest 继续由 Git 忽略。当前只完成 transport 层和执行控制准备；未创建真实 Phase 1 claim、未打开 gzip/tar、未读取标签/视频、未执行 G0–G3，也没有跨数据集外部有效性结论。

## Round 12 配对多轴监督—剂量交互复分析

- `validity/round12_existing_outputs_frozen_protocol.json`、`research_review_memo_round12_existing_outputs_direction.md` 和相关 reviewer decision：结果盲冻结的唯一分析方向、效应定义、同步下界和一次性停止规则。
- `scripts/run_round12_existing_outputs_analysis.py`、`src/arsc_eval/round12_existing_outputs.py` 和 `src/arsc_eval/round12_output_serializers.py`：哈希绑定的门禁、纯统计核心和确定性输出层。
- `research_review_memo_round12_analysis_runner_preresult.md` 与 `validity/round12_analysis_runner_reviewer_decision.json`：唯一 `attempt01` 的结果前独立 GO。
- `validity/round12_existing_outputs_results.json`、`round12_existing_outputs_point_diagnostics.csv`、`round12_existing_outputs_component_draws.npz`、`round12_existing_outputs_protocol.log` 和 `round12_existing_outputs_artifact_index.json`：一次正式运行的结果、诊断、全部四效应抽样、日志及哈希索引。
- `validity/.round12_existing_outputs_attempt01.claim`：必须永久保留的一次性执行 claim；不授权删除或重跑。
- `research_review_memo_round12_existing_outputs_postresult.md` 与 `validity/round12_existing_outputs_postresult_reviewer_decision.json`：独立结果后完整性与科学解释裁定。

正式结构化判定为 `PASS`，结果后裁定为 `ACCEPT_PASS_WITH_LIMITATIONS`。`D_C1=0.020017`，Bonferroni `q=0.0125` 单侧下界为 `0.001826`；三个扰动族均为正，五个 seed 中四个为正，seed 43 为 `-0.001884`。D_A、D_R、D_S 通过 `-0.01` 非劣护栏，但不得表述为三轴全面改善。本轮加强 BDD-OIA 内部的剂量聚合 RQ2-light 证据，不回答 CEG，也不证明因果、faithfulness、真实安全或外部有效性。

## 种子 42 归档先导实验

以下根目录文件早于新的配对种子复现，不得与其合并：

- `main_results.csv`
- `clean_metrics.json`
- `rationale_metrics.json`
- `safety_metrics.json`
- `consistency_metrics.json`
- `critical_mask_metrics.json`
- `calibration.json`
- `training_log_action_only.csv`
- `training_log_joint.csv`
- `tmux_action_only.log`、`tmux_joint.log` 和原始评估日志。

保留这些制品是为了透明性，不将其作为五种子验证性证据。

## CEG 测量开发记录

所有 v2、v3 和 v4 CEG 数值均排除在验证性主张之外。

- `validity/mask_audit_v2`：绑定审计失败。
- `validity/mask_audit_v3`：绑定/污染审计失败。
- `validity/mask_audit_v4`：文件名不相交的红/绿灯审计未通过冻结的总体/状态分层门；未运行验证性 CEG。
- `validity/masks_v*_generation.json`、`masks_v4_confirmatory_population.json` 和 `masks_v4_invariants.json`：完整的生成与不变量证据。
- `research_review_memo_round1.md` 和 `research_review_memo_round2_prereg.md`：独立诊断和 v4 预注册。

这些负向结果验证了测量门的作用：实现没有把低质量定位代理转化为 ARSC 成功主张。

## 外部数据可行性

- `dataset_scout_round1.md`：单一来源数据集筛选。
- `validity/vla4codrive_probe_feasibility.json`：稀疏公开文件技术探测。
- `validity/vla4codrive_repository_index.json`：完整仓库索引审计；仅有九个规范场景，最多 2,160 个配对窗口。
- `research_review_memo_round3_external_prereg.md` 和 `research_review_memo_round4_vla_feasibility.md`：冻结门和针对 VLA4CoDrive 训练的正式 STOP 判定。
- `validity/bdd100k_validation_label_overlap.json`：仅有 53 个未见过且状态匹配的验证候选，低于预注册的 v5 掩码门。

## 最终 BDD100K-train v5 CEG 停止记录

- `validity/bdd100k_train_v5_metadata_protocol.json`：冻结的单次 `200/50/50/30` 纯元数据门。
- `research_review_memo_round6_amendment01.md` 和 `validity/bdd100k_train_v5_protocol_amendment01.json`：将传输表过滤为原始 BDD 训练行的独立授权和精确来源记录。
- `validity/bdd100k_train_v5_amendment01_pre_gate_check.json`：唯一一次正式门运行前的全部五项条件重启检查。
- `validity/bdd100k_train_v5_metadata_gate.json` 和 `bdd100k_train_v5_candidates.jsonl`：冻结机器结果和纯元数据提案清单。
- `validity/tmux_bdd100k_train_v5_metadata_amendment01.log` 和 `tmux_bdd100k_train_v5_gate_amendment01.log`：成功的仅训练集传输及门运行日志。
- `research_review_memo_round6_final.md`：最终科学 STOP 裁定。

冻结机器判定为 `STOP_CEG_INDEPENDENCE`，因为分析器使用了 `data/raw/lastframe`，而非真实的 `data/raw/lastframe/data` 图像根目录，导致哈希独立性未得到评估。尽管如此，哈希前提案上限仍仅为 87 个样本（红灯 50、绿灯 37、87 个组），所以任何根目录修正都无法满足总数 ≥200 或绿灯 ≥50。独立审阅因此也给出 `STOP_CEG_POPULATION_NO_V6`。未重跑候选池、未生成掩码，也未读取提案 logits。

## 工程来源记录

- `validity/tmux_rq1_multiseed_attempt01_failed.log`：在保存种子 43 测试效果/缓存前发生的序列化失败记录。
- `validation_tests.log`：最终保存的测试运行日志。
- `validation_compileall.log`：最终字节码编译检查日志。
- `validation_verify_outputs.log`：必要输出及 README 命令验证器日志。
- `environment_snapshot.json`：Python、CUDA、GPU 和软件包版本。
- `reproduction_check.json`：原始必要输出验证器结果。

下载的数据集、模型检查点、检测器权重和审计联系表均有意不纳入版本控制。其来源、必要哈希和重新生成命令保存在受版本控制的配置、脚本、JSON 汇总与日志中。
