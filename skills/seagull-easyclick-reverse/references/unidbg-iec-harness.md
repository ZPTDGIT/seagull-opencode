# unidbg IEC2 解包 harness（实战记录）

> 实战位置：`E:\autojs_work\jinhe_decrypt\`（`VaultMain.java` + `run.cmd` + `run2.cmd`）
> 目标 APK：锦和_.apk，pkg `com.avpxamu7b.ccy838r2w`

## 0. files/ 目录约定（IOResolver 把模拟器路径映射到本目录同名文件）

```
files/
├── bundle.iec        # APK 内 kotlin/<随机名>.properties（IEC2 包，~150KB）
├── release.iec       # OSS 更新包（update.json 指向，同格式同 stamp，~155KB）
└── stamp.finger.so   # 就是 assets/<随机名> 原文件字节（317B，ECDC 容器；libecvault 内部解，无需预处理）
```

`stamp.finger.so` 从哪来：APK 资产随机名映射表里查到 `"stamp.finger.so": "h5858tkti5y"`，直接把 `assets/h5858tkti5y` 原样复制过来即可（换 App 需重解映射表，见主 SKILL 的资产映射说明）。

## 1. JNI 调用链（VaultMain.java 核心）

```java
AndroidEmulator emulator = AndroidEmulatorBuilder.for64Bit().setProcessName("com.avpxamu7b.ccy838r2w").build();
memory.setLibraryResolver(new AndroidResolver(23));               // 无 System.load，全靠 JNI stub
VM vm = emulator.createDalvikVM();
vm.setJni(new AbstractJni() { /* 只需补 Context->getPackageName() */ });
// IOResolver：模拟器里任何路径 → files/<basename> 存在则命中
DalvikModule dm = vm.loadLibrary(new File("...\\lib\\arm64-v8a\\libecvault.so"), true);
dm.callJNI_OnLoad(emulator);

DvmClass vault = vm.resolveClass("com/gibb/ecpkg/NativeVault");
DvmObject<?> ctx = vm.resolveClass("android/content/Context").newObject(null);
byte[] stamp = Files.readAllBytes(files/stamp.finger.so);

String deviceJson = "{\"androidId\":\"...\",\"brand\":\"samsung\",\"model\":\"SM-G9810\","
    + "\"osVersion\":\"12\",\"width\":1080,\"height\":2400,"
    + "\"apkVersion\":\"12.4.0\",\"ecVersion\":\"12.4.0\","
    + "\"md5\":\"<APK文件MD5>\",\"pkg\":\"com.avpxamu7b.ccy838r2w\"}";

// 1) 看授权码（可选，返回 UFPVVF）
vault.callStaticJniMethodObject(emulator, "nativePeekStamp(Ljava/lang/String;)Ljava/lang/String;", bundleGuest);

// 2) 开包
long handle = vault.callStaticJniMethodLong(emulator,
    "nativeOpenIecBundle(Landroid/content/Context;Ljava/lang/String;[BLjava/lang/String;ILjava/lang/String;)J",
    ctx, new StringObject(vm, "/data/local/tmp/bundle.iec"), new ByteArray(vm, stamp),
    new StringObject(vm, ""), 2, new StringObject(vm, deviceJson));

// 3) 列清单 → JSON 数组 [{path, kind}]
// 4) 逐 entry：nativeReadBundleEntryHandle(Context, handle, path) → [B → dump 到磁盘
//    文件名安全化：entry.replaceAll("[\\\\/:*?\"<>|]", "_")
// 5) nativeCloseIecBundle(handle)
```

要点：
- `apkType=2`（来自 ectemplate 内容，APK 内固定 2）。
- `deviceJson.md5` 必须是**传入那个 APK/更新包文件的 MD5**；device 信息不绑定个人设备（用任意真机信息即可）。
- 解出物：`jar/main.jar`（里面是 classes.dex）、`uijar/ui.jar`、`layout/main.xml`（原始 UI 源码！）、`update.json`。

## 2. 环境与运行

- unidbg：`E:\autojs_work\tools\unidbg_src\unidbg-master`，`mvnw package` 构建（**JDK8**）。
  - 源码需打两个补丁：`_GetIntArrayRegion`、`_IsAssignableFrom`（否则 native 回调异常）。
- 运行：`run.cmd`（默认解 `files/bundle.iec` → `dump/`）、`run2.cmd`（解 `release.iec` → `dump_update/`）。
  - classpath 关键依赖：unidbg-android/api/unicorn2 + unicorn/capstone/keystone/demumble + fastjson2 + commons-codec/io/collections4 + jna + slf4j。
  - 换包：把新 `.iec` 放进 `files/`，改 `run2.cmd` 里 `VaultMain <bundleName> <dumpDir>`，跑即可。
- 换 App 三件事：改 `WORK` 相关路径、`deviceJson` 的 `pkg`/`md5`、`assets` 随机名映射表里找新的 stamp 文件名。

## 3. 踩坑

| 坑 | 现象 | 处置 |
|---|---|---|
| 缺 JNI stub | `[JNI] unhandled method` 后 native 崩溃/返回 0 | 按日志补 `callObjectMethodV` 分支；本例只需 `getPackageName` |
| stamp 用了错文件 | `nativeOpenIecBundle` 返回 <=0 | stamp = `assets/<映射名>` 原文件字节，不是解密产物 |
| md5 不匹配 | 开包失败 | deviceJson.md5 = 目标 APK/iec 文件 MD5 |
| IOResolver 没命中 | `FileNotFound` | 所有模拟器路径按 basename 找 `files/`；别忘了放 bundle.iec |
| 忘记 JNI_OnLoad | 句柄全 0 | `dm.callJNI_OnLoad(emulator)` |
| OSS 更新包 | — | 同流程；`nativePeekStamp` 应返回与 APK 相同授权码 |
