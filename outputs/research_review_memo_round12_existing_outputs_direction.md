# Round 12 现有 BDD-OIA 产物统计方向独立审阅

审阅日期：2026-08-02  
裁决：`GO_FREEZE_ONE_ANALYSIS`  
唯一推荐主分析：**配对多轴 rationale-supervision × corruption-dose interaction**

## 1. 范围与结论

本审阅只读取 Round 10 已保存的结果、二值预测、置信度、标签、source-clip 分组、充分统计量与 bootstrap draws。没有访问 `data/external/daadx_official`，没有下载、模型推理、训练，也没有实现或运行拟议的 Round 12 正式统计分析。

结论是：现有产物足以完成一个有明确证伪力、与 Round 10 不重复、无需新 inference 的最小分析。不要同时启动其他现有输出分析。

## 2. 唯一主分析及科学问题

分析名称：`ROUND12_PAIRED_MULTIAXIS_SUPERVISION_DOSE_INTERACTION`。

它回答：在已有 clean-action 等效性成立的前提下，Joint Action–Rationale 模型相对 Action-Only 的历史 RQ2-light 稳定性优势，能否推广到全部三类 corruption 的四个非零剂量，同时不以 A、R 或 S 的实质恶化为代价？

这是一个四轴共同约束的 RQ2 强化/证伪分析：

- A：Joint 相对 Action-Only 的 action Macro-F1 剂量退化差异；
- R：Joint rationale Macro-F1 在剂量下的保持程度；
- S：Joint 相对 Action-Only 的 tie-averaged AURC 剂量退化差异；
- C1：Action-Only 相对 Joint 的 action flip-rate 优势。

R 没有 Action-Only 对照，因为该模型没有 rationale head；因此 R 只能作为 Joint 获得 C1/S 优势时的非劣 guardrail，不能解释成“rationale supervision 提升了 R”。

## 3. 精确假设与效应量

记模型 `AO=Action-Only`、`J=Joint`，训练种子为 `s`，corruption family 为 `f`，非零 level 为 `l∈{1,2,3,4}`。clean 使用同一 family 的 level 0；实现必须先验证三个 family 的 level-0 数组完全一致，并只计一次 clean baseline。

所有效应先在每个 seed×family×level 上计算，再对 12 个非零 family×level cells 等权平均，最后对五个 seed 等权平均：

```text
D_A  = mean{ [A_J(f,l)-A_J(f,0)] - [A_AO(f,l)-A_AO(f,0)] }
D_R  = mean{ R_J(f,l)-R_J(f,0) }
D_S  = mean{ [AURC_AO(f,l)-AURC_AO(f,0)]
             -[AURC_J(f,l)-AURC_J(f,0)] }
D_C1 = mean{ Flip_AO(f,l)-Flip_J(f,l) }
```

方向解释：`D_A/D_R/D_S` 越大越好，`D_C1>0` 表示 Joint 更稳定。

预注册全局假设是一个 conjunction：

- C1 practical superiority：`D_C1 ≥ 0.01`，且其同时校正单侧下界严格大于 0；
- A non-inferiority：`D_A` 的同时校正单侧下界严格大于 `-0.01`；
- R non-inferiority：`D_R` 的同时校正单侧下界严格大于 `-0.01`；
- S non-inferiority：`D_S` 的同时校正单侧下界严格大于 `-0.01`。

`0.01` 不是新的 outcome-adaptive MID：A/R/S 沿用 Round 10 已冻结的 operational convention，C1 模型差异沿用 RQ2-light 已冻结的 minimum advantage。

额外保留两项既有 RQ2 C1 guardrails：五个 seed 中至少 4 个 seed-specific `D_C1>0`；三个 family 各自跨四个非零 levels 的 `D_C1` 均不得小于 `-0.01`。不得按结果删 seed、family 或 severity。

## 4. 现有输入可用性证据

主输入：

- `outputs/validity/round10_corruption_formal_attempt02/round10_corruption_primitives.npz`  
  SHA-256 `80821C7DEE9194ABA62B373383B4FD9EF8105D3750C48902A91EF45D278B2E83`
- `outputs/validity/round10_corruption_formal_attempt02/round10_corruption_bootstrap_draws.npz`  
  SHA-256 `893FE2F899BE4F725E3B056BB26B060EDBE4AB40AA7144D3BB83114D1F87DB02`

primitives 已核对存在：

- `seeds (5,) = [43,44,45,46,47]`
- `families (3,) = [brightness,blur,noise]`
- `levels (5,) = [0,1,2,3,4]`
- `models (2,) = [action_only,joint]`
- `clip_id_by_image (4557,)`、`clip_keys (3904,)`、`clip_sizes (3904,)`
- `action_targets (4557,4)`、`rationale_targets (4557,21)`
- `action_predictions (5,3,5,2,4557,4)`
- `rationale_predictions (5,3,5,4557,21)`
- `confidence/errors/group_ids (5,3,5,2,4557)`
- clip-level `A_tp/A_fp/A_fn (5,3,5,2,3904,4)`
- clip-level `R_tp/R_fp/R_fn (5,3,5,3904,21)`
- `C1_action_clip_sums (5,3,5,2,3904)`
- 已保存 `curve_A/curve_R/curve_S/curve_C1` 和 safety diagnostics。

因此 A/R/C1 可由 clip sufficient statistics 精确重算；S 的 tie-averaged AURC 可由保存的 confidence、errors、clip mapping 精确重算。无需 checkpoint、图像或新 logits。

bootstrap 文件已保存 Round 10 原有共享 draws：`seed_position_draws (5000,5)`、`clip_position_draws (5000,3904)`、`expanded_image_counts (5000,)`。Round 12 必须复用这些 exact draws，不生成新的随机抽样，从而减少分析自由度并维持与 Round 10 相同依赖结构。

辅助完整性绑定：

- Round 10 results SHA `9AE834DD81D4A397BA966917245AAA581007A0BFBF5B08CA773D7515756242C4`
- Round 10 point diagnostics SHA `A0F24ED0528CD81B96789E8798AB9B31E44727021F763F6EA157142500B79BF3`
- Round 10 protocol amendment SHA `220D36BEB76CAFDE5BCC3528B49F737E6681A43FF2ECA9A3C22531A1FF88644B`
- RQ1 frozen protocol SHA `CC5FE969EA90EFB1181F67AB5D18CE67C05DE9207F903C7F14EBD964AC07EE0C`
- RQ1 summary SHA `ECA8D453E9DB67CB933CAF2217DAFC62BD054709734C857AF8A5BE9665680000`
- Round 10 independent postresult decision SHA `795FCECE213B78C03FD820274D67338FED0F57426E2A33AEF6F281F762266A89`

## 5. 分析单位、依赖结构与统计检验

科学泛化单位是训练 seed 与 source clip，二者是 crossed factors；4557 images 不是独立样本。每个 bootstrap replicate 必须：

1. 使用保存的一个五位置 seed draw；重复 seed 位置保留；
2. 使用保存的一个 3904 位置 clip draw；每次抽中 clip 时按 canonical 顺序加入其全部 images，重复 clip 完整重复；
3. 同一 seed/clip draw 同时用于所有 family、level、model 和四个 axes，保持所有 paired contrasts；
4. 在 expanded sample 内重新计算 Macro-F1、tie-averaged AURC 和 flip rate；不得 bootstrap 已聚合的 60 个 cell means；
5. 每个 replicate 输出 `D_A,D_R,D_S,D_C1`，五个抽中 seed 位置和 12 个 cells 均等权。

效应量报告 point estimate、5000 draws 的 percentile interval、以及用于 gate 的单侧 Bonferroni simultaneous lower bound。四个 co-primary components 控制 familywise α=0.05，固定下分位数为 `0.05/4 = 0.0125`，`numpy.quantile(method='linear')`；严格使用未四舍五入 float64。另报告 seed-specific 与 family-specific `D_C1` 作为冻结 guardrail，不额外进行探索性显著性筛选。

## 6. PASS / PARTIAL / FAIL gate

### PASS

同时满足：

1. `D_C1` point estimate `≥0.01` 且 0.0125 分位 simultaneous lower bound `>0`；
2. 至少 4/5 seed-specific `D_C1>0`；
3. 三个 family-specific `D_C1≥-0.01`；
4. `D_A,D_R,D_S` 各自的 0.0125 分位 simultaneous lower bound均 `>-0.01`。

解释：在 clean action 等效性背景下，RQ2-light 的 C1 优势可推广到全 dose grid，并且没有发现 A/R/S 的实质代价；支持“四轴共同揭示收益与 guardrail”的互补性。仍不支持因果忠实性、安全保证或外部有效性。

### PARTIAL

C1 的前三项全部通过，但 A/R/S 至少一个 non-inferiority gate 失败。

解释：可保留“Joint 在 action C1 上更稳定”的剂量推广，但必须撤回“无多轴代价”或“整体更稳健”的措辞；论文应把 ARSC 定位为揭示 trade-off 的诊断框架，而不是给出单一优胜模型。

### FAIL

C1 的 point/CI、4/5 seed 或 family guardrail 任一失败。

解释：RQ2-light 只能保留为原固定扰动设置下的有限结果，不能声称随 severity 或跨 operator 稳健推广。Round 10 的 C1 仍可作为 corruption-sensitive diagnostic，但“rationale supervision 提升稳定性”的广义归因应删除。A/R/S 的 Round 10 partial/fail 结论保持不变。

## 7. 与 Round 10 的非重复性

Round 10 检验的是：每个模型内部、每个 family×axis 的曲线是否沿 severity 严格单调，并通过 12 个 family×axis gates。它没有检验 supervision×dose 的模型差异。

历史 RQ2-light 使用每个 family 的一个既有 perturbation 输出和平均 flip advantage；它没有使用全部四个非零 doses，也没有 A/R/S guardrails。

Round 12 固定使用所有 12 个非零 family×level cells，主量是 clean-adjusted Joint-vs-Action paired interaction，并以四轴 conjunction 作最终 gate。因此既不是重跑 Round 10 monotonicity，也不是把旧 RQ2-light 换一组 bootstrap 再报告。

## 8. 不做新 inference 的真实性与停止规则

可以真实做到不做新 inference：所需 targets、predictions、confidence、errors、clip groups 和 bootstrap draws 均已保存，并已被 Round 10 独立重构审计确认。Round 12 只允许读取上述固定 artifacts 和执行统计重聚合。

实施前必须先冻结独立 protocol、确切公式、四个 gate、输入 SHA、输出 allowlist 和一次性停止规则；不得先计算新效应再修改 margin、cell weighting、axis component、bootstrap 或 gate。只实施这一项分析；不要并行启动备选分析。
