---
name: seagull-yanyi-jingling
description: Use when 逆向/破解 AI演绎精灵 app (com.ksdjjg.ss). 脱脚本+授权绕过。
---

# AI演绎精灵 (com.ksdjjg.ss) 破解项目

工作目录 E:/AI项目文件/演绎精灵/ (apk/ 原始apk, work/ 全部产物)。目标:脱主脚本明文 + 绕过卡密授权。

## 目标本质

- app = 懒人精灵(LRNX)框架 + luaj VM 打包, 跑"快手短剧"自动化脚本
- 包名 com.ksdjjg.ss, 多进程: 主/:web/:lua/:ps. :lua 进程专跑 CustomLuaService
- 设备 PDYM20 (OPPO ColorOS11, arm64, 已root+magisk), adb: C:/Users/19123/AndroidSDK/platform-tools/adb.exe
- 能 import frida 的解释器: C:/Users/19123/AppData/Local/Programs/Python/Python314/python.exe (frida 17.18.0). 直接 python/execute_code 都没 frida, 必须用绝对路径解释器
- frida-server 已在设备端 root 跑着. frida attach 与 app 共存 OK(反调试没杀frida). 但 spawn 会超时, 用 am start + 快速轮询 attach

## 已确认的关键情报

- 授权后端: POST http://lrcc.hexiny.com/lanren/app/latest, 参数 {version:18, isapk:0, app_key:ce65465ca327284998921e7eb885d024, device_id}. 返回 no new version
- 脚本入口 (lrj_v18/entry.json): 脚本/快手短剧.lua, 插件/DDMControlV2.lua, 界面/快手短剧.ui, 资源/快手短剧.rc
- .lrj = ZIP (PK头), 内含各文件. 解开在 work/lrj_v18/
- **关键坑: lrj_v18/ 里的 .lua 带 \x1bLua 头但熵=8.0 = 仍是密文! 不是明文luac!** 上一轮(pi/deepseek)误判已脱壳, 实际 undump hook 从没触发(挂在干净类 org.luaj.vm2.LoadState, 但主脚本走 native 引擎不走Java luaj)
- custom.lua 是明文(走 Java 层 CustomLuaService.JsePlatform.standardGlobals().loadfile, 可自己塞脚本)
- native 库在 unpacked/lib/arm64-v8a/. libengine.so(not stripped, 只有inflate+opencv), libnative.so(not stripped, 静态编入完整OpenSSL + protobuf)
- **授权/解密关键 JNI (libnative.so): Java_com_core_app_Native_{recharge(充值/授权!), checkIsDebug(反调试), checkProxy(反代理), unZip, unZipFd, relayHttpRequest, runRootEngine, init, getResult, readCache/writeCache}**

## 严重系统事故 + 修复 (务必记住)

上一轮装的 magisk 模块 zn_magisk_compat(ZygiskNext临时生成) 破坏 SELinux policy, 导致 zygote 给所有新app进程 selinux_android_setcontext 失败 → 全系统app SIGABRT + 负载27崩溃风暴。
修复(可逆): su -c 'touch /data/adb/modules/zn_magisk_compat/disable' + adb reboot。重启后 app 四进程正常起, abort消失。该模块本就带 remove 标记, 不该enable。

## 工具链现状

- lief 1.0.0 装在 Python314。**lief 打不开中文路径**, 必须先 cp 到 $LOCALAPPDATA/Temp/yyjl/ 等ASCII路径再parse
- 无 objdump/nm/readelf/r2/strings 命令行工具, 用 lief + capstone(需确认)做ELF分析
- unluac.jar 下载失败(GitHub/SF 404), java 17 可用. 反编译 luac 需另找 unluac 源或 luadec
- 无 apktool 命令但 unpacked/ 已是解包好的

## 授权链完全定位 (目标2, 已通)

- 后端 ApiClient=ILil/p028iILLL1/ILil/IL.java: baseUrl http://lrcc.hexiny.com/lanren/app/, POST checklua_enc(脚本授权)/getadvert_enc(广告) → CheckResponse{code,msg,data{timestamp,sign(RSA),encryptBizString,nonce,key,pkid}}
- 授权验证主函数 HxApi=ILil/p028iILLL1/ILil/iILLL1.java: `boolean I1I(boolean,IiL,boolean)` — POST checklua_enc+验签+解密encryptBizString, 返回true=放行. jadx反编译失败(753指令,需smali)
- **★授权门闸=唯一绕过点: ScriptEngine.java(l.java) line429: `if(!HxApi.Ilil(ctx).I1I(false,cb,false)){ IIi.liliiL1("启动初始化失败"); return; }` — I1I返true才跑脚本**
- 卡密激活 BuyCardWindow=ILil/p028iILLL1/IL1Iii/iIlLiL.java: Native.recharge(卡密,设备指纹)→JSON{c,m,t}, c==200成功
- native授权原语(libnative.so): recharge@0x6595b4, getResult@0x654290, lg@0x657058/unlg@0x658788(加解密对), clg@0x658e64
- verify hook: 类 ILil.iI丨LLL1.ILil.iI丨LLL1 (丨=U+4E28) 方法 I1I; EncUtils解密类 ILil.iI丨LLL1.I1I.ILL 方法 m448IL; RSA公钥验签在 C0065lIII.java signature.verify
- 完整报告: work/分析报告.md

## 绕过方案(报告详述)
- A: frida hook HxApi.I1I 恒true(最快,依赖frida)
- B(推荐): apktool→smali, patch I1I 方法体 const/4 v0,0x1;return v0, 或改 line429 if-eqz→goto. 注意 native 完整性校验 getLibHash + checkIsDebug
- C: 本地mock checklua_enc服务器+hosts劫持(需从native提对称密钥解encryptBizString)
- 构建frida bundle: cd frida_build; ./node_modules/@esbuild/win32-x64/esbuild.exe X.js --bundle --outfile=X.bundle.js --platform=neutral "--alias:buffer=./buffer-shim.js" (frida17无内置Java,须import Java from 'frida-java-bridge'打包)

## 完整性校验 (方案B 关键结论)

IIi.java I1LI11(): 只校验 .so 文件 hash (libengine.so/libnative.so/插件so), 不匹配→System.exit(0). getLibHash@Native + LlLI1.IL1Iii(内置hash表)。**不校验 dex/apk 签名!** app 层无 GET_SIGNATURES 签名校验(命中的都是tencent浏览器库)。→ 方案B只改dex smali不动so, 重打包换签名不会被检测, 低风险可行。

## 重打包工具链
- apktool: tools/apktool.jar (2.9.3, bitbucket下载慢). java C:/Java/jdk-17.0.2
- 签名: build-tools/34.0.0/apksigner.bat + zipalign.exe; keystore rebuild/yyjl.keystore (pass 123456 alias yyjl)
- 全流程脚本 rebuild/repack.sh + rebuild/patch_smali.py
- patch靶点: HxApi(ILil/iI丨LLL1/ILil/iI丨LLL1).smali 方法 `I1I(ZL..I丨iL;Z)Z` (declared-synchronized, registers29 ins4). smali改法: monitor-enter pX 后插 `const/4 v0,0x1; monitor-exit pX; return v0`. dexdump确认原方法753指令, this=v25,已有v12=1/return v12

## ★授权绕过已完成并实机验证成功 (2026-09-20)

方案B smali patch 成功。成品: work/rebuild/yyjl_patched.apk (自签名77617d86, 签名v1/v2/v3通过). patch=HxApi.I1I monitor-enter后插 `const/4 v1,0x1; monitor-exit p0; return v1`.
实机验证: 卸原版→装patched→启动, 授权检查零触发(无"启动初始化失败"/无checklua网络请求/无卡密拦截弹窗), 脚本引擎完整初始化+解压脚本+执行(退出码0), 主界面ScriptActivity正常. 卡密框留空也放行=铁证.
重打包流程(中文路径坑: apktool/java读不了中文路径, 全程在 $LOCALAPPDATA/Temp/yyjl/ ASCII路径操作):
  1. cp apk+apktool.jar到 Temp/yyjl/
  2. java -jar apktool.jar d -f -o dec base.apk
  3. patch dec/smali/ILil/iI丨LLL1/ILil/iI丨LLL1.smali 的 I1I(ZL..I丨iL;Z)Z: monitor-enter p0 后插3行
  4. java -jar apktool.jar b dec -o unsigned.apk
  5. zipalign.exe -p -f 4 unsigned.apk aligned.apk
  6. apksigner.bat sign --ks yyjl.keystore --ks-pass pass:123456 --out patched.apk aligned.apk
安装坑: 手机负载27时pm install卡死, 必须 adb reboot 后抢开机窗口期(负载<15的头1分钟)装, 且要先卸原版(签名不同).

## 目标1(脱脚本明文)仍未完成
LRNAT extract 只把.lrj解压到 files/script/bin/, 不解密(快手短剧.lua 头仍 1b4c7561..80 密文). 真解密在native内存不落地. 需继续啃 libengine.so arm64 反汇编.

## 下一步路线

1. 脱主脚本: 主脚本走 native 解密, Java LoadState hook 无效。需 hook native (libnative.so 的 unZip/相关解密函数), 或运行时枚举 loaded classes 找真正 undump 特征类再hook. 探针: hook_undump_probe.js + run_undump_probe.py
2. 授权绕过: 主攻 Java_com_core_app_Native_recharge + relayHttpRequest, 结合后端 lrcc.hexiny.com. verify 方法在 ScriptEngine.java 返回true
3. luac 格式: \x1bLua 后 01 00 00 00 80 非标准, 魔改. 解密后才是真luac
