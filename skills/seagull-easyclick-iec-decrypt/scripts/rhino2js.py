"""
Rhino Java → JS 全自动转译器 v2
将 jadx 反编译的 Rhino NativeFunction Java 源码转译为可执行 JS。

用法: python rhino2js.py <java_file> <output_js>
"""
import re, sys, os, textwrap

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

CONSTANTS = {}
REGEXPS = {}

def parse_constants(java_text):
    for m in re.finditer(r'private static Integer _k(\d+) = (\d+);', java_text):
        CONSTANTS[f'_k{m.group(1)}'] = m.group(2)
    for m in re.finditer(r'private static Double _k(\d+) = OptRuntime\.wrapDouble\(([^)]+)\)', java_text):
        CONSTANTS[f'_k{m.group(1)}'] = m.group(2).rstrip('d')
    for m in re.finditer(r'private static Integer _k(\d+) = -(\d+);', java_text):
        CONSTANTS[f'_k{m.group(1)}'] = f'-{m.group(2)}'

def parse_regexps(java_text):
    for m in re.finditer(r'_re(\d+)_(\d+) = .*?compileRegExp\(context, "(.*?)", "(.*?)"\)', java_text):
        key = f'_re{m.group(1)}_{m.group(2)}'
        pattern = m.group(3).replace('\\\\', '\\')
        flags = m.group(4)
        REGEXPS[key] = f'/{pattern}/{flags}'

def get_function_names(java_text):
    names = {}
    in_func = False
    current_case = None
    for line in java_text.split('\n'):
        if 'public String getFunctionName()' in line:
            in_func = True; continue
        if in_func:
            m = re.match(r'\s*case (\d+):', line)
            if m: current_case = int(m.group(1)); continue
            if 'default:' in line: current_case = -1; continue
            m = re.match(r'\s*return "(.*?)";', line)
            if m and current_case is not None:
                names[current_case] = m.group(1); current_case = None; continue
            if re.match(r'\s*\}\s*$', line) and 'switch' not in line:
                in_func = False
    return names

def get_param_counts(java_text):
    counts = {}
    in_func = False
    pending = []
    for line in java_text.split('\n'):
        if 'public int getParamCount()' in line: in_func = True; continue
        if in_func:
            m = re.match(r'\s*case (\d+):', line)
            if m: pending.append(int(m.group(1))); continue
            if 'default:' in line: pending.append(-1); continue
            m = re.match(r'\s*return (\d+);', line)
            if m:
                for c in pending: counts[c] = int(m.group(1))
                pending = []; continue
            if re.match(r'\s*\}\s*$', line): in_func = False
    return counts

def get_param_var_count(java_text):
    counts = {}
    in_func = False
    pending = []
    for line in java_text.split('\n'):
        if 'public int getParamAndVarCount()' in line: in_func = True; continue
        if in_func:
            m = re.match(r'\s*case (\d+):', line)
            if m: pending.append(int(m.group(1))); continue
            if 'default:' in line: pending.append(-1); continue
            m = re.match(r'\s*return (\d+);', line)
            if m:
                for c in pending: counts[c] = int(m.group(1))
                pending = []; continue
            if re.match(r'\s*\}\s*$', line): in_func = False
    return counts

def get_param_var_names(java_text):
    """Parse getParamOrVarName - handles nested switches"""
    result = {}
    block = ''
    in_func = False
    brace_count = 0
    for line in java_text.split('\n'):
        if 'public String getParamOrVarName(int i)' in line:
            in_func = True; brace_count = 0; continue
        if in_func:
            brace_count += line.count('{') - line.count('}')
            block += line + '\n'
            if brace_count <= 0:
                in_func = False
                break
    
    # Parse the outer switch
    outer_case = None
    inner_cases = {}
    default_name = None
    lines = block.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # Multiple cases falling through to null
        m = re.match(r'case (\d+):', line)
        if m:
            cid = int(m.group(1))
            # Check if next meaningful line is return null or another case or switch
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            next_line = lines[j].strip() if j < len(lines) else ''
            
            if next_line == 'return null;':
                # These ids have no params/vars
                i = j + 1; continue
            elif next_line.startswith('case ') or next_line == 'default:':
                # Fallthrough - this outer case is part of a group
                i += 1; continue
            elif 'switch' in next_line:
                # This outer case has inner switch
                outer_case = cid
                result[cid] = {}
                i = j + 1; continue
            elif next_line.startswith('return "'):
                # Single return, no inner switch
                nm = re.match(r'return "(.*?)";', next_line)
                if nm:
                    result[cid] = {0: nm.group(1)}
                outer_case = None
                i = j + 1; continue
            else:
                outer_case = cid
                result[cid] = {}
                i += 1; continue
        
        # Inner switch cases
        if outer_case is not None:
            m2 = re.match(r'case (\d+):', line)
            if m2:
                inner_idx = int(m2.group(1))
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                next_line = lines[j].strip() if j < len(lines) else ''
                nm = re.match(r'return "(.*?)";', next_line)
                if nm:
                    result[outer_case][inner_idx] = nm.group(1)
                i = j + 1; continue
            if line == 'default:':
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                next_line = lines[j].strip() if j < len(lines) else ''
                nm = re.match(r'return "(.*?)";', next_line)
                if nm:
                    result[outer_case][-1] = nm.group(1)
                outer_case = None
                i = j + 1; continue
        i += 1
    return result

def extract_method_bodies(java_text):
    """Extract each _c_ method body by matching braces"""
    methods = {}
    pattern = re.compile(r'^\s+private static Object (?:m\d+_c_|_c_).*?_(\d+)\(', re.MULTILINE)
    
    for match in pattern.finditer(java_text):
        mid = int(match.group(1))
        start = match.start()
        # Find first {
        brace_start = java_text.index('{', start)
        brace_count = 0
        pos = brace_start
        while pos < len(java_text):
            if java_text[pos] == '{': brace_count += 1
            elif java_text[pos] == '}':
                brace_count -= 1
                if brace_count == 0:
                    methods[mid] = java_text[brace_start+1:pos].strip()
                    break
            pos += 1
    return methods

# ─── Java → JS 转译引擎 ───

def replace_constants(text):
    """Replace _kN with actual values"""
    for k, v in CONSTANTS.items():
        text = re.sub(r'\b' + k + r'\b', v, text)
    return text

def replace_regexps(text):
    for k, v in REGEXPS.items():
        text = text.replace(f'ScriptRuntime.wrapRegExp(cx, scope, {k})', v)
        text = text.replace(f'ScriptRuntime.wrapRegExp(context, scriptableCreateFunctionActivation, {k})', v)
        text = text.replace(f'ScriptRuntime.wrapRegExp(context, scriptableEnterWith', v.rstrip(')'))
    return text

class RhinoTranslator:
    """Translates Java Rhino bytecode patterns to JS"""
    
    def __init__(self, class_name, func_names, param_counts, pv_names, pv_counts):
        self.class_name = class_name
        self.func_names = func_names
        self.param_counts = param_counts
        self.pv_names = pv_names
        self.pv_counts = pv_counts
    
    def translate_body(self, method_body, func_id):
        """Main entry: translate a Java method body to JS statements"""
        # Preprocess
        body = method_body
        body = replace_constants(body)
        
        # Remove boilerplate
        body = re.sub(r'Scriptable \w+ = ScriptRuntime\.createFunctionActivation\([^;]+;', '', body)
        body = re.sub(r'ScriptRuntime\.enterActivationFunction\([^;]+;', '', body)
        body = re.sub(r'ScriptRuntime\.exitActivationFunction\([^;]+;', '', body)
        body = re.sub(r'Object\[\] \w+ = ScriptRuntime\.emptyArgs;', '', body)
        body = re.sub(r'_reInit\(context\);', '', body)
        
        # Remove variable declarations
        body = re.sub(r'(?:Scriptable|Object|Number|Integer|TT_\w+|String|boolean) \w+;?\n', '', body)
        body = re.sub(r'(?:Scriptable|Object|Number|Integer) \w+ = (?:ScriptRuntime\.zeroObj|null|Undefined\.instance);?\n', '', body)
        
        # Process line by line
        lines = body.split('\n')
        js_lines = []
        skip_finally = False
        
        for line in lines:
            translated = self.translate_line(line.strip(), func_id)
            if translated is not None:
                js_lines.append(translated)
        
        return '\n'.join(js_lines)
    
    def translate_line(self, line, func_id):
        """Translate a single Java line to JS"""
        if not line or line == '{' or line == '}':
            return line if line in ('{', '}') else None
        
        # Skip JADX warnings and comments
        if line.startswith('/*') or line.startswith('*') or line.startswith('//'):
            return None
        if line.startswith('try {'):
            return 'try {'
        if line.startswith('} catch'):
            return '} catch(e) {'
        if line.startswith('} finally {') or line.startswith('finally {'):
            return None
        if 'throw th;' in line:
            return None
        
        # Remove trailing semicolons for processing, add back later
        has_semi = line.endswith(';')
        if has_semi:
            line = line[:-1]
        
        result = self._translate_expr(line)
        if result is None:
            return None
        
        if has_semi and result and not result.endswith('{') and not result.endswith('}'):
            result += ';'
        
        return result
    
    def _translate_expr(self, expr):
        """Translate a Java expression to JS"""
        expr = expr.strip()
        if not expr:
            return None
        
        # ─── Control flow ───
        if expr.startswith('while (MathLinker.math_TOBOOLEAN(Boolean.TRUE))'):
            return 'while (true)'
        if expr == 'break':
            return 'break'
        if expr == 'continue':
            return 'continue'
        if expr.startswith('return '):
            val = self._translate_value(expr[7:])
            return f'return {val}'
        if expr == 'return':
            return 'return'
        
        # if conditions
        m = re.match(r'if \((.+)\) \{', expr)
        if m:
            cond = self._translate_condition(m.group(1))
            return f'if ({cond}) {{'
        m = re.match(r'\} else if \((.+)\) \{', expr)
        if m:
            cond = self._translate_condition(m.group(1))
            return f'}} else if ({cond}) {{'
        if expr == '} else {':
            return '} else {'
        
        # while conditions
        m = re.match(r'while \((.+)\) \{', expr)
        if m:
            cond = self._translate_condition(m.group(1))
            return f'while ({cond}) {{'
        
        # for loops
        m = re.match(r'for \((.+)\) \{', expr)
        if m:
            return f'for ({m.group(1)}) {{'
        
        # ─── initFunction (inner function registration) ───
        m = re.match(r'OptRuntime\.initFunction\(new \w+\(\w+, \w+, (\d+)\), \d+, \w+, \w+\)', expr)
        if m:
            fid = int(m.group(1))
            fname = self.func_names.get(fid, f'_anon_{fid}')
            if fname:
                return f'// (registers inner function: {fname})'
            return None
        
        # ─── Function calls ───
        result = self._try_translate_call(expr)
        if result is not None:
            return result
        
        # ─── Assignments ───
        result = self._try_translate_assignment(expr)
        if result is not None:
            return result
        
        # ─── Increment/Decrement ───
        m = re.match(r'ScriptRuntime\.nameIncrDecr\(\w+, "(\w+)", \w+, (\d+)\)', expr)
        if m:
            name = m.group(1)
            mode = int(m.group(2))
            if mode == 0: return f'{name}++'
            elif mode == 1: return f'++{name}'
            elif mode == 2: return f'{name}++'  # post-inc (mode 2 in Rhino = post-inc for nameIncrDecr)
            elif mode == 3: return f'{name}--'
            return f'{name}++'
        
        # ─── enterWith / leaveWith (with(){} scope) ───
        if 'ScriptRuntime.enterWith(' in expr or 'ScriptRuntime.leaveWith(' in expr:
            return None  # Skip scope management
        if 'ScriptRuntime.newCatchScope(' in expr:
            return None
        
        # ─── fillObjectLiteral ───
        if 'ScriptRuntime.fillObjectLiteral(' in expr:
            return None  # Object creation boilerplate
        if 'context.newObject(' in expr:
            return None
        
        # ─── setProp ───
        m = re.match(r'PropLinker\.prop_setObjectProp\(\w+, (.+), \w+, \w+, "(\w+)"\)', expr)
        if m:
            val = self._translate_value(m.group(1))
            prop = m.group(2)
            return f'this.{prop} = {val}'
        
        # ─── Direct inlined function calls: _c_funcName_N(...) ───
        m = re.match(r'_c_(\w+?)_(\d+)\(.*', expr)
        if m:
            fname = m.group(1)
            fid = int(m.group(2))
            actual_name = self.func_names.get(fid, fname)
            # Extract the actual arguments (skip internal params)
            # Pattern: _c_name_id(thisObj, cx, scope, thisScope, arg1, arg2, ..., emptyArgs)
            # The real args start after the 4th param and before ScriptRuntime.emptyArgs
            args_match = re.search(r'\((?:[^,]+, ){4}(.+?)(?:, ScriptRuntime\.emptyArgs)?\)', expr)
            if args_match:
                raw_args = args_match.group(1)
                args = self._split_top_level(raw_args)
                # Filter out Java internal args (double 0.0d, etc)
                js_args = []
                for a in args:
                    a = a.strip()
                    if a in ('0.0d', 'ScriptRuntime.emptyArgs', '0.0'): continue
                    translated = self._translate_value(a)
                    if translated and translated not in ('undefined', '0.0'):
                        js_args.append(translated)
                return f'{actual_name or fname}({", ".join(js_args)})'
            return f'{actual_name or fname}()'
        
        # ─── name_getNameFunctionAndThis + lastStoredScriptable + call = function call ───
        # Pattern: tT_xxx = NameLinker.name_getNameFunctionAndThis(scope, cx, "funcName")
        m = re.match(r'\w+ = NameLinker\.name_getNameFunctionAndThis\(\w+, \w+, "(.+?)"\)', expr)
        if m:
            # Store for next line's .call()
            self._pending_func_call = m.group(1)
            return None
        
        # ScriptRuntime.lastStoredScriptable(context) — skip
        m = re.match(r'\w+ = ScriptRuntime\.lastStoredScriptable\(\w+\)', expr)
        if m:
            return None
        
        # .call(context, scope, thisObj, new Object[]{args})
        m = re.match(r'\w+\.call\(\w+, \w+, \w+, new Object\[\]\{(.+?)\}\)', expr)
        if m and hasattr(self, '_pending_func_call') and self._pending_func_call:
            fname = self._pending_func_call
            self._pending_func_call = None
            args = self._split_top_level(m.group(1))
            js_args = ', '.join(self._translate_value(a) for a in args)
            return f'{fname}({js_args})'
        
        # .call(context, scope, thisObj, emptyArgs) — no args
        m = re.match(r'\w+\.call\(\w+, \w+, \w+, \w+\)', expr)
        if m and hasattr(self, '_pending_func_call') and self._pending_func_call:
            fname = self._pending_func_call
            self._pending_func_call = None
            return f'{fname}()'
        
        # ─── instanceof check (optimization branch, skip) ───
        if 'instanceof TT_ShiPi_Liucheng' in expr or 'instanceof ' + self.class_name in expr:
            return None
        m = re.match(r'if \(\w+ instanceof \w+\) \{', expr)
        if m:
            return None
        
        # ─── _id == N check (optimization branch, skip) ───
        m = re.match(r'if \(\w+\._id == \d+\) \{', expr)
        if m:
            return None
        
        # ─── Scriptable/scope management (skip) ───
        if re.match(r'(?:Scriptable|TT_\w+) \w+ = .+\.getParentScope\(\)', expr):
            return None
        if re.match(r'\w+ = \w+', expr) and ('scriptable' in expr.lower() or 'Scriptable' in expr):
            return None
        
        # ─── ScriptRuntime.padArguments ───
        m = re.match(r'ScriptRuntime\.padArguments\((.+)\)', expr)
        if m:
            return None  # Argument padding, not needed in JS
        
        # ─── Boolean assignments to Java vars ───
        if re.match(r'\w+ = Boolean\.(TRUE|FALSE)', expr):
            return None
        if re.match(r'\w+ = Undefined\.instance', expr):
            return None
        
        # ─── Object array building (for callName) ───
        m = re.match(r'Object\[\] \w+ = new Object\[\d+\]', expr)
        if m:
            return None
        m = re.match(r'\w+\[\d+\] = (.+)', expr)
        if m:
            return None
        
        # ─── More Java internal patterns to skip ───
        # Object/Number/Scriptable declarations
        if re.match(r'(?:Object|Number|Scriptable|Integer|String|boolean|int)\s', expr):
            return None
        if re.match(r'(?:Object|Number)\[\]\s', expr):
            return None
        # Java casts and intermediate vars
        if re.match(r'obj\w* = ', expr):
            return None
        if re.match(r'num\w* = ', expr):
            return None
        # ScriptRuntime.padArguments
        if 'padArguments' in expr:
            return None
        # OptRuntime.wrapDouble
        if 'OptRuntime.wrapDouble' in expr:
            return None
        # fillObjectLiteral
        if 'fillObjectLiteral' in expr:
            return None
        # name_getNameFunctionAndThis that wasn't caught
        m = re.match(r'\w+ = NameLinker\.name_getNameFunctionAndThis\(\w+, \w+, "(.+?)"\)', expr)
        if m:
            self._pending_func_call = m.group(1)
            return None
        # .call with new Object[] inline
        m = re.match(r'\w+\.call\(\w+, \w+, \w+, new Object\[\]\{(.+?)\}\)', expr)
        if m and hasattr(self, '_pending_func_call') and self._pending_func_call:
            fname = self._pending_func_call
            self._pending_func_call = None
            args = self._split_top_level(m.group(1))
            js_args = ', '.join(self._translate_value(a) for a in args)
            return f'{fname}({js_args})'
        # .call without specific args (fallback)
        m = re.match(r'(\w+)\.call\(\w+, \w+, \w+, .+\)', expr)
        if m:
            if hasattr(self, '_pending_func_call') and self._pending_func_call:
                fname = self._pending_func_call
                self._pending_func_call = None
                return f'{fname}()'
            return None
        
        # ─── Self-assignments (Rhino optimization artifacts) ───
        m = re.match(r'(\w+) = \1\s*$', expr)
        if m:
            return None
        
        # ─── TT_xxx variable declarations and self-assignments ───
        if re.match(r'TT_\w+ ', expr):
            return None
        
        # ─── NameLinker.name_setName with Java internal vars ───
        m = re.match(r'NameLinker\.name_setName\((\w+), (.+), \w+, \w+, "(.+?)"\)', expr)
        if m:
            name = m.group(3)
            val = self._translate_value(m.group(2))
            return f'{name} = {val}'
        
        # ─── OptRuntime.call1 deep nesting fallback ───
        # Try harder to parse nested call1 chains
        if expr.startswith('OptRuntime.call1('):
            return self._translate_deep_call1(expr)
        
        # Fallback: return as comment if can't translate
        short = expr[:200] if len(expr) > 200 else expr
        return f'/* TODO: {short} */'
    
    def _translate_deep_call1(self, expr):
        """Handle deeply nested OptRuntime.call1 chains"""
        # Try to extract method chain: obj.method(arg)
        # Pattern: OptRuntime.call1(getPropFunctionAndThis(obj, "method"), lastStored, arg, cx, scope)
        m = re.search(r'prop_getPropFunctionAndThis\((.+?), \w+, \w+, "(\w+)"\)', expr)
        if m:
            inner_obj = m.group(1)
            method = m.group(2)
            # Try to find the argument (3rd param of call1)
            # Split the whole call1
            args = self._split_top_level(expr[len('OptRuntime.call1('):-1])
            if len(args) >= 3:
                arg = self._translate_value(args[2])
                obj = self._translate_value(inner_obj)
                return f'{obj}.{method}({arg})'
        return f'/* TODO: {expr[:200]} */'
    
    def _translate_condition(self, cond):
        """Translate a Java condition expression to JS"""
        cond = cond.strip()
        
        # MathLinker.math_TOBOOLEAN(x)
        m = re.match(r'MathLinker\.math_TOBOOLEAN\((.+)\)', cond)
        if m:
            inner = self._translate_value(m.group(1))
            return inner
        
        # !MathLinker.math_TOBOOLEAN(x)
        m = re.match(r'!MathLinker\.math_TOBOOLEAN\((.+)\)', cond)
        if m:
            inner = self._translate_value(m.group(1))
            return f'!({inner})'
        
        # MathLinker.math_eq / shallowEq
        m = re.match(r'MathLinker\.math_eq\((.+)\)', cond)
        if m:
            args = self._split_top_level(m.group(1))
            if len(args) == 2:
                return f'{self._translate_value(args[0])} == {self._translate_value(args[1])}'
        
        m = re.match(r'MathLinker\.math_shallowEq\((.+)\)', cond)
        if m:
            args = self._split_top_level(m.group(1))
            if len(args) == 2:
                return f'{self._translate_value(args[0])} === {self._translate_value(args[1])}'
        
        # Comparisons
        for op_name, js_op in [('compare_lt', '<'), ('compare_le', '<='), ('compare_gt', '>'), ('compare_ge', '>=')]:
            m = re.match(rf'MathLinker\.math_{op_name}\((.+)\)', cond)
            if m:
                args = self._split_top_level(m.group(1))
                if len(args) == 2:
                    return f'{self._translate_value(args[0])} {js_op} {self._translate_value(args[1])}'
        
        # Combined conditions with &&
        if ' && ' in cond:
            parts = cond.split(' && ')
            return ' && '.join(self._translate_condition(p) for p in parts)
        if ' || ' in cond:
            parts = cond.split(' || ')
            return ' || '.join(self._translate_condition(p) for p in parts)
        
        # Negation
        if cond.startswith('!'):
            return '!' + self._translate_condition(cond[1:])
        
        return self._translate_value(cond)
    
    def _translate_value(self, val):
        """Translate a Java value expression to JS"""
        val = val.strip()
        
        if val in ('Boolean.TRUE', 'true'): return 'true'
        if val in ('Boolean.FALSE', 'false'): return 'false'
        if val == 'Undefined.instance' or val == 'undefined': return 'undefined'
        if val == 'ScriptRuntime.zeroObj' or val == '0': return '0'
        if val == 'OptRuntime.oneObj' or val == '1': return '1'
        if val == '(Object) null' or val == 'null': return 'null'
        if val == 'ScriptRuntime.emptyArgs': return '[]'
        
        # String literals
        m = re.match(r'^"(.*)"$', val)
        if m: return f'"{m.group(1)}"'
        
        # Numeric
        if re.match(r'^-?\d+(\.\d+)?$', val):
            return val
        
        # NameLinker.name_getName → variable reference
        m = re.match(r'NameLinker\.name_getName\(\w+, \w+, "(.+?)"\)', val)
        if m: return m.group(1)
        
        # PropLinker.prop_getObjectProp → obj.prop
        m = re.match(r'PropLinker\.prop_getObjectProp\((.+), \w+, \w+, "(\w+)"\)', val)
        if m: return f'{self._translate_value(m.group(1))}.{m.group(2)}'
        
        # PropLinker.prop_getObjectElem → obj[key]
        m = re.match(r'PropLinker\.prop_getObjectElem\((.+), (.+), \w+, \w+\)', val)
        if m: return f'{self._translate_value(m.group(1))}[{self._translate_value(m.group(2))}]'
        
        # ScriptRuntime.getObjectElem
        m = re.match(r'ScriptRuntime\.getObjectElem\((.+), (.+), \w+\)', val)
        if m: return f'{self._translate_value(m.group(1))}[{self._translate_value(m.group(2))}]'
        
        # Math operations
        m = re.match(r'MathLinker\.math_add\((.+)\)', val)
        if m:
            args = self._split_top_level(m.group(1))
            if len(args) >= 2:
                return f'{self._translate_value(args[0])} + {self._translate_value(args[1])}'
        
        m = re.match(r'ScriptRuntime\.add\((.+)\)', val)
        if m:
            args = self._split_top_level(m.group(1))
            if len(args) >= 2:
                return f'{self._translate_value(args[0])} + {self._translate_value(args[1])}'
        
        m = re.match(r'ScriptRuntime\.subtract\((.+)\)', val)
        if m:
            args = self._split_top_level(m.group(1))
            if len(args) >= 2:
                return f'{self._translate_value(args[0])} - {self._translate_value(args[1])}'
        
        m = re.match(r'ScriptRuntime\.multiply\((.+)\)', val)
        if m:
            args = self._split_top_level(m.group(1))
            if len(args) >= 2:
                return f'{self._translate_value(args[0])} * {self._translate_value(args[1])}'
        
        m = re.match(r'ScriptRuntime\.divide\((.+)\)', val)
        if m:
            args = self._split_top_level(m.group(1))
            if len(args) >= 2:
                return f'{self._translate_value(args[0])} / {self._translate_value(args[1])}'
        
        # MathLinker.math_TONUMERIC → strip (identity in JS)
        m = re.match(r'MathLinker\.math_TONUMERIC\((.+)\)', val)
        if m: return self._translate_value(m.group(1))
        
        # Function calls
        result = self._try_translate_call(val)
        if result is not None:
            return result
        
        # OptRuntime.callProp0 → obj.method()
        m = re.match(r'OptRuntime\.callProp0\((.+), "(\w+)", \w+, \w+\)', val)
        if m:
            obj = self._translate_value(m.group(1))
            method = m.group(2)
            return f'{obj}.{method}()'
        
        # OptRuntime.call1 → obj.method(arg) — improved
        m = re.match(r'OptRuntime\.call1\((.+)\)', val)
        if m:
            args = self._split_top_level(m.group(1))
            if len(args) >= 4:
                func_expr = args[0].strip()
                # Check if it's a getPropFunctionAndThis pattern
                pm = re.match(r'PropLinker\.prop_getPropFunctionAndThis\((.+), \w+, \w+, "(\w+)"\)', func_expr)
                if pm:
                    obj = self._translate_value(pm.group(1))
                    method = pm.group(2)
                    arg = self._translate_value(args[2])
                    return f'{obj}.{method}({arg})'
                return f'{self._translate_value(func_expr)}({self._translate_value(args[2])})'
        
        # OptRuntime.callN → func(arg1, arg2, ...)
        m = re.match(r'OptRuntime\.callN\((.+)\)', val)
        if m:
            args = self._split_top_level(m.group(1))
            if len(args) >= 3:
                func = self._translate_value(args[0])
                call_args = [self._translate_value(a) for a in args[2:-1]]
                return f'{func}({", ".join(call_args)})'
        
        # OptRuntime.callName(new Object[]{...}, "func", cx, scope) inside value position
        m = re.match(r'OptRuntime\.callName\(new Object\[\]\{(.+?)\}, "(.+?)", \w+, \w+\)', val)
        if m:
            func_name = m.group(2)
            args = self._split_top_level(m.group(1))
            translated_args = ', '.join(self._translate_value(a) for a in args)
            return f'{func_name}({translated_args})'
        
        # OptRuntime.callName0 in value position
        m = re.match(r'OptRuntime\.callName0\("(\w+)", \w+, \w+\)', val)
        if m:
            return f'{m.group(1)}()'
        
        # OptRuntime.call2
        m = re.match(r'OptRuntime\.call2\((.+)\)', val)
        if m:
            args = self._split_top_level(m.group(1))
            if len(args) >= 5:
                func_expr = args[0].strip()
                pm = re.match(r'PropLinker\.prop_getPropFunctionAndThis\((.+), \w+, \w+, "(\w+)"\)', func_expr)
                if pm:
                    obj = self._translate_value(pm.group(1))
                    method = pm.group(2)
                    return f'{obj}.{method}({self._translate_value(args[2])}, {self._translate_value(args[3])})'
        
        # ScriptRuntime.typeof / typeofName
        m = re.match(r'ScriptRuntime\.typeofName\(\w+, "(\w+)"\)', val)
        if m: return f'typeof {m.group(1)}'
        m = re.match(r'ScriptRuntime\.typeof\((.+)\)', val)
        if m: return f'typeof {self._translate_value(m.group(1))}'
        
        # OptRuntime.isNullOrUndefined
        m = re.match(r'OptRuntime\.isNullOrUndefined\((.+)\)', val)
        if m: return f'({self._translate_value(m.group(1))} == null)'
        
        # ScriptRuntime.toString
        m = re.match(r'ScriptRuntime\.toString\((.+)\)', val)
        if m: return f'String({self._translate_value(m.group(1))})'
        
        # ScriptRuntime.toNumber
        m = re.match(r'ScriptRuntime\.toNumber\((.+)\)', val)
        if m: return f'Number({self._translate_value(m.group(1))})'
        
        # ScriptRuntime.not
        m = re.match(r'ScriptRuntime\.not\((.+)\)', val)
        if m: return f'!({self._translate_value(m.group(1))})'
        
        # wrapRegExp
        for rkey, rval in REGEXPS.items():
            if rkey in val:
                return rval
        
        # Strip type casts
        val = re.sub(r'\(Scriptable\)\s*', '', val)
        val = re.sub(r'\(Object\)\s*', '', val)
        val = re.sub(r'\(String\)\s*', '', val)
        
        # lastStoredScriptable - skip
        if 'lastStoredScriptable' in val:
            return 'this'
        
        return val
    
    def _try_translate_call(self, expr):
        """Try to translate various call patterns"""
        
        # OptRuntime.callName0("funcName", cx, scope) → funcName()
        m = re.match(r'OptRuntime\.callName0\("(\w+)", \w+, \w+\)', expr)
        if m: return f'{m.group(1)}()'
        
        # ─── EasyClick UI API chain: has(id("xxx")) / has(text("xxx")) ───
        # Pattern: OptRuntime.callName(new Object[]{OptRuntime.callName(new Object[]{"xxx"}, "id/text", cx, scope)}, "has", cx, scope)
        # This is: has(id("xxx")) or has(text("xxx"))
        # Also handles: has(desc("xxx").clz("yyy"))
        
        # OptRuntime.callName(new Object[]{args}, "funcName", cx, scope) → funcName(args)
        m = re.match(r'OptRuntime\.callName\(new Object\[\]\{(.+?)\}, "(.+?)", \w+, \w+\)', expr)
        if m:
            func_name = m.group(2)
            args_str = m.group(1)
            args = self._split_top_level(args_str)
            
            # Translate args, handling nested callName patterns
            translated_args = []
            for a in args:
                ta = self._translate_value(a)
                translated_args.append(ta)
            
            return f'{func_name}({", ".join(translated_args)})'
        
        # OptRuntime.callName(objArr, "funcName", cx, scope) — pre-built array
        m = re.match(r'OptRuntime\.callName\((\w+), "(.+?)", \w+, \w+\)', expr)
        if m:
            return f'{m.group(2)}(...{m.group(1)})'
        
        # OptRuntime.callProp0(obj, "method", cx, scope) → obj.method()
        m = re.match(r'OptRuntime\.callProp0\((.+), "(\w+)", \w+, \w+\)', expr)
        if m:
            obj = self._translate_value(m.group(1))
            return f'{obj}.{m.group(2)}()'
        
        # NameLinker.name_setName(..., value, ..., "name") → name = value
        m = re.match(r'NameLinker\.name_setName\(NameLinker\.name_bind\(\w+, \w+, "(.+?)"\), (.+), \w+, \w+, "(.+?)"\)', expr)
        if m:
            name = m.group(1)
            val = self._translate_value(m.group(2))
            return f'{name} = {val}'
        
        # PropLinker.prop_setObjectProp
        m = re.match(r'PropLinker\.prop_setObjectProp\((.+?), (.+), \w+, \w+, "(\w+)"\)', expr)
        if m:
            obj = self._translate_value(m.group(1))
            val = self._translate_value(m.group(2))
            prop = m.group(3)
            return f'{obj}.{prop} = {val}'
        
        # ScriptRuntime.setObjectElem
        m = re.match(r'ScriptRuntime\.setObjectElem\((.+), (.+), (.+), \w+\)', expr)
        if m:
            args = self._split_top_level(f'{m.group(1)}, {m.group(2)}, {m.group(3)}')
            if len(args) >= 3:
                return f'{self._translate_value(args[0])}[{self._translate_value(args[1])}] = {self._translate_value(args[2])}'
        
        return None
    
    def _try_translate_assignment(self, expr):
        """Try to translate assignment patterns"""
        # Variable assignments with complex RHS
        m = re.match(r'(\w+) = (.+)', expr)
        if m:
            lhs = m.group(1)
            rhs = m.group(2)
            # Skip Java internal variable assignments
            skip_prefixes = ('scriptable', 'tT_', 'obj', 'num', 'regExpProxy')
            if any(lhs.startswith(p) for p in skip_prefixes):
                return None
            # Skip scope/context related
            if 'getParentScope' in rhs or 'lastStoredScriptable' in rhs:
                return None
            if 'enterWith' in rhs or 'leaveWith' in rhs or 'newCatchScope' in rhs:
                return None
            if 'createFunctionActivation' in rhs or 'newObject(scriptable' in rhs:
                return None
            return f'{lhs} = {self._translate_value(rhs)}'
        return None
    
    def _split_top_level(self, text):
        """Split by commas at the top level (respecting parens/brackets)"""
        parts = []
        depth = 0
        current = []
        for ch in text:
            if ch in ('(', '[', '{'):
                depth += 1
                current.append(ch)
            elif ch in (')', ']', '}'):
                depth -= 1
                current.append(ch)
            elif ch == ',' and depth == 0:
                parts.append(''.join(current).strip())
                current = []
            else:
                current.append(ch)
        if current:
            parts.append(''.join(current).strip())
        return parts
    
    def build_function(self, func_id, method_body):
        """Build a complete JS function from method body"""
        fname = self.func_names.get(func_id, '')
        pc = self.param_counts.get(func_id, 0)
        pv = self.pv_names.get(func_id, {})
        total = self.pv_counts.get(func_id, 0)
        
        # Build param list
        params = []
        for i in range(pc):
            if i in pv:
                params.append(pv[i])
            elif -1 in pv and i == 0:
                params.append(pv[-1])
            else:
                params.append(f'arg{i}')
        
        # Build var declarations
        var_names = []
        for i in range(pc, total):
            vn = pv.get(i, pv.get(-1, f'var{i}'))
            if vn not in params and vn not in var_names:
                var_names.append(vn)
        
        # Translate body
        js_body = self.translate_body(method_body, func_id)
        
        # Clean up body
        js_body = self._cleanup(js_body)
        
        # Build function
        param_str = ', '.join(params)
        if fname:
            header = f'function {fname}({param_str})'
        else:
            header = f'function({param_str})'
        
        # Add var declarations
        var_decl = ''
        if var_names:
            var_decl = '    var ' + ', '.join(var_names) + ';\n'
        
        return header, var_decl, js_body
    
    def _cleanup(self, js_text):
        """Clean up translated JS"""
        # Remove empty lines
        lines = [l for l in js_text.split('\n') if l.strip()]
        # Remove scope management leftovers
        lines = [l for l in lines if 'scriptable' not in l.lower() or 'TODO' in l]
        # Remove null assignments from scope vars
        lines = [l for l in lines if not re.match(r'\s*\w+ = undefined;', l)]
        return '\n'.join(lines)


def generate_js(java_path, class_name):
    """Main: read Java, translate all methods, output JS"""
    with open(java_path, 'r', encoding='utf-8') as f:
        java_text = f.read()
    
    parse_constants(java_text)
    parse_regexps(java_text)
    
    func_names = get_function_names(java_text)
    param_counts = get_param_counts(java_text)
    pv_names = get_param_var_names(java_text)
    pv_counts = get_param_var_count(java_text)
    methods = extract_method_bodies(java_text)
    
    translator = RhinoTranslator(class_name, func_names, param_counts, pv_names, pv_counts)
    
    # Determine structure: which functions are top-level vs nested
    # _c_script_0 shows which are top-level (initFunction at script level)
    script_body = methods.get(0, '')
    top_level_ids = set()
    for m in re.finditer(r'new \w+\(\w+, \w+, (\d+)\)', script_body):
        top_level_ids.add(int(m.group(1)))
    
    # id=1 (头条视频流程) is special - constructor that defines this.xxx
    # ids 2-6 are methods assigned inside id=1
    # id=7 (操作流程) registers ids 8,9,13,14,15,17,19 as inner functions
    
    output_lines = [f'// {class_name}.js — 从 {class_name}.java 自动转译']
    
    # Script-level vars
    output_lines.append('var err = [];')
    output_lines.append('var PostCount = 0;')
    output_lines.append('')
    
    # Process each function
    for fid in sorted(methods.keys()):
        if fid == 0:  # script_0 already handled
            continue
        
        fname = func_names.get(fid, '')
        body = methods[fid]
        
        header, var_decl, js_body = translator.build_function(fid, body)
        
        # Add function comment
        if fname:
            output_lines.append(f'// id={fid}: {fname}')
        else:
            output_lines.append(f'// id={fid}: (anonymous)')
        
        output_lines.append(f'{header} {{')
        if var_decl:
            output_lines.append(var_decl.rstrip())
        
        # Indent body
        for bline in js_body.split('\n'):
            if bline.strip():
                output_lines.append(f'    {bline}')
        
        output_lines.append('}')
        output_lines.append('')
    
    return '\n'.join(output_lines)


def main():
    if len(sys.argv) < 2:
        java_path = r'C:\Users\19123\AppData\Local\Temp\opencode\jadx_main_jar\sources\com\js\TT_ShiPi_Liucheng.java'
        out_path = r'C:\Users\19123\AppData\Local\Temp\opencode\test_translated.js'
    else:
        java_path = sys.argv[1]
        out_path = sys.argv[2] if len(sys.argv) > 2 else java_path.replace('.java', '.js')
    
    class_name = os.path.basename(java_path).replace('.java', '')
    print(f"Translating {class_name}...")
    
    js_output = generate_js(java_path, class_name)
    
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(js_output)
    
    print(f"Output: {out_path}")
    print(f"Size: {len(js_output)} bytes, {len(js_output.splitlines())} lines")

if __name__ == '__main__':
    main()
