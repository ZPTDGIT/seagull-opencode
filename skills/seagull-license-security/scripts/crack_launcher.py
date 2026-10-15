# -*- coding: utf-8 -*-
"""
Seagull 通用破解启动器（Nuitka OneFile / 内嵌 CPython GUI 目标）

用法:
    python crack_launcher.py [目标程序.exe] [--attach] [--dump]
    - 默认: 找目标(自己同目录/cwd) → 已有实例则直接注入, 否则启动 → 识别 CPython GUI 子进程 → 注入
    - --attach: 只对已在运行的目标注入
    - --dump:   只读侦察(需配 dump_payload.py)
环境变量:
    CRACK_APP_NAME=目标程序.exe   指定目标 exe 名

打包(PyInstaller, frida 进包):
    pyinstaller --onefile --console --name 破解启动器 --icon app.ico ^
      --add-data "inject_payload.py;." --add-data "dump_payload.py;." crack_launcher.py

实测要点见 references/nuitka-runtime-crack.md:
    - 认进程用模块判据(python3xx.dll + Qt*Widgets), 不能用体积
    - 子进程刚出生模块没加载完 → 探测要退避重试, 不能一次失败就拉黑
    - 注入rc=0后等状态文件 DONE, 然后 detach; patch 驻留在进程内, frida 断开不失效
"""
import os
import sys
import time
import ctypes
import random
import subprocess
from ctypes import wintypes

APP_NAME = os.environ.get('CRACK_APP_NAME', '目标程序.exe')
STATUS_NAME = 'crack_status.txt'

JS = r"""
function findPy() {
    var mods = Process.enumerateModules();
    for (var i = 0; i < mods.length; i++) {
        var n = mods[i].name.toLowerCase();
        if (/^python3\d+\.dll$/.test(n)) return mods[i];
    }
    return Process.getModuleByName('python3.dll');
}
rpc.exports = {
    mods: function () {
        var out = [];
        try {
            Process.enumerateModules().forEach(function (m) { out.push(m.name); });
        } catch (e) { out.push('ERR:' + e); }
        return out;
    },
    runpy: function (code) {
        var mod = findPy();
        var ensure = new NativeFunction(mod.getExportByName('PyGILState_Ensure'), 'pointer', []);
        var release = new NativeFunction(mod.getExportByName('PyGILState_Release'), 'void', ['pointer']);
        var run = new NativeFunction(mod.getExportByName('PyRun_SimpleString'), 'int', ['pointer']);
        var gil = ensure();
        var rc = -1;
        try {
            rc = run(Memory.allocUtf8String(code));
        } catch (e) {
            rc = -999;
        } finally {
            release(gil);
        }
        return rc;
    }
};
"""


def base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def load_text(name):
    cands = []
    if getattr(sys, 'frozen', False):
        cands.append(os.path.join(sys._MEIPASS, name))
    cands.append(os.path.join(base_dir(), name))
    for c in cands:
        if os.path.isfile(c):
            with open(c, 'r', encoding='utf-8') as f:
                return f.read()
    raise RuntimeError('missing payload: %s' % name)


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ('dwSize', wintypes.DWORD),
        ('cntUsage', wintypes.DWORD),
        ('th32ProcessID', wintypes.DWORD),
        ('th32DefaultHeapID', ctypes.c_void_p),
        ('th32ModuleID', wintypes.DWORD),
        ('cntThreads', wintypes.DWORD),
        ('th32ParentProcessID', wintypes.DWORD),
        ('pcPriClassBase', ctypes.c_long),
        ('dwFlags', wintypes.DWORD),
        ('szExeFile', wintypes.WCHAR * 260),
    ]


def list_procs():
    # 注意: x64 下 HANDLE 必须显式声明 restype, 否则句柄被 int 截断
    TH32CS_SNAPPROCESS = 2
    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k32.Process32FirstW.restype = wintypes.BOOL
    k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    k32.Process32NextW.restype = wintypes.BOOL
    k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    procs = []
    if not snap or snap == wintypes.HANDLE(-1).value:
        return procs
    pe = PROCESSENTRY32W()
    pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    ok = k32.Process32FirstW(snap, ctypes.byref(pe))
    while ok:
        procs.append((int(pe.th32ProcessID), int(pe.th32ParentProcessID), pe.szExeFile))
        ok = k32.Process32NextW(snap, ctypes.byref(pe))
    k32.CloseHandle(snap)
    return procs


def probe_pid(device, pid):
    """注入探测: 命中 内嵌python + GUI框架 的进程返回 (session, script), 否则 None。"""
    session = device.attach(pid)
    script = session.create_script(JS)
    script.load()
    mods = script.exports_sync.mods()
    low = [str(m).lower() for m in mods]
    has_py = any(m.startswith('python3') and m.endswith('.dll') for m in low)
    has_gui = any(('qt6widgets' in m) or ('qtwidgets' in m) or ('qt5widgets' in m) or ('pyside' in m) for m in low)
    if has_py and has_gui:
        return session, script
    try:
        script.unload()
    except Exception:
        pass
    try:
        session.detach()
    except Exception:
        pass
    return None, None


def find_gui_child(device, outer_pid, timeout=150):
    """在 outer_pid 的子进程里找 GUI 真身。退避重试(2.5s), 防止模块未加载完误判。"""
    deadline = time.time() + timeout
    next_try = {}
    while time.time() < deadline:
        now = time.time()
        for pid, ppid, name in list_procs():
            if ppid != outer_pid:
                continue
            if next_try.get(pid, 0) > now:
                continue
            next_try[pid] = now + 2.5
            try:
                session, script = probe_pid(device, pid)
            except Exception:
                continue
            if session is not None:
                return pid, session, script
        time.sleep(0.6)
    return None, None, None


def find_existing_gui(device, timeout=10):
    """按名字找已运行实例的 GUI 真身(快速轮询)。"""
    deadline = time.time() + timeout
    next_try = {}
    while time.time() < deadline:
        now = time.time()
        for pid, ppid, name in list_procs():
            if name != APP_NAME:
                continue
            if next_try.get(pid, 0) > now:
                continue
            next_try[pid] = now + 2.5
            try:
                session, script = probe_pid(device, pid)
            except Exception:
                continue
            if session is not None:
                return pid, session, script
        time.sleep(0.8)
    return None, None, None


def status_path():
    tmp = os.environ.get('TEMP') or os.environ.get('TMP') or 'C:/Windows/Temp'
    return os.path.join(tmp, STATUS_NAME)


def wait_status(path, run_id, timeout=180, printer=print):
    deadline = time.time() + timeout
    done = False
    pos = 0
    while time.time() < deadline:
        if os.path.isfile(path):
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    f.seek(pos)
                    chunk = f.read()
                    pos = f.tell()
                for line in chunk.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    if ('[%s]' % run_id) in line:
                        printer('    ' + line)
                        if 'DONE' in line or 'FAIL' in line:
                            done = True
            except Exception:
                pass
        if done:
            return True
        time.sleep(0.6)
    return done


def do_inject(device, session, script, child_pid, payload_name, timeout=180):
    print('[+] 找到 CPython GUI 子进程 PID=%d' % child_pid)
    run_id = '%06x' % random.randrange(16 ** 6)
    payload = load_text(payload_name).replace('__RUN_ID__', run_id)
    path = status_path()
    try:
        os.remove(path)
    except Exception:
        pass
    print('[*] 注入载荷...')
    rc = script.exports_sync.runpy(payload)
    print('[*] payload rc=%s，等待内部安装器完成...' % rc)
    ok = wait_status(path, run_id, timeout=timeout)
    try:
        session.detach()
    except Exception:
        pass
    return ok


def pause_exit(seconds=8, ok=False):
    if not sys.stdin or not sys.stdin.isatty():
        return
    if not ok:
        try:
            input('按回车退出...')
        except Exception:
            pass
        return
    print('\n[*] %d 秒后自动关闭本窗口（目标程序继续运行）' % seconds)
    try:
        import msvcrt
        for _ in range(seconds * 10):
            if msvcrt.kbhit():
                msvcrt.getch()
                break
            time.sleep(0.1)
    except Exception:
        time.sleep(seconds)


def main():
    global APP_NAME
    args = sys.argv[1:]
    mode = 'launch'
    for a in args:
        if a == '--attach':
            mode = 'attach'
        elif a == '--dump':
            mode = 'dump'
        elif not a.startswith('--'):
            APP_NAME = a
    print('=' * 56)
    print(' 破解启动器 (Nuitka/嵌入CPython GUI)')
    print('=' * 56)
    import frida
    device = frida.get_local_device()

    if mode == 'dump':
        pid, session, script = find_existing_gui(device)
        if pid is None:
            print('[-] 未找到正在运行的目标')
            pause_exit()
            return
        print('[+] 目标 PID=%d，只读侦察...' % pid)
        do_inject(device, session, script, pid, 'dump_payload.py', timeout=90)
        pause_exit(ok=True)
        return

    if mode == 'attach':
        pid, session, script = find_existing_gui(device)
        if pid is None:
            print('[-] 未找到正在运行的目标，先启动再试')
            pause_exit()
            return
        ok = do_inject(device, session, script, pid, 'inject_payload.py')
        print('[%s] 完成' % ('+' if ok else '-'))
        pause_exit(ok=ok)
        return

    app = None
    for c in (os.path.join(base_dir(), APP_NAME), os.path.join(os.getcwd(), APP_NAME)):
        if os.path.isfile(c):
            app = c
            break
    if app is None:
        print('[-] 未找到 %s' % APP_NAME)
        print('    请把本程序放到目标 exe 同目录再运行')
        pause_exit()
        return

    pid, session, script = find_existing_gui(device)
    if pid is not None:
        print('[!] 检测到目标已在运行 PID=%d，直接注入' % pid)
        ok = do_inject(device, session, script, pid, 'inject_payload.py')
        print('[%s] 完成' % ('+' if ok else '-'))
        pause_exit(ok=ok)
        return

    print('[*] 启动: %s' % app)
    proc = subprocess.Popen([app], cwd=os.path.dirname(app))
    outer = proc.pid
    print('[*] 外层引导 PID=%d，等待 CPython GUI 子进程...' % outer)
    child, session, script = find_gui_child(device, outer, timeout=150)
    if child is None:
        print('[-] 未找到 GUI 子进程，启动失败或超时')
        pause_exit()
        return
    ok = do_inject(device, session, script, child, 'inject_payload.py')
    if ok:
        print('[+] 完成：破解已生效')
    else:
        print('[-] 超时，请把上面日志截图反馈')
    pause_exit(ok=ok)


if __name__ == '__main__':
    main()
