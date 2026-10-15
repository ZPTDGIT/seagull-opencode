import re
import sys

def strip_comments(s):
    out = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == '/' and i + 1 < n and s[i+1] == '/':
            j = s.find('\n', i)
            i = n if j < 0 else j
        elif c == '/' and i + 1 < n and s[i+1] == '*':
            j = s.find('*/', i + 2)
            i = n if j < 0 else j + 2
        elif c in ('"', "'", '`'):
            q = c
            out.append(c)
            i += 1
            while i < n:
                out.append(s[i])
                if s[i] == '\\':
                    if i + 1 < n:
                        out.append(s[i+1])
                        i += 2
                        continue
                elif s[i] == q:
                    i += 1
                    break
                i += 1
        else:
            out.append(c)
            i += 1
    return ''.join(out)

def extract_strings(s):
    res = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c in ('"', "'", '`'):
            q = c
            buf = []
            i += 1
            while i < n:
                if s[i] == '\\' and i + 1 < n:
                    buf.append(s[i:i+2])
                    i += 2
                    continue
                if s[i] == q:
                    i += 1
                    break
                buf.append(s[i])
                i += 1
            res.append(''.join(buf))
        else:
            i += 1
    return res

def extract_numbers(s):
    s2 = re.sub(r"'[^']*'|\"[^\"]*\"|`[^`]*`", ' ', s)
    return re.findall(r'(?<![\w.$\u4e00-\u9fff])(\d+(?:\.\d+)?)(?![\w.$\u4e00-\u9fff])', s2)

def extract_calls(s):
    names = set()
    for m in re.finditer(r'([A-Za-z_$\u4e00-\u9fff][\w$\u4e00-\u9fff]*)\s*\(', s):
        names.add(m.group(1))
    return names

def extract_functions(s):
    funcs = {}
    i = 0
    n = len(s)
    while True:
        m = re.search(r'function\s+([A-Za-z_$\u4e00-\u9fff][\w$\u4e00-\u9fff]*)\s*\(', s[i:])
        if not m:
            break
        name = m.group(1)
        start = i + m.end()
        # 找到函数体第一个 {
        j = s.find('{', start)
        if j < 0:
            break
        depth = 0
        k = j
        in_str = None
        while k < n:
            c = s[k]
            if in_str:
                if c == '\\':
                    k += 2
                    continue
                if c == in_str:
                    in_str = None
            elif c in ('"', "'", '`'):
                in_str = c
            elif c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    k += 1
                    break
            k += 1
        body = s[j:k]
        if name not in funcs:
            funcs[name] = body
        i = k
    return funcs

def compare(file_a, file_b, out):
    a = open(file_a, encoding='utf-8', errors='replace').read()
    b = open(file_b, encoding='utf-8', errors='replace').read()
    as_ = strip_comments(a)
    bs = strip_comments(b)
    out.append('#### %s' % file_a)
    out.append('#### %s' % file_b)
    # 全局字符串多重集
    sa = sorted(extract_strings(as_))
    sb = sorted(extract_strings(bs))
    from collections import Counter
    ca, cb = Counter(sa), Counter(sb)
    only_a = list((ca - cb).elements())
    only_b = list((cb - ca).elements())
    out.append('全局字符串: 源=%d 译=%d 源独有=%d 译独有=%d' % (len(sa), len(sb), len(only_a), len(only_b)))
    for s in only_a[:20]:
        out.append('  源独有: %r' % s[:100])
    for s in only_b[:20]:
        out.append('  译独有: %r' % s[:100])
    # 数字
    na = Counter(extract_numbers(as_))
    nb = Counter(extract_numbers(bs))
    oa = list((na - nb).elements())
    ob = list((nb - na).elements())
    out.append('数字: 源独有=%d 译独有=%d' % (len(oa), len(ob)))
    out.append('  源独有: %s' % sorted(set(oa))[:25])
    out.append('  译独有: %s' % sorted(set(ob))[:25])
    # 函数级
    fa = extract_functions(as_)
    fb = extract_functions(bs)
    common = sorted(set(fa) & set(fb))
    onlyf_a = sorted(set(fa) - set(fb))
    onlyf_b = sorted(set(fb) - set(fa))
    out.append('函数: 源=%d 译=%d 共有=%d 源独有=%s 译独有=%s' % (
        len(fa), len(fb), len(common), onlyf_a[:10], onlyf_b[:10]))
    bad = []
    for name in common:
        sa2 = Counter(extract_strings(fa[name]))
        sb2 = Counter(extract_strings(fb[name]))
        diff = sum((sa2 - sb2).values()) + sum((sb2 - sa2).values())
        if diff:
            bad.append((diff, name))
    bad.sort(reverse=True)
    out.append('函数级字符串不一致: %d/%d' % (len(bad), len(common)))
    for d, name in bad[:15]:
        out.append('  [%d] %s' % (d, name))
        sa2 = Counter(extract_strings(fa[name]))
        sb2 = Counter(extract_strings(fb[name]))
        for s in list((sa2 - sb2).elements())[:4]:
            out.append('      源独有: %r' % s[:80])
        for s in list((sb2 - sa2).elements())[:4]:
            out.append('      译独有: %r' % s[:80])
    out.append('')

def main():
    base = r'E:\IDEA项目\10.3抖音直播间'
    tr = r'E:\autojs_work\user_js_out'
    pairs = [
        (base + r'\src\js\main.js', tr + r'\main.js'),
        (base + r'\src\js\laoleng.js', tr + r'\laoleng.js'),
        (base + r'\src\js\yidao.js', tr + r'\yidao.js'),
        (base + r'\src\layout\ui.js', tr + r'\ui.js'),
    ]
    out = []
    for a, b in pairs:
        compare(a, b, out)
    open(r'E:\autojs_work\diff_report.txt', 'w', encoding='utf-8').write('\n'.join(out))
    print('report written')

if __name__ == '__main__':
    main()
