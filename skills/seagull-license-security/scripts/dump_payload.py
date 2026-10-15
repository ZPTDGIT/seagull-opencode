# -*- coding: utf-8 -*-
"""
只读侦察载荷示例（先 dump 再动手）
由 crack_launcher.py --dump 注入。输出到 %TEMP%\crack_status.txt。

采集内容:
  - 授权管理器活对象: __dict__ 标量字段 + 方法面
  - MainWindow 控件可见性 + content_stack 页数
  - 业务视图类是否存在目标门方法
按目标换类名即可复用。
"""
import gc, os, time, traceback

_RUN_ID = '__RUN_ID__'
_STATUS = os.path.join(os.environ.get('TEMP', 'C:/Windows/Temp'), 'crack_status.txt')


def _log(msg):
    try:
        with open(_STATUS, 'a', encoding='utf-8') as f:
            f.write('[%s][%s] %s\n' % (time.strftime('%H:%M:%S'), _RUN_ID, msg))
    except Exception:
        pass


try:
    am = None
    mw = None
    views = {}
    for o in gc.get_objects():
        try:
            n = type(o).__name__
            if am is None and n == 'AuthManager':       # <- 换目标类名
                am = o
            elif mw is None and n == 'MainWindow':       # <- 换目标类名
                mw = o
            elif n in ('BloggerView', 'VideoView', 'CommentView'):   # <- 换目标视图类
                views.setdefault(n, o)
        except Exception:
            pass

    _log('DUMP pid=%s py=%s' % (os.getpid(), '.'.join(map(str, __import__('sys').version_info[:3]))))
    _log('DUMP AuthManager=%s MainWindow=%s' % (am is not None, mw is not None))
    _log('DUMP views=%s' % ','.join(sorted(views.keys())))

    if am is not None:
        try:
            d = {}
            for k, v in am.__dict__.items():
                if isinstance(v, (bool, int, float, str, type(None))):
                    d[k] = v
                else:
                    d[k] = '<%s>' % type(v).__name__
            _log('DUMP AM.__dict__=' + repr(d))
        except Exception:
            _log('DUMP AM dict err: ' + traceback.format_exc())
        try:
            meths = [m for m in dir(am) if not m.startswith('__') and callable(getattr(am, m, None))]
            _log('DUMP AM callables=' + ','.join(sorted(meths)))
        except Exception:
            pass

    if mw is not None:
        info = []
        for an in ('auth_view', 'sidebar_menu', 'main_splitter', 'content_stack', 'is_authenticated'):
            try:
                w = getattr(mw, an)
            except Exception:
                info.append('%s=ERR' % an)
                continue
            if hasattr(w, 'isVisible'):
                try:
                    info.append('%s.visible=%s' % (an, w.isVisible()))
                except Exception:
                    info.append('%s.visible=?' % an)
            else:
                info.append('%s=%r' % (an, w))
        try:
            cs = mw.content_stack
            info.append('content_count=%s current=%s' % (cs.count(), cs.currentIndex()))
        except Exception:
            pass
        _log('DUMP MW ' + '; '.join(info))

    for n, v in views.items():
        try:
            _log('DUMP view %s has_target_gate=%s' % (n, hasattr(type(v), '_verify_collection_session_token')))
        except Exception:
            pass
except Exception:
    _log('DUMP fatal: ' + traceback.format_exc())

_log('DONE')
