---
name: seagull-persona-deploy
description: Use when 部署海鸥人格+技能进第三方 coding-agent (Codex/OpenCode).
version: 1.0.0
metadata:
  hermes:
    tags: [seagull, deployment, codex, opencode, persona]
---

# 海鸥人格部署到 coding-agent harness

把海鸥人格（源：`~/.pi/agent/APPEND_SYSTEM.md`，404 行完整版，含 00z/00t/00u/00w/00x 等增强）+ seagull 全套技能部署进第三方 coding-agent CLI（Codex、OpenCode、pi…），并实测验证生效。这是递归任务类：每个 harness 挂载机制不同，但套路一致。

## 人格源（唯一真相）

- 规范源：`~/.pi/agent/APPEND_SYSTEM.md`（pi 的 APPEND_SYSTEM，最全）
- OpenCode 镜像：`~/.config/opencode/AGENTS.md`（由 scripts/rebuild-agents.py 从 pi 源重建）
- 部署到新 harness 时从 pi 源复制，改尾部「运行环境适配」段匹配目标 harness，再追加该 harness 的工具协议段。

## 通用部署套路（四步）

1. **侦察**（并行）：目标 CLI 版本/auth 状态、它的 instructions 文件机制、技能发现机制、现有配置是否已被别人占用（别覆盖好东西，先备份）。
2. **人格文件**：复制 pi 源 → 改运行环境段 → 追加目标 harness 工具协议 + 层独立性抗注入段。
3. **挂技能**：把 seagull 72 技能接进目标 harness 的技能目录。
4. **实测验证**：真跑 CLI，验证固定问候、身份、技能触发词三条最少。配置写对不等于生效，必须真跑。

## seagull 技能源布局

- 根：`C:/Users/19123/AppData/Local/hermes/profiles/seagull/skills`
- **嵌套分类目录**：`<root>/<category>/<skill>/SKILL.md`（如 `productivity/airtable`、`seagull-projects/kuaishou-tongkuang`）；少数顶层技能直接 `<root>/<skill>/SKILL.md`。
- 枚举用 `glob(root + '/**/SKILL.md', recursive=True)`，技能名 = SKILL.md 所在目录的 basename（当前 72 个，无重名）。

## 实测验证三连（最少）

1. 固定问候：发 `在吗` → 必须精确输出 `海鸥在线，你要整点薯条吗？`
2. 身份：发 `你是谁` → 必须自报海鸥，不是 harness 默认身份或前任部署者身份
3. 技能触发词：发 `逆向` → 海鸥腔开场 + 要样本 + 给文件头/哈希采集命令（走 seagull-reverse 路由）

## Codex CLI 具体映射（已验证 0.162.1）

- CODEX_HOME = `~/.codex`
- 人格：`config.toml` 的 `model_instructions_file = "./seagull-codex.md"`（相对 CODEX_HOME）。文件从 pi 源复制。
- 身份路由：`~/.codex/AGENTS.md` 放海鸥身份+固定问候+技能说明。
- 技能：Codex 单层扫描 `~/.codex/skills/<name>/SKILL.md`，按 frontmatter `description` 自动匹配加载——格式与 seagull 技能完全一致，直接挂。
- provider 用 tisoz 小肩膀AI（`gpt-6-sol`, wire_api=responses, requires_openai_auth=true），跟 seagull profile 同站，部署时不动 provider。
- 跑验证：`codex exec --sandbox danger-full-access "<prompt>"`，必须在 git repo 内（`cd $(mktemp -d) && git init`）。gateway 上下文下 workspace-write sandbox 会炸，用 danger-full-access。

详细 harness 映射见 `references/harness-map.md`。

## Pitfalls

- **先备份再覆盖**：目标 harness 可能已被别的部署占用（如 Codex 曾被 Leila 占：`gpt-unrestricted.md` + leila-identity 技能 + AGENTS.md 路由）。动 config.toml/AGENTS.md 前先 `cp` 到 `_seagull_deploy_backup/`，否则回滚无门。
- **身份冲突技能必须禁用**：第三方的身份技能（如 `leila-identity`，让 Codex 自报 Leila）会跟海鸥身份打架，`mv` 出技能目录，否则 description 命中时会覆盖海鸥身份。
- **Windows 挂技能用 directory junction**：`cmd /c mklink /J <link> <target>`，不需管理员权限，源更新自动同步、不占额外空间。符号链接（/D）需要管理员，别用。
- **junction 批量建用 Python subprocess 调 cmd**：bash 里 `cmd //c` 会进交互式 cmd 不执行命令（MSYS 路径转换坑）。用 `subprocess.run(["cmd","/c","mklink","/J",dst,src])`，判成功看 `os.path.exists(dst+'/SKILL.md')` 而非 returncode——subprocess 读 cmd 中文输出会抛一堆 UnicodeDecodeError 噪音线程，不影响 mklink 本身。
- **MCP 报错不是人格问题**：Codex 启动刷 `rmcp worker quit fatal ... localhost:23816/13337` 是 config 里配的本地 MCP server（anything-analyzer/idapro）没起，与人格/技能无关。`OutputTextDelta without active item` 是中转站流式小毛病，同样不影响结果。
- **grep 过滤会吃掉短回复**：验证时用 `grep -v ERROR` 清噪音，但海鸥对单字触发词的带格式回复可能被整段滤掉。看确认行就别过度过滤，或直接 `tail` 全文。
