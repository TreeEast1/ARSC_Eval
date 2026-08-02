# Round 12 既有输出分析冻结协议：结果前独立复核

## 0. 裁决

**`GO_IMPLEMENT_ROUND12_RESULT_BLIND`**

固定候选已经足以授权下一步的“结果盲实现与合成测试”。本裁决不授权读取正式结果值、不授权执行 bootstrap、不授权生成正式结果、不授权 `GO_RUN`，也不授权 DAAD-X、训练、新推理或第二项并行分析。

## 1. 复核边界与固定字节

本次只审阅下列固定文件及其结构、控制流和文本协议，没有读取 NPZ 数组值、没有计算任何 D 统计量，也没有修改候选文件：

| 文件 | SHA-256 |
|---|---|
| `scripts/freeze_round12_existing_outputs_protocol.py` | `B0C828F8FED137BD692FD0E02A1937FD6DAF81C63391A022506F4CC434B281E5` |
| `tests/test_freeze_round12_existing_outputs_protocol.py` | `A4D8DDF3C75FEDEC7B29E907246F4FA1F0C2222A19BC24E4B28FB4A73AD45EF6` |
| `outputs/validity/round12_existing_outputs_frozen_protocol.json` | `643F60022965E298B07F8CED4BEB8F6FC547ACA3B1C717DF8A60EC6ECDF2D6F7` |
| `outputs/research_review_memo_round12_existing_outputs_direction.md` | `F260312611350C0B0A53AA681670954116EDFB961E163CFE1922C6DADDDC7A8A` |
| `outputs/validity/round12_existing_outputs_reviewer_decision.json` | `404A5E65B480BC8E61287105EDEF007FAA266F231B7C7F00BBFFFFE5E0C4528D` |

固定协议还逐一绑定七项既有证据的 SHA-256，并为两个 NPZ 固定精确 key、shape 和 dtype allowlist。任何证据字节、成员名、数组形状或 dtype 改变都会在冻结阶段失败关闭。

## 2. 结果盲性与确定性

冻结脚本对 NPZ 的语义检查是真正的 header-only：它通过 ZIP central directory 找到 `.npy` 成员，只解析 NPY magic、版本、header、shape 和 dtype；不调用 `numpy.load`，不解码数组 payload，也不计算模型指标。对整个 NPZ 做流式 SHA-256 只是把既有字节身份绑定到协议，不属于结果解释或计算。

脚本只允许无参数 canonical invocation，输出路径固定；已有协议只有在字节完全一致时才返回 `UNCHANGED`，否则拒绝覆盖。新写入使用同目录临时文件、flush/fsync 和原子替换；预留的未来正式产物一旦存在就失败关闭。主执行方报告真实冻结连续两次得到 `WROTE`、`UNCHANGED`，且协议 SHA 均为上述固定值。

因此，当前冻结过程没有提供基于结果选择公式、阈值、输出路径或第二分析的通道。

## 3. 科学合同核对

冻结协议与方向裁决一致地固定：

- 五个 seed、三个 corruption family、四个非零 level、两个 action model 和 A/R/S/C1 四轴；
- 十二个 family-by-level cell 等权，五个 seed position 等权；每个 seed/model 的 clean baseline 在跨 family 精确相等后只计一次；
- `D_A`、`D_R`、`D_S`、`D_C1` 的公式和“越大越有利”方向；R 仅是 joint 模型内部 retention guardrail；
- C1 实用阈值 `0.01`、C1 单侧下界 `> 0`、至少四个正 seed、每个 family 不低于 `-0.01`，以及 A/R/S 单侧下界均 `> -0.01`；
- PASS、PARTIAL、FAIL 的优先含义和论文 claim boundary；
- 精确复用 Round 10 的 `5000` 组 seed-position 与 clip-position draws，形状分别为 `(5000, 5)` 与 `(5000, 3904)`，同一 replicate 在所有 family、level、model、axis 间共享，形成 crossed seed-plus-source-clip bootstrap；
- 从扩展后的 clip 样本重算 macro-F1、tie-averaged AURC 和 flip rate，禁止 bootstrap 聚合后的 cell means；
- 四个共同主要分量使用 Bonferroni simultaneous one-sided lower bounds，`q=0.0125`，NumPy linear quantile、float64；
- 非有限值和空样本失败关闭，macro-F1 零分母计零，门限比较使用未四舍五入值；
- 只允许一个固定正式结果包，且未来执行必须另获授权。

协议中 PARTIAL 的一句自然语言写作“all three C1 guardrails”但括号实际列出 point/CI、seed count、family floor；结构化 PASS/FAIL 条款明确表达四个 C1 判断，不形成可选择的统计分支。实现及结果 schema 应统一称为“四项 C1 条件”，避免论文表述歧义。

## 4. 测试证据

主执行方固定候选上的目标测试结果为 `17 passed, 1 skipped`；唯一 skip 是 Windows symlink privilege 条件。全套结果为 `236 passed, 1 skipped`。目标测试覆盖：确定性与幂等性、任意参数拒绝、证据 SHA/方向 schema/NPZ allowlist 失败关闭、`numpy.load` 被禁用时仍可完成 header-only 检查、重复或非 NPY member、object dtype、未知 NPY 版本、symlink/非普通输出、原子替换失败清理、精确 margin/gate/q、授权为 false、协议 round-trip 和禁止的可执行导入/调用。

本审阅者在当前受限沙箱中复跑时，18 项均在 `tmp_path` fixture 建立前因 Windows ACL 对 pytest 临时目录返回 `WinError 5`，没有进入被测代码；这是一项环境性未复现，而不是测试断言失败。主执行方的完整通过记录与静态代码核对共同作为本裁决证据。

按工作区的混合模型路由要求，曾请求 DeepSeek V4 Flash 做一轮只读机械检查，但 API `fetch failed`，未得到外部输出；最终判断完全由主审阅模型承担。

## 5. 实现阶段必须满足的接受条件

本次 GO 仅在以下边界内有效：

1. 实现必须显式验证 metadata 的值与顺序、draw 索引范围、source-clip 映射和跨 family clean equality；任何不一致都在计算 D 之前停止。
2. 正式点估计和 bootstrap 只能从协议指定的原始 primitives 与两组固定 draws 重建；不得把 `curve_*`、`endpoint_effects`、`endpoint_draws`、`family_axis_gate_draws` 或 `safety_diagnostics` 当作 Round 12 结果输入。
3. tie-averaged AURC 必须只有一个明确实现，逐项复现已绑定的 Round 10 语义，并用包含 ties、全等 confidence、单样本和空/非有限失败路径的合成测试锁定；不得在正式数据上比较多个实现后选择。
4. clean equality 必须覆盖各指标实际依赖的原始 clean arrays 或其可审计充分统计，而不只是 shape；失败必须先于任何效果或区间计算。
5. 实现须逐项输出 seed-specific 与 family-specific C1 guardrail 的机器可审计中间量，但不得在本轮运行正式输入。
6. 实现代码、合成测试、唯一正式输出 schema、artifact allowlist、原子写入和 one-shot runner 必须接受下一轮独立结果前复核。只有该复核可决定是否 `GO_RUN`。

这些条件是在不接触结果的前提下把执行语义机械化，不允许改变已冻结的 estimand、方向、权重、阈值、multiplicity 或 gate。

## 6. 剩余风险与主张边界

剩余风险主要是实现错误，而非尚未冻结的科学选择：tie-averaged AURC 的具体代码仍待绑定；clean equality 和 primitive-only 读取需在实现中明确；crossed bootstrap 可能带来显著内存和运行时压力；五个训练 seed 仍限制精度与外推；同一 BDD-OIA 既有输出上的分析不能建立因果性、安全性、faithfulness 或外部有效性。

`GO_IMPLEMENT_ROUND12_RESULT_BLIND` 只说明当前协议足以进入结果盲实现和合成测试。它不说明四个效应为正、不说明任何 gate 会通过，也不构成对 ARSC 有效性或论文结论的结果证据。
