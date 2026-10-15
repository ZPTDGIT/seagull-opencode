"""
EasyClick IEC Package Decryptor (Pure Java Layer)
一键解密 EasyClick 打包 APK 中不含 libecvault.so 的 IEC 加密包。

用法:
    python decrypt_iec.py --apk target.apk --output ./extracted
    python decrypt_iec.py --mod xxxmod.bin --output ./extracted  # 已提取的 xxxmod 文件

流程: APK → properties 定位 → classpath/assets 提取 → JAR壳剥离 → IEC 解析 → XOR 解密
"""
import sys, struct, os, hashlib, zlib, argparse, io
sys.stdout.reconfigure(encoding='utf-8', errors='replace')


# ─── 基础工具 ───

def read_bytes(data, pos, n):
    return data[pos:pos+n], pos+n

def read_le_uint32(data, pos):
    return struct.unpack_from('<I', data, pos)[0], pos+4

def xor_decrypt(data_bytes, key_bytes):
    result = bytearray(data_bytes)
    klen = len(key_bytes)
    for i in range(len(result)):
        result[i] ^= key_bytes[i % klen]
    return bytes(result)

def crc2_check(data_bytes):
    """CRC-16 校验 (poly=0xA001, init=0xFFFF), 对应 C8o80o.m4946lll"""
    crc = 0xFFFF
    for b in data_bytes:
        crc = ((crc & 0xFF) ^ (b & 0xFF)) | (0xFF00 & crc)
        for _ in range(8):
            flag = crc & 1
            crc >>= 1
            if flag > 0:
                crc ^= 0xA001
    return struct.pack('<H', crc & 0xFFFF)

def md5hex(data_bytes):
    return hashlib.md5(data_bytes).hexdigest()

def hex_decode_str(hex_str):
    """Hex 字符串 → UTF-8 字符串"""
    try:
        return bytes.fromhex(hex_str).decode('utf-8')
    except:
        return None


# ─── APK / ZIP 操作 ───

def read_apk_entry(apk_path, entry_name):
    """从 APK (ZIP) 中读取指定 entry 的原始字节"""
    import zipfile
    with zipfile.ZipFile(apk_path, 'r') as z:
        if entry_name in z.namelist():
            return z.read(entry_name)
    return None

def list_apk_entries(apk_path):
    """列出 APK 中所有 entry 名"""
    import zipfile
    with zipfile.ZipFile(apk_path, 'r') as z:
        return z.namelist()

def read_apk_asset(apk_path, asset_name):
    """读取 assets/ 下的文件"""
    return read_apk_entry(apk_path, f"assets/{asset_name}")


# ─── IEC 定位: properties maven_hash ───

PROPERTIES_PRIORITY = [
    "play-services-base.properties",
    "apache-common-service.properties",
    "transport-runtime.properties",
]

def locate_iec_path(apk_path):
    """
    从 APK 的 properties 文件中读 maven_hash → hex 解码 → 得到 IEC 路径。
    properties 可能在 assets/ 下或 APK 根目录。
    优先级: play-services-base → apache-common-service → transport-runtime
    条件: 解码后含 "." 才通过
    全失败 → fallback "ts.iec"
    """
    for prop_name in PROPERTIES_PRIORITY:
        # 先尝试 assets/, 再尝试 APK 根
        data = read_apk_asset(apk_path, prop_name)
        if data is None:
            data = read_apk_entry(apk_path, prop_name)
        if data is None:
            continue
        text = data.decode('utf-8', errors='replace')
        # 解析 properties
        for line in text.split('\n'):
            line = line.strip()
            if line.startswith('maven_hash='):
                hex_val = line.split('=', 1)[1].strip()
                decoded = hex_decode_str(hex_val)
                if decoded and '.' in decoded:
                    print(f"[*] IEC path from {prop_name}: {decoded}")
                    return decoded
    print("[!] All properties failed, fallback to ts.iec")
    return "ts.iec"


def extract_iec_from_apk(apk_path, iec_path):
    """
    从 APK 中提取 IEC 文件。
    先尝试 assets/ 下, 再尝试 APK 根 classpath。
    """
    # 尝试 assets/
    data = read_apk_asset(apk_path, iec_path)
    if data and len(data) > 0:
        print(f"[*] Found IEC in assets/{iec_path} ({len(data)} bytes)")
        return data

    # 尝试 APK 根 classpath (Class.getResourceAsStream 路径)
    data = read_apk_entry(apk_path, iec_path)
    if data and len(data) > 0:
        print(f"[*] Found IEC in APK classpath: {iec_path} ({len(data)} bytes)")
        return data

    # 尝试加 / 前缀
    if not iec_path.startswith('/'):
        data = read_apk_entry(apk_path, '/' + iec_path)
        if data and len(data) > 0:
            print(f"[*] Found IEC at /{iec_path} ({len(data)} bytes)")
            return data

    print(f"[!] IEC file not found: {iec_path}")
    return None


# ─── JAR 壳流式解析 ───

def parse_jar_stream(data):
    """
    流式解析 JAR (可能无 central directory)。
    返回 [(entry_name, decompressed_data), ...]
    """
    entries = []
    pos = 0
    while pos < len(data) - 4:
        sig = data[pos:pos+4]
        if sig != b'PK\x03\x04':
            break
        ver, flags, method = struct.unpack_from('<HHH', data, pos+4)
        name_len, extra_len = struct.unpack_from('<HH', data, pos+26)
        name = data[pos+30:pos+30+name_len].decode('utf-8', errors='replace')
        data_start = pos + 30 + name_len + extra_len
        has_dd = (flags & 0x08) != 0

        if has_dd:
            scan = data_start
            comp_size = 0
            uncomp_size = 0
            found = False
            while scan < len(data) - 4:
                if data[scan:scan+4] == b'PK\x07\x08':
                    _, comp_size, uncomp_size = struct.unpack_from('<III', data, scan+4)
                    found = True
                    break
                scan += 1
            if not found:
                break
            entry_data = data[data_start:data_start+comp_size]
            next_pos = scan + 16
        else:
            comp_size = struct.unpack_from('<I', data, pos+18)[0]
            entry_data = data[data_start:data_start+comp_size]
            next_pos = data_start + comp_size

        # Decompress
        if method == 8 and comp_size > 0:
            try:
                raw = zlib.decompress(entry_data, -15)
            except:
                raw = entry_data
        else:
            raw = entry_data

        entries.append((name, raw))
        pos = next_pos
    return entries


def strip_jar_shell(iec_data):
    """
    剥离 JAR 壳:
    1. 读 MANIFEST.MF → Extension-Name (目标条目名) + Sealed (MD5)
    2. 提取目标条目 → 校验 MD5
    3. 读末尾4字节偏移 → 截取 → 返回 xxxmod
    """
    if iec_data[:2] != b'PK':
        # 不是 JAR, 可能直接就是 IEC 二进制
        if iec_data[0] == 3 and iec_data[1] == 11:
            print("[*] No JAR shell, direct IEC format")
            return iec_data
        print(f"[!] Unknown format: {iec_data[:4].hex()}")
        return None

    entries = parse_jar_stream(iec_data)
    entry_map = {name: data for name, data in entries}

    # 读 MANIFEST.MF
    manifest_data = entry_map.get('META-INF/MANIFEST.MF')
    if manifest_data is None:
        print("[!] No MANIFEST.MF in JAR")
        return None

    manifest_text = manifest_data.decode('utf-8', errors='replace')
    ext_name = None
    sealed_md5 = None
    for line in manifest_text.split('\n'):
        line = line.strip()
        if line.startswith('Extension-Name:'):
            ext_name = line.split(':', 1)[1].strip()
        if line.startswith('Sealed:'):
            sealed_md5 = line.split(':', 1)[1].strip()

    if ext_name is None:
        print("[!] No Extension-Name in MANIFEST.MF")
        return None

    print(f"[*] JAR target entry: {ext_name}")
    print(f"[*] Expected MD5: {sealed_md5}")

    # 提取目标条目
    target_data = entry_map.get(ext_name)
    if target_data is None:
        print(f"[!] Entry {ext_name} not found in JAR")
        return None

    # MD5 校验
    actual_md5 = md5hex(target_data)
    if sealed_md5 and actual_md5 != sealed_md5.lower():
        print(f"[!] MD5 mismatch: got {actual_md5}, expected {sealed_md5}")
        # Continue anyway
    else:
        print(f"[*] MD5 verified: {actual_md5}")

    # 读末尾4字节 → 偏移
    if len(target_data) < 4:
        print("[!] Target entry too small")
        return None

    offset = struct.unpack('<I', target_data[-4:])[0]
    print(f"[*] Offset: {offset}, extracting {len(target_data) - offset - 4} bytes")

    # 截取: [offset : len-4]
    mod_data = target_data[offset:len(target_data)-4]
    return mod_data


# ─── IEC 二进制格式解析 ───

def parse_iec_header(data, pos):
    """解析 IEC 头部 (对应 ooo080.m3734lll)"""
    header = {}

    magic, pos = read_bytes(data, pos, 2)
    if magic[0] != 3 or magic[1] != 11:
        raise ValueError(f"Bad IEC magic: {magic[0]:02X} {magic[1]:02X} (expected 03 0B)")

    header['version'], pos = read_le_uint32(data, pos)
    header['flag1'] = data[pos]; pos += 1
    header['flag2'] = data[pos]; pos += 1
    header['metadataSize'], pos = read_le_uint32(data, pos)
    header['indexDataSize'], pos = read_le_uint32(data, pos)
    header['reserved'], pos = read_le_uint32(data, pos)

    header['xor_key'], pos = read_bytes(data, pos, 32)
    header['xor_key_ints'] = []
    for i in range(0, 32, 2):
        val = header['xor_key'][i] + (header['xor_key'][i+1] << 8)
        header['xor_key_ints'].append(val)

    pkg_name_len, pos = read_le_uint32(data, pos)
    pkg_name_enc, pos = read_bytes(data, pos, pkg_name_len)
    header['packageName'] = xor_decrypt(pkg_name_enc, header['xor_key']).decode('utf-8', errors='replace').strip()

    sig_len, pos = read_le_uint32(data, pos)
    sig_enc, pos = read_bytes(data, pos, sig_len)
    header['signature'] = xor_decrypt(sig_enc, header['xor_key']).decode('utf-8', errors='replace').strip()

    second_key_len, pos = read_le_uint32(data, pos)
    second_key_enc, pos = read_bytes(data, pos, 32)
    header['second_xor_key'] = xor_decrypt(second_key_enc, header['xor_key'])

    return header, pos


def validate_index_data(header, data, pos):
    """读取并验证索引块 (对应 ooo080.m3731lll)"""
    idx_size = header['indexDataSize']
    idx_data, pos = read_bytes(data, pos, idx_size)
    if idx_data[0] != 10 or idx_data[1] != 11:
        raise ValueError(f"Bad index magic: {idx_data[0]:02X} {idx_data[1]:02X}")
    return idx_data, pos


def parse_entries(header, data, pos):
    """解析数据条目 (对应 ooo080.m3735lll)"""
    entries = []

    magic, pos = read_bytes(data, pos, 2)
    if magic[0] != 15 or magic[1] != 16:
        raise ValueError(f"Bad data magic: {magic[0]:02X} {magic[1]:02X}")

    entry_count, pos = read_le_uint32(data, pos)

    for i in range(entry_count):
        flag = data[pos]; pos += 1
        crc_key, pos = read_bytes(data, pos, 2)
        name_len, pos = read_le_uint32(data, pos)
        data_len, pos = read_le_uint32(data, pos)
        sig_len, pos = read_le_uint32(data, pos)

        # 文件名 XOR 解密 (只用 crc_key 2字节)
        name_enc, pos = read_bytes(data, pos, name_len)
        name = xor_decrypt(name_enc, crc_key).decode('utf-8', errors='replace')

        # 数据
        entry_data, pos = read_bytes(data, pos, data_len)
        entry_sig, pos = read_bytes(data, pos, sig_len)

        # flag==1 → XOR 解密
        if flag == 1:
            entry_data = xor_decrypt(entry_data, crc_key)

        # CRC 校验
        crc_check = crc2_check(entry_data)
        crc_ok = (crc_check[0] == crc_key[0] and crc_check[1] == crc_key[1])

        entries.append({
            'name': name,
            'data': entry_data,
            'flag': flag,
            'crc_ok': crc_ok,
        })

    return entries


# ─── 输出 ───

def save_entries(entries, out_dir):
    """保存所有解密后的条目到输出目录"""
    os.makedirs(out_dir, exist_ok=True)
    for i, e in enumerate(entries):
        name = e['name']
        crc_status = "OK" if e['crc_ok'] else "FAIL"
        print(f"  [{i:2d}] {name:55s} {len(e['data']):8d}B  flag={e['flag']}  crc={crc_status}")

        safe_name = name.replace('/', os.sep).replace('\\', os.sep)
        safe_name = ''.join(c if (c.isalnum() or c in '._-/\\') else '_' for c in safe_name)
        if not safe_name.strip('_'):
            safe_name = f'entry_{i}'
        out_path = os.path.join(out_dir, safe_name)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, 'wb') as f:
            f.write(e['data'])


# ─── 主流程 ───

def decrypt_apk(apk_path, out_dir):
    """从 APK 一键解密 IEC 包"""
    print(f"=== EasyClick IEC Decryptor ===")
    print(f"APK: {apk_path}")
    print(f"Output: {out_dir}\n")

    # 1. 定位 IEC 文件路径
    iec_path = locate_iec_path(apk_path)

    # 2. 从 APK 提取 IEC 文件
    iec_data = extract_iec_from_apk(apk_path, iec_path)
    if iec_data is None:
        print("[!] Failed to extract IEC file")
        return False

    # 3. 剥离 JAR 壳
    mod_data = strip_jar_shell(iec_data)
    if mod_data is None:
        print("[!] Failed to strip JAR shell")
        return False

    print(f"[*] IEC mod data: {len(mod_data)} bytes")

    # 4. 解析 IEC 格式
    return decrypt_mod(mod_data, out_dir)


def decrypt_mod(mod_data, out_dir):
    """解密已提取的 xxxmod 数据"""
    header, pos = parse_iec_header(mod_data, 0)

    print(f"\n[*] IEC Header:")
    print(f"    Version: {header['version']}")
    print(f"    Package: {header['packageName']}")
    print(f"    IndexSize: {header['indexDataSize']}")

    idx_data, pos = validate_index_data(header, mod_data, pos)
    print(f"    Index block: {len(idx_data)} bytes")

    entries = parse_entries(header, mod_data, pos)
    print(f"\n[*] {len(entries)} entries:")
    save_entries(entries, out_dir)

    crc_fail = [e for e in entries if not e['crc_ok']]
    if crc_fail:
        print(f"\n[!] WARNING: {len(crc_fail)} entries failed CRC check")
    else:
        print(f"\n[+] All {len(entries)} entries decrypted, CRC OK")

    # 提示 Rhino JAR
    jar_entries = [e for e in entries if e['name'].endswith('.jar')]
    if jar_entries:
        print(f"\n[*] Found {len(jar_entries)} JAR file(s) containing Rhino compiled classes:")
        for e in jar_entries:
            print(f"    {e['name']} ({len(e['data'])} bytes)")
        print(f"    → Use jadx to decompile, then rhino2js to transpile back to JS")

    print(f"\n[+] Done. Output: {out_dir}")
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='EasyClick IEC Decryptor (Pure Java Layer)')
    parser.add_argument('--apk', help='APK file path')
    parser.add_argument('--mod', help='Already extracted xxxmod file path')
    parser.add_argument('--output', '-o', required=True, help='Output directory')
    args = parser.parse_args()

    if args.apk:
        decrypt_apk(args.apk, args.output)
    elif args.mod:
        data = open(args.mod, 'rb').read()
        decrypt_mod(data, args.output)
    else:
        parser.error("Must specify --apk or --mod")
