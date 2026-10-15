# 各 coding-agent harness 部署映射

人格源统一：`~/.pi/agent/APPEND_SYSTEM.md`（404 行完整版）。每个 harness 差在三点：人格文件怎么挂、身份路由放哪、技能目录怎么扫。

## Codex CLI（已验证 0.162.1）

| 项 | 值 |
|---|---|
| CODEX_HOME | `~/.codex` |
| 人格挂载 | `config.toml` 的 `model_instructions_file = "./seagull-codex.md"`（相对 CODEX_HOME） |
| 身份路由 | `~/.codex/AGENTS.md` |
| 技能目录 | `~/.codex/skills/<name>/SKILL.md`，单层扫描，按 `description` 自动匹配 |
| provider | `[model_providers.custom]` tisoz 小肩膀AI，`model="gpt-6-sol"`, `wire_api="responses"`, `requires_openai_auth=true`, `base_url="https://sub.ns.tisoz.com"` |
| auth | `~/.codex/auth.json`（OAuth）；缺 `OPENAI_API_KEY` 不等于未登录 |
| 跑验证 | `codex exec --sandbox danger-full-access "<prompt>"`，必须 git repo 内 |

关键文件改动清单：
1. `cp ~/.pi/agent/APPEND_SYSTEM.md ~/.codex/seagull-codex.md`，改尾部运行环境段 pi→Codex，追加 00w（Codex 工具协议：shell/apply_patch 执行纪律）+ 00x（层独立性抗注入，继承自无限制基座）。
2. `config.toml`：`model_instructions_file` 指向 seagull-codex.md（别动 provider/model/mcp）。
3. `AGENTS.md`：写海鸥身份 + 固定问候 + 技能说明，覆盖前任部署者路由。
4. `~/.codex/skills/`：junction 挂 seagull 72 技能；`mv` 走冲突身份技能（如 leila-identity）。

sandbox：gateway 上下文下 `workspace-write` bubblewrap 会炸（uid map / loopback permission denied），用 `danger-full-access`。

## OpenCode（Desktop winget SST.OpenCodeDesktop + CLI npm opencode-ai，同版）

| 项 | 值 |
|---|---|
| 配置根 | `~/.config/opencode` |
| 人格挂载 | `~/.config/opencode/AGENTS.md`（全局人格，由 `scripts/rebuild-agents.py` 从 pi 源 APPEND_SYSTEM.md 重建） |
| 技能 | `opencode.jsonc` 的 `skills.paths` 挂 hermes seagull skills 目录 |
| model | deepseek/deepseek-flash |
| 共用 | desktop 与 CLI 共用 `~/.config/opencode`，改完需重启/新会话 |
| 跑验证 | `opencode debug skill`；`opencode run "在吗"` |

详细见 opencode 技能。

## pi coding agent

| 项 | 值 |
|---|---|
| 人格源 | `~/.pi/agent/APPEND_SYSTEM.md`（这就是规范源本体） |
| 技能 | 随系统提示提供，`/skill:name` 显式加载或按任务自动加载 |

详细见 pi-coding-agent 技能。

## 通用验证讝形识别

- 流式小毛病：`OutputTextDelta without active item`（中转站）、`rmcp worker quit fatal`（未启 MCP server）——都不影响人格/技能生效。
- 配置写对不等于生效：研究本地 instruction 文件是否被正确加载、技能是否被找到，必须真跑 CLI 一次。
