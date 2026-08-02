# Round 11 DAAD-X runner 最终结果盲审备忘录

## 裁决

**`GO_CREATE_EXECUTION_BINDING_NOT_RUN`**。

runner 在冻结候选字节上已通过 B1–B5 最终复审。现在只允许创建一个 additive、no-override、`NOT_RUN_DRAFT_ONLY` 的 execution-binding 草案，供下一轮独立审阅 operational values。该草案不得被 runner 接受为执行权限。

本裁决**不是** `GO_RUN`：不授权运行 formal preflight，不授权打开或列举官方大 tar，不授权真实视频解码、真实标签读取、attempt01 写入、训练或推理。未来必须在 runner/tests/core/binding 全部进入同一 HEAD、binding operational values 独立复核、并另行生成精确互绑的 execution reviewer decision 后，才可能另发 GO_RUN。

## 固定审阅快照

| 文件 | SHA-256 |
|---|---|
| `scripts/run_round11_daadx_preflight.py` | `E61B2C6CEEAE8D1A51FD614E71B2357FDED863C3BEF81816AFD8D3CC96D5AB53` |
| `tests/test_round11_daadx_preflight_runner.py` | `FCB5A57710D06CF834EF662FDE768445ED9F6358D47C0B886222F2575189ACC5` |
| `src/arsc_eval/daadx_preflight.py` | `73639F1B85F84B2A27DC650E3DE1FC203A181561FA00306BCD5A5D2E76860E53` |
| `outputs/validity/round11_daadx_preflight_protocol.json` | `01642976FAE14A43A25BDD65CA8D007E3C944D2B91771907ABE1B59553FAE880` |
| `outputs/validity/round11_implementation_reviewer_decision.json` | `A70426CBAC7A6163F361F4A95624C95C33AE15E1009196BD9B14F78BB7932538` |

审阅 HEAD 为 `cce0f9cfa0f1437575ddc01c705e23d9fc8a1582`。runner 与 runner tests 在该 HEAD 中仍为 untracked 候选，因此当前 `require_binding_in_head=True` 的执行校验必然拒绝，不能把本裁决误当现成运行权限。

冻结 protocol 保持 byte-identical，SHA 仍为 `01642976...FAE880`；没有改写或 refreeze。

## 独立验证

- `python -m py_compile scripts/run_round11_daadx_preflight.py src/arsc_eval/daadx_preflight.py`：PASS。
- `PYTHONPATH=src;scripts python -m pytest tests/test_round11_daadx_preflight_runner.py -q`：`47 passed in 2.55s`。
- 排除默认解释器缺少 `cv2/ultralytics` 的三个 collection 模块后，全仓其余测试：`147 passed in 9.79s`。
- 主审报告 scoped `47` / full `160` PASS；其中 full `160` 未在本机默认解释器独立复现，故只作为二级证据。

测试只使用代码、临时目录、微型合成 tar 与 canary CSV。本审阅未打开/列举官方大 tar，未读取或解码真实视频，未读取真实 DAAD-X 标签、BDD-OIA 输入或模型输出；未修改 runner、tests、core 或 frozen protocol。

## B1–B5 复审结论

### B1：代码闭包与独立 GO decision 互绑 — PASS

`validate_execution_authority` 现在绑定 protocol、runner、runner tests、`src/arsc_eval/daadx_preflight.py`、operational-contract canonical hash 与独立 reviewer-decision path/hash。可执行 reviewer decision 使用固定字段集合，并反向锁定同一 protocol/runner/tests/core/operational hash；binding、protocol、runner、tests、core、review decision 全部要求 HEAD-exact。

`NOT_RUN_DRAFT_ONLY` 明确被执行校验拒绝。core hash、review schema/decision/role 或 operational hash 的反例均有负测试。binding 不再依靠自声明 role 获得 GO。

### B2：gate-local 失败与 16 文件闭包 — PASS

G0 audit 使用独立异常边界；G0 PASS 后，下游 annotation/seal 错误归 G1，front extract/probe 错误归 G2，provenance absent/read/parse/taxonomy 错误归 G3，不再覆盖已 PASS 的 G0。

缺失 annotation 的 `KeyError` 已纳入 G1 局部失败；provenance 缺失/非法已纳入 G3。六类合成失败路径验证了 gate 状态和完整 16-artifact closure。G0–G3 全 PASS 仍只返回 phase-1 diagnostic，不发布伪 formal STOP。

### B3：duplicate provenance header — PASS

header 现在要求非空、字段唯一、只含 allowlist 且包含 `uuid`/`provenance_class`。duplicate UUID/class/evidence header 与大小写伪字段均被拒绝。

### B4：label worker schema — PASS

父进程同时验证精确字段集合、`schema_version == ARSC_ROUND11_DAADX_LABEL_SEAL_V1`、parser version、三 split source SHA、UUID count、row shape、唯一 UUID 和 split allowlist。错误 schema/parser/source SHA 负测试通过；worker 继续使用 `-I`、clean environment、timeout、解释器 hash 与 stdout/stderr capture。

### B5：strict provenance row parsing — PASS

parser 已改用 `csv.reader(..., strict=True)`，逐行要求 `len(row) == len(header)`，再以 strict `zip` 构造记录；row-level `csv.Error` 转为 `ContractError`。未闭合 quote 与超宽 row 两个此前可造成 G3 假 PASS 的反例现在均被拒绝。

## 其余安全与方法学结论

- G3 FAIL 后短路 G4–G7 并保持 INCONCLUSIVE、形成 frozen AND-rule STOP，方法学上合理；G3 PASS 时当前 runner 不发布 formal verdict。
- G0 使用双次 archive SHA、raw header checksum、严格 UTF-8/POSIX/Windows path、PAX-only metadata、type/sparse/collision 检查、流式资源上限、tarfile 二次解析及逐 regular-member SHA。
- G1 要求每个 eligible UUID 恰好一个 front，不做替代；G2 使用逐视频 extract→rehash→probe/full-decode→rehash→delete，scratch 容量与 timeout 由 future binding 冻结。
- provenance artifacts 不发布低熵 source/session token 的普通 SHA；只发布 class/status。
- G8 采用精确 16 个 regular non-symlink entries、15 项 self-excluded index、唯一 exit marker、exclusive writes、file/directory fsync、同父目录 atomic rename 和 post-publish rehash；results 在外部闭包前保持 `PENDING_EXTERNAL_CLOSURE`。
- 所有 subprocess 使用 argv list、无 shell；解释器与 ffmpeg/ffprobe 使用绝对路径及 SHA。Windows scratch work name、同卷 staging/final 与 no-overwrite 合同已建立。
- `training_authorized` 始终为 false；runner 不包含训练、checkpoint、模型推理依赖。

## binding 草案边界与下一道门

现在允许创建的 binding 草案必须：

1. `decision` 为 `NOT_RUN_DRAFT_ONLY`，不能是 `GO_RUN`；
2. 仅向 frozen protocol 添加 operational contract，不得覆盖任一 scientific/protocol 字段；
3. 填入明确 archive annotation/front/provenance layout、PAX/resource ceilings、scratch root/capacity/lifecycle、Python/ffmpeg/ffprobe absolute path+SHA、worker timeout/env policy、atomic artifact topology 与 phase policy；
4. 绑定本备忘录所列 protocol/runner/tests/core SHA，但在候选代码再次变化后必须失效；
5. 不创建 formal staging/final/log/index，不触发 archive inventory 或视频 decode。

草案生成后，独立 reviewer 必须逐字段核查真实 operational values、工具字节、磁盘容量与 HEAD blobs，并生成 runner 所要求的 `ARSC_ROUND11_DAADX_EXECUTION_REVIEWER_DECISION_V1` 精确 GO decision。只有该后续裁决才可能授权一次 result-blind preflight；本备忘录不能被引用为 GO_RUN reviewer decision。

本次 `GO_CREATE_EXECUTION_BINDING_NOT_RUN` 是工程草案授权，不是 DAAD-X G0–G8 结果，也不允许提前切换 Candidate A。
