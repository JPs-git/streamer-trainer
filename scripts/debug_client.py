"""
调试客户端 — 无需 OBS，在终端里模拟主播说话。

用法：
  1. 先启动后端：uv run python -m backend.main
  2. 再运行本脚本：uv run python scripts/debug_client.py

在浏览器打开 http://localhost:8765/ 实时查看弹幕。
"""

import asyncio
import json
import sys

import httpx
import websockets


BACKEND = "http://localhost:8765"
WS_DANMAKU = "ws://localhost:8765/danmaku"


async def listen_danmaku():
    """连接 /danmaku WS 并打印收到的消息。"""
    while True:
        try:
            async with websockets.connect(WS_DANMAKU) as ws:
                while True:
                    msg = json.loads(await ws.recv())
                    msg_type = msg.get("type", "?")
                    if msg_type == "danmaku":
                        name = msg.get("name", "?")
                        text = msg.get("text", "")
                        effect = msg.get("effect", "")
                        prefix = "⚠ " if effect == "highlight" else "  "
                        print(f"  {prefix}{name}: {text}")
                    elif msg_type == "system":
                        action = msg.get("action", "")
                        name = msg.get("name", "")
                        icon = "🟢" if action == "enter" else "🔴"
                        print(f"  {icon} {name} {action}")
        except Exception:
            print("  [WS 断开，3秒后重连]", file=sys.stderr)
            await asyncio.sleep(3)


async def main():
    print("=" * 50)
    print("主播培训弹幕系统 — 调试客户端")
    print("=" * 50)
    print()
    print(f"后端: {BACKEND}")
    print(f"前端: {BACKEND}/")
    print()
    print("输入主播说的话，按回车发送。输入 /quit 退出。")
    print()

    # 启动 WS 监听
    asyncio.create_task(listen_danmaku())
    await asyncio.sleep(0.5)

    async with httpx.AsyncClient() as client:
        while True:
            try:
                line = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: sys.stdin.readline().strip()
                )
            except (EOFError, KeyboardInterrupt):
                break

            if not line:
                continue
            if line == "/quit":
                break

            try:
                r = await client.post(
                    f"{BACKEND}/debug_text",
                    json={"text": line},
                    timeout=10,
                )
                if r.status_code == 200:
                    print(f"  ✅ 已发送")
                else:
                    print(f"  ❌ 错误: {r.status_code} {r.text}")
            except Exception as e:
                print(f"  ❌ 请求失败: {e}")


if __name__ == "__main__":
    asyncio.run(main())
