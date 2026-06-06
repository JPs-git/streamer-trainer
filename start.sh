#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_PID=""

cleanup() {
    if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo ""
        echo "🧹 正在关闭后端..."
        kill "$BACKEND_PID" 2>/dev/null || true
        wait "$BACKEND_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

echo "============================================"
echo "  主播培训弹幕系统"
echo "============================================"
echo ""

echo "🚀 启动后端..."
uv run python -m backend.main &
BACKEND_PID=$!

echo "⏳ 等待后端就绪..."
for i in $(seq 1 30); do
    if curl -s http://localhost:8765/ > /dev/null 2>&1; then
        echo "✅ 后端已就绪 → http://localhost:8765/"
        echo ""
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "❌ 后端启动超时"
        exit 1
    fi
    sleep 1
done

echo "💡 打开浏览器访问 http://localhost:8765/"
echo "   在页面底部输入框输入主播台词后发送即可触发弹幕生成"
echo ""
wait $BACKEND_PID
