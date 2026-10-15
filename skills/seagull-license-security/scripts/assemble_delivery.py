# -*- coding: utf-8 -*-
"""
交付组装脚本: 文件夹包 + payload.zip + 单文件 SFX
前置:
  1. dist/破解启动器.exe        (PyInstaller 构建)
  2. work/stub.exe             (csc 编译 sfx_stub.cs)
  3. 原始目标目录 (SRC_APP)
输出:
  交付/<PKG_NAME>/             文件夹直达版(含启动器+目标+数据+说明)
  交付/<PKG_NAME>.zip          payload zip (= SFX 内嵌数据)
  交付/<PKG_NAME>_单文件.exe    [stub][marker][zip][len][magic]
结构:
  [stub.exe][b'<<<APP-PKG-V1>>>'][payload.zip][struct '<q' len][b'TKPROEND']
"""
import os
import shutil
import struct
import zipfile

# ---------------- CONFIG ----------------
ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_APP = os.path.join(ROOT, 'TKPro_extracted', 'TKPro')    # 原始目标目录
LAUNCHER = os.path.join(ROOT, 'dist', '破解启动器.exe')      # PyInstaller 产物
STUB = os.path.join(ROOT, 'work', 'stub.exe')               # csc 产物
OUT = os.path.join(ROOT, '交付')
PKG_NAME = 'TKPro破解版'
PKG = os.path.join(OUT, PKG_NAME)
PAYLOAD_ZIP = os.path.join(ROOT, 'work', 'payload.zip')
SINGLE = os.path.join(OUT, PKG_NAME + '_单文件.exe')
MARKER = b'<<<APP-PKG-V1>>>'          # 必须与 sfx_stub.cs 的 MARK 一致
MAGIC = b'TKPROEND'                   # 必须与 sfx_stub.cs 的 _end 一致
APP_FILES = [                         # 从 SRC_APP 拷哪些文件 (数据/状态)
    'TKPro采集器.exe',
    'account.json',
    'archive.db',
    'collector.db',
    'collector.db-shm',
    'enrich.db',
    'enrich.db-shm',
    'monitor.db',
    'monitor.db-shm',
]
DATA_DIRS = ['datas']                 # 整目录拷贝清单
README = '使用说明.txt'
README_TEXT = '''双击「破解启动器.exe」启动即可。
每次都用启动器进入；直接点原版 exe 会弹卡密框。
安全软件报毒请把本文件夹加白名单（frida 注入组件误报高发）。
'''
# ----------------------------------------


def copy_tree():
    if os.path.exists(PKG):
        shutil.rmtree(PKG)
    os.makedirs(PKG)
    for name in APP_FILES:
        s = os.path.join(SRC_APP, name)
        if os.path.isfile(s):
            shutil.copy2(s, os.path.join(PKG, name))
        else:
            print('[!] missing: %s' % name)
    for d in DATA_DIRS:
        s = os.path.join(SRC_APP, d)
        if os.path.isdir(s):
            shutil.copytree(s, os.path.join(PKG, d))
    shutil.copy2(LAUNCHER, os.path.join(PKG, '破解启动器.exe'))
    with open(os.path.join(PKG, README), 'w', encoding='utf-8') as f:
        f.write(README_TEXT)
    total = sum(os.path.getsize(os.path.join(b, f)) for b, _, fs in os.walk(PKG) for f in fs)
    print('[+] package folder: %s (%.1f MB)' % (PKG, total / 1048576.0))


def make_zip():
    if os.path.exists(PAYLOAD_ZIP):
        os.remove(PAYLOAD_ZIP)
    with zipfile.ZipFile(PAYLOAD_ZIP, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for base, dirs, files in os.walk(PKG):
            for f in files:
                full = os.path.join(base, f)
                z.write(full, os.path.relpath(full, PKG))
    print('[+] payload zip: %.1f MB' % (os.path.getsize(PAYLOAD_ZIP) / 1048576.0))


def make_single():
    if not os.path.isfile(STUB):
        print('[-] stub.exe not built')
        return
    with open(STUB, 'rb') as f:
        stub = f.read()
    with open(PAYLOAD_ZIP, 'rb') as f:
        payload = f.read()
    with open(SINGLE, 'wb') as f:
        f.write(stub)
        f.write(MARKER)
        f.write(payload)
        f.write(struct.pack('<q', len(payload)))
        f.write(MAGIC)
    print('[+] single exe: %s (%.1f MB)' % (SINGLE, os.path.getsize(SINGLE) / 1048576.0))


def verify_single():
    with open(SINGLE, 'rb') as f:
        f.seek(-16, os.SEEK_END)
        tail = f.read(16)
        ln = struct.unpack('<q', tail[:8])[0]
        assert tail[8:] == MAGIC, 'trailer broken'
        f.seek(-16 - ln - len(MARKER), os.SEEK_END)
        assert f.read(len(MARKER)) == MARKER, 'marker broken'
        f.seek(-16 - ln, os.SEEK_END)
        assert f.read(4) == b'PK\x03\x04', 'zip head broken'
    print('[+] single exe verified: payload=%.1f MB' % (ln / 1048576.0))


if __name__ == '__main__':
    copy_tree()
    make_zip()
    make_single()
    if os.path.isfile(SINGLE):
        verify_single()
