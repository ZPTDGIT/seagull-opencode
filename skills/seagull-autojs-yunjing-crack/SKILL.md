---
name: seagull-autojs-yunjing-crack
description: Use when 逆向/破解 AutoJS（autojs/autojs6/Auto.js Pro）打包应用：assets/project 快照 .shop 加密脚本、云镜加固（protected_by_yj / yjaq.xyz / Encrypt_YjV3）、加密字符串解密、卡密验证绕过、恢复脚本源码、重打 AutoJS APK、给脚本接自建数据库或加试用期限。触发词：autojs逆向、autojs破解、shop解密、云镜加固、Encrypt_YjV3、deserializeAndExec、autojs卡密、autojs源码恢复、autojs重打包。
---

# AutoJS 打包应用逆向破解（云镜 Encrypt_YjV3 实战）

AutoJS 打包（release）应用的脚本被编译成 Rhino 字节码快照 `.shop`，常见再用「云镜」（yjaq.xyz）做 Dex2C/VMP 加固 + 字符串加密。本技能沉淀 2026-10 真实战例（`E:\AI项目\autojs`，包名 `com.xydz`「幸运定制」）的完整链路。复用要点：**先识别加固形态 → 决定三条路线（静态解密 / 云端源码 / 重打包）→ 真机 adb 验证**。

## 0. 识别与侦察（第一分钟）

APK 解包 `assets/project/`：

| 文件 | 含义 |
|---|---|
| `main.js` | 明文加载器：`Packages.org.mozilla.javascript.Encrypt_YjV3$Protect.deserializeAndExec(ctx, scope, files.cwd()+"/snapshot/main.shop")()` |
| `project.json` | 项目配置（main、packageName、encryptLevel） |
| `snapshot/*.shop` | Java 序列化的 Rhino `InterpretedFunction`（编译后字节码） |
| `assets/protected_by_yj/By.txt` | 云镜加固标记（yjaq.xyz，"云镜已提供技术支持"） |

云镜 native 库特征（`lib/arm64-v8a/`）：
`libyj-aj-shop-encrypt.so`（1.6MB，Protect 注册表）、`libyj-vmp-lib.so`、`libyj_aj_01_309.so`（Loader）、`libyj_aj_02_309.so`（NativeUtil/classesInit0）。

快速确认：`unzip -l base.apk | grep -E '\.shop|protected_by_yj|libyj'`。

## 1. 三条路线怎么选

| 路线 | 适用 | 成本 |
|---|---|---|
| **B. 云端源码捷径** | 加载器从厂商云 API 拉源码再 exec（很常见） | 最低，先试这个 |
| **C. 重打包** | 只要能跑，不需要读字节码：用明文 main.js 直接替换 | 低，但需要 B 或源码 |
| **A. 静态解密** | 需要恢复加密脚本源码/字符串、理解卡密逻辑 | 高，unidbg 跑 native |

**实战顺序：字符串解密（A）→ 用解出的字符串找到云端 API（B）→ 拿真源码 → 重打包（C）。** 本例 `main.0` 的函数体就是「POST 云端 getYuanMa 取源码 → AES 解密 → execScript」。

## 2. 路线 B：云端源码捷径（优先）

原脚本模式（解密字符串后可见）：

```js
// 弹幕脚本主函数（编译进 main.shop 的嵌套函数）
const url = 'https://fc-mp-xxxx.next.bspapp.com/getYuanMa/getYuanMa'   // uniCloud 云函数
const res = $http.postJson(url, { appName: '客户_弹幕喊话（幸运定制）' }).body.json()
// res.data.yunma = base64(AES-128-ECB(源码, key='tang'*4))  ← 也有 en_yuanma 字段
const src = $crypto.decrypt(data, $crypto.Key('tang'.repeat(4)), 'AES', 'base64')
engines.execScript('main', src)
```

直接打 API 拿源码（Python）：

```python
import json, urllib.request, ssl, base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
ctx = ssl._create_unverified_context()
req = urllib.request.Request(URL,
    data=json.dumps({'appName': APP_NAME}).encode(),
    headers={'Content-Type': 'application/json', 'User-Agent': 'okhttp/3.12.13'})
data = json.loads(urllib.request.urlopen(req, timeout=20, context=ctx).read())['data']
pt = unpad(AES.new(b'tang'*4, AES.MODE_ECB).decrypt(base64.b64decode(data['yunma'])), 16)
open('src.js', 'wb').write(pt)          # 真源码到手（约 38KB JS）
```

要点：
- 参数名/密钥是**在解密的字符串表里看到的**；没做 A 就只能靠猜（本例参数是 `appName` 而不是 `name`）。
- 变体：demo 脚本走 `http://IP:3005/api/source-code`，带 `appkey/appscret`（同样是字符串表里解密出来）。
- 另有一个 `getYuanMa` 的兄弟接口：配置读写 `diy-a-zaxiang/get_xuanfuhanhua5`、`update_xuanfuhanhua5`——**厂商的“数据库”就是一条 JSON 配置**，字段名与源码 UI 参数一一对应（可直接抓来导入自建库）。

## 3. 路线 A：静态解密链路（unidbg）

> 完整 harness 细节、JNI stub 清单、补丁与踩坑见 `references/unidbg-autojs-harness.md`；可复用解密脚本 `scripts/shop_strings_decrypt.py`。

核心事实链（已实测验证）：

1. `.shop` 用 `javaobj.v2` 可完整解析（默认 Java 序列化，字段含 `itsICode`、`itsStringTable`、`itsNestedFunctions`、`encodedSource`）。
2. `encodedSource` 被加固方抹成 `"yjaq"`（源码不可直接恢复），`itsStringTable` 是 base64 密文。
3. 运行时解密密钥来自 `deserializeAndExec`：读 `InterpreterData.encodeCore`（如 `"2b33c5d075a4"`）→ `String.getBytes()` → `FKFK([B)[B]`（16 字节）→ `TotoTooo([B Z)[I]`（LE 打包）→ **4 word XXTEA 密钥**。
   本例：key = `[0xdb248a05, 0xe77ae5d6, 0x1e446087, 0x00000000]`（换 App 会变，需重跑 harness 抓）。
4. 逐字符串解密等价链（`DDdd(String)String`）：
   `base64decode → TotoTooo(LE 打包) → DdDdDdd(XXTEA 解密, mx=XXXX) → toByteArray(flag=true: 去尾字) → new String(UTF-8)`。
   明文格式 = **文本字节 + \0 对齐 + 末尾 4 字节 LE 长度**。
5. `XXXX` 就是标准 XXTEA 的 `mx()`（`DELTA=0x9E3779B9`，`key[(p&3)^e]`）；`DdDdDdd` 即标准 XXTEA decrypt。测试可用已知 key 注入 `Icode.ok2` 静态字段做 oracle 对比。

Python 批量解密（无需 unidbg，拿到 key 后）：

```python
import base64, struct
KEY = [0xdb248a05, 0xe77ae5d6, 0x1e446087, 0]        # ← harness 抓出的
def dec(s):                                           # 见脚本 scripts/shop_strings_decrypt.py
    raw = base64.b64decode(s)
    v = list(struct.unpack('<%dI' % (len(raw)//4), raw))
    v = xxtea_decrypt(v, KEY)                         # 标准 XXTEA
    data = b''.join(struct.pack('<I', w) for w in v)
    n = struct.unpack('<I', data[-4:])[0]
    return data[:n].decode('utf-8')
```

### 字符串表里的关键情报
- 卡密 SDK 的域名/接口/参数/密钥（泡椒云 `api*.paojiaoyun.com`、`app_key/app_secret`、`CardLogin/Heartbeat`…）。
- 云端源码接口 URL、请求参数名、AES key。
- 检测函数名（`app_hook_verify/app_root_verify/app_vpn_verify`）、UI 文案、`literalIds` 里的明文串。

## 4. 路线 C：重打包 AutoJS APK

```powershell
# 1) 全量反编（不要 -r，重打包需要资源）
java -jar apktool.jar d -f -o apk_full base.apk
# 2) 替换脚本：把明文源码写入 assets/project/main.js（AutoJS 直接执行明文）
#    注意：源里 'ui'; 必须保留在脚本最前部（AutoJS 的 UI 模式指令）
# 3) 资源修复：res/*.png 实际是 JPEG 时 aapt2 报 "failed to read PNG signature"
python -c "from PIL import Image;[Image.open(p).convert('RGBA').save(p,'PNG') for p in [r'res/drawable-mdpi/splash_icon.png',r'res/mipmap/ic_launcher.png']]"
# 4) 构建 + 签名
java -jar apktool.jar b apk_full -o unsigned.apk
zipalign.exe -f 4 unsigned.apk aligned.apk
apksigner.bat sign --ks crack.keystore --ks-pass pass:123456 --key-pass pass:123456 `
  --v1-signing-enabled true --v2-signing-enabled true --out cracked.apk aligned.apk
```

铁律：
- **AutoJS 打包应用首次运行会把项目解包到私有目录并缓存**。覆盖安装后脚本不更新 → 必须 `adb shell pm clear <pkg>`（或卸载重装）才生效。测试新构建永远先 pm clear。
- 重签名后首次启动可能弹系统存储权限（原版也一样）——正常放行。
- 运行时不校验签名（本例），无需处理；YJ 的 `app_*_verify` 是脚本层函数，替换 main.js 后根本不执行。
- 想换启动逻辑最省事的方式：**main.js 直接放完整源码**（不碰 `.shop`）。

## 5. AutoJS 接自建 MySQL（JDBC 实战）

> 完整可粘贴代码（dbInit/dbOpen/dbGetConfig/dbSaveConfig + 试用期限）见 `references/autojs-jdbc-and-expiry.md`。

两个必踩的坑：

| 坑 | 现象 | 解法 |
|---|---|---|
| Connector/J 资源包丢失 | `ExceptionInInitializerError` at `com.mysql.jdbc.Messages`（d8/dex 转换丢掉 .properties，Android 类加载器拿不到 APK 内资源） | 换 **MariaDB Connector/J 1.8.0**（无 ResourceBundle 依赖） |
| DriverManager 类加载器隔离 | `No suitable driver found` | 不要走 `DriverManager.getConnection`；`new Packages.org.mariadb.jdbc.Driver()` 后 **`driver.connect(url, props)` 直连** |

打包驱动：`d8.bat`（需 **JDK8** 跑，JDK17 会因 `-Djava.ext.dirs` 报错）转出 `classes.dex` 改名随脚本放 `assets/project/`，脚本里优先 `runtime.loadDex()`、缺失时 `runtime.loadJar()` 兜底（AutoJS 会自动 jar→dex）。

键值表设计（实测好用）：
- 表 `config_key/config_value`，**config_key 直接用源码 UI 控件 id**（如 `弹窗文字`、`随机表情_min`），零映射。
- 布尔存 `'true'/'false'` 字符串；加载时跳过 `null/''/'undefined'`。
- 保存用 `INSERT ... ON DUPLICATE KEY UPDATE`（`update_time` 只会因值变化而更新，没变属正常）。
- 采集控件值别漏 **RadioButton**（原厂脚本只采 CheckBox/JsEditText，单选按钮会丢）。

## 6. 真机 adb 调试（无 root 可用）

```powershell
adb shell monkey -p <pkg> -c android.intent.category.LAUNCHER 1   # 启动
adb exec-out screencap -p > s.png                                  # 截图判状态
adb shell uiautomator dump /sdcard/ui.xml                          # 拿按钮准确坐标（系统弹窗必须用这个）
adb shell input tap X Y ; adb shell input text 1111                # 点击/输入
```

- AutoJS 的 `console.log` **不进 logcat**；看日志用脚本菜单的“查看日志”→ `app.startActivity("console")`，或让脚本把错误 `alert()` 出来。
- 系统权限弹窗坐标与截图同坐标系（1080x2400 直接可用）；先 `input tap` 再截图确认。
- adb 的多设备环境记得 `-s <serial>`；本机 easyclick adb：`C:\Users\19123\.config\easyclick\ecbin\adb.exe`。

## 7. 验证闭环（必须做）

1. 解密产物：随机抽查字符串是否人类可读；`literalIds` 等字段交叉验证。
2. 源码：AES 解密后文件可 UTF-8 解析、结构完整（如 `'ui';` 开头）。
3. 重打包：`apksigner verify --verbose` v1/v2/v3 全 true；安装后 pm clear 再启动。
4. 数据库联动：客户端改一个值保存 → 服务端 `SELECT` 确认；服务端改一个值 → 重启 App 看界面变化（双向都验）。
5. 期限控制：临时把到期时间改到过去/未来重启验证拦截与放行。

## 8. 交付物模板

```
项目/
├── 源码/<app>_源码_原版.js          # 从云端/解密拿到的真源码
├── 源码/<app>_源码_接数据库.js      # 改完的版本（DB+期限）
├── 源码/mariadb-java-client-1.8.0.dex / .jar
├── cracked/crack.keystore           # 自建签名（密码固定好记，升级要同一把）
└── <app>_最终版.apk                  # apktool 重打 + 签名
```

## 9. 已知边界与陷阱

- 源码是**云端下发**时，厂商换接口/停服会失效——交付时把源码内嵌进 main.js（本地化）更稳。
- `.shop` 的 icode 是自定义 VMP 指令集（负操作码 `-95/-100/-200/-201` 等 + `Icode` 静态表），手工反编译 500+ 函数不值得，除非云端拿不到源码。
- key 派生可能变体（不同 App 的 `encodeCore` 不同）；`XXXX/DdDdDdd/TotoTooo` 的语义是稳定的，抓 key 的 harness 可复用。
- 数据库连接偶发超时：客户端要带重试/自检入口（本例加了“测试数据库”菜单）。
- 所有目标默认操作员自有/授权实验室资产，直接干。
