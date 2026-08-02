# Round 11 DAAD-X `NOT_RUN` 执行绑定草案独立复审

复审时间：2026-08-02（UTC）  
复审角色：独立科研与运行安全复审 agent  
裁决：`GO_COMMIT_NOT_RUN_BINDING_DRAFT`

## 1. 复审范围与禁区

本次仅审阅以下候选文件：

- `scripts/create_round11_daadx_execution_binding_draft.py`
- `tests/test_round11_daadx_execution_binding_draft.py`
- `outputs/validity/round11_daadx_execution_binding.draft.json`

并只读核对其绑定的 frozen protocol、formal runner、runner tests、core 与上一轮 runner reviewer decision。没有读取、列举、解压或校验 `data/` 下任何官方归档；没有视频解码、真实标签读取、formal preflight、训练或推理；没有修改 protocol、core、runner 或候选文件。

本裁决只允许把不可执行草案提交进 Git，**不构成 `GO_RUN`，也不构成任何 DAAD-X G0–G8 证据**。

## 2. 精确字节绑定

| 文件 | SHA-256 |
|---|---|
| `scripts/create_round11_daadx_execution_binding_draft.py` | `7C4609172FAFD7C38BD42496D4A96AE92B38C8FD900CF5D8B64F57775269D493` |
| `tests/test_round11_daadx_execution_binding_draft.py` | `B23B5D90F31D4262224FB1C0F9F4CDC5CE66C35441ADF93F4DA12AFF70150EF4` |
| `outputs/validity/round11_daadx_execution_binding.draft.json` | `4DCFF1D7110B032DBE458CE37D5B95CB9C469F47A5EF62C05C2156219FA6B5AC` |
| `outputs/validity/round11_daadx_preflight_protocol.json` | `01642976FAE14A43A25BDD65CA8D007E3C944D2B91771907ABE1B59553FAE880` |
| `scripts/run_round11_daadx_preflight.py` | `E61B2C6CEEAE8D1A51FD614E71B2357FDED863C3BEF81816AFD8D3CC96D5AB53` |
| `tests/test_round11_daadx_preflight_runner.py` | `FCB5A57710D06CF834EF662FDE768445ED9F6358D47C0B886222F2575189ACC5` |
| `src/arsc_eval/daadx_preflight.py` | `73639F1B85F84B2A27DC650E3DE1FC203A181561FA00306BCD5A5D2E76860E53` |
| `outputs/validity/round11_runner_reviewer_decision.json` | `3C2D6AFC465DE586F1597EC149E81E8F4EED1976A025D112C13B8E2150ECB29D` |

草案内记录的 protocol、runner、runner tests、core 和 runner-reviewer SHA 与本次独立重算完全一致。

## 3. D1–D5 逐项复核

### D1 — provenance taxonomy：通过

候选生成器与真实生成物均精确列出以下五类，拼写和大小写逐项一致：

1. `AUTHORITATIVE_SOURCE_ID`
2. `AUTHORITATIVE_SESSION_ID`
3. `AUTHORITATIVE_RAW_VIDEO_ID`
4. `AUDITABLE_RAW_RECORDING_TOKEN`
5. `AUDITABLE_ACQUISITION_RIG_SESSION`

它们与 runner 的 `_PROVENANCE_REQUIREMENTS` 五个键精确对应；没有把“未发现近重复”误当作来源证据，也没有引入第六类或含糊的兜底类别。该结论只说明 taxonomy 接口相容，不说明真实 DAAD-X 已具备这些证据。

### D2 — 不完整 schema 与晋升阻断：通过

- 顶层 schema 为 `ARSC_ROUND11_DAADX_EXECUTION_BINDING_INCOMPLETE_DRAFT_V1`，decision 为 `NOT_RUN_DRAFT_ONLY`。
- 内层 schema 为 `ARSC_ROUND11_DAADX_OPERATIONAL_CONTRACT_INCOMPLETE_DRAFT_V1`，字段名是 `operational_contract_draft`；候选不存在 runner 所需的 `operational_contract`。
- annotation 三个精确成员路径、front regex、provenance member 和 ffprobe 均保持 `null`/`UNRESOLVED`，没有猜测官方归档布局。
- 四个独立 promotion blocker 明确要求：最终 binding schema/字段 allowlist、最终 operational schema 并移除 draft status、独立 `GO_RUN` reviewer decision 及哈希绑定、授权 inventory 后重新审定容量上限。
- 因 schema、decision、字段名和缺失 reviewer decision 同时隔离，不能通过原地把单个值从 `NOT_RUN` 改成 `GO_RUN` 完成晋升；必须生成新的最终合约并接受独立复审。

### D3 — 64 MiB 上限与 OOM 边界：通过（仅限当前草案设计）

- 草案 `max_member_bytes = 67,108,864`，scratch `maximum_single_file_bytes` 同为 64 MiB；两个容量区块均显式标记 `DRAFT`，没有声称 conservative/final。
- runner 先在 `_audit_raw_tar_headers` 中读取固定 512-byte 原始 header，解析 size 后立即比较 `bounds.max_member_bytes`，只有通过后才以 1 MiB 块流式 drain payload。完成整次原始审计后才进入 `tarfile.open` 的 resolved-member 遍历，因此 8 GiB PAX/member payload 不会先被 `tarfile` 整体分配。
- resolved-member 路径也在 `extractfile` 前再次比较单成员上限；selected annotation/provenance 的整块 `read()` 只对已经通过原始与 resolved 双重审计、记录在 audit map 中的 regular member 执行，当前草案上界为 64 MiB。
- 该容量值仍是待 authorized layout inventory 与独立 capacity review 的草案值；本裁决不冻结或批准它作为最终运行参数。未来最终合约仍需保持归档在单次运行期间字节不可变，并由 execution reviewer 复核实际容量与工具链。

### D4 — 上游授权、哈希与唯一性 fail-closed：通过

- 生成器要求上一轮 reviewer 的 schema、`GO_CREATE_EXECUTION_BINDING_NOT_RUN`、`candidate_bytes_frozen_for_this_review=true` 全部精确匹配。
- `create_nonrun_execution_binding_draft` 必须为 true；formal runner、archive inventory、真实 decode、真实 label 等必须为 false。
- `create_go_run_execution_binding`、`create_execution_go_reviewer_decision`、外部训练/推理、修改 protocol、写 attempt01 outputs 任一不是显式 false 都会拒绝。
- protocol、runner、runner tests、core 四个关键路径在 `reviewed_files` 中必须各出现且仅出现一次，且 SHA 必须等于当前字节；protocol 另有冻结常量 SHA。缺失、重复、陈旧哈希和错误 protocol bytes 均有负向测试。
- 真实草案还单独绑定上一轮 reviewer decision 的路径与 SHA。

### D5 — 数据访问前拒绝、原子发布、工具与 scratch：通过

- `validate_execution_authority` 在接收归档路径或执行 G0 前先读取 binding，并首先要求字典型 `operational_contract`；本草案只有 `operational_contract_draft`，因此以 `execution binding lacks operational_contract` fail-closed。纯合成测试直接覆盖此路径。
- 发布使用目标同目录 `mkstemp`、UTF-8 写入、flush、`fsync`、`os.replace`，异常时清理临时文件；默认已存在目标会拒绝，只有显式 `--force` 才能原子替换。
- 草案绑定 Python 绝对路径及 SHA、`-I` 隔离、300 秒 timeout、clean allowlist 环境；ffmpeg 绝对路径及 SHA 已记录为 `HOST_VERIFIED_DRAFT_ONLY`，ffprobe 保持 `UNRESOLVED` 并列为 blocker。
- scratch 记录绝对 root、20 GiB reserve、32 GiB cumulative cap、64 MiB single-file cap、固定工作目录名与 `EXTRACT_ONE_PROBE_REHASH_DELETE` 生命周期，并明确标记 `HOST_PATH_VERIFIED_DRAFT_ONLY`。本次复审没有进入该 `data/` 路径复验其现场容量；最终 GO_RUN 前必须重新进行 host-level 验证。

## 4. 测试证据

独立运行命令：

```powershell
$env:PYTHONPATH='src;scripts'; & 'D:\anaconda3\envs\Nuclear_Transformer\python.exe' -m pytest tests\test_round11_daadx_execution_binding_draft.py -q -p no:cacheprovider
```

结果：`19 passed in 0.31s`。

主 agent 报告的 `179 passed` 仅作为二级证据；本复审没有把它冒充独立复现。按工作区混合路由规则尝试的 DeepSeek 机械预审在沙箱内外均因 API `fetch failed` 未产生结果或修改，故没有采纳任何 DeepSeek 结论。

## 5. 裁决与严格授权边界

裁决为 `GO_COMMIT_NOT_RUN_BINDING_DRAFT`：D1–D5 的修订足以把当前三个候选字节及本复审产物提交进 Git，作为结果盲、不可执行的运行合约草案保存。

以下行为仍全部禁止：

- 把本裁决解释为 `GO_RUN` 或独立 execution reviewer decision；
- 读取、列举、解压官方大 tar 或进行真实标签/视频访问；
- 创建或发布 formal attempt01 结果；
- 训练、推理、修改/重冻结 protocol、切换科研结论；
- 原地修改本草案以伪装最终合约。

任何未来执行至少还需：授权的 transport/layout inventory、补齐精确布局与 ffprobe、独立审定容量和 host 状态、生成全新 final-schema operational contract/binding、将 exact bytes 提交到同一 HEAD，并由另一独立 reviewer 签发与这些字节互相绑定的 `GO_RUN` 决策。
