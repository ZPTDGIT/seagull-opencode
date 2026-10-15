# -*- coding: utf-8 -*-
"""
Rhino (EasyClick 编译模式) 反编译类 -> JS 源码 转译器

用法:
    python rhino2js.py <jadx_sources_dir> <output_dir> [类名...]

输入: jadx 反编译出的 com/js/*.java（EasyClick 编译模式产物）
输出: 对应 *.js（函数名/参数名/中文常量/控制流还原；局部临时变量名为 jadx 生成名）
"""
import os
import re
import sys
import io

import javalang
from javalang import tree as jtree

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


# ------------------------------------------------------------------ 工具

def jstr(s):
    body = s[1:-1]
    out = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == '\\' and i + 1 < len(body):
            nxt = body[i + 1]
            mapping = {'n': '\n', 'r': '\r', 't': '\t', '"': '"', "'": "'", '\\': '\\'}
            if nxt == 'u' and i + 5 < len(body):
                try:
                    out.append(chr(int(body[i + 2:i + 6], 16)))
                    i += 6
                    continue
                except Exception:
                    pass
            if nxt in mapping:
                out.append(mapping[nxt])
            else:
                out.append('\\' + nxt)
            i += 2
            continue
        out.append(ch)
        i += 1
    return ''.join(out)


def numlit(s):
    s = re.sub(r'[dDfFlL]+$', '', s.strip())
    try:
        f = float(s)
        if f == int(f):
            return str(int(f))
        return repr(f)
    except Exception:
        return s


class Ctx:
    def __init__(self):
        self.classname = ''
        self.source_file = ''
        self.funcnames = {}
        self.method_of_id = {}
        self.paramnames = {}
        self.paramcount = {}
        self.consts = {}
        self.regex = {}


# ------------------------------------------------------------------ 解析

def parse_file(path):
    src = open(path, encoding='utf-8', errors='replace').read()
    src = re.sub(r'\\u(?![0-9a-fA-F]{4})', r'\\\\u', src)
    cu = javalang.parse.parse(src)
    cls = cu.types[0]
    ctx = Ctx()
    ctx.classname = cls.name
    m = re.search(r'\(js/([\w\u4e00-\u9fff]+\.js)#\d+\)', src)
    if m:
        ctx.source_file = 'js/' + m.group(1)

    for _, fd in cls.filter(jtree.FieldDeclaration):
        for d in fd.declarators:
            if d.initializer is not None:
                ctx.consts[d.name] = d.initializer

    for _, md in cls.filter(jtree.MethodDeclaration):
        if md.name == 'getFunctionName':
            for sw in top_switches(md):
                pending = []
                for case in sw.cases:
                    cid = as_int(case_val(case))
                    val = None
                    for st in case.statements:
                        if isinstance(st, jtree.ReturnStatement) and isinstance(st.expression, jtree.Literal):
                            val = jstr(st.expression.value)
                    if val is None:
                        pending.append(cid)
                        continue
                    for pcid in pending:
                        if pcid is not None:
                            ctx.funcnames[pcid] = val
                    pending = []
                    if cid is not None:
                        ctx.funcnames[cid] = val
        elif md.name == 'call':
            for _, sw in md.filter(jtree.SwitchStatement):
                for case in sw.cases:
                    cid = as_int(case_val(case))
                    for st in case.statements:
                        for _, inv in st.filter(jtree.MethodInvocation):
                            mname = inv.member or ''
                            if cid is not None and (mname.startswith('_c_') or re.match(r'm\d+_c_', mname)):
                                ctx.method_of_id[cid] = mname
                        for _, inv in st.filter(jtree.MethodInvocation):
                            if (inv.member or '').startswith('_c_script'):
                                if case_val(case) is None:
                                    ctx.method_of_id[0] = inv.member
        elif md.name == 'getParamOrVarName':
            for sw in top_switches(md):
                for case in sw.cases:
                    cid = as_int(case_val(case))
                    if cid is None:
                        continue
                    d = {}
                    default_name = None
                    for st in case.statements:
                        if isinstance(st, jtree.ReturnStatement) and isinstance(st.expression, jtree.Literal):
                            d[0] = jstr(st.expression.value)
                        if isinstance(st, jtree.SwitchStatement):
                            for sc in st.cases:
                                si = as_int(case_val(sc))
                                for s2 in sc.statements:
                                    if isinstance(s2, jtree.ReturnStatement) and isinstance(s2.expression, jtree.Literal):
                                        nm = jstr(s2.expression.value)
                                        if si is None:
                                            default_name = nm
                                        else:
                                            d[si] = nm
                    if default_name is not None:
                        for kk in range(64):
                            d.setdefault(kk, default_name)
                    ctx.paramnames[cid] = d
        elif md.name == 'getParamCount':
            for sw in top_switches(md):
                pending = []
                for case in sw.cases:
                    cid = as_int(case_val(case))
                    val = None
                    for st in case.statements:
                        if isinstance(st, jtree.ReturnStatement) and isinstance(st.expression, jtree.Literal):
                            try:
                                val = int(st.expression.value)
                            except Exception:
                                val = None
                    if val is None:
                        pending.append(cid)
                        continue
                    for pcid in pending:
                        if pcid is not None:
                            ctx.paramcount[pcid] = val
                    pending = []
                    if cid is not None:
                        ctx.paramcount[cid] = val
                    else:
                        for pcid in range(1, 256):
                            ctx.paramcount.setdefault(pcid, val)
        elif md.name == '_reInit':
            def find_regex(inv):
                if isinstance(inv, jtree.MethodInvocation):
                    if inv.member == 'compileRegExp':
                        lits = [a for a in inv.arguments if isinstance(a, jtree.Literal)]
                        if len(lits) >= 2:
                            return lits[0].value, lits[1].value
                    for sel in (inv.selectors or []):
                        r = find_regex(sel)
                        if r:
                            return r
                return None
            for _, assign in md.filter(jtree.Assignment):
                if isinstance(assign.expressionl, jtree.MemberReference) and isinstance(assign.value, jtree.MethodInvocation):
                    r = find_regex(assign.value)
                    if r:
                        pat = jstr(r[0])
                        flg = jstr(r[1])
                        ctx.regex[assign.expressionl.member] = 'new RegExp(%s, %s)' % (jsstr(pat), jsstr(flg))
    return cls, ctx


def as_int(s):
    if s is None:
        return None
    try:
        return int(s)
    except Exception:
        return None


def case_val(case):
    c = case.case
    if c is None:
        return None
    if isinstance(c, list):
        if len(c) == 1 and isinstance(c[0], jtree.Literal):
            return str(c[0].value)
        return None
    return str(c)


# ------------------------------------------------------------------ 转译

class Translator:
    def __init__(self, ctx):
        self.ctx = ctx
        self.enum_subs = {}
        self.rename = {}

    # ---------------- 表达式 ----------------

    def expr(self, node, scope=None):
        txt = self.expr_core(node, scope)
        if node is not None:
            pre = getattr(node, 'prefix_operators', None) or []
            post = getattr(node, 'postfix_operators', None) or []
            if pre:
                txt = '(' + ''.join(pre) + txt + ')'
            if post:
                txt = '(' + txt + ''.join(post) + ')'
        return txt

    def expr_core(self, node, scope=None):
        if node is None:
            return 'undefined'
        tn = type(node).__name__
        if tn == 'Literal':
            v = node.value
            if getattr(node, 'type', None) == 'String' or (isinstance(v, str) and v.startswith('"') and v.endswith('"')):
                return jsstr(jstr(v))
            if v in ('true', 'false'):
                return v
            if v == 'null':
                return 'null'
            if re.fullmatch(r'[0-9].*[dDfFlL]?', v):
                return numlit(v)
            return v
        if tn == 'MemberReference':
            q = node.qualifier or ''
            if q == 'scriptable2':
                q = 'this'
            name = node.member
            full = (q + '.' + name) if q else name
            special = {
                'Undefined.instance': 'undefined',
                'Boolean.TRUE': 'true',
                'Boolean.FALSE': 'false',
                'Void.TYPE': 'undefined',
                'ScriptRuntime.zeroObj': '0',
                'OptRuntime.zeroObj': '0',
                'OptRuntime.oneObj': '1',
                'OptRuntime.minusOneObj': '-1',
                'ScriptRuntime.emptyArgs': '[]',
                'objArr2': '[]',
                'scriptable2': 'this',
            }
            if full in special:
                res = special[full]
            elif full in self.rename:
                res = self.rename[full]
            elif name in self.ctx.regex and not q:
                res = self.ctx.regex[name]
            elif name in self.ctx.consts and not q:
                res = self.const_of(name)
            elif full == 'ScriptRuntime.lastStoredScriptable(context)':
                res = 'this'
            else:
                res = full
            for sel in (node.selectors or []):
                if isinstance(sel, jtree.ArraySelector):
                    if res == 'objArr' and isinstance(sel.index, jtree.Literal):
                        key = 'objArr[%s]' % sel.index.value
                        if key in self.rename:
                            res = self.rename[key]
                            continue
                    res = '%s[%s]' % (res, self.expr(sel.index, scope))
                elif isinstance(sel, jtree.MethodInvocation):
                    inner = ', '.join(self.expr(x, scope) for x in (sel.arguments or []))
                    res = '%s.%s(%s)' % (res, sel.member, inner)
                else:
                    mm = getattr(sel, 'member', None)
                    if mm:
                        res = '%s.%s' % (res, mm)
            return res
        if tn == 'BinaryOperation':
            if node.operandl is None:
                ops = getattr(node, 'prefix_operators', None) or []
                op = ''.join(ops) if ops else (node.operator or '')
                return '(%s%s)' % (op, self.expr(node.operandr, scope))
            op = {'==': '===', '!=': '!=='}.get(node.operator, node.operator)
            return '(%s %s %s)' % (self.expr(node.operandl, scope), op, self.expr(node.operandr, scope))
        if tn == 'Cast':
            return self.expr(node.expression, scope)
        if tn == 'Assignment':
            lhs = self.expr(node.expressionl, scope)
            rhs = self.expr(node.value, scope)
            return '%s %s %s' % (lhs, getattr(node, 'type', None) or getattr(node, 'operator', '='), rhs)
        if tn == 'TernaryExpression':
            return '(%s ? %s : %s)' % (self.expr(node.condition, scope), self.expr(node.if_true, scope), self.expr(node.if_false, scope))
        if tn == 'MethodInvocation':
            return self.invoke(node, scope)
        if tn == 'ClassCreator':
            return self.class_creator(node, scope)
        if tn == 'ArrayCreator':
            if getattr(node, 'initializer', None) is not None:
                return '[' + ', '.join(self.expr(x, scope) for x in node.initializer.initializers) + ']'
            return '[]'
        if tn == 'ArraySelector':
            if isinstance(node.array, jtree.MemberReference) and node.array.member == 'objArr' and isinstance(node.index, jtree.Literal):
                key = 'objArr[%s]' % node.index.value
                if key in self.rename:
                    return self.rename[key]
            return '%s[%s]' % (self.expr(node.array, scope), self.expr(node.index, scope))
        if tn in ('BasicType', 'ReferenceType', 'Type', 'VoidType'):
            nm = getattr(node, 'name', None)
            if nm is not None and hasattr(nm, 'name'):
                nm = nm.name
            return str(nm) if nm else 'Object'
        if tn == 'This':
            return 'this'
        if tn == 'InnerClassCreator':
            return self.class_creator(node, scope)
        return '/*TODO:%s*/' % tn

    def const_of(self, name):
        init = self.ctx.consts[name]
        return self.expr(init)

    def callQ(self, node):
        return node.qualifier or ''

    def invoke(self, node, scope=None):
        q = self.callQ(node)
        m = node.member
        args = list(node.arguments or [])

        # ---- Linker ----
        if q == 'NameLinker':
            if m in ('name_getName', 'name_getNameFunctionAndThis'):
                return jstr(args[2].value)
            if m == 'name_bind':
                return 'BIND:' + jstr(args[2].value)
            if m in ('name_setName', 'name_setConst'):
                target = self.expr(args[0], scope)
                name = target.split('BIND:')[-1]
                return '%s = %s' % (name, self.expr(args[1], scope))
        if q == 'PropLinker':
            if m in ('prop_getObjectProp', 'prop_getObjectPropNoWarn'):
                o = self.expr(args[0], scope)
                n = jstr(args[3].value) if len(args) > 3 and isinstance(args[3], jtree.Literal) else '?'
                return self.member(o, n)
            if m == 'prop_setObjectProp':
                o = self.expr(args[0], scope)
                v = self.expr(args[1], scope)
                n = jstr(args[4].value) if len(args) > 4 and isinstance(args[4], jtree.Literal) else '?'
                return '%s = %s' % (self.member(o, n), v)
            if m in ('prop_getObjectElem', 'prop_getObjectIndex'):
                return '%s[%s]' % (self.expr(args[0], scope), self.expr(args[1], scope))
            if m in ('prop_setObjectElem', 'prop_setObjectIndex'):
                return '%s[%s] = %s' % (self.expr(args[0], scope), self.expr(args[1], scope), self.expr(args[2], scope))
            if m == 'prop_getPropFunctionAndThis':
                o = self.expr(args[0], scope)
                n = jstr(args[3].value) if len(args) > 3 and isinstance(args[3], jtree.Literal) else '?'
                return self.member(o, n)
        # ---- Math linker ----
        if q == 'MathLinker':
            a = lambda i: self.expr(args[i], scope)
            if m == 'math_add':
                return '(%s + %s)' % (a(0), a(1))
            if m in ('math_TONUMBER', 'math_TONUMERIC'):
                return 'Number(%s)' % a(0)
            if m == 'math_TOBOOLEAN':
                return '(!!(%s))' % a(0)
            if m == 'math_TOINT32':
                return '((%s) | 0)' % a(0)
            if m == 'math_TOUINT32':
                return '((%s) >>> 0)' % a(0)
            if m == 'math_compare_gt':
                return '(%s > %s)' % (a(0), a(1))
            if m == 'math_compare_lt':
                return '(%s < %s)' % (a(0), a(1))
            if m == 'math_compare_le':
                return '(%s <= %s)' % (a(0), a(1))
            if m == 'math_compare_ge':
                return '(%s >= %s)' % (a(0), a(1))
            if m == 'math_eq':
                return '(%s === %s)' % (a(0), a(1))
            if m == 'math_shallowEq':
                return '(%s == %s)' % (a(0), a(1))
            if m == 'math_shallowNe':
                return '(%s != %s)' % (a(0), a(1))
        # ---- ScriptRuntime ----
        if q == 'ScriptRuntime':
            a = lambda i: self.expr(args[i], scope)
            if m in ('add',):
                return '(%s + %s)' % (a(0), a(1))
            if m == 'subtract':
                return '(%s - %s)' % (a(0), a(1))
            if m == 'multiply':
                return '(%s * %s)' % (a(0), a(1))
            if m == 'divide':
                return '(%s / %s)' % (a(0), a(1))
            if m == 'remainder':
                return '(%s %% %s)' % (a(0), a(1))
            if m == 'bitwiseNOT':
                return '(~%s)' % a(0)
            if m == 'bitwiseOR':
                return '(%s | %s)' % (a(0), a(1))
            if m == 'bitwiseXOR':
                return '(%s ^ %s)' % (a(0), a(1))
            if m == 'bitwiseAND':
                return '(%s & %s)' % (a(0), a(1))
            if m == 'toInt32':
                return '((%s) | 0)' % a(0)
            if m == 'typeof':
                return '(typeof %s)' % a(0)
            if m == 'typeofName':
                return '(typeof %s)' % jstr(args[1].value)
            if m == 'instanceOf':
                return '(%s instanceof %s)' % (a(0), a(1))
            if m == 'wrapRegExp':
                rexpr = self.expr(args[2], scope)
                return rexpr
            if m == 'nameIncrDecr':
                name = jstr(args[1].value)
                code = self.expr(args[3]) if len(args) > 3 else '2'
                return '%s%s' % (name, '++' if code == '2' else '--')
            if m == 'propIncrDecr':
                o = self.expr(args[0], scope)
                n = jstr(args[1].value)
                code = self.expr(args[4]) if len(args) > 4 else '2'
                return '%s.%s%s' % (o, n, '++' if code == '2' else '--')
            if m == 'newObject':
                cls_expr = self.expr(args[0], scope)
                extra = self.array_elems(args[3], scope) if len(args) > 3 else []
                return 'new %s(%s)' % (cls_expr, ', '.join(extra))
            if m == 'newArrayLiteral':
                elems = self.array_elems(args[0], scope) if len(args) > 0 else []
                return '[%s]' % ', '.join(elems)
            if m == 'fillObjectLiteral':
                o = self.expr(args[0], scope)
                keys = self.array_elems(args[1], scope)
                vals = self.array_elems(args[2], scope)
                pairs = []
                for k, v in zip(keys, vals):
                    kk = k[1:-1] if k.startswith("'") and k.endswith("'") else k
                    if not re.fullmatch(r'[A-Za-z_$\u4e00-\u9fff][\w$\u4e00-\u9fff]*', kk):
                        kk = jsstr(kk)
                    pairs.append('%s: %s' % (kk, v))
                return '%s = { %s }' % (o, ', '.join(pairs))
            if m == 'enumId':
                e_name = self.expr(args[0], scope)
                return self.enum_subs.get(e_name, 'key')
            if m == 'lastStoredScriptable':
                return 'this'
            if m in ('createFunctionActivation', 'enterActivationFunction', 'exitActivationFunction',
                     'enterWith', 'leaveWith', 'initScript', 'checkRegExpProxy', 'padArguments'):
                return '/* %s */' % m
        # ---- OptRuntime ----
        if q == 'OptRuntime':
            if m == 'wrapDouble':
                return self.expr(args[0], scope)
            if m == 'add':
                return '(%s + %s)' % (self.expr(args[0], scope), self.expr(args[1], scope))
            if m in ('call0', 'call1', 'call2', 'callN'):
                return self.opt_call(m, args, scope)
            if m == 'callName' or m == 'callName0':
                return self.opt_call_name(m, args, scope)
            if m.startswith('callProp'):
                n_args = int(m[len('callProp'):]) if m[len('callProp'):].isdigit() else 0
                o = self.expr(args[0], scope)
                nm = jstr(args[1].value)
                extra = [self.expr(x, scope) for x in args[2:2 + n_args]]
                return '%s(%s)' % (self.member(o, nm), ', '.join(extra))
            if m == 'bindThis':
                fn = self.expr(args[0], scope)
                if len(args) > 3:
                    return '%s.bind(%s)' % (fn, self.expr(args[3], scope))
                return fn + '.bind(this)'
            if m == 'newArrayLiteral':
                elems = self.array_elems(args[0], scope)
                return '[%s]' % ', '.join(elems)
            if m == 'main':
                return '/* main */'
        if q == 'context' and m == 'newObject':
            return '{}'
        # 一般方法调用
        if q:
            base = self.expr(node.qualifier if isinstance(node.qualifier, jtree.Node) else jtree.MemberReference(node.qualifier.split('.')[0], '.'.join(node.qualifier.split('.')[1:]) if '.' in node.qualifier else None), scope) if False else None
        render_args = ', '.join(self.expr(x, scope) for x in args)
        if q:
            return '%s.%s(%s)' % (q, m, render_args)
        return '%s(%s)' % (m, render_args)

    @staticmethod
    def member(o, n):
        if re.fullmatch(r'[A-Za-z_$][\w$]*', n):
            return '%s.%s' % (o, n)
        return '%s[%s]' % (o, jsstr(n))

    def array_elems(self, node, scope):
        if node is None:
            return []
        if isinstance(node, jtree.ArrayCreator) and getattr(node, 'initializer', None) is not None:
            return [self.expr(x, scope) for x in node.initializer.initializers]
        if isinstance(node, jtree.MemberReference) and node.member in ('emptyArgs', 'objArr2'):
            return []
        if isinstance(node, jtree.Literal) and node.value == 'null':
            return []
        return [self.expr(node, scope)]

    def opt_call(self, m, args, scope):
        # (fn, thisObj, a..., ctx, scope)
        body = list(args)
        if len(body) >= 2:
            ctxn, scopn = body[-2], body[-1]
            body = body[:-2]
            del ctxn, scopn
        fn = body[0]
        rest = body[1:]
        this_obj = None
        if rest and is_call(rest[0], 'ScriptRuntime', 'lastStoredScriptable'):
            this_obj = 'this'
            rest = rest[1:]
        js_args = [self.expr(x, scope) for x in rest]
        if is_call(fn, 'PropLinker', 'prop_getPropFunctionAndThis'):
            fa = list(fn.arguments)
            obj = self.expr(fa[0], scope)
            nm = jstr(fa[3].value)
            return '%s(%s)' % (self.member(obj, nm), ', '.join(js_args))
        if is_call(fn, 'NameLinker', 'name_getNameFunctionAndThis'):
            nm = jstr(fn.arguments[2].value)
            return '%s(%s)' % (nm, ', '.join(js_args))
        fexpr = self.expr(fn, scope)
        if this_obj is not None:
            return '%s.call(this%s)' % (fexpr, (', ' + ', '.join(js_args)) if js_args else '')
        return '%s(%s)' % (fexpr, ', '.join(js_args))

    def opt_call_name(self, m, args, scope):
        if m == 'callName0':
            nm = jstr(args[0].value)
            return '%s()' % nm
        arr = args[0]
        nm = jstr(args[1].value)
        elems = self.array_elems(arr, scope)
        cleaned = []
        for e in elems:
            if isinstance(e, str) and e.startswith("'") and re.match(r"^'\(js/", e):
                continue
            cleaned.append(e)
        return '%s(%s)' % (nm, ', '.join(cleaned))

    def class_creator(self, node, scope):
        tname = node.type.name if hasattr(node.type, 'name') else str(node.type)
        if tname == 'Object':
            if getattr(node, 'arguments', None):
                arg = node.arguments[0]
                if isinstance(arg, jtree.ArrayCreator) and getattr(arg, 'initializer', None) is not None:
                    return '[' + ', '.join(self.expr(x, scope) for x in arg.initializer.initializers) + ']'
            return '{}'
        # throw new JavaScriptException(value, "js/x.js", line) -> 抛出 value
        if tname in ('JavaScriptException', 'EcmaError', 'EvaluatorException'):
            args = list(node.arguments or [])
            return self.expr(args[0], scope) if args else 'undefined'
        # new <Class>(scriptable, context, ID) -> 函数引用
        if len(node.arguments) == 3 and isinstance(node.arguments[-1], jtree.Literal) \
                and not isinstance(node.arguments[1], jtree.Literal):
            try:
                fid = int(node.arguments[-1].value)
                name = self.ctx.funcnames.get(fid)
                return name if name else '__fn%d' % fid
            except Exception:
                pass
        return 'new %s(%s)' % (tname, ', '.join(self.expr(x, scope) for x in (node.arguments or [])))

    # ---------------- 语句 ----------------

    def stmts(self, body, ind='  '):
        out = []
        if body is None:
            return out
        st = list(body)
        i = 0
        while i < len(st):
            node = st[i]
            consumed, lines = self.try_special(st, i, ind)
            if consumed:
                out.extend(lines)
                i += consumed
                continue
            out.extend(self.stmt(node, ind))
            i += 1
        return out

    def try_special(self, st, i, ind):
        node = st[i]
        # padArguments 补齐块: if (objArr.length < N) { objArr = padArguments(...); }
        if isinstance(node, jtree.IfStatement) and node.else_statement is None:
            blk_body = blk(node.then_statement)
            if len(blk_body) == 1 and isinstance(blk_body[0], jtree.StatementExpression):
                e0 = blk_body[0].expression
                if isinstance(e0, jtree.Assignment) and is_call(e0.value, 'ScriptRuntime', 'padArguments'):
                    return 1, []
        # 参数槽位 fixup: if (obj === undefined) obj = d;  (Rhino 调用约定, JS 里无意义)
        if isinstance(node, jtree.IfStatement) and node.else_statement is None and 'obj' in self.rename:
            body = blk(node.then_statement)
            if len(body) == 1 and isinstance(body[0], jtree.StatementExpression):
                e = body[0].expression
                if isinstance(e, jtree.Assignment):
                    lhs = getattr(e.expressionl, 'member', None)
                    rhs = e.value
                    if lhs == 'obj':
                        if isinstance(rhs, jtree.MemberReference) and rhs.member == 'd':
                            return 1, []
                        if isinstance(rhs, jtree.MethodInvocation) and 'wrap' in (rhs.member or ''):
                            return 1, []
        # enterWith 残留声明: var x = ScriptRuntime.enterWith(...);  -> 丢弃
        if isinstance(node, jtree.LocalVariableDeclaration):
            d0 = node.declarators[0]
            if d0.initializer is not None and isinstance(d0.initializer, jtree.MethodInvocation) and d0.initializer.member in ('enterWith', 'leaveWith', 'enterActivationFunction', 'exitActivationFunction', 'initScript', 'checkRegExpProxy', 'padArguments'):
                return 1, []
            if d0.initializer is not None and is_call(d0.initializer, 'NameLinker', 'name_bind'):
                args0 = list(d0.initializer.arguments)
                if len(args0) >= 3 and isinstance(args0[2], jtree.Literal):
                    self.rename[d0.name] = 'BIND:' + jstr(args0[2].value)
                return 1, []
        # 槽位本地变量声明: Object objX = objArr[K] / Object obj = Undefined.instance
        if isinstance(node, jtree.LocalVariableDeclaration):
            d = node.declarators[0]
            init = d.initializer
            if d.name in self.rename and (init is None or (isinstance(init, jtree.MemberReference) and init.member == 'instance')):
                return 1, []
            if isinstance(init, jtree.ArraySelector) and isinstance(init.array, jtree.MemberReference) and init.array.member == 'objArr' and isinstance(init.index, jtree.Literal):
                key = 'objArr[%s]' % init.index.value
                if key in self.rename:
                    self.rename[d.name] = self.rename[key]
                    return 1, []
            if isinstance(init, jtree.MemberReference) and init.member == 'objArr' and init.selectors and isinstance(init.selectors[0], jtree.ArraySelector):
                sel = init.selectors[0]
                if isinstance(sel.index, jtree.Literal):
                    key = 'objArr[%s]' % sel.index.value
                    if key in self.rename:
                        self.rename[d.name] = self.rename[key]
                        return 1, []
        # 1) parentScope 声明
        if isinstance(node, jtree.LocalVariableDeclaration):
            d = node.declarators[0]
            init = d.initializer
            if d.name == 'parentScope' or (init is not None and isinstance(init, jtree.MethodInvocation) and init.member == 'getParentScope'):
                return 1, []
            if init is not None and is_call(init, 'ScriptRuntime', 'padArguments'):
                return 1, []
            if d.name == 'objArr2' and isinstance(init, jtree.MemberReference) and init.member == 'emptyArgs':
                return 1, []
            # activation
            if init is not None and is_call(init, 'ScriptRuntime', 'createFunctionActivation'):
                j = i + 1
                if j < len(st) and isinstance(st[j], jtree.StatementExpression) and is_call(st[j].expression, 'ScriptRuntime', 'enterActivationFunction'):
                    k = j + 1
                    if k < len(st) and isinstance(st[k], jtree.TryStatement):
                        lines = self.stmts(blk(st[k].block), ind)
                        return 3, lines
                # 没有配套 enterActivation 的形态：声明本身直接丢弃
                return 1, []
            # with
            if init is not None and is_call(init, 'ScriptRuntime', 'enterWith'):
                j = i + 1
                if j < len(st) and isinstance(st[j], jtree.TryStatement):
                    with_expr = self.expr(init.arguments[0])
                    lines = ['%swith (%s) {' % (ind, with_expr)]
                    lines += self.stmts(blk(st[j].block), ind + '  ')
                    lines.append(ind + '}')
                    return 2, lines
            # enum
            if init is not None and is_call(init, 'ScriptRuntime', 'enumInit'):
                j = i + 1
                if j < len(st) and isinstance(st[j], jtree.WhileStatement) and self.cond_has_enumnext(st[j].condition, d.name):
                    obj = self.expr(init.arguments[0])
                    body = list(st[j].body.statements) if isinstance(st[j].body, jtree.BlockStatement) else [st[j].body]
                    loopvar = 'key'
                    if body:
                        b0 = body[0]
                        if isinstance(b0, jtree.LocalVariableDeclaration) and b0.declarators[0].initializer is not None and is_call(b0.declarators[0].initializer, 'ScriptRuntime', 'enumId'):
                            loopvar = b0.declarators[0].name
                            body = body[1:]
                        elif isinstance(b0, jtree.StatementExpression) and isinstance(b0.expression, jtree.Assignment) and is_call(b0.expression.value, 'ScriptRuntime', 'enumId'):
                            loopvar = self.expr(b0.expression.expressionl)
                            body = body[1:]
                    self.enum_subs[d.name] = loopvar
                    lines = ['%sfor (var %s in %s) {' % (ind, loopvar, obj)]
                    lines += self.stmts(body, ind + '  ')
                    lines.append(ind + '}')
                    del self.enum_subs[d.name]
                    return 2, lines
            # 优化直调块
            if init is not None and is_call(init, 'NameLinker', 'name_getNameFunctionAndThis'):
                fname = jstr(init.arguments[2].value)
                j = i + 1
                if j < len(st) and isinstance(st[j], jtree.LocalVariableDeclaration) and st[j].declarators[0].initializer is not None and is_call(st[j].declarators[0].initializer, 'ScriptRuntime', 'lastStoredScriptable'):
                    k = j + 1
                    if k < len(st) and isinstance(st[k], jtree.IfStatement) and self.is_direct_call_if(st[k], d.name):
                        expr_text = self.direct_call_expr(st[k], fname)
                        if expr_text:
                            return 3, [ind + expr_text + ';']
        # 2) 直调块（无显式变量声明时，例如 objCall 已提前声明）
        if isinstance(node, jtree.IfStatement) and self.is_direct_call_if(node, None):
            expr_text = self.direct_call_expr(node, None)
            if expr_text:
                return 1, [ind + expr_text + ';']
        # 3) fillObjectLiteral 独立语句
        if isinstance(node, jtree.StatementExpression) and is_call(node.expression, 'ScriptRuntime', 'fillObjectLiteral'):
            return 1, [ind + self.expr(node.expression) + ';']
        # 自赋值 a = a; 跳过
        if isinstance(node, jtree.StatementExpression) and isinstance(node.expression, jtree.Assignment):
            a = node.expression
            l = getattr(a.expressionl, 'member', None)
            r = getattr(a.value, 'member', None)
            if l is not None and l == r and not getattr(a.expressionl, 'qualifier', None):
                return 1, []
        # 4) 优化器残留的裸表达式（如 wrapDouble(x); 单独一行）跳过
        if isinstance(node, jtree.StatementExpression) and isinstance(node.expression, (jtree.MemberReference, jtree.Literal)):
            return 1, []
        if isinstance(node, jtree.StatementExpression) and is_call(node.expression, 'OptRuntime', 'wrapDouble'):
            return 1, []
        # 4a) 独立空数组/死表达式语句跳过
        if isinstance(node, jtree.StatementExpression) and isinstance(node.expression, jtree.ArrayCreator):
            return 1, []
        # 4b) x = leaveWith/enterWith/... 赋值残留跳过
        if isinstance(node, jtree.StatementExpression) and isinstance(node.expression, jtree.Assignment):
            val = node.expression.value
            if isinstance(val, jtree.MethodInvocation) and val.member in ('leaveWith', 'enterWith', 'enterActivationFunction', 'exitActivationFunction', 'initScript', 'checkRegExpProxy', 'padArguments'):
                return 1, []
        # 5) initFunction / initScript / enterActivationFunction 等独立语句
        if isinstance(node, jtree.StatementExpression):
            e = node.expression
            if isinstance(e, jtree.MethodInvocation):
                if is_call(e, 'OptRuntime', 'initFunction') or is_call(e, 'ScriptRuntime', 'initScript') \
                        or is_call(e, 'ScriptRuntime', 'enterActivationFunction') or is_call(e, 'ScriptRuntime', 'leaveWith') \
                        or is_call(e, 'ScriptRuntime', 'enterWith') or is_call(e, 'ScriptRuntime', 'checkRegExpProxy') \
                        or is_call(e, 'ScriptRuntime', 'padArguments'):
                    return 1, []
        return 0, []

    def cond_has_enumnext(self, node, enum_var):
        for _, inv in node.filter(jtree.MethodInvocation):
            if is_call(inv, 'ScriptRuntime', 'enumNext'):
                return True
        return False

    def is_direct_call_if(self, node, var):
        if not isinstance(node, jtree.IfStatement):
            return False
        cond = node.condition
        if not (isinstance(cond, jtree.BinaryOperation) and cond.operator == 'instanceof'):
            return False
        for _, inv in node.filter(jtree.MethodInvocation):
            if inv.member == 'call' or (inv.member or '').startswith('_c_'):
                return True
        return False

    def direct_call_expr(self, node, fname):
        args = None
        direct = None
        for _, inv in node.filter(jtree.MethodInvocation):
            if inv.member == 'call' and len(inv.arguments) == 4:
                args = self.array_elems(inv.arguments[3], None)
            if (inv.member or '').startswith('_c_'):
                direct = inv.member
        if args is None and direct is None:
            return None
        if args is None:
            args = []
        if not fname and direct:
            m = re.match(r'_c_(.+)_\d+$', direct)
            fname = m.group(1) if m and m.group(1) != 'script' else direct
        if not fname or fname.startswith('_c_'):
            return None
        lhs = None
        for _, assign in node.filter(jtree.Assignment):
            if not isinstance(assign.value, jtree.MethodInvocation):
                continue
            if assign.value.member == 'call' or (assign.value.member or '').startswith('_c_'):
                lt = self.expr(assign.expressionl)
                if lt != fname and not lt.startswith('/*') and lt != 'undefined':
                    lhs = lt
        cleaned = [a for a in args if not (isinstance(a, str) and a.startswith("'(") and '#)' in a)]
        call = '%s(%s)' % (fname, ', '.join(cleaned))
        return ('%s = %s' % (lhs, call)) if lhs else call

    def stmt(self, node, ind):
        tn = type(node).__name__
        if tn == 'LocalVariableDeclaration':
            d = node.declarators[0]
            if d.initializer is None:
                return []
            return ['%svar %s = %s;' % (ind, d.name, self.expr(d.initializer))]
        if tn == 'StatementExpression':
            e = node.expression
            text = self.expr(e)
            if text.startswith('/*'):
                return [ind + text]
            return [ind + text + ';']
        if tn == 'IfStatement':
            lines = ['%sif (%s) {' % (ind, self.expr(node.condition))]
            lines += self.stmts(blk(node.then_statement), ind + '  ')
            if node.else_statement is not None:
                lines.append(ind + '} else {')
                lines += self.stmts(blk(node.else_statement), ind + '  ')
            lines.append(ind + '}')
            return lines
        if tn == 'WhileStatement':
            lines = ['%swhile (%s) {' % (ind, self.expr(node.condition))]
            lines += self.stmts(blk(node.body), ind + '  ')
            lines.append(ind + '}')
            return lines
        if tn == 'DoStatement':
            lines = [ind + 'do {']
            lines += self.stmts(blk(node.body), ind + '  ')
            lines.append('%s} while (%s);' % (ind, self.expr(node.condition)))
            return lines
        if tn == 'ForStatement':
            def flat_nodes(n, acc):
                if isinstance(n, (list, tuple)):
                    for y in n:
                        flat_nodes(y, acc)
                elif n is not None:
                    acc.append(n)
                return acc
            init = ''
            if node.control is not None:
                inits = flat_nodes(node.control.init, [])
                vd = None
                vdec = None
                lit = None
                other = []
                for x in inits:
                    if isinstance(x, jtree.VariableDeclaration) and vd is None:
                        vd = x
                    elif isinstance(x, jtree.VariableDeclarator) and vdec is None:
                        vdec = x
                    elif isinstance(x, jtree.Literal) and lit is None:
                        lit = x
                    elif isinstance(x, (jtree.StatementExpression, jtree.Assignment, jtree.MethodInvocation)):
                        other.append(x)
                parts = []
                name = None
                val = None
                if vd is not None and getattr(vd, 'declarators', None):
                    name = vd.declarators[0].name
                    val = vd.declarators[0].initializer
                elif vdec is not None:
                    name = vdec.name
                    val = vdec.initializer
                if name is not None:
                    if val is None:
                        val = lit
                    parts.append('var %s = %s' % (name, self.expr(val) if val is not None else 'undefined'))
                for x in other:
                    parts.append(self.expr(x))
                init = ', '.join(parts)
            cond = self.expr(node.control.condition) if node.control and node.control.condition else ''
            upd = []
            if node.control is not None:
                for x in flat_nodes(node.control.update, []):
                    if isinstance(x, (jtree.StatementExpression, jtree.Assignment, jtree.MethodInvocation)):
                        upd.append(self.expr(x))
            lines = ['%sfor (%s; %s; %s) {' % (ind, init, cond, ', '.join(upd))]
            lines += self.stmts(blk(node.body), ind + '  ')
            lines.append(ind + '}')
            return lines
        if tn == 'ReturnStatement':
            return ['%sreturn %s;' % (ind, self.expr(node.expression) if node.expression is not None else 'undefined')]
        if tn == 'ThrowStatement':
            return ['%sthrow %s;' % (ind, self.expr(node.expression))]
        if tn == 'BreakStatement':
            return [ind + 'break;']
        if tn == 'ContinueStatement':
            return [ind + 'continue;']
        if tn == 'TryStatement':
            lines = [ind + 'try {']
            lines += self.stmts(blk(node.block), ind + '  ')
            if node.catches:
                c = node.catches[0]
                p = c.parameter
                pname = p.name if hasattr(p, 'name') else 'e'
                lines.append('%s} catch (%s) {' % (ind, pname))
                lines += self.stmts(blk(c.block), ind + '  ')
            if node.finally_block:
                lines.append(ind + '} finally {')
                lines += self.stmts(blk(node.finally_block), ind + '  ')
            lines.append(ind + '}')
            return lines
        if tn == 'SynchronizedStatement':
            return self.stmts(blk(node.block), ind)
        if tn == 'BlockStatement':
            return self.stmts(node.statements, ind)
        if tn == 'SwitchStatement':
            lines = ['%sswitch (%s) {' % (ind, self.expr(node.expression))]
            for case in node.cases:
                lines.append('%scase %s:' % (ind + '  ', case_val(case) if case_val(case) is not None else 'default'))
                lines += self.stmts(case.statements, ind + '    ')
            lines.append(ind + '}')
            return lines
        return ['%s/*TODO stmt %s*/' % (ind, tn)]


# ------------------------------------------------------------------ 组装

def top_switches(method):
    out = []
    body = method.body if isinstance(method.body, list) else (method.body.statements if method.body else [])
    for st in body:
        if isinstance(st, jtree.SwitchStatement):
            out.append(st)
        if isinstance(st, jtree.TryStatement):
            for s2 in blk(st.block):
                if isinstance(s2, jtree.SwitchStatement):
                    out.append(s2)
    return out


def blk(x):
    if x is None:
        return []
    if isinstance(x, list):
        return x
    if hasattr(x, 'statements'):
        return x.statements
    return [x]


def jsstr(s):
    out = []
    for ch in s:
        if ch == '\\':
            out.append('\\\\')
        elif ch == "'":
            out.append("\\'")
        elif ch == '\n':
            out.append('\\n')
        elif ch == '\r':
            out.append('\\r')
        elif ch == '\t':
            out.append('\\t')
        elif ord(ch) < 32:
            out.append('\\u%04x' % ord(ch))
        else:
            out.append(ch)
    return "'" + ''.join(out) + "'"


def is_call(node, q, m):
    return isinstance(node, jtree.MethodInvocation) and (node.qualifier or '') == q and node.member == m


def emit_js(path, cls, ctx):
    methods = {md.name: md for _, md in cls.filter(jtree.MethodDeclaration)}
    tr = Translator(ctx)
    lines = []
    header = '// 还原自 com.js.%s' % ctx.classname
    if ctx.source_file:
        header += '  (原脚本: %s)' % ctx.source_file
    lines.append(header)
    lines.append('// 由 EasyClick 编译产物反编译还原; 局部临时变量名为反编译器生成, 逻辑与常量完整')
    lines.append('')

    for name, init in ctx.consts.items():
        try:
            txt = tr.expr(init)
        except Exception:
            continue
        lines.append('var %s = %s;' % (name, txt))
    for name, txt in ctx.regex.items():
        lines.append('var %s = %s;' % (name, txt))
    if ctx.consts or ctx.regex:
        lines.append('')

    ids = sorted(set(list(ctx.method_of_id.keys())))
    for fid in ids:
        if fid == 0:
            continue
        mname = ctx.method_of_id.get(fid)
        md = methods.get(mname)
        if md is None:
            continue
        jsname = ctx.funcnames.get(fid) or '__fn%d' % fid
        pc = ctx.paramcount.get(fid)
        pnames = ctx.paramnames.get(fid, {})
        if pc is None:
            pc = (max(pnames.keys()) + 1) if pnames else 0
        params = []
        for k in range(pc):
            nm = pnames.get(k)
            params.append(nm if nm else 'p%d' % k)
        lines.append('function %s(%s) {' % (jsname, ', '.join(params)))
        mparams = [q.name for q in md.parameters]
        rename = {}
        if len(mparams) >= 6 and mparams[4] == 'obj' and mparams[5] == 'd':
            if len(params) >= 1:
                rename['obj'] = params[0]
                rename['d'] = params[0]
            for k in range(1, len(params)):
                rename['objArr[%d]' % (k - 1)] = params[k]
        else:
            for k in range(len(params)):
                rename['objArr[%d]' % k] = params[k]
        tr.rename = rename
        body = tr.stmts(md.body if md.body else [], '  ')
        lines += body if body else ['  // (空)']
        lines.append('}')
        lines.append('')

    # 顶层脚本
    smethod = methods.get(ctx.method_of_id.get(0, ''))
    if smethod is not None:
        lines.append('// ====================== 顶层脚本 ======================')
        lines.append('(function () {')
        tr.rename = {}
        lines += tr.stmts(smethod.body if smethod.body else [], '  ')
        lines.append('})();')

    open(path, 'w', encoding='utf-8').write('\n'.join(lines))
    return len(ids)


def main():
    src_dir = sys.argv[1]
    out_dir = sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)
    targets = sys.argv[3:] or None
    files = [f for f in os.listdir(src_dir) if f.endswith('.java')]
    files.sort(key=lambda f: -os.path.getsize(os.path.join(src_dir, f)))
    for f in files:
        if targets and f[:-5] not in targets:
            continue
        path = os.path.join(src_dir, f)
        try:
            cls, ctx = parse_file(path)
        except Exception as e:
            print('解析失败', f, e)
            continue
        out = os.path.join(out_dir, f[:-5] + '.js')
        n = emit_js(out, cls, ctx)
        print('%-18s -> %-24s 函数=%d 原名=%d' % (f, os.path.basename(out), n, len([v for v in ctx.funcnames.values() if v])))


if __name__ == '__main__':
    main()
