# Round 11 DAAD-X NOT_RUN execution-binding 草案独立盲审

## 裁决

**`STOP_FIX_BINDING_DRAFT_BEFORE_COMMIT`**。

当前 JSON 是不可执行的，formal runner 已独立验证会在任何 archive access 前拒绝它；因此不存在误启动 formal preflight 的即时风险。但该草案尚不适合提交为受审 operational draft：它猜测了错误的 provenance taxonomy，冒用最终 binding schema，却没有列全晋升阻断字段，并给出了可允许 8 GiB 单对象全量内存读取的“不保守”资源上限。

这不是 DAAD-X G0–G8 科学失败，也不撤销 runner 的 `GO_CREATE_EXECUTION_BINDING_NOT_RUN`。它只要求修复 binding 生成器、草案和测试后重新审阅。不得为了补 layout 而读取或列举官方 tar。

## 审阅快照与边界

| 文件 | SHA-256 |
|---|---|
| `scripts/create_round11_daadx_execution_binding_draft.py` | `9753D2B4ED4B04F95C5A857189F3B0648DE3989FE554AEC00678A96D1DE3C66B` |
| `tests/test_round11_daadx_execution_binding_draft.py` | `D467E4670FAB27758FA375E655C6F2FE5F7A54F3B82AC099A17BF167BD1D0FC5` |
| `outputs/validity/round11_daadx_execution_binding.draft.json` | `A213043AB2298DFD7039E0ACEC56390FC55169022BEDBDAADD52F3E5649473A1` |
| bound runner | `E61B2C6CEEAE8D1A51FD614E71B2357FDED863C3BEF81816AFD8D3CC96D5AB53` |
| bound runner tests | `FCB5A57710D06CF834EF662FDE768445ED9F6358D47C0B886222F2575189ACC5` |
| bound core | `73639F1B85F84B2A27DC650E3DE1FC203A181561FA00306BCD5A5D2E76860E53` |
| frozen protocol | `01642976FAE14A43A25BDD65CA8D007E3C944D2B91771907ABE1B59553FAE880` |
| bound runner-reviewer decision | `3C2D6AFC465DE586F1597EC149E81E8F4EED1976A025D112C13B8E2150ECB29D` |

审阅 HEAD 为 `cce0f9cfa0f1437575ddc01c705e23d9fc8a1582`；三个 binding-draft 候选文件均未进入该 HEAD。

未读取、列举或解压官方 tar；未读取真实标签；未解码视频；未运行 formal preflight；未修改 protocol、core、runner 或三个候选文件。只运行纯合成测试、哈希/文件属性检查和 runner 的 read-before-data authority validator。

## 阻断项

### D1 / P0：provenance taxonomy 被错误猜测，且与 runner 合同不兼容

生成器 `scripts/create_round11_daadx_execution_binding_draft.py:67-75` 和落盘草案填入：

`driver_id, session_id, route_id, sequence_id, recording_id, trip_id, source_video_id`

runner 在 `scripts/run_round11_daadx_preflight.py:370-374` 强制接受的却是五个 evidence-class 枚举：

`AUTHORITATIVE_SOURCE_ID, AUTHORITATIVE_SESSION_ID, AUTHORITATIVE_RAW_VIDEO_ID, AUDITABLE_RAW_RECORDING_TOKEN, AUDITABLE_ACQUISITION_RIG_SESSION`

前一组更像可能存在的原始列/标识符名称，不是已冻结的 evidence-class taxonomy；它既没有数据证据，也无法通过 future `validate_protocol_contract`。这违反“未知布局不猜测”。

要求：taxonomy 是 runner 已知科学合同，应精确复制五个枚举，而不是设为猜测值；未知的 annotation paths、front regex 和 provenance member 继续保持 `null`。增加测试证明草案 taxonomy 与 runner `_PROVENANCE_REQUIREMENTS` 精确相等。

### D2 / P0：草案冒用最终 schema，且 `unresolved_fields` 没有列全晋升阻断

草案顶层声称 `ARSC_ROUND11_DAADX_EXECUTION_BINDING_V1`，但使用 `operational_contract_draft` 而非 final runner 所需的 `operational_contract`；内部 schema 是 `...OPERATIONAL_CONTRACT_DRAFT_V1`，archive bounds 与 scratch 还包含 final contract 会拒绝的 `status` 字段，future reviewer path 也是 draft-only 字段名。

当前 `unresolved_fields` 只列五个 layout null 和 ffprobe，未列：

- draft schema 到 final schema 的显式 promotion；
- `operational_contract_draft` 到 `operational_contract` 的转换；
- 删除 draft-only `status` 字段；
- 生成独立 execution reviewer decision；
- D1 taxonomy 修正与资源上限复核。

因此消费者可能误以为“只补六个 null 即可晋升”，实际仍必然被 runner 拒绝。

要求：使用独立顶层 schema `ARSC_ROUND11_DAADX_EXECUTION_BINDING_DRAFT_V1`；添加机器可读 `promotion_blockers`，完整列出所有转换和独立 review 门；明确 final binding 必须由受审 promotion helper 重新生成，禁止原地改 decision。

### D3 / P0：8 GiB 单 member 上限不能称为保守，允许全量内存读取导致 OOM

草案把 `max_member_bytes` 与 `maximum_single_file_bytes` 都设为 8 GiB，同时 label worker timeout 只有 300 秒。runner 的 `read_regular_member_bytes` 会对选定 annotation/provenance member 执行整对象 `source.read()`；worker 又对三份 annotation 执行 `Path.read_bytes()`。因此合法通过 archive bound 的输入仍可触发单个 8 GiB、甚至三份大文件的全量内存分配，进程可能在没有闭合 artifact 的情况下被 OOM 终止。

要求：在不知道真实 layout/size 前，不得把这些数值标为 conservative/final candidate。需要二选一：

1. runner/operational schema 增加独立的 selected metadata in-memory byte cap，并在读取前强制检查；或
2. annotation/provenance 改为严格有界的 streaming parser/worker。

资源草案还应给出 peak scratch 与 RAM 预算推导，保证 annotation 常驻、单视频临时文件、20 GiB reserve 和 worker timeout 相互一致。该修复不需要读取 tar，可以先冻结安全工程上限，真实 layout 仍保持 unresolved。

### D4 / P1：生成器只哈希 review 文件，不验证它确实授权当前字节

`create_draft` 只要求 review path 存在并记录 SHA；没有解析并验证 reviewer decision 的 schema/decision/claim boundary，也没有核对该 decision 内绑定的 protocol、runner、tests 和 core SHA。调用者可传入任意仓库内文件，生成外观完整的 NOT_RUN 草案。

当前落盘草案恰好绑定了正确的 `GO_CREATE_EXECUTION_BINDING_NOT_RUN` decision，且其五项核心哈希都准确；问题在于生成器不能保证这一性质。

要求：生成器 fail-closed 校验 runner-review decision 固定 schema、`decision == GO_CREATE_EXECUTION_BINDING_NOT_RUN`、formal/archive/training 均 false，以及其 protocol/runner/tests/core SHA 与当前输入逐项一致。增加 wrong decision、stale hash、wrong protocol 的负测试。

### D5 / P1：测试没有审阅实际生成草案，也没有覆盖 promotion/resource 反例

现有第二个测试构造的只是 `{schema_version, decision}` 两字段对象；runner 因缺 `operational_contract` 拒绝它，并未测试 `create_draft()` 的真实对象。虽然本审阅已直接确认落盘草案也被拒绝，但自动测试没有锁定这一事实。

要求：

- 将 `create_draft()` 的真实返回值交给 runner validator，断言在数据访问前拒绝；
- 断言 top-level draft schema 与 final schema 不同；
- 断言所有 null 和 promotion blockers 完整、一致；
- 覆盖 taxonomy、review decision、stale hash、unsafe memory cap、resolved/unresolved tool records；
- CLI 默认拒绝覆盖已存在且已审阅的 draft，或要求显式 `--force` 并采用原子写入。

## 已通过且应保留

- `decision` 精确为 `NOT_RUN_DRAFT_ONLY`；archive/formal/training authority 全为 false。
- 未填 `operational_contract`，实际 runner 返回 `ContractError: execution binding lacks operational_contract`，发生在任何 archive read 前。
- protocol、runner、runner tests、core 和 runner-review decision 的落盘 SHA 全部与当前文件一致。
- ffmpeg 绝对路径存在且 SHA 匹配；ffprobe 明确 `UNRESOLVED`，没有猜测路径。
- Python 解释器绝对路径存在且 SHA 匹配；`-I`、clean environment 与 300 秒 timeout 被显式记录。
- scratch root 是存在的普通目录，不是 link/reparse point；当前可用空间远高于 20 GiB reserve。这里只证明 host path 事实，不证明 D3 的 RAM/resource contract。
- artifact topology 与 phase policy 精确匹配已审 runner。
- annotation members、front regex、provenance member 均保持 `null`；生成器没有读取 archive。
- 使用相同输入重新调用 `create_draft()` 得到与落盘 JSON 完全相等的对象。
- `py_compile` PASS；纯合成测试 `2 passed in 0.10s`；JSON 可解析。

## 当前授权边界

允许：修改生成器/测试/草案；用纯合成输入重新生成；保持所有 archive layout 字段 unresolved；复跑不访问数据的 hash、schema 和 rejection tests。

禁止：提交当前草案作为受审 operational candidate；把 schema/decision 改成 GO_RUN；生成 execution GO reviewer decision；读取/列举 tar 以填路径；解码视频；读取标签；写 formal attempt；修改/refreeze protocol；训练或推理。

修复 D1–D5 后应重新冻结三文件 SHA 并独立复审。只有得到 `GO_COMMIT_NOT_RUN_BINDING_DRAFT` 后才适合先提交；提交仍不等于 GO_RUN。
