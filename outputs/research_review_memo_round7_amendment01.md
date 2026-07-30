# Round 7 Amendment 01 最终结果前合规确认

日期：2026-07-31  
审查对象：`outputs/validity/arsc_axis_falsification_protocol_amendment01.json`  
对象 SHA256：`BD089BED634FC7D50D391AE17FFEEC54EB1D3ADBA91035EB553D8C5D7E0CE91F`  
审查边界：未运行、请求或查看任何 intervention outcome  
最终裁决：**GO**

## 合规核验

### 1. Crossed shared-image bootstrap：PASS

Amendment 已明确：

- 每个 replicate 有放回抽取五个 training-seed indices；
- 每个 replicate 只生成一份 4,557 canonical image indices multiset；
- 同一 image multiset 应用于全部被抽中的 seeds；
- model、target control、confidence ordering、pairing 与三扰动关系全部保持配对；
- seed 重复抽中时复用同一冻结输出与同一 image multiset。

这正确处理了相同 test images 与五个 training seeds 的 crossed 设计，不再把 image 错当成 seed 内嵌套。replicates、bootstrap seed、95% percentile interval 均未改变。

### 2. S 决策拆分：PASS

Amendment 已把：

- `measurement_ordering_gate`
- `frozen_model_confidence_informativeness`

分开。

前者由 prediction/error invariants、oracle 最小、adversarial 最大及严格正 extremal contrast 决定；后者只解释 original ranking 相对一个冻结 random reference 的信息性。

`full_suite_measurement_pass` 明确排除 original-vs-random contrasts；另设 `full_empirical_battery_pass`。这消除了“模型 confidence 不优于一次随机排列”等同“S metric implementation 无效”的逻辑混淆。

### 3. ECE 边界：PASS

已明确：

- original calibrated ECE 保留既有受限描述；
- synthetic-ordering ECE 仅作 numeric diagnostic；
- 禁止 synthetic ECE directional claim。

该处理符合 ECE 依赖 score magnitude、而不仅依赖 ordering 的性质。

### 4. Wrong-pair precheck：PASS

输入期记录显示 offset 997：

- 是 bijection；
- fixed points=0；
- same-filename pairs=0；
- same-clip-group pairs=0；
- clip group 定义与既有边界一致；
- map 在 seeds/models/perturbations 间共享。

正式 exact audit 仍会在任何 bootstrap/directional outcome 前复核这些条件。没有改 offset 或基于结果选择 pairing。

### 5. Zero-support precheck：PASS

输入期 target-support 记录显示：

- action 与 rationale targets 均为 binary；
- 四个 action 类均有 positive support；
- 21 个 rationale 类均有 positive support。

因此 perfect-control Macro/Micro-F1=1 的 exact gate 不会触发 zero-support 歧义。未删除类别或改变既有 F1 convention。

### 6. Round 5 exact reproduction audit：PASS

Amendment 冻结了：

- Round 5 aggregate artifact 的 path/hash；
- seeds 43–47 每个 `rq1_metrics.json` 的 path/hash。

Expanded audit 要求 original A/R/S/C1 每 seed point estimates 精确复现 Round 5，且所有 control 不得 in-place 修改 frozen arrays。任一不一致都在 bootstrap 和科学解释前 STOP。

### 7. Expanded exact invariants：PASS

新增 audit 覆盖：

- protocol/amendment/cache/calibration/reference hashes；
- five-seed filename/target bitwise identity；
- finite logits、binary targets、unique filenames；
- 全部 row/class/pair maps 的 bijection 与 fixed points；
- row-only prevalence preservation；
- A/R/S/C1 跨轴不变性；
- perfect A/R；
- S score 唯一性、声明 ordering 与 oracle/adversarial separation；
- correct/wrong/identity pairing；
- identity C1 的逐样本 exact values；
- Round 5 original reproduction。

`failure_action` 明确为保存 diagnostics 并在 outcome 前 STOP，不允许自行改变 intervention。该集合充分覆盖 Round 7 memo 要求。

## 未授权变化检查

Amendment 保持不变：

- caches 与 calibration；
- seeds 43–47；
- threshold 0.5；
- row/class maps；
- wrong offset 997；
- random seed/order；
- interventions 与 point-estimate contrasts；
- 4/5 seed 方向规则；
- bootstrap replicates/seed/confidence level；
- prohibited claims。

没有发现：

- 新 permutation 选择；
- 新 threshold；
- 新模型或数据；
- CEG 恢复；
- outcome-dependent fallback；
- silent rerun 权限。

## 运行边界

批准后只允许：

1. 先执行 expanded exact audit；
2. audit 全过后运行一次冻结 falsification suite；
3. 使用 crossed shared-image bootstrap；
4. 完整报告 intermediate controls、five-seed raw contrasts 和失败项；
5. 分别报告 measurement suite 与 model-confidence empirical battery。

任一 exact invariant 失败即 **STOP**，不得换 map、offset、random order、threshold 或 metric convention。

## 最终裁决

**GO**

Amendment 01 严格落实 Round 7 唯一允许的修订，没有扩大研究范围或引入结果适应性。可按冻结协议运行一次。

结果无论通过或失败，都只能支持 BDD-OIA 五冻结 seeds 下 A/R/S/C1 的内部 measurement sensitivity 与 discriminant behavior；不得恢复 CEG、声称 causal faithfulness、安全保证或外部效度。
