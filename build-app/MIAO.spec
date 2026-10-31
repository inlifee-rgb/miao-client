# -*- mode: python ; coding: utf-8 -*-
# onedir 打包：启动秒开（不再解压 37MB 临时目录）
# 路径全部基于 SPECPATH 计算 —— 本地 E:\ 和 GitHub Actions runner 都能跑
import os

from PyInstaller.utils.hooks import collect_all

ROOT = os.path.dirname(os.path.abspath(SPECPATH))   # 仓库根（console 目录）

FILES = [
    'ui.css', 'ui.js', 'index.html', 'app.html',
    'logo-h.svg', 'logo-dark.svg', 'logo-symbol.svg',
    'app-icon.png', 'favicon.ico', 'gen_models.py',
]
datas = [(os.path.join(ROOT, f), '.') for f in FILES if os.path.isfile(os.path.join(ROOT, f))]

binaries = []
hiddenimports = ['clr', 'webview.platforms.edgechromium']
for pkg in ('webview', 'pythonnet', 'clr_loader'):
    t = collect_all(pkg)
    datas += t[0]
    binaries += t[1]
    hiddenimports += t[2]


a = Analysis(
    [os.path.join(ROOT, 'app.py')],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,     # 标准 onedir：exe 只留引导器，秒开
    name='MIAO',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[os.path.join(ROOT, 'app.ico')],
)

# onedir：把依赖解压成目录，启动只加载不重复解压 → 打开秒开
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MIAO',
)
