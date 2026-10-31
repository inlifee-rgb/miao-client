# -*- mode: python ; coding: utf-8 -*-
# macOS 打包：在 Mac 上执行 build_mac.sh 生成 MIAO.app
import os
from PyInstaller.utils.hooks import collect_all

# 仓库根 = SPECPATH 的上一级（spec 位于 <repo>/build-app/）
ROOT = os.path.dirname(os.path.abspath(SPECPATH))
D = lambda *p: os.path.join(ROOT, *p)

datas = [
    (D('ui.css'), '.'), (D('ui.js'), '.'), (D('index.html'), '.'), (D('app.html'), '.'),
    (D('logo-h.svg'), '.'), (D('logo-dark.svg'), '.'), (D('logo-symbol.svg'), '.'),
    (D('app-icon.png'), '.'), (D('favicon.ico'), '.'),
    (D('gen_models.py') if os.path.isfile(D('gen_models.py')) else os.path.join(os.path.dirname(ROOT), 'gen_models.py'), '.'),
]
binaries = []
hiddenimports = []
for pkg in ('webview',):
    t = collect_all(pkg)
    datas += t[0]; binaries += t[1]; hiddenimports += t[2]

a = Analysis([D('app.py')], pathex=[], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports, hookspath=[], hooksconfig={},
             runtime_hooks=[], excludes=[], noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='MIAO',
          debug=False, strip=False, upx=False, console=False, icon=D('app.icns'))
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=False, name='MIAO')
app = BUNDLE(coll, name='MIAO.app', icon=D('app.icns'),
             bundle_identifier='cn.dorimi.miao',
             info_plist={
                 'CFBundleName': 'MIAO',
                 'CFBundleDisplayName': 'MIAO for WorkBuddy',
                 'CFBundleShortVersionString': '1.1.4',
                 'CFBundleVersion': '1.1.4',
                 'NSHighResolutionCapable': True,
                 'LSMinimumSystemVersion': '11.0',
             })
