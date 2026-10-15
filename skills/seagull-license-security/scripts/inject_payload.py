# -*- coding: utf-8 -*-
"""
注入载荷示例（战例 TKPro采集器：易速云云验证全链恒真）
由 crack_launcher.py 经 frida PyRun_SimpleString 注入目标 CPython 进程执行。

 适配指南（换目标时改这些）:
  1. _scan(): 换目标类名（授权管理器 / MainWindow / 业务视图类）
  2. _BACKEND: 换目标授权方法的恒真化清单
  3. _USER: 伪造的登录态 user_info（dict 子类 __missing__ 兜底 + 常见 key 预填）
  4. _patch_views(): 换目标功能门方法名
  5. 状态文件路径 ≤ 与 launcher 的 STATUS_NAME 保持一致

原理要点:
  - 实例级 + 类级双 patch（现有对象 / 之后新建对象都覆盖）
  - UI 挂载只 emit 信号（Qt 队列连接跨线程安全），不直接跨线程调 GUI 槽
  - 后台线程干活（等对象/轮询），注入口立即返回
  - '__RUN_ID__' 占位由 launcher 替换，用于状态文件防串台
"""
import gc, os, time, threading, traceback

_RUN_ID = '__RUN_ID__'
_STATUS = os.path.join(os.environ.get('TEMP', 'C:/Windows/Temp'), 'crack_status.txt')


def _log(msg):
    try:
        with open(_STATUS, 'a', encoding='utf-8') as f:
            f.write('[%s][%s] %s\n' % (time.strftime('%H:%M:%S'), _RUN_ID, msg))
    except Exception:
        pass


class _Info(dict):
    def __missing__(self, k):
        return '2036-12-31 23:59:59'


_USER = _Info({
    'card_key': 'LOCAL-2036',
    'expire_time': '2036-12-31 23:59:59',
    'expired_at': '2036-12-31 23:59:59',
    'expire_at': '2036-12-31 23:59:59',
    'end_time': '2036-12-31 23:59:59',
    'end_date': '2036-12-31 23:59:59',
    'expiration': '2036-12-31 23:59:59',
    'remaining_days': 3650,
    'days': 3650,
    'status': 'active',
    'is_active': True,
    'subscription': 'active',
    'subscription_status': 'active',
})


def _T(*a, **k):
    return True


def _F(*a, **k):
    return False


def _N(*a, **k):
    return None


# ---- 换目标时改: 授权管理器方法 → 恒真化处理 ----
_BACKEND = (
    ('_validate_card_expiry', _T),
    ('_call_login_api', _T),
    ('auto_login', _T),
    ('has_saved_card_key', _T),
    ('should_show_login_dialog', _F),
    ('_send_heartbeat', _T),
    ('_should_trigger_heartbeat_failure', _F),
    ('_handle_heartbeat_request_failure', _N),
)


def _scan():
    """按类名找活对象（Nuitka 编译类无 import 必要，用 type(o).__name__）。"""
    am = None
    mw = None
    for o in gc.get_objects():
        try:
            n = type(o).__name__
            if am is None and n == 'AuthManager':      # <- 换目标类名
                am = o
            elif mw is None and n == 'MainWindow':      # <- 换目标类名
                mw = o
        except Exception:
            pass
    return am, mw


def _patch_backend(am):
    inst_ok = 0
    for name, fn in _BACKEND:
        try:
            setattr(am, name, fn)
            inst_ok += 1
        except Exception:
            pass
    # 类级补刀: 覆盖后续新建实例
    try:
        for name, fn in _BACKEND:
            try:
                setattr(type(am), name, fn)
            except Exception:
                pass
    except Exception:
        pass
    try:
        am.get_auth_status = lambda *a, **k: {'is_logged_in': True, 'card_key': 'LOCAL-2036', 'user_info': dict(_USER)}
    except Exception:
        pass
    try:
        am.is_logged_in = True
        am.card_key = 'LOCAL-2036'
        am.token = 'LOCAL-TOKEN-OK'
        am.user_info = _USER
    except Exception:
        _log('field set err: ' + traceback.format_exc())
    return inst_ok


def _patch_views():
    """功能门（如采集会话令牌）: 扫视图类的方法恒真。"""
    got = set()
    try:
        for o in gc.get_objects():
            try:
                n = type(o).__name__
                if n in ('BloggerView', 'VideoView', 'CommentView'):   # <- 换目标视图类
                    t = type(o)
                    if not getattr(t, '_tkpro_ok', False) and hasattr(t, '_verify_collection_session_token'):
                        t._verify_collection_session_token = _T       # <- 换目标门方法
                        t._tkpro_ok = True
                        got.add(n)
            except Exception:
                pass
    except Exception:
        pass
    return got


def _report_ui():
    try:
        am2, mw2 = _scan()
        if mw2 is None:
            _log('UI MainWindow not found')
            return
        info = []
        for an in ('auth_view', 'sidebar_menu', 'main_splitter', 'content_stack'):
            w = getattr(mw2, an, None)
            if w is None:
                info.append('%s=NA' % an)
            elif hasattr(w, 'isVisible'):
                try:
                    info.append('%s=%s' % (an, w.isVisible()))
                except Exception:
                    info.append('%s=?' % an)
            else:
                info.append('%s=%r' % (an, w))
        try:
            info.append('content_idx=%s' % mw2.content_stack.currentIndex())
        except Exception:
            pass
        try:
            info.append('is_authenticated=%s' % getattr(mw2, 'is_authenticated', 'NA'))
        except Exception:
            pass
        _log('UI ' + '; '.join(info))
    except Exception:
        _log('UI report err: ' + traceback.format_exc())


def _main():
    _log('installer start pid=%s' % os.getpid())
    deadline = time.time() + 180
    am = None
    mw = None
    while time.time() < deadline:
        am, mw = _scan()
        if am is not None:
            break
        time.sleep(1.5)
    if am is None:
        _log('FAIL AuthManager not found')
        return
    _log('AuthManager found')
    n = _patch_backend(am)
    _log('backend patched methods=%d' % n)
    first = _patch_views()
    _log('views pass1=%s' % (','.join(sorted(first)) if first else 'none'))
    dl2 = time.time() + 90
    while time.time() < dl2 and mw is None:
        _, mw = _scan()
        if mw is None:
            time.sleep(1)
    try:
        am.login_success.emit(_USER)      # 只 emit 信号挂载 UI, 不跨线程直调 GUI 槽
        _log('emit login_success (mw=%s)' % (mw is not None))
    except Exception:
        _log('emit err: ' + traceback.format_exc())
    for i in range(4):                     # 视图类可能登录后才创建, 延迟补扫
        time.sleep(1.5)
        g = _patch_views()
        if g:
            _log('views pass%s=%s' % (i + 2, ','.join(sorted(g))))
    time.sleep(1.0)
    _report_ui()
    _log('DONE')


try:
    t = threading.Thread(target=_main)
    t.daemon = True
    t.start()
    _log('payload loaded, installer thread spawned')
except Exception:
    _log('fatal: ' + traceback.format_exc())
