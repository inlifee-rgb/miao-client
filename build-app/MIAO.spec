# -*- mode: python ; coding: utf-8 -*-
# onedir 打包：启动秒开（不再解压 37MB 临时目录）
from PyInstaller.utils.hooks import collect_all

datas = [('E:/dorimi/ai/wb_oauth/console/ui.css', '.'), ('E:/dorimi/ai/wb_oauth/console/ui.js', '.'), ('E:/dorimi/ai/wb_oauth/console/index.html', '.'), ('E:/dorimi/ai/wb_oauth/console/app.html', '.'), ('E:/dorimi/ai/wb_oauth/console/logo-h.svg', '.'), ('E:/dorimi/ai/wb_oauth/console/logo-dark.svg', '.'), ('E:/dorimi/ai/wb_oauth/console/logo-symbol.svg', '.'), ('E:/dorimi/ai/wb_oauth/console/app-icon.png', '.'), ('E:/dorimi/ai/wb_oauth/console/favicon.ico', '.'), ('E:/dorimi/ai/wb_oauth/gen_models.py', '.')]
binaries = []
hiddenimports = ['clr', 'webview.platforms.edgechromium']
tmp_ret = collect_all('webview')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pythonnet')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('clr_loader')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['../app.py'],
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
    icon=['E:/dorimi/ai/wb_oauth/console/app.ico'],
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
