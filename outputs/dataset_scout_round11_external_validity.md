# Round 11 外部数据集有效性可行性复核

复核日期：2026-07-31（Asia/Shanghai）  
研究边界：仅核验官方项目页、官方论文、作者官方仓库和由官方页面直接指向的数据托管端点；未下载大数据、未读取任何模型输出、未训练或运行模型。

## 冻结问题与结论

本轮不是寻找“看起来相关”的数据集，而是判断是否已有一个外部数据集可以在不改变 ARSC 含义的前提下，支持 BDD-OIA 的 Action-only 与 Joint 配对实验。最低要求是：无需人工审批即可取得当前可用数据；视觉、动作和理由三者能绑定；独立样本组可以跨 split 隔离；动作可预注册映射到 Forward/Stop/Left/Right；理由不是事后自由编码出来的伪金标；自然或天气严重度可以结果盲冻结；许可允许本项目的研究使用。

**正式结论：`STOP_ROUND11_EXTERNAL_TRAINING`。** 当前没有候选同时通过数据完整性、来源分组独立性和标签构念门。**DAAD-X 是唯一允许继续做结果盲数据预检的候选**，但不是训练 GO：必须先从官方整包恢复完整媒体清单，并得到或可靠重建 driver/session/source-group，使任何 train/val/test 划分按来源组完全隔离。若这两项任一不能满足，则永久停止 DAAD-X 的验证性实验。

## 候选对照

| 数据集 | 无人工审批公开下载 | 当前可下载规模 | 独立单元 | 四动作映射 | 21 类理由 | 严重度 | 本轮判定 |
|---|---|---|---|---|---|---|---|
| DAAD-X | 是 | 官方直链 tar 18,585,647,156 bytes；HF 八个媒体目录合计 23,045,013,921 bytes | 官方仅给 clip UUID；driver/session/source-group 未发布 | 部分可映射；U-turn 必须排除，且原标签为互斥 7 类 | 原生 17 类多标签 ego explanations，最接近但不等于 21 类 | 论文称天气/时段多样，但 CSV 无逐 clip 严重度字段 | 唯一预检候选；停止训练 |
| BDD-X | 是 | 731,609-byte 注释 ZIP；6,970 视频、77+ h、26K+ activities、8.4M+ frames | 6,970 个源视频；activity 不能当独立样本 | 只能从自由文本动作描述编码 | 自由文本 explanation，无 21 类金标 | 只有自然条件描述，无可冻结分级字段 | STOP |
| PSI | 否 | 通过申请后提供视频、CV/cognitive annotations 与 split；主页称 196 个唯一 encounter scenes | encounter scene；仓库使用 204 个 video IDs | 速度与方向只能部分交叉映射 | 人类自由文本 reasoning，无 21 类金标 | 无冻结的天气严重度轴 | STOP_ACCESS |
| VLA4CoDrive | 是 | GitHub API 报告仓库 3,211,618 KB；Action 2,160 JSON、Language 2,184 JSON；并非论文宣称的完整 8-town 规模 | 只有 9 个基础 scene IDs，跨 8 weather × 3 vehicles × 10 windows 重复 | 可由控制/轨迹阈值派生 | Reasoning 是 VLM 生成自由文本，不是离散金标 | 8 个合成天气可配对，但不是自然严重度且只有 9 个来源场景 | STOP_PSEUDOREPLICATION |

## 1. DAAD-X：唯一值得继续预检，但当前不能训练

### 官方性与可获得性

- [ICCV 2025 官方论文](https://openaccess.thecvf.com/content/ICCV2025/papers/Karuppasamy_Towards_Safer_and_Understandable_Driver_Intention_Prediction_ICCV_2025_paper.pdf)把 DAAD-X 定义为 DAAD 的真实道路视频子集，包含 1,568 个 7–15 秒 clips、7 个 maneuver 类、15 个 gaze explanations 和 17 个多标签 ego-vehicle explanations。
- [作者项目页](https://mukil07.github.io/VCBM.github.io/)直接指向 [Skyrmion/DAAD-X](https://huggingface.co/datasets/Skyrmion/DAAD-X)，因此该 HF 数据集可以确认是作者官方发布，而不是第三方镜像。
- [作者官方代码仓库](https://github.com/Mukil07/Explainable-Driver-Intention-Prediction)同样指向数据集；本轮核验的 `main` commit 为 `932c463b10f2cad42d2d3854376b40a919f47d0a`。
- 作者仓库还给出 [CVIT 官方整包直链](https://cvit.iiit.ac.in/images/datasets/daadx/daadx.tar.gz)。2026-07-31 的 HTTP range 响应为 `206`，`Content-Range: bytes 0-0/18585647156`，无需登录或人工审批。
- HF card 标注 `apache-2.0`。这足以授权按 card 使用 HF 发布物，但 CVIT 直链页面没有单独展示底层 DAAD 视频许可文本；因此公开仓库只应提交代码、清单哈希和派生统计，不应重新分发视频，除非作者进一步明确底层媒体许可。

### 当前 HF 完整性复核

只读取 HF API 文件清单与四个小型 CSV，未下载视频。当前 HF revision 为 `35eddaa90667beffc5481e014df8fc6176ed0168`。

- `train.csv` / `val.csv` / `test.csv` 分别有 `1096 / 313 / 157` 行和同数唯一 UUID；三个 split 的 UUID 交集均为 0，总并集为 1,566。它与论文/代码 README 的 `1,568` 不一致：当前发布少 2 个 split 条目。
- `total.csv` 有 1,725 行，`time.csv` 有 1,951 行，二者也不等于 1,566 条正式 split 并集，不能把任一文件默认为正式总体。
- `common/front_view_common` 有 1,721 个 MP4、3,015,220,288 bytes（2.808 GiB），其中 294 个不在正式 split；正式 1,566 个 UUID 中有 139 个 front-view 文件缺失。
- 可用于 front-view 的正式样本仅为：train `994/1096`、val `285/313`、test `148/157`，合计 `1427/1566`。缺失分别为 `102/28/9`，缺失率 `9.31% / 8.95% / 5.73%`。
- HF 八个媒体目录的文件数为：`aria_common=1721`、`ariagaze_view_common=1799`、`driver_common=1721`、`front_view_common=1721`、`gaze_common=1721`、`left_view_common=1721`、`rear_view_common=1721`、`right_view_common=1721`；总计 23,045,013,921 bytes（21.462 GiB）。目录计数不一致进一步要求整包级绑定审计。

缺失不能假设为完全随机。按 maneuver，缺失率从 Right Turn 的 `15/213=7.04%` 到 Left Lane Change 的 `24/175=13.71%`；U-turn 为 `5/49=10.20%`。稀有解释类别的波动更大：gaze 类 14 缺 `9/30=30.00%`，ego 类 16 缺 `4/16=25.00%`，而部分稀有类缺失为 0。样本太少且没有预注册缺失机制检验，不能据此断言系统性方向，但足以拒绝 MCAR 假设和“直接删掉 139 条即可”的处理。

### 动作、理由与 ARSC 映射

可预注册的最小动作 crosswalk 是：Straight → Forward；Slow/Stop → Stop；Left Turn 与 Left Lane Change → Left；Right Turn 与 Right Lane Change → Right；U-turn 排除。该映射仍有两个构念差异：DAAD-X 的 7 类 maneuver 是互斥单类，而 BDD-OIA 是四项多标签；Slow/Stop 合并标签也不能严格区分减速与停车。因此只能作为相邻构念的外部检验，不能宣称复刻 BDD-OIA 动作任务。

17 个 ego explanations 是当前所有候选中唯一原生、人工审阅的多标签理由向量，可以直接评价 rationale macro/micro/per-class F1。它们与 BDD-OIA 的交通灯、前车、切入、左右车道、转弯等概念有明显语义交集，但不是同一个 21 类本体；不得把缺少的 4 类补成恒负标签，也不得用文本模型补标后称为金标。正式外部结果应报告原生 17 类，并把预先冻结的语义 crosswalk 仅作为描述性附录。

### 独立性、严重度与成本

论文说明原始 DAAD 跨多个 drivers、天气、时段和场景，但当前 CSV 只有 clip UUID、maneuver、gaze label 和 17 维 ego vector，没有 driver、route、continuous-session 或 source-video group。论文采用的是按标签分层的 `70/20/10` split，而不是明确的 driver/session-group split。UUID 不重叠只能证明 clip ID 不重复，不能证明同一司机、同一路段或同一连续采集段没有跨 split。该分组泄漏风险是验证性训练的硬阻断项。

CSV 也没有逐 clip weather、illumination 或自然严重度标签，所以不能冻结自然 severity 曲线；只能在通过分组门后另做与 Round 10 相同的人工像素扰动，这验证的是跨数据集的算子响应，而不是自然天气响应。

若未来通过完整性与分组门，最小成本方案是只使用 front view，在每个 7–15 秒 clip 冻结一个决策前 anchor frame，训练同一轻量 backbone 的 Action-only 与 Joint，各 5 个配对种子。下载成本约为 front-only 2.808 GiB（HF 当前不完整）或官方整包 18.586 GB；视频解码、来源聚类和十次训练属于中等成本。直接训练全视频/多视图模型则为高成本，且不再是 BDD-OIA 架构对照，不获本轮授权。

## 2. BDD-X：容易获取，但不是独立外部验证

[官方仓库](https://github.com/JinkyuKimUCB/BDD-X-dataset)给出的 Google Drive 链接当前无需登录即可返回 `BDD-X-Dataset.zip`，`Content-Length=731609`。ZIP 只含 `BDD-X-Annotations_v1.csv` 与 `{train,val,test}.txt`；视频通过 CSV 中的源 URL 另行获取，逐 URL 当前可用性未在本轮下载审计。[官方统计](https://github.com/JinkyuKimUCB/BDD-X-dataset#statistics)为 6,970 个约 40 秒视频、77+ 小时、26K+ 带时间戳 activities、8.4M+ frames，split 为 `5597/717/656` 个视频。

每个 activity 有人类动作描述与 explanation，但二者均为自由文本。可以用结果盲词典把明显的 straight/stop/left/right 短语编码为四动作，也可以人工把 explanation 编入 21 类，但这会创建新的测量工具，而不是复用已有金标；必须另做双人盲标一致性研究，成本高且不能直接支持原 RQ。

独立 bootstrap 单元必须是 6,970 个源视频，不能把同一视频内 3–4 个 activities 当独立样本。更致命的是 BDD-X 与 BDD-OIA 都来自 Berkeley DeepDrive/BDD 数据源；在视频 ID 和感知哈希去重之前，它不是来源独立的外部数据集。官方描述提到昼夜、道路类型和季节多样性，但公开注释没有冻结的逐 activity 分级天气轴。

[UC Berkeley 许可](https://github.com/JinkyuKimUCB/BDD-X-dataset/blob/master/LICENSE)允许教育、研究和非营利用途下使用、复制、修改和分发，但要求保留版权与免责声明；商业使用需另行许可。即使如此，本项目不应重新分发源视频或帧。

成本方面，完整 77 小时视频下载、解码、与 BDD-OIA 去重以及自由文本双人编码均为高成本；在完成这些工作前没有验证性收益，故 `STOP_BDDX_SOURCE_AND_LABEL_NONINDEPENDENCE`。

## 3. PSI：科学语义接近，但访问门直接失败

[NeurIPS 2025 官方论文](https://papers.neurips.cc/paper_files/paper/2025/hash/436fb0fa57c75e0d2063b5bc19a21da1-Abstract-Datasets_and_Benchmarks_Track.html)和[官方主页](http://pedestriandataset.situated-intent.net/)把 PSI 定义为带人类解释的真实行人冲突数据。主页当前报告 PSI-2.0 有 196 个唯一 encounter scenes、74 名人类驾驶员/标注者的 987K+ intent estimations 和 5,773 个 segmentation boundaries/reasoning explanations。官方 GitHub 则以 `video_0001`–`video_0204` 组织 PSI 2.0，并提供 train/val/test split；因此 204 是文件 ID 范围，196 才是主页宣称的唯一场景数，二者不得混作独立样本数。

[官方 Driver Decision 仓库](https://github.com/PSI-Intention2022/PSI-DriverDecision-Prediction)明确给出 speed：`increaseSpeed/decreaseSpeed/maintainSpeed`，direction：`goStraight/turnLeft/turnRight`，并有 explanation 自由文本。Left/Right 可直接映射；Forward 可由 goStraight 与非停止速度近似；但 decreaseSpeed 不能自动等同 Stop，仓库注释和基线输出对是否含独立 stop 还存在表述差异。理由虽由人类产生，却不是 21 类多标签金标。

访问门在 2026-07-31 仍未解除。官方主页的 “Download Data” 实际跳转到 [Request Access Google Form](https://docs.google.com/forms/d/e/1FAIpQLSfuzL_3E8pGEU0xI0pnRfX15fGqUgks4XVu2ClPQ8V05oU0Cg/viewform?usp=sf_link)，表单明确只向大学和非营利研究机构授权，不向个人或商业实体授权，并要求机构邮箱、PI 信息、仅学术用途确认及接受 [Data Use Agreement](https://s3.amazonaws.com/pedestriandataset.situated-intent.net/TASI+Benchmark+Data+Sharing+Agreement_PSI.pdf)。这不是无需人工审批的公开下载，也不能假定允许重分发。

若已获授权，196 个 encounter scenes 的训练/评估成本较低到中等；但需要把自由文本解释重新标成 21 类且没有自然天气 severity 轴。当前机器结论为 `STOP_PSI_MANUAL_APPROVAL`。

## 4. VLA4CoDrive：公开但只有九个基础来源场景

[WACV 2026 官方论文](https://openaccess.thecvf.com/content/WACV2026W/LLVM-AD/html/Boroujeni_VLA4CoDrive_Vision-Language-Action_Dataset_for_Cooperative_Autonomous_Driving_WACVW_2026_paper.html)宣称 8 towns × 8 weather、约 10M vision samples、150K language annotations 和 1M action records。[官方仓库](https://github.com/SayedPedramHaeri/VLA4CoDrive)为无需审批的公开 GitHub 仓库并采用 Apache-2.0。

但是本轮从官方 GitHub tree API 对当前 `main`（`d8d6b290b7acfe1ae89b75f2d72fc8f94deeef61`）复核，实际可下载的 Action 子树只有 2,160 个 JSON（298,596,568 bytes），Language 子树 2,184 个 JSON（6,702,264 bytes），二者都只出现 `Town10HD` 与 `scene001`–`scene009`。2,160 正好等于 `8 weather × 3 vehicles × 9 scenes × 10 windows`；天气、车辆和窗口都不是新的来源独立场景。独立单元上限是 9 个基础 scene groups，而不是 2,160。

动作可以由 steer/throttle/brake、速度和 30-step trajectory 用训练集内冻结阈值派生；但 Context/Caption/Description/Reasoning 是 VideoLLaMA2 生成的自由文本，不是人工离散理由金标。8 个 frame-aligned 合成天气适合受控配对，却不能当成自然天气独立样本，也没有足够的 9 个来源组支撑稳定层级推断。下载和训练成本低到中等不弥补伪重复，故保持 `STOP_VLA4CODRIVE_PSEUDOREPLICATION`。

## 决策门与唯一后续动作

DAAD-X 只有在下列所有结果盲门通过后，才允许另行申请训练 GO：

1. 对官方 `daadx.tar.gz` 做只读清单与 SHA256 绑定，证明 1,566 个正式 split UUID 均有可解码 front view，或在结果盲协议中解释并冻结唯一合法总体；不得把 HF 的 139 个缺失样本静默删除。
2. 获得官方 driver/session/source IDs，或用时间连续性、视觉近重复和多视图同步信息建立保守 source groups；train/val/test 的 group 交集必须为 0。
3. 重新冻结 grouped split；每个 group 只能属于一个 split，所有缺失处理、U-turn 排除和 anchor frame 规则必须在标签结果读取前固定。
4. 使用原生 17 类 ego explanations 作为正式 R 轴；BDD-OIA 21 类 crosswalk 仅作描述性分析。
5. 只允许 front-view anchor-frame 的配对五种子最小实验。自然 weather severity 继续记为 `UNAVAILABLE`；任何 brightness/blur/noise 轴必须明确是合成扰动外部复现。

在这些门通过前，允许的唯一动作是 `DAADX_DOWNLOAD_AND_GROUP_INTEGRITY_PREFLIGHT_ONLY`，禁止模型训练、验证集调参、测试集推理和任何 ARSC 成功主张。

## 官方证据入口

- DAAD-X：[ICCV 2025 论文](https://openaccess.thecvf.com/content/ICCV2025/papers/Karuppasamy_Towards_Safer_and_Understandable_Driver_Intention_Prediction_ICCV_2025_paper.pdf)、[项目页](https://mukil07.github.io/VCBM.github.io/)、[代码](https://github.com/Mukil07/Explainable-Driver-Intention-Prediction)、[HF 数据](https://huggingface.co/datasets/Skyrmion/DAAD-X)、[官方 tar](https://cvit.iiit.ac.in/images/datasets/daadx/daadx.tar.gz)。
- BDD-X：[仓库与统计](https://github.com/JinkyuKimUCB/BDD-X-dataset)、[ECCV 2018 论文](https://openaccess.thecvf.com/content_ECCV_2018/papers/Jinkyu_Kim_Textual_Explanations_for_ECCV_2018_paper.pdf)、[许可](https://github.com/JinkyuKimUCB/BDD-X-dataset/blob/master/LICENSE)。
- PSI：[NeurIPS 2025 论文](https://papers.neurips.cc/paper_files/paper/2025/hash/436fb0fa57c75e0d2063b5bc19a21da1-Abstract-Datasets_and_Benchmarks_Track.html)、[主页](http://pedestriandataset.situated-intent.net/)、[数据准备仓库](https://github.com/PSI-Intention2022/PSI-Dataset)、[Driver Decision 仓库](https://github.com/PSI-Intention2022/PSI-DriverDecision-Prediction)、[申请表](https://docs.google.com/forms/d/e/1FAIpQLSfuzL_3E8pGEU0xI0pnRfX15fGqUgks4XVu2ClPQ8V05oU0Cg/viewform?usp=sf_link)。
- VLA4CoDrive：[WACV 2026 论文](https://openaccess.thecvf.com/content/WACV2026W/LLVM-AD/html/Boroujeni_VLA4CoDrive_Vision-Language-Action_Dataset_for_Cooperative_Autonomous_Driving_WACVW_2026_paper.html)、[仓库](https://github.com/SayedPedramHaeri/VLA4CoDrive)。
