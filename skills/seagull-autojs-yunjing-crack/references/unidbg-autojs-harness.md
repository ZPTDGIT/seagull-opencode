# unidbg AutoJS/云镜 harness 搭建与踩坑（实战记录）

战例产物：`E:\AI项目\autojs\harness\`（Main.java / MyJni.java / NativeHelper.java / MutString.java + 编译运行脚本）。
目标：在 PC 上跑云镜的 Android arm64 native 库，拿到 `.shop` 字符串解密所需的 XXTEA 密钥，并追踪 `deserializeAndExec` 的真实解密链。

## 1. 环境搭建

```powershell
# 1) 下载 unidbg（国内用 ghproxy 镜像）
#    https://ghproxy.net/https://github.com/zhkl0228/unidbg/archive/refs/heads/master.zip
# 2) 必须 JDK8 编译（JDK17 会因 java.lang.Module 冲突失败）
$env:JAVA_HOME = "E:\path\to\jdk8"
cd unidbg-master
.\mvnw.cmd package "-Dmaven.test.skip=true"     # 全部模块
# 3) 运行时 classpath 需要：
#    unidbg-android.jar + unidbg-api.jar + backend/unicorn2/target/*.jar
#    + .m2 里的 unicorn-1.0.15 / capstone / keystone / demumble / jna / slf4j
#    + org.scijava:native-lib-loader（不加载它 unicorn 初始化直接 ClassNotFound）
```

JDK8 单独下载：`https://ghproxy.net/https://github.com/adoptium/temurin8-binaries/releases/download/jdk8u504-b01/OpenJDK8U-jdk_x64_windows_hotspot_8u504b01.zip`

## 2. 模拟器骨架（Handler 池）

核心难点：unidbg 的 `AbstractEmulator.emulate` **同一实例不允许嵌套执行**（报 `IllegalStateException: running`）。
而云镜 native 内部通过 JNI 回调（`CallStaticObjectMethodA`）调其它 native → 需要用**另一个 emulator 实例**顶上。
做成 Handler 池（`NativeHelper.java`）：

```java
static class Handler {
    AndroidEmulator emu; VM vm; DvmClass enc; DvmClass protect; boolean busy;
    void init() {
        emu = AndroidEmulatorBuilder.for64Bit().setProcessName("com.xydz.helper"+n).build();
        emu.getMemory().setLibraryResolver(new AndroidResolver(23));
        vm = emu.createDalvikVM();
        vm.setJni(new MyJni());
        for (String l : new String[]{"libc++_shared.so","libyj-vmp-lib.so","libyj_aj_02_309.so",
                "libyj_aj_01_309.so","libyj-aj-shop-encrypt.so"}) {
            DalvikModule dm = vm.loadLibrary(new File(LIB, l), true);
            dm.callJNI_OnLoad(emu);
        }
        vm.resolveClass("yj_dcc_loader_aj/NativeUtil").callStaticJniMethod(emu, "classesInit0(I)V", 0);
        loader.callStaticJniMethod(emu, "registerNativesForClass(ILjava/lang/Class;)V", i, cls);  // 0..5
        hidden.callStaticJniMethod(emu, "special_clinit_"+idx+"(Ljava/lang/Class;)V", cls);        // 0..5
        enc = vm.resolveClass("org/mozilla/javascript/Encrypt_YjV3");
        protect = vm.resolveClass("org/mozilla/javascript/Encrypt_YjV3$Protect");
    }
}
// acquire(): 拿空闲 handler，没有就新建；转发调用都从这里走
```

注册结果用反射读 `DvmClass.nativesMap`，拿到函数指针：

```
Encrypt_YjV3: DDdd/TotoTooo/FKFK/DdDdDdd/IiiII/toByteArray/enenenie/ddddd/addInt/RrRr/lLLlLl
Protect:      XXXX / iiIii / IiiiI / Iiiii / IIIii ...（必须实现 String.intern 才会注册成功）
```

## 3. MyJni 必须实现的 JNI stub（按踩坑顺序）

| 签名 | 行为 |
|---|---|
| `android/util/Base64->decode(Ljava/lang/String;I)[B` | 标准 base64 解码 |
| `java/lang/String->intern()Ljava/lang/String;` | **返回自身**（不实现它 registerNativesForClass 会中途抛异常静默失败） |
| `java/lang/String->getBytes()[B` | UTF-8 |
| `java/lang/Math->min/max(II)I` | 直通 |
| `java/lang/System->arraycopy(...)V` | 支持 byte/int/short/float/double |
| `java/lang/System->loadLibrary(...)V` | no-op |
| `java/io/*->allocObject` / `<init>` / `close()V` / `readObject()Ljava/lang/Object;` | `readObject` 返回预构建的 InterpretedFunction 代理（见下） |
| `java/util/HashSet/HashMap->allocObject` | `dvmClass.newObject(new HashSet/HashMap<>())` |
| `java/lang/String-><init>([B...)`（含 charset 参数） | 正确按 charset 解码 |
| `java/nio/charset/StandardCharsets->UTF_8` 静态字段 | 返回 Charset 对象 |
| `Encrypt_YjV3->TotoTooo/DdDdDdd/FKFK/toByteArray/...` | 转发 Handler 池（**TotoTooo 可在 Java 侧复刻**：LE 打包 + flag 追加长度 word） |
| `Encrypt_YjV3$Protect->XXXX(IIIII)I` | 转发（XXTEA 的 mx 就是它） |

### 静态字段跨实例共享
密钥表是 native 写进 Java 静态字段的（`Icode.ok1..ok6/initCode`、`Protect.tag`）。不同 Handler 的 VM 不共享 → MyJni 里做**全局 `STATIC_FIELDS` map** + `cloneForVm()`（IntArray/ByteArray/StringObject/ArrayObject 克隆到当前 VM 再返回，否则 jobject 句柄跨 VM 无效）。

### 对象代理（调 `deserializeAndExec` / `RrRr` 用）
- 用 fastjson 把 `.shop` 的 JSON 结构解析成 `Map`，`vm.resolveClass("org/mozilla/javascript/InterpreterData").newObject(map)` 造代理对象；字段读写走 `getObjectField/setObjectField/getIntField/setIntField` 的 Map 分支，按 `class->field:type` 签名解析。
- `getObjectField` 里按 type 包装：`[I→IntArray`、`[Ljava/lang/String;→ArrayObject(StringObject[])`、嵌套 Map→递归代理（IdentityHashMap 缓存保证同对象身份）。
- 要抓 `readObject` 时：`java/io/ObjectInputStream->readObject()Ljava/lang/Object;` 返回 `vm.resolveClass("org/mozilla/javascript/InterpretedFunction").newObject({idata: <idataMap>})`，即可继续观察 native 后续动作。

## 4. 关键发现：密钥派生链

```
deserializeAndExec(null ctx, null scope, "/path/main.shop")
 ├─ Protect.operate(ctx, scope)                    → stub no-op
 ├─ new FileInputStream(path) / ObjectInputStream → stub，readObject 返回代理
 ├─ getObjectField(InterpretedFunction -> idata)
 ├─ getObjectField(InterpreterData -> encodeCore)   → "2b33c5d075a4"
 ├─ String.getBytes()
 ├─ -$$Nest$smFKFK([B)[B                            → 16 字节 05 8a 24 db d6 e5 7a e7 87 60 44 1e 00 00 00 00
 └─ -$$Nest$smTotoTooo([B Z)[I                       → key = [0xdb248a05, 0xe77ae5d6, 0x1e446087, 0x00000000]
```

拿到 key 后不需要再跑 native：`scripts/shop_strings_decrypt.py` 直接批量解。

## 5. unidbg 源码补丁（master 0.9.10 实测）

`unidbg-android/.../DalvikVM64.java` 的 `_GetIntArrayRegion` / `_GetLongArrayRegion` / `_GetFloatArrayRegion` 都是 `throw new UnsupportedOperationException()`；
XXTEA 的 mx 要读 key 数组 → 照 `_GetShortArrayRegion` 的写法补实现（`IntArray.value` + `Arrays.copyOfRange` + `buf.write`）。
注意 0.9.10 没有 `LongArray` 类，long 分支保持 stub；Int/Float 可用。

## 6. 排错速查

| 现象 | 原因/处理 |
|---|---|
| `find method failed: classesInit0(I)V` | 没调对应库的 JNI_OnLoad（`vm.loadLibrary(file,true)` 后还要 `dm.callJNI_OnLoad(emu)`） |
| registerNatives 后 nativesMap 仍为空 | 缺 `String.intern()` stub |
| `IllegalStateException: running` | 嵌套调用同一 emulator → Handler 池换实例 |
| `find method failed: XXXX` | XXXX 注册在 `registerNativesForClass(4, Protect.class)`，要先调它 |
| ok 表为空 / key 全 0 | Handler 顺序：classesInit0 → registerNativesForClass(0..5) → special_clinit_*_* 都要跑 |
| `backend Break at svc` 大段寄存器 dump | 正常调试输出，看上文最近的 `UnsupportedOperationException` 即可 |
| `ConcurrentModificationException` | 前一个 JNI stub 抛异常导致中断，修好 stub 自动消失 |
