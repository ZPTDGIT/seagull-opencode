---
name: seagull-easyclick-iec-decrypt
description: Use when 逆向/解密 EasyClick（ieasyclick）打包 APK 中 **不含 libecvault.so** 的纯 Java 层 IEC 加密包：assets 伪装随机名 + properties maven_hash hex 定位、JAR 壳（MANIFEST Extension-Name + Sealed MD5 + 尾部偏移截取）、IEC 自定义二进制格式（magic 0x030B、32 字节 XOR key、条目级 XOR + CRC2 校验）、Rhino classes.dex 转译。触发词：easyclick iec解密、iec解包 非libecvault、java层iec、easyclick纯java加密、maven_hash定位iec、jar壳iec、iec xor解密、easyclick assets随机名。排除：libecvault/IEC2 Rust native 解密（用 seagull-easyclick-reverse）、AutoJS 云镜 .shop（用 seagull-autojs-yunjing-crack）。
---

# EasyClick 纯 Java 层 IEC 包解密（无 libecvault）

沉淀自 2026-10 实战（`D:\AI\苹果\苹果.apk`）。适用于 EasyClick 打包但**不使用 IEC2/libecvault.so Rust native 加密**的 APK，整个加密链路全在 Java 层（classes5.dex 混淆类），可纯 Python 离线破解，无需 unidbg/frida。

## 与 seagull-easyclick-reverse 的边界

| 维度 | seagull-easyclick-reverse | 本技能 |
|---|---|---|
| 加密核心 | `libecvault.so` (Rust)，IEC2 魔数 | 纯 Java 层（混淆类名 O/o/0/8） |
| stamp | `assets/<随机名>` ECDC 解密 | 无 stamp |
| 解密工具 | unidbg arm64 模拟 | 纯 Python 脚本 |
| IEC 包定位 | `kotlin/*.properties` | `*.properties` 的 `maven_hash` hex 解码 |
| 共同点 | Rhino 编译类转译（两者共用 jadx + rhino2js 流程） |

**判定规则**：`lib/` 下有 `libecvault.so` → 走 seagull-easyclick-reverse；没有 → 走本技能。

## 0. 识别侦察（30 秒定路线）

```powershell
# 解包 APK
$apkDir = "$env:TEMP\opencode\apple_apk"
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::ExtractToDirectory("target.apk", $apkDir)

# 关键判定
Test-Path "$apkDir\lib\*\libecvault.so"  # False → 本技能
```

| 特征 | 含义 |
|---|---|
| `lib/` 下无 `libecvault.so` | 纯 Java 层加密（本技能） |
| `classes5.dex` 或 `classes4.dex` 含 `com.js.*` | EasyClick API + 加密类 |
| `assets/` 下有随机名小文件 + 2个大 ZIP | 加密配置 + 运行时包 |
| APK 根目录 `*.properties` 含 `maven_hash` 字段 | IEC 包定位线索（不在 assets/ 下） |
| assets 小文件头 `11 0A 20 24` | 自定义 XOR 加密配置文件 |

## 1. 完整解密链路

```
APK
 ├─ *.properties (maven_hash) ──hex解码──→ IEC 文件路径
 │   优先级: play-services-base → apache-common-service → transport-runtime
 │   条件: 解码后含 "." 才通过, 否则跳到下一个
 │   全失败 → fallback "ts.iec"
 │
 ├─ IEC 文件可能藏在:
 │   a) assets/ 根目录（随机名文件）
 │   b) APK 根目录的 classpath 资源（如 org/mozilla/.../*.so）← 本案例
 │   c) Class.getResourceAsStream() 可达的任意路径
 │
 ├─ 第一层: JAR 壳剥离
 │   JarInputStream → MANIFEST.MF
 │   ├─ Extension-Name → 内部加密条目名（如 layout/res/xxx.png）
 │   ├─ Sealed → MD5 校验值
 │   提取指定条目 → 校验 MD5 → 读末尾4字节(LE uint32)= 偏移
 │   → 从偏移截取到倒数第4字节 → xxxmod 文件
 │   注意: JAR 可能是流式写入(无 central directory), Python zipfile 无法解析
 │         必须用流式解析(逐 local file header + data descriptor)
 │
 ├─ 第二层: IEC 二进制格式解析
 │   magic: 0x03 0x0B
 │   头部: version(4) + flag1(1) + flag2(1) + metadataSize(4)
 │         + indexDataSize(4) + reserved(4) + xor_key(32)
 │         + pkgNameLen(4) + pkgName(XOR) + sigLen(4) + sig(XOR)
 │         + secondKeyLen(4) + secondKey(32, XOR'd with primary key)
 │   索引块: magic 0x0A 0x0B + 签名校验数据
 │   数据块: magic 0x0F 0x10 + entryCount(4)
 │   每条目: flag(1) + crc_key(2) + nameLen(4) + dataLen(4) + sigLen(4)
 │           + name(XOR with crc_key) + data + sig
 │           flag==1 → data XOR decrypt with crc_key
 │           CRC2 校验: CRC-16 (poly=0xA001, init=0xFFFF)
 │
 └─ 第三层: 内容还原
     ├─ *.js → 明文 JS 源码（直接可读）
     ├─ jar/main.jar → ZIP 内含 classes.dex → jadx 反编译 → Rhino 转译
     ├─ uijar/ui.jar → 同上
     ├─ *.html / *.css → UI 布局资源
     └─ res/*.png → 图片资源
```

## 2. properties maven_hash 定位机制

代码类: `C0552oO080` (IECPkgStoreInfo)

properties 文件在 **APK 根目录**（不在 `assets/` 下），和 `classes.dex`、`AndroidManifest.xml` 同级。

```python
# 优先级链（base64 解码后是 properties 文件名，位于 APK 根目录）
priority = [
    "cGxheS1zZXJ2aWNlcy1iYXNlLnByb3BlcnRpZXM=",  # play-services-base.properties
    "YXBhY2hlLWNvbW1vbi1zZXJ2aWNlLnByb3BlcnRpZXM=",  # apache-common-service.properties
    "dHJhbnNwb3J0LXJ1bnRpbWUucHJvcGVydGllcw=="  # transport-runtime.properties
]

# 每个 properties 读 maven_hash → hex 解码成 UTF-8 字符串
# 如果结果非空且含 "." → 作为 IEC 包路径
# 全失败 → fallback "ts.iec"
```

**实战案例**:
- `play-services-base` → `ivpd300lmzqnr2gzhnk872j...` 不含`.` → 跳过
- `apache-common-service` → 不存在 → 跳过
- `transport-runtime` → `org/mozilla/javascript/resources/nd4a6tyaqpxc.so` 含`.` → 命中

IEC 包伪装成 Rhino 资源 `.so` 文件，打包在 APK 根目录的 classpath 中。

## 3. JAR 壳流式解析

JAR 可能是**流式写入**（每个 entry 的 size 在 data descriptor 而非 local file header），Python `zipfile` 无法处理。必须逐 local file header 流式解析：

```python
# 参见 scripts/decrypt_iec.py 中的 parse_jar_stream()
# 关键: flags & 0x08 → has data descriptor
# 扫描 PK\x07\x08 签名取真实 comp_size/uncomp_size
```

## 4. IEC 头部结构（ooo080.m3734lll）

```
偏移  大小  字段               说明
0     2     magic              {0x03, 0x0B}
2     4     version            LE uint32
6     1     flag1
7     1     flag2
8     4     metadataSize       LE uint32
12    4     indexDataSize      LE uint32, 索引块字节数
16    4     reserved           LE uint32
20    32    xor_key            主 XOR 密钥(IIiL1), 同时转 int[16] 做签名校验
52    4     pkgNameLen         LE uint32
56    N     pkgName            XOR(xor_key) → 包名字符串
56+N  4     sigLen             LE uint32
60+N  M     signature          XOR(xor_key) → RSA 公钥/签名字符串
...   4     secondKeyLen       LE uint32
...   32    secondXorKey       XOR(xor_key) → 二级密钥(iIlI), 用于条目名解密
```

## 5. IEC 条目格式（ooo080.m3735lll）

索引块之后：
```
2 bytes  magic {0x0F, 0x10}
4 bytes  entryCount (LE)

每条目:
  1 byte   flag        (0=不加密, 1=XOR加密)
  2 bytes  crc_key     (CRC-16 校验字节, 同时是 XOR key)
  4 bytes  nameLen     (LE)
  4 bytes  dataLen     (LE)
  4 bytes  sigLen      (LE)
  N bytes  name        XOR(crc_key) → UTF-8 文件名
  M bytes  data        flag==1 → XOR(crc_key) → 明文
  K bytes  sig         签名数据(HMAC 校验)
```

CRC-16 校验算法（`C8o80o.m4946lll`）:
```python
def crc2(data):
    crc = 0xFFFF
    for b in data:
        crc = ((crc & 0xFF) ^ (b & 0xFF)) | (0xFF00 & crc)
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return struct.pack('<H', crc & 0xFFFF)
```

## 6. 自动化脚本

### 一键解密: `scripts/decrypt_iec.py`

```powershell
python scripts/decrypt_iec.py --apk target.apk --output ./extracted
```

脚本自动完成:
1. 解包 APK
2. 读 properties → 定位 IEC 文件
3. 从 APK classpath 提取 IEC 文件
4. 剥离 JAR 壳（流式解析）
5. 解析 IEC 二进制格式
6. XOR 解密所有条目 + CRC 校验
7. 输出到指定目录

### Rhino 编译类→JS 自动转译: `scripts/rhino2js.py`

解密后 `jar/main.jar` 和 `uijar/ui.jar` 内的 `classes.dex` 需要先 jadx 反编译再自动转译：

```powershell
# 1. jadx 反编译 JAR（内含 classes.dex）
jadx -d out_main jar/main.jar
jadx -d out_ui  uijar/ui.jar

# 2. 自动转译每个 Rhino NativeFunction 类
python scripts/rhino2js.py out_main/sources/com/js/main.java  restored/main.js
python scripts/rhino2js.py out_main/sources/com/js/PJYSDK.java restored/PJYSDK.js
# ... 对每个 .java 文件执行
```

转译器特性：
- 自动提取 `getFunctionName` / `getParamOrVarName` / `getParamCount` 元数据
- 内联 `_kN` 常量池、`_reN_M` 正则表达式
- 翻译 Rhino API 调用链：`NameLinker`/`PropLinker`/`OptRuntime`/`MathLinker`/`ScriptRuntime`
- 处理 EasyClick 特有的 UI API（`has`/`id`/`text`/`desc`/`swipeToPoint` 等）
- 跳过 Rhino 内部优化分支（`instanceof` 检查、`_id` 分发、scope 管理）
- 实测覆盖率 98.5%（5179行JS，80个TODO 残留在深嵌套链式调用）

## 7. 混淆类名映射（jadx 输出）

classes5.dex 中核心类（类名全部用 O/o/0/8 组合混淆）:

| 混淆类名 | 功能 | 对应概念 |
|---|---|---|
| `C0552oO080` | IECPkgStoreInfo | IEC 包管理器, 定位/解密 assets |
| `ooo080` | IEC 解析器 | JAR壳剥离 + IEC 二进制格式解析 |
| `C0499OOoo8o0` | 配置解密 | 解密 `11 0A 20 24` 头部的 assets 文件 |
| `O880O0` | AES/ECB 工具 | 网络通信加密（与 IEC 无关） |
| `oOoo888o` | AES-CTR 加密器 | WinZip 风格（PBKDF2, 本案例未使用） |
| `O0Oo8o` | AES-CTR 解密器 | WinZip 风格解密端 |
| `C0086OoO0o8` | AndroidClassLoader | loadDex/loadJar 运行时加载 |
| `OO0o88` | 配置管理 | 读 config.json, 提供版本号+IEC文件名 |
| `C0528OOO` | Hex 工具 | hex 字符串 ↔ bytes 互转 |
| `C0035O80oOo` | 字节工具 | LE 读写 + XOR + 数组拼接 |
| `C8o80o` | CRC-16 | 条目完整性校验 |
| `C0176o08` | IO 工具 | assets.open / getResourceAsStream |

## 8. assets 文件类型速查

| 文件头 (hex) | 类型 | 说明 |
|---|---|---|
| `11 0A 20 24` + LE uint32 | 自定义加密配置 | XOR + CRC2 校验 |
| `50 4B 03 04` | ZIP/APK | 嵌套运行时包 |
| `89 50 4E 47` | PNG | 图片资源 |
| `41 43 45 44` | Java 序列化 | UUID/设备绑定 |
| `65 79 4A...` / `41 77 45...` | Base64 编码 | 解码后是 JSON 或标志位 |
| `36/37/38...` (ASCII 0-9/a-f) | Hex 编码 | 解码后是 token/密钥 |

## 9. 常见变体与应对

| 变体 | 应对 |
|---|---|
| IEC 文件在 assets 根目录（随机名） | properties 优先链第一级就命中 |
| IEC 文件在 APK classpath（伪装 .so） | `Class.getResourceAsStream()` 路径, 从 APK ZIP entries 直接提取 |
| JAR 壳有 central directory | Python `zipfile` 可直接解析, 不需要流式 |
| JAR 壳无 central directory（流式写入） | 必须逐 local file header + data descriptor 流式解析 |
| IEC 条目 flag=0（不加密） | 跳过 XOR, 直接读明文 |
| 有 AES-WinZip 层 | 需要额外追溯密码来源（`o08880.Lil()` → 配置类） |
| 嵌套 ZIP 内含 Rhino 引擎 | 运行时框架, 不含用户脚本, 可跳过 |

## 10. 踩坑记录

1. **Python zipfile 无法解析流式 JAR**: 报 `BadZipFile: File is not a zip file`。必须手写流式解析器。
2. **maven_hash 含 `.` 的判断**: 代码用 `lastIndexOf(".") == -1` 跳过，不是检查是否是有效文件名。
3. **IEC 文件可能不在 assets 目录**: 会藏在 APK 根的 classpath entries 里，伪装成 `.so` / `.properties` 等。
4. **文件名 XOR key 只用 crc_key (2 bytes)**: 不要拼接 second_xor_key，那是索引块用的。
5. **偏移截取逻辑**: 末尾4字节是偏移值，从偏移处截到倒数第4字节（不含偏移字段本身）。
6. **中文文件名**: IEC 条目名可能含中文（如 `res/关闭红包.png`），注意编码处理。
