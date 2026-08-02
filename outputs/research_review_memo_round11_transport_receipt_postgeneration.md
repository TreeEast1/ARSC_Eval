# Round 11 DAAD-X transport receipt 一次性结果后独立 opaque 审阅备忘录

日期：2026-08-02  
裁决：`ACCEPT_ROUND11_TRANSPORT_RECEIPT`

## 审阅边界

本次只读审阅固定 receipt、真实 assembler manifest、assembled archive 的 opaque bytes、已创建的 assembled transport 审阅工件，以及 HEAD-exact assembler/receipt-builder 实现与测试。未重跑 receipt builder，未调用 gzip/tar、未打开或列举 archive 成员，未访问标签或视频，未创建 claim，未运行 Phase1、G0–G8、训练或推理。

DeepSeek worker 在执行前返回 `fetch failed`，未执行检查或写入文件；全部复核和最终裁决由主审阅者独立完成。

## Receipt 原始字节与严格 schema

- path：`data/external/daadx_official/daadx_transport_receipt.json`
- bytes：1629
- SHA-256：`D738E21E5DC1976C192CFA3982E2CA2941FF3D2AF8A811BA432D51778A6B1C7F`
- 类型：regular、non-symlink、`nlink==1`
- receipt raw bytes 与 sort-keys、compact separators、UTF-8、单尾换行的 canonical JSON byte-for-byte 相等，且无重复 JSON key。

顶层字段恰为 `schema_version`、`transport_only`、`official`、`assembler_manifest`、`assembled_archive`、`chunk_plan`、`implementation`；schema 为 `ARSC_ROUND11_DAADX_TRANSPORT_RECEIPT_V1`，`transport_only=true`。所有嵌套对象与四个 implementation 记录的字段集也均精确，无额外或缺失字段。

## Official transport 与真实对象绑定

Receipt 精确记录：

- original URL：`https://cvit.iiit.ac.in/images/datasets/daadx/daadx.tar.gz`
- resolved CDN URL：`https://cdn.iiit.ac.in/cdn/cvit.iiit.ac.in/images/datasets/daadx/daadx.tar.gz`
- quoted ETag：`"68089dd7-453ca7834"`
- expected total：18585647156 bytes

真实 manifest：

- path：`data/external/daadx_official/daadx_assembled_ranges_manifest.json`
- schema：`ARSC_ASSEMBLED_RANGES_MANIFEST_V1`
- bytes：15792
- SHA-256：`FDBCC19DD726F8CA5C93A8189C47A5ACBEA5E6D1EC131679B4302E7493A835DC`

真实 assembled archive 再次独立 opaque streaming scan：

- path：`data/external/daadx_official/daadx.assembled.tar.gz`
- bytes：18585647156
- SHA-256：`98E6DD4D068004B090A5D62C648A727AF902EBF3B176BCE2CE044EABDE91E965`

receipt、manifest 和 archive 的 path、bytes、SHA 三向一致。manifest 的 70 个 chunk 条目形成从 0 到 18585647156 的连续覆盖；把实际 manifest chunk 记录规范化并 canonical 编码后得到：

`chunk_records_sha256 = A0A7C1560F907D05F842F724700B59856D638708DB55599ED129A2E4C267D5BC`

与 receipt 完全一致。

## 实现角色闭包

Receipt 中四个角色、顺序、path 和实际 SHA 均精确：

- assembler：`scripts/assemble_verified_ranges.py`，`34BD9B4DB03C1338D7E5F72048F5FABD93C29A89995AA0B6CBD6ED7BEF632DE4`
- assembler-tests：`tests/test_assemble_verified_ranges.py`，`5BD6AE33CB5A48B451C67B2B9BF20EB0A66B5F74842DC426FAA4B229DA6882B8`
- receipt-builder：`scripts/build_round11_daadx_transport_receipt.py`，`4244F5881BBD73357D8C8B3E3F654691470EFABF7929E593616BA0BBFE2D7C75`
- receipt-tests：`tests/test_build_round11_daadx_transport_receipt.py`，`7633A5329EF37281C4609973E292354F3AE3934BCBCD07D1F8F04B5B9E09A3D4`

四个文件均为当前 HEAD tracked 且工作区 byte-exact，并匹配既有独立 builder/assembler 审阅。assembled transport reviewer decision 也绑定相同 manifest/archive/builder 字节。

## 一次性与 publication 状态

先前独立裁决只授权固定输出的一次 no-overwrite 成功生成。当前观察到唯一固定 receipt 文件，内容和 SHA 完整有效；对应 `daadx_transport_receipt.json.tmp` 不存在。由于 builder 明确拒绝已有 output 或 temp，当前路径不能再次成功生成或覆盖。因此本次接受为该授权下的一次成功 transport receipt；不根据无法审计的历史叙述扩张结论。

## Git 受控 snapshot 建议

建议把源 receipt 的 **exact 1629 bytes** 复制到：

`outputs/validity/round11_daadx_transport_receipt.json`

作为 Git 受控 snapshot，assembled archive 继续保持忽略、不进入 Git。复制必须满足：

1. 不修改或删除 data 下的源 receipt；
2. snapshot 和 `.tmp` 预先均不存在，使用 no-overwrite 写入；
3. 不解析、重排或重新序列化 JSON，只复制 exact bytes；
4. 复制后重新核对源和 snapshot 均为 1629 bytes，SHA-256 均为 `D738E21E5DC1976C192CFA3982E2CA2941FF3D2AF8A811BA432D51778A6B1C7F`；
5. 仅在该复核通过后提交 snapshot 与本次审阅证据。

本审阅只提出并授权这一受控保存步骤，没有自行执行复制。

## 后续权限边界

下一步只允许设计和集成 HEAD-exact execution binding，使其绑定 receipt snapshot、真实 manifest/archive、runner/tests/core、Phase1 control、operational contract 和工具。仍不授权 archive content access、tar inventory、claim、Phase1、formal preflight、G0–G8、训练、推理或 `GO_RUN`；这些必须等待新的独立 execution reviewer decision。
