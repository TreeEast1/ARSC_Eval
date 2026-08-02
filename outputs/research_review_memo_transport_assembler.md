# Transport range assembler 独立安全复审

复审日期：2026-08-02  
裁决：`STOP_FIX_TRANSPORT_ASSEMBLER`

## 范围与边界

本轮仅只读审阅：

- `scripts/assemble_verified_ranges.py`
- `tests/test_assemble_verified_ranges.py`

没有访问、列举、读取或解析 `data/`，没有接触真实 DAAD-X chunk/tar，没有执行 gzip/tar 语义，也没有修改候选或测试。即使未来复审通过，也只允许提交 transport 工具，不授权真实数据拼接、归档读取或 `GO_RUN`。

## 精确字节

| 文件 | SHA-256 |
|---|---|
| `scripts/assemble_verified_ranges.py` | `3A8D71E53EE1F2AD72D30B1D1F456DA4B08E89C813552CDF4D70BF6CF024C97D` |
| `tests/test_assemble_verified_ranges.py` | `5F64C175F12DEDE2938EC150C56E6B48ACFBAB1298AC8BF80E1E53C5FDA7B445` |

## 已核对通过的设计

- `compute_ranges` 从 `expected_total/chunk_bytes` 唯一导出连续范围，并正确处理末块余数、空输入和至少四位的高索引规范命名。
- scan 会拒绝缺块、错尺寸、额外同模式文件、非规范数字宽度和扫描时可见的 symlink；output/manifest 相同解析路径或与预期 source chunk 冲突也会拒绝。
- 每个 chunk 在扫描时流式 SHA-256 一次，在追加时再独立计算一次；组装后发布的 output 又被重新流式验证 size 与 SHA。
- 默认拒绝覆盖；output、manifest 的目录目标和 symlink 目标均在写入前拒绝。
- manifest 使用排序键和固定结构，合成输入下可确定复现。
- manifest replace 后目录 fsync 失败、发布阶段失败、post-verify 失败及单个 rollback 失败继续处理另一目标的意图均有明确代码和合成测试。
- 模块没有导入或调用 gzip/tarfile，不声明归档语义，只处理不透明字节。

## 阻断发现 T1：备份建立失败会误删旧目标

严重度：阻断提交。

`assemble()` 在进入同一个大 `try` 后依次为旧 output 和旧 manifest 调用 `_copy_backup`。`backup_output`、`backup_manifest` 初值均为 `None`；异常处理无条件调用：

```python
_rollback_one(output, backup_output)
_rollback_one(manifest, backup_manifest)
```

而 `_rollback_one(path, None)` 的语义是“此目标在事务前不存在”，因此会执行 `path.unlink(missing_ok=True)`。

这导致：

1. 若第一个 `_copy_backup(output, ...)` 自身失败，两个 backup 变量都仍为 `None`，异常路径会删除原有 output 和原有 manifest。
2. 若 output 备份成功、随后 `_copy_backup(manifest, ...)` 失败，output 可从备份恢复，但原有 manifest 会因 `backup_manifest is None` 被误删。

此时尚未发生任何 publish，旧目标本应完全不变。当前实现把“事务前不存在”和“事务前存在但备份尚未成功”折叠为同一个 `None` 状态，违反了候选声明的 force 可恢复两文件事务，也会造成不可恢复的数据丢失。现有 38 个测试没有覆盖第一/第二个备份创建失败。

## 必须修复与复测

- 分离记录每个目标的 `existed_before`、`backup_ready` 与 `published/replaced` 状态。
- 备份准备阶段任一 `_copy_backup` 失败时，不得调用“删除新目标”的 rollback 分支；两个旧目标必须保持原字节。已完成的临时备份应安全清理，若清理失败则保留并明确报告。
- 只有原先不存在且确实已发布的新目标，才允许在 rollback 中删除。
- 新增至少两个合成负向测试：第一个旧目标备份失败；第一个备份成功而第二个旧目标备份失败。两种情况均须断言旧 output/manifest 字节完全保留，并验证备份/临时文件处置。
- 修复后重新运行目标测试与全套测试，并重新计算候选 SHA，再进行独立复审。

## 测试证据

独立目标测试首次运行得到 `5 passed, 33 errors`；33 个错误全部发生在 pytest `tmp_path` setup，原因为沙箱无权访问默认临时目录 `C:\Users\user\AppData\Local\Temp\pytest-of-user`，不是候选断言失败。改用工作区 `--basetemp` 仍受 ACL 限制；提权重跑随后被中断，因此本复审没有声称独立复现 `38 passed`。

主 agent 报告的 `38 target passed / 217 full passed` 仅作为二级证据，不能覆盖上述未测试的备份准备失败分支。按混合路由规则尝试的 DeepSeek 机械预审因 API `fetch failed` 没有产生可采纳证据。

## 裁决与 claim boundary

裁决为 `STOP_FIX_TRANSPORT_ASSEMBLER`。在 T1 修复、补测、重新哈希并通过独立复审前，不授权提交当前 transport assembler 候选。

本裁决不授权访问或拼接真实 chunks，不授权读取/列举/解压真实 tar，不授权视频/标签访问、formal preflight、训练、推理或 `GO_RUN`。
