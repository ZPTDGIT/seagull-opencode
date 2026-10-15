---
name: seagull-tkpro-crack
description: Use when 维护/重打 TKPro采集器 破解版（Nuitka OneFile + 易速云云验证）或处理 E:/自用AI/2026_10_3_tk采集 目录。启动器注入链 + 交付包重建。
---

# TKPro采集器 破解项目（v5.0.0，已交付）

工作目录 `E:/自用AI/2026_10_3_tk采集/`：
`TKPro.zip`（原始快照 369MB，含 .i64）→ `TKPro_extracted/TKPro/`（目标+原始分析文档）→ `work/`（构建脚本+载荷+stub）→ `交付/`（成品）→ 桌面已放 `TKPro破解版_单文件.exe` + `TKPro破解版.zip`。

## 目标本质

- TKPro采集器 v5.0.0：Nuitka OneFile（内嵌 CPython 3.11 + PyQt6），143MB，SHA256 `BA87A23FFB818236240C9AD608A71BF34AD380D6EF735152C7C974C267F81625`（**原文件未改动**）
- 授权 = 易速云网络验证（纯云）：`api.easysu.cn`；心跳 600s；WMI 设备指纹；响应签名（app_secret 驻留内存）
- 采集数据服务端 `43.128.26.158:8000/9000`；签名服务器 `104.219.250.215:9595`
- 原始分析文档（别丢）：`TKPro_extracted/TKPro/.claude/CLAUDE.md` + `TKPro采集器-attempts.md` + `安全分析_交接文档.md`

## 破解链（全实测通过）

1. **双进程**：外层 bootstrap（~143MB，无 python311.dll）+ 子进程 CPython GUI（加载 python311.dll + Qt6Widgets）= 真身
2. **注入**：frida 17.18 → `PyGILState_Ensure + PyRun_SimpleString`（Python314 解释器：`C:/Users/19123/AppData/Local/Programs/Python/Python314/python.exe`）
3. **载荷**（`work/inject_payload.py`）：
   - `AuthManager`（src.utils.auth_manager）8 方法恒真 + `is_logged_in/card_key/token/user_info` 直写 + `emit login_success` 挂载
   - 心跳中和 3 件套（`_send_heartbeat`/`_should_trigger_heartbeat_failure`/`_handle_heartbeat_request_failure`）
   - 采集会话令牌门：`BloggerView/VideoView/CommentView._verify_collection_session_token` 恒真
4. 进程重启失效 → **每次从启动器进入**（自动重注入）

## 交付与重建

- 成品：`交付/TKPro破解版/`、`TKPro破解版.zip`、`TKPro破解版_单文件.exe`（桌面各一份）
- 重建三步（详见 `work/构建说明.md`）：
  1. `pyinstaller --onefile --console --name 破解启动器 --icon work/app.ico --add-data "work/inject_payload.py;." --add-data "work/dump_payload.py;." work/crack_launcher.py`
  2. `csc /target:exe /platform:x64 /win32icon:work/app.ico /r:System.IO.Compression.FileSystem.dll /r:System.IO.Compression.dll /out:work/stub.exe work/sfx.cs`
  3. `python work/make_delivery.py`
- **坑**：重建 payload 后必须改 `work/sfx.cs` 的 `BUILD` 常量，否则单文件版不重新解压
- 通用方法论+模板已固化到技能 `seagull-license-security`（`references/nuitka-runtime-crack.md` + `scripts/`）

## 测试与验收

- 状态文件：`%TEMP%\tkpro_crack_status.txt`（逐行日志 + run_id）
- 通过标准：`auth_view=False; sidebar_menu/main_splitter/content_stack=True; is_authenticated=True; content_idx=0 (BloggerView)`
- 单文件版缓存目录：`%LOCALAPPDATA%\TKProCrack\app`（数据也在那里持久化）
- 桌面实测证据：datas/2026-10-03/blogger/US.txt 641 行真实采集数据（采集链通）

## 已知边界

- 安全软件对 frida 组件误报 → 交付说明已要求加白名单
- 采集功能若遇服务端 feature gate（非客户端判定），本地全翻真也拿不到数据——用状态文件+服务端 URL 日志判断在哪一侧
- 原始 .py 源码不可得（Nuitka 编译型，无字节码）；结构级还原 + 运行时 patch 是正确路线
