# Round 12 既有输出剂量交互：独立事后审查

日期：2026-08-02  
裁决：`ACCEPT_PASS_WITH_LIMITATIONS`

## 1. 审查范围与完整性

本审查读取了 Round 12 单次正式 attempt01 的五个输出、持久 claim、冻结协议、GO_RUN 决策、runner/core/serializer 及相关既有结论；没有再次运行正式入口，没有修改正式输出或 claim，也没有进行新推理或训练。

完整性检查通过：

- artifact index 中四个非索引文件的路径、字节数与 SHA-256 均和当前文件逐字节一致；index 自身不自哈希，符合冻结设计。
- component NPZ 恰含 `D_A/D_R/D_S/D_C1` 四个固定顺序成员；每个均为 `(5000,)`、`float64`、全 finite，ZIP 成员时间戳均为冻结的 1980-01-01。
- 四个数组的线性 q=0.0125 与 results JSON 的 lower bounds 逐位相等。
- CSV 共 23 条记录，点估计、lower bound、五个 seed、三个 family 和七个 gate 的语义及数值均与 results JSON 一致；gate 布尔值位于声明的 `passed` 列。
- log 的 sequence 为 0–11，无缺口，记录 5000 replicates、q=0.0125、PASS、index built 和 done。
- claim 为单个 32 位小写十六进制 token 加换行，正式输出只有一套，GO 决策只授权 attempt01 一次执行；未发现第二次运行证据。claim 必须继续保留，不能自动删除或重跑。
- 正式结果 provenance 中的十二项代码、测试、协议和输入绑定与 GO_RUN 决策一致。

## 2. 冻结判据复核

公式、方向和判据均按冻结协议执行：三类 corruption、四个非零剂量、五个 seed 等权；同一 seed/source-clip bootstrap draw 在所有 family、level、model 和 axis 之间共享；从扩展 clip 样本重算 Macro-F1、tie-averaged AURC 与 flip rate；5000 replicates；四个共同主要分量采用 Bonferroni 单侧 q=0.0125 lower bounds；所有门槛用未四舍五入的 float64 比较。

七项 gate 全部通过，因此正式结构化 verdict `PASS` 正确。

| 分量 | 点估计 | q=0.0125 lower bound | 冻结判据的保守含义 |
|---|---:|---:|---|
| D_A | +0.003826 | +0.000220 | Joint 的动作质量保留相对 Action-Only 至少通过 −0.01 非劣门；点值小幅有利 |
| D_R | −0.001956 | −0.003641 | Joint 内部 rationale 质量随 corruption 有小幅下降，但通过 −0.01 retention 非劣门 |
| D_S | +0.000796 | −0.005292 | 选择性风险交互通过 −0.01 非劣门；不能声称稳定的正向 S 优势 |
| D_C1 | +0.020017 | +0.001826 | 汇总 action-flip 优势点值约 2.00 个百分点，达到 0.01 实践点门，且同时校正 lower bound 严格大于 0 |

需要强调：D_C1 的置信下界大于 0，但没有大于 0.01；正确表述是“点效应达到实践门且方向下界为正”，不是“整个区间都超过 1 个百分点”。A/R/S 通过的是预注册非劣保护门，不等同于三个轴都存在实质改善。

## 3. 异质性

三个 family 的 D_C1 均为正：brightness `+0.016820`、blur `+0.016765`、noise `+0.026465`。这支持 family 汇总层面的方向一致性，但不能推出每个具体剂量 cell 都为正。

五个 seed 的 D_C1 为：

- seed 43：`−0.001884`
- seed 44：`+0.006218`
- seed 45：`+0.032880`
- seed 46：`+0.050984`
- seed 47：`+0.011886`

四个 seed 为正、一个 seed 为负，恰好通过冻结的 4/5 条件。seed 43 的负值必须与汇总结果同时报告；不能写成“所有 seed 都更稳定”。正效应大小也明显跨 seed 变化，因此结论是平均/汇总优势，而非逐训练运行保证。

## 4. 与 Round 10 和 RQ2-light 的关系

Round 10 检验的是各模型内部 family-by-axis 的单调 dose response，结果只对 C1 显示强诊断敏感性，A/R/S 没有普遍单调支持。Round 12 检验的是 Joint 相对 Action-Only 的 supervision-by-dose 交互，并设置 A/R/S 非劣 guardrails；两者问题不同，不矛盾。

历史 RQ2-light 在每个 family 的单一冻结轻扰动上得到三扰动平均 flip 优势 `+0.016107`，并有 4/5 seed 同向。Round 12 将这一窄结论扩展为所有 12 个非零 family×dose cells 的预注册等权汇总：D_C1 为 `+0.020017`，三个 family 汇总均为正，4/5 seed 为正，同时 A/R/S 非劣门通过。因此可称“固定 BDD-OIA、固定五个配对 seed 和冻结合成 corruption grid 下，RQ2-light 的动作一致性优势具有剂量汇总支持，并未观察到超过 0.01 margin 的 A/R/S 劣化”。

这仍不回答 RQ2-CEG。CEG/evidence-sensitivity 分支继续保持 `UNANSWERED/closed`，Round 12 的 flip 结果不能替代关键证据依赖测量。

## 5. 允许与禁止的论文表述

允许的保守结论：

> 在 BDD-OIA、五个冻结配对训练 seed、三类合成像素 corruption 的四个非零剂量及预注册 crossed seed/source-clip bootstrap 下，Joint 相对 Action-Only 的汇总 action-flip 优势点估计约为 2.00 个百分点，Bonferroni 单侧 lower bound 为 0.18 个百分点；三个 corruption family 汇总均为正，五个 seed 中四个为正。A、R、S 同时通过 −1 个百分点的非劣 guardrails。

禁止以下推断：

- rationale supervision 导致了该优势，或产生因果鲁棒性提升；
- Joint 使用了正确证据、rationale 更 faithful/grounded，或 RQ2-CEG 已回答；
- Joint 在每个 seed、每个 family×dose cell、每个 coverage 或所有安全指标上均占优；
- 结果构成道路安全保证、自然 corruption 鲁棒性或外部数据集有效性证据；
- D_R 是 Joint 相对 Action-Only 的 rationale 优势，因为 Action-Only 没有 rationale head。

## 6. 局限与最终裁决

五个训练 seed 限制了训练随机性推断精度；bootstrap 的大量 clip 重采样不能增加独立训练运行数。corruption 是冻结的合成像素变换，不能代表自然天气/传感器故障分布。C1 是动作预测一致性，不是安全、校准或语义忠实性。D_R 仅是 Joint 内部 retention guardrail。外部有效性仍需独立数据完成来源隔离、标签绑定与预注册后验证。

最终接受结构化 `PASS`，但只接受上述窄范围解释：`ACCEPT_PASS_WITH_LIMITATIONS`。任何更强的因果、安全、faithfulness 或 external-validity 表述均不获本审查支持。
