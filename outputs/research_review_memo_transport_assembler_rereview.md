# Transport range assembler 修正版独立复审

复审日期：2026-08-02  
裁决：`GO_COMMIT_TRANSPORT_ASSEMBLER`

## 1. 复审范围与严格边界

本轮只读复核以下固定候选：

- `scripts/assemble_verified_ranges.py`
- `tests/test_assemble_verified_ranges.py`

没有修改候选；没有访问、列举、读取或解析 `data/`；没有接触真实 DAAD-X chunks/tar；没有执行网络、gzip/tar、视频、标签、formal preflight、训练或推理。

本裁决只授权提交本次固定工具、测试和审阅证据，**不授权真实数据组装，也不构成 `GO_RUN`**。

## 2. 固定字节

| 文件 | SHA-256 |
|---|---|
| `scripts/assemble_verified_ranges.py` | `34BD9B4DB03C1338D7E5F72048F5FABD93C29A89995AA0B6CBD6ED7BEF632DE4` |
| `tests/test_assemble_verified_ranges.py` | `5BD6AE33CB5A48B451C67B2B9BF20EB0A66B5F74842DC426FAA4B229DA6882B8` |

本次独立重算与委托固定 SHA 完全一致。

## 3. 上轮阻断 T1 复核：通过

上轮问题是备份变量 `None` 同时表示“原目标不存在”和“原目标存在但备份尚未成功”，导致备份准备失败后统一 rollback 可能误删旧 output/manifest。

修正版已经结构性分离两个阶段：

1. `old_output`、`old_manifest` 明确记录事务前存在性。
2. force backup preparation 在独立 `try` 中完成；第一或第二个 `_copy_backup` 抛错时只调用 `_abort_backup_prep`。
3. `_abort_backup_prep` 只清理已经创建的 backup 副本，不调用 `_rollback_one`，也不修改或删除原 output/manifest。
4. 只有所有需要的备份均已返回且仍存在，代码才越过预发布不变量进入组装和 publish 事务。
5. publish 阶段异常后才运行原有两目标独立 rollback。

新增的两个合成回归测试分别覆盖：

- 第一个备份立即失败：只调用一次备份函数，两个原目标字节保持不变，没有 backup/assemble/manifest 临时产物。
- output 备份成功、第二个 manifest 备份失败：已创建的 output backup 被清理，两个原目标字节保持不变，发布阶段没有开始。

因此 T1 对正常异常路径已关闭。

## 4. 整体 transport 边界复核

### 范围、命名与尺寸

- `compute_ranges` 仅由 `expected_total` 和正 `chunk_bytes` 推导 `[0,total)` 的连续无缝分区，末块余数、零长度和高索引命名均有覆盖。
- chunk 文件名必须等于对应索引的规范 `chunk_{index:03d}.resilient.bin`；缺失、额外同模式文件、错误数字宽度和错误尺寸均 fail-closed。
- 与 chunk pattern 匹配的扫描时 symlink 被拒绝；output/manifest symlink、目录目标、二者解析为同一路径、以及与预期 source chunk 的路径冲突均被拒绝。

### 完整性

- 每个 chunk 在 scan 阶段流式计算 SHA-256 和字节数；assembly 阶段重新打开并第二次独立计算 SHA-256/字节数，发生中途修改时拒绝。
- 组装临时文件 flush+fsync 后以同目录 `os.replace` 发布。
- 发布后的 output 在 manifest 发布前被再次完整流式读取，size 和 SHA-256 必须与组装期值一致。
- manifest 固定 schema、排序键、固定换行与仅由已验证输入导出的内容，使相同路径名和输入下字节确定。

### 双文件可恢复事务

- 默认不覆盖既有 output 或 manifest。
- force 模式在任何 publish 前复制并 fsync 所有既有目标；publish/post-verify/manifest replace 或目录 fsync 失败时分别恢复旧目标或删除事务中新建目标。
- 一个目标 rollback 失败不会阻止另一个目标继续恢复；未消费的 backup 会保留并通过 `RollbackError` 报告。
- manifest replace 已完成但后续目录 fsync 失败的路径会进入整体 rollback，不留下正常异常模型下的半产物。
- 实现只声明每个文件的原子 replace，没有错误声称跨文件瞬时原子性。

### 无外部或归档语义

候选只导入标准库 `argparse/hashlib/json/os/re/tempfile/dataclasses/pathlib`；没有网络、subprocess、gzip、tarfile 或 archive parser。所有 chunk 内容均按不透明字节处理。

## 5. 测试证据分级

本复审执行：

```powershell
D:\anaconda3\envs\Nuclear_Transformer\python.exe -m pytest tests\test_assemble_verified_ranges.py -q -p no:cacheprovider
```

结果为 `5 passed, 35 errors`。35 个错误全部发生在 pytest `tmp_path` fixture setup，统一原因为 Windows 沙箱不能读取 `C:\Users\user\AppData\Local\Temp\pytest-of-user`；没有观察到候选测试断言失败。此前尝试工作区 `--basetemp` 同样受 ACL 限制，提权重跑被中断。因此本复审不虚假声称独立完成了 40 项动态复现。

主 agent 报告的目标/全仓通过结果属于二级证据；其中此前的 `38 target / 217 full` 对应修复前测试数量，不能单独证明新增两项测试，但新增测试源码与修复控制流已由本复审逐行核对。DeepSeek 机械预审因 API `fetch failed` 未产生可采纳结果。

鉴于本裁决只授权提交、T1 修复控制流明确且候选未获真实执行权，当前环境 ACL 不作为提交阻断；在任何真实 chunk 组装授权之前，仍必须在可用的正常临时目录环境对当前固定 SHA 完整运行目标与全仓测试。

## 6. 残余风险与后续约束

- 两文件事务是“可恢复的逐文件原子发布”，不是跨文件原子提交；进程终止或断电可能发生在两个 replace 之间，消费者必须只接受 manifest/output 哈希互相一致的完整对。
- `_fsync_dir` 在宿主不支持目录句柄时会 best-effort 返回；Windows 上的掉电持久性弱于成功完成目录 fsync 的平台。
- 路径和 symlink 检查与后续打开之间仍存在一般本地并发替换 TOCTOU；真实使用时 chunk 目录和目标目录必须由单一受信进程控制并禁止并发写入。
- 建议 output/manifest 放在 chunk 目录之外，且不要使用 `chunk_*.resilient.bin` 命名，以避免污染 chunk namespace。
- `assert` 形式的备份就绪检查不应被视为外部安全边界；真实运行不得使用 `python -O`，未来可改为显式异常以进一步 fail-closed。

以上均不否定当前提交价值，但必须在未来真实 transport 授权和执行协议中显式约束。

## 7. 裁决与 claim boundary

最终裁决：`GO_COMMIT_TRANSPORT_ASSEMBLER`。

仅授权提交以下固定字节及本复审产物：transport assembler、对应合成测试、复审 memo 和机器裁决。该 GO 不授权：

- 访问、列举、哈希或组装任何真实 DAAD-X chunk；
- 打开、解析、列举或解压 gzip/tar；
- 真实数据删除、覆盖或 force 运行；
- formal preflight、视频/标签访问、训练、推理；
- `GO_RUN` 或任何科研 gate 结论。
