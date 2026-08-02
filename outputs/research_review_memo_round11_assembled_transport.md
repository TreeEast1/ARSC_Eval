# Round 11 DAAD-X assembled transport 独立 opaque 审阅备忘录

日期：2026-08-02  
裁决：`GO_GENERATE_ROUND11_TRANSPORT_RECEIPT_ONCE`

## 审阅边界

本次只读审阅以下 transport 对象：

- `data/external/daadx_official/chunks/` 中规范的 70 个 range 文件
- `data/external/daadx_official/daadx.assembled.tar.gz`
- `data/external/daadx_official/daadx_assembled_ranges_manifest.json`
- 已提交 assembler、receipt builder、对应测试及既有独立审阅证据

assembled archive 始终作为 opaque bytes 读取。未调用 gzip/tar 库或命令，未打开或列举 archive 成员，未读取标签、视频或模型输出，未创建 Phase1 claim，未运行 Phase1、G0–G8、训练或推理。DeepSeek worker 在执行前返回 `fetch failed`，未读取或写入文件；全部流式校验和最终裁决由主审阅者独立完成。

## Manifest 与 range 计划

- manifest SHA-256：`FDBCC19DD726F8CA5C93A8189C47A5ACBEA5E6D1EC131679B4302E7493A835DC`，15792 bytes。
- 顶层字段恰为 `schema`、`parameters`、`chunks`、`assembled`，无重复 JSON key；schema 为 `ARSC_ASSEMBLED_RANGES_MANIFEST_V1`。
- parameters 精确固定为：`chunk_bytes=268435456`、`chunk_count=70`、`expected_total=18585647156`、`suffix=resilient.bin`。
- 70 个 chunk 条目字段恰为 `file/index/range_start/byte_count/sha256`；index 为 0–69，名称严格为 `chunk_000.resilient.bin` 至 `chunk_069.resilient.bin`，range_start 连续无洞无重叠。
- chunk 0–68 各为 268435456 bytes；chunk 69 为 63600692 bytes；总计 18585647156 bytes。
- chunks 目录中与规范 range 命名模式匹配的文件集合恰好为上述 70 个，没有缺失或额外 canonical range。每个 range、manifest 和 assembled archive 均为 regular、non-symlink、`nlink==1`。

## 独立 opaque hash 证据

审阅者逐一流式读取并重算 70 个实际 chunk SHA-256，全部与 manifest 对应条目一致。同时按 range 顺序把相同实际 chunk bytes 输入一个连续 SHA-256：

- ordered-concatenation bytes：18585647156
- ordered-concatenation SHA-256：`98E6DD4D068004B090A5D62C648A727AF902EBF3B176BCE2CE044EABDE91E965`

随后独立流式读取 assembled archive：

- path：`data/external/daadx_official/daadx.assembled.tar.gz`
- basename：`daadx.assembled.tar.gz`，与 manifest `assembled.file` 精确一致
- bytes：18585647156
- SHA-256：`98E6DD4D068004B090A5D62C648A727AF902EBF3B176BCE2CE044EABDE91E965`

实际 assembled archive、manifest 声明及 70 段 ordered concatenation 的 bytes/SHA 三者完全一致。这构成组装完整成功的文件级证据，不依赖仍存活的 tmux session 或叙述性 exit-code 声明。

## 已审实现闭包

- `scripts/assemble_verified_ranges.py`：21256 bytes，SHA-256 `34BD9B4DB03C1338D7E5F72048F5FABD93C29A89995AA0B6CBD6ED7BEF632DE4`
- `tests/test_assemble_verified_ranges.py`：35243 bytes，SHA-256 `5BD6AE33CB5A48B451C67B2B9BF20EB0A66B5F74842DC426FAA4B229DA6882B8`
- `scripts/build_round11_daadx_transport_receipt.py`：13200 bytes，SHA-256 `4244F5881BBD73357D8C8B3E3F654691470EFABF7929E593616BA0BBFE2D7C75`
- `tests/test_build_round11_daadx_transport_receipt.py`：13189 bytes，SHA-256 `7633A5329EF37281C4609973E292354F3AE3934BCBCD07D1F8F04B5B9E09A3D4`

四个文件均为当前 HEAD 已跟踪且工作区 byte-exact；哈希分别匹配 assembler rereviewer 和 receipt-builder reviewer 的既有独立裁决。独立运行 `python -m pytest -q tests/test_assemble_verified_ranges.py -p no:cacheprovider` 得到 `40 passed in 2.45s`。

## 一次性 receipt 授权

允许使用上述 exact receipt builder 对本备忘录绑定的 manifest 与 opaque assembled archive 生成一次 transport receipt，固定输出为：

`data/external/daadx_official/daadx_transport_receipt.json`

该输出及其 `.tmp` 当前均不存在。builder 必须使用 no-overwrite publication；任何已有 output/temp、manifest/archive/hash/bytes/basename/implementation SHA 变化均须 STOP，不得删除、覆盖、重试或改用其他输出。生成后必须由另一轮独立 opaque reviewer 绑定真实 receipt bytes/SHA，才能进入 execution binding。

## 授权边界

`GO_GENERATE_ROUND11_TRANSPORT_RECEIPT_ONCE` 仅授权 receipt builder 对固定 manifest/archive 做一次 opaque streaming hash 并 no-overwrite 写入固定 receipt。它不授权 gzip/tar 打开或成员枚举，不授权标签/视频访问，不授权 Phase1 claim、runner、formal preflight、G0–G8、训练、推理或外部有效性结论，也不是 `GO_RUN`。
