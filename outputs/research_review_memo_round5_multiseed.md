# Round 5 独立事后审阅：BDD-OIA 五新种子 RQ1 / RQ2-light

日期：2026-07-31  
审阅范围：冻结五种子汇总、冻结协议、Amendment 01、Round 4 路线与 BDD100K validation 候选计数  
总体裁决：**五种子 RQ1 与 RQ2-light 判定按预注册成立；CEG 仍未回答**

## 1. 协议与修订有效性

primary seeds 为 43–47，seed 42 作为已观察 pilot 排除。训练预算、checkpoint、0.5 阈值、动作等价边界 ±0.03、C1 参数和 RQ2-light 判据均在新结果前冻结。

Amendment 01 只把不可 pickle 的局部扰动闭包改为顶层 callable；记录显示：

- 修订前没有 prediction cache、RQ1 metrics 或被查看的 test effect；
- 配置、test manifest、checkpoint、calibration、evaluation、metric 与 aggregation hash 保持冻结；
- 逐像素等价与 Windows `num_workers=8` worker check 已通过；
- 从 seed 43 evaluation 重启，未重训或重校准。

因此五种子结果仍可视为 pre-result engineering amendment 后的冻结 replication，不存在已知 outcome-adaptive 修改。

## 2. 预注册判定复核

### 2.1 Action equivalence：PASS，判定正确

冻结条件：

```text
95% hierarchical CI of
Δ Action Macro-F1 = Joint - Action-only
must be fully inside [-0.03, +0.03]
```

结果：

- Action-only Macro-F1：0.6741；
- Joint Macro-F1：0.6856；
- mean ΔA：+0.01154；
- hierarchical 95% CI：[+0.00159, +0.02181]。

该区间完全落在 `[-0.03,+0.03]` 内，所以 equivalence PASS 正确。

区间也完全大于 0，表示在本固定协议下 Joint 平均动作 F1 有小幅正差异。正确表述是：

> 两模型动作表现满足预注册的实践等价，同时 Joint 平均高约 1.15 个百分点。

不能写成“动作完全相同”或“没有差异”。等价与小幅正差异可以同时成立。

### 2.2 RQ2-light：SUPPORTED，判定正确

冻结条件：

1. `mean[FlipRate(Action-only)-FlipRate(Joint)] ≥0.01`；
2. 至少 4/5 新 seeds 为正；
3. 任一单扰动的平均 advantage 不低于 -0.01。

实际：

- overall mean advantage：0.01611；
- raw seeds：-0.00505、+0.00395、+0.02750、+0.04513、+0.00900；
- positive seeds：4/5；
- brightness：+0.01356；
- blur：+0.00917；
- noise：+0.02559；
- 最差单扰动仍高于 -0.01；
- overall hierarchical 95% CI：[+0.00101,+0.03281]。

三项预注册条件全部满足，`supported=true` 正确。

但异质性不能省略：

- seed 43 整体方向为负；
- seed 44 与 47 虽为正，但各自低于 0.01 实践阈值；
- brightness CI 为 [-0.00356,+0.03199]；
- blur CI 为 [-0.00843,+0.02822]；
- 只有 noise CI [+0.01132,+0.03959] 在单扰动层面稳定为正；
- Joint mean-three Flip Rate 的跨 seed SD 为 0.02156，明显大于 Action-only 的 0.00614。

因此支持的是：

> 在三种冻结轻扰动平均后，Joint 的动作翻转率相对 Action-only 平均降低约 1.61 个百分点，并满足 4/5 seeds 同向的预注册门槛。

不能声称 brightness、blur、noise 三者都分别得到稳定改善，也不能声称 Joint 在每个 seed 都更稳。

## 3. A / R / S / C1 的解释

### A：支持实践等价和小幅平均优势

- Macro-F1：0.6741 vs 0.6856；
- Micro-F1：0.7097 vs 0.7188；
- Δ Macro-F1 的 seed SD 为 0.01272，说明训练随机性不可忽略；
- 四动作中 Right 的平均提升最明显，Stop 基本相近；不能把整体均值写成所有动作一致改善。

可声称：固定 BDD-OIA、ResNet-50、五 epoch 和五个新配对 seeds 下，两模型动作准确度实践等价，Joint 有小幅平均优势。

不能声称：架构普遍优于、所有动作改善、跨数据集等价。

### R：证明额外输出可测，但总体预测质量有限

- Joint Rationale Macro-F1：0.2736，95% CI [0.2561,0.2929]；
- Micro-F1：0.5031，95% CI [0.4835,0.5225]；
- car、person、left_lane、left_follow、no_left_lane、left_solid_line 等类别五个 seeds 均为 0；
- 多个稀有类别接近 0，而 green_light、red_light、rider 等明显较高。

可声称：Joint 提供了可重复评价的 21 类 rationale 预测，但类别覆盖高度不均，Macro-F1 仍低。

不能声称：

- Joint 的 R 优于 Action-only，因为 Action-only 没有 rationale head；
- rationale label F1 证明 explanation faithfulness；
- 高 Jaccard 证明模型使用了正确证据。

### S：AURC 有平均改善，但不构成整体安全支配

- AURC：Action-only 0.3888，Joint 0.3722；
- ΔAURC：-0.01660，95% CI [-0.03356,-0.00040]，较低为好；
- UAR@90 Δ：-0.01107，CI [-0.02604,+0.00200]，跨 0；
- calibrated ECE Δ：+0.00045，CI [-0.02044,+0.01629]，无稳定差异；
- uncalibrated ECE 对 Joint 有利，但 calibration 后差异消失。

可声称：在冻结的 exact-set error 与 maximum-action-probability confidence 定义下，Joint 的平均 AURC 较低。

不能声称：

- Joint 在所有 coverage 都更安全；
- UAR@90 已稳定改善；
- calibration 质量优于 Action-only；
- AURC 改善等同真实驾驶事故风险下降。

### C1：动作稳定性汇总改善；rationale set 稳定不等于正确

- mean-three Action Flip Rate：0.1185 vs 0.1024；
- 预注册 mean advantage 为 +0.01611；
- noise 的差异最稳定，brightness/blur 的区间跨 0；
- Joint 的 flip 跨 seed 波动更大。

Joint rationale mean-three Jaccard 为 0.9160。单扰动 unconditional Jaccard 约 0.902–0.930；union-nonempty conditional Jaccard 仍约 0.887–0.920。empty-empty fraction 约 0.127，所以高 Jaccard 并非完全由两边都为空造成，但仍受到阈值化输出和类别预测模式影响。

可声称：Joint 的 thresholded rationale 集合对三种轻扰动较稳定，且排除 empty-empty 后仍较高。

不能声称：这些 rationale 是正确的、忠实的或因果上被模型使用。稳定地输出错误标签仍可获得高 Jaccard。

## 4. 层级 CI 能支持到哪里

汇总使用“先重采样训练 seed，再在选中 seed 内重采样 image”的层级 paired bootstrap，并保留模型与三扰动配对；这比把五个 seed 的全部图像简单池化更符合设计。

它支持：

- 固定训练协议下，同时考虑 image 与 seed 变异的区间；
- action equivalence 的预注册判断；
- mean-three Flip Rate 聚合差异的区间；
- AURC 平均差异的有限结论。

限制：

- 只有 5 个训练 seeds，seed population 的尾部与异质性估计仍粗；
- CI 不能外推到其他 backbone、训练预算、数据集或真实天气；
- overall CI 不能替代逐 seed 与逐扰动报告；
- CI 排除 0 不是 causal claim。

## 5. 能与不能声称的总表

### 可以声称

1. 五个新配对 seeds 下 Action-only 与 Joint 满足 ±0.03 动作实践等价。
2. Joint 的平均 Action Macro-F1 小幅较高。
3. ARSC 的 R、S、C1 列确实揭示了 A 单独不表达的信息。
4. Joint 在冻结 Safety 定义下平均 AURC 较低，但 UAR@90 与 calibrated ECE 没有稳定差异。
5. RQ2-light 三扰动汇总子分支按预注册得到支持。
6. Joint rationale predictions 对轻扰动具有较高 set consistency，但 rationale accuracy 和类别覆盖仍有限。

### 不能声称

1. rationale supervision 已提高 causal faithfulness 或正确证据依赖。
2. RQ2 整体得到支持；**CEG 分支仍是 unanswered**。
3. RQ2-light 可以替代 CEG。
4. Joint 在所有 seed、所有扰动或所有 safety coverage 上都占优。
5. 高 Rationale Jaccard 等于高 rationale correctness。
6. 五种子 BDD-OIA 结果具有真实世界或跨数据集外部效度。
7. v4 mask 被五种子结果“补救”。

## 6. 与前序失败的合并判断

- v4：red binding 与 control contamination gate 失败，不能作确认性 CEG；
- BDD100K official validation：全新 state-matched 候选仅 53，red 34、green 19，未达到总数 100、每状态 30 的旧候选门；
- VLA4CoDrive：仅 9 canonical scenes、最多 2,160 paired windows，已按预注册 STOP training。

这些失败都不能由当前 RQ2-light 的正结果替代。当前证据最强的部分是 BDD-OIA 内部五种子 A/R/S/C1；剩余最直接缺口仍是一个真正通过 measurement gate 的 CEG。

## 7. 唯一下一步首选

**首选：只做 BDD100K train 官方 traffic-light state boxes 与冻结 BDD-OIA evaluation manifest 的元数据交集，尝试建立一次性、完全未见样本的 v5 候选池。**

此步先不生成 mask、不读取五种子 logits、不训练。

### GO / STOP gates

1. **独立性 gate**  
   固定官方 train annotation revision；排除所有 v2–v4 generation/audit 文件、同 video/scene 近邻帧、模型 train/validation 文件。任何 filename/scene/hash overlap：STOP。

2. **候选规模 gate**  
   在任何新 mask 前需有 ≥200 个全新 official state-matched candidates，red ≥50、green ≥50、≥30 个独立 video/scene groups。任一不足：STOP CEG，不降低门槛、不转做 v6。

3. **冻结生成 gate**  
   generator 只能在旧 development pool 上冻结；新候选池只运行一次。critical/control 实际像素尺寸完全相同，render mismatch=0，control 与全部官方关键框零交叠。任一 invariant 失败：STOP。

4. **模型输出盲审 gate**  
   binding ≥0.90 overall、red、green；control contamination ≤0.05 overall、red、green；semantic unchanged ≥0.95。gate 冻结前不得读取任何五种子 CEG。任一失败：STOP，不在同一 pool 继续修改。

5. **唯一确认性运行 gate**  
   1–4 全过后，才允许对 seeds 43–47 的冻结 checkpoints 计算一次 Action-only/Joint ΔCEG。RQ2-CEG 支持仍要求预注册实践效应与 seed 方向门槛；否则报告未支持，不追加 seed。

若 BDD100K train 在 gate 2 就不足，下一轮应正式结束 CEG 主线并把 RQ2 限定为“light perturbation 子分支支持、evidence-sensitivity 未回答”，而不是继续横向寻找数据集。

## 8. 最终裁决

**Round 5：PASS with bounded claims。**

- Action equivalence：PASS；
- RQ2-light：SUPPORTED；
- RQ2-CEG：UNANSWERED；
- A/R/S/C1：形成五种子内部重复性证据，但不形成 causal 或 external validity；
- 唯一下一步：BDD100K train 官方框的全新 v5 元数据候选 gate；任一 gate 失败即停止 CEG 路线。
