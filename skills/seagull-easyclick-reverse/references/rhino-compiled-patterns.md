# Rhino 优化编译类 → JS 模式映射（rhino2js 依据）

EasyClick 用 Rhino 定制版把 JS 编译成 JVM 类。每个脚本一个类，类里按 `_id` 分发函数。
以下是全部已实测惯用法；`scripts/rhino2js.py` 已实现这些规则。**改转译器先看本表**。

## 1. 类结构

| 成员 | 语义 | 转译规则 |
|---|---|---|
| `call()` switch | `case _id → 方法(...)` | `_id`→方法名映射；方法名正则必须覆盖：`m\d+_c__\d+`、`m\d+_c_[^_]+_\d+`（带名字直调，曾漏 18 个函数）、`_c_名字_id`、`_c_script_0`（顶层脚本） |
| `getFunctionName()` | `case _id → "函数名"` | 中文原样；`""`=匿名 → `__fn<id>`；**空 case 继承后续 return（fallthrough）** |
| `getParamOrVarName(i)` | 每 `_id` 嵌套 switch → 名字 | 参数/变量原名（中文保留） |
| `getParamCount()` | 参数个数 | fallthrough：`case 2/3/4/5: default: return 0` 这种分组要继承 |
| `_reInit()` | `_reN_M = checkRegExpProxy(ctx).compileRegExp(ctx, pat, flags)` | 嵌套在 selectors 里，取两个字面量参数；输出 `var _reN_M = new RegExp('pat','flags')` |
| 静态字段 `_kN` | 数字常量池 | `var _kN = 值` 输出在文件头 |
| 源码标记 `"(js/x.js#N)"` | callName 数组首元素 | 过滤掉 |

## 2. 调用约定（参数槽）

优化方法签名：`(脚本类 var, Context, Scriptable scope, Scriptable thisObj, Object obj, double d, Object[] objArr)`
或 `(..., Object[] objArr)`（无 obj/d 槽）。

- `obj` = 第 0 个实参（对象时）；`d` = 第 0 个实参（数字时）。
- `objArr` = 第 1 个及之后的实参（obj/d 风格），或第 0 个起（纯 objArr 风格）。
- `padArguments(objArr, n)` 补齐 → 跳过整块。
- `if (obj == Undefined) obj = wrapDouble(d)` → 跳过（调用约定，不是源码）。
- `Object objX = objArr[K]` → 声明跳过，`objX` 重命名为第 K 个参数名。
- `scriptable2` → `this`（thisObj）。
- `lastStoredScriptable(ctx)` → `this`。

## 3. 链接器映射（invoke 层）

| 编译调用 | JS |
|---|---|
| `NameLinker.name_getName(scope, cx, "x")` | `x` |
| `name_getNameFunctionAndThis(...) + instanceof + _id==N` 直调块 | `函数名(args)`（含带名字方法 `mNN_c_名字_id`） |
| `name_bind(scope, cx, "x")` | `BIND:x`（供 name_setName 解出 `x = v`） |
| `name_setName(name_bind(...), v, ..., "x")` / `name_setConst` | `x = v` |
| `nameIncrDecr(scope, "x", cx, 2)` | `x++`（2=增量，其他=减量） |
| `PropLinker.prop_getObjectProp(o,…, "n")` | `o.n` |
| `prop_getObjectElem(o, k)` / `prop_setObjectElem(o, k, v)` | `o[k]` / `o[k] = v` |
| `prop_getPropFunctionAndThis(o, …, "f")` + `OptRuntime.callN(…)` | `o.f(args)` |
| `propIncrDecr(o, "n", …, code)` | `o.n++`/`o.n--` |
| `MathLinker.math_add(a,b)` | `(a + b)` |
| `math_TONUMBER/math_TONUMERIC(x)` | `Number(x)` |
| `math_TOBOOLEAN(x)` | `(!!(x))` |
| `math_shallowEq / math_compare_lt/gt/le/ge` | `===` / `< > <= >=` |
| `ScriptRuntime.multiply/subtract` | `a * b` / `a - b` |
| `OptRuntime.wrapDouble(x)` | `x`（独立语句直接删） |
| `OptRuntime.add(a,b)` | `(a + b)` |
| `OptRuntime.call0/1/2/N(fn, thisObj?, args…, cx, scope)` | `fn(args)`（fn 为 `name_getNameFunctionAndThis` 时取名字直呼） |
| `OptRuntime.callName({args}, "name", …)` / `callName0` | `name(args)` / `name()` |
| `OptRuntime.callProp0..N(o, "n", …)` | `o.n(args)` |
| `OptRuntime.newObject(cls…, args)` | `new Cls(args)`；args 为 `emptyArgs`/`objArr2` → `()` |
| `OptRuntime.newArrayLiteral(...)` / `bindThis` / `initFunction` | `[…]` / `fn.bind(this)` / 删除 |
| `ScriptRuntime.zeroObj/oneObj/minusOneObj` | `0` / `1` / `-1` |
| `ScriptRuntime.emptyArgs` | `[]` |
| `ScriptRuntime.fillObjectLiteral(obj, keys[], vals[], …)` | `obj = { k: v, … }`（键非合法标识符才加引号，中文算合法） |
| `ScriptRuntime.enterWith(obj,…)` + `try { … } leaveWith` | `with (obj) { … }`；无 try 配套则直接丢声明 |
| `ScriptRuntime.createFunctionActivation/enterActivationFunction/exitActivationFunction/initScript/checkRegExpProxy/padArguments` | 全部丢弃（含 `x = leaveWith(...)`、独立 `leaveWith/enterWith` 语句） |
| `ScriptRuntime.newCatchScope(e, null, "e", …)` | `catch (e)`（多异常类型的重复 catch 只取第一个） |
| `ScriptRuntime.enumInit/`enumNext`/`enumId` | `for (var k in obj) { … }` |
| `context.newObject(scope)` | `{}` |

## 4. 结构惯用法

- **函数引用**：`new 脚本类(scope, cx, id)` → `funcnames[id]` 或 `__fnN`。
  启发式必须收紧：`len(args)==3 且 args[1] 非字面量`（否则 `new JavaScriptException(v,"js/x.js",行号)` 会被误伤）。
- **throw**：`throw new JavaScriptException(value, "js/x.js", line)` → `throw value;`（`EcmaError`/`EvaluatorException` 同理）。
- **instanceof**：`x instanceof 类` → 渲染类型名（javalang 给的是 Type 节点，别落 TODO）。
- **for 循环 init**：javalang 对 `for (double d=0;…)` 会解析成 tuple 碎片列表 → 扁平化后从 VariableDeclaration/VariableDeclarator/Literal 拼回。
- **do-while**：输出 `} while (cond);` 时 `ind` 是缩进、`}` 由格式串带，别双写。
- **自赋值** `a = a;`：跳过。
- **独立空数组** `[];`、裸 `wrapDouble`：跳过。
- **死代码允许保留**：`objArrN[i]=…`（对象字面量构建中间语句）、`qur;` 之类不影响运行；可后续清理。

## 5. 已知的"表示风格差异"（不是 bug，比对时别误报）

| 源码写法 | 转译输出 | 说明 |
|---|---|---|
| `{"x": 1}` | `{ x: 1 }` | 键引号风格，等价 |
| 字符串里的原始 NUL/控制字符 | `'\u0000'` / `'\u0012'` | 转义风格，值等价 |
| `/[^\d]/g` 正则字面量 | `new RegExp('[^\\d]','g')` | 等价（避免字面量转义 bug 的刻意选择） |
| 模板字符串 `` `a${x}b` `` | `'a' + x + 'b'` | 拆分，等价 |
| 内联匿名回调 | 独立 `function __fnN` + 引用 | 编译产物本来就拆类，等价 |
| `0xff000000` | `4278190080` | 进制风格，等价 |
| `"..."` 里的 `'` | `\'` | 转义风格，等价 |

## 6. 验证闭环（改动转译器后必跑）

1. `python rhino2js.py <jadx目录> <输出目录> <类名...>`
2. 全部产物 `node --check`
3. 有 IDE 工程时跑 `compare_js.py`：命名函数覆盖必须 100%，函数级字符串差异应只剩第 5 节类别
4. 抽查关键模式：`grep "TODO|BIND:|__fn.*(" 找误引用；`grep "throw "` 确认抛的是值不是函数

## 7. 实战 bug 史（防止回退）

| 日期 | bug | 修复 |
|---|---|---|
| 2026-10 | `mNN_c_名字_id` 未匹配 → yidao 漏 18 函数 | 方法名正则放宽 |
| 2026-10 | `throw JavaScriptException` → `throw __fnN` | 类型特判解包 + 启发式收紧 |
| 2026-10 | `instanceof` → `/*TODO:ReferenceType*/` 语法错误 | 渲染类型名 |
| 2026-10 | `getParamCount` fallthrough 丢参 → 64 泡沫参数 | pending 继承 |
| 2026-10 | DoStatement 双 `}}` | 格式串修 |
| 2026-10 | 正则字面量转义 `\/` 炸语法 | 改 `new RegExp(字符串)` |
| 2026-10 | `objArr[0]` 选择器被忽略（jadx 挂在 MemberReference.selectors） | selectors 递归渲染 |
