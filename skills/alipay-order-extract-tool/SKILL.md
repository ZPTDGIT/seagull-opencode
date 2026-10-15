---
name: alipay-order-extract-tool
description: Use when working on 支付宝订单提取工具 (E:/AI项目/提取信息).
---

# 支付宝订单信息提取工具 (E:\AI项目\提取信息)

## 是什么
Tkinter GUI + DrissionPage(CDP 9222) + openpyxl：在 b.alipay.com 买家订单页按「支付宝交易号」查询 → 点详情开新标签 → 按域名分流解析物流信息(淘宝/天猫/1688/归档页/支付宝页) → 写回 Excel。支持断点续跑(SKIP_FILLED + 交易自动关闭列)与秒级停止。

## 文件
- `app.py` 主程序(逻辑全在这)；`xlsx_repair.py` 残表体检/修复；`fix_xlsx.py` 独立命令行修复(历史产物)
- 重打包：`py -3.14 -m PyInstaller --noconfirm --onefile --windowed --name "支付宝订单信息提取工具" --collect-all DrissionPage app.py` → 把 dist/*.exe 拷到桌面。打包后验证：CArchiveReader 列 TOC 查模块 + Popen 启动十几秒查存活。
- 源码没变时 PyInstaller 走缓存会跳过 EXE 重建(产物 mtime 不变)；要全新构建：先删 dist/*.exe 再加 `--clean`。
- **启动测试必须树杀**：`taskkill /F /T /PID <pid>`。onefile 子进程会残留并锁住 dist 的 exe，下次打包直接失败（或被缓存跳过）；杀完再 Get-Process 查一遍残留。

## 环境
- 项目操作一律 `py -3.14`(3.14 带 DrissionPage 4.1.1.4 / openpyxl 3.1.5 / pyinstaller)。Hermes 终端里的 `python` 是 hermes venv(3.11，无依赖)，别用它跑项目。
- GUI 需本机 Chrome；调试端口 9222，user-data-dir=%LOCALAPPDATA%\Google\Chrome\DebugProfile(登录态在这里)。
- 表格源：微信下载 E:\下载文件\微信\xwechat_files\...\msg\file\<月>\，工作副本一般在 C:\Users\19123\Desktop\。

## 关键坑：残缺 xlsx(换电脑/传输后高频)
- 症状：`读取表格失败: There is no item named '[Content_Types].xml' in the archive`。文件被第三方重打包丢了 [Content_Types].xml / workbook.xml / rels / styles.xml 等标准部件，openpyxl 拒读。
- 修复：`xlsx_repair.check/repair` — openpyxl 模板打底补全部件、清理丢图 drawing 引用、.bak 备份、**先写临时文件校验，通过才替换原文件**。app.py `_prepare_table` 在「开始运行」时自动调用；.xls(OLE2)/坏 zip 给中文明确报错。
- **openpyxl 靠 [Content_Types].xml 清单定位 sharedStrings**：重建 Content_Types 时必须给实际存在的 `xl/sharedStrings.xml` 补 Override，否则共享字符串读不出来 → `IndexError: list index out of range`。
- sheet 名从 docProps/app.xml 的 `<TitlesOfParts>` 块恢复；HeadingPairs 里也有 `<vt:lpstr>`，**必须只在 TitlesOfParts 内匹配**。
- 文件类判别：`PK`=xlsx zip；`D0CF11E0`=老 .xls(OLE2，修不了，提示另存 .xlsx)。

## 测试套路
- 样本：桌面 *.xlsx/.bak + 微信原件目录。残表复刻：copy 一份改后缀 .xlsx 再测。
- E2E 不走 GUI 点击：真 `App().withdraw()` 后直接调 `_prepare_table` / `_ensure_headers` / `_read_trade_rows`，再模拟写回+保存+重读。
- 合成 WPS 血统残表：从完好 WPS 文件里剔除 5 个标准部件重打包，可同时测 sharedStrings 与 sheet 名恢复。
