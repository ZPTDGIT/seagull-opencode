# AutoJS 接自建 MySQL + 试用期限（可直接粘贴）

来源：幸运定制实战最终版（`E:\AI项目\autojs\源码\幸运定制_源码_接数据库.js`），真机验证通过。
适用：AutoJS Pro 9 打包应用（Rhino 引擎，支持 ES6 let/箭头函数）。

## 1. 驱动准备（PC 侧，一次）

```powershell
# 1) 下载 MariaDB 驱动（不要用 MySQL Connector/J，安卓上资源包问题）
#    https://maven.aliyun.com/repository/public/org/mariadb/jdbc/mariadb-java-client/1.8.0/mariadb-java-client-1.8.0.jar
# 2) d8 转 dex（d8.bat 必须用 JDK8 跑）
$env:JAVA_HOME="<jdk8>"
& "<AndroidSDK>\build-tools\33.0.1\d8.bat" --release --min-api 21 `
  --lib "<AndroidSDK>\platforms\android-34\android.jar" `
  --output <outdir> mariadb-java-client-1.8.0.jar
# outdir\classes.dex 改名为 mariadb-java-client-1.8.0.dex
# 最终把 .dex 和 .jar 都放进 assets/project/（和 main.js 同目录）
```

## 2. 脚本核心代码（放在源码常量区）

```js
// ===================== 数据库配置（自建 MySQL） =====================
const DB_HOST = '36.140.99.150'
const DB_PORT = 3306
const DB_USER = 'ksjk'
const DB_PASS = 'ksjk'
const DB_NAME = 'ksjk'
const DB_CONFIG_TABLE = 'ksjk_config'      // 表结构: config_key(unique) / config_value / update_time

let __db_driver = null
let __db_driver_loaded = false
let __db_err_reported = false

function dbInit() {
    if (__db_driver_loaded) return
    let dexPath = files.join(files.cwd(), 'mariadb-java-client-1.8.0.dex')
    let jarPath = files.join(files.cwd(), 'mariadb-java-client-1.8.0.jar')
    if (files.exists(dexPath)) {
        runtime.loadDex(dexPath)            // 优先：预转 dex
    } else {
        runtime.loadJar(jarPath)            // 兜底：AutoJS 自动 jar→dex
    }
    // 不能用 DriverManager.getConnection（类加载器隔离会 No suitable driver）
    __db_driver = new Packages.org.mariadb.jdbc.Driver()
    __db_driver_loaded = true
}

function dbOpen() {
    dbInit()
    let url = 'jdbc:mariadb://' + DB_HOST + ':' + DB_PORT + '/' + DB_NAME +
        '?useUnicode=true&characterEncoding=utf8&useSSL=false'
    let props = new java.util.Properties()
    props.setProperty('user', DB_USER)
    props.setProperty('password', DB_PASS)
    return __db_driver.connect(url, props)
}

// 读取全部配置 -> { 控件id: 值 }（表键 = 控件id，一一对应）
function dbGetConfig() {
    let obj = {}
    let conn = null, st = null, rs = null
    try {
        conn = dbOpen()
        st = conn.createStatement()
        rs = st.executeQuery('SELECT config_key, config_value FROM ' + DB_CONFIG_TABLE)
        while (rs.next()) {
            let k = rs.getString('config_key')
            let v = rs.getString('config_value')
            if (v != null && v != '' && v != 'undefined') obj[k] = v
        }
    } catch (e) {
        console.error('读取数据库配置失败:', e)
        if (!__db_err_reported) {
            __db_err_reported = true
            try { ui.run(() => alert('数据库读取失败', '' + e)) } catch (e2) { }
        }
    } finally {
        try { if (rs) rs.close() } catch (e) { }
        try { if (st) st.close() } catch (e) { }
        try { if (conn) conn.close() } catch (e) { }
    }
    return obj
}

// 保存配置（有则更新无则插入）
function dbSaveConfig(obj, ids_input) {
    let conn = null, ps = null
    try {
        conn = dbOpen()
        ps = conn.prepareStatement(
            'INSERT INTO ' + DB_CONFIG_TABLE + '(config_key, config_value) VALUES(?, ?) ' +
            'ON DUPLICATE KEY UPDATE config_value = VALUES(config_value)')
        ids_input.forEach(item => {
            if (obj[item] === undefined) return
            ps.setString(1, item)
            ps.setString(2, obj[item] + '')
            ps.addBatch()
        })
        ps.executeBatch()
        return true
    } catch (e) {
        console.error('保存数据库配置失败:', e)
        try { ui.run(() => alert('数据库保存失败', '' + e)) } catch (e2) { }
        return false
    } finally {
        try { if (ps) ps.close() } catch (e) { }
        try { if (conn) conn.close() } catch (e) { }
    }
}

// 自检（建议挂到菜单“测试数据库”）
function dbSelfTest(ids_input) {
    let report = []
    try {
        report.push('cwd=' + files.cwd())
        report.push('dex存在=' + files.exists(files.join(files.cwd(), 'mariadb-java-client-1.8.0.dex')))
    } catch (e) { report.push('路径检查失败: ' + e) }
    try { dbInit(); report.push('驱动加载: OK') }
    catch (e) { report.push('驱动加载失败: ' + e); return report.join('\n') }
    let conn = null
    try { conn = dbOpen(); report.push('数据库连接: OK') }
    catch (e) { report.push('数据库连接失败: ' + e); return report.join('\n') }
    try {
        let st = conn.createStatement()
        let rs = st.executeQuery('SELECT COUNT(*) FROM ' + DB_CONFIG_TABLE)
        rs.next()
        report.push('读取配置表: OK, ' + rs.getInt(1) + ' 行')
        rs.close(); st.close()
    } catch (e) { report.push('读取配置表失败: ' + e) }
    try { conn.close() } catch (e) { }
    return report.join('\n')
}
```

## 3. UI 回填 / 采集（注意 RadioButton）

```js
// 启动回填（threads.start 里）
let obj = dbGetConfig()
setTimeout(() => {
    ids_input.forEach(item => {
        if (ui[item] && obj[item] != undefined) {
            let cls = ui[item].toString() + ''
            if (cls.indexOf('CheckBox') != -1 || cls.indexOf('RadioButton') != -1) {
                ui.run(() => ui[item].attr('checked', obj[item] + ""))
            } else if (cls.indexOf('JsEditText') != -1) {
                ui.run(() => ui[item].attr('text', obj[item]))
            }
        }
    })
}, 500)

// 采集（保存时）——同样别漏 RadioButton
let obj = {}
ids_input.forEach(item => {
    if (!ui[item]) return
    let cls = ui[item].toString() + ''
    if (cls.indexOf('CheckBox') != -1 || cls.indexOf('RadioButton') != -1) obj[item] = ui[item].checked
    else if (cls.indexOf('JsEditText') != -1) obj[item] = ui[item].text()
})
// threads.start(() => { if (dbSaveConfig(obj, ids_input)) alert('成功') })
```

## 4. 试用期限（放在 `'ui';` 之后、其余代码之前）

```js
// 到期时间：2026年10月4日 12:00:00（月份从0开始，9=10月）
const 脚本到期时间 = new Date(2026, 9, 4, 12, 0, 0).getTime();
if (Date.now() > 脚本到期时间) {
    dialogs.alert('提示', '本脚本已到期（有效期至 2026-10-04 12:00），无法继续使用。', '知道了').then(() => exit());
    throw new Error('脚本已到期');
}
setInterval(() => {
    if (Date.now() > 脚本到期时间) {
        toast('脚本已到期，已停止运行');
        exit();
    }
}, 60 * 1000);
```

## 5. 数据库侧（MySQL 5.7 实测）

```sql
CREATE TABLE ksjk_config (
  id INT(11) NOT NULL AUTO_INCREMENT PRIMARY KEY,
  config_key VARCHAR(100) NOT NULL UNIQUE,
  config_value TEXT,
  update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
-- config_key 直接用脚本 UI 控件 id：弹窗文字 / 弹幕话术 / 随机表情_min / ... / 横向 / 竖向
-- 布尔值存字符串 'true'/'false'；加载跳过 ''/'undefined'
```

导入厂商原配置（如果原脚本走云端）：直接抓 `get_xuanfuhanhua5` 返回的 `data`，字段名与源码参数同名，逐个 UPSERT 即可。

## 6. 常见坑

| 现象 | 原因 | 处理 |
|---|---|---|
| `No suitable driver found` | 走了 DriverManager，动态加载的驱动被类加载器过滤 | 用 `driver.connect(url, props)` |
| `ExceptionInInitializerError` at `com.mysql.jdbc.Messages` | Connector/J 的资源包被 dex 转换丢掉 | 换 MariaDB Connector/J 1.8.0 |
| `runtime.loadDex` 找不到文件 | `files.cwd()` 与想象不同 | 用 `files.exists()` 打印确认；jar 兜底 `runtime.loadJar` |
| 改了脚本但界面没变 | AutoJS 首次运行解包后缓存 | 卸载重装或 `adb shell pm clear <pkg>` |
| 保存成功但 update_time 没变 | `ON DUPLICATE KEY UPDATE` 值没变化时不触发行更新 | 正常现象 |
| 单选按钮存不上 | 原采集逻辑只认 CheckBox/JsEditText | cls 判断加 `RadioButton` |
