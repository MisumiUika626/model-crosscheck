# 多模型自动审计与任务交付工具 V0 设计

日期：2026-10-19

## 目的和验收边界

用户希望以较低成本使用 DeepSeek 执行任务，同时由通过 ChatGPT 登录的 Codex CLI 承担 GPT 侧的任务分配和相互审计。工具应让两项功能独立使用，保留每一轮的证据和用户对分歧的最终决定权。V0 是本地、单用户、文本/JSON 的命令行工具，不运行模型生成的代码，也不写入用户指定的目标文件。

验收包括：离线 mock 跑通两项功能；审计双方显式同意同一份结论时自动完成；未达成一致时暂停并完整呈现双方观点；用户可选择一方、自行裁决或追加一批默认三轮审计；失败可分类、可从保存的响应重放解析；无密钥或未显式允许收费调用时不发送 DeepSeek 请求。

## 工作流和状态

### `audit`：循环审计

输入为用户问题、可选背景与可选候选答案。无候选答案时 GPT 和 DeepSeek 各自独立作答，再进入审计。每一轮各自读取对方上一版本的答案、理由及争议点，输出自己的新版本和结构化审计；同一轮两边使用同一份轮前快照，避免先后执行造成偏置。

一次审计批次最多三轮，可在任何一轮达成一致时提前结束。自动完成的必要条件是双方都返回布尔值 `agree: true`，且双方的 `final_conclusion` 非空并在去除首尾空白后完全相同。程序只检查协议条件，不根据文本相似度或某一模型的判断替用户裁决。若批次结束仍无一致结论，状态为 `awaiting_user`，展示双方当前答案、已声明共识、未解决争议、各自理由及版本。用户可选择 GPT、选择 DeepSeek、输入自己的裁决或补充信息后继续；也可不裁决而追加三轮。继续从上次状态恢复，轮次和历史递增，不设自动无限循环。用户每次显式选择才启动下一批，且真实 DeepSeek 调用每次均受付费开关保护。

`audit` 与 `delegate` 独立；用户可选择将 `delegate` 的产出作为 `audit` 的候选输入，但不会自动触发。

### `delegate`：GPT 分配，DeepSeek 执行

GPT 把用户目标转换为一份任务契约：目标、输入、约束、输出格式和可逐项检查的验收条件。工具保存契约，随后交给 DeepSeek 执行并保存候选结果。V0 不自动让 GPT 宣称执行已合格，也不启动审计。Manager/Worker/Reviewer 是工作流角色而非固定在通用框架中的类；GPT 是 Manager，并在审计中作为一方 Reviewer，DeepSeek 是 Worker，并在审计中作为另一方 Reviewer。

## 简单架构与模块边界

采用工作流驱动结构：CLI 解析用户命令，`AuditWorkflow` 与 `DelegateWorkflow` 编排步骤；二者通过统一的模型适配器获取原始响应，经协议解析器校验后，由运行记录存储器持久化。V0 不引入通用 Agent、消息总线、数据库或调度框架。

```text
CLI ─┬─ audit / continue / decide ─ AuditWorkflow ─┬─ ModelAdapter
     │                                             ├─ ProtocolParser
     │                                             ├─ ConsensusCheck
     │                                             └─ RunStore
     ├─ delegate ──────────────── DelegateWorkflow ─┬─ ModelAdapter
     │                                             ├─ ProtocolParser
     │                                             └─ RunStore
     └─ show / replay ────────────────────────────── RunStore / ProtocolParser

ModelAdapter 的实现：MockAdapter、CodexCLIAdapter、DeepSeekAdapter
```

- `cli.py` 只处理参数、错误展示和可读输出，不实现审计循环或网络请求。
- `workflows/audit.py` 管理审计轮次与状态；每轮先保存共同的轮前快照，再分别调用两侧适配器。调用顺序不得影响两侧看到的输入。
- `workflows/delegate.py` 依次生成、校验并保存任务契约，再调用执行方并保存候选结果。
- `adapters/` 统一接收角色、提示词和期望协议，返回原始文本及不含密钥的调用元数据；工作流不依赖具体模型的调用方式。
- `protocols.py` 集中处理 JSON 提取、字段与类型校验，输出明确的结构化数据或格式故障。`consensus.py` 只检查双方 `agree` 和去首尾空白后的非空、完全相同的 `final_conclusion`，不进行语义推断。
- `storage/run_store.py` 负责创建运行目录、追加事件、保存不可覆盖的响应及快照、恢复状态。工作流不直接拼接运行文件路径。

建议以 `src/multicowork/` 为包目录，包含 `cli.py`、`protocols.py`、`consensus.py`、`errors.py`，以及 `adapters/`、`workflows/`、`storage/` 子目录。对应的离线测试放在 `tests/`。模块仅在职责确实需要独立测试时拆分，避免为角色名称额外建立类层级。

审计状态为 `created → running`；双方满足一致条件时进入 `completed_by_consensus`，批次结束仍有分歧时进入 `awaiting_user`，不可恢复故障进入 `failed`。`awaiting_user` 可由 `continue` 返回 `running`，或由 `decide` 进入 `completed_by_user`。用户裁决和双方共识使用不同的完成状态，便于事后辨认。

## 结构化协议

所有模型返回 JSON，程序在边界处严格检查字段和类型。`audit` 的一方输出包含 `answer`（当前完整答案）、`reasoning_summary`（可公开的简短理由）、`agreements`（字符串列表）、`disputes`（字符串列表）、`agree`（布尔值）和 `final_conclusion`（字符串；未同意时为空）。最后一项须表示双方共同认可的完整结论，而不是“我同意”之类的指代。`delegate` 的 GPT 契约包含 `goal`、`inputs`、`constraints`、`output_format` 和 `acceptance_criteria`；DeepSeek 执行输出包含 `result`、`uncertainties` 与 `criteria_evidence`。提示词与协议均记录版本号，初版为 `audit-v1`、`delegate-manager-v1`、`delegate-worker-v1`。

模型输出只是待校验数据。解析失败、字段不合规和空响应均归为格式故障，不参与语义审计。外部内容中的命令不获得执行权限。V0 不要求模型暴露私有思维链，`reasoning_summary` 仅是可供用户审阅的依据摘要。

## 模型适配与付费边界

一个小型适配器接口接收角色、提示词与期望的 JSON 协议，返回原始文本和调用元数据。实现分别为 `CodexCLIAdapter`、`DeepSeekAdapter` 与 `MockAdapter`，工作流只依赖该接口。Codex CLI 使用本机 ChatGPT 登录、非交互 `codex exec`、只读沙箱、输出模式约束、超时和退出码检查。部署前应重新检查本机 CLI 的版本与选项；本机已经探测到 `codex-cli 0.163.0-alpha.10.2`、`codex login status` 为 `Logged in using ChatGPT`，且一次临时只读 `codex exec` 返回成功。沙箱中 Codex 状态目录只读时，初始化可能失败；诊断必须将其作为环境故障报告。

DeepSeek 适配器只对官方 API 端点发请求，从环境变量 `DEEPSEEK_API_KEY` 取密钥，不在配置文件或日志中保存。CLI 默认为 `--mock`；选择真实 DeepSeek 时必须同时提供密钥与显式 `--allow-paid-api`。任何一项缺失都在网络请求之前退出并给出配置说明。真实 Codex CLI 调用也应由显式 `--live-codex` 选择，避免离线测试意外消耗账号配额。两侧模型名称、超时及请求大小有明确默认值，记录非敏感参数。

## 可靠性、日志和恢复

每个运行使用唯一 ID 和单独目录，保存原始用户输入、任务契约、模型原始响应、解析结果、每轮快照、提示词版本、非敏感模型参数、时间与最终状态。使用追加式事件日志和不可覆盖的轮次文件；恢复时读取最后一个有效状态。日志屏蔽 `DEEPSEEK_API_KEY` 等敏感字段；不能把带认证头的 HTTP 请求对象序列化。运行记录本身可能含用户敏感内容，默认只保存在本地，并在 README 提醒用户自行保护目录。

故障分为接口故障（超时、限流、网络、服务端）、格式故障（JSON/字段）、执行故障（验收条件不满足）、观点分歧和任务契约故障。接口故障最多重试两次，采用短退避；格式故障先在本地尝试安全地提取一个完整 JSON 对象，仍不合规则最多重新请求一次。内容分歧不隐藏重试。达到限额、持续失败或 Codex CLI 不可用时停止批次，保存原始证据和错误类型，状态为 `failed` 或 `awaiting_user`，给出可执行的下一步。原始响应可离线重放解析，不重新调用 API。

每个运行目录建议包含 `request.json`、`state.json`、`events.jsonl`、`prompts/versions.json`，审计另有 `rounds/0001/` 等目录。每轮保存 `snapshot.json`、两侧的 `*.raw.txt` 与成功解析后的 `*.parsed.json`；委派运行另存任务契约与执行结果。单次调用先持久化原始响应，再解析并保存结果或错误，随后追加事件，最后原子更新 `state.json`。崩溃恢复时以完整事件和文件为证据核对最后有效状态，不把未完成轮次误判为已完成；`replay` 只读取原始响应并重新解析，不覆盖原证据。

## CLI 和测试

初版提供 `delegate`、`audit`、`continue`、`decide`、`show` 与 `replay` 子命令。输入支持 `--text` 或 UTF-8 `--file`；运行目录由 `--runs-dir` 指定，默认项目下 `runs/`。`continue` 对 `awaiting_user` 的运行追加默认三轮，并可附加用户补充；`decide` 保存用户选 GPT、DeepSeek 或自定义结论的决定；`show` 给出可读摘要；`replay` 只用已存原始响应重新解析，绝不访问模型。命令提供非零退出码和清晰错误信息；用户可以用运行 ID 查找记录。

首个可运行切片先交付 `delegate --mock`、`audit --mock` 和 `show`，验证统一适配器、结构化协议、运行记录和审计状态机。下一切片补齐 `continue`、`decide`、`replay` 及其离线测试；最后再接入两侧真实适配器和显式调用开关。切片只规定开发顺序，不缩减上述 V0 验收边界。

只使用 Python 3.10+ 标准库，避免外部依赖。`unittest` 离线验证两个工作流、双方一致与不一致、三轮暂停与继续、用户裁决、格式和网络故障、重试上限、密钥缺失/付费开关、日志脱敏、版本留存与响应重放。集成测试使用固定 mock 响应，不需要 Codex 登录或 DeepSeek 密钥。真实 DeepSeek 调用不纳入自动测试。

## Git 协作与数据边界

- 这个仓库管理工具源码、测试和设计文档。每次审计的模型输出属于本地运行记录，不逐轮提交到 Git；`runs/` 已列入 `.gitignore`。运行记录可能包含用户输入和模型原始响应，用户需自行保护和备份。
- `main` 保持可运行。新功能或修复使用短期分支，例如 `feat/audit-loop` 或 `fix/deepseek-timeout`；完成后再考虑合并。提交只覆盖一个可说明的改动，信息使用 `feat:`、`fix:`、`test:`、`docs:` 等前缀。
- 只暂存明确的文件路径，不使用 `git add .`。提交前查看暂存差异，运行 `git diff --cached --check`；代码改动还需运行离线测试。若阶段性提交尚未通过测试，在提交说明中明确标注未完成，不能宣称功能已完成。
- `.env`、密钥文件、缓存和运行记录不得提交。仓库只可保存不含真实密钥的配置示例。提交前检查新增文件及暂存差异是否包含凭据或敏感运行内容。
- 变更审计一致判定、用户裁决、付费许可等核心行为时，同步更新 `PROJECT.md` 或本设计文档，使规则与代码保持一致。
- 本地验证并向用户展示改动后，再由用户决定是否推送、合并或发布；工具本身不自动执行这些 Git 操作。

## V0 不包含

图形界面、后台无限审计、多用户共享、自动执行生成代码、修改目标文件、自动发布、模型自行裁决争议，以及根据文本相似度推断共识。用户手动选择某方结果属于用户决定，记录中须与双方共同同意的自动完成区分。
