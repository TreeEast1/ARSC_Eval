# ARSC-Eval 第二数据集筛选（Round 1）

状态：只完成一手来源核验，尚未下载。按照独立审阅意见，BDD-OIA
内部效度闸门通过前不启动第二数据集训练。

## 首选：VLA4CoDrive

- 官方仓库：<https://github.com/SayedPedramHaeri/VLA4CoDrive>
- 官方论文页：
  <https://openaccess.thecvf.com/content/WACV2026W/LLVM-AD/html/Boroujeni_VLA4CoDrive_Vision-Language-Action_Dataset_for_Cooperative_Autonomous_Driving_WACVW_2026_paper.html>
- 许可：Apache-2.0；CARLA 合成域；公开仓库，无账号/表单门槛。
- 官方规模：约 10M vision samples、150K language annotations、1M
  action records、300–360 小时；8 towns × 8 weather，frame-aligned replay。
- 可用监督：多视角 RGB、COCO/VOC/KITTI 2D/3D 标注、逐帧
  steer/throttle/brake、30-step trajectory，以及 clip-level context、
  caption、description、reasoning。

与 ARSC 的最小映射方案：

1. A：仅用训练集冻结的 `vEgo`、brake、trajectory 横向位移阈值映射
   Forward/Stop/Left/Right。
2. R：先对 reasoning 做固定词典 ontology 的覆盖率、歧义率人工审计；
   未通过前不报告 Rationale-F1。
3. S：复用动作概率的 AURC、UAR@90、ECE。
4. C：复用 brightness/blur/noise；frame-aligned weather 只作为同一
   Consistency 指标的外部压力条件。
5. CEG：优先利用官方 2D boxes，避免 BDD-OIA 的通用 YOLO 伪框问题。
6. split：必须按 scene_id 分组；同一 scene 的 weather、vehicle、window
   不得跨 train/validation/test。

定位：独立合成域的受控机制验证，不单独代表真实世界外部效度。

## 备选

- PSI：真实 pedestrian-conflict 场景、有人类 reasoning 和 bbox，科学匹配
  较强；但官网需要 Google Form 人工申请，本轮无法无人值守获取。
- BDD-X：公开视频与人工 action/explanation 可获取，但理由是自由文本，
  缺少关键框，且与 BDD-OIA 同源；必须先做视频 ID/感知哈希去重。

## 暂不采用

- DriveLM / nuScenes：需要注册或表单。
- Reason2Drive：官方完整 train/eval 尚未发布。
- nuReasoning：官方页面仍标注 Coming Soon。
- CoVLA：Hugging Face gated access 与专门协议。

## 决策

若 BDD-OIA 的 mask 内部效度无法通过，优先在 VLA4CoDrive 做一个
scene-disjoint 小型可行性审计，验证动作类平衡、理由 ontology 覆盖率、
weather 对齐和 bbox 可用性；审计通过后再启动训练。
