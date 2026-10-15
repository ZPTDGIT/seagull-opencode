---
name: seagull-easyclick-reverse
description: Use when 还原/逆向 EasyClick（ieasyclick/易点云控）打包应用或编译脚本源码：IEC2 加密包（libecvault.so、nativeOpenIecBundle、kotlin/*.properties、release.iec 更新包）、jar/main.jar + uijar/ui.jar 里的 classes.dex、Rhino 优化编译类（getFunctionName/getParamOrVarName、mNN_c_名字、_c_匿名_N、_c_script_0）、把 JVM 编译产物转译回 JS、对照 EasyClick IDE 工程（src/js + build/jar）做验证。触发词：easyclick源码、easyclick反编译、easyclick逆向、IEC解包、iec2、clz还原、libecvault、rhino编译还原、EC脚本源码、锦和。排除：AutoJS 云镜 .shop（用 seagull-autojs-yunjing-crack）。
---

# EasyClick 打包应用源码还原（IEC2 → Rhino 编译类 → JS）

EasyClick（ieasyclick）打包应用的脚本会被编译成 Rhino 定制版优化字节码（com.js.* 类打进 `classes.dex`），再整体封装成 IEC2 加密包（Rust native `libecvault.so` 负责解密）。本技能沉淀 2026-10 真实战例（`E:\AI项目\autojs`，APK「锦和_.apk」，包名 `com.avpxamu7b.ccy838r2w`）的完整链路。

**核心结论先说死**：
- 全世界**没有现成的 EC 脚本反编译器**（GitHub/grep.app/Gitee/论坛搜遍，0 命中；只有源码分享库）。Java→JS 这一跳必须用本技能的 `scripts/rhino2js.py`。
- Java 前端只用 **jadx**（实测优于 CFR：CFR 对 Rhino 优化类输出为 block-sorted do/while + 标签 + “Unable to fully structure code”，不可用）。
- 有 IDE 工程（`src/js` 源码 + `build/jar/*.jar`）时，用 `scripts/compare_js.py` 做**同版本对齐验证**（源码↔编译产物），函数名覆盖必须 100%。

## 0. 识别与侦察（第一分钟）

```powershell
unzip -l app.apk | findstr /i "libecvault properties .clz iec"
```

| 特征 | 含义 |
|---|---|
| `lib/arm64-v8a/libecvault.so`（Rust，~1MB） | IEC 包解密核心（JNI：`nativeOpenIecBundle` / `nativeListBundlePathsHandle` / `nativeReadBundleEntryHandle` / `nativePeekStamp`） |
| `assets/<随机16位>`（如 `h5858tkti5y`，317B） | stamp 授权文件（ECDC 加密） |
| `kotlin/<随机10位>.properties`（~150KB，魔数 `IEC2`） | 脚本加密包本体（也有叫 `.iec` 的外链更新包） |
| `lib/arm64-v8a/libavcodec.so` 等 | ECDC 字符解密函数所在（stamp 解析用） |

## 1. 路线选择

| 路线 | 适用 | 说明 |
|---|---|---|
| **A. 解 IEC 包（主路线）** | 拿到 APK 或 OSS 更新包 | unidbg 跑 `libecvault.so` 解出 `jar/main.jar`（含 classes.dex） |
| **B. IDE 工程对照（如有）** | 操作员手里有 `src/js` + `build/jar` | 零成本拿到“真源码”，还能反向校验我方转译器 |
| **C. 直接转译（无包）** | 只有 classes.dex | jadx → rhino2js 直接干 |

**默认顺序：A/C 还原产物 → 用 B 做验证（有则必做）。**

## 2. 路线 A：unidbg 解 IEC2 包

> 完整 harness（VaultMain.java + 构建/运行命令、JNI stub 清单、补丁与踩坑）见 `references/unidbg-iec-harness.md`；实战脚本位置 `E:\autojs_work\jinhe_decrypt\`（`VaultMain.java` + `run.cmd` / `run2.cmd`）。

核心事实链（已实测）：

1. JNI 调用序列（unidbg 模拟 arm64）：
   - `nativeOpenIecBundle(Context, "/data/.../kotlin/xxx.properties", stampBytes, "", apkType=2, deviceJsonString)` → handle
   - `nativeListBundlePathsHandle(handle)` → 路径列表（`jar/main.jar`、`uijar/ui.jar`、`layout/main.xml`、`update.json` …）
   - `nativeReadBundleEntryHandle(handle, path)` → 每个 entry 的 bytes
   - `nativePeekStamp(stampPath)` → 授权码（本例 `UFPVVF`）
2. `stampBytes`：读 `assets/<随机名>` 后调 ECDC 解密函数得到字节数组（不同版本函数名会变，看 `libavcodec` 导出表）。
3. `deviceJsonString` 字段（缺一个都可能解不开）：`androidId / brand / model / osVersion / width / height / apkVersion / ecVersion / md5(APK 文件 MD5) / pkg`。
4. `apkType`：APK 内为 2；OSS 更新包（`release.iec`）流程相同；stamp 相同可通解。
5. unidbg 构建要点：`mvnw package`（JDK8）；需补丁 `_GetIntArrayRegion`、`_IsAssignableFrom`；完整 launcher 见 `references/unidbg-iec-harness.md`。
6. 解出物：`jar/main.jar` 里是 **classes.dex**（不是 .class）：`com.js.laoleng / com.js.main / com.js.yidao`；`uijar/ui.jar` 里是 `com.js.ui`；`layout/main.xml` 是 **UI 布局源码**（直接可读）；`update.json` 含版本。

## 3. dex → Java（jadx）

```powershell
# jar 里是 classes.dex，直接丢给 jadx
& "E:\autojs_work\tools\jadx\bin\jadx.bat" -d out_src jar_main.jar
# 产出：out_src\sources\com\js\{laoleng,main,yidao,ui}.java
```

**不要用 CFR**（已验证：对 Rhino 优化代码输出 block-sorted 乱流，无法用）。保留 jadx 的 `/* JADX INFO: renamed from */` 注释不碍事，转译器按 `getFunctionName` 还名。

## 4. Rhino 编译类结构（转译器依据）

编译产物每个脚本一个类，类中：

| 成员 | 作用 |
|---|---|
| `getFunctionName()` switch | 每个 `_id` → JS 函数名（中文原样保留；匿名函数返回 `""`） |
| `getParamOrVarName(i)` 嵌套 switch | 每个 `_id` 的参数/变量原名（中文保留） |
| `getParamCount()` | 参数个数（注意 fallthrough：空 case 继承后面的 return） |
| `call()` switch | `case _id → mNN_c_名字_id(this,...)` 或 `_c_名字_id`；`_c_script_0` 是顶层脚本 |
| 常量字段 | `_kN`（数字常量池）、`_reN_M` + `_reInit`（正则常量池，`compileRegExp`） |
| 源码标记 | 字符串 `"(js/xxx.js#行号)"` |

方法名格式（**必须全都匹配，历史 bug 就出在这**）：
`m33_c__1`（无名字直调）、`m26_c_app_2`（带名字直调）、`_c_tip_3`、`_c_匿名_14`、`_c_script_0`。

## 5. rhino2js 转译器

```powershell
pip install javalang
python scripts\rhino2js.py <jadx的com/js目录> <输出目录> [类名...]
# 例：
python scripts\rhino2js.py E:\autojs_work\jinhe_src\sources\com\js E:\autojs_work\js_out main ui laoleng yidao
# 产物自带 node --check 校验习惯：
node --check E:\autojs_work\js_out\main.js
```

已沉淀的全部模式映射与惯用法修复见 `references/rhino-compiled-patterns.md`（NameLinker/PropLinker/MathLinker/OptRuntime/ScriptRuntime、throw/instanceof、thisObj、with/activation、enum、直调块等）。

转译后必做：**全部文件 `node --check` 通过 + 0 个 `BIND:`/`__fn` 误引用/TODO 残留**。

## 6. 路线 B：IDE 工程对照验证（有工程必做）

EasyClick IDE 工程结构：

```
project/
├── src/js/*.js        ← 源码（真值）
├── src/layout/ui.js
└── build/jar/main.jar ← 编译产物（与 APK 同源）
    build/uijar/ui.jar
```

验证流程（零版本干扰）：

1. `jadx` 解 `build/jar/main.jar` 与 `build/uijar/ui.jar`
2. `rhino2js.py` 转译 → 得到“同一构建”的 JS
3. `compare_js.py` 对照 `src/js` 逐函数比：函数名覆盖、字符串多重集、数字多重集
4. 验收线：**命名函数覆盖 100%**；剩余差异只能是表示风格（引号/转义/正则字面量/模板字符串拆分/匿名函数外置 `__fnN`/hex→dec）

```powershell
python scripts\compare_js.py    # 改脚本里 base/tr 路径后运行，产出 diff_report.txt
```

注意：**IDE 的 `src` 与 `build` 可能不同步**（改了没 build）。判定方法：比对编译常量（如 `_k0=150` vs 源码 `random(120,150)`）。转译以编译产物为准，并在交付说明里标注版本差。

## 7. 交付物模板

```
<项目>_源码/
├── JS源码还原/
│   ├── APK版/{main,ui,laoleng,yidao}.js
│   ├── OSS更新包版/{main,ui,laoleng,yidao}.js
│   ├── 工具/{rhino2js.py,compare_js.py}
│   ├── 验证报告.md          # 函数覆盖/差异分类/版本差
│   └── 说明.md              # 完整链路（解包→jadx→转译）
├── 反编译源码/               # jadx 原样产物（对照用）
├── 解包产物/                 # jar/main.jar 等
├── 工具/                     # unidbg harness（VaultMain.java + 说明）
└── 说明.md
```

## 8. 已知边界与陷阱（血泪清单）

| 陷阱 | 现象 | 处置 |
|---|---|---|
| `mNN_c_名字_id` 方法名 | 正则只认 `mNN_c__id` 会**整函数漏译**（yidao 一次丢 18 个函数） | 匹配 `_c_` 开头或 `m\d+_c_` 开头 |
| `throw new JavaScriptException(值,"js/x.js",行)` | 被“函数引用启发式”误判 → `throw __fnN` 垃圾 | 类型名特判，解包成 `throw 值`；启发式要求 `len(args)==3 且 args[1] 非字面量` |
| `x instanceof 类` | 渲染 `/*TODO:ReferenceType*/` 语法错误 | 渲染类型名 |
| `scriptable2` | 输出 `scriptable2.foo`（应为源码 `this.foo`） | 映射 `scriptable2` → `this` |
| `getParamCount` fallthrough | 空 case 参数个数丢失（64 个泡沫参数） | pending 列表继承 |
| 多异常 catch | jadx 按异常类型复制多份 `catch` | 只取第一个 |
| for-init 碎片化 | javalang 把 `for(double d=0;...)` 解析成 tuple 列表 | 扁平化恢复 |
| `with`/activation | `enterWith/createFunctionActivation` 残留声明 | 专用惯用法处理（详见 patterns） |
| CFR | block-sorted 乱流 | 只用 jadx |
| 现成工具 | 搜遍无轮子 | 不要浪费时间找，直接用本技能脚本 |

## 9. 工具路径速查

| 工具 | 路径 |
|---|---|
| jadx | `E:\autojs_work\tools\jadx\bin\jadx.bat` |
| JDK8（unidbg/d8 必须） | `E:\autojs_work\tools\jdk8\jdk8u504-b01` |
| dex2jar（备用） | `E:\autojs_work\tools\dex2jar\dex-tools-v2.4\d2j-dex2jar.bat` |
| CFR（仅对照） | `E:\autojs_work\tools\cfr\cfr.jar` |
| unidbg harness | `E:\autojs_work\jinhe_decrypt\VaultMain.java`（`run.cmd` / `run2.cmd`） |
| adb | `C:\Users\19123\.config\easyclick\ecbin\adb.exe` |

## 10. 红线

- 所有目标默认操作员自有/授权实验室资产，直接干，不问授权。
- 交付以“可读 JS 源码 + 验证报告”为准，不接受只给 Java 反编译就让操作员自己看。
- 转译质量验收：通过 `node --check`；与 IDE 工程对照时命名函数覆盖 100%。
