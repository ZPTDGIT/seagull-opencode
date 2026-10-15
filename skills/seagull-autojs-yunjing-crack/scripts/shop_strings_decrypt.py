#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AutoJS .shop 字符串表批量解密（云镜 Encrypt_YjV3 场景）

用法:
    python shop_strings_decrypt.py <main.shop> --key db248a05 e77ae5d6 1e446087 00000000
    python shop_strings_decrypt.py <main.shop> --key-file key.txt -o out.json

说明:
    - .shop 是 Java 序列化的 Rhino InterpretedFunction（需要 pip install javaobj-py3）
    - 密钥来自 unidbg harness 抓取的 encodeCore -> FKFK -> TotoTooo 派生结果（4 个 32bit word）
    - 解密算法 = 标准 XXTEA decrypt + 去尾 4 字节 LE 长度
    - 明文条目 = utf-8 文本；解析失败的原样保留
"""
import argparse
import base64
import json
import re
import struct
import sys

MASK = 0xFFFFFFFF
DELTA = 0x9E3779B9


def _mx(sum_, y, z, p, e, key):
    a = (((z >> 5) ^ ((y << 2) & MASK)) + ((y >> 3) ^ ((z << 4) & MASK))) & MASK
    b = ((sum_ ^ y) + (key[(p & 3) ^ e] ^ z)) & MASK
    return (a ^ b) & MASK


def xxtea_decrypt(v, key):
    n = len(v)
    if n < 2:
        return v[:]
    v = v[:]
    q = 6 + 52 // n
    sum_ = (q * DELTA) & MASK
    y = v[0]
    while True:
        e = (sum_ >> 2) & 3
        for p in range(n - 1, 0, -1):
            z = v[p - 1]
            v[p] = (v[p] - _mx(sum_, y, z, p, e, key)) & MASK
            y = v[p]
        z = v[n - 1]
        v[0] = (v[0] - _mx(sum_, y, z, 0, e, key)) & MASK
        y = v[0]
        sum_ = (sum_ - DELTA) & MASK
        q -= 1
        if q == 0:
            break
    return v


def decrypt_string(s, key):
    """返回 (明文, 是否解密成功)"""
    if not s or not re.fullmatch(r'[A-Za-z0-9+/=]+', s):
        return s, False
    try:
        raw = base64.b64decode(s)
    except Exception:
        return s, False
    if not raw or len(raw) % 4 != 0:
        return s, False
    words = list(struct.unpack('<%dI' % (len(raw) // 4), raw))
    dec = xxtea_decrypt(words, key)
    data = b''.join(struct.pack('<I', w) for w in dec)
    if len(data) >= 4:
        n = struct.unpack('<I', data[-4:])[0]
        if 0 <= n <= len(data) - 4:
            body = data[:n]
            for enc in ('utf-8', 'gbk'):
                try:
                    return body.decode(enc), True
                except Exception:
                    pass
    return s, False


def get(obj, name, default=None):
    try:
        v = getattr(obj, name)
    except Exception:
        return default
    if v is None:
        return None
    return getattr(v, 'value', v)


def parse_shop(path):
    import javaobj.v2 as javaobj
    with open(path, 'rb') as f:
        root = javaobj.load(f)
    return root.idata


def walk(idata, path, out, key, stats):
    table = get(idata, 'itsStringTable')
    if table:
        decoded = []
        for s in table:
            s = getattr(s, 'value', s)
            text, ok = decrypt_string(s, key)
            stats[0 if ok else 1] += 1
            decoded.append(text)
        out.append({'path': path, 'strings': decoded})
    nested = get(idata, 'itsNestedFunctions')
    if nested:
        for i, sub in enumerate(nested):
            walk(sub, '%s.%d' % (path, i), out, key, stats)


def main():
    ap = argparse.ArgumentParser(description='AutoJS .shop 字符串表解密')
    ap.add_argument('shop', help='main.shop 路径')
    ap.add_argument('--key', nargs=4, default=None, help='4 个 32bit word（hex，可带 0x）')
    ap.add_argument('--key-file', default=None, help='每行一个 hex word 的密钥文件')
    ap.add_argument('-o', '--output', default=None, help='输出 JSON（默认 <shop>.decrypted.json）')
    args = ap.parse_args()

    words = None
    if args.key:
        words = [int(x, 16) & MASK for x in args.key]
    elif args.key_file:
        words = []
        for line in open(args.key_file, encoding='utf-8'):
            line = line.strip()
            if line:
                words.append(int(line, 16) & MASK)
    if not words or len(words) != 4:
        print('需要 4 个 32bit 密钥 word（--key 或 --key-file）', file=sys.stderr)
        sys.exit(1)

    idata = parse_shop(args.shop)
    out, stats = [], [0, 0]
    walk(idata, 'root', out, words, stats)

    outp = args.output or (args.shop + '.decrypted.json')
    with open(outp, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    total = stats[0] + stats[1]
    print('函数数量: %d, 字符串: %d, 解密成功: %d, 保留原文: %d' % (len(out), total, stats[0], stats[1]))
    print('输出: %s' % outp)


if __name__ == '__main__':
    main()
