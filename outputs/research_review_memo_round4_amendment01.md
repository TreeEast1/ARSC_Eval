# Round 4 Protocol Amendment 01 独立审阅

日期：2026-07-31  
对象：BDD-OIA 五个新配对种子 RQ1 的 Windows DataLoader pickle 修复  
审阅性质：pre-result engineering amendment；不修改 estimand、数据、扰动或分析规则  
正式裁决：**GO 实施限定修复；重启 evaluation 为 CONDITIONAL GO**

## 1. 事件与结果盲性核验

冻结协议：

- `outputs/validity/rq1_multiseed_frozen_protocol.json`
- primary seeds：43、44、45、46、47；
- seed 42 排除为 archival pilot；
- 5 epochs；
- best validation Action Macro-F1 checkpoint；
- action/rationale threshold 均为 0.5；
- brightness=1.10、blur radius=1.0、noise std=5.0、noise seed=20260731；
- `num_workers=8`；
- CEG 明确排除。

已发生：

- seed 43 Action-only 与 Joint 训练完成；
- 两模型 calibration 仅使用 official validation，已完成；
- evaluation 在第一个 lossless perturbation 的 DataLoader worker 启动时中止；
- Windows spawn 尝试 pickle dataset 内的 transform，报错：

```text
AttributeError: Can't pickle local object
'make_benign_perturbation.<locals>.transform'
```

本轮只读检查确认：

- `outputs/validity/rq1_seed_43/prediction_cache/rq1_lossless.npz` 不存在；
- `outputs/validity/rq1_seed_43/rq1_metrics.json` 不存在；
- seed 43 目录当前仅保存 paired-design check、训练日志与 validation calibration；
- tmux 日志没有打印 clean/test metric、model contrast、seed-level effect 或 perturbation effect。

`evaluate_rq1_seed.py` 先在内存运行 clean 条件，然后才进入 perturbation；所以中止前可能短暂计算过 clean logits。但是函数只有在所有 clean/perturbation、两个模型均完成后才返回 payload，`np.savez_compressed` 又发生在该函数返回以后。本次异常发生在返回之前，clean logits 没有写入 cache、没有进入 bootstrap、没有写入 JSON，也没有打印。

因此，当前没有可被研究者用于调整参数、模型、阈值或分析规则的 test effect。该事件仍处于 **pre-result** 边界内。

## 2. Amendment 是否改变研究问题

拟议修改：

- 把 `make_benign_perturbation` 返回的局部闭包改为定义在模块顶层、可 pickle 的 dataclass callable；
- `kind`、brightness factor、blur radius、noise std、noise seed 不变；
- `__call__` 仍调用完全相同的 PIL brightness、PIL Gaussian blur 与 `deterministic_noise`；
- 像素、文件名派生 noise、seed、condition 顺序、DataLoader workers、模型、checkpoint、calibration、threshold、bootstrap 和决策门槛均不变；
- 增加 pickle round-trip 与逐像素等价测试。

在这些限制下，该修改只改变 Python 对象的序列化位置：

```text
local closure
    ->
module-level callable with identical fields and __call__
```

它不改变：

- 被评价的样本；
- clean 或 perturbation 图像的目标像素；
- A/R/S/C1 的定义；
- 模型输出函数；
- RQ1/RQ2-light 的判据；
- 训练或 checkpoint 选择；
- test 结果的可见性。

所以它属于可接受的 **pre-result engineering amendment**，不是 outcome-adaptive protocol change。

## 3. 允许修改的精确范围

### 3.1 允许

只允许：

1. 在 `src/arsc_eval/data.py` 增加顶层、可导入、最好 `frozen=True` 的 dataclass callable；
2. 把原闭包中的三条分支逐字等价地放入该 callable 的 `__call__`；
3. 让 `make_benign_perturbation(...)` 继续验证 `kind`，再返回该 callable；
4. 在 `tests/test_data_perturbations.py` 增加：
   - pickle dumps/loads round-trip；
   - brightness/blur/noise 的逐像素等价；
   - noise 对相同 filename 可重复、不同 filename 仍不同；
   - identity 参数仍逐像素保持；
5. 增加一个 Windows spawn / DataLoader `num_workers=8` 的最小 integration smoke test；
6. 保存本 amendment、代码 diff、旧/新 SHA256 和测试输出。

### 3.2 不允许

本 amendment 不授权：

- 把 `num_workers` 改成 0 或其他值；
- 改 batch size、condition 顺序或 prefetch 行为；
- 改 brightness、blur、noise 参数或 noise seed；
- 改 filename hash、随机数生成器、clip/cast/rounding；
- 改 PIL 到 torchvision/OpenCV 等实现；
- 改图像 resize、normalize、JPEG/PNG 行为；
- 改 seed 列表；
- 改 checkpoint 或 calibration；
- 改 threshold、confidence、bootstrap 或 decision rule；
- 在测试修复前用临时单进程路径查看 seed 43 test 结果；
- 顺便重构 dataset、engine、evaluation、metrics 或 aggregation；
- 重新训练 seed 43。

若修复需要上述任一变化，当前 GO 自动失效，必须 STOP 并提交新的 amendment。

## 4. 重启前硬门

只有以下全部通过，evaluation 才可重启。

### Gate A：结果仍不可见

重启前再次确认：

- seed 43 `rq1_lossless.npz` 不存在；
- seed 43 `rq1_metrics.json` 不存在；
- 没有其他临时 logits、partial NPZ、CSV、console metric 或调试 dump；
- 没有人通过临时 `num_workers=0` 或其他旁路查看 test predictions/effects。

若发现任何已保存或已查看的 seed 43 test effect：**STOP**。不得删除痕迹后仍把 seed 43 当作 primary new seed；需另行审阅 seed 列表和替代方案。

### Gate B：pickle round-trip

对三种 frozen transform 分别：

1. `pickle.dumps` 成功；
2. `pickle.loads` 成功；
3. round-trip 后 dataclass 字段与原对象严格相同；
4. 对同一 image/file_name，round-trip 前后输出 mode、size、dtype 与每个 pixel 完全相同。

任一失败：**STOP evaluation**。

### Gate C：与 pre-amendment 像素映射严格等价

不能只测试“输出看起来相近”。必须逐像素一致：

- brightness，frozen factor=1.10；
- blur，frozen radius=1.0；
- noise，frozen std=5.0、seed=20260731；
- identity 参数；
- 至少两个不同输入图；
- noise 至少两个不同 filename；
- RGB mode、边界像素、clip 到 0/255 的情况均覆盖。

参考值应来自 amendment 前闭包实现保存的 golden arrays/hash，或测试内独立保留的原实现参考函数。每种情形要求 `array_equal`，不是 `allclose`。

若任一 pixel 不同：这已不是 serialization-only amendment。必须 **STOP**；原 100-image semantic audit 不能自动沿用，不能边看 test 边决定是否接受新像素。

### Gate D：真实 Windows worker 路径

单独 `pickle.dumps` 不能完全替代实际 spawn。必须用项目 dataset/loader 或最小等价 dataset：

- Windows spawn；
- `num_workers=8`，与冻结配置一致；
- transform 作为 dataset 字段传入；
- 至少完整读取一个 batch；
- 三种 perturbation 均覆盖；
- worker 无 pickle/import/EOF error。

任一失败：**STOP evaluation**。不得以 `num_workers=0` 绕过。

### Gate E：未授权文件保持不变

对 amendment 前后保存 hash/diff。除以下外不得变化：

- `src/arsc_eval/data.py`
- perturbation 相关 tests
- amendment/provenance 记录

特别要求以下冻结对象 hash 不变：

- seed 43 config；
- Action-only/Joint checkpoints；
- 两份 calibration JSON；
- test manifest；
- semantic audit；
- `evaluate_rq1_seed.py`；
- `arsc_eval/rq1.py`；
- metrics/aggregation code；
- seeds 43–47 的分析判据。

若变化：**STOP 并重新审阅**。

## 5. 现有 semantic audit 是否需要重做

若 Gate C 证明三个 transform 对 amendment 前实现逐像素完全相同，则：

- 原模型输出盲化的 100-image / 300-pair semantic audit 仍适用；
- brightness、blur、noise 的 unchanged rate 仍为 1.0；
- 不需要因对象从 closure 变为 dataclass 而重做人眼审计。

若像素有任何变化，则原 audit 对新实现不再具有严格 provenance。此时本 amendment 失败，不能用“变化很小”解释后继续。

## 6. seed 43 checkpoint 与 calibration 是否可复用

**允许复用，不应重训。**

原因：

- seed 43 训练只使用 train/validation；
- checkpoint 由 validation Action Macro-F1 选择；
- calibration 只用 validation；
- 本次修改仅触及 evaluation 时的可选 PIL perturbation callable；
- clean training dataset 未传入该 callable；
- 没有 test effect 参与 checkpoint 或 temperature 选择。

重新训练不仅没有科学必要，反而会引入不需要的新随机差异。必须保存原 checkpoint 与 calibration hash并原样复用。

## 7. 精确重启边界

修复与 Gate A–E 全部通过后：

1. **只从 seed 43 的 `evaluate_rq1` stage 重启**；
2. 使用原：
   - `configs/rq1_seed43.yaml`
   - Action-only best-action checkpoint
   - Joint best-action checkpoint
   - 两份 calibration JSON
   - device
   - bootstrap replicates/seed
   - `num_workers=8`
3. 不重跑 seed 43 train；
4. 不重跑 seed 43 calibration；
5. 因当前 cache 不存在，完整重跑 seed 43 clean + 三种 perturbation evaluation 是正确行为；
6. seed 43 成功写出完整 cache 与 `rq1_metrics.json` 后，才按冻结顺序进入 seed 44–47；
7. 所有 seeds 的 evaluation 都使用同一 amended callable；
8. aggregate 只在 43–47 五个 seed 均完成后运行。

若现有 runner 无法从 evaluate stage 安全恢复，应显式运行 seed 43 evaluation 命令，而不是重启整条 runner 并覆盖 checkpoint。

## 8. 后续异常的处理

- 如果同一修复后仍是 pickle/spawn error：STOP，不降 workers。
- 如果出现新的、仍发生在任何 prediction cache/metric 写出前的纯工程错误：保留日志，另提交有界 amendment；不能自行扩大修改。
- 如果已经生成 cache 或显示任何 test metric 后才发现错误：结果边界已改变。不得再把修复当作本次 pre-result amendment，必须暂停并独立审阅是否需要冻结旧结果、排除 seed 或新建分析版本。
- 不得因为 seed 43 后续效果方向不理想而修改 callable、workers、seed 或 perturbation。

## 9. 最终裁决

### Amendment 实施

**GO**

批准把局部闭包改成顶层可 pickle dataclass callable，并加入 pickle round-trip、逐像素等价和 Windows worker smoke tests。该批准严格限于 serialization-only 修改。

### Evaluation 重启

**CONDITIONAL GO**

Gate A–E 全部通过后，允许从 seed 43 `evaluate_rq1` 重启，复用现有训练 checkpoint 与 calibration；禁止重训、改 workers 或改任何研究参数。

### 自动 STOP 条件

以下任一出现即 STOP：

- 发现已保存/已查看的 seed 43 test effect；
- 新旧 transform 任一 pixel 不同；
- pickle 或真实 worker smoke 失败；
- frozen config/checkpoint/calibration/evaluation/metric code 变化；
- 需要通过 `num_workers=0`、改 seed 或改扰动参数才能运行。

在这些边界内，该修复不会削弱五新种子 RQ1 的 pre-result replication 身份。
