#!/bin/bash
# macOS 打包脚本（必须在 macOS 上运行：bash build-app/build_mac.sh）
set -e
cd "$(dirname "$0")/.."

echo "[1/5] 环境检查"
command -v python3 >/dev/null || { echo "缺少 python3，请先装 Xcode Command Line Tools（xcode-select --install）"; exit 1; }
python3 -V
sw_vers | head -2

echo "[2/5] 虚拟环境"
[ -d .venv-mac ] || python3 -m venv .venv-mac
source .venv-mac/bin/activate

echo "[3/5] 安装依赖"
pip install -q --upgrade pip
pip install -q pyinstaller pywebview qrcode pillow

echo "[4/5] 生成 .icns 图标"
python3 build-app/make_icns.py

echo "[5/5] 打包 .app"
pyinstaller build-app/MIAO-mac.spec --noconfirm --clean

VER=$(awk -F"'" '/^APP_VERSION/{print $2; exit}' app.py)
echo "版本: $VER"
cd dist
rm -f "MIAO-mac-$VER.zip"
ditto -c -k --keepParent MIAO.app "MIAO-mac-$VER.zip"

echo
echo "完成：dist/MIAO.app  和  dist/MIAO-mac-$VER.zip"
echo
echo "分发前提醒：未签名的 App 在别人机器上会被 Gatekeeper 拦。"
echo "  · 内测：让用户右键 → 打开，或执行 xattr -dr com.apple.quarantine /Applications/MIAO.app"
echo "  · 正式：需要 Apple Developer 账号（99 美元/年）做 codesign + notarytool 公证"
