---
name: pi-coding-agent
description: Use when fixing pi coding agent's seagull setup.
---

# pi coding agent — 海鸥人格维护 (Windows)

pi = `@earendil-works/pi-coding-agent`，npm 全局安装（当前 0.86.1）。

## 配置三件套 (全部在 ~/.pi/agent/)

| 文件 | 作用 |
|---|---|
| `APPEND_SYSTEM.md` | 海鸥人格（全局追加系统提示；与 pi 默认提示冲突时以它为准） |
| `settings.json` | `skills` 数组挂载 `~/AppData/Local/hermes/profiles/seagull/skills`（66 个 SKILL.md）；provider=deepseek, model=deepseek-flash, thinking=max |
| `auth.json` | deepseek 凭证（不要动） |

会话存放在 `<项目cwd>/.pi/sessions/`（settings.json 的 sessionDir 是相对路径）。

## 症状 → 修法

- **"不听指挥"/跑偏/自嗨深挖** → 全量重装（下方流程）+ 确认人格文件含「操作员指挥权（00z）」段；提醒用户：旧会话别 `pi -c` 续，开新会话（大上下文拖垮指令遵循）
- **升级/重装 pi 本体** → `npm install -g @earendil-works/pi-coding-agent@latest`
- **技能不生效** → 检查 settings.json skills 数组 + 目录里 SKILL.md 数量（`find ... -name SKILL.md | wc -l`）

## 重装流程（已验证 2026-09-21）

1. 备份：`mkdir -p ~/.pi/backups/seagull-pi-reinstall-$(date +%Y%m%d-%H%M%S)`；`APPEND_SYSTEM.md`（mv）、`settings.json`、`models-store.json` 拷入
2. `npm install -g @earendil-works/pi-coding-agent@latest`
3. 重建人格：`python scripts/rebuild-persona.py [源文件]`（默认取最新备份目录的 APPEND_SYSTEM.md；= 原人格 + 00z 指挥权铁律 + pi 运行环境适配段 → 写出到 ~/.pi/agent/APPEND_SYSTEM.md）
4. 重建 settings.json（保持 skills 数组 + provider/model 不变）
5. 验证（真跑，别猜）：
   - `pi -p --no-session "在吗"` → `海鸥在线，你要整点薯条吗？`
   - `pi -p --no-session "逆向"` → 第一行含 `逆向工程已打开`
   - 问 skills 总数 → 66；seagull- 开头的全可见

## 坑（都踩过）

- bash heredoc 内联 Python 时反斜杠会被 MSYS 吞掉 → 写 .py 文件再执行
- npm 重装的 allow-scripts 警告（esbuild 等）不影响 pi 运行（预打包 bundle）；claude-code / codex 不受连带影响（验过）
- 人格文件用 UTF-8 无 BOM、LF 换行写
- pi 0.86.x 无影响 APPEND_SYSTEM.md / settings.skills 机制的破坏性变更
