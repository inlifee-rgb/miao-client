#!/bin/bash
# MIAO for WorkBuddy · macOS 一键配置
# 用法：双击运行，或在终端执行 bash miao_configure_mac.command
set -u
SERVER="http://103.236.73.61:18085"
CONSOLE="http://103.236.73.61:18300"

echo "===================================================="
echo "  MIAO for WorkBuddy · macOS 配置"
echo "===================================================="
echo

if [ -n "${1:-}" ]; then
  KEY="$1"
else
  printf "请输入你的 MIAO 密钥（sk- 开头）: "
  read -r KEY
fi

if [ -z "${KEY:-}" ]; then
  echo "❌ 未输入密钥，退出"
  exit 1
fi

echo
echo "[1/3] 从网关拉取模型清单..."
TMP=$(mktemp /tmp/miao_models.XXXXXX.json)
if ! curl -fsS --max-time 20 "$SERVER/download/models.json?key=$KEY" -o "$TMP"; then
  echo "❌ 密钥无效，或网络不通（${SERVER}）"
  rm -f "$TMP"
  exit 1
fi
COUNT=$(grep -c '"name"' "$TMP" 2>/dev/null || echo 0)
if [ "$COUNT" -lt 1 ]; then
  echo "❌ 返回内容异常，可能密钥无效"
  rm -f "$TMP"
  exit 1
fi
echo "    ✓ 拿到 $COUNT 个模型"

echo "[2/3] 写入 WorkBuddy 配置..."
STAMP=$(date +%Y%m%d-%H%M%S)
TARGETS="$HOME/.workbuddy/models.json"
if [ -d "$HOME/Library/Application Support/WorkBuddy" ]; then
  TARGETS="$TARGETS|$HOME/Library/Application Support/WorkBuddy/models.json"
fi

OLDIFS=$IFS
IFS='|'
for P in $TARGETS; do
  mkdir -p "$(dirname "$P")"
  if [ -f "$P" ]; then
    cp "$P" "$P.bak-$STAMP"
    echo "    已备份: $P.bak-$STAMP"
  fi
  cp "$TMP" "$P"
  echo "    ✓ 已写入: $P"
done
IFS=$OLDIFS
rm -f "$TMP"

echo "[3/3] 完成"
echo
echo "===================================================="
echo "  ✅ 配置写入成功"
echo "===================================================="
echo "  下一步：完全退出 WorkBuddy（⌘Q），再重新打开"
echo "  模型列表里会出现 Miao:* 系列"
echo
echo "  查余额 / 用量：$CONSOLE"
echo
printf "按回车关闭窗口..."
read -r _
