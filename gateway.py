"""MIAO Console 后端（本地/内网单文件服务）

职责：
  1. 托管 console/ 下的静态页面（index.html = 网页控制台，app.html = 桌面 App）
  2. /api/me*        按用户自己的 sk- 密钥查余额、用量、调用明细、密钥列表
  3. /api/me/redeem  兑换码充值（自有表 dorimi_redeem，不动 new-api 内部逻辑）
  4. /api/me/order   充值下单（自有表 dorimi_orders；支付回调 /api/pay/notify 预留）

为什么不用 new-api 自带的令牌接口：
  new-api 的 /api/user/* 需要用户级 access_token（登录后才有），而客户手上只有 sk- 密钥。
  这里用密钥反查 user_id，再用管理员库连接取数，客户体验最轻。

用法：
  python gateway.py                # 默认 18300 起找空端口
  python gateway.py --port 18300
"""
import argparse
import base64
import io
import json
import os
import re
import socketserver
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler

import sys as _sys

if getattr(_sys, 'frozen', False):
    # PyInstaller 单文件：页面被打进 _MEIPASS
    BASE = getattr(_sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    WEB = BASE
else:
    BASE = os.path.dirname(os.path.abspath(__file__))
    # gateway.py 与页面同目录；若被放到别处，则退回到 ./console
    WEB = BASE if os.path.isfile(os.path.join(BASE, 'index.html')) else os.path.join(BASE, 'console')
START_PORT = 18300
# MIAO 网关目录（version.json / downloads / miao.db 所在）；容器部署时用环境变量指定
MIAO_HOME = os.environ.get('MIAO_HOME') or os.path.join(BASE, '..', '..', 'miao_gateway')

DB_CONTAINER = 'dorimi-ai-mysql'
DB_USER = 'tangyuan'
DB_PASS = '05cc291dd0394f9ad5834eab00beb900b6fda8f1b8a002c7'
DB_NAME = 'tangyuan'

# 1 积分 = QUOTA_PER_CREDIT 个 new-api quota（QuotaPerUnit=10000 时）
QUOTA_PER_CREDIT = 10000

_CACHE = {}
_cache_lock = threading.Lock()


# ---------------------------------------------------------------- DB

def sql(query, want_rows=False, timeout=25):
    cmd = ['docker', 'exec', DB_CONTAINER, 'mysql',
           '-u' + DB_USER, '-p' + DB_PASS, DB_NAME,
           '--default-character-set=utf8mb4', '-N', '-B', '-e', query]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=timeout, encoding='utf-8', errors='replace')
    except Exception as e:
        raise RuntimeError('数据库不可用: %s' % e)
    lines = [l for l in (out.stdout or '').splitlines() if 'Warning' not in l]
    if out.returncode != 0 and not lines:
        raise RuntimeError((out.stderr or 'mysql 失败').strip()[:200])
    return lines if want_rows else None


def q(sql_text):
    return sql(sql_text, want_rows=True) or []


def esc(s):
    return str(s).replace('\\', '\\\\').replace("'", "\\'")


def raw_key(k):
    k = (k or '').strip()
    return k[3:] if k.startswith('sk-') else k


def cached(name, ttl, fn):
    now = time.time()
    with _cache_lock:
        hit = _CACHE.get(name)
        if hit and now - hit[0] < ttl:
            return hit[1]
    v = fn()
    with _cache_lock:
        _CACHE[name] = (now, v)
    return v


def ensure_tables():
    """2026-10-30 起数据源为 MIAO 网关 SQLite（不再依赖 new-api MySQL 容器）"""
    try:
        import sqlite3
        gw = os.path.join(BASE, '..', '..', 'miao_gateway', 'miao.db')
        if not os.path.exists(gw):
            gw = os.path.join(os.path.dirname(BASE), 'miao_gateway', 'miao.db')
        conn = sqlite3.connect(gw, timeout=20)
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL, key TEXT NOT NULL UNIQUE, model TEXT DEFAULT '',
                quota INTEGER DEFAULT -1, used INTEGER DEFAULT 0,
                enabled INTEGER DEFAULT 1, created_at INTEGER DEFAULT 0,
                last_used INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS redeem (
                code TEXT PRIMARY KEY, points INTEGER NOT NULL, note TEXT DEFAULT '',
                used_by TEXT DEFAULT '', used_at INTEGER DEFAULT 0, created_at INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT, out_trade_no TEXT UNIQUE,
                key_name TEXT NOT NULL, amount REAL DEFAULT 0, points INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending', created_at INTEGER DEFAULT 0, paid_at INTEGER DEFAULT 0
            );
        ''')
        conn.commit()
        conn.close()
    except Exception as e:
        print('[!] 网关表初始化跳过:', e)


# ---------------------------------------------------------------- 业务

def _gw_db():
    """MIAO 网关 SQLite（自研分发后端，2026-10-30 起替代 new-api MySQL）

    路径解析必须兼容两种运行形态：
      · 源码运行：BASE = console/            → ../../miao_gateway/miao.db
      · 打包运行：BASE = dist/_internal      → 逐级向上找不到，需遍历探测
    """
    import sqlite3
    cands = []
    env = os.environ.get('MIAO_DB_PATH')
    if env:
        cands.append(env)
    cands.append(os.path.join(MIAO_HOME, 'miao.db'))
    cands.append(os.path.join(BASE, '..', '..', 'miao_gateway', 'miao.db'))
    cands.append(os.path.join(os.path.dirname(BASE), 'miao_gateway', 'miao.db'))
    # 打包形态：从 BASE 一路向上找到盘符根（dist/_internal → dist → console → wb_oauth → ai）
    cur = BASE
    while True:
        cands.append(os.path.join(cur, 'miao_gateway', 'miao.db'))
        nxt = os.path.dirname(cur)
        if nxt == cur:
            break
        cur = nxt
    # 本机部署兜底（客户机不存在该路径时跳过）
    cands.append(r'E:\dorimi\ai\miao_gateway\miao.db')
    for c in cands:
        if c and os.path.isfile(c):
            conn = sqlite3.connect(c, timeout=20)
            conn.row_factory = sqlite3.Row
            return conn
    raise FileNotFoundError('miao.db not found; tried: %s' % '; '.join(cands[:6]))


def model_list():
    """从 MIAO 网关 models.json 读模型 + 费率"""
    try:
        gw_models = os.path.join(BASE, '..', '..', 'miao_gateway', 'models.json')
        if not os.path.exists(gw_models):
            gw_models = os.path.join(os.path.dirname(BASE), 'miao_gateway', 'models.json')
        data = json.load(open(gw_models, encoding='utf-8'))
        out = []
        for mid, rate in data:
            t = '免费' if rate == 0 else ('%.2f' % rate).rstrip('0').rstrip('.') + 'x'
            out.append({'id': mid, 'rate': t})
        return out
    except Exception:
        return [{'id': 'deepseek-v4.1-flash', 'rate': '0.11x'}]


def find_me(key):
    rk = (key or '').strip()
    if not rk:
        return None
    try:
        conn = _gw_db()
        try:
            r = conn.execute('SELECT * FROM keys WHERE key=?', (rk,)).fetchone()
        finally:
            conn.close()
    except Exception:
        return None
    if not r or not r['enabled']:
        return None
    unlimited = r['quota'] < 0
    remain = -1 if unlimited else (r['quota'] - r['used'])
    return {
        'ok': True,
        'user_id': r['id'],
        'username': r['name'],
        'display_name': r['name'],
        'quota': round(remain / QUOTA_PER_CREDIT, 4) if not unlimited else -1,
        'used_quota': round(r['used'] / QUOTA_PER_CREDIT, 4),
        'request_count': None,
        'status': 1 if r['enabled'] else 0,
        'unlimited': unlimited,
    }


def me_logs(key, limit=12):
    me = find_me(key)
    if not me:
        return []
    try:
        conn = _gw_db()
        try:
            rows = conn.execute(
                'SELECT created_at,model,prompt_tokens,completion_tokens,quota FROM logs '
                'WHERE key_name=? ORDER BY id DESC LIMIT ?', (me['username'], int(limit))).fetchall()
        finally:
            conn.close()
    except Exception:
        return []
    out = []
    for r in rows:
        out.append({
            'time': time.strftime('%m-%d %H:%M', time.localtime(r['created_at'] or 0)),
            'model': r['model'],
            'prompt_tokens': r['prompt_tokens'],
            'completion_tokens': r['completion_tokens'],
            'credits': round((r['quota'] or 0) / QUOTA_PER_CREDIT, 4),
        })
    return out


def me_tokens(key):
    me = find_me(key)
    if not me:
        return []
    try:
        conn = _gw_db()
        try:
            r = conn.execute('SELECT * FROM keys WHERE key=?', ((key or '').strip(),)).fetchone()
        finally:
            conn.close()
    except Exception:
        return []
    if not r:
        return []
    k = r['key']
    return [{
        'name': r['name'],
        'masked': (k[:6] + '••••••' + k[-4:]) if len(k) > 12 else k,
        'unlimited': r['quota'] < 0,
        'remain': round((r['quota'] - r['used']) / QUOTA_PER_CREDIT, 4) if r['quota'] >= 0 else -1,
        'used': round(r['used'] / QUOTA_PER_CREDIT, 4),
    }]


def redeem(key, code):
    me = find_me(key)
    if not me:
        return {'ok': False, 'message': '密钥无效'}
    code = (code or '').strip().upper()
    if not code:
        return {'ok': False, 'message': '请输入兑换码'}
    ok, msg, pts = _gw_redeem((key or '').strip(), code)
    if ok:
        _CACHE.clear()
    return {'ok': ok, 'message': msg, 'added': pts if ok else 0}


def _gw_redeem(key, code):
    try:
        import sqlite3
        conn = _gw_db()
        try:
            r = conn.execute('SELECT code,points,used_by FROM redeem WHERE code=?', (code,)).fetchone()
            if not r:
                return False, '兑换码不存在', 0
            if r['used_by']:
                return False, '该兑换码已被使用', 0
            conn.execute('UPDATE redeem SET used_by=?, used_at=? WHERE code=? AND used_by=""',
                         (key, int(time.time()), code))
            conn.execute('UPDATE keys SET quota=CASE WHEN quota<0 THEN quota ELSE quota+? END WHERE key=?',
                         (r['points'] * QUOTA_PER_CREDIT, key))
            conn.commit()
            return True, '充值成功', r['points']
        finally:
            conn.close()
    except Exception as e:
        return False, '网关不可用: %s' % str(e)[:80], 0


def create_order(key, amount, points):
    me = find_me(key)
    if not me:
        return {'ok': False, 'message': '密钥无效'}
    ok, no = _gw_order((key or '').strip(), amount, points)
    if not ok:
        return {'ok': False, 'message': '下单失败'}
    return {
        'ok': True,
        'order': no,
        'amount': amount,
        'points': points,
        'pay_url': '',
        'message': '订单 %s 已创建。微信支付通道尚未接入商户号，请联系客服凭订单号支付。' % no,
    }


def _gw_order(key, amount, points):
    try:
        conn = _gw_db()
        try:
            no = 'DM%d%s' % (int(time.time()), str(abs(hash(key)) % 1000).zfill(3))
            conn.execute('INSERT INTO orders(out_trade_no,key_name,amount,points,status,created_at) '
                         'VALUES(?,?,?,?,?,?)',
                         (no, key, float(amount), int(points), 'pending', int(time.time())))
            conn.commit()
            return True, no
        finally:
            conn.close()
    except Exception:
        return False, ''


def qr_png(text, box=8):
    try:
        import qrcode
        img = qrcode.make(text, border=2, box_size=box)
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return buf.getvalue()
    except Exception:
        return None


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = 'MiaoConsole/1.0'

    def log_message(self, fmt, *a):
        if os.environ.get('MIAO_DEBUG'):
            sys.stderr.write('%s - %s\n' % (self.address_string(), fmt % a))

    # ---------- helpers
    def _send(self, code, body, ctype='application/json; charset=utf-8', extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode('utf-8')
        elif isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _file(self, rel):
        p = os.path.join(WEB, rel)
        if not os.path.isfile(p):
            return self._send(404, {'ok': False, 'message': 'not found'})
        ext = os.path.splitext(p)[1].lower()
        ctype = {'.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8',
                 '.js': 'application/javascript; charset=utf-8',
                 '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml',
                 '.json': 'application/json; charset=utf-8'}.get(ext, 'application/octet-stream')
        with open(p, 'rb') as f:
            self._send(200, f.read(), ctype)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        path = u.path
        qs = urllib.parse.parse_qs(u.query)
        key = (qs.get('key') or [''])[0]

        try:
            if path in ('/', '/index.html'):
                return self._file('index.html')
            if path == '/app':
                return self._file('app.html')
            if path == '/api/models':
                return self._send(200, {'models': model_list()})
            if path == '/api/version':
                # 转发到 MIAO 网关的版本清单（桌面 App / 网页控制台共用检测更新）
                try:
                    gw = os.path.join(MIAO_HOME, 'version.json')
                    if not os.path.isfile(gw):
                        gw = os.path.join(BASE, '..', '..', 'miao_gateway', 'version.json')
                    if not os.path.isfile(gw):
                        gw = os.path.join(os.path.dirname(BASE), 'miao_gateway', 'version.json')
                    v = json.load(open(gw, encoding='utf-8'))
                    v['ok'] = True
                    return self._send(200, v)
                except Exception as e:
                    return self._send(500, {'ok': False, 'message': str(e)[:120]})
            if path.startswith('/download/'):
                # 客户端安装包下载（从 MIAO 网关 downloads 目录）
                name = os.path.basename(path[len('/download/'):])
                gw_dl = os.path.join(MIAO_HOME, 'downloads', name)
                if not os.path.isfile(gw_dl):
                    gw_dl = os.path.join(BASE, '..', '..', 'miao_gateway', 'downloads', name)
                if not os.path.isfile(gw_dl):
                    gw_dl = os.path.join(os.path.dirname(BASE), 'miao_gateway', 'downloads', name)
                if not os.path.isfile(gw_dl) or '..' in name:
                    return self._send(404, {'ok': False, 'message': '安装包不存在'})
                size = os.path.getsize(gw_dl)
                with open(gw_dl, 'rb') as f:
                    blob = f.read()
                return self._send(200, blob, 'application/octet-stream',
                                  extra={'Content-Disposition': 'attachment; filename="%s"' % name,
                                         'Cache-Control': 'no-cache'})
            if path == '/api/me':
                me = cached('me:' + raw_key(key), 3, lambda: find_me(key))
                if not me:
                    return self._send(200, {'ok': False, 'message': '密钥无效或已停用'})
                return self._send(200, me)
            if path == '/api/me/logs':
                lim = int((qs.get('limit') or ['12'])[0])
                return self._send(200, {'rows': me_logs(key, min(lim, 100))})
            if path == '/api/me/tokens':
                return self._send(200, {'rows': me_tokens(key)})
            if path == '/qr.png':
                custom = os.path.join(WEB, 'service-qr.png')
                if os.path.isfile(custom):
                    with open(custom, 'rb') as f:
                        return self._send(200, f.read(), 'image/png')
                cfg = os.path.join(WEB, 'service.json')
                text = 'http://127.0.0.1:18085/v1'   # MIAO 自研网关地址（扫码配置 WorkBuddy 模型用）
                if os.path.isfile(cfg):
                    try:
                        text = json.load(open(cfg, encoding='utf-8')).get('qr_text', text)
                    except Exception:
                        pass
                png = qr_png(text)
                if not png:
                    return self._send(404, {'ok': False})
                return self._send(200, png, 'image/png')
            # 静态
            safe = path.lstrip('/')
            if '..' not in safe and safe:
                return self._file(safe)
            return self._send(404, {'ok': False, 'message': 'not found'})
        except Exception as e:
            return self._send(500, {'ok': False, 'message': str(e)[:200]})

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        try:
            n = int(self.headers.get('Content-Length') or 0)
            body = json.loads(self.rfile.read(n).decode('utf-8') or '{}') if n else {}
        except Exception:
            body = {}

        try:
            if u.path == '/api/me/redeem':
                return self._send(200, redeem(body.get('key'), body.get('code')))
            if u.path == '/api/me/order':
                return self._send(200, create_order(
                    body.get('key'), body.get('amount', 0), body.get('points', 0)))
            return self._send(404, {'ok': False, 'message': 'not found'})
        except Exception as e:
            return self._send(500, {'ok': False, 'message': str(e)[:200]})


class Server(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def find_port(start):
    import socket
    for p in range(start, start + 40):
        with socket.socket() as s:
            if s.connect_ex(('127.0.0.1', p)) != 0:
                return p
    return start


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=0)
    ap.add_argument('--bind', default='127.0.0.1')   # 容器部署传 0.0.0.0
    ap.add_argument('--no-browser', action='store_true')
    a = ap.parse_args()

    if not os.path.isdir(WEB):
        print('[X] 找不到页面目录:', WEB)
        return 1
    try:
        ensure_tables()
        print('[1] 数据表就绪（dorimi_redeem / dorimi_orders）')
    except Exception as e:
        print('[!] 建表跳过:', e)

    port = a.port or find_port(START_PORT)
    srv = Server((a.bind, port), Handler)
    url = 'http://%s:%d/' % (a.bind, port)
    print('[2] MIAO Console 已启动: %s' % url)
    print('    页面目录:', WEB)
    if not a.no_browser:
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\n已停止')
    return 0


if __name__ == '__main__':
    sys.exit(main())
