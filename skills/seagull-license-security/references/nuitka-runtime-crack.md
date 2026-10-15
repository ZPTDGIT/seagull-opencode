# Nuitka OneFile 运行时破解 + 一键打包交付 实战链路

> 战例：TKPro采集器 v5.0.0（Nuitka OneFile + 内嵌 CPython 3.11 + PyQt6 + 易速云云验证）
> 2026-10-03 全链实测通过。所有结论均有活体验证，非推测。
> 通用性：任何「Nuitka/standalone 内嵌 CPython 的桌面 GUI + 云验证/卡密」目标均可套用。

---

## 0. 适用判定（triage）

- diec / 查壳 = `Nuitka[OneFile]` 或 `Nuitka[Standalone]`，单 exe 100MB+，内嵌 CPython。
- 明文字符串裸扫为空 / 只有巧合碎片 → Nuitka 常量压进 RCDATA blob，属正常，别当失败。
- 目标可能带第三方网络验证成品（如易速云 EasysuCloudHelper / easy_sdk）：纯云验证 + 心跳保活。
- **无字节码可反编译**：运行时实测 `func.__code__.co_code` 是空壳，`co_consts=(None,'Compiled function bytecode used')`。放弃 pycdc/decompyle 路线。
- 新版 Nuitka standalone 的主程序会编译成 `run.dll`（200MB+ 原生码），业务逻辑全在里面；onefile 解压目录里**不会有任何 .py/.pyc**（只有三方库 .pyd + 资源文件）。

## 1. 双进程结构（头号大坑）

Nuitka OneFile 运行时 = **父子双进程**：

| 进程 | 特征 | 说明 |
|---|---|---|
| 外层 bootstrap | exe 同体积（如 143MB），仅 34 模块左右，**无 python311.dll** | 只负责解压到 `%TEMP%\onefile_<外层PID>_<rand>\` 再拉起子进程 |
| 子进程 CPython GUI | 内存更大（300MB+），加载 `python311.dll` + `Qt6Widgets` | **真身**，所有 Python 对象都在它里面 |

**认进程判据（铁律）**：
- 必须用模块判据：加载了 `python3XX.dll` + `Qt*Widgets` 的那个才是 GUI 真身。
- **绝不能靠体积认**——volume 标签会认到外层壳，注入必报 `unable to find module python311.dll`。
- temp 目录名 `onefile_<外层PID>_...` 可反查父子关系。
- OneFile 是解压运行，**改目标目录文件没用**（子进程从 temp 目录加载）；别在静态 patch 上浪费时间（repack 成本极高，运行时不香吗）。

## 2. 注入通道（frida 进内 CPython）

frida attach 子进程 → JS 侧拿 python 模块导出 → 在进程内跑任意 Python：

```js
rpc.exports = {
    runpy: function (code) {
        var mod = Process.getModuleByName('python311.dll'); // 版本自适应见 scripts/
        var ensure = new NativeFunction(mod.getExportByName('PyGILState_Ensure'), 'pointer', []);
        var release = new NativeFunction(mod.getExportByName('PyGILState_Release'), 'void', ['pointer']);
        var run = new NativeFunction(mod.getExportByName('PyRun_SimpleString'), 'int', ['pointer']);
        var gil = ensure();
        var rc = run(Memory.allocUtf8String(code));
        release(gil);
        return rc;
    }
};
```

要点：
- `rc=0` = 执行成功。整段载荷（KB 级）走 `allocUtf8String` 没问题。
- **注入是纯 Python 对象级 patch（setattr 换方法/改字段/发信号），frida 断开后依然生效**——它只负责把代码送进去。
- 但 patch 存在于进程内存：**进程重启即失效** → 交付必须做成"启动即自动注入"（启动器），这也是"客户端判定不可信"的实证。
- 载荷在启动线程干长活（等对象/轮询），不要阻塞注入口。

## 3. 只读侦察（先 dump 再动手）

`scripts/dump_payload_example.py`：
- `gc.get_objects()` 遍历，`type(o).__name__` 匹配找活对象（License/Auth 管理器、MainWindow、业务视图类）。不依赖 import，天然适配 Nuitka 编译类。
- dump `__dict__`（只读字段）+ `dir()` 方法面 + 控件 visible 状态 + signals 类型。
- 云验证体系：再 dump SDK 私有字段——**签名密钥等常明文驻留内存**（战例中 app_secret 直接可读，加固报告要点）。
- 把授权画成**门清单**：登录门 → UI挂载门 → 心跳二次验证门 → 功能会话令牌门……多道串联，逐道定位逐道翻。

## 4. 全链恒真载荷设计（scripts/inject_payload_example.py）

- **实例级 + 类级双 patch**：`setattr(实例, ...)` 覆盖现有对象；`setattr(type(obj), ...)` 覆盖新建实例/类级引用。全部 try 包住。
- 布尔门恒真化：`_validate_card_expiry→True`、`_call_login_api→True`、`auto_login→True`、`should_show_login_dialog→False`、`has_saved_card_key→True`。
- 登录态字段直写：`is_logged_in=True` + token + user_info。
  - user_info 用 **dict 子类 + `__missing__` 兜底** + 常见过期字段预填（expire_time/expired_at/end_time…），防 UI 取值 KeyError。
- **UI 挂载要点**：等 MainWindow 对象出现后，**emit `login_success(user_info)` 信号**——Qt 队列连接会自动切到主线程执行槽，跨线程安全。**不要**在注入线程直接调 `on_auth_success` 之类 GUI 槽（未定义行为）。
- 心跳中和：`_send_heartbeat→恒成功(不碰网)`、`_should_trigger_heartbeat_failure→False`、`_handle_heartbeat_request_failure→no-op`。
- 功能门（如采集会话令牌）：扫视图类 `_verify_*` 方法恒真；**pass1 立即 + pass2 延迟补扫**（视图类可能登录后才创建），打标记防重复。
- 全程落 `%TEMP%\tkpro_crack_status.txt` 状态文件（带 run_id），外部可轮询验收。

## 5. 交付形态 A：一键启动器（核心）

`scripts/crack_launcher.py`（PyInstaller 打包，frida 进包）：
1. 找目标 exe（自己同目录 → cwd）
2. 已有实例（10s 快速轮询）→ 直接注入；没有 → 启动目标
3. Toolhelp32 枚举子进程（**必须设 ctypes restype/argtypes，x64 下 HANDLE 不设会被截断**）
4. 对子进程探测注入 → `rc` + 状态文件等待 → 完成即 detach（patch 已驻留）
5. 控制台显示进度，成功后倒计时自动关（目标程序不受影响）

**坑（实测踩过）**：
- 子进程刚 spawn 时模块没加载完：探测一次失败**必须退避重试**（2.5s/次），不能一次不中就拉黑 PID——否则 150s 超时误报"未找到子进程"。
- 状态文件 IPC：launcher 先删旧文件；载荷每行带 `[run_id]` 防串台。
- 启动器**不要**命名成与目标 exe 同名（find_app 自匹配会死循环）。
- 已有实例检查别设太长（10s 足够）；没有实例时纯等待会拖慢正常启动。

## 6. 交付形态 B：单文件自解压 SFX

需求：一个 exe = 目标 + 启动器 + 数据，双击即用。

- **PyInstaller onefile 不能尾部追加数据**：bootloader 的 CArchive cookie 必须在文件最尾部，追加即坏。别试。
- 方案：**C# stub（系统自带 csc.exe，.NET4）+ 尾部附加 payload**
  ```
  [stub.exe][marker(18B)][payload.zip][int64 zip_len][magic TKPROEND]
  ```
  - stub 读自身尾部 → 校验 magic/len → 定位 zip → 解压到 `%LOCALAPPDATA%\<App>\app`（stamp 文件防重复解压；重建后改 BUILD 常量强制重解）
  - 然后 shell 启动解压目录里的「破解启动器.exe」（用 UseShellExecute，stub 立即退出）
  - 数据（db/账号态）落在解压目录，天然持久化
- csc 编译：`csc /target:exe /platform:x64 /win32icon:app.ico /r:System.IO.Compression.FileSystem.dll sfx.cs`
- **编码坑**：csc 源码中文用 `\uXXXX` 转义（如 `\u7834\u89e3`），彻底绕开源文件编码。
- .NET `ZipFile.ExtractToDirectory` 处理 UTF-8 中文文件名正常（实测）。
- 组装/校验脚本：`scripts/assemble_delivery.py`。

## 7. 测试协议（每形态都跑）

| 用例 | 步骤 | 通过标准 |
|---|---|---|
| 已运行实例注入 | 目标已开着 → 跑启动器 | 状态文件 DONE + UI 挂载回报 |
| 全新启动注入 | 杀全部进程 → 跑启动器 | 子进程识别 + 注入 + 挂载 |
| 单文件首跑 | 删 `%LOCALAPPDATA%` 缓存目录 → 跑单文件 | 解压 + 启动 + 注入 全通 |
| 重启复跑 | 关闭目标 → 再跑一次 | 自动重注入（不需要手动清理） |

验收证据固定看：状态文件逐行日志、`auth_view=False / sidebar=True / content_idx / is_authenticated=True` 类 UI 可见性回报、进程列表。

## 8. 红线

- **原 exe 一字节不改**（保留 SHA256 可验），破解全在注入层 → 可逆、可解释、交付干净。
- 交付说明必须写：杀软对 frida 组件高发误报 → 加白名单；必须从启动器进入。
- 若目标是云验证 + 服务端功能门（数据必须服务端下发），客户端全翻真也可能拿不到数据 → 提前向用户说明边界，用状态日志验证是"客户端判定"还是"服务端 gate"。
