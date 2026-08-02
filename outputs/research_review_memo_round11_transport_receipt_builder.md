# Round 11 DAAD-X transport receipt builder 独立提交前审查

日期：2026-08-02  
裁决：`GO_COMMIT_TRANSPORT_RECEIPT_BUILDER`

## 审查边界

本轮只审查 transport-only receipt builder、合成测试、已提交 range assembler/测试及冻结 Round 11 协议。未读取、哈希或解析当前 DAAD-X 分块/归档，未运行正式 receipt，未打开 gzip/tar，未读取标签或视频，未执行 G0–G8、训练或推理。

## 通过项

- 正式常量锁定为 original URL `https://cvit.iiit.ac.in/images/datasets/daadx/daadx.tar.gz`、resolved CDN URL `https://cdn.iiit.ac.in/cdn/cvit.iiit.ac.in/images/datasets/daadx/daadx.tar.gz`、带双引号 ETag `"68089dd7-453ca7834"`、总字节数 `18,585,647,156`、range 大小 `268,435,456`，对应恰好 70 段；builder 拒绝替换这些 transport 常量。
- assembler manifest 顶层、parameters、assembled 和每个 chunk 的字段集均为 exact allowlist；chunk index/order、规范文件名、range start、byte count、suffix、SHA 和最后余段均由固定公式验证。
- assembled archive 仅作为 opaque bytes 流读取，不打开 gzip/tar；同一次 streaming 同时计算整档 SHA、精确字节数和每个固定 range SHA，并逐项对照 manifest。因此 manifest 的整档 SHA 与 70 段 SHA 都绑定到同一 assembled bytes。
- manifest 从同一捕获字节缓冲解析和哈希；长 archive scan 后再次要求磁盘 manifest 字节完全一致，关闭已识别的 manifest TOCTOU。
- CLI 在路径解析前拒绝 manifest/archive symlink；manifest/archive alias 被拒绝。四个实现角色、顺序、repo-relative path、文件 SHA 固定，重复 role、顺序变化、symlink 和 hardlink identity alias 均 fail closed。
- receipt JSON 使用 sort-keys、紧凑 separators、UTF-8、拒绝 NaN、单换行，重复构建确定一致。
- publication 使用同目录 exclusive `xb` 临时文件、文件 fsync、no-overwrite hard link、临时文件清理和父目录 fsync。竞争者 output 或预存 temp 不会被删除；link failure 只清理本次拥有的 temp。

## 测试证据

- Reviewer-local synthetic command：`python -m pytest -q tests/test_build_round11_daadx_transport_receipt.py tests/test_assemble_verified_ranges.py`
- 结果：`65 passed, 3 skipped in 2.43s`。
- 三个 skip 均来自当前 Windows 环境无法创建 symlink/hardlink；代码路径同时有显式 fail-closed 检查，其余竞态和结构反例均通过。
- 未使用正式常量运行 builder，未产生真实 receipt。

## 残余限制

- receipt 证明“当前 opaque assembled bytes 与 reviewed assembler manifest 相符”，不独立证明远端服务器实际在每次请求中返回该 ETag；`expected_etag` 是冻结 transport 合同。最终 transport reviewer 仍须对真实 manifest、receipt 和 archive 做 opaque hash 复核。
- Windows 目录 fsync 是 best-effort；崩溃可能留下 owned temp，但下一次执行会 fail closed，不得自动覆盖。
- builder 不授权 archive content access。完整 receipt 生成后仍需独立 transport 复核、严格 execution binding、单次 claim 和新的 GO_RUN 审查。

## 授权边界

本裁决仅授权提交下列 exact builder/test bytes 及本审查证据。它不是 GO_RUN，不授权读取或解析 DAAD-X 归档/分块，不构成 G0–G8 证据，不授权正式 preflight、标签/视频访问、训练、推理或外部有效性结论。
