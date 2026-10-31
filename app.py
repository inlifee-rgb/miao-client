"""DORIMI for WorkBuddy — 桌面端

形态与 FoxToken 一致：原生窗口 + WebView2 渲染 HTML。
窗口里跑的就是 console/app.html，同一套设计系统，不另做一套 UI。

职责：
  · 内嵌启动 gateway（余额、用量、兑换、下单都在里面）
  · 原生桥：写 models.json、打开 WorkBuddy、打开网页控制台

用法：
  python app.py              正常启动
  python app.py --debug      打开调试
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser

if getattr(sys, 'frozen', False):
    BASE = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
else:
    BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.dirname(BASE))   # gen_models.py 在上一级

import gateway  # noqa: E402
import gen_models  # noqa: E402

# ─────────────── 版本与更新 ───────────────
APP_NAME = 'MIAO for WorkBuddy'
APP_VERSION = '1.1.5'                      # 当前安装版本（每次打包必须 +1）
GATEWAY_BASE = 'http://127.0.0.1:18085'    # MIAO 自研网关（不再依赖 new-api）
VERSION_URL = GATEWAY_BASE + '/api/version'
DOWNLOAD_URL = GATEWAY_BASE + '/download/MIAO.zip'
APP_DATA = os.path.join(os.path.expanduser('~'), '.workbuddy', 'miao_app')
os.makedirs(APP_DATA, exist_ok=True)       # WebView2 持久化存储目录（localStorage/cookies）


def _http_get(url, timeout=10):
    """极简 HTTP GET（pywebview 环境里 urllib 足够，不引 requests）"""
    import urllib.request
    req = urllib.request.Request(url, headers={'User-Agent': 'MIAO-Updater/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read(), dict(r.headers)


try:
    import webview
except Exception as e:  # pragma: no cover
    print('[X] 缺少 pywebview:', e)
    raise


IS_MAC = sys.platform == 'darwin'
IS_WIN = sys.platform.startswith('win')


def models_path():
    return os.path.join(os.path.expanduser('~'), '.workbuddy', 'models.json')


def exe_candidates():
    """WorkBuddy 主程序的常见位置，按优先级（Windows / macOS 双平台）"""
    if IS_MAC:
        return [
            '/Applications/WorkBuddy.app',
            os.path.expanduser('~/Applications/WorkBuddy.app'),
        ]
    return [
        r'E:\Program Files\WorkBuddy\WorkBuddy.exe',
        r'C:\Program Files\WorkBuddy\WorkBuddy.exe',
        os.path.expandvars(r'%LOCALAPPDATA%\Programs\WorkBuddy\WorkBuddy.exe'),
        os.path.expandvars(r'%LOCALAPPDATA%\WorkBuddy\WorkBuddy.exe'),
    ]


def open_workbuddy_app():
    """启动 WorkBuddy：Windows 用 startfile，macOS 用 open -a"""
    if IS_MAC:
        for app in exe_candidates():
            if os.path.exists(app):
                subprocess.Popen(['open', '-a', app])
                return {'ok': True, 'path': app}
        # 兜底：按应用名启动（装在非标准路径也能起）
        r = subprocess.run(['open', '-a', 'WorkBuddy'], capture_output=True)
        if r.returncode == 0:
            return {'ok': True, 'path': 'WorkBuddy'}
        return {'ok': False, 'message': '未找到 WorkBuddy.app，请先从 workbuddy.cn 安装'}
    for exe in exe_candidates():
        if os.path.isfile(exe):
            try:
                os.startfile(exe)  # noqa: S606
                return {'ok': True, 'path': exe}
            except Exception as e:
                return {'ok': False, 'message': str(e)[:120]}
    return {'ok': False, 'message': '未找到 WorkBuddy 安装位置'}


class Api:
    def __init__(self):
        self.port = 0

    # ---------- 状态 ----------
    def get_state(self):
        p = models_path()
        key, count, configured = '', 0, False
        if os.path.isfile(p):
            try:
                data = json.load(open(p, encoding='utf-8'))
                count = len(data)
                for x in data:
                    k = x.get('apiKey') or ''
                    if str(x.get('id', '')).startswith('Miao:') and k.startswith('sk-'):
                        key = k
                        configured = True
                        break
            except Exception:
                pass
        return {'ok': True, 'configured': configured, 'count': count,
                'key': key, 'path': p, 'version': APP_VERSION}

    # ---------- 写配置 ----------
    def apply_config(self, key):
        key = (key or '').strip()
        if not key.startswith('sk-'):
            return {'ok': False, 'message': '密钥格式不对，应以 sk- 开头'}
        p = models_path()
        if not os.path.isdir(os.path.dirname(p)):
            return {'ok': False, 'message': '没找到 .workbuddy 目录，请先启动一次 WorkBuddy'}

        backup = ''
        keep = []
        if os.path.isfile(p):
            try:
                backup = p + '.bak-' + time.strftime('%Y%m%d-%H%M%S')
                shutil.copy2(p, backup)
                for x in json.load(open(p, encoding='utf-8')):
                    mid = str(x.get('id', ''))
                    if not mid.startswith('Miao:') and not mid.startswith('miao_'):
                        keep.append(x)
            except Exception:
                pass

        data = gen_models.build('Miao', gateway_default_url(), key) + keep
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return {'ok': True, 'count': len(data), 'kept': len(keep),
                'backup': os.path.basename(backup) if backup else '', 'path': p}

    # ---------- 检测更新 ----------
    def check_update(self):
        """查网关 /api/version，返回 {has_update, latest, current, notes, url}"""
        try:
            st, raw, _h = _http_get(VERSION_URL, timeout=8)
            if st != 200:
                return {'ok': False, 'message': '网关版本接口不可用（HTTP %d）' % st}
            v = json.loads(raw.decode('utf-8'))
            latest = str(v.get('latest', ''))
            if not latest:
                return {'ok': False, 'message': '版本信息不完整'}
            has = _ver_cmp(latest, APP_VERSION) > 0
            return {
                'ok': True, 'has_update': has,
                'current': APP_VERSION, 'latest': latest,
                'notes': v.get('notes', []),
                'url': (GATEWAY_BASE + v.get('url', '')) if v.get('url') else DOWNLOAD_URL,
            }
        except Exception as e:
            return {'ok': False, 'message': '检查更新失败：%s' % str(e)[:120]}

    def download_update(self, url=None, to_dir=None):
        """下载新版安装包（onedir → zip 分发）到 to_dir（默认 App 同目录 downloads/）
        返回 {ok, path, size, kind}；kind='zip' 时 apply_update 走目录替换"""
        url = url or DOWNLOAD_URL
        to_dir = to_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'downloads')
        try:
            os.makedirs(to_dir, exist_ok=True)
            kind = 'zip' if url.endswith('.zip') else 'exe'
            target = os.path.join(to_dir, 'MIAO.%s' % ('zip' if kind == 'zip' else 'exe'))
            st, raw, _h = _http_get(url, timeout=180)
            if st != 200:
                return {'ok': False, 'message': '下载失败（HTTP %d）' % st}
            tmp = target + '.part'
            with open(tmp, 'wb') as f:
                f.write(raw)
            os.replace(tmp, target)
            return {'ok': True, 'path': target, 'size': len(raw), 'kind': kind}
        except Exception as e:
            return {'ok': False, 'message': '下载失败：%s' % str(e)[:120]}

    def apply_update(self, pkg_path=None, current_exe=None):
        """应用更新：
        - zip（onedir）：解压到 App 同目录 MIAO_new/，bat 等旧进程退出后整目录替换
        - exe（onefile）：bat 等旧进程退出后单文件替换
        返回 {ok, message}；bat 立即启动，不阻塞"""
        pkg_path = pkg_path or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'downloads', 'MIAO.zip')
        current_exe = current_exe or sys.executable
        if not os.path.isfile(pkg_path):
            return {'ok': False, 'message': '未找到下载好的新版本安装包'}
        if os.path.abspath(pkg_path).lower() == os.path.abspath(current_exe).lower():
            return {'ok': False, 'message': '安装包与当前程序相同，无需替换'}

        app_dir = os.path.dirname(current_exe)          # MIAO.exe 所在目录（onedir 根）
        is_zip = pkg_path.lower().endswith('.zip')
        if IS_MAC:
            # macOS：.app 结构整体替换，交给 shell 脚本延迟执行
            return self._apply_update_mac(pkg_path)
        try:
            if is_zip:
                # 解压到 MIAO_new/，bat 负责等退出 → 替换目录 → 启动
                import zipfile
                new_dir = os.path.join(app_dir, 'MIAO_new')
                if os.path.isdir(new_dir):
                    import shutil
                    shutil.rmtree(new_dir, ignore_errors=True)
                os.makedirs(new_dir, exist_ok=True)
                with zipfile.ZipFile(pkg_path) as zf:
                    zf.extractall(new_dir)
                exe_name = 'MIAO.exe'
                new_exe = os.path.join(new_dir, exe_name)
                if not os.path.isfile(new_exe):
                    return {'ok': False, 'message': '更新包结构不正确：缺少 %s' % exe_name}

                bat = os.path.join(app_dir, 'miao_update.bat')
                cur = '"%s"' % current_exe
                new = '"%s"' % new_exe
                cur_dir = '"%s"' % app_dir
                new_dir_q = '"%s"' % new_dir
                # 等旧进程退出 → 目录级替换（删旧 _internal 拷贝新目录）→ 启动
                lines = [
                    '@echo off',
                    'chcp 65001 >nul',
                    'title MIAO 更新中...',
                    'echo 正在更新 MIAO，请稍候...',
                    ':wait',
                    'tasklist /FI "IMAGENAME eq MIAO.exe" 2>nul | find /i "MIAO.exe" >nul',
                    'if errorlevel 1 goto do_copy',
                    'timeout /t 1 /nobreak >nul',
                    'goto wait',
                    ':do_copy',
                    'if exist %cur_dir%\\_internal rd /s /q %cur_dir%\\_internal',
                    'copy /y %new_dir_q%\\_internal %cur_dir%\\_internal >nul',
                    'copy /y %new% %cur% >nul',
                    'if errorlevel 1 (echo 替换失败：文件被占用 & pause & exit /b 1)',
                    'rd /s /q %new_dir_q% >nul 2>nul',
                    'start "" %cur%',
                    'exit',
                ]
            else:
                bat = os.path.join(os.path.dirname(pkg_path), 'miao_update.bat')
                cur = '"%s"' % current_exe
                new = '"%s"' % pkg_path
                lines = [
                    '@echo off',
                    'chcp 65001 >nul',
                    'title MIAO 更新中...',
                    'echo 正在更新 MIAO，请稍候...',
                    ':wait',
                    'tasklist /FI "IMAGENAME eq MIAO.exe" 2>nul | find /i "MIAO.exe" >nul',
                    'if errorlevel 1 goto do_copy',
                    'timeout /t 1 /nobreak >nul',
                    'goto wait',
                    ':do_copy',
                    'copy /y %s %s >nul' % (new, cur),
                    'if errorlevel 1 (echo 替换失败：文件被占用 & pause & exit /b 1)',
                    'start "" %s' % cur,
                    'exit',
                ]
            with open(bat, 'w', encoding='utf-8') as f:
                f.write('\r\n'.join(lines))
            import subprocess
            subprocess.Popen(['cmd.exe', '/c', bat],
                             creationflags=0x08000000,  # CREATE_NO_WINDOW
                             close_fds=True)
            return {'ok': True, 'message': '更新已开始，程序将自动重启', 'bat': bat}
        except Exception as e:
            return {'ok': False, 'message': '更新失败：%s' % str(e)[:120]}

    def _apply_update_mac(self, pkg_path):
        """macOS 更新：解压到临时目录 → 后台脚本等进程退出 → 替换 .app → 重启"""
        import tempfile
        import zipfile
        exe = os.path.abspath(sys.executable)          # .../MIAO.app/Contents/MacOS/MIAO
        app_path = os.path.dirname(os.path.dirname(exe))
        if not app_path.endswith('.app'):
            return {'ok': False, 'message': '当前不在 .app 内运行，无法自动替换，请手动安装'}
        try:
            tmp = tempfile.mkdtemp(prefix='miao_upd_')
            with zipfile.ZipFile(pkg_path) as zf:
                zf.extractall(tmp)
            new_app = None
            for root, dirs, _ in os.walk(tmp):
                for d in dirs:
                    if d.endswith('.app'):
                        new_app = os.path.join(root, d)
                        break
                if new_app:
                    break
            if not new_app:
                return {'ok': False, 'message': '更新包里没有 .app'}
            sh = os.path.join(tmp, 'update.sh')
            with open(sh, 'w', encoding='utf-8') as f:
                f.write('#!/bin/bash\n')
                f.write('sleep 1\n')
                f.write('while pgrep -x MIAO >/dev/null 2>&1; do sleep 1; done\n')
                f.write('rm -rf "%s"\n' % app_path)
                f.write('cp -R "%s" "%s"\n' % (new_app, app_path))
                f.write('xattr -dr com.apple.quarantine "%s" 2>/dev/null\n' % app_path)
                f.write('open "%s"\n' % app_path)
            os.chmod(sh, 0o755)
            subprocess.Popen(['/bin/bash', sh], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {'ok': True, 'message': '更新已开始，程序将自动重启'}
        except Exception as e:
            return {'ok': False, 'message': '更新失败：%s' % str(e)[:120]}

    # ---------- 原生动作 ----------
    def open_workbuddy(self):
        return open_workbuddy_app()

    def open_web_console(self):
        # MIAO 网页控制台（自研，不再依赖 new-api / ai.dorimi.cn）
        webbrowser.open('http://127.0.0.1:18300/index.html')
        return {'ok': True}

    def copy_text(self, text):
        try:
            s = str(text)
            if IS_MAC:
                subprocess.run(['pbcopy'], input=s.encode('utf-8'), timeout=5)
            else:
                subprocess.run('clip', input=s.encode('utf-16-le'),
                               shell=True, timeout=5)
            return {'ok': True}
        except Exception as e:
            return {'ok': False, 'message': str(e)[:100]}


def _ver_cmp(a, b):
    """比较两个版本号 '1.2.3' → 返回 a>b?1 : a<b?-1 : 0"""
    pa = [int(x) for x in str(a).replace('v', '').split('.')]
    pb = [int(x) for x in str(b).replace('v', '').split('.')]
    while len(pa) < 3:
        pa.append(0)
    while len(pb) < 3:
        pb.append(0)
    for x, y in zip(pa, pb):
        if x != y:
            return 1 if x > y else -1
    return 0


def gateway_default_url():
    # 默认指向 MIAO 自研网关，不再回退到 new-api
    return getattr(gen_models, 'DEFAULT_URL', 'http://127.0.0.1:18085/v1')


def _probe_console(port, timeout=1.5):
    """探测本机指定端口是否已有 MIAO 控制台在跑（避免重复起服务、抢占 18300）"""
    try:
        st, body, _ = _http_get('http://127.0.0.1:%d/api/version' % port, timeout=timeout)
        if st != 200:
            return False
        d = json.loads(body.decode('utf-8', 'ignore'))
        return d.get('app_name') == APP_NAME or 'latest' in d
    except Exception:
        return False


def main():
    debug = '--debug' in sys.argv
    try:
        gateway.ensure_tables()
    except Exception as e:
        print('[!] 建表跳过:', e)

    port = gateway.find_port(gateway.START_PORT)
    srv = None
    if port != gateway.START_PORT and _probe_console(gateway.START_PORT):
        # 已有常驻控制台（能读网关库），直接复用，不再自带一份
        port = gateway.START_PORT
        print('[1] 复用已运行的 MIAO 控制台 http://127.0.0.1:%d' % port)
    else:
        srv = gateway.Server(('127.0.0.1', port), gateway.Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        print('[1] 本地服务 http://127.0.0.1:%d' % port)

    url = 'http://127.0.0.1:%d/app' % port
    win = webview.create_window(
        APP_NAME,
        url,
        width=500,
        height=668,
        min_size=(440, 620),
        background_color='#F4F6F9',
        text_select=True,
        js_api=Api(),
    )
    webview.start(
        debug=debug,
        private_mode=False,            # 关键：localStorage 落盘，密钥下次不再重登
        storage_path=APP_DATA,         # 持久化目录：~/.workbuddy/miao_app
    )
    if srv is not None:
        srv.shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())
