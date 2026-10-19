# 多模型自动审计与任务交付工具

## 目标

用一个本地 Python 命令行工具提供两个可独立运行的 V0 功能：GPT 与 DeepSeek 的循环审计，以及 GPT 给 DeepSeek 的任务分配。用户保留未解决分歧的裁决权。默认离线模拟，真实 DeepSeek 调用需要显式许可。

## 当前边界

- GPT 通过本机已登录 ChatGPT 的 Codex CLI 非交互运行；不假设 ChatGPT Plus 提供通用 OpenAI API 密钥或额度。
- DeepSeek 通过官方 API 适配器运行；无密钥时只运行 mock。
- 模型只输出文本或 JSON。生成的代码、文档属于候选结果，V0 不直接修改目标文件。
- 每次调用、审计轮次、用户决定与故障均留存版本和日志；密钥不进入日志。

详细协议见 [设计文档](docs/superpowers/specs/2026-10-19-multimodel-v0-design.md)。
