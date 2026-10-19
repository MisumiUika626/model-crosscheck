# Model Crosscheck

一个面向 GPT 与 DeepSeek 的本地命令行协作工具，支持任务委派、循环交叉审计、证据留存和人工裁决。

> Local CLI for GPT-DeepSeek task delegation and evidence-preserving cross-audits, with human arbitration and offline mocks.

## 当前目标

V0 提供两个可以独立运行的工作流：

- `delegate`：由 GPT 整理任务契约，再交给 DeepSeek 生成候选结果。
- `audit`：GPT 与 DeepSeek 基于同一轮快照相互审计；无法达成一致时暂停并交给用户裁决。

工具默认使用离线 mock，不会自动执行模型生成的代码，也不会直接修改目标文件。真实 DeepSeek 请求需要 API 密钥和显式付费许可。

## 当前状态

项目处于 V0 设计阶段，尚未提供可安装版本。目标、边界和验收条件见 [PROJECT.md](PROJECT.md)，详细协议见 [V0 设计文档](docs/superpowers/specs/2026-10-19-multimodel-v0-design.md)。

## 计划中的技术边界

- Python 3.10+，优先使用标准库。
- Codex CLI 作为 GPT 侧适配器，DeepSeek 官方 API 作为另一侧适配器。
- 所有模型输出按结构化协议校验并保留版本记录。
- 本地运行记录默认写入 `runs/`，该目录不提交到 Git。

## License

[MIT](LICENSE)
