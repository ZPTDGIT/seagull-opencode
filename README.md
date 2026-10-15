# 海鸥 (Seagull) · opencode 一键部署

海鸥人格 + 全套技能（76 个），一键部署到任意 Windows 电脑的 opencode。

## 一键部署

打开 PowerShell（Win + X → 终端 / PowerShell），粘贴执行：

```powershell
irm https://raw.githubusercontent.com/ZPTDGIT/seagull-opencode/main/install.ps1 | iex
```

国内网络如果 raw.githubusercontent.com 连不上，用镜像：

```powershell
irm https://gh-proxy.com/https://raw.githubusercontent.com/ZPTDGIT/seagull-opencode/main/install.ps1 | iex
```

下载源在脚本内自带三级自动回退（GitHub → gh-proxy → ghfast），通常直接成功。
装完**重启 opencode**，即可用「在吗」验证：应回复 `海鸥在线，你要整点薯条吗？`

## 装了什么

| 内容 | 部署位置 |
|------|----------|
| 海鸥人格（AGENTS.md，00z~00u 全部行为协议） | `~/.config/opencode/AGENTS.md` |
| 技能包 76 个（反逆向/渗透/游戏辅助/卡密/license/exploit/web协议恢复/达尔文等） | `~/.config/opencode/skills/<技能名>/` |

- 与现有文件冲突时自动备份到 `~/.config/opencode/_seagull_backup/<时间戳>/`，不会直接覆盖丢失
- 不修改 `opencode.json(c)`，不动你的模型/API 配置

## 技能清单（部分）

- **seagull 主线**：seagull-reverse / seagull-pentest / seagull-game-hack / seagull-license-security / seagull-exploit / web-protocol-recovery / darwin-skill
- **实战项目包**：seagull-projects/*（AutoJS 云镜解密、EasyClick 逆向、快手同框、TKPro、AI演绎精灵等）
- **通用工具**：github / docx / xlsx / pdf / notion / obsidian / maps / arxiv 等

## 其他安装方式

手动下载 zip 包后执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -LocalZip .\seagull-opencode-main.zip
```

直接使用本机目录（不走网络）：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -SourceDir .\
```

## 更新

重跑一键命令即可（旧的冲突文件会再次备份）。

## 卸载

删除 `~/.config/opencode/skills/` 下对应技能目录和 `AGENTS.md`，或从 `_seagull_backup/` 恢复你原来的文件。

## 验证

1. 新会话输入 `在吗` → 固定回复 `海鸥在线，你要整点薯条吗？`
2. 输入 `你是谁` → 自报海鸥
3. 输入 `逆向` → 触发 seagull-reverse 路由
