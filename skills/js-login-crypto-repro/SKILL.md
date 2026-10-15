---
name: js-login-crypto-repro
description: Reproduce JS login encryption (password/sign) in Python.
---

# JS 登录加密逆向复现 (Python)

目标: 找到网站登录接口的加密位置, 用 Python 等价复现, 并做双向验证。

## 流程

1. 浏览器打开真实登录页(注意: 登录框可能在独立域名 iframe, 如 ptlogin.*), 枚举:
   - 所有 script src + 内联脚本; 表单 inputs(特别注意: 可见密码框无 name + 隐藏域同名, 说明真实值会经 JS 处理后写入隐藏域)
   - 隐藏配置域(如 sec/sign 开关)控制是否加密传输
2. 下载 JS 用 curl (browser 的 js() helper 没有 await_promise, fetch 拿不到完整文本)。带上 UA 和 Referer。
3. grep 定位: `encrypt|password|sign|CryptoJS|RSA` + 隐藏域 id/name。触发点在 submit 校验函数里, 形如 `x == 1 ? encryptAES(v) : v`。
4. 识别 CryptoJS 用法(三种常见形态):
   - `AES.encrypt(msg, 'passphrase')` → OpenSSL 兼容格式 (见下)
   - `AES.encrypt(msg, key, {iv: iv, mode: CBC})` → 原生 key/iv 直接实现
   - `JSEncrypt/setPublicKey` → RSA, 用 pycryptodome PKCS1_v1_5
5. Python 复现 CryptoJS passphrase 模式 = OpenSSL 格式:
   - 随机 8 字节 salt; EVP_BytesToKey(MD5, 1 轮) 派生 key(32B)+iv(16B)
   - AES-256-CBC + PKCS7, 输出 base64(b"Salted__" + salt + ct), 前缀恒为 `U2FsdGVkX1`
   - 模板见 references/cryptojs_passphrase.py
6. 验证必须双向(单向只能证明一半):
   - a. 浏览器控制台实调原版加密函数取样本 → Python 解密 = 明文
   - b. Python 加密 → 浏览器 CryptoJS.AES.decrypt(py_ct, passphrase).toString(Utf8) = 明文
   - c. E2E: 不存在账号 POST 登录接口, 服务端返回业务错误(如“用户不存在/密码错误”)而非格式错误 = 请求管线通。只发一次, 不要用真实账号。
7. 交付脚本含 encrypt/decrypt/login 三模式 + 自检子命令。

## 坑
- CryptoJS passphrase 模式的 IV 由 salt 派生, 没有独立随机 IV, 别手写错。
- JS 端明文按 UTF-8 编码, Python 侧要 `.encode('utf-8')`。
- 登录字段值全部照抄真实表单(读 DOM 里每个隐藏域的 value), 别只凭抓包猜。
- 加密前的值可能还要过一遍校验正则(JS 拦得住的不代表服务端也拦)。
- Windows: curl 是 MSYS 版可用; 但传给原生程序(venv 的 python)的路径用 C:/forward/slash 形式。
- 隔离环境: `uv venv .venv && uv pip install pycryptodome requests`, 用 .venv/Scripts/python.exe 跑。

## 案例
4399 登录: validation.js `encryptAES = CryptoJS.AES.encrypt(IdVal, 'lzYW5qaXVua').toString()`, sec==1 时密文写入隐藏域 password 提交 login.do。Python 复现一次通过, 双向验证 + 假账号 E2E 均通过。

抖音 (login.douyin.com/passport/web/*, SDK 3.4.4, 2026-09 验证):
- 接口 `POST https://login.douyin.com/passport/web/user/login/` (密码登录); 同类 sms_login/check_qrconnect/get_qrcode。
- 字段加密极简: `encrypt = ''.join(format(b^5,'x') for b in utf8(v))` — 注意 JS `.toString(16)` **不补前导零**, Python 用 `format(b^5,'x')` 而非 `:02x`; encryptParams 附加 `mix_mode=1&fixed_mix_mode=1`。
- 签名 header `x-tt-passport-aid-sign` = `HMAC(key=HKDF(ts, appKey), msg=f'aid=&path=&ts=')`; `ts`=**当天UTC正午**秒级(一天内稳定); HKDF 实为 `HMAC(key=HEX2B(HMAC(key=utf8(ts), msg=utf8(appKey))), msg=b'\x01')`; appKey 硬编码在前端 chunk (`client-entry*.js`), aid=6383 时为 `163e7ce78d58971a41f5b969996d85c2`。
- 风控: 提交先弹滑块 (verifycenter), 通过后才发登录请求; 裸请求(Python无cookie) → error_code 4031, 浏览器内同结构请求 → 业务响应(如 7=太频繁)。协议层与风控层要分开判定。
- 关键技巧: ①`webpackChunk*` push`[[rand],{},r=>req=r]` 取 webpack require, 再按模块号调真加密函数取证; ②hook `setRequestHeader` 抓 SDK 真实请求头; ③懒加载 chunk URL = runtime 里 `{id:"hash"}` 映射拼 `<publicPath>/async/<id>.<hash>.js` (404 时先试加 `async/`)。
