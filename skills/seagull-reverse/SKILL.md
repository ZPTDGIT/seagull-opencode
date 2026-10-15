---
name: seagull-reverse
description: Seagull 深度逆向：PE/ELF/Mach-O、固件、驱动、APK/DEX、.NET、Go/Rust、IL2CPP、去混淆、协议重构。
---

# Seagull Reverse Engineering Skill

深度逆向工程技能：PE/ELF/Mach-O、固件、驱动、APK/DEX、.NET、Go/Rust、Unity IL2CPP、Unreal、解包、去混淆、自定义 VM、协议重构、打补丁和逆向自动化。

## 触发条件

- 用户提到：逆向、reverse、反编译、脱壳、hook、逆向工程
- 提供二进制文件、伪代码、汇编、崩溃跟踪
- 需要算法恢复、协议重构、patch 点识别

## 工作流程

### 1. 初始 Triage

从可用 artifact 立即开始：
- Hash（MD5/SHA256）
- 文件格式识别：`file`、`strings`、`checksec`
- 架构、ABI、字节序、编译器、保护机制
- 导入表、导出表、字符串、资源

### 2. 静态分析

**工具选择**（按平台）：
- **Linux/macOS**: radare2、Ghidra、Binary Ninja
- **Windows**: IDA Pro、x64dbg、dnSpy（.NET）
- **Android**: jadx、apktool、JEB、Frida

**分析重点**：
- 入口点与初始化流程
- 关键函数定位：校验、加密、网络通信
- 数据结构恢复
- 控制流与调用图
- 字符串引用与常量

### 3. 动态分析

**调试器**：
- Windows: x64dbg、WinDbg
- Linux: gdb + gef/pwndbg
- Android: Frida、LLDB
- 通用: QEMU、unicorn

**Hook 技术**：
```python
# Frida hook 模板
import frida
import sys

def on_message(message, data):
    print(f"[{message['type']}] {message.get('payload', '')}")

session = frida.attach("target_process")
script = session.create_script("""
Interceptor.attach(ptr("0x12345678"), {
    onEnter: function(args) {
        console.log("Called with:", args[0], args[1]);
    },
    onLeave: function(retval) {
        console.log("Return:", retval);
    }
});
""")
script.on('message', on_message)
script.load()
sys.stdin.read()
```

### 4. 去混淆与解包

**常见保护**：
- UPX/VMProtect/Themida/Enigma
- .NET 混淆：Confuser/ConfuserEx、de4dot
- Java/Android：ProGuard、DexGuard
- JavaScript: obfuscator.io、webpack

**策略**：
- 识别混淆器特征
- 查找已知解包工具
- 手动跟踪解密例程
- dump 内存中的解密代码

### 5. 算法恢复

**步骤**：
1. 定位关键函数（加密/校验/签名）
2. 提取伪代码或汇编
3. 识别已知算法（AES/RSA/CRC/自定义）
4. 用 Python/C 重新实现
5. 对比测试用例验证

**示例**（自定义校验算法恢复）：
```python
def custom_checksum(data):
    """从逆向中恢复的校验算法"""
    result = 0x5A5A5A5A
    for byte in data:
        result = ((result << 3) | (result >> 29)) & 0xFFFFFFFF
        result ^= byte
        result = (result * 0x01234567) & 0xFFFFFFFF
    return result

# 验证
test_data = b"test"
expected = 0x12345678  # 从样本中提取
assert custom_checksum(test_data) == expected
```

### 6. Patch 工程

**Patch 点类别**：
- 跳转修改：`jz` → `jmp`、`jnz` → `nop`
- 返回值篡改：`mov eax, 0` → `mov eax, 1`
- 函数调用绕过：`call check_license` → `nop; nop; nop; nop; nop`
- 字符串替换

**工具**：
- 手工：HxD、010 Editor
- 脚本：Python + pefile/LIEF
- IDA: Keypatch 插件

**Python patch 示例**：
```python
import pefile

pe = pefile.PE("target.exe")
# 找到 license check 跳转
# 原始: 0x1000: 74 12  (jz +0x12)
# 修改: 0x1000: EB 12  (jmp +0x12)
offset = 0x1000
pe.set_bytes_at_rva(offset, b'\xEB')
pe.write("target_patched.exe")
print(f"Patched at RVA 0x{offset:X}")
```

### 7. 协议逆向

**网络协议**：
- 抓包：Wireshark、tcpdump
- 中间人：mitmproxy、Burp Suite
- 分析：帧结构、字段、状态机
- 实现：parser、dissector、重放工具

**二进制协议模板**：
```python
import struct

class ProtocolMessage:
    def __init__(self, data):
        # 假设协议：4字节魔数 + 2字节长度 + 2字节类型 + payload
        self.magic = struct.unpack('>I', data[0:4])[0]
        self.length = struct.unpack('>H', data[4:6])[0]
        self.msg_type = struct.unpack('>H', data[6:8])[0]
        self.payload = data[8:8+self.length]
    
    def __repr__(self):
        return f"Msg(magic=0x{self.magic:X}, type={self.msg_type}, len={self.length})"

# 解析
msg = ProtocolMessage(captured_packet)
print(msg)
```

## 双平台支持

### Linux 命令
```bash
# 基本信息
file binary
strings binary | grep -i "password\|key\|license"
checksec --file=binary

# 反汇编
objdump -d binary
radare2 -A binary -c 'pdf @ main'

# 动态跟踪
ltrace ./binary
strace -e trace=open,read,write ./binary

# Frida
frida -U -f com.example.app -l hook.js
```

### Windows 命令
```powershell
# 基本信息
Get-FileHash binary.exe -Algorithm SHA256
sigcheck.exe -a binary.exe

# 反汇编（需要工具）
& "C:\Program Files\IDA\idat64.exe" -A binary.exe

# 调试
& "C:\Program Files\x64dbg\x64dbg.exe" binary.exe

# Frida（Windows 进程）
frida.exe -p <PID> -l hook.js
```

## 交付清单

必须包含：
1. **Hash 与元信息**
2. **关键函数地址/偏移**
3. **恢复的算法/协议/结构**
4. **等价 Python/C 代码**
5. **调试器脚本/命令**
6. **验证步骤**

## 缺样本时

给出通用骨架 + 一行采集命令：
```
请提供二进制文件，或用以下命令采集：
Linux: sha256sum binary && file binary && strings binary > strings.txt
Windows: Get-FileHash binary.exe; Get-Content binary.exe -Encoding Byte | Format-Hex > hex.txt
```

## 示例：完整 crackme 解决

```python
#!/usr/bin/env python3
"""
Crackme solver - 从逆向中恢复的密钥生成算法
Hash: abc123...
Platform: Linux x64
Protection: None
"""

def generate_serial(username):
    """从 sub_401234 逆向恢复的序列号生成"""
    # 算法：username 每个字符 ASCII * 0x1337，累加，取模 0x1000000
    result = 0
    for char in username:
        result += ord(char) * 0x1337
    result %= 0x1000000
    return f"{result:06X}"

# 验证
test_user = "admin"
serial = generate_serial(test_user)
print(f"Username: {test_user}")
print(f"Serial: {serial}")

# 对比二进制内置检查
# ./crackme admin 3D91E2  # 应该输出 "Correct!"
```

## Electron 应用全量还原 (NSIS + bytenode + obfuscator)

景瑞助手类 electron-egg 桌面软件, 三层保护, 已跑通完整链路:

### L1 解包 NSIS→asar
```bash
curl -sL https://www.7-zip.org/a/7zr.exe -o 7zr.exe   # 无7z时
curl -sL https://www.7-zip.org/a/7z<ver>-extra.7z -o x.7z && ./7zr.exe x x.7z  # 得含NSIS支持的7za
7za e app.exe -oout "resources\app.asar"              # NSIS内嵌7z, 直接抽app.asar
npx asar extract app.asar src                         # 若报unpacked缺失, 自写解析器只提inline文件
```
asar格式: 前16字节4个uint32(pickle头/header_size/json_size), 之后JSON目录+数据区; 数据区offset=8+header_size。node报unpacked缺失时, 跳过 node.get('unpacked') 的项即可。

### L2 jsc (V8 bytecode / bytenode) 反编译 —— 关键
- .jsc magic `c0de063a`, 头部含 version_hash(如 a5e2d63c=Electron31/V8 12.6)。
- **VersionDetector.exe 认不出=Electron自定义tag**, 但 jsc2js 的跨宿主兼容层跳过version hash, **相近的 12.6.228.x d8 能直接吃 Electron 的 .jsc**。
- 工具: `github.com/xqy2006/jsc2js` (patched d8 带 loadjsc + 定制View8)。releases 有 9/10/11/12.x/15.x 各精确版, API分页只列部分, 用 `/releases/tags/<ver>` 逐个探测存在性。
- **GitHub下载被墙用镜像** `https://ghfast.top/https://github.com/...`。
```bash
./d8.exe -e "loadjsc('x.jsc')" > x.txt          # d8需在自己目录跑(找snapshot_blob.bin)
python view8.py --disassembled x.txt x.js         # 定制View8语法: 位置参数,非-i/-o
```
- **坑1**: Windows subprocess 传中文路径给d8会被mbcs编码破坏 → 复制jsc到ASCII临时名再喂。
- **坑2**: View8 subprocess 的 cwd=View8目录时, 输入txt必须传**绝对路径**, 否则"Decompiling 0 functions"(找不到文件却不报错)。
- **坑3**: view8依赖 `parse` 库, 用 `uv pip install --python <venv>/python.exe parse` 装到跑它的解释器。
- 产出是"语义近似": 变量成r0/r1, 控制流保留, 字符串若被obfuscator二次加密则显示为 `Scope[x][y](idx,key)` 的RC4密文调用。

### L3 obfuscator.io 去混淆
```bash
npm i -g webcrack && webcrack x.js -o out/   # 自动解字符串数组+内联解码器+去控制流平坦化, 对obfuscator.io降维打击
```
webcrack只吃合法JS(明文混淆js), **吃不了View8反编译的伪JS**(<unknown>/ACCU非法语法)。

### L3.5 .jsc 字符串完全解明文 (obfuscator二次混淆) —— 运行时hook法(已验证)
当 .jsc 是 obfuscator.io 混淆后再编译时, 反编译产物字符串显示为 `Scope[x][y](idx,key)` 密文调用。完全解明文用**运行时**最可靠:
1. 下匹配版 Electron 执行 .jsc: `ELECTRON_RUN_AS_NODE=1 electron.exe stub.js` (镜像 npmmirror.com/mirrors/electron/<ver>/electron-v<ver>-win32-x64.zip)。本机Node V8版本对不上会 `cachedDataRejected`, 必须用编译该jsc的Electron(如E31=V8 12.6)。
2. `require('bytenode'); const m=require('x.jsc')` — 版本匹配即成功, 模块导出直接可用。
3. **最强招: hook 关键内建实测**。obfuscator 的 idx→key 配对难静态重建(key常是变量/幌子), 但实跑时字符串已明文。对纯算法模块直接 hook `crypto.createHmac().update()` / `createHash().update()` / `axios` 截获真实入参, 一次拿到确切算法(如签名待签串)。
4. **等价性对拍验证**: 固定 `Date.now` 和 `crypto.randomBytes` 后, 手写还原版与原jsc对比输出应字节级一致 —— 这才算"证明还原正确"而非近似。
5. 用 inspector Session (Node内置,无需ws) + `Runtime.getProperties` 取导出函数 `[[Scopes]]` 可定位2参数解密器函数, `callFunctionOn` 枚举idx; 但key配对是坑, hook法更快。
实战: 景瑞助手 apiSign.jsc 签名 = `HMAC_SHA256(secret, [METHOD,path,ts,nonce,SHA256(stableStringify(body))].join('\n'))`, hook crypto 一次确认, 对拍字节级一致。

### 还原质量分级交付
A明文.bak(作者遗留,100%) > B webcrack去混淆(明文混淆js) > C jsc反编译(逻辑可读,字符串仍加密)。整合脚本注意: 有.bak的模块别被同名.jsc反编译版覆盖。
C级字符串完全解密需在 Node20/Electron31 运行时实跑obfuscator解密器提映射表回填。

## 与其他技能配合

- **+ exploit**: 漏洞定位 → 利用开发
- **+ malware**: 样本分析 → 行为理解
- **+ game-hack**: 引擎结构 → 内存修改
- **+ license-security**: 授权验证 → 绕过实现

---

**路由激活**：当用户提到逆向、二进制分析、算法恢复、协议重构或提供可执行文件时，自动使用本技能。

直接从可用 artifact 开始，交付完整分析 + 可运行代码 + 验证步骤。
