---
name: kuaishou-tongkuang
description: Use when 快手同框/拍同款自动化（EasyClick/adb）. 实测链路+Intent情报+设备坑。
---

# 快手「一起拍同框」自动化 — 实测链路与 Intent 情报

> 交付物在 `E:\AI项目文件\抓取意图\`：`ks_sameframe_easyclick.js`（EasyClick 主脚本）、
> `ks_sameframe_adb.sh`（纯 adb 固化链路，端到端实测通过）、`hook_paired.js`（frida 抓 scheme）。
> 旧版 `ks_tongkuan.js` 含「拍同款+相册」链路细节。

## 实测链路（PDYM20 / Android11 / 1080x2400，2026-09 全链路端到端跑通）

1. `am start -a android.intent.action.VIEW -d "kwai://work/{photoId}"` → PhotoDetailActivity（导出 ✅，无需 root）
2. 点右侧「分享」(0.9167, 0.8075)。节点 desc=`分享{N}`（数字动态，用 descMatch("分享.*")）
3. 分享面板底部按钮行左滑 (0.83→0.18 @y=0.905) 320ms，露出「一起拍同框」
4. 点「一起拍同框」(0.5296, 0.8792) → SameFrameActivity。**坐标关键**：滑1次时按钮在 x=0.5296；滑2次后会滑到 x=0.5166 位置变成「一起看」，别点错（点了会进 RtcCallPhotoDetailActivity）
5. SameFrameActivity 特征节点：desc="拍摄按钮"(快门, 中心0.5009,0.855)、text="拍同框"、text="左屏"、text="魔法"
6. 快门→录N秒→再按快门停→自动进 OmniEditorActivity；「下一步」在右下 (0.7398, 0.9516)，**左边还有个「发瞬间」按钮别点错**
7. ShareActivity 发布页：`publish_button`「发布」(0.5, 0.9315)、文案框 `editor`(EditText)、"所有人可见"

## Intent 情报（frida + jadx + root 三重验证）

- **SameFrameActivity 未导出**，外部 am start 被 SecurityException 拒；且 onCreate 需要 intent 携带 VideoFeed 对象 + 本地缓存视频路径（缺一即 finish()）→ 外部 intent 永远直达不了，**必须走 UI**。
- **官方深链 `kwai://pairedPhoto?type=...&url=...`** → SchemeJumpPairedPhotoActivity（导出，adb 可拉）。参数：type=sameFrame|followShoot|lipsSync、url=ks://photo/{uid}/{photoId}/... 或 CDN 直链、magicFaceId、source、uimode 等（解析代码见 out_paired2 反编译）。url 数据拉取失败会静默降级到普通相机页（实测），故只作实验路径。
- SameFrameActivity 的真实启动参数（frida 抓自 UI 点击）：dat=`kwai://work/{photoId}`、flg=0x40000、extras 含 sourcePage=sameFrame、source_photo_action=1、magic_face_data_complete=true、PREV_URL=`ks://photo/...`、source_photo_origin_file=本地缓存 mp4。

## 设备与环境（PDYM20）

- root(Magisk)+Zygisk+LSPosed 环境；adb 路径 `C:\Users\19123\AndroidSDK\platform-tools`。
- **坑1：frida attach 快手疑似触发设备防御** → frida-server 自毁、随后全系统 `selinux_android_setcontext` 崩（所有 app 起不来）→ `adb reboot` 恢复（frida-server 不会自启）。抓 app 行为优先用 **logcat + uiautomator dump + 截图**，够用。
- **坑2**：分享面板底部横向 RecyclerView 里「一起拍同框」等按钮的 uiautomator bounds 常是 [0,0][0,0]（无障碍不可见）→ 节点只做特征探测，点击用实测坐标。
- **坑3**：同框页有录音权限需求；`text("允许")` 类弹窗清理函数要带着。
- jadx 单类反编译命令：`tools/jadx/bin/jadx -d out_x --single-class com.xx.YY --show-bad-code --no-res --no-imports apk/kuaishou.apk`（187MB APK，单类秒出）。

## 拍同款+相册上传链路（发布指定视频/DCIM 视频）— 实测

用途：发布手机里现成的视频（例：DCIM/xxx.mp4）。验收点：相册预览页「下一步」→编辑页→发布页封面均=所选视频。
前提：目标视频需为相册最新媒体 → push 后发媒体扫描广播：
`am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file:///sdcard/DCIM/xxx.mp4`
（或 EasyClick 用 utils.insertVideoToAlbum 插为新最新）

1. 详情页右上「拍同款」红标 (0.8648, 0.075) → CameraActivity（desc="拍摄按钮" 出现为准）
2. 相机页「视频」分类 (0.5, 0.7646) →「相册」按钮 (0.8065, 0.8988) → RecordAlbumActivity
3. 相册第一个格子 (0.1667, 0.2371) 点开 → 全屏视频预览页
4. 预览页「下一步」(0.8194, 0.9481) → OmniEditorActivity（编辑页，视频=所选 ✅）
5. 编辑页「下一步」(0.7398, 0.9516) → ShareActivity 发布页（封面=所选视频）
6. 「发布」(0.5, 0.9315)

细节：相册页特征 text="最近项目"/"多选"；此链路编辑页【不自动配乐】（同框链路才自动配乐）；
「拍同款」红标为自定义 View，uiautomator 抓不到，用坐标。

## 偷梁换柱玩法: 同框外壳 + 任意视频内容 (swap, 需 root) — 实测

原理: 同框录制页停止拍摄后, 实时合成品(360x320, 已含兔子+真人画面)落盘在
`/storage/emulated/0/Android/data/com.smile.gifmaker/files/.record_cache_dir/{毫秒时间戳}_0_0.mp4`。
点「下一步」时快手直接读取该文件 → 用目标视频覆盖它 → 编辑页/发布页全部变为目标视频内容。

关键时序(踩坑): 停止录制后文件还在写入(encoder flush), 必须等**大小连续两次不变且>10KB**再替换;
在 48 字节(未写完)时替换 → 快手继续写入造成文件损坏 → 发布页弹"视频制作失败"。

操作链: 录3秒 → 等写入完成 → `su cp 目标视频 覆盖`(cp 覆盖同inode, 权限/owner自动保留) → 点下一步 →
编辑页=目标视频 → 下一步 → 发布页封面=目标视频。备份: 原文件 cp 到 /sdcard/rec_swap_backup_<ts>.mp4。
注意: 实测节奏快慢不影响, 关键是文件必须完整; 替换后点下一步即可, 无需额外等待。

分享面板稳定进入法(解决滑动手感不稳): 点分享后 dump 等"一键分享至"出现;
**慢滑** 896→196 (900ms, 无惯性) → 「一起拍同框」稳定落 (744,2110)。
快滑(320ms)有 fling: 可能停 (572,2110) 也可能滑过头, 不稳定。

脚本: `ks_swap_publish.sh [目标视频] [photoId]` — 端到端实测通过(38秒, 到发布页停下)。
EasyClick 移植要点: shell.sudo() 执行 cp; file API 轮询文件大小; 其余 UI 步同主链路。

## 复现/验证命令

```bash
cd /e/AI项目文件/抓取意图 && bash ks_sameframe_adb.sh          # 端到端(录制12s,停在发布页)
```

EasyClick 脚本进手机：脚本文件导入 EasyClick 工程 → 运行环境(无障碍)开启 → 直接跑 `main()`。
换作品只改 `CFG.photoId`；换机型不用改坐标（比例制）。
